"""First-party connectors orchestrator: SEC EDGAR, GitHub, Hugging Face, arXiv, Fed FOMC, HKEX, CNInfo."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from pipeline.connectors.arxiv_papers import fetch_arxiv_papers
from pipeline.connectors.base import HttpCacheStore
from pipeline.connectors.china_realtime import fetch_china_realtime_wires, refresh_live_wire_file
from pipeline.connectors.direct_rss import fetch_direct_rss_media
from pipeline.connectors.gemini_search_hunter import fetch_gemini_search_breaking_news
from pipeline.connectors.github_releases import fetch_github_releases
from pipeline.connectors.hkex_cninfo import fetch_cninfo_announcements, fetch_hkex_announcements
from pipeline.connectors.huggingface_hub import fetch_huggingface_models
from pipeline.connectors.macro_fomc import fetch_macro_fomc
from pipeline.connectors.sec_edgar import fetch_sec_edgar
from pipeline.gemini_pool import get_quota_summary
from pipeline.manifest import load_json_if_exists
from pipeline.time_utils import now_shanghai, to_iso_shanghai


def run_all_first_party_connectors(base_dir: Path | str = ".") -> Dict[str, Any]:
    """Run all fault-isolated independent official/tech connectors with shared HTTP cache."""
    root = Path(base_dir)
    cache = HttpCacheStore(root)
    fetched_iso = to_iso_shanghai(now_shanghai())

    prev_conn = load_json_if_exists(root / "data/connectors_latest.json", default={})
    prev_tools = prev_conn.get("tech_tools") if isinstance(prev_conn, dict) else []
    prev_items = prev_conn.get("items") if isinstance(prev_conn, dict) else []
    if not prev_tools:
        prev_tt_doc = load_json_if_exists(root / "data/tech_tools.json", default={})
        prev_tools = prev_tt_doc.get("tools", []) if isinstance(prev_tt_doc, dict) else []

    runners = [
        ("china-realtime-wires", lambda: fetch_china_realtime_wires(cache)),
        ("gemini-search-hunter", lambda: fetch_gemini_search_breaking_news(cache, base_dir=root)),
        ("direct-rss-media", lambda: fetch_direct_rss_media(cache)),
        ("sec-edgar", lambda: fetch_sec_edgar(cache, base_dir=str(root))),
        ("github-releases", lambda: fetch_github_releases(cache, previous_tools=prev_tools, previous_items=prev_items)),
        ("huggingface-hub", lambda: fetch_huggingface_models(cache, previous_tools=prev_tools, previous_items=prev_items)),
        ("arxiv-api", lambda: fetch_arxiv_papers(cache)),
        ("fed-fomc", lambda: fetch_macro_fomc(cache)),
        ("hkexnews", lambda: fetch_hkex_announcements(cache, previous_items=prev_items)),
        ("cninfo", lambda: fetch_cninfo_announcements()),
    ]

    reports: List[Dict[str, Any]] = []
    all_items: List[dict] = []
    tech_tools: List[dict] = []
    calendar_events: List[dict] = []
    entity_updates: Dict[str, dict] = {}
    direct_platforms_by_category: Dict[str, List[dict]] = {"finance": [], "global": [], "tech": [], "general": []}
    direct_source_reports: List[dict] = []

    for cid, fn in runners:
        try:
            res = fn()
        except Exception as exc:
            res = {
                "connector_id": cid,
                "connector_name": cid,
                "source_tier": "first_party",
                "status": "error",
                "fetched_at": fetched_iso,
                "latency_ms": 0,
                "item_count": 0,
                "error_message": f"Connector exception: {type(exc).__name__}: {exc}",
                "items": [],
            }

        rep_row = {
            "connector_id": res.get("connector_id", cid),
            "connector_name": res.get("connector_name", cid),
            "source_tier": res.get("source_tier", "first_party"),
            "status": res.get("status", "error"),
            "fetched_at": res.get("fetched_at", fetched_iso),
            "latency_ms": res.get("latency_ms", 0),
            "item_count": res.get("item_count", 0),
            "calendar_count": res.get("calendar_count", 0),
            "error_message": res.get("error_message"),
            "tos_note": res.get("tos_note"),
        }
        for extra_k in ("verification_stats", "per_key_errors", "quota_exhausted", "degraded", "quality_flags", "cache_reused"):
            if res.get(extra_k) is not None:
                rep_row[extra_k] = res[extra_k]
        reports.append(rep_row)
        all_items.extend(res.get("items") or [])
        tech_tools.extend(res.get("tech_tools") or [])
        calendar_events.extend(res.get("calendar_events") or [])
        for cat_k, plat_list in (res.get("platforms_by_category") or {}).items():
            direct_platforms_by_category.setdefault(cat_k, []).extend(plat_list)
        direct_source_reports.extend(res.get("source_reports") or [])
        for eid, upd in (res.get("entity_updates") or {}).items():
            cur = entity_updates.setdefault(eid, {})
            cur.update(upd)

    cache.save()

    # Also write/update data/live_wire.json combining 7x24 domestic wires + breaking direct RSS headlines
    try:
        refresh_live_wire_file(root, extra_items=all_items[:60])
    except Exception:
        pass

    ok_connectors = sum(1 for r in reports if r["status"] in {"ok", "cached_304", "partial", "degraded"})
    return {
        "schema_version": "4.1",
        "fetched_at": fetched_iso,
        "gemini_quota": get_quota_summary(root),
        "summary": {
            "total_connectors": len(reports),
            "healthy_connectors": ok_connectors,
            "total_first_party_items": len(all_items),
            "tech_tools_count": len(tech_tools),
            "calendar_events_count": len(calendar_events),
        },
        "connectors": reports,
        "items": all_items,
        "tech_tools": tech_tools,
        "calendar_events": calendar_events,
        "entity_updates": entity_updates,
        "direct_platforms_by_category": direct_platforms_by_category,
        "direct_source_reports": direct_source_reports,
    }
