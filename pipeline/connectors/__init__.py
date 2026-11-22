"""First-party connectors orchestrator: SEC EDGAR, GitHub, Hugging Face, arXiv, Fed FOMC, HKEX, CNInfo."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
from pipeline.time_utils import now_shanghai, parse_iso_datetime, to_iso_shanghai

# Lightweight cadence cache windows (seconds) to avoid redundant upstream hits in hourly crawls
_CONNECTOR_CACHE_TTL_SEC: Dict[str, int] = {
    "fed-fomc": 24 * 3600,
    "sec-edgar": 4 * 3600,
    "github-releases": 4 * 3600,
    "huggingface-hub": 4 * 3600,
    "arxiv-api": 12 * 3600,
}


def _try_reuse_cached_connector(
    cid: str,
    prev_conn: Any,
    prev_tools: List[dict],
    prev_items: List[dict],
    fetched_iso: str,
) -> Optional[Dict[str, Any]]:
    ttl = _CONNECTOR_CACHE_TTL_SEC.get(cid)
    if not ttl or not isinstance(prev_conn, dict):
        return None
    prev_rep = next(
        (r for r in (prev_conn.get("connectors") or []) if isinstance(r, dict) and r.get("connector_id") == cid),
        None,
    )
    if not prev_rep or prev_rep.get("status") not in {"ok", "cached_304", "cached_ttl"}:
        return None
    prev_dt = parse_iso_datetime(prev_rep.get("fetched_at"))
    now_dt = parse_iso_datetime(fetched_iso) or now_shanghai()
    if prev_dt is None or (now_dt - prev_dt).total_seconds() >= ttl:
        return None

    cached_items = [dict(it) for it in (prev_items or []) if isinstance(it, dict) and it.get("source_id") == cid]
    cached_cal = (
        [dict(c) for c in (prev_conn.get("calendar_events") or []) if isinstance(c, dict) and "fomc" in str(c.get("calendar_id") or "").lower()]
        if cid == "fed-fomc"
        else []
    )
    if cid in {"github-releases", "huggingface-hub"}:
        cached_tools = [
            dict(t)
            for t in (prev_tools or [])
            if isinstance(t, dict) and (
                (
                    str(t.get("tool_id") or "").startswith("tool_hf_")
                    or "huggingface.co" in str(t.get("official_url") or "")
                )
                if cid == "huggingface-hub"
                else (
                    str(t.get("tool_id") or "").startswith("tool_gh_")
                    or (
                        "github.com" in str(t.get("official_url") or "")
                        and "huggingface.co" not in str(t.get("official_url") or "")
                    )
                )
            )
        ]
    else:
        cached_tools = []
    cached_ent_updates = (prev_conn.get("entity_updates") or {}) if cid == "sec-edgar" else {}

    # Require actual payload before skipping a fetch
    if cid == "fed-fomc" and not cached_cal:
        return None
    if cid in {"sec-edgar", "arxiv-api"} and not cached_items and not cached_ent_updates:
        return None
    if cid in {"github-releases", "huggingface-hub"} and not cached_items and not cached_tools:
        return None

    return {
        "connector_id": cid,
        "connector_name": prev_rep.get("connector_name", cid),
        "source_tier": prev_rep.get("source_tier", "first_party"),
        "status": "cached_ttl",
        "fetched_at": str(prev_rep.get("fetched_at") or fetched_iso),
        "latency_ms": 0,
        "item_count": len(cached_items),
        "calendar_count": len(cached_cal),
        "cache_reused": True,
        "tos_note": prev_rep.get("tos_note"),
        "items": cached_items,
        "tech_tools": cached_tools,
        "calendar_events": cached_cal,
        "entity_updates": cached_ent_updates,
    }


def run_all_first_party_connectors(base_dir: Path | str = ".") -> Dict[str, Any]:
    """Run fault-isolated healthy first-party connectors with shared HTTP & cadence cache."""
    root = Path(base_dir)
    cache = HttpCacheStore(root)
    fetched_iso = to_iso_shanghai(now_shanghai())

    prev_conn = load_json_if_exists(root / "data/connectors_latest.json", default={})
    prev_tools = prev_conn.get("tech_tools") if isinstance(prev_conn, dict) else []
    prev_items = prev_conn.get("items") if isinstance(prev_conn, dict) else []
    if not prev_tools:
        prev_tt_doc = load_json_if_exists(root / "data/tech_tools.json", default={})
        prev_tools = prev_tt_doc.get("tools", []) if isinstance(prev_tt_doc, dict) else []

    runners: List[tuple[str, Callable[[], Dict[str, Any]]]] = [
        ("china-realtime-wires", lambda: fetch_china_realtime_wires(cache)),
        ("direct-rss-media", lambda: fetch_direct_rss_media(cache)),
        ("sec-edgar", lambda: fetch_sec_edgar(cache, base_dir=str(root))),
        ("github-releases", lambda: fetch_github_releases(cache, previous_tools=prev_tools, previous_items=prev_items)),
        ("huggingface-hub", lambda: fetch_huggingface_models(cache, previous_tools=prev_tools, previous_items=prev_items)),
        ("arxiv-api", lambda: fetch_arxiv_papers(cache)),
        ("fed-fomc", lambda: fetch_macro_fomc(cache)),
    ]
    if os.environ.get("ENABLE_GEMINI_SEARCH_HUNTER", "0").strip() == "1":
        runners.insert(1, ("gemini-search-hunter", lambda: fetch_gemini_search_breaking_news(cache, base_dir=root)))

    reports: List[Dict[str, Any]] = []
    all_items: List[dict] = []
    tech_tools: List[dict] = []
    seen_tool_keys: set[str] = set()
    calendar_events: List[dict] = []
    entity_updates: Dict[str, dict] = {}
    direct_platforms_by_category: Dict[str, List[dict]] = {"finance": [], "global": [], "tech": [], "general": []}
    direct_source_reports: List[dict] = []

    for cid, fn in runners:
        try:
            res = _try_reuse_cached_connector(cid, prev_conn, prev_tools, prev_items, fetched_iso) or fn()
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
        for raw_t in (res.get("tech_tools") or []):
            if not isinstance(raw_t, dict):
                continue
            tid_k = str(raw_t.get("tool_id") or "").strip().lower()
            tname_k = str(raw_t.get("name") or "").strip().lower()
            if (tid_k and tid_k in seen_tool_keys) or (tname_k and tname_k in seen_tool_keys):
                continue
            if tid_k:
                seen_tool_keys.add(tid_k)
            if tname_k:
                seen_tool_keys.add(tname_k)
            tech_tools.append(raw_t)
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

    ok_connectors = sum(1 for r in reports if r["status"] in {"ok", "cached_304", "cached_ttl", "partial", "degraded"})
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
