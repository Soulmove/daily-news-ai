"""Proactive AI & Global Breaking News Hunter powered by GitHub Actions Gemini + Google Search Grounding.

Uses `pipeline.gemini_pool` across all 13 configured Secrets with:
  - CI-persistent throttle cache (`data/gemini_hunter_cache.json`, 90-minute interval)
  - Real `published_date` preservation & 7-day staleness filtering (never stamping fetched_at as pubDate)
  - Grounding chunk extraction + concurrent HTTP URL reachability & domain/source sanity verification
  - Graceful degraded cache fallback + structured per-key quota diagnostics
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from pipeline.connectors.base import HttpCacheStore
from pipeline.gemini_pool import call_gemini_raw, collect_api_key_slots
from pipeline.id_utils import canonicalize_url, is_generic_quote_or_homepage_url, make_raw_item_id
from pipeline.manifest import atomic_write_json, load_json_if_exists
from pipeline.time_utils import now_shanghai, parse_iso_datetime, parse_published_at, to_iso_shanghai

THROTTLE_SECONDS = 5400  # 90 minutes -> max ~16 search grounding cycles/day
DEGRADED_FALLBACK_MAX_AGE_SECONDS = 12 * 3600  # up to 12h fallback cache on 429/exhaustion
STALE_AGE_HOURS = 168.0  # reject search results older than 7 days

_VERIFY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_HOST_LABEL_MAP = {
    "reuters.com": ("Reuters", "reuters"),
    "bloomberg.com": ("Bloomberg", "bloomberg"),
    "cnbc.com": ("CNBC", "cnbc"),
    "ft.com": ("Financial Times", "ft"),
    "wsj.com": ("Wall Street Journal", "wsj"),
    "apnews.com": ("Associated Press", "apnews"),
    "bbc.com": ("BBC", "bbc"),
    "bbc.co.uk": ("BBC", "bbc"),
    "aljazeera.com": ("Al Jazeera", "aljazeera"),
    "nytimes.com": ("New York Times", "nytimes"),
    "theguardian.com": ("The Guardian", "guardian"),
    "techcrunch.com": ("TechCrunch", "techcrunch"),
    "theverge.com": ("The Verge", "theverge"),
    "arstechnica.com": ("Ars Technica", "arstechnica"),
    "scmp.com": ("South China Morning Post", "scmp"),
    "zaobao.com": ("联合早报", "zaobao"),
    "wallstreetcn.com": ("华尔街见闻", "wallstreetcn"),
    "cls.cn": ("财联社", "cls"),
    "openai.com": ("OpenAI", "openai"),
    "anthropic.com": ("Anthropic", "anthropic"),
    "deepmind.google": ("Google DeepMind", "google"),
    "blog.google": ("Google Blog", "google"),
    "x.ai": ("xAI", "xai"),
    "sec.gov": ("SEC EDGAR", "sec-edgar"),
    "github.com": ("GitHub", "github"),
    "huggingface.co": ("Hugging Face", "huggingface"),
    "icj-cij.org": ("International Court of Justice", "icj"),
}


def _collect_all_keys() -> List[str]:
    return [s.secret for s in collect_api_key_slots()]


def _extract_grounding_chunks(resp: Any) -> List[Dict[str, str]]:
    chunks_out: List[Dict[str, str]] = []
    candidates = getattr(resp, "candidates", None) or []
    for cand in candidates:
        gm = getattr(cand, "grounding_metadata", None) or (cand.get("grounding_metadata") if isinstance(cand, dict) else None)
        if not gm:
            continue
        raw_chunks = getattr(gm, "grounding_chunks", None) or (gm.get("grounding_chunks") if isinstance(gm, dict) else None) or []
        for ch in raw_chunks:
            web = getattr(ch, "web", None) or (ch.get("web") if isinstance(ch, dict) else None)
            if not web:
                continue
            uri = str(getattr(web, "uri", None) or (web.get("uri") if isinstance(web, dict) else "") or "").strip()
            title = str(getattr(web, "title", None) or (web.get("title") if isinstance(web, dict) else "") or "").strip()
            if uri and uri.startswith(("http://", "https://")):
                chunks_out.append({"uri": uri, "title": title})
    return chunks_out


def _host_matches_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _derive_source_from_host(resolved_url: str, claimed_source: str, chunk_title: str = "") -> Tuple[str, str]:
    try:
        host = urlparse(resolved_url).netloc.lower().removeprefix("www.")
    except Exception:
        host = ""
    for dom, (label, fam) in _HOST_LABEL_MAP.items():
        if _host_matches_domain(host, dom):
            # If claimed source is consistent with label or Chinese alias, preserve claimed; otherwise use authoritative label
            if claimed_source and (label.lower() in claimed_source.lower() or fam in claimed_source.lower() or len(claimed_source) <= 18):
                return claimed_source, fam
            return label, fam

    clean_chunk = chunk_title.strip()
    if clean_chunk and "." in clean_chunk and len(clean_chunk) <= 40:
        fam_slug = re.sub(r"[^a-z0-9]", "", host.split(".")[0])[:16] or "web"
        return claimed_source or clean_chunk, f"gsearch-{fam_slug}"

    fam_slug = re.sub(r"[^a-z0-9]", "", (host.split(".")[0] if host else claimed_source.lower()))[:16] or "web"
    return (claimed_source or host or "Google Search Grounding"), f"gsearch-{fam_slug}"


def _probe_url(raw_url: str) -> Optional[str]:
    """Verify HTTP reachability and resolve redirects (e.g. vertexaisearch redirect -> publisher URL)."""
    if not raw_url or not raw_url.startswith(("http://", "https://")):
        return None
    try:
        resp = requests.head(raw_url, headers=_VERIFY_HEADERS, allow_redirects=True, timeout=(3, 5))
        if resp.status_code in (403, 405, 501):
            resp = requests.get(raw_url, headers=_VERIFY_HEADERS, allow_redirects=True, stream=True, timeout=(3, 6))
            try:
                status_ok = 200 <= resp.status_code < 400
                final_url = str(resp.url or raw_url)
            finally:
                resp.close()
        else:
            status_ok = 200 <= resp.status_code < 400
            final_url = str(resp.url or raw_url)
        if not status_ok:
            return None
        canon = canonicalize_url(final_url)
        if not canon or "vertexaisearch.cloud.google.com" in canon:
            return None
        if is_generic_quote_or_homepage_url(canon, "gemini-search-hunter"):
            return None
        return canon
    except Exception:
        return None


def _match_chunk_for_row(title: str, source_name: str, chunks: List[Dict[str, str]]) -> List[str]:
    if not chunks:
        return []
    t_toks = set(re.findall(r"[a-z0-9]{3,}", title.lower()))
    s_low = source_name.lower()
    scored: List[Tuple[int, str]] = []
    for ch in chunks:
        ch_t = (ch.get("title") or "").lower()
        ch_u = ch.get("uri") or ""
        score = 0
        if s_low and (s_low in ch_t or s_low.replace(" ", "") in ch_u.lower()):
            score += 4
        c_toks = set(re.findall(r"[a-z0-9]{3,}", ch_t + " " + ch_u.lower()))
        score += len(t_toks & c_toks)
        if score > 0:
            scored.append((score, ch_u))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [u for _, u in scored[:3]]


def _verify_and_resolve_candidate(row: Dict[str, Any], chunks: List[Dict[str, str]]) -> Optional[Tuple[str, str, str]]:
    """Return (verified_url, resolved_source_name, publisher_family) or None if no valid reachable URL exists."""
    raw_u = str(row.get("url") or "").strip()
    title = str(row.get("title") or "").strip()
    src_name = str(row.get("source_name") or "").strip()

    candidates: List[str] = []
    if raw_u:
        candidates.append(raw_u)
    for cu in _match_chunk_for_row(title, src_name, chunks):
        if cu not in candidates:
            candidates.append(cu)

    for cand_u in candidates:
        resolved = _probe_url(cand_u)
        if resolved:
            chunk_title = next((c.get("title", "") for c in chunks if c.get("uri") == cand_u), "")
            out_src, fam = _derive_source_from_host(resolved, src_name, chunk_title)
            return resolved, out_src, fam
    return None


def _parse_search_published_at(raw_date: Any, fetched_dt: Any) -> Tuple[Optional[str], str, Optional[str]]:
    """Parse model-reported published_date honestly; return (published_at_iso, pub_source, event_date)."""
    txt = str(raw_date or "").strip()
    if not txt:
        return None, "unknown", None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt):
        iso_cand = f"{txt}T00:00:00+08:00"
        dt = parse_iso_datetime(iso_cand)
        if dt is None:
            return None, "unknown", None
        return to_iso_shanghai(dt), "search_grounding", txt
    pub_iso, pub_src = parse_published_at(txt, "gemini-search-hunter")
    if pub_iso:
        return pub_iso, pub_src or "search_grounding", pub_iso[:10]
    return None, "unknown", None


def fetch_gemini_search_breaking_news(
    cache: Optional[HttpCacheStore] = None,
    *,
    base_dir: Path | str = ".",
) -> Dict[str, Any]:
    """Use Gemini Google Search Grounding in CI to catch zero-lag AI models, GitHub drops & global events."""
    del cache
    t0 = time.monotonic()
    fetched_dt = now_shanghai()
    fetched_iso = to_iso_shanghai(fetched_dt)
    root = Path(base_dir)
    cache_path = root / "data" / "gemini_hunter_cache.json"
    legacy_stamp = root / ".http_cache" / "gemini_hunter_last.json"

    keys = _collect_all_keys()
    if not keys:
        return {
            "connector_id": "gemini-search-hunter",
            "connector_name": "GitHub 云端 AI 搜索雷达 (待密钥环境触发)",
            "source_tier": "direct_media",
            "status": "ok",
            "fetched_at": fetched_iso,
            "latency_ms": 0,
            "item_count": 0,
            "calendar_count": 0,
            "error_message": None,
            "tos_note": "仅在配置了仓库 Gemini Secrets 的 GitHub Actions 环境中自动联网检索，不消耗用户端密钥。",
            "items": [],
        }

    # Check CI-persistent cache (falling back cleanly to legacy stamp if present)
    prev_cache: Dict[str, Any] = load_json_if_exists(cache_path, default={}) or {}
    if not prev_cache and legacy_stamp.exists():
        prev_cache = load_json_if_exists(legacy_stamp, default={}) or {}

    if isinstance(prev_cache, dict) and isinstance(prev_cache.get("items"), list):
        age_sec = time.time() - float(prev_cache.get("ts") or 0)
        if age_sec < THROTTLE_SECONDS:
            return {
                "connector_id": "gemini-search-hunter",
                "connector_name": f"GitHub 云端 AI 搜索雷达 (缓存复用 {len(prev_cache['items'])} 条)",
                "source_tier": "direct_media",
                "status": "cached_304",
                "fetched_at": fetched_iso,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "item_count": len(prev_cache["items"]),
                "calendar_count": 0,
                "error_message": None,
                "cache_reused": True,
                "verification_stats": prev_cache.get("verification_stats"),
                "tos_note": "90 分钟节流期内复用已核验搜索结果以节省免费 API 配额。",
                "items": prev_cache["items"],
            }

    try:
        from google.genai import types
        search_tools = [types.Tool(google_search=types.GoogleSearch())]
    except Exception:
        search_tools = [{"google_search": {}}]

    today_str = fetched_dt.strftime("%Y-%m-%d")
    prompt = (
        f"当前北京时间日期为 {today_str}。请利用 Google 搜索检索过去 24–72 小时内真实发生的全球重大突发与前沿科技动态，"
        "重点查明：1) Google Gemini、OpenAI、Anthropic Claude、xAI Grok、阿里千问 Qwen、DeepSeek、Kimi、腾讯混元最新模型或 GitHub/Hugging Face 热门开源 AI 工具发布；"
        "2) 美联储、A股/美股/黄金关税、重大裁决/和解与外交峰会突发。\n"
        "严格要求：必须填写准确的原文发布日期 published_date（YYYY-MM-DD），严禁把多周前的旧闻伪装成今日发生，url 必须是搜索到的真实可访问新闻原文页。\n"
        "请输出严格 JSON 数组（8–12 条），每条字段：\n"
        '{"category":"tech|finance|global","title":"简洁准确的中文新闻标题","summary":"80字内中文事实摘要","source_name":"原始媒体/官方机构名","url":"https://真实原文URL","published_date":"YYYY-MM-DD"}'
    )

    res = call_gemini_raw(
        scope="search_hunter",
        prompt=prompt,
        models=("gemini-4-hydrogen", "gemini-2.5-flash"),
        temperature=0.15,
        tools=search_tools,
        base_dir=root,
    )

    raw_candidates: List[Dict[str, Any]] = []
    chunks: List[Dict[str, str]] = []
    parse_err: Optional[str] = None
    if res.ok and res.text:
        chunks = _extract_grounding_chunks(res.raw_response)
        m = re.search(r"\[[\s\S]*\]", res.text)
        if m:
            try:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, list):
                    raw_candidates = [r for r in parsed[:14] if isinstance(r, dict) and r.get("title")]
            except Exception as exc:
                parse_err = f"JSONDecodeError: {str(exc)[:80]}"
        else:
            parse_err = "No JSON array in Gemini Search response"

    stale_rejected = 0
    date_filtered_rows: List[Tuple[Dict[str, Any], Optional[str], str, Optional[str]]] = []
    for r in raw_candidates:
        pub_iso, pub_src, ev_date = _parse_search_published_at(r.get("published_date"), fetched_dt)
        if pub_iso:
            pub_dt = parse_iso_datetime(pub_iso)
            if pub_dt is not None and (fetched_dt - pub_dt).total_seconds() > STALE_AGE_HOURS * 3600:
                stale_rejected += 1
                continue
        date_filtered_rows.append((r, pub_iso, pub_src, ev_date))

    # Concurrently verify & resolve every candidate URL before emitting downstream
    url_verified = 0
    url_rejected = 0
    items: List[dict] = []
    if date_filtered_rows:
        verified_results: Dict[int, Optional[Tuple[str, str, str]]] = {}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = {
                pool.submit(_verify_and_resolve_candidate, row, chunks): idx
                for idx, (row, _, _, _) in enumerate(date_filtered_rows)
            }
            for fut in as_completed(futs):
                idx = futs[fut]
                try:
                    verified_results[idx] = fut.result()
                except Exception:
                    verified_results[idx] = None

        for idx, (r, pub_iso, pub_src, ev_date) in enumerate(date_filtered_rows):
            ver = verified_results.get(idx)
            if not ver:
                url_rejected += 1
                continue
            url_verified += 1
            verified_url, resolved_source, pub_family = ver
            title = str(r["title"]).strip()
            cat = str(r.get("category") or "tech").lower()
            if cat not in {"tech", "finance", "global", "general"}:
                cat = "tech"
            excerpt = str(r.get("summary") or "").strip()
            items.append(
                {
                    "item_id": make_raw_item_id("gemini-search", verified_url, title),
                    "source_id": "gemini-search-hunter",
                    "source_name": f"{resolved_source} (AI搜索雷达)",
                    "category": cat,
                    "source_kind": "news",
                    "source_tier": "direct_media",
                    "publisher_family": pub_family,
                    "citable_as_news": True,
                    "title": title,
                    "url": verified_url,
                    "canonical_url": verified_url,
                    "published_at": pub_iso,
                    "published_at_source": pub_src,
                    "event_date": ev_date,
                    "fetched_at": fetched_iso,
                    "excerpt": excerpt or None,
                    "metric_label": "AI 搜索雷达",
                    "url_verified": True,
                }
            )

    verification_stats = {
        "raw_candidates": len(raw_candidates),
        "stale_rejected": stale_rejected,
        "url_verified": url_verified,
        "url_rejected": url_rejected,
        "grounding_chunks_count": len(chunks),
        "model_used": res.model_used,
        "key_slot": res.key_slot,
    }

    if items:
        try:
            atomic_write_json(
                cache_path,
                {
                    "schema_version": "4.1",
                    "ts": time.time(),
                    "fetched_at": fetched_iso,
                    "verification_stats": verification_stats,
                    "items": items,
                },
            )
        except Exception:
            pass
        return {
            "connector_id": "gemini-search-hunter",
            "connector_name": f"GitHub 云端 AI 搜索雷达 ({len(items)} 条)",
            "source_tier": "direct_media",
            "status": "ok",
            "fetched_at": fetched_iso,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "item_count": len(items),
            "calendar_count": 0,
            "error_message": None,
            "verification_stats": verification_stats,
            "per_key_errors": res.per_key_errors[:6],
            "quota_exhausted": res.quota_exhausted,
            "degraded": False,
            "quality_flags": [],
            "tos_note": "通过 GitHub Actions 全密钥池调用 Google Search Grounding 并校验原文 URL 与发布时间。",
            "items": items,
        }

    # Degraded fallback to cached verified items (<12h) when rate-limited / exhausted
    cached_items = prev_cache.get("items") if isinstance(prev_cache, dict) else None
    cache_age = time.time() - float(prev_cache.get("ts") or 0) if isinstance(prev_cache, dict) else 1e9
    if (res.quota_exhausted or not res.ok) and isinstance(cached_items, list) and cached_items and cache_age <= DEGRADED_FALLBACK_MAX_AGE_SECONDS:
        err_msg = parse_err or res.error_message or "Quota exhausted"
        return {
            "connector_id": "gemini-search-hunter",
            "connector_name": f"GitHub 云端 AI 搜索雷达 (配额降级复用 {len(cached_items)} 条)",
            "source_tier": "direct_media",
            "status": "degraded",
            "fetched_at": fetched_iso,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "item_count": len(cached_items),
            "calendar_count": 0,
            "error_message": err_msg,
            "verification_stats": verification_stats,
            "per_key_errors": res.per_key_errors[:6],
            "quota_exhausted": res.quota_exhausted,
            "degraded": True,
            "quality_flags": ["search_hunter_quota_degraded"],
            "tos_note": "搜索雷达配额受限，已降级复用最近 12 小时内已核验缓存条目。",
            "items": cached_items,
        }

    final_err = parse_err or res.error_message
    return {
        "connector_id": "gemini-search-hunter",
        "connector_name": "GitHub 云端 AI 搜索雷达 (0 条)",
        "source_tier": "direct_media",
        "status": "degraded" if res.quota_exhausted else ("error" if final_err else "empty"),
        "fetched_at": fetched_iso,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "item_count": 0,
        "calendar_count": 0,
        "error_message": final_err,
        "verification_stats": verification_stats,
        "per_key_errors": res.per_key_errors[:8],
        "quota_exhausted": res.quota_exhausted,
        "degraded": bool(res.quota_exhausted or final_err),
        "quality_flags": ["search_hunter_quota_exhausted"] if res.quota_exhausted else [],
        "tos_note": "通过 GitHub Actions 全密钥池调用 Google Search Grounding 自动采集全球新闻与开源动态。",
        "items": [],
    }
