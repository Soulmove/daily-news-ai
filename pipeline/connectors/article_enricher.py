"""Selective polite article HTML metadata & lead paragraph extractor (Task 2: Deep Fetch)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from pipeline.connectors.base import HttpCacheStore, polite_get, repair_mojibake
from pipeline.entities import match_entities_with_reasons
from pipeline.time_utils import now_shanghai, parse_published_at, to_iso_shanghai

# Domains known to block unauthenticated scrapers or be behind paywalls / dynamic login walls
SKIP_OR_RESTRICTED_DOMAINS = {
    "weibo.com", "s.weibo.com", "douyin.com", "www.douyin.com",
    "tieba.baidu.com", "www.zhihu.com", "zhihu.com", "xueqiu.com",
    "mp.weixin.qq.com", "www.bilibili.com", "bilibili.com",
}


class _ArticleLeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: Dict[str, str] = {}
        self.json_ld_blocks: List[str] = []
        self.paragraphs: List[str] = []
        self._in_p = False
        self._p_buf: List[str] = []
        self._in_ld = False
        self._ld_buf: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if t in {"script", "style", "noscript", "nav", "footer", "header"}:
            if t == "script" and attr_map.get("type", "").lower() == "application/ld+json":
                self._in_ld = True
                self._ld_buf = []
            else:
                self._skip_depth += 1
            return

        if t == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").lower().strip()
            val = attr_map.get("content", "").strip()
            if key and val and key not in self.meta:
                self.meta[key] = val
        elif t == "p" and self._skip_depth == 0:
            self._in_p = True
            self._p_buf = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {"script", "style", "noscript", "nav", "footer", "header"}:
            if t == "script" and self._in_ld:
                self._in_ld = False
                joined = "".join(self._ld_buf).strip()
                if joined:
                    self.json_ld_blocks.append(joined)
            elif self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if t == "p" and self._in_p:
            self._in_p = False
            text = " ".join("".join(self._p_buf).split()).strip()
            # Keep meaningful article sentences, skip short UI labels/copyright lines
            if len(text) >= 24 and not any(
                noise in text for noise in ("Copyright", "备案号", "登录后评论", "打开APP", "阅读原文", "相关推荐")
            ):
                self.paragraphs.append(text)

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self._ld_buf.append(data)
        elif self._in_p and self._skip_depth == 0:
            self._p_buf.append(data)


_BAD_THUMB_RE = re.compile(
    r"(?:1x1|pixel|spacer|favicon|sprite|badge|logo|icon|avatar|\.svg(?:$|\?)|^data:|"
    r"news\.google\.com/api/attachments|gstatic\.com/images|googleusercontent\.com/.*=s\d+-c)",
    re.I,
)


def _normalize_thumb_url(raw_val: Any, base_url: str = "") -> Optional[str]:
    if not raw_val or not isinstance(raw_val, str):
        return None
    u = raw_val.strip()
    if not u or _BAD_THUMB_RE.search(u):
        return None
    if u.startswith("//"):
        u = "https:" + u
    elif base_url and not u.startswith(("http://", "https://")):
        u = urljoin(base_url, u)
    if not u.startswith(("http://", "https://")) or len(u) > 600:
        return None
    return u


def _extract_article_image_url(meta: Dict[str, str], json_ld_blocks: List[str], base_url: str = "") -> Optional[str]:
    for key in ("og:image:secure_url", "og:image", "og:image:url", "twitter:image", "twitter:image:src", "image"):
        val = _normalize_thumb_url(meta.get(key), base_url)
        if val:
            return val
    for block in json_ld_blocks:
        try:
            obj = json.loads(block)
            candidates = obj if isinstance(obj, list) else [obj]
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                img = c.get("image") or c.get("thumbnailUrl")
                if isinstance(img, str):
                    val = _normalize_thumb_url(img, base_url)
                    if val:
                        return val
                elif isinstance(img, dict):
                    val = _normalize_thumb_url(img.get("url") or img.get("@id"), base_url)
                    if val:
                        return val
                elif isinstance(img, list):
                    for item in img:
                        cand = item.get("url") if isinstance(item, dict) else item
                        val = _normalize_thumb_url(cand, base_url)
                        if val:
                            return val
        except Exception:
            continue
    return None


def parse_article_html(html_text: str, base_url: str = "") -> Dict[str, Any]:
    """Extract meta description, article:published_time, JSON-LD datePublished, thumbnail_url, and lead paragraphs."""
    parser = _ArticleLeadParser()
    parser.feed(html_text[:250_000])

    meta = parser.meta
    ld_pub = None
    ld_desc = None
    for block in parser.json_ld_blocks:
        try:
            obj = json.loads(block)
            candidates = obj if isinstance(obj, list) else [obj]
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                if not ld_pub and c.get("datePublished"):
                    ld_pub = str(c["datePublished"])
                if not ld_desc and c.get("description"):
                    ld_desc = str(c["description"])
        except Exception:
            continue

    pub_candidate = (
        meta.get("article:published_time")
        or meta.get("og:release_date")
        or meta.get("pubdate")
        or meta.get("publishdate")
        or meta.get("date")
        or ld_pub
    )
    pub_iso, _ = parse_published_at(pub_candidate, "html_meta") if pub_candidate else (None, None)

    desc = repair_mojibake(meta.get("og:description") or meta.get("description") or ld_desc or "")
    desc = " ".join(desc.split()).strip()

    lead_paragraphs = [repair_mojibake(p) for p in parser.paragraphs[:3]]
    lead_body = " ".join(lead_paragraphs).strip()
    if len(lead_body) > 580:
        lead_body = lead_body[:579].rstrip() + "…"

    thumb_url = _extract_article_image_url(meta, parser.json_ld_blocks, base_url=base_url)

    return {
        "published_at": pub_iso,
        "meta_description": desc[:320] if desc else None,
        "lead_paragraphs": lead_paragraphs,
        "lead_excerpt": lead_body or (desc[:320] if desc else None),
        "thumbnail_url": thumb_url,
    }


def deep_fetch_selected_items(
    clusters: List[dict],
    cache: HttpCacheStore,
    *,
    max_articles: int = 32,
) -> Dict[str, Any]:
    """
    Task 2: Selectively deep-fetch priority / watched / title_only / missing-thumbnail news items
    from directly accessible domains with category balance across finance, tech & global.
    """
    fetched_iso = to_iso_shanghai(now_shanghai())
    logs: List[Dict[str, Any]] = []

    scored_candidates: List[tuple[int, dict]] = []
    for cl in clusters:
        matches = match_entities_with_reasons(f"{cl.get('title', '')} {cl.get('excerpt') or ''}")
        score = len(matches) * 10 + (0 if cl.get("excerpt") else 6) + (0 if cl.get("thumbnail_url") else 2)
        if cl.get("category") in {"finance", "tech"}:
            score += 3
        elif cl.get("category") == "global":
            score += 4
        scored_candidates.append((score, cl))

    scored_candidates.sort(key=lambda pair: pair[0], reverse=True)

    global_quota: List[dict] = []
    other_queue: List[dict] = []
    for _, cl in scored_candidates:
        if cl.get("category") == "global" and not cl.get("excerpt") and len(global_quota) < 6:
            global_quota.append(cl)
        else:
            other_queue.append(cl)
    ordered_queue = global_quota + other_queue

    fetch_targets: List[Tuple[dict, dict]] = []
    for cl in ordered_queue:
        if len(fetch_targets) >= max_articles:
            break
        sources = cl.get("related_sources") or [cl]
        chosen_src = None
        for s in sources:
            u = s.get("url") or ""
            host = (urlparse(u).netloc or "").lower()
            if not u or host in SKIP_OR_RESTRICTED_DOMAINS:
                continue
            if u.lower().endswith(".pdf"):
                continue
            needs_text = not s.get("excerpt") or len(str(s.get("excerpt") or "")) < 80
            needs_thumb = not s.get("thumbnail_url") and not cl.get("thumbnail_url")
            if needs_text or needs_thumb:
                chosen_src = s
                break
        if chosen_src is not None:
            fetch_targets.append((cl, chosen_src))

    attempted = len(fetch_targets)
    enriched_count = 0

    def _fetch_one(pair: Tuple[dict, dict]) -> Tuple[dict, dict, Any]:
        cl_item, src_item = pair
        res = polite_get(
            src_item["url"],
            headers={"Accept": "text/html,application/xhtml+xml"},
            cache=cache,
            timeout=(4, 6),
            retries=1,
        )
        return cl_item, src_item, res

    if fetch_targets:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = [pool.submit(_fetch_one, pair) for pair in fetch_targets]
            for fut in as_completed(futs):
                try:
                    cl, chosen_src, res = fut.result()
                except Exception:
                    continue
                target_url = chosen_src["url"]
                if res.ok and res.text:
                    parsed = parse_article_html(res.text, base_url=target_url)
                    excerpt = parsed.get("lead_excerpt") or parsed.get("meta_description")
                    thumb = parsed.get("thumbnail_url")
                    got_any = False
                    if excerpt and (not chosen_src.get("excerpt") or len(excerpt) > len(str(chosen_src.get("excerpt") or ""))):
                        chosen_src["excerpt"] = excerpt
                        chosen_src["deep_fetch_status"] = "extracted_body_lead" if parsed["lead_paragraphs"] else "meta_only"
                        cl["excerpt"] = cl.get("excerpt") or excerpt
                        cl["deep_fetch_status"] = chosen_src["deep_fetch_status"]
                        got_any = True
                    if thumb:
                        chosen_src["thumbnail_url"] = chosen_src.get("thumbnail_url") or thumb
                        cl["thumbnail_url"] = cl.get("thumbnail_url") or thumb
                        chosen_src.setdefault("deep_fetch_status", "meta_only")
                        got_any = True
                    if not chosen_src.get("published_at") and parsed.get("published_at"):
                        chosen_src["published_at"] = parsed["published_at"]
                        chosen_src["published_at_source"] = "article_html_meta"
                    if not cl.get("published_at") and parsed.get("published_at"):
                        cl["published_at"] = parsed["published_at"]
                    if got_any:
                        enriched_count += 1
                        logs.append(
                            {
                                "url": target_url,
                                "status": chosen_src.get("deep_fetch_status") or "meta_only",
                                "chars": len(excerpt or ""),
                                "has_thumbnail": bool(thumb),
                            }
                        )
                    else:
                        chosen_src["deep_fetch_status"] = "empty_or_js_rendered"
                        logs.append({"url": target_url, "status": "empty_or_js_rendered", "reason": "未提取到静态正文段落或图片"})
                else:
                    st = res.status if res.status != "ok" else "error"
                    chosen_src["deep_fetch_status"] = st
                    logs.append({"url": target_url, "status": st, "reason": res.error_message})

    return {
        "attempted": attempted,
        "enriched": enriched_count,
        "checked_at": fetched_iso,
        "logs": logs,
    }
