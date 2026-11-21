"""Post-sync / on-demand live site reconciliation for sanitized V3 telemetry & archives."""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from pipeline.bilingual import enrich_bilingual_events, enrich_bilingual_topics
from pipeline.build_briefing import _postprocess_and_prune_cross_category
from pipeline.connectors.base import HttpCacheStore
from pipeline.connectors.sec_edgar import fetch_sec_edgar
from pipeline.manifest import atomic_write_json, load_json_if_exists
from pipeline.market_quotes import refresh_market_quotes_file
from pipeline.sources import CATEGORIES, CATEGORY_FILES
from pipeline.time_utils import now_shanghai, to_iso_shanghai
from pipeline.v3_builder import build_v3_artifacts


def _load_secrets_env_if_present() -> None:
    env_file = Path("/etc/insight-pro/secrets.env")
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def backfill_history_index(root: Path) -> int:
    """Fill missing generated_at/input_cutoff_at/published_at in history/smart_index.json."""
    hist_path = root / "history" / "smart_index.json"
    doc = load_json_if_exists(hist_path, default=[])
    entries = doc if isinstance(doc, list) else (doc.get("entries") or doc.get("batches") or [] if isinstance(doc, dict) else [])
    fixed = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("generated_at") and entry.get("input_cutoff_at"):
            continue
        rel = str(entry.get("path") or "").strip("/")
        if rel:
            arc_man = load_json_if_exists(root / rel / "manifest.json", default={})
            if isinstance(arc_man, dict):
                if not entry.get("generated_at") and arc_man.get("generated_at"):
                    entry["generated_at"] = arc_man["generated_at"]
                if not entry.get("input_cutoff_at") and arc_man.get("input_cutoff_at"):
                    entry["input_cutoff_at"] = arc_man["input_cutoff_at"]
        bid = str(entry.get("batch_id") or "")
        m_bid = re.search(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})", bid)
        iso_guess = None
        if m_bid:
            y, mo, d, hh, mm, ss = m_bid.groups()
            iso_guess = f"{y}-{mo}-{d}T{hh}:{mm}:{ss}+08:00"
        elif rel:
            m_rel = re.search(r"(\d{4}-\d{2}-\d{2})/(\d{2})-?(\d{2})(?:-?(\d{2}))?", rel)
            if m_rel:
                d_str, hh, mm, ss = m_rel.group(1), m_rel.group(2), m_rel.group(3), (m_rel.group(4) or "00")
                iso_guess = f"{d_str}T{hh}:{mm}:{ss}+08:00"
        if not iso_guess and entry.get("display"):
            m_disp = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2})", str(entry["display"]))
            if m_disp:
                iso_guess = f"{m_disp.group(1)}T{m_disp.group(2)}:{m_disp.group(3)}:00+08:00"
        if iso_guess:
            if not entry.get("generated_at"):
                entry["generated_at"] = iso_guess
            if not entry.get("input_cutoff_at"):
                entry["input_cutoff_at"] = iso_guess
            if not entry.get("published_at"):
                entry["published_at"] = iso_guess
            fixed += 1
    if fixed > 0:
        atomic_write_json(hist_path, doc)
    return fixed


def _extract_raw_items_by_cat(root: Path) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for cat in CATEGORIES:
        raw_doc = load_json_if_exists(root / CATEGORY_FILES[cat], default={}) or {}
        items: List[dict] = []
        if isinstance(raw_doc, dict):
            for plat in raw_doc.get("platforms") or []:
                if isinstance(plat, dict):
                    items.extend(x for x in (plat.get("items") or []) if isinstance(x, dict))
        out[cat] = items
    return out


