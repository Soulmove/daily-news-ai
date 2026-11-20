"""Direct RSS/Atom news connector removing single-point dependency on third-party aggregators."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
import html
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import requests

from pipeline.connectors.base import HttpCacheStore
from pipeline.id_utils import canonicalize_url, make_raw_item_id
from pipeline.time_utils import now_shanghai, parse_iso_datetime, parse_published_at, to_iso_shanghai

_RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InsightPro/3.5; +https://soulmove.github.io/daily-news-ai/)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}

DIRECT_RSS_FEEDS: List[Dict[str, str]] = [
    # --- Official AI Labs & Developer Blogs (Zero-Lag Primary Sources) ---
    {"id": "rss-google-ai-blog", "name": "Google AI 官方博客", "category": "tech", "url": "https://blog.google/technology/ai/rss/", "family": "google-blog"},
    {"id": "rss-deepmind-blog", "name": "Google DeepMind 博客", "category": "tech", "url": "https://deepmind.google/blog/rss.xml", "family": "deepmind"},
    {"id": "rss-openai-news", "name": "OpenAI 官方动态", "category": "tech", "url": "https://openai.com/news/rss.xml", "family": "openai"},
    {"id": "rss-hf-blog", "name": "Hugging Face 官方博客", "category": "tech", "url": "https://huggingface.co/blog/feed.xml", "family": "huggingface"},
    {"id": "rss-github-changelog", "name": "GitHub Changelog", "category": "tech", "url": "https://github.blog/changelog/feed/", "family": "github"},
    {"id": "rss-nvidia-blog", "name": "NVIDIA 官方博客", "category": "tech", "url": "https://blogs.nvidia.com/feed/", "family": "nvidia"},
    {"id": "rss-simonwillison", "name": "Simon Willison AI 追踪", "category": "tech", "url": "https://simonwillison.net/atom/everything/", "family": "simonwillison"},
    # --- Real-Time AI Specialist & Tech Media ---
    {"id": "rss-9to5google", "name": "9to5Google", "category": "tech", "url": "https://9to5google.com/feed/", "family": "9to5google"},
    {"id": "rss-the-decoder", "name": "The Decoder (AI前沿)", "category": "tech", "url": "https://the-decoder.com/feed/", "family": "thedecoder"},
    {"id": "rss-marktechpost", "name": "MarkTechPost (AI论文/模型)", "category": "tech", "url": "https://www.marktechpost.com/feed/", "family": "marktechpost"},
    {"id": "rss-techcrunch", "name": "TechCrunch AI & Tech", "category": "tech", "url": "https://techcrunch.com/feed/", "family": "techcrunch"},
    {"id": "rss-theverge", "name": "The Verge", "category": "tech", "url": "https://www.theverge.com/rss/index.xml", "family": "theverge"},
    {"id": "rss-arstechnica", "name": "Ars Technica", "category": "tech", "url": "https://feeds.arstechnica.com/arstechnica/index", "family": "arstechnica"},
    {"id": "rss-hn-frontpage", "name": "Hacker News 热榜", "category": "tech", "url": "https://hnrss.org/frontpage?points=60", "family": "hackernews"},
    # --- Google News Zero-Lag Targeted Topic Search Radars (when:1d / when:2d) ---
    {
        "id": "rss-gnews-ai-models-en",
        "name": "Google News 全球 AI 模型雷达",
        "category": "tech",
        "url": "https://news.google.com/rss/search?q=(Gemini+OR+OpenAI+OR+GPT+OR+Claude+OR+Anthropic+OR+Qwen+OR+DeepSeek+OR+Kimi+OR+Grok)+model+release+when:2d&hl=en-US&gl=US&ceid=US:en",
        "family": "gnews-ai-en",
    },
    {
        "id": "rss-gnews-ai-models-zh",
        "name": "Google News 中文大模型雷达",
        "category": "tech",
        "url": "https://news.google.com/rss/search?q=(大模型+OR+Gemini+OR+OpenAI+OR+Claude+OR+千问+OR+DeepSeek+OR+Kimi+OR+混元)+发布+when:2d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "family": "gnews-ai-zh",
    },
    {
        "id": "rss-gnews-opensource-ai",
        "name": "Google News 开源 AI 与推理雷达",
        "category": "tech",
        "url": "https://news.google.com/rss/search?q=(%22open+source%22+LLM+OR+Hugging+Face+OR+vLLM+OR+llama.cpp+OR+AI+agent)+when:2d&hl=en-US&gl=US&ceid=US:en",
        "family": "gnews-oss-ai",
    },
    {
        "id": "rss-gnews-markets-zh",
        "name": "Google News A股/美股宏观异动",
        "category": "finance",
        "url": "https://news.google.com/rss/search?q=(A股+OR+美股+OR+美联储+OR+央行+OR+加息+OR+降息+OR+黄金+OR+关税)+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "family": "gnews-fin-zh",
    },
    {
        "id": "rss-gnews-reuters-bloomberg",
        "name": "路透/彭博突发全球雷达",
        "category": "global",
        "url": "https://news.google.com/rss/search?q=(site:reuters.com+OR+site:bloomberg.com)+(Fed+OR+China+OR+Trump+OR+AI+OR+chip+OR+oil+OR+tariff)+when:1d&hl=en-US&gl=US&ceid=US:en",
        "family": "gnews-wire",
    },
    # --- Global / Geopolitics / Major Summits ---
    {"id": "rss-gnews-world-zh", "name": "Google News 中文国际", "category": "global", "url": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "family": "gnews-zh"},
    {"id": "rss-gnews-world-en", "name": "Google News 英文国际", "category": "global", "url": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en", "family": "gnews-en"},
    {"id": "rss-bbc-world", "name": "BBC News World", "category": "global", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "family": "bbc"},
    {"id": "rss-bbc-asia", "name": "BBC News Asia", "category": "global", "url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml", "family": "bbc"},
    {"id": "rss-guardian-world", "name": "The Guardian World", "category": "global", "url": "https://www.theguardian.com/world/rss", "family": "guardian"},
    {"id": "rss-npr-world", "name": "NPR World", "category": "global", "url": "https://feeds.npr.org/1004/rss.xml", "family": "npr"},
    {"id": "rss-scmp-china", "name": "南华早报 SCMP China", "category": "global", "url": "https://www.scmp.com/rss/4/feed", "family": "scmp"},
    # --- Finance / Markets ---
    {"id": "rss-cnbc-world", "name": "CNBC Top News", "category": "finance", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362", "family": "cnbc"},
    {"id": "rss-cnbc-tech", "name": "CNBC Tech & AI", "category": "finance", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "family": "cnbc"},
    {"id": "rss-wsj-markets", "name": "WSJ Markets", "category": "finance", "url": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "family": "wsj"},
]

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _clean_xml_text(raw: Optional[str], max_len: int = 260) -> Optional[str]:
    if not raw:
        return None
    text = html.unescape(_HTML_TAG_RE.sub(" ", str(raw)))
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def parse_rss_or_atom_xml(
    xml_bytes: bytes,
    *,
    feed_spec: Dict[str, str],
    fetched_iso: str,
    now_dt=None,
    max_items: int = 18,
    max_age_hours: int = 72,
) -> List[dict]:
    """Parse RSS 2.0 or Atom XML bytes into normalized V3 raw items."""
    ref_dt = now_dt or now_shanghai()
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    fid = feed_spec["id"]
    fname = feed_spec["name"]
    cat = feed_spec["category"]
    family = feed_spec.get("family") or fid

    raw_nodes = root.findall(".//item")
    is_atom = False
    if not raw_nodes:
        raw_nodes = root.findall(f".//{_ATOM_NS}entry")
        is_atom = True

    out: List[dict] = []
    seen_urls: set[str] = set()

    for node in raw_nodes:
        if len(out) >= max_items:
            break
        if is_atom:
            title_el = node.find(f"{_ATOM_NS}title")
            link_el = node.find(f"{_ATOM_NS}link[@rel='alternate']") or node.find(f"{_ATOM_NS}link")
            link_val = link_el.attrib.get("href") if link_el is not None else ""
            pub_el = node.find(f"{_ATOM_NS}published")
            if pub_el is None:
                pub_el = node.find(f"{_ATOM_NS}updated")
            desc_el = node.find(f"{_ATOM_NS}summary")
            if desc_el is None:
                desc_el = node.find(f"{_ATOM_NS}content")
        else:
            title_el = node.find("title")
            link_el = node.find("link")
            link_val = (link_el.text or "").strip() if link_el is not None else ""
            pub_el = node.find("pubDate")
            if pub_el is None:
                pub_el = node.find("{http://purl.org/dc/elements/1.1/}date")
            desc_el = node.find("description")

        title = _clean_xml_text(title_el.text if title_el is not None else None, max_len=200)
        if not title or len(title) < 4:
            continue
        canon_url = canonicalize_url(link_val)
        if not canon_url or canon_url in seen_urls:
            continue

        pub_raw = pub_el.text.strip() if (pub_el is not None and pub_el.text) else None
        pub_iso, pub_src = parse_published_at(pub_raw, fid)
        if pub_iso:
            pdt = parse_iso_datetime(pub_iso)
            if pdt and (ref_dt - pdt) > timedelta(hours=max_age_hours):
                continue

        excerpt = _clean_xml_text(desc_el.text if desc_el is not None else None, max_len=260)
        if excerpt and excerpt == title:
            excerpt = None

        seen_urls.add(canon_url)
        item_id = make_raw_item_id(fid, canon_url, title)
        out.append(
            {
                "item_id": item_id,
                "source_id": fid,
                "source_name": fname,
                "category": cat,
                "source_kind": "news",
                "source_tier": "direct_media",
                "publisher_family": family,
                "citable_as_news": True,
                "title": title,
                "url": canon_url,
                "canonical_url": canon_url,
                "published_at": pub_iso,
                "published_at_source": pub_src,
                "fetched_at": fetched_iso,
                "excerpt": excerpt,
                "metric_label": None,
            }
        )

    return out


def _fetch_one_feed(spec: Dict[str, str], fetched_iso: str, ref_dt) -> Tuple[Dict[str, str], List[dict], Optional[str]]:
    try:
        resp = requests.get(spec["url"], headers=_RSS_HEADERS, timeout=(4, 7))
        if resp.status_code != 200:
            return spec, [], f"HTTP {resp.status_code}"
        items = parse_rss_or_atom_xml(resp.content, feed_spec=spec, fetched_iso=fetched_iso, now_dt=ref_dt)
        return spec, items, None
    except Exception as exc:
        return spec, [], f"{type(exc).__name__}: {str(exc)[:80]}"


def fetch_direct_rss_media(
    cache: Optional[HttpCacheStore] = None,
    *,
    feeds: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Fetch authoritative direct RSS/Atom news feeds concurrently with per-feed fault isolation."""
    del cache  # Feeds fetched concurrently without shared non-threadsafe cache writes
    t0 = time.monotonic()
    ref_dt = now_shanghai()
    fetched_iso = to_iso_shanghai(ref_dt)
    feed_list = feeds if feeds is not None else DIRECT_RSS_FEEDS

    all_items: List[dict] = []
    platforms_by_category: Dict[str, List[dict]] = {"finance": [], "global": [], "tech": [], "general": []}
    source_reports: List[dict] = []
    ok_feeds = 0
    errors: List[str] = []

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(_fetch_one_feed, spec, fetched_iso, ref_dt) for spec in feed_list]
        for fut in as_completed(futures):
            spec, items, err = fut.result()
            cat = spec["category"]
            pub_cnt = sum(1 for it in items if it.get("published_at"))
            if err:
                errors.append(f"{spec['id']}: {err}")
                status = "error"
            elif not items:
                status = "empty"
            else:
                ok_feeds += 1
                status = "ok"
            all_items.extend(items)
            latest_item_ts = max((it.get("published_at") for it in items if it.get("published_at")), default=None)
            platforms_by_category.setdefault(cat, []).append(
                {
                    "id": spec["id"],
                    "name": spec["name"],
                    "kind": "news",
                    "status": status,
                    "upstream_status": "direct_rss",
                    "upstream_updated_at": latest_item_ts or fetched_iso,
                    "fetched_at": fetched_iso,
                    "last_success_at": (latest_item_ts or fetched_iso) if status == "ok" else None,
                    "items": items,
                }
            )
            source_reports.append(
                {
                    "id": spec["id"],
                    "name": spec["name"],
                    "category": cat,
                    "kind": "news",
                    "status": status,
                    "item_count": len(items),
                    "pub_date_coverage": round(pub_cnt / len(items), 2) if items else 0.0,
                    "upstream_updated_at": latest_item_ts or fetched_iso,
                    "last_success_at": (latest_item_ts or fetched_iso) if status == "ok" else None,
                    "error_message": err,
                }
            )

    latency_ms = int((time.monotonic() - t0) * 1000)
    overall_status = "ok" if ok_feeds >= max(1, len(feed_list) // 2) else ("partial" if ok_feeds > 0 else "error")
    return {
        "connector_id": "direct-rss-media",
        "connector_name": f"直连全球/科技权威 RSS ({ok_feeds}/{len(feed_list)})",
        "source_tier": "direct_media",
        "status": overall_status,
        "fetched_at": fetched_iso,
        "latency_ms": latency_ms,
        "item_count": len(all_items),
        "calendar_count": 0,
        "error_message": "; ".join(errors[:4]) if errors else None,
        "tos_note": "遵守各媒体公开 RSS/Atom 订阅协议，仅抓取公开标题、摘要与原文直链。",
        "items": all_items,
        "platforms_by_category": platforms_by_category,
        "source_reports": source_reports,
    }
