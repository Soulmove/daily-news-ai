"""V2 Raw News Crawler with timezone-aware timestamps, stable IDs, and per-source health tracking."""

from __future__ import annotations

import argparse
from datetime import timedelta
import html as html_lib
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import requests

from pipeline.connectors import run_all_first_party_connectors
from pipeline.connectors.article_enricher import deep_fetch_selected_items
from pipeline.connectors.base import HttpCacheStore, repair_mojibake
from pipeline.connectors.china_realtime import refresh_live_wire_file
from pipeline.dedup import deduplicate_raw_items, is_consumer_promo_or_fluff, strip_raw_urls_and_domain_tails
from pipeline.id_utils import canonicalize_url, make_raw_item_id
from pipeline.manifest import (
    atomic_write_json,
    load_json_if_exists,
    load_manifest,
    prune_old_archives,
    save_manifest,
    upsert_history_index,
)
from pipeline.sources import (
    ACTIVE_SOURCES,
    CATEGORIES,
    CATEGORY_FILES,
    RETIRED_SOURCES,
    SOURCE_BY_ID,
    SourceDef,
)
from pipeline.time_utils import (
    format_batch_id,
    now_shanghai,
    parse_epoch_ms,
    parse_iso_datetime,
    parse_published_at,
    to_iso_shanghai,
)

UPSTREAM_ENTIRE_URL = "https://newsnow.busiyi.world/api/s/entire"
UPSTREAM_SINGLE_URL = "https://newsnow.busiyi.world/api/s"
STALE_THRESHOLD_HOURS = 6.0

