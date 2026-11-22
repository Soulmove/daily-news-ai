"""Shared connector utilities: domain rate limiting, ETag/Last-Modified cache, and honest error states."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests

from pipeline.manifest import atomic_write_json, load_json_if_exists
from pipeline.time_utils import now_shanghai, to_iso_shanghai

DEFAULT_USER_AGENT = "InsightPro-V3-ResearchBot/3.0 (https://github.com/Soulmove/daily-news-ai)"
SEC_EDGAR_USER_AGENT = "SoulmoveDailyNewsAI/3.0 (research-contact@soulmove.org)"
HTTP_CACHE_PATH = Path("data/http_cache.json")


class DomainRateLimiter:
    """Thread-safe per-domain minimum interval rate limiter."""

    def __init__(self, default_interval_sec: float = 0.45) -> None:
        self.default_interval = default_interval_sec
        self._lock = threading.Lock()
        self._last_request_at: Dict[str, float] = {}
        self._domain_intervals: Dict[str, float] = {
            "data.sec.gov": 0.25,       # SEC allows max 10 req/s; stay very conservative
            "api.github.com": 0.35,
            "huggingface.co": 0.35,
            "export.arxiv.org": 1.0,    # arXiv asks for polite spacing between queries
            "www1.hkexnews.hk": 0.6,
            "www.cninfo.com.cn": 0.6,
        }

    def wait(self, url: str) -> None:
        host = (urlparse(url).netloc or "").lower()
        interval = self._domain_intervals.get(host, self.default_interval)
        with self._lock:
            now = time.monotonic()
            prev = self._last_request_at.get(host, 0.0)
            wait_sec = interval - (now - prev)
            if wait_sec > 0:
                time.sleep(wait_sec)
            self._last_request_at[host] = time.monotonic()


class HttpCacheStore:
    """Bounded persistent ETag / Last-Modified cache stored in data/http_cache.json."""

    def __init__(self, base_dir: Path | str = ".") -> None:
        self.path = Path(base_dir) / HTTP_CACHE_PATH
        self._lock = threading.Lock()
        raw = load_json_if_exists(self.path, default={})
        self.entries: Dict[str, Dict[str, Any]] = raw if isinstance(raw, dict) else {}

    def get_conditional_headers(self, url: str) -> Dict[str, str]:
        with self._lock:
            entry = self.entries.get(url)
            if not isinstance(entry, dict):
                return {}
            hdrs: Dict[str, str] = {}
            if entry.get("etag"):
                hdrs["If-None-Match"] = str(entry["etag"])
            if entry.get("last_modified"):
                hdrs["If-Modified-Since"] = str(entry["last_modified"])
            return hdrs

    def get_cached_summary(self, url: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self.entries.get(url)
            return dict(entry) if isinstance(entry, dict) else None

    def update(self, url: str, resp: requests.Response) -> None:
        etag = resp.headers.get("ETag")
        last_mod = resp.headers.get("Last-Modified")
        rec = {
            "etag": etag,
            "last_modified": last_mod,
            "checked_at": to_iso_shanghai(now_shanghai()),
            "http_status": resp.status_code,
        }
        with self._lock:
            self.entries[url] = rec

    def save(self, max_entries: int = 400) -> None:
        with self._lock:
            if len(self.entries) > max_entries:
                keys = sorted(
                    self.entries.keys(),
                    key=lambda k: str(self.entries[k].get("checked_at") or ""),
                    reverse=True,
                )[:max_entries]
                self.entries = {k: self.entries[k] for k in keys}
            atomic_write_json(self.path, self.entries)


def repair_mojibake(text: str) -> str:
    """Safely recover UTF-8 Chinese text accidentally decoded as Latin-1/Windows-1252."""
    if not text or not any(marker in text for marker in ("æ", "ç", "å", "ï¼", "ã")):
        return text
    try:
        fixed = text.encode("latin-1").decode("utf-8")
        if any("\u4e00" <= ch <= "\u9fff" for ch in fixed):
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return text


def _decode_http_bytes(raw_bytes: bytes, resp: requests.Response) -> str:
    if not raw_bytes:
        return ""
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes.decode("utf-8-sig", errors="replace")
    meta_m = re.search(br'charset=["\']?([a-zA-Z0-9_-]+)', raw_bytes[:4096], re.I)
    meta_charset = meta_m.group(1).decode("ascii", errors="ignore").lower() if meta_m else ""
    if meta_charset and meta_charset not in {"iso-8859-1", "latin-1", "latin1"}:
        try:
            return raw_bytes.decode(meta_charset, errors="replace").lstrip("\ufeff")
        except LookupError:
            pass
    # Always try strict UTF-8 before chardet/apparent_encoding to prevent Latin-1 mojibake on CJK HTML
    try:
        return raw_bytes.decode("utf-8", errors="strict").lstrip("\ufeff")
    except UnicodeDecodeError:
        enc = resp.apparent_encoding or resp.encoding or "utf-8"
        return raw_bytes.decode(enc, errors="replace").lstrip("\ufeff")


_GLOBAL_LIMITER = DomainRateLimiter()


@dataclass
class FetchResult:
    ok: bool
    status: str  # "ok" | "not_modified_304" | "rate_limited" | "blocked_or_restricted" | "error"
    http_status: Optional[int]
    text: Optional[str]
    latency_ms: int
    from_cache: bool = False
    error_message: Optional[str] = None
    json_data: Any = None
    final_url: Optional[str] = None


def polite_get(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    cache: Optional[HttpCacheStore] = None,
    timeout: Tuple[int, int] = (5, 10),
    retries: int = 2,
    expect_json: bool = False,
) -> FetchResult:
    """Perform a rate-limited, conditional HTTP GET with honest error classification."""
    req_headers: Dict[str, str] = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        req_headers.update(headers)
    if cache is not None:
        req_headers.update(cache.get_conditional_headers(url))

    last_err: Optional[str] = None
    last_code: Optional[int] = None
    t0 = time.monotonic()

    for attempt in range(retries):
        _GLOBAL_LIMITER.wait(url)
        try:
            resp = requests.get(url, headers=req_headers, params=params, timeout=timeout)
            latency_ms = int((time.monotonic() - t0) * 1000)
            last_code = resp.status_code

            if resp.status_code == 304:
                return FetchResult(
                    ok=True,
                    status="not_modified_304",
                    http_status=304,
                    text=None,
                    latency_ms=latency_ms,
                    from_cache=True,
                )

            if resp.status_code == 200:
                if cache is not None:
                    cache.update(url, resp)
                decoded_text = _decode_http_bytes(resp.content or b"", resp)
                parsed_json = None
                if expect_json:
                    try:
                        parsed_json = resp.json()
                    except ValueError as exc:
                        return FetchResult(
                            ok=False,
                            status="error",
                            http_status=200,
                            text=decoded_text[:300],
                            latency_ms=latency_ms,
                            error_message=f"JSON 解析失败: {exc}",
                        )
                return FetchResult(
                    ok=True,
                    status="ok",
                    http_status=200,
                    text=decoded_text,
                    latency_ms=latency_ms,
                    json_data=parsed_json,
                    final_url=str(getattr(resp, "url", "") or "").strip() or None,
                )

            if resp.status_code == 429:
                last_err = "触发限流 (HTTP 429)"
                if attempt < retries - 1:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                return FetchResult(
                    ok=False,
                    status="rate_limited",
                    http_status=429,
                    text=None,
                    latency_ms=latency_ms,
                    error_message=last_err,
                )

            if resp.status_code in {401, 403, 451}:
                return FetchResult(
                    ok=False,
                    status="blocked_or_restricted",
                    http_status=resp.status_code,
                    text=None,
                    latency_ms=latency_ms,
                    error_message=f"访问受限/需授权或反爬拦截 (HTTP {resp.status_code})",
                )

            last_err = f"HTTP {resp.status_code}"
            if resp.status_code < 500:
                return FetchResult(
                    ok=False,
                    status="error",
                    http_status=resp.status_code,
                    text=None,
                    latency_ms=latency_ms,
                    error_message=last_err,
                )
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__}: {str(exc)[:140]}"
            if attempt < retries - 1:
                time.sleep(1.2 * (attempt + 1))

    return FetchResult(
        ok=False,
        status="error",
        http_status=last_code,
        text=None,
        latency_ms=int((time.monotonic() - t0) * 1000),
        error_message=last_err or "请求失败",
    )