def refresh_and_sanitize_site_data(root: Path | str, *, refresh_sec: bool = False) -> Dict[str, Any]:
    """Reconcile existing live JSON artifacts with latest P0-P2 pipeline rules without needing Gemini regeneration."""
    _load_secrets_env_if_present()
    base = Path(root)
    now_iso = to_iso_shanghai(now_shanghai())

    hist_fixed = backfill_history_index(base)
    mq = refresh_market_quotes_file(base)

    # Restore non-empty manifest schema from data/manifest.json or root manifest.json
    manifest_data = load_json_if_exists(base / "data" / "manifest.json", default=None)
    manifest_root = load_json_if_exists(base / "manifest.json", default=None)
    manifest: Dict[str, Any] = {}
    for cand in (manifest_data, manifest_root):
        if isinstance(cand, dict) and cand.get("smart"):
            manifest = cand
            break
    if not manifest:
        manifest = manifest_data if isinstance(manifest_data, dict) else (manifest_root if isinstance(manifest_root, dict) else {})

    smart_meta = manifest.setdefault("smart", {})
    batch_id = str(smart_meta.get("latest_batch_id") or manifest.get("batch_id") or "live-reconciled")
    generated_at = str(smart_meta.get("generated_at") or manifest.get("generated_at") or now_iso)
    cat_manifest = smart_meta.setdefault("categories", {})

    connectors_latest = load_json_if_exists(base / "data" / "connectors_latest.json", default={})
    if not isinstance(connectors_latest, dict):
        connectors_latest = {}
    connectors_payload: Dict[str, Any] = {
        "entity_updates": dict(connectors_latest.get("entity_updates") or {}),
        "tech_tools": list(connectors_latest.get("tech_tools") or []),
        "calendar_events": list(connectors_latest.get("calendar_events") or []),
        "items": list(connectors_latest.get("items") or []),
    }
    if not connectors_payload["tech_tools"]:
        existing_tt = load_json_if_exists(base / "data" / "tech_tools.json", default={}) or {}
        connectors_payload["tech_tools"] = [
            t for t in (existing_tt.get("tools") or []) if not str(t.get("tool_id") or "").startswith("tool_evt_")
        ]

    sec_stale_check = base / "data" / "sec_companyfacts_cache.json"
    if refresh_sec or not sec_stale_check.exists():
        try:
            sec_res = fetch_sec_edgar(HttpCacheStore(base), base_dir=str(base))
            for eid, upd in (sec_res.get("entity_updates") or {}).items():
                cur = connectors_payload["entity_updates"].setdefault(eid, {})
                cur.update(upd)
            if sec_res.get("calendar_items"):
                connectors_payload["calendar_events"].extend(sec_res["calendar_items"])
        except Exception:
            pass

    cat_docs: Dict[str, dict] = {}
    for cat in CATEGORIES:
        fname = f"analysis_{cat}.json"
        arc_rel = str((cat_manifest.get(cat) or {}).get("path") or "")
        doc = load_json_if_exists(base / fname, default=None)
        if not (isinstance(doc, dict) and doc.get("events")) and arc_rel:
            doc = load_json_if_exists(base / arc_rel, default=None)
        if isinstance(doc, dict) and doc.get("events"):
            cat_docs[cat] = doc
            cat_manifest.setdefault(cat, {})
            if batch_id == "live-reconciled" and doc.get("batch_id"):
                batch_id = str(doc["batch_id"])
            if doc.get("generated_at"):
                generated_at = str(doc["generated_at"])

    if not cat_docs:
        return {"ok": False, "reason": "no_analysis_docs_found", "history_fixed": hist_fixed}

    _postprocess_and_prune_cross_category(cat_docs, cat_manifest, max_per_category=14)

    for cat, doc in cat_docs.items():
        enrich_bilingual_events(doc.get("events") or [])
        doc["published_at"] = now_iso
        atomic_write_json(base / f"analysis_{cat}.json", doc)
        arc_rel = str((cat_manifest.get(cat) or {}).get("path") or "")
        if arc_rel and (base / arc_rel).parent.exists():
            atomic_write_json(base / arc_rel, doc)

    raw_items_by_cat = _extract_raw_items_by_cat(base)
    prev_cat_events = {c: [] for c in cat_docs}
    v3_summary = build_v3_artifacts(
        base,
        batch_id=batch_id,
        generated_at_iso=generated_at,
        cat_docs=cat_docs,
        prev_cat_events=prev_cat_events,
        prev_batch_id=smart_meta.get("previous_batch_id"),
        connectors_payload=connectors_payload,
        raw_items_by_cat=raw_items_by_cat,
    )

    st_path = base / "data" / "storylines_index.json"
    st_doc = load_json_if_exists(st_path, default={})
    if isinstance(st_doc, dict) and st_doc.get("storylines"):
        enrich_bilingual_topics(st_doc["storylines"])
        atomic_write_json(st_path, st_doc)

    # Also ensure ai_progress.json items carry English title_en/what_it_does_en
    from pipeline.bilingual import _has_cjk_text, _translate_zh_to_en_glossary
    ai_p_path = base / "data" / "ai_progress.json"
    ai_p_doc = load_json_if_exists(ai_p_path, default={})
    if isinstance(ai_p_doc, dict):
        changed_ai = False
        for item in ai_p_doc.get("timeline") or []:
            if isinstance(item, dict):
                te = str(item.get("title_en") or "")
                if not te or _has_cjk_text(te):
                    item["title_en"] = _translate_zh_to_en_glossary(str(item.get("title") or ""), [str(item.get("company_name") or "")])
                    changed_ai = True
                we = str(item.get("what_it_does_en") or "")
                if not we or _has_cjk_text(we):
                    item["what_it_does_en"] = _translate_zh_to_en_glossary(str(item.get("what_it_does") or ""), [str(item.get("company_name") or "")])
                    changed_ai = True
        for comp in ai_p_doc.get("companies") or []:
            if isinstance(comp, dict):
                for item in comp.get("items") or []:
                    if isinstance(item, dict):
                        te = str(item.get("title_en") or "")
                        if not te or _has_cjk_text(te):
                            item["title_en"] = _translate_zh_to_en_glossary(str(item.get("title") or ""), [str(comp.get("company_name") or "")])
                            changed_ai = True
        if changed_ai:
            atomic_write_json(ai_p_path, ai_p_doc)

    manifest["site_published_at"] = now_iso
    manifest["v3"] = v3_summary
    atomic_write_json(base / "data" / "manifest.json", manifest)
    atomic_write_json(base / "manifest.json", manifest)

    return {
        "ok": True,
        "history_fixed": hist_fixed,
        "market_quotes_count": len(mq.get("quotes") or {}),
        **v3_summary,
    }
