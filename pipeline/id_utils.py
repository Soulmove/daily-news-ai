"""Deterministic ID generation, URL canonicalization, and source URL validation."""

from __future__ import annotations

import hashlib
import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Tracking parameters stripped during canonicalization while preserving functional params (e.g. ?q=, ?id=, ?wd=)
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "spm", "spm_id_from", "from", "isappinstalled", "share_token", "share_id",
    "fbclid", "gclid", "mc_cid", "mc_eid", "vd_source", "band_rank", "refer",
}

_XUEQIU_QUOTE_RE = re.compile(r"^https?://(?:www\.)?xueqiu\.com/s/[^/?#]+/?$", re.IGNORECASE)


def canonicalize_url(raw_url: Optional[str]) -> Optional[str]:
    """
    Normalize a raw URL and reject invalid placeholders (#, empty, non-http).
    Returns normalized http(s) URL string, or None when invalid.
    """
    if not raw_url or not isinstance(raw_url, str):
        return None
    text = raw_url.strip()
    if not text or text in {"#", "about:blank", "null", "None", "undefined"}:
        return None
    if text.startswith("//"):
        text = "https:" + text

    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Filter tracking query parameters case-insensitively
    kept_params = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    query = urlencode(kept_params, doseq=True)
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    return urlunparse((scheme, netloc, path, "", query, ""))


def is_generic_quote_or_homepage_url(url: Optional[str], source_id: str = "") -> bool:
    """
    Detect non-article generic links such as stock quote pages (xueqiu.com/s/NVDA)
    or bare site homepages without a path.
    """
    if source_id == "xueqiu-hotstock":
        return True
    canon = canonicalize_url(url)
    if not canon:
        return True
    if _XUEQIU_QUOTE_RE.match(canon):
        return True
    parsed = urlparse(canon)
    # Bare homepage (path == "/" and no query) is not a specific news article
    if (not parsed.path or parsed.path == "/") and not parsed.query:
        return True
    return False


def normalize_title(title: str) -> str:
    """Normalize whitespace and punctuation for deterministic hashing and comparison."""
    if not title:
        return ""
    s = title.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def make_raw_item_id(source_id: str, canonical_url: Optional[str], title: str) -> str:
    """
    Build a stable, deterministic article/raw item ID (`article_id`) anchored
    primarily on source_id + canonical_url. Falls back to normalized title if URL is missing.
    """
    anchor = canonical_url if canonical_url else f"title:{normalize_title(title)}"
    digest = hashlib.sha1(f"{source_id}|{anchor}".encode("utf-8")).hexdigest()[:12]
    safe_src = re.sub(r"[^a-z0-9_-]", "-", source_id.lower())
    return f"{safe_src}_{digest}"


def make_article_id(source_id: str, canonical_url: Optional[str], title: str) -> str:
    """Explicit alias for article-level identity, distinct from event_id and storyline_id."""
    return make_raw_item_id(source_id, canonical_url, title)


def normalize_event_fingerprint(title: str, entities: Optional[list[str]] = None) -> str:
    """
    Build an event fingerprint independent of source ordering so omnibus articles split
    into multiple events produce distinct hashes and source-order changes keep the same core ID.
    """
    cleaned = normalize_title(title)
    # Strip leading vague rumor prefixes for stable matching while keeping distinguishing core text
    cleaned = re.sub(r"^(?:传闻称|消息称|据悉|曝|网传)[：:，,\s]*", "", cleaned)
    cleaned = re.sub(r"[，。！？、：；“”\"'‘’（）()【】\[\]]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    ent_part = ""
    if entities:
        uniq = sorted({normalize_title(str(e)) for e in entities if str(e).strip()})[:3]
        ent_part = "|".join(uniq)
    return f"{ent_part}::{cleaned}" if ent_part else cleaned


def make_event_id(
    category: str,
    primary_item_id: Optional[str] = None,
    title: str = "",
    entities: Optional[list[str]] = None,
) -> str:
    """
    Build a deterministic event ID anchored on normalized event semantics & title
    (independent of which source article appears first in citations).
    """
    fp = normalize_event_fingerprint(title, entities)
    if not fp and primary_item_id:
        fp = primary_item_id
    digest = hashlib.sha1(f"v3|{category}|{fp}".encode("utf-8")).hexdigest()[:12]
    return f"evt_{digest}"


def make_storyline_id(
    category: str,
    title: str,
    entities: Optional[list[str]] = None,
) -> str:
    """
    Build a persistent cross-batch storyline ID anchored on specific topic semantics.
    Avoids merging unrelated events merely because both share a region or generic term like 'AI'.
    """
    generic_block = {"ai", "人工智能", "中国", "美国", "市场", "科技", "全球", "行业", "企业", "公司"}
    specific_ents = [
        normalize_title(str(e))
        for e in (entities or [])
        if str(e).strip() and normalize_title(str(e)) not in generic_block
    ]
    cleaned_title = normalize_event_fingerprint(title, [])
    key = f"{category}|{'|'.join(sorted(set(specific_ents))[:2])}|{cleaned_title[:48]}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"st_{digest}"


def ensure_unique_event_id(
    candidate_id: str,
    used_ids: set[str],
    *,
    category: str,
    title: str,
    ordinal: int = 0,
) -> str:
    """Guarantee zero duplicate event_id within a batch even under hash collisions."""
    if candidate_id not in used_ids:
        used_ids.add(candidate_id)
        return candidate_id
    suffix_seed = f"{category}|{candidate_id}|{normalize_title(title)}|{ordinal}"
    for salt in range(10):
        digest = hashlib.sha1(f"{suffix_seed}|{salt}".encode("utf-8")).hexdigest()[:12]
        alt = f"evt_{digest}"
        if alt not in used_ids:
            used_ids.add(alt)
            return alt
    raise RuntimeError(f"Unable to disambiguate event_id collision for {candidate_id}")
