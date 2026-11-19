"""arXiv official Atom API connector for AI models, inference & hardware papers (with v1/v2 tracking)."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List
import xml.etree.ElementTree as ET

from pipeline.connectors.base import HttpCacheStore, polite_get
from pipeline.id_utils import make_raw_item_id
from pipeline.time_utils import now_shanghai, parse_published_at, to_iso_shanghai

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_arxiv_papers(cache: HttpCacheStore, *, max_results: int = 8) -> Dict[str, Any]:
    """Fetch recent cs.AI/cs.CL/cs.AR papers from official arXiv export API."""
    url = (
        "https://export.arxiv.org/api/query?"
        "search_query=(cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.AR)+AND+(all:reasoning+OR+all:quantization+OR+all:inference+OR+all:HBM)"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )
    fetched_iso = to_iso_shanghai(now_shanghai())
    t0 = time.monotonic()

    res = polite_get(url, cache=cache, timeout=(5, 10))
    if not res.ok:
        return {
            "connector_id": "arxiv-api",
            "connector_name": "arXiv AI / 架构论文预印本官方接口",
            "source_tier": "tech_material",
            "status": "error",
            "fetched_at": fetched_iso,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "item_count": 0,
            "error_message": res.error_message,
            "tos_note": "遵守 arXiv API 公共检索间隔，保留摘要与官方 abs/pdf 入口，论文主张严格标为待独立复现。",
            "items": [],
        }

    if res.status == "not_modified_304" or not res.text:
        return {
            "connector_id": "arxiv-api",
            "connector_name": "arXiv AI / 架构论文预印本官方接口",
            "source_tier": "tech_material",
            "status": "cached_304",
            "fetched_at": fetched_iso,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "item_count": 0,
            "error_message": None,
            "tos_note": "arXiv 公共 Atom 接口（条件缓存命中）。",
            "items": [],
        }

    items: List[dict] = []
    try:
        root = ET.fromstring(res.text)
        for entry in root.findall("atom:entry", ATOM_NS):
            raw_id = (entry.findtext("atom:id", default="", namespaces=ATOM_NS) or "").strip()
            raw_title = " ".join((entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").split())
            summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").split())
            published_raw = entry.findtext("atom:published", default="", namespaces=ATOM_NS)
            updated_raw = entry.findtext("atom:updated", default="", namespaces=ATOM_NS)
            ver_match = re.search(r"v(\d+)$", raw_id)
            version = f"v{ver_match.group(1)}" if ver_match else "v1"
            pub_iso, _ = parse_published_at(updated_raw or published_raw, "arxiv")
            abs_url = raw_id.replace("http://", "https://")
            if not abs_url or not raw_title:
                continue
            short_sum = summary[:280].rstrip() + ("…" if len(summary) > 280 else "")
            items.append(
                {
                    "item_id": make_raw_item_id("arxiv-api", abs_url, raw_title),
                    "source_id": "arxiv-api",
                    "source_name": "arXiv 论文预印本",
                    "source_kind": "preprint_paper",
                    "source_tier": "tech_material",
                    "publisher_family": "arxiv",
                    "citable_as_news": True,
                    "category": "tech",
                    "title": f"[arXiv {version}] {raw_title}",
                    "url": abs_url,
                    "canonical_url": abs_url,
                    "published_at": pub_iso,
                    "published_at_source": "arxiv_atom",
                    "fetched_at": fetched_iso,
                    "excerpt": f"【作者论文主张（待独立复现）· {version}】{short_sum}",
                    "paper_version": version,
                }
            )
    except ET.ParseError as exc:
        return {
            "connector_id": "arxiv-api",
            "connector_name": "arXiv AI / 架构论文预印本官方接口",
            "source_tier": "tech_material",
            "status": "error",
            "fetched_at": fetched_iso,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "item_count": 0,
            "error_message": f"Atom XML 解析错误: {exc}",
            "items": [],
        }

    return {
        "connector_id": "arxiv-api",
        "connector_name": "arXiv AI / 架构论文预印本官方接口",
        "source_tier": "tech_material",
        "status": "ok" if items else "empty",
        "fetched_at": fetched_iso,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "item_count": len(items),
        "error_message": None,
        "tos_note": "arXiv API 公共访问，论文版本及摘要已标明“作者论文主张（待独立复现）”。",
        "items": items,
    }
