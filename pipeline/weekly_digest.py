"""2-Stage Weekly Major Events Digest Generator (Monday–Sunday + Admin Dynamic Schedule).

Stage 1 (Programmatic Distillation):
  - Collects smart analysis archives across the natural Monday-Sunday window (Asia/Shanghai)
  - Filters out chatter, promos, gossip, and omnibus summary roundups
  - Deduplicates globally across days & categories, merging multi-day arcs into timeline evolution
  - Separates events cleanly into 4 non-overlapping sectors (`macro_finance`, `geopolitics`, `tech_ai`, `industry_society`)
  - Scores and tiers into P0 / P1 / P2 priorities (4-6 per sector, <= 24 total)

Stage 2 (AI Assisted Editorial Synthesis):
  - Passes ONLY the distilled candidates to Gemini via `gemini_pool.py` to generate week theme,
    executive thesis bullets, one-line quick scan takeaways, deep impact notes, cross-sector links,
    and next-week catalysts (with high-quality deterministic fallback when offline).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.request import Request, urlopen

from pipeline.dedup import (
    has_authoritative_primary_source,
    is_consumer_promo_or_fluff,
    is_omnibus_digest_title,
    strip_raw_urls_and_domain_tails,
    title_similarity,
)
from pipeline.gemini_pool import call_gemini_json, count_healthy_keys
from pipeline.heavy_classifier import compute_deterministic_heavy_score, is_heavy_noise_excluded
from pipeline.manifest import atomic_write_json, load_json_if_exists
from pipeline.time_utils import SHANGHAI_TZ, now_shanghai, parse_iso_datetime, to_iso_shanghai


SECTOR_META: Tuple[Dict[str, str], ...] = (
    {
        "sector_id": "macro_finance",
        "title": "宏观与金融市场",
        "title_en": "Macro & Financial Markets",
        "subtitle": "央行利率、汇市债券、黄金原油与 A 股 / 美股定价主线",
        "subtitle_en": "Central banks, yields, commodities & broad equity pricing",
        "accent": "amber",
    },
    {
        "sector_id": "geopolitics",
        "title": "国际地缘与政策",
        "title_en": "Geopolitics & Policy",
        "subtitle": "大国博弈、外交关税、国际安全局势与监管法案落地",
        "subtitle_en": "Diplomacy, trade policy, geopolitical conflicts & regulation",
        "accent": "rose",
    },
    {
        "sector_id": "tech_ai",
        "title": "科技与 AI 前沿",
        "title_en": "Tech & AI Frontier",
        "subtitle": "大模型迭代、算力芯片、开源生态与前沿科研突破",
        "subtitle_en": "Foundation models, AI chips, compute & breakthroughs",
        "accent": "blue",
    },
    {
        "sector_id": "industry_society",
        "title": "产业与综合要闻",
        "title_en": "Industry & Real Economy",
        "subtitle": "巨头经营动态、新能源汽车、航空制造与重大公共事件",
        "subtitle_en": "Corporate shifts, supply chains, autos, energy & public events",
        "accent": "emerald",
    },
)

SECTOR_IDS: Tuple[str, ...] = tuple(s["sector_id"] for s in SECTOR_META)
DAY_LABELS_ZH: Tuple[str, ...] = ("周日", "周一", "周二", "周三", "周四", "周五", "周六")

_TECH_AI_RE = re.compile(
    r"(?:openai|anthropic|claude|gpt-?\d|gemini|deepseek|qwen|llama|mistral|hugging\s?face|arxiv|大模型|"
    r"人工智能|\bai\b|aigc|算力|芯片|半导体|晶圆|光刻机|hbm|英伟达|nvidia|amd|tsmc|台积电|asml|"
    r"开源模型|github|微软.*ai|谷歌.*ai|苹果.*ai|马斯克.*xai|机器人|自动驾驶|量子计算|云计算)",
    re.I,
)
_GEOPOLITICS_RE = re.compile(
    r"(?:特朗普|拜登|白宫|五角大楼|国务院|外交部|联合国|北约|欧盟|apec|g7|g20|峰会|访华|会晤|"
    r"关税|制裁|出口管制|禁令|停火|停战|空袭|导弹|无人机|军舰|海峡|霍尔木兹|美伊|俄乌|中东|加沙|"
    r"以色列|伊朗|俄罗斯|乌克兰|菲律宾|南海|外交|协定|法案|听证会|国会|参议院|大选)",
    re.I,
)
_MACRO_FINANCE_RE = re.compile(
    r"(?:美联储|fomc|央行|降息|加息|降准|逆回购|通胀|cpi|pce|非农|gdp|美债|国债|收益率|汇率|人民币|美元指数|"
    r"现货黄金|金价|白银|原油|布伦特|wti|纳指|标普|道指|上证|沪指|深成指|创业板|恒生|恒指|a股|港股|美股|"
    r"基金|公募|险资|ipo|证监|交易所|利率|货币政策|财政预算|流动性)",
    re.I,
)
_INDUSTRY_CORP_RE = re.compile(
    r"(?:利润|营收|盈利|净利润|财报|亏损|利润预警|裁员|并购|收购|销量|航司|燃油成本|汽车|订单|产能|破产|门店|消费|零售|制造)",
    re.I,
)
_WEEKLY_INTRADAY_NOISE_RE = re.compile(
    r"(?:^美股盘前|半日涨超|高开低走|低开高走|午评|收评|集体回落|集体收跌|打包粤菜|被撞亡|U17|国少|早间要闻)",
    re.I,
)
_SUBJECT_ANCHORS_RE = re.compile(
    r"(?:英伟达|nvidia|黄仁勋|anthropic|openai|DeepSeek|马斯克|特朗普|美联储|央行|黄金|白银|原油|霍尔木兹|利比亚|神舟二十四|COP31)",
    re.I,
)
_EVIDENCE_RANK = {
    "official_confirmed": 4,
    "multi_source": 3,
    "single_source": 2,
    "needs_verification": 1,
}
_SEV_RANK = {"S": 3, "A": 2, "B": 1}


def _clean_text(raw: Any, max_len: int = 320) -> str:
    txt = strip_raw_urls_and_domain_tails(str(raw or ""))
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) > max_len:
        return txt[: max_len - 1].rstrip("，。；,; ") + "…"
    return txt


def _cjk_bigrams(text: str) -> set[str]:
    cleaned = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


def _extract_anchors(title: str, entities: Sequence[str]) -> set[str]:
    anchors = {str(e).strip().lower() for e in entities if isinstance(e, str) and len(e.strip()) >= 2}
    for m in _SUBJECT_ANCHORS_RE.findall(title or ""):
        anchors.add(m.lower())
    return anchors


def _is_duplicate_story(a_title: str, b_title: str, a_entities: Sequence[str], b_entities: Sequence[str]) -> bool:
    if not a_title or not b_title:
        return False
    if title_similarity(a_title, b_title) >= 0.44:
        return True
    bg_a = _cjk_bigrams(a_title)
    bg_b = _cjk_bigrams(b_title)
    anchors_a = _extract_anchors(a_title, a_entities)
    anchors_b = _extract_anchors(b_title, b_entities)
    shared_anchors = anchors_a & anchors_b
    # If two items share >= 2 distinctive subjects (e.g. 黄仁勋 + 英伟达) or share a CEO/person + related phrasing, treat as one evolving story
    if len(shared_anchors) >= 2:
        return True
    if bg_a and bg_b:
        jac = len(bg_a & bg_b) / len(bg_a | bg_b)
        if jac >= 0.40:
            return True
        if jac >= 0.22 and shared_anchors:
            return True
    # Merge companion opinion riffs mentioning exact same key executive return / central bank rate decision
    if ("黄仁勋" in anchors_a and "黄仁勋" in anchors_b) or ("神舟二十四" in anchors_a and "神舟二十四" in anchors_b):
        return True
    return False


def classify_weekly_sector(ev: Dict[str, Any]) -> str:
    """Assign exactly ONE weekly sector cleanly so sectors never mix duplicates or topics."""
    cat = str(ev.get("category") or "").lower().strip()
    title = str(ev.get("title_zh") or ev.get("title") or "")
    summary = str(ev.get("fact_summary") or ev.get("summary") or "")
    blob = f"{title} {summary[:220]}"

    # Specific keyword disambiguation takes precedence over broad source bucket
    tech_hits = len(_TECH_AI_RE.findall(blob))
    geo_hits = len(_GEOPOLITICS_RE.findall(blob))
    fin_hits = len(_MACRO_FINANCE_RE.findall(blob))
    corp_hits = len(_INDUSTRY_CORP_RE.findall(blob))

    if cat == "tech" or tech_hits >= 2 or (tech_hits >= 1 and fin_hits == 0 and geo_hits == 0):
        return "tech_ai"
    if corp_hits >= 2 and fin_hits == 0 and geo_hits == 0:
        return "industry_society"
    if geo_hits >= 2 or (cat == "global" and geo_hits >= 1 and fin_hits == 0):
        return "geopolitics"
    if fin_hits >= 2 or (cat == "finance" and fin_hits >= 1 and corp_hits < 2):
        return "macro_finance"
    if cat == "global":
        return "geopolitics"
    if cat == "finance":
        if corp_hits >= 1:
            return "industry_society"
        return "macro_finance"
    return "industry_society"


def compute_natural_week_bounds(ref_dt: Optional[datetime] = None) -> Dict[str, Any]:
    """Compute Asia/Shanghai Monday-to-Sunday window and ISO week ID."""
    dt = ref_dt.astimezone(SHANGHAI_TZ) if ref_dt else now_shanghai()
    iso_year, iso_week, iso_weekday = dt.isocalendar()
    monday = (dt - timedelta(days=iso_weekday - 1)).date()
    sunday = monday + timedelta(days=6)
    dates = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
    week_id = f"{iso_year}-W{iso_week:02d}"
    return {
        "week_id": week_id,
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "date_range_label": f"{monday.strftime('%m.%d')} 周一 — {sunday.strftime('%m.%d')} 周日",
        "dates": dates,
    }


def _parse_hhmm_or_iso_time(raw_iso: str, fallback_hhmm: str = "") -> str:
    dt = parse_iso_datetime(raw_iso)
    if dt is not None:
        return dt.astimezone(SHANGHAI_TZ).strftime("%m-%d %H:%M")
    return fallback_hhmm


def _load_archive_snapshots(base_path: Path, candidate_dates: Sequence[str], include_root: bool = True) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Return sorted chronological tuples `(date_str, time_label, analysis_doc)`."""
    snapshots: List[Tuple[str, str, Dict[str, Any]]] = []
    smart_root = base_path / "archives" / "smart"
    seen_files: set[Path] = set()

    for d_str in sorted(candidate_dates):
        day_dir = smart_root / d_str
        if not day_dir.is_dir():
            continue
        batch_dirs = sorted([p for p in day_dir.iterdir() if p.is_dir()], key=lambda p: p.name)
        for bdir in batch_dirs:
            t_label = bdir.name.replace("-", ":")
            for cat in ("finance", "global", "tech", "general"):
                fp = bdir / f"analysis_{cat}.json"
                if not fp.is_file() or fp in seen_files:
                    continue
                seen_files.add(fp)
                doc = load_json_if_exists(fp)
                if isinstance(doc, dict) and isinstance(doc.get("events"), list):
                    snapshots.append((d_str, f"{d_str[5:]} {t_label}", doc))

    if include_root:
        today_str = now_shanghai().date().isoformat()
        for cat in ("finance", "global", "tech", "general"):
            fp = base_path / f"analysis_{cat}.json"
            if fp.is_file():
                doc = load_json_if_exists(fp)
                if isinstance(doc, dict) and isinstance(doc.get("events"), list):
                    d_str = str(doc.get("generated_at") or today_str)[:10]
                    t_label = _parse_hhmm_or_iso_time(str(doc.get("generated_at") or ""), d_str[5:])
                    snapshots.append((d_str, t_label, doc))

    return snapshots