DEFAULT_HEADERS = {
    "content-type": "application/json",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


def _clean_text(value: Any, max_len: int = 500) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    stripped = html_lib.unescape(re.sub(r"<[^>]+>", " ", value))
    cleaned = repair_mojibake(" ".join(stripped.strip().split()))
    cleaned = strip_raw_urls_and_domain_tails(cleaned)
    if not cleaned:
        return None
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def _format_metric(value: Any) -> Optional[str]:
    if value is None or value is False or value == "":
        return None
    return _clean_text(str(value), max_len=64)


def _request_with_retry(
    method: str,
    url: str,
    *,
    json_payload: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: int = 25,
    retries: int = 3,
) -> Tuple[Optional[requests.Response], Optional[str]]:
    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            resp = requests.request(
                method,
                url,
                headers=DEFAULT_HEADERS,
                json=json_payload,
                params=params,
                timeout=timeout,
            )
            if resp.status_code == 200:
                return resp, None
            last_err = f"HTTP {resp.status_code}: {resp.text[:160].strip()}"
            if resp.status_code < 500 and resp.status_code != 429:
                return resp, last_err
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        if attempt < retries - 1:
            time.sleep(1.5 * (2**attempt))
    return None, last_err


def _load_previous_source_index(base_dir: Path, manifest: Dict[str, Any]) -> Tuple[Dict[str, dict], Dict[str, list]]:
    prev_sources: Dict[str, dict] = {}
    prev_items_by_source: Dict[str, list] = {}
    raw_info = manifest.get("raw", {}) if isinstance(manifest, dict) else {}
    latest_path = raw_info.get("latest_path")
    if latest_path:
        meta = load_json_if_exists(base_dir / latest_path / "meta.json", default={})
        if isinstance(meta, dict):
            for s in meta.get("sources", []):
                if isinstance(s, dict) and s.get("id"):
                    prev_sources[s["id"]] = s
        for cat in CATEGORIES:
            cat_data = load_json_if_exists(base_dir / latest_path / CATEGORY_FILES[cat], default=[])
            if isinstance(cat_data, list):
                for plat in cat_data:
                    if isinstance(plat, dict) and plat.get("id") and plat.get("items"):
                        prev_items_by_source[plat["id"]] = plat["items"]
    return prev_sources, prev_items_by_source


def normalize_upstream_items(
    source_def: SourceDef,
    raw_items: List[dict],
    fetched_at_iso: str,
) -> Tuple[List[dict], int]:
    """Normalize upstream items into V2 schema with canonical URLs, HTML-clean excerpts, and 72h freshness gate."""
    normalized: List[dict] = []
    skipped = 0
    seen_ids = set()
    ref_dt = parse_iso_datetime(fetched_at_iso) or now_shanghai()

    for idx, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            skipped += 1
            continue
        title = _clean_text(item.get("title"), max_len=240)
        raw_url = item.get("url") or item.get("mobileUrl")
        canon_url = canonicalize_url(raw_url)
        if not title or not canon_url:
            skipped += 1
            continue
        if "newsnow.busiyi.world" in canon_url or "wallstreetcn.com/charts/" in canon_url:
            skipped += 1
            continue

        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        pub_raw = item.get("pubDate")
        if pub_raw is None:
            pub_raw = extra.get("date")
        published_at, published_source = parse_published_at(pub_raw, source_def.id)

        # Prevent multi-day / >72h stale articles from masquerading as real-time hot stream items
        if published_at:
            pub_dt = parse_iso_datetime(published_at)
            if pub_dt is not None and (ref_dt - pub_dt) > timedelta(hours=72):
                skipped += 1
                continue

        excerpt = _clean_text(extra.get("hover"), max_len=420)
        if is_consumer_promo_or_fluff(title, excerpt or ""):
            skipped += 1
            continue
        raw_thumb = extra.get("thumbnail") or extra.get("image") or item.get("thumbnail_url")
        thumb_url = raw_thumb.strip() if isinstance(raw_thumb, str) and raw_thumb.strip().startswith(("http://", "https://")) else None
        metric_label = _format_metric(extra.get("info"))
        item_id = make_raw_item_id(source_def.id, canon_url, title)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        normalized.append(
            {
                "item_id": item_id,
                "upstream_id": str(item.get("id")) if item.get("id") is not None else None,
                "source_id": source_def.id,
                "source_name": source_def.name,
                "source_kind": source_def.kind,
                "citable_as_news": source_def.citable_as_news,
                "category": source_def.category,
                "title": title,
                "url": canon_url,
                "canonical_url": canon_url,
                "published_at": published_at,
                "published_at_source": published_source,
                "fetched_at": fetched_at_iso,
                "excerpt": excerpt,
                "thumbnail_url": thumb_url,
                "metric_label": metric_label,
                "rank": idx,
            }
        )
    return normalized, skipped


def fetch_raw_snapshot(
    base_dir: Path | str = ".",
    *,
    schedule_source: str = "manual_cli",
    respect_cadence: bool = False,
    skip_connectors: bool = False,
    skip_deep_fetch: bool = False,
    upstream_fail_test: bool = False,
) -> Dict[str, Any]:
    """Run a full raw crawl across NewsNow sources + independent official connectors and publish atomically."""
    root = Path(base_dir)
    fetched_dt = now_shanghai()
    fetched_at_iso = to_iso_shanghai(fetched_dt)
    batch_id = format_batch_id("raw", fetched_dt)
    date_str = fetched_dt.strftime("%Y-%m-%d")
    time_str = fetched_dt.strftime("%H-%M")
    rel_archive_dir = f"archives/raw/{date_str}/{time_str}/"
    abs_archive_dir = root / rel_archive_dir

    manifest = load_manifest(root)
    prev_sources, prev_items_by_source = _load_previous_source_index(root, manifest)

    # 1. Determine which aggregator sources are due according to expected_interval_minutes
    active_ids: List[str] = []
    reused_by_cadence: Dict[str, List[dict]] = {}
    for source_def in ACTIVE_SOURCES:
        sid = source_def.id
        if respect_cadence:
            pm = prev_sources.get(sid, {})
            prev_dt = parse_iso_datetime(pm.get("last_success_at"))
            if (
                pm.get("status") == "ok"
                and prev_dt is not None
                and prev_items_by_source.get(sid)
                and (fetched_dt - prev_dt).total_seconds() < source_def.expected_interval_minutes * 60
            ):
                reused_by_cadence[sid] = prev_items_by_source[sid]
                continue
        active_ids.append(sid)

    print(f"[{fetched_at_iso}] Fetching {len(active_ids)} due sources (+{len(reused_by_cadence)} within cadence) for batch {batch_id}...")

    platform_payloads: Dict[str, dict] = {}
    batch_err: Optional[str] = None
    if upstream_fail_test:
        batch_err = "Simulated aggregator upstream outage"
    elif active_ids:
        resp, batch_err = _request_with_retry(
            "POST",
            UPSTREAM_ENTIRE_URL,
            json_payload={"sources": active_ids},
            timeout=30,
            retries=3,
        )
        if resp is not None and resp.status_code == 200:
            try:
                body = resp.json()
                if isinstance(body, list):
                    for entry in body:
                        if isinstance(entry, dict) and entry.get("id"):
                            platform_payloads[entry["id"]] = entry
            except ValueError as exc:
                batch_err = f"Invalid JSON from entire endpoint: {exc}"

    # Individual fallback probe for any source omitted by /entire (or if /entire failed partially)
    missing_ids = [sid for sid in active_ids if sid not in platform_payloads]
    single_errors: Dict[str, Tuple[Optional[int], str]] = {}
    if missing_ids and not upstream_fail_test:
        print(f"Probing {len(missing_ids)} missing sources individually...")
        for sid in missing_ids:
            s_resp, s_err = _request_with_retry(
                "GET",
                UPSTREAM_SINGLE_URL,
                params={"id": sid},
                timeout=12,
                retries=2,
            )
            if s_resp is not None and s_resp.status_code == 200:
                try:
                    data = s_resp.json()
                    if isinstance(data, dict) and data.get("id"):
                        platform_payloads[sid] = data
                        continue
                except ValueError as exc:
                    s_err = f"Invalid JSON: {exc}"
            http_code = s_resp.status_code if s_resp is not None else None
            single_errors[sid] = (http_code, s_err or batch_err or "Source omitted by upstream")
    elif upstream_fail_test:
        for sid in missing_ids:
            single_errors[sid] = (503, batch_err or "Simulated upstream outage")

    # 2. Run fault-isolated independent first-party connectors (SEC, GitHub, HF, arXiv, Fed FOMC, HKEX, CNInfo)
    connectors_payload: Dict[str, Any]
    if skip_connectors:
        connectors_payload = {
            "schema_version": "3.0",
            "fetched_at": fetched_at_iso,
            "summary": {"total_connectors": 0, "healthy_connectors": 0, "total_first_party_items": 0},
            "connectors": [],
            "items": [],
            "tech_tools": [],
            "calendar_events": [],
            "entity_updates": {},
        }
    else:
        connectors_payload = run_all_first_party_connectors(root)

    categorized_platforms: Dict[str, List[dict]] = {cat: [] for cat in CATEGORIES}
    all_raw_items: List[dict] = []
    source_reports: List[dict] = []

    ok_count = 0
    empty_count = 0
    error_count = 0
    stale_count = 0

    for source_def in ACTIVE_SOURCES:
        sid = source_def.id
        prev_meta = prev_sources.get(sid, {})
        prev_last_success = prev_meta.get("last_success_at")

        if sid in reused_by_cadence:
            cached_items = reused_by_cadence[sid]
            ok_count += 1
            pub_present = sum(1 for x in cached_items if x.get("published_at"))
            pub_cov = round(pub_present / len(cached_items), 3) if cached_items else 0.0
            source_reports.append(
                {
                    "id": sid,
                    "name": source_def.name,
                    "category": source_def.category,
                    "kind": source_def.kind,
                    "expected_interval_minutes": source_def.expected_interval_minutes,
                    "status": "ok",
                    "http_status": 304,
                    "upstream_status": "cached_within_cadence",
                    "upstream_updated_at": prev_meta.get("upstream_updated_at"),
                    "fetched_at": prev_meta.get("fetched_at") or fetched_at_iso,
                    "last_success_at": prev_last_success,
                    "item_count": len(cached_items),
                    "pub_date_coverage": pub_cov,
                    "error_message": None,
                    "fallback_used": False,
                    "reused_within_cadence": True,
                }
            )
            categorized_platforms[source_def.category].append(
                {
                    "id": sid,
                    "name": source_def.name,
                    "kind": source_def.kind,
                    "status": "ok",
                    "upstream_status": "cached_within_cadence",
                    "upstream_updated_at": prev_meta.get("upstream_updated_at"),
                    "fetched_at": prev_meta.get("fetched_at") or fetched_at_iso,
                    "last_success_at": prev_last_success,
                    "items": cached_items,
                }
            )
            all_raw_items.extend(cached_items)
            continue

        payload = platform_payloads.get(sid)

        if payload is None:
            http_code, err_msg = single_errors.get(sid, (None, batch_err or "No response"))
            fallback_items = prev_items_by_source.get(sid, [])
            fallback_used = bool(fallback_items)
            error_count += 1
            source_reports.append(
                {
                    "id": sid,
                    "name": source_def.name,
                    "category": source_def.category,
                    "kind": source_def.kind,
                    "expected_interval_minutes": source_def.expected_interval_minutes,
                    "status": "error",
                    "http_status": http_code,
                    "upstream_status": None,
                    "upstream_updated_at": prev_meta.get("upstream_updated_at"),
                    "fetched_at": fetched_at_iso,
                    "last_success_at": prev_last_success,
                    "item_count": 0,
                    "pub_date_coverage": 0.0,
                    "error_message": err_msg,
                    "fallback_used": fallback_used,
                    "fallback_item_count": len(fallback_items) if fallback_used else 0,
                }
            )
            categorized_platforms[source_def.category].append(
                {
                    "id": sid,
                    "name": source_def.name,
                    "kind": source_def.kind,
                    "status": "error",
                    "fetched_at": fetched_at_iso,
                    "last_success_at": prev_last_success,
                    "error_message": err_msg,
                    "fallback_used": fallback_used,
                    "fallback_items": fallback_items if fallback_used else [],
                    "items": [],
                }
            )
            continue

        raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
        upstream_status = payload.get("status")
        upd_dt = parse_epoch_ms(payload.get("updatedTime"))
        upd_iso = to_iso_shanghai(upd_dt) if upd_dt else None

        norm_items, skipped_count = normalize_upstream_items(source_def, raw_items, fetched_at_iso)

        # Detect staleness: upstream updatedTime older than STALE_THRESHOLD_HOURS
        is_stale = False
        if upd_dt is not None:
            age_hours = (fetched_dt - upd_dt).total_seconds() / 3600.0
            if age_hours > STALE_THRESHOLD_HOURS:
                is_stale = True

        if not norm_items:
            status = "empty"
            empty_count += 1
            last_success = prev_last_success
        elif is_stale:
            status = "stale"
            stale_count += 1
            last_success = upd_iso or to_iso_shanghai(now_shanghai())
        else:
            status = "ok"
            ok_count += 1
            last_success = upd_iso or to_iso_shanghai(now_shanghai())

        pub_present = sum(1 for x in norm_items if x.get("published_at"))
        pub_cov = round(pub_present / len(norm_items), 3) if norm_items else 0.0

        source_reports.append(
            {
                "id": sid,
                "name": source_def.name,
                "category": source_def.category,
                "kind": source_def.kind,
                "expected_interval_minutes": source_def.expected_interval_minutes,
                "status": status,
                "http_status": 200,
                "upstream_status": upstream_status,
                "upstream_updated_at": upd_iso,
                "fetched_at": fetched_at_iso,
                "last_success_at": last_success,
                "item_count": len(norm_items),
                "skipped_invalid_items": skipped_count,
                "pub_date_coverage": pub_cov,
                "error_message": "上游返回为空（0条）" if status == "empty" else ("上游更新已停滞超过 6 小时" if status == "stale" else None),
                "fallback_used": False,
                "fallback_item_count": 0,
            }
        )

        categorized_platforms[source_def.category].append(
            {
                "id": sid,
                "name": source_def.name,
                "kind": source_def.kind,
                "status": status,
                "upstream_status": upstream_status,
                "upstream_updated_at": upd_iso,
                "fetched_at": fetched_at_iso,
                "last_success_at": last_success,
                "items": norm_items,
            }
        )
        all_raw_items.extend(norm_items)

    # Merge direct RSS/Atom media feeds directly into categorized platforms & health reports
    # so global/finance/tech remain fresh and authoritative even if newsnow.busiyi.world degrades.
    direct_platforms = connectors_payload.get("direct_platforms_by_category") or {}
    direct_reports = connectors_payload.get("direct_source_reports") or []
    direct_item_ids: set[str] = set()
    for cat_k, plat_list in direct_platforms.items():
        if cat_k in categorized_platforms:
            for plat in plat_list:
                categorized_platforms[cat_k].append(plat)
                for it in plat.get("items") or []:
                    all_raw_items.append(it)
                    if it.get("item_id"):
                        direct_item_ids.add(it["item_id"])
    for rep in direct_reports:
        source_reports.append(rep)
        st = rep.get("status")
        if st == "ok":
            ok_count += 1
        elif st == "empty":
            empty_count += 1
        else:
            error_count += 1

    # Exclude direct_rss items already injected into all_raw_items from connector_items to prevent double-counting
    connector_items = [
        it for it in (connectors_payload.get("items") or [])
        if it.get("item_id") not in direct_item_ids
    ]
    healthy_connectors = connectors_payload.get("summary", {}).get("healthy_connectors", 0)
    total_configured_sources = len(ACTIVE_SOURCES) + len(direct_reports)
    total_successful_sources = ok_count + stale_count
    if total_successful_sources == 0 and healthy_connectors == 0:
        raise RuntimeError(f"All {total_configured_sources} sources and independent connectors failed: {batch_err}")

    if total_successful_sources == 0 and healthy_connectors > 0:
        crawl_status = "partial_degraded_aggregator"
    elif error_count > 0 or empty_count > 0 or stale_count > 0:
        crawl_status = "partial"
    else:
        crawl_status = "ok"

    # Merge first-party connector items into cluster & deep-fetch pipelines cleanly
    combined_items = all_raw_items + connector_items
    deduped_clusters = deduplicate_raw_items(combined_items)

    # Task 2: Selective deep-fetch for priority / watched / title-only / missing-thumbnail articles
    deep_fetch_summary: Dict[str, Any] = {"attempted": 0, "enriched": 0, "checked_at": fetched_at_iso, "logs": []}
    if not skip_deep_fetch and deduped_clusters:
        cache = HttpCacheStore(root)
        deep_fetch_summary = deep_fetch_selected_items(deduped_clusters, cache, max_articles=32)
        cache.save()
        # Propagate extracted excerpts, thumbnails & pubDates back into per-platform items saved on disk
        enriched_by_id: Dict[str, dict] = {}
        for cl in deduped_clusters:
            for src in cl.get("related_sources") or []:
                if (src.get("deep_fetch_status") or src.get("thumbnail_url")) and src.get("item_id"):
                    enriched_by_id[src["item_id"]] = src
        for cat_list in categorized_platforms.values():
            for plat in cat_list:
                for it in plat.get("items", []):
                    upd = enriched_by_id.get(it.get("item_id", ""))
                    if upd:
                        if upd.get("excerpt"):
                            it["excerpt"] = upd["excerpt"]
                        if upd.get("thumbnail_url") and not it.get("thumbnail_url"):
                            it["thumbnail_url"] = upd["thumbnail_url"]
                        if upd.get("published_at") and not it.get("published_at"):
                            it["published_at"] = upd["published_at"]
                            it["published_at_source"] = upd.get("published_at_source")
                        if upd.get("deep_fetch_status"):
                            it["deep_fetch_status"] = upd["deep_fetch_status"]

    category_summary: Dict[str, dict] = {}
    for cat in CATEGORIES:
        cat_reports = [s for s in source_reports if s["category"] == cat]
        cat_items = sum(s["item_count"] for s in cat_reports)
        cat_ok = sum(1 for s in cat_reports if s["status"] == "ok")
        cat_err = sum(1 for s in cat_reports if s["status"] == "error")
        cat_empty = sum(1 for s in cat_reports if s["status"] == "empty")
        cat_stale = sum(1 for s in cat_reports if s["status"] == "stale")
        cat_status = "ok" if (cat_err == 0 and cat_empty == 0 and cat_stale == 0) else ("failed" if cat_items == 0 else "partial")
        category_summary[cat] = {
            "file": CATEGORY_FILES[cat],
            "path": f"{rel_archive_dir}{CATEGORY_FILES[cat]}",
            "status": cat_status,
            "source_count": len(cat_reports),
            "ok_sources": cat_ok,
            "error_sources": cat_err,
            "empty_sources": cat_empty,
            "stale_sources": cat_stale,
            "item_count": cat_items,
        }

    published_iso = to_iso_shanghai(now_shanghai())
    batch_meta = {
        "schema_version": "3.0",
        "batch_type": "raw",
        "batch_id": batch_id,
        "fetched_at": fetched_at_iso,
        "published_at": published_iso,
        "target_cadence_minutes": 15,
        "schedule_source": schedule_source,
        "crawl_status": crawl_status,
        "summary": {
            "configured_sources": total_configured_sources,
            "ok_sources": ok_count,
            "empty_sources": empty_count,
            "error_sources": error_count,
            "stale_sources": stale_count,
            "retired_sources": len(RETIRED_SOURCES),
            "total_raw_items": len(all_raw_items),
            "first_party_items": len(connector_items),
            "healthy_connectors": healthy_connectors,
            "total_connectors": connectors_payload.get("summary", {}).get("total_connectors", 0),
            "deep_fetched_enriched": deep_fetch_summary.get("enriched", 0),
            "deduped_events": len(deduped_clusters),
        },
        "categories": category_summary,
        "sources": source_reports,
        "connectors": connectors_payload.get("connectors", []),
        "deep_fetch": deep_fetch_summary,
        "retired_sources": RETIRED_SOURCES,
    }

    # 1. Write immutable archive snapshot first
    # Persist a slimmed copy of connectors payload on disk (avoid duplicating direct_platforms_by_category 2x)
    connectors_disk_payload = {
        k: v
        for k, v in connectors_payload.items()
        if k not in {"direct_platforms_by_category", "direct_source_reports"}
    }
    abs_archive_dir.mkdir(parents=True, exist_ok=True)
    for cat in CATEGORIES:
        atomic_write_json(abs_archive_dir / CATEGORY_FILES[cat], categorized_platforms[cat])
    atomic_write_json(abs_archive_dir / "connectors.json", connectors_disk_payload)
    atomic_write_json(abs_archive_dir / "meta.json", batch_meta)

    # 2. Write root legacy-compatible latest files & V3 connectors latest file
    for cat in CATEGORIES:
        atomic_write_json(root / CATEGORY_FILES[cat], categorized_platforms[cat])
    atomic_write_json(root / "data/connectors_latest.json", connectors_disk_payload)
    if not skip_connectors:
        try:
            refresh_live_wire_file(root)
        except Exception:
            pass

    # 3. Update raw history index
    index_entry = {
        "display": fetched_dt.strftime("%Y-%m-%d %H:%M"),
        "path": rel_archive_dir,
        "batch_id": batch_id,
        "fetched_at": fetched_at_iso,
        "published_at": published_iso,
        "status": crawl_status,
        "ok_sources": ok_count,
        "error_sources": error_count,
        "total_items": len(all_raw_items),
        "first_party_items": len(connector_items),
    }
    upsert_history_index(root / "history/raw_index.json", index_entry, max_entries=120)
    prune_old_archives(root, "history/raw_index.json", keep_latest=6)

    # 4. Atomically switch data/manifest.json raw pointer
    quota_info = connectors_payload.get("gemini_quota") if isinstance(connectors_payload.get("gemini_quota"), dict) else None
    raw_degraded = crawl_status not in {"complete", "ok"}
    alerts: List[Dict[str, Any]] = []
    if raw_degraded:
        alerts.append({"code": "raw_crawl_degraded", "severity": "warning", "message": f"原始抓取状态：{crawl_status}（错误源 {error_count} 个）"})
    if quota_info and quota_info.get("total_configured_keys", 0) > 0 and quota_info.get("healthy_keys", 0) == 0:
        alerts.append({"code": "gemini_quota_exhausted", "severity": "critical", "message": "全部已配置 Gemini API Key 当前处于冷却或耗尽状态"})

    manifest["schema_version"] = "4.1"
    manifest["site_published_at"] = published_iso
    manifest["degraded"] = raw_degraded or bool(
        (manifest.get("smart") or {}).get("status") not in {None, "complete", "ok"}
    )
    manifest["alerts"] = alerts
    manifest["raw"] = {
        "latest_batch_id": batch_id,
        "latest_path": rel_archive_dir,
        "meta_path": f"{rel_archive_dir}meta.json",
        "connectors_path": f"{rel_archive_dir}connectors.json",
        "fetched_at": fetched_at_iso,
        "published_at": published_iso,
        "target_cadence_minutes": 15,
        "schedule_source": schedule_source,
        "status": crawl_status,
        "summary": batch_meta["summary"],
        "categories": category_summary,
    }
    manifest["connectors"] = {
        "latest_path": "data/connectors_latest.json",
        "fetched_at": fetched_at_iso,
        "summary": connectors_payload.get("summary", {}),
    }
    if quota_info is not None:
        manifest["gemini_quota"] = quota_info
        manifest["quota"] = quota_info
    manifest["scheduler"] = {
        "provider": "cloud_runner",
        "raw_cron": "*/15 * * * *",
        "smart_cron": "15 */1 * * *",
        "note": "高频错峰调度（原始抓取每 15 分钟 / 深度研报每小时）；服务端静默增量同步。",
    }
    save_manifest(manifest, root)

    print(
        f"[{published_iso}] Raw batch {batch_id} published: status={crawl_status}, "
        f"ok={ok_count}, stale={stale_count}, empty={empty_count}, error={error_count}, "
        f"connectors={healthy_connectors}/{connectors_payload.get('summary', {}).get('total_connectors', 0)}, "
        f"items={len(all_raw_items)}+{len(connector_items)}, deep_enriched={deep_fetch_summary.get('enriched', 0)}, "
        f"deduped={len(deduped_clusters)}"
    )
    return batch_meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch live raw news snapshot + first-party connectors (V3.0)")
    parser.add_argument("--base-dir", default=".", help="Repository root directory")
    parser.add_argument("--schedule-source", default="manual_cli", help="Trigger origin tag")
    parser.add_argument("--respect-cadence", action="store_true", help="Reuse fresh per-source cache inside expected_interval_minutes")
    parser.add_argument("--skip-connectors", action="store_true", help="Skip external first-party API connectors")
    parser.add_argument("--skip-deep-fetch", action="store_true", help="Skip selective article HTML lead extraction")
    args = parser.parse_args()
    fetch_raw_snapshot(
        args.base_dir,
        schedule_source=args.schedule_source,
        respect_cadence=args.respect_cadence,
        skip_connectors=args.skip_connectors,
        skip_deep_fetch=args.skip_deep_fetch,
    )


if __name__ == "__main__":
    main()