def distill_weekly_candidates(
    base_dir: Path | str = ".",
    *,
    ref_dt: Optional[datetime] = None,
    max_per_sector: int = 6,
) -> Dict[str, Any]:
    """
    Stage 1 pure deterministic distillation:
      - Collects Mon-Sun snapshots (falling back up to trailing 7 days if early in week)
      - Filters noise / fluff / non-authoritative rumors
      - Merges recurring storyline / event_id occurrences and runs strict global dedup
      - Assigns strict 4-sector separation and P0 / P1 / P2 priorities
    """
    base_path = Path(base_dir)
    week_info = compute_natural_week_bounds(ref_dt)
    today_date = (ref_dt.astimezone(SHANGHAI_TZ) if ref_dt else now_shanghai()).date()
    effective_dates = [d for d in week_info["dates"] if d <= today_date.isoformat()]
    if not effective_dates:
        effective_dates = [today_date.isoformat()]

    snapshots = _load_archive_snapshots(base_path, effective_dates, include_root=True)
    window_mode = "natural_week"
    # Early in a new week (e.g., Mon/Tue morning before many archives), broaden scan window gently if sparse
    distinct_days_found = {s[0] for s in snapshots}
    if len(distinct_days_found) < 2 and (base_path / "archives" / "smart").is_dir():
        rolling_dates = [(today_date - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        snapshots = _load_archive_snapshots(base_path, rolling_dates, include_root=True)
        window_mode = "natural_week_with_trailing_7d_backfill"

    # Load supplementary finance impact & calendar
    finance_doc = load_json_if_exists(base_path / "data" / "finance_impact.json") or {}
    impact_map = finance_doc.get("event_impact_map") if isinstance(finance_doc, dict) else {}
    if not isinstance(impact_map, dict):
        impact_map = {}

    calendar_doc = load_json_if_exists(base_path / "data" / "calendar.json") or {}
    raw_cal_events = calendar_doc.get("events") if isinstance(calendar_doc, dict) else []
    if not isinstance(raw_cal_events, list):
        raw_cal_events = []

    raw_event_count = 0
    clusters: Dict[str, Dict[str, Any]] = {}

    for snap_date, snap_time_label, doc in snapshots:
        for ev in doc.get("events") or []:
            if not isinstance(ev, dict):
                continue
            raw_event_count += 1
            title = _clean_text(ev.get("title_zh") or ev.get("title") or "", 140)
            summary = _clean_text(ev.get("fact_summary") or ev.get("summary") or "", 320)
            if not title or len(title) < 6:
                continue
            if is_omnibus_digest_title(title) or is_consumer_promo_or_fluff(title, summary):
                continue
            if is_heavy_noise_excluded(title, summary) or _WEEKLY_INTRADAY_NOISE_RE.search(title):
                continue

            sources = [s for s in (ev.get("sources") or []) if isinstance(s, dict)]
            ev_status = str(ev.get("evidence_status") or "single_source")
            if not has_authoritative_primary_source(sources) and ev_status != "official_confirmed":
                continue

            key = str(ev.get("storyline_id") or "").strip() or str(ev.get("event_id") or "").strip()
            if not key:
                continue

            sev = str(ev.get("severity_tier") or "B").upper()
            if sev not in _SEV_RANK:
                sev = "A" if ev.get("importance") == "high" else "B"

            entry = clusters.get(key)
            if entry is None:
                entry = {
                    "cluster_key": key,
                    "event_id": str(ev.get("event_id") or ""),
                    "storyline_id": str(ev.get("storyline_id") or ""),
                    "title": title,
                    "title_en": _clean_text(ev.get("title_en") or "", 160),
                    "fact_summary": summary,
                    "ai_analysis": _clean_text(ev.get("ai_analysis") or "", 340),
                    "speculation_or_outlook": _clean_text(ev.get("speculation_or_outlook") or "", 200),
                    "severity_tier": sev,
                    "evidence_status": ev_status,
                    "heavy_reason_tag": ev.get("heavy_reason_tag"),
                    "category": str(ev.get("category") or "general"),
                    "entities": list(ev.get("entities") or [])[:5],
                    "sources": [],
                    "_seen_urls": set(),
                    "_seen_names": set(),
                    "active_days": [],
                    "first_seen_at": ev.get("first_discovered_at") or ev.get("latest_reported_at") or snap_date,
                    "last_seen_at": ev.get("latest_reported_at") or snap_date,
                    "evolution_steps": [],
                    "_seen_step_titles": set(),
                    "occurrence_count": 0,
                }
                clusters[key] = entry

            entry["occurrence_count"] += 1
            if snap_date not in entry["active_days"]:
                entry["active_days"].append(snap_date)
            if _SEV_RANK.get(sev, 1) > _SEV_RANK.get(entry["severity_tier"], 1):
                entry["severity_tier"] = sev
            if _EVIDENCE_RANK.get(ev_status, 1) > _EVIDENCE_RANK.get(entry["evidence_status"], 1):
                entry["evidence_status"] = ev_status
            if not entry["heavy_reason_tag"] and ev.get("heavy_reason_tag"):
                entry["heavy_reason_tag"] = ev.get("heavy_reason_tag")
            # Keep richest/latest factual summary & analysis
            if len(summary) > len(entry["fact_summary"]):
                entry["fact_summary"] = summary
                entry["title"] = title
            ai_txt = _clean_text(ev.get("ai_analysis") or "", 340)
            if len(ai_txt) > len(entry["ai_analysis"]):
                entry["ai_analysis"] = ai_txt
            out_txt = _clean_text(ev.get("speculation_or_outlook") or "", 200)
            if len(out_txt) > len(entry["speculation_or_outlook"]):
                entry["speculation_or_outlook"] = out_txt

            latest_ts = str(ev.get("latest_reported_at") or "")
            if latest_ts and latest_ts > str(entry["last_seen_at"]):
                entry["last_seen_at"] = latest_ts
                if ev.get("event_id"):
                    entry["event_id"] = str(ev.get("event_id"))

            for e_name in ev.get("entities") or []:
                if isinstance(e_name, str) and e_name not in entry["entities"] and len(entry["entities"]) < 6:
                    entry["entities"].append(e_name)

            for s in sources:
                sname = str(s.get("publisher_name") or s.get("source_name") or "").strip()
                surl = str(s.get("url") or "").strip()
                if surl and surl in entry["_seen_urls"]:
                    continue
                if sname and sname in entry["_seen_names"] and len(entry["sources"]) >= 3:
                    continue
                if surl:
                    entry["_seen_urls"].add(surl)
                if sname:
                    entry["_seen_names"].add(sname)
                entry["sources"].append(
                    {
                        "source_name": sname or "权威信源",
                        "url": surl,
                        "source_tier": s.get("source_tier") or "direct_media",
                    }
                )

            norm_step = re.sub(r"\s+", "", title[:26])
            if norm_step not in entry["_seen_step_titles"]:
                entry["_seen_step_titles"].add(norm_step)
                entry["evolution_steps"].append(
                    {
                        "date": snap_time_label or snap_date,
                        "headline": title,
                        "detail": summary[:140],
                    }
                )

    # Score merged clusters
    scored: List[Dict[str, Any]] = []
    for item in clusters.values():
        day_span = max(1, len(item["active_days"]))
        pub_count = max(1, len(item["_seen_names"]) or len(item["sources"]))
        heavy_base = compute_deterministic_heavy_score(
            item["title"],
            item["fact_summary"],
            independent_publishers=pub_count,
            is_official=item["evidence_status"] == "official_confirmed",
            has_authoritative_source=True,
            age_hours=6.0,
        )
        imp = impact_map.get(item["event_id"]) if isinstance(impact_map, dict) else None
        fin_bonus = 0.0
        impact_tags: List[str] = []
        market_polarity = None
        if isinstance(imp, dict):
            fin_bonus = min(12.0, float(imp.get("intensity") or 0) * 2.2)
            market_polarity = imp.get("polarity")
            if imp.get("tag"):
                impact_tags.append(str(imp.get("tag")))

        sev_bonus = 16.0 if item["severity_tier"] == "S" else 6.0 if item["severity_tier"] == "A" else 0.0
        ev_bonus = 14.0 if item["evidence_status"] == "official_confirmed" else 7.0 if item["evidence_status"] == "multi_source" else 0.0
        span_bonus = min(24.0, (day_span - 1) * 9.0) + min(18.0, pub_count * 4.5)
        score = round(heavy_base + sev_bonus + ev_bonus + span_bonus + fin_bonus, 2)

        # Keep up to 3 evolution checkpoints (first, middle, latest)
        steps = item["evolution_steps"]
        if len(steps) > 3:
            steps = [steps[0], steps[len(steps) // 2], steps[-1]]

        sector_id = classify_weekly_sector(item)
        days_sorted = sorted(item["active_days"])
        scored.append(
            {
                "id": f"wk_{week_info['week_id'].replace('-', '_').lower()}_{item['event_id'] or item['cluster_key']}",
                "event_id": item["event_id"],
                "storyline_id": item["storyline_id"] or None,
                "sector_id": sector_id,
                "priority": "P1",  # tiered below per sector
                "priority_reason": "",
                "weekly_score": score,
                "severity_tier": item["severity_tier"],
                "evidence_status": item["evidence_status"],
                "heavy_reason_tag": item["heavy_reason_tag"],
                "title": item["title"],
                "title_en": item["title_en"],
                "fact_summary": item["fact_summary"],
                "one_line_takeaway": _clean_text(item["fact_summary"] or item["title"], 96),
                "why_it_matters": _clean_text(item["ai_analysis"] or item["fact_summary"], 220),
                "next_week_watch": _clean_text(item["speculation_or_outlook"], 140),
                "active_days": days_sorted,
                "first_seen": days_sorted[0] if days_sorted else week_info["week_start"],
                "last_seen": days_sorted[-1] if days_sorted else week_info["week_end"],
                "day_span": day_span,
                "source_count": pub_count,
                "sources": item["sources"][:5],
                "entities": item["entities"][:5],
                "impact_tags": impact_tags,
                "market_polarity": market_polarity,
                "evolution_steps": steps,
                "last_seen_at": item["last_seen_at"],
            }
        )

    # Sort descending by weekly_score, then run strict GLOBAL cross-sector semantic dedup
    scored.sort(key=lambda x: (-x["weekly_score"], -x["day_span"], -x["source_count"], x["title"]))

    deduped_global: List[Dict[str, Any]] = []
    for cand in scored:
        duplicate_target = None
        for kept in deduped_global:
            if _is_duplicate_story(cand["title"], kept["title"], cand["entities"], kept["entities"]):
                duplicate_target = kept
                break
        if duplicate_target is not None:
            # Absorb any unique days / sources / steps into higher-scored kept item, never emit duplicate!
            for d in cand["active_days"]:
                if d not in duplicate_target["active_days"]:
                    duplicate_target["active_days"].append(d)
            duplicate_target["active_days"].sort()
            duplicate_target["first_seen"] = duplicate_target["active_days"][0]
            duplicate_target["last_seen"] = duplicate_target["active_days"][-1]
            duplicate_target["day_span"] = len(duplicate_target["active_days"])
            existing_names = {s["source_name"] for s in duplicate_target["sources"]}
            for src in cand["sources"]:
                if src["source_name"] not in existing_names and len(duplicate_target["sources"]) < 5:
                    existing_names.add(src["source_name"])
                    duplicate_target["sources"].append(src)
                    duplicate_target["source_count"] += 1
            continue
        deduped_global.append(cand)

    # Bucket cleanly into 4 separate sectors (strict cap, zero mixing)
    sector_buckets: Dict[str, List[Dict[str, Any]]] = {sid: [] for sid in SECTOR_IDS}
    for it in deduped_global:
        sid = it["sector_id"]
        if len(sector_buckets[sid]) < max_per_sector:
            sector_buckets[sid].append(it)

    # Priority assignment inside each sector: strictly P0 (top 1-2), P1 (next 2), P2 (rest)
    all_selected: List[Dict[str, Any]] = []
    p0_threshold = sorted([x["weekly_score"] for x in deduped_global], reverse=True)[min(5, max(0, len(deduped_global) - 1))] if deduped_global else 50.0
    for sid in SECTOR_IDS:
        bucket = sector_buckets[sid]
        for idx, it in enumerate(bucket):
            if idx == 0 or (idx == 1 and (it["severity_tier"] == "S" or it["weekly_score"] >= p0_threshold)):
                it["priority"] = "P0"
            elif idx <= 3:
                it["priority"] = "P1"
            else:
                it["priority"] = "P2"
            reason_parts: List[str] = []
            if it.get("evidence_status") == "official_confirmed":
                reason_parts.append("官方确认")
            elif it.get("evidence_status") == "multi_source":
                reason_parts.append("多源互证")
            if int(it.get("day_span") or 1) >= 2:
                reason_parts.append(f"跨{it['day_span']}天演化")
            if it.get("impact_tags"):
                reason_parts.append("市场联动")
            if not reason_parts:
                reason_parts.append(f"{it.get('source_count', 1)}家信源")
            it["priority_reason"] = " · ".join(reason_parts[:3])
            all_selected.append(it)

    # Next-week upcoming catalysts from calendar.json
    week_end_str = week_info["week_end"]
    upcoming_cal: List[Dict[str, Any]] = []
    for ce in raw_cal_events:
        if not isinstance(ce, dict):
            continue
        date_str = str(ce.get("scheduled_date") or ce.get("date") or "")[:10]
        if date_str and date_str >= week_end_str:
            upcoming_cal.append(ce)
    upcoming_cal.sort(key=lambda x: str(x.get("scheduled_date") or x.get("date") or "9999"))

    return {
        "week_info": week_info,
        "window_mode": window_mode,
        "raw_scanned_count": raw_event_count,
        "unique_cluster_count": len(deduped_global),
        "sector_buckets": sector_buckets,
        "items": all_selected,
        "upcoming_calendar": upcoming_cal[:8],
    }


def _build_deterministic_synthesis(stage1: Dict[str, Any]) -> Dict[str, Any]:
    buckets: Dict[str, List[Dict[str, Any]]] = stage1["sector_buckets"]
    p0_items = [it for it in stage1["items"] if it["priority"] == "P0"]
    top_titles = [it["title"] for it in sorted(p0_items, key=lambda x: -x["weekly_score"])[:3]]

    week_theme = (
        f"本周核心脉络：{'；'.join(t[:24] for t in top_titles[:2])}"
        if top_titles
        else "本周全球市场与产业关键进展全景盘点"
    )
    thesis: List[str] = []
    for sid in ("macro_finance", "geopolitics", "tech_ai"):
        b = buckets.get(sid) or []
        if b:
            meta = next(m for m in SECTOR_META if m["sector_id"] == sid)
            thesis.append(f"【{meta['title']}】{b[0]['title']}——{b[0]['one_line_takeaway']}")
    if not thesis:
        thesis = ["本周各核心板块已完成多源交叉去重与优先级分级，点击条目可按大概看或细看切换。"]

    keywords: List[str] = []
    for it in sorted(stage1["items"], key=lambda x: -x["weekly_score"]):
        for ent in it.get("entities") or []:
            short = str(ent).split("/")[0].strip()[:12]
            if short and short not in keywords and len(keywords) < 6:
                keywords.append(short)

    sectors_summary: Dict[str, str] = {}
    for meta in SECTOR_META:
        sid = meta["sector_id"]
        b = buckets.get(sid) or []
        if b:
            sectors_summary[sid] = f"本周共收录 {len(b)} 项高权重进展，核心围绕「{b[0]['title'][:28]}」展开。"
        else:
            sectors_summary[sid] = "本统计周期内该板块暂无高优先级异动。"

    cross_threads: List[Dict[str, str]] = []
    if buckets["geopolitics"] and buckets["macro_finance"]:
        cross_threads.append(
            {
                "title": "地缘风险外溢 -> 大宗商品与股指避险重定价",
                "from_sector": "geopolitics",
                "to_sector": "macro_finance",
                "logic": f"地缘侧「{buckets['geopolitics'][0]['title'][:24]}」与金融侧「{buckets['macro_finance'][0]['title'][:24]}」形成共振定价。",
            }
        )
    if buckets["tech_ai"] and (buckets["industry_society"] or buckets["macro_finance"]):
        cross_threads.append(
            {
                "title": "AI 前沿演进与算力链 -> 科技估值与产业资本开支",
                "from_sector": "tech_ai",
                "to_sector": "industry_society" if buckets["industry_society"] else "macro_finance",
                "logic": f"AI 侧「{buckets['tech_ai'][0]['title'][:24]}」持续牵引下游产业与资本开支预期。",
            }
        )

    next_catalysts: List[Dict[str, str]] = []
    for ce in stage1["upcoming_calendar"][:3]:
        ce_title = _clean_text(ce.get("title") or ce.get("event_name") or "", 60)
        if not ce_title:
            continue
        ce_date = str(ce.get("scheduled_date") or ce.get("date") or "下周待定")[:10]
        next_catalysts.append(
            {
                "date": ce_date,
                "title": ce_title,
                "sector_id": classify_weekly_sector({"title": ce_title, "category": ce.get("category") or "finance"}),
                "why_watch": _clean_text(ce.get("watch_focus") or ce.get("description") or "验证市场预期与官方数据是否一致", 90),
                "action_hint": "可前往前瞻验证区参与概率预判",
            }
        )

    return {
        "generation_mode": "deterministic_weekly_v1",
        "model_used": None,
        "week_theme": week_theme,
        "executive_thesis": thesis[:3],
        "keywords": keywords[:6],
        "sectors_summary": sectors_summary,
        "cross_sector_threads": cross_threads,
        "next_week_catalysts": next_catalysts,
        "item_overrides": {},
    }


def _enrich_with_ai(stage1: Dict[str, Any], base_path: Path, use_ai: bool = True) -> Dict[str, Any]:
    fallback = _build_deterministic_synthesis(stage1)
    items = stage1["items"]
    if not use_ai or not items or count_healthy_keys(base_dir=base_path) <= 0:
        return fallback

    compact_candidates = [
        {
            "id": it["id"],
            "sector_id": it["sector_id"],
            "priority": it["priority"],
            "day_span": it["day_span"],
            "source_count": it["source_count"],
            "title": it["title"],
            "fact_summary": it["fact_summary"][:180],
            "why_hint": it["why_it_matters"][:140],
        }
        for it in items
    ]
    compact_cal = [
        {
            "date": str(c.get("scheduled_date") or c.get("date") or "")[:10],
            "title": str(c.get("title") or "")[:60],
        }
        for c in stage1["upcoming_calendar"][:5]
    ]

    prompt = (
        "你是镜信 MirrorBrief 周刊首席主编。以下是本周经过去重、分板块提纯后的重大新闻事件清单（4 个板块已固定，不得增删 ID 或重复编排）：\n"
        f"{json.dumps(compact_candidates, ensure_ascii=False)}\n\n"
        f"下周日程参考：{json.dumps(compact_cal, ensure_ascii=False)}\n\n"
        "请用极其凝练、客观、克制的中文输出严格 JSON 对象（禁止任何表情符号 emoji）：\n"
        "{\n"
        '  "week_theme": "一句话点透本周总基调（<=32字）",\n'
        '  "executive_thesis": ["3条高度浓缩的本周核心主线结论，每条<=55字"],\n'
        '  "keywords": ["4到6个本周高频关键词"],\n'
        '  "sectors_summary": {\n'
        '    "macro_finance": "宏观金融板块本周一句总结",\n'
        '    "geopolitics": "国际地缘政策板块本周一句总结",\n'
        '    "tech_ai": "科技与AI板块本周一句总结",\n'
        '    "industry_society": "产业综合板块本周一句总结"\n'
        "  },\n"
        '  "items": [\n'
        '    {"id": "对应id", "one_line_takeaway": "适合大概看的一句话精华(<=45字)", "why_it_matters": "适合细看的深度影响研判(60-110字)", "next_week_watch": "下周跟踪看点(<=45字)"}\n'
        "  ],\n"
        '  "cross_sector_threads": [\n'
        '    {"title": "跨板块暗线标题", "from_sector": "macro_finance|geopolitics|tech_ai|industry_society", "to_sector": "macro_finance|geopolitics|tech_ai|industry_society", "logic": "一句话因果链"}\n'
        "  ],\n"
        '  "next_week_catalysts": [\n'
        '    {"date": "YYYY-MM-DD", "title": "下周重点盯防事件", "sector_id": "macro_finance|geopolitics|tech_ai|industry_society", "why_watch": "核心看点", "action_hint": "建议结合站内某功能验证"}\n'
        "  ]\n"
        "}"
    )

    res = call_gemini_json(
        scope="weekly_digest",
        prompt=prompt,
        tier="tier1",
        temperature=0.2,
        timeout_ms=28_000,
        base_dir=base_path,
    )
    if not res.ok or not isinstance(res.data, dict):
        return fallback

    data = res.data
    overrides: Dict[str, Dict[str, str]] = {}
    for row in data.get("items") or []:
        if isinstance(row, dict) and row.get("id"):
            overrides[str(row["id"])] = {
                "one_line_takeaway": _clean_text(row.get("one_line_takeaway") or "", 110),
                "why_it_matters": _clean_text(row.get("why_it_matters") or "", 240),
                "next_week_watch": _clean_text(row.get("next_week_watch") or "", 120),
            }

    sectors_summary = dict(fallback["sectors_summary"])
    if isinstance(data.get("sectors_summary"), dict):
        for sid in SECTOR_IDS:
            val = _clean_text(data["sectors_summary"].get(sid) or "", 110)
            if val:
                sectors_summary[sid] = val

    thesis = [
        _clean_text(x, 120)
        for x in (data.get("executive_thesis") or [])
        if isinstance(x, str) and len(x.strip()) >= 6
    ][:4]

    keywords = [
        _clean_text(x, 20)
        for x in (data.get("keywords") or [])
        if isinstance(x, str) and x.strip()
    ][:6]

    threads: List[Dict[str, str]] = []
    for th in (data.get("cross_sector_threads") or [])[:3]:
        if isinstance(th, dict) and th.get("title") and th.get("logic"):
            fs = str(th.get("from_sector") or "geopolitics")
            ts = str(th.get("to_sector") or "macro_finance")
            threads.append(
                {
                    "title": _clean_text(th["title"], 60),
                    "from_sector": fs if fs in SECTOR_IDS else "geopolitics",
                    "to_sector": ts if ts in SECTOR_IDS else "macro_finance",
                    "logic": _clean_text(th["logic"], 140),
                }
            )

    catalysts: List[Dict[str, str]] = []
    for cat in (data.get("next_week_catalysts") or [])[:4]:
        if isinstance(cat, dict) and cat.get("title"):
            sid = str(cat.get("sector_id") or "macro_finance")
            catalysts.append(
                {
                    "date": _clean_text(cat.get("date") or "下周", 24),
                    "title": _clean_text(cat["title"], 70),
                    "sector_id": sid if sid in SECTOR_IDS else "macro_finance",
                    "why_watch": _clean_text(cat.get("why_watch") or "", 110),
                    "action_hint": _clean_text(cat.get("action_hint") or "前瞻验证与事件追踪同步盯防", 60),
                }
            )

    return {
        "generation_mode": "ai_weekly_assisted_v1",
        "model_used": res.model_used,
        "week_theme": _clean_text(data.get("week_theme") or fallback["week_theme"], 70) or fallback["week_theme"],
        "executive_thesis": thesis or fallback["executive_thesis"],
        "keywords": keywords or fallback["keywords"],
        "sectors_summary": sectors_summary,
        "cross_sector_threads": threads or fallback["cross_sector_threads"],
        "next_week_catalysts": catalysts or fallback["next_week_catalysts"],
        "item_overrides": overrides,
    }


def build_and_write_weekly_digest(
    base_dir: Path | str = ".",
    *,
    ref_dt: Optional[datetime] = None,
    use_ai: bool = True,
    schedule_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base_path = Path(base_dir)
    stage1 = distill_weekly_candidates(base_path, ref_dt=ref_dt)
    synth = _enrich_with_ai(stage1, base_path, use_ai=use_ai)
    overrides = synth.get("item_overrides") or {}

    sectors_out: List[Dict[str, Any]] = []
    p0_total = 0
    total_items = 0

    for meta in SECTOR_META:
        sid = meta["sector_id"]
        items_clean: List[Dict[str, Any]] = []
        for raw_it in stage1["sector_buckets"][sid]:
            ov = overrides.get(raw_it["id"]) or {}
            clean_it = {
                **raw_it,
                "one_line_takeaway": ov.get("one_line_takeaway") or raw_it["one_line_takeaway"],
                "why_it_matters": ov.get("why_it_matters") or raw_it["why_it_matters"],
                "next_week_watch": ov.get("next_week_watch") or raw_it["next_week_watch"],
            }
            if clean_it["priority"] == "P0":
                p0_total += 1
            total_items += 1
            items_clean.append(clean_it)

        sectors_out.append(
            {
                **meta,
                "sector_takeaway": synth["sectors_summary"].get(sid, ""),
                "item_count": len(items_clean),
                "p0_count": sum(1 for x in items_clean if x["priority"] == "P0"),
                "items": items_clean,
            }
        )

    week_info = stage1["week_info"]
    now_iso = to_iso_shanghai(ref_dt or now_shanghai())
    sched = schedule_meta or {"day": 0, "hour": 18, "minute": 0, "label": "每周日 18:00 (Asia/Shanghai)"}

    doc = {
        "schema_version": "3.0",
        "week_id": week_info["week_id"],
        "week_start": week_info["week_start"],
        "week_end": week_info["week_end"],
        "date_range_label": week_info["date_range_label"],
        "generated_at": now_iso,
        "generation_mode": synth["generation_mode"],
        "model_used": synth.get("model_used"),
        "window_mode": stage1["window_mode"],
        "stats": {
            "raw_scanned": stage1["raw_scanned_count"],
            "unique_clusters": stage1["unique_cluster_count"],
            "selected_items": total_items,
            "p0_count": p0_total,
        },
        "schedule": sched,
        "week_theme": synth["week_theme"],
        "executive_thesis": synth["executive_thesis"],
        "keywords": synth["keywords"],
        "sectors": sectors_out,
        "cross_sector_threads": synth["cross_sector_threads"],
        "next_week_catalysts": synth["next_week_catalysts"],
    }

    data_dir = base_path / "data"
    digests_dir = data_dir / "weekly_digests"
    digests_dir.mkdir(parents=True, exist_ok=True)
    issue_rel = f"data/weekly_digests/{week_info['week_id']}.json"

    atomic_write_json(data_dir / "weekly_digest.json", doc)
    atomic_write_json(base_path / issue_rel, doc)

    index_path = data_dir / "weekly_digests_index.json"
    existing_idx = load_json_if_exists(index_path)
    entries = existing_idx.get("issues") if isinstance(existing_idx, dict) else []
    if not isinstance(entries, list):
        entries = []

    new_entry = {
        "week_id": week_info["week_id"],
        "label": f"{week_info['week_id']}（{week_info['date_range_label']}）",
        "date_range": week_info["date_range_label"],
        "week_start": week_info["week_start"],
        "week_end": week_info["week_end"],
        "week_theme": doc["week_theme"],
        "generated_at": now_iso,
        "total_items": total_items,
        "p0_count": p0_total,
        "path": issue_rel,
    }
    filtered_entries = [e for e in entries if isinstance(e, dict) and e.get("week_id") != week_info["week_id"]]
    updated_entries = [new_entry] + filtered_entries
    updated_entries.sort(key=lambda x: str(x.get("week_id") or ""), reverse=True)
    atomic_write_json(
        index_path,
        {
            "schema_version": "3.0",
            "updated_at": now_iso,
            "latest_week_id": week_info["week_id"],
            "issues": updated_entries[:16],
        },
    )
    return doc


def fetch_remote_weekly_schedule(settings_url: str) -> Dict[str, Any]:
    req = Request(settings_url, headers={"User-Agent": "MirrorBrief-WeeklyCron/3.0"})
    with urlopen(req, timeout=12) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    day = int(raw.get("weekly_digest_day", 0))
    hour = int(raw.get("weekly_digest_hour", 18))
    minute = int(raw.get("weekly_digest_minute", 0))
    enabled = bool(raw.get("weekly_digest_enabled", True))
    day = max(0, min(6, day))
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return {
        "enabled": enabled,
        "day": day,
        "hour": hour,
        "minute": minute,
        "label": f"每{DAY_LABELS_ZH[day]} {hour:02d}:{minute:02d} (Asia/Shanghai)",
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build 2-stage Weekly Major Events Digest for MirrorBrief")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--no-ai", action="store_true", help="Skip Gemini synthesis and use deterministic refinement")
    parser.add_argument("--check-schedule-url", default="", help="Check D1 admin schedule via /api/public/settings before running")
    parser.add_argument("--force", action="store_true", help="Ignore schedule gate and force build")
    args = parser.parse_args(argv)

    base_path = Path(args.base_dir)
    now_dt = now_shanghai()
    sched = {"enabled": True, "day": 0, "hour": 18, "minute": 0, "label": "每周日 18:00 (Asia/Shanghai)"}

    if args.check_schedule_url:
        try:
            sched = fetch_remote_weekly_schedule(args.check_schedule_url)
        except Exception as exc:
            print(f"[weekly_digest] Warning: could not fetch remote schedule ({exc}), using default Sun 18:00.")

    if not args.force and args.check_schedule_url:
        if not sched["enabled"]:
            print("SCHEDULE_SKIP: weekly_digest_enabled=false in site_settings.")
            return 0
        # Python weekday(): Mon=0..Sun=6 -> convert to JS/Cron Sunday=0, Mon=1..Sat=6
        cur_js_day = (now_dt.weekday() + 1) % 7
        if cur_js_day != sched["day"] or now_dt.hour != sched["hour"]:
            print(
                f"SCHEDULE_SKIP: current Beijing {DAY_LABELS_ZH[cur_js_day]} {now_dt.hour:02d}:{now_dt.minute:02d} "
                f"!= target {sched['label']}"
            )
            return 0
        existing = load_json_if_exists(base_path / "data" / "weekly_digest.json") or {}
        if str(existing.get("generated_at") or "")[:10] == now_dt.date().isoformat():
            print(f"SCHEDULE_SKIP: already generated today ({now_dt.date().isoformat()}).")
            return 0

    doc = build_and_write_weekly_digest(
        base_path,
        ref_dt=now_dt,
        use_ai=not args.no_ai,
        schedule_meta={
            "day": sched["day"],
            "hour": sched["hour"],
            "minute": sched["minute"],
            "label": sched["label"],
        },
    )
    print(
        f"WEEKLY_DIGEST_OK: week={doc['week_id']} range={doc['date_range_label']} "
        f"mode={doc['generation_mode']} items={doc['stats']['selected_items']} p0={doc['stats']['p0_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
