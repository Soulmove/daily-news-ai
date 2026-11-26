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
    r"(?:^美股盘前|半日涨超|高开低走|低开高走|午评|收评|集体回落|集体收跌|逆市高开|CPO概念震荡反弹|打包粤菜|被撞亡|U17|国少|早间要闻|学生课间|说四川话|被认定违纪)",
    re.I,
)
_SUBJECT_ANCHORS_RE = re.compile(
    r"(?:英伟达|nvidia|黄仁勋|anthropic|openai|DeepSeek|马斯克|特朗普|美联储|央行|mlf|逆回购|黄金|白银|原油|油轮|霍尔木兹|利比亚|俄罗斯|俄军|乌克兰|航天员|神舟二十四|神舟|COP31|保证金)",
    re.I,
)
_CLICHE_PATTERNS = re.compile(
    r"(?:持续推进|坚决拥护|全面从严|开放包容|深化[\u4e00-\u9fff]{0,8}交流|坚实支撑|常态化阶段|里程碑式突破|"
    r"核心变量变化|边际变化|定价逻辑|跨境资本流向发生方向性调整|精细化管理意图|合理充裕|存量博弈|虹吸与切换|"
    r"平抑[\u4e00-\u9fff]{0,8}波动|持续跟踪[\u4e00-\u9fff]{0,12}进展|关注官方[\u4e00-\u9fff]{0,12}通报|"
    r"关注后续[\u4e00-\u9fff]{0,12}外溢|引发舆论关注|引发广泛关注|引发市场广泛关注|多起重大热点|实际效果待实测验证|"
    r"展现[\u4e00-\u9fff]{0,10}意愿|彰显[\u4e00-\u9fff]{0,10}信心|维持流动性平稳的同时|引导资金结构优化|进一步观察|密切关注后续动态)",
    re.I,
)
_VALID_OUTLOOK_DIRECTIONS = ("up", "down", "volatile", "watch")
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


def _scrub_cliches(text: Any, fallback: str = "", max_len: int = 240) -> str:
    """Remove boilerplate officialese and empty analyst filler; keep plain concrete facts."""
    txt = _clean_text(text, max_len=max_len)
    if not txt:
        return fallback
    parts = [p.strip() for p in re.split(r"(?<=[。；;！!])\s*", txt) if p.strip()]
    kept = [p for p in parts if not _CLICHE_PATTERNS.search(p)]
    if not kept:
        # Also test whole string in case it lacked punctuation
        if not _CLICHE_PATTERNS.search(txt):
            return txt
        return fallback
    joined = "".join(kept)
    useful = re.sub(r"[\s，。；;！!：:、\-—（）()]+", "", joined)
    if len(useful) < 8:
        return fallback
    return _clean_text(joined, max_len=max_len)


def _is_title_parrot(takeaway: str, title: str) -> bool:
    """Detect when takeaway merely repeats or slightly trims the headline without new insight."""
    if not takeaway or not title:
        return True
    if title_similarity(takeaway, title) >= 0.72:
        return True
    bg_t = _cjk_bigrams(takeaway)
    bg_h = _cjk_bigrams(title)
    if bg_t and bg_h:
        overlap = len(bg_t & bg_h)
        if (overlap / len(bg_t | bg_h)) >= 0.65:
            return True
        # Catch shorter takeaways that merely trim the headline without adding new substance
        if (overlap / len(bg_t)) >= 0.72:
            return True
    return False


def _make_plain_title(raw_title: str) -> str:
    """Shorten dateline-prefixed or overly bureaucratic notices into direct plain Chinese."""
    t = _clean_text(raw_title, 140)
    t = re.sub(r"^(?:财联社|华尔街见闻|格隆汇|证券时报|新浪财经)\d{1,2}月\d{1,2}日电[，,:：\s]*", "", t)
    t = re.sub(r"^(?:市场消息|外媒|报道|快讯)[：:]\s*", "", t)
    m_mlf = re.search(r"央行.*?(\d+亿元)\s*MLF", t, re.I)
    if m_mlf and "保持银行体系流动性" in t:
        return f"央行放出 {m_mlf.group(1)} 1年期流动性，大资金年末更稳了"
    return _clean_text(t, 64)


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

    preds_doc = load_json_if_exists(base_path / "data" / "predictions_public.json") or {}
    raw_preds = preds_doc.get("predictions") if isinstance(preds_doc, dict) else []
    if not isinstance(raw_preds, list):
        raw_preds = []
    open_predictions: List[Dict[str, Any]] = []
    for pr in raw_preds:
        if not isinstance(pr, dict):
            continue
        if str(pr.get("status") or "").lower() != "open":
            continue
        pid = str(pr.get("prediction_id") or "").strip()
        ptitle = _clean_text(pr.get("title") or pr.get("question") or "", 90)
        if not pid or not ptitle:
            continue
        open_predictions.append(
            {
                "prediction_id": pid,
                "title": ptitle,
                "due_at": str(pr.get("due_at") or "")[:16],
                "probability_pct": pr.get("probability_pct"),
                "win_rule": _clean_text(pr.get("win_rule") or "", 110),
                "current_judgment": _clean_text(pr.get("current_judgment") or "", 120),
                "invalidation_trigger": _clean_text(pr.get("invalidation_trigger") or "", 100),
                "category": str(pr.get("category") or "macro"),
            }
        )

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
        plain_title = _make_plain_title(item["title"])
        clean_fact = _scrub_cliches(item["fact_summary"], fallback=item["title"], max_len=300)
        fallback_why = f"件事主要卡在：{clean_fact[:110]}" if len(clean_fact) > 12 else "重点看后续有没有实打实的数字或落地方案出台。"
        clean_why = _scrub_cliches(item["ai_analysis"], fallback=clean_fact[:160] or fallback_why, max_len=220)
        clean_watch = _scrub_cliches(item["speculation_or_outlook"], fallback="下周盯官方正式口径和市场资金有没有真正跟进。", max_len=140)
        one_line = clean_fact if not _is_title_parrot(clean_fact, item["title"]) else clean_why
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
                "plain_title": plain_title,
                "title_en": item["title_en"],
                "fact_summary": clean_fact,
                "one_line_takeaway": _clean_text(one_line or item["title"], 96),
                "why_it_matters": clean_why,
                "next_week_watch": clean_watch,
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

    # Next-week upcoming catalysts from calendar.json (use scheduled_at, scheduled_date, or date; skip past events)
    today_str = today_date.isoformat()
    upcoming_cal: List[Dict[str, Any]] = []
    for ce in raw_cal_events:
        if not isinstance(ce, dict) or ce.get("is_past"):
            continue
        raw_dt = str(ce.get("scheduled_at") or ce.get("scheduled_date") or ce.get("date") or "").strip()
        date_str = raw_dt[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", raw_dt) else ""
        if date_str and date_str >= today_str:
            upcoming_cal.append({**ce, "_resolved_date": date_str})
    # Also include upcoming non-past items with original_time_note when scheduled_at is missing
    if len(upcoming_cal) < 4:
        seen_cal_t = {str(c.get("title") or "") for c in upcoming_cal}
        for ce in raw_cal_events:
            if not isinstance(ce, dict) or ce.get("is_past"):
                continue
            ct = str(ce.get("title") or "")
            if ct and ct not in seen_cal_t:
                upcoming_cal.append({**ce, "_resolved_date": str(ce.get("original_time_note") or "近期窗口")[:16]})
                seen_cal_t.add(ct)
    upcoming_cal.sort(key=lambda x: str(x.get("_resolved_date") or "9999"))

    return {
        "week_info": week_info,
        "window_mode": window_mode,
        "raw_scanned_count": raw_event_count,
        "unique_cluster_count": len(deduped_global),
        "sector_buckets": sector_buckets,
        "items": all_selected,
        "upcoming_calendar": upcoming_cal[:8],
        "open_predictions": open_predictions[:10],
    }


def _match_prediction_id(topic_text: str, sector_id: str, open_preds: Sequence[Dict[str, Any]]) -> Optional[str]:
    if not open_preds:
        return None
    blob = (topic_text or "").lower()
    key_terms = ("美联储", "加息", "降息", "两融", "保证金", "黄仁勋", "英伟达", "qwen", "阿里", "anthropic", "神舟", "油", "黄金")
    for pr in open_preds:
        pt = str(pr.get("title") or "").lower()
        for k in key_terms:
            if k in blob and k in pt:
                return str(pr["prediction_id"])
    sec_cat_map = {
        "macro_finance": ("macro", "market", "finance"),
        "geopolitics": ("global", "geopolitics", "global_space"),
        "tech_ai": ("tech_ai", "tech"),
        "industry_society": ("industry", "general", "global_space"),
    }
    cats = sec_cat_map.get(sector_id, ())
    for pr in open_preds:
        if str(pr.get("category") or "").lower() in cats:
            return str(pr["prediction_id"])
    return None


def _build_deterministic_synthesis(stage1: Dict[str, Any]) -> Dict[str, Any]:
    buckets: Dict[str, List[Dict[str, Any]]] = stage1["sector_buckets"]
    open_preds: List[Dict[str, Any]] = stage1.get("open_predictions") or []
    p0_items = [it for it in stage1["items"] if it["priority"] == "P0"]
    top_titles = [it.get("plain_title") or it["title"] for it in sorted(p0_items, key=lambda x: -x["weekly_score"])[:3]]

    week_theme = (
        f"本周最影响钱袋子和局势的事：{'、'.join(t[:18] for t in top_titles[:2])}"
        if top_titles
        else "本周全球市场与科技产业关键变化大白话盘点"
    )
    thesis: List[str] = []
    plain_prefixes = {
        "macro_finance": "钱袋子主线",
        "geopolitics": "外部局势",
        "tech_ai": "AI 和科技圈",
        "industry_society": "行业大事件",
    }
    for sid in ("macro_finance", "geopolitics", "tech_ai"):
        b = buckets.get(sid) or []
        if b:
            headline = b[0].get("plain_title") or b[0]["title"]
            detail = _scrub_cliches(b[0]["fact_summary"], fallback=b[0]["one_line_takeaway"], max_len=70)
            thesis.append(f"【{plain_prefixes[sid]}】{headline[:26]}——{detail[:52]}")
    if not thesis:
        thesis = ["本周四大板块重要消息已完成去重整理，可先大概看主线，再挑重点深挖。"]

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
            head_p = b[0].get("plain_title") or b[0]["title"]
            if len(b) > 1:
                second_p = b[1].get("plain_title") or b[1]["title"]
                sectors_summary[sid] = f"本周 {len(b)} 件大事里，最牵动全局的是「{head_p[:20]}」和「{second_p[:18]}」。"
            else:
                sectors_summary[sid] = f"这周重点盯住一件事：{head_p[:30]}。"
        else:
            sectors_summary[sid] = "这周该板块没有太大动静，属于正常过渡期。"

    cross_threads: List[Dict[str, str]] = []
    if buckets["geopolitics"] and buckets["macro_finance"]:
        geo_h = buckets["geopolitics"][0].get("plain_title") or buckets["geopolitics"][0]["title"]
        fin_h = buckets["macro_finance"][0].get("plain_title") or buckets["macro_finance"][0]["title"]
        cross_threads.append(
            {
                "title": "外面一打架或闹僵，原油黄金和汇率最先抖三抖",
                "from_sector": "geopolitics",
                "to_sector": "macro_finance",
                "logic": f"一边是「{geo_h[:20]}」，另一边钱袋子盯着「{fin_h[:20]}」，避险资金容易来回倒腾。",
            }
        )
    if buckets["tech_ai"] and (buckets["industry_society"] or buckets["macro_finance"]):
        ai_h = buckets["tech_ai"][0].get("plain_title") or buckets["tech_ai"][0]["title"]
        cross_threads.append(
            {
                "title": "AI 大厂一边拼技术发布，一边马上要面对能不能赚回钱的考题",
                "from_sector": "tech_ai",
                "to_sector": "macro_finance",
                "logic": f"像「{ai_h[:22]}」这种大动作出来后，下周资金会更较真地看估值划不划算。",
            }
        )

    next_catalysts: List[Dict[str, str]] = []
    for ce in stage1["upcoming_calendar"][:4]:
        ce_title = _clean_text(ce.get("title") or ce.get("event_name") or "", 60)
        if not ce_title:
            continue
        ce_date = str(ce.get("_resolved_date") or ce.get("scheduled_date") or ce.get("date") or "下周待定")[:16]
        watch_raw = ce.get("watch_variable") or ce.get("pre_expectation") or ce.get("description") or "看实际公布结果跟大家事先猜的是高还是低"
        next_catalysts.append(
            {
                "date": ce_date,
                "title": ce_title,
                "sector_id": classify_weekly_sector({"title": ce_title, "category": ce.get("category") or "finance"}),
                "why_watch": _scrub_cliches(watch_raw, fallback="到点核对官方正式结果，看跟市场事前预期差多少", max_len=95),
                "action_hint": "可点进前瞻验证直接押一个判断",
            }
        )

    next_week_outlook: List[Dict[str, Any]] = []
    used_preds: set[str] = set()
    for meta in SECTOR_META:
        sid = meta["sector_id"]
        b = buckets.get(sid) or []
        if not b and sid not in ("macro_finance", "tech_ai"):
            continue
        lead = b[0] if b else None
        lead_title = (lead.get("plain_title") or lead["title"]) if lead else meta["title"]
        matched_pid = _match_prediction_id(lead_title, sid, [p for p in open_preds if p["prediction_id"] not in used_preds])
        if matched_pid:
            used_preds.add(matched_pid)
        matched_pr = next((p for p in open_preds if p["prediction_id"] == matched_pid), None)

        if sid == "macro_finance":
            outlook_row = {
                "id": "outlook_macro_finance",
                "sector_id": sid,
                "topic": "A股/美股流动性与利率预期走向",
                "direction": "volatile",
                "direction_label": "大概率先涨后分化",
                "confidence_pct": 66,
                "plain_forecast": f"下周市场最先试探真钱进不进场：一边看「{lead_title[:22]}」，另一边等美国关键通胀/议息消息落听，资金不敢一口气梭哈。",
                "if_up_trigger": "如果两融成交明显放大且美元回落，前期跌多的成长与蓝筹能走一波顺风行情。",
                "if_down_trigger": "如果出现放量高开低走或通胀数据高于预期，就容易重演当天冲高回落、资金缩回防守。",
                "watch_time": (matched_pr or {}).get("due_at")[:10] if matched_pr else "下周一开盘至周中",
                "linked_prediction_id": matched_pid,
            }
        elif sid == "geopolitics":
            outlook_row = {
                "id": "outlook_geopolitics",
                "sector_id": sid,
                "topic": "地缘冲突外溢与能源航运风险",
                "direction": "volatile",
                "direction_label": "容易突然跳一下、来回拉扯",
                "confidence_pct": 64,
                "plain_forecast": f"本周「{lead_title[:24]}」说明摩擦还在往外扩，下周各方嘴上喊话和局部动作都会多，但短期一次彻底谈拢的难度依然大。",
                "if_up_trigger": "一旦主要产油国或海峡护航传出缓和协议，油价和运价溢价会很快回吐。",
                "if_down_trigger": "如果周末或下周初再传出商船遇袭或报复升级，原油、航运和黄金又会瞬间跳涨避险。",
                "watch_time": "下周全周突发窗口",
                "linked_prediction_id": matched_pid,
            }
        elif sid == "tech_ai":
            outlook_row = {
                "id": "outlook_tech_ai",
                "sector_id": sid,
                "topic": "AI 龙头股价与新模型/高估值考验",
                "direction": "watch",
                "direction_label": "看业绩和真本事，分化会很狠",
                "confidence_pct": 68,
                "plain_forecast": f"从「{lead_title[:24]}」能看出来，现在光讲概念已经不够用了：有真芯片出货或实测好用的公司能撑住，纯讲高估值的随时面临回调。",
                "if_up_trigger": "如果有大厂明确开源或上调明年算力订单，硬件和核心软件龙头还能带队往上走。",
                "if_down_trigger": "如果新股继续破发或大模型实测口碑翻车，高位 AI 股要防资金趁利好兑现砸盘。",
                "watch_time": (matched_pr or {}).get("due_at")[:10] if matched_pr else "下周三至周末",
                "linked_prediction_id": matched_pid,
            }
        else:
            outlook_row = {
                "id": "outlook_industry_society",
                "sector_id": sid,
                "topic": "大宗产油合作与产业并购落地",
                "direction": "watch",
                "direction_label": "看各自算盘和监管点不点头",
                "confidence_pct": 58,
                "plain_forecast": f"围绕「{lead_title[:24]}」，产业链里各家都在抢筹码或重新谈价钱，下周重点看原本卡住的并购融资、配额争端能不能给出准话。",
                "if_up_trigger": "如果有头部企业顺利落地并购方案或重大工程进展传出，对应赛道情绪会明显转暖。",
                "if_down_trigger": "如果监管卡审或产油/产业链内讧闹大，相关板块得做好横盘震荡的准备。",
                "watch_time": "下周中后期",
                "linked_prediction_id": matched_pid,
            }
        next_week_outlook.append(outlook_row)

    return {
        "generation_mode": "deterministic_weekly_v1",
        "model_used": None,
        "week_theme": week_theme,
        "executive_thesis": thesis[:3],
        "keywords": keywords[:6],
        "sectors_summary": sectors_summary,
        "cross_sector_threads": cross_threads,
        "next_week_catalysts": next_catalysts,
        "next_week_outlook": next_week_outlook,
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
            "date": str(c.get("_resolved_date") or c.get("scheduled_date") or c.get("date") or "")[:16],
            "title": str(c.get("title") or "")[:60],
            "watch_variable": _clean_text(c.get("watch_variable") or "", 70),
            "pre_expectation": _clean_text(c.get("pre_expectation") or "", 70),
        }
        for c in stage1["upcoming_calendar"][:5]
    ]
    open_preds = stage1.get("open_predictions") or []
    compact_preds = [
        {
            "prediction_id": p["prediction_id"],
            "title": p["title"],
            "due_at": p["due_at"],
            "probability_pct": p.get("probability_pct"),
            "win_rule": p.get("win_rule", ""),
        }
        for p in open_preds[:8]
    ]

    prompt = (
        "你是镜信 MirrorBrief 周刊首席主编。请你像一个思维犀利、长期跟踪全球政经科技的老朋友那样，"
        "用【大白话、讲人话、直接给判断】把本周这批已经去重、分好 4 个板块的重大新闻讲透，再给出可检验的下周走向预测。\n\n"
        f"本周候选事件（4 个板块已固定，不得增删 ID）：\n{json.dumps(compact_candidates, ensure_ascii=False)}\n\n"
        f"下周重点时间表：{json.dumps(compact_cal, ensure_ascii=False)}\n\n"
        f"站内正在进行的预测题目（可用于关联 linked_prediction_id）：\n{json.dumps(compact_preds, ensure_ascii=False)}\n\n"
        "【严格写作铁律（违反会被程序直接拦截删改）】:\n"
        "1. 绝对禁止一切公文套话与券商空话，包括但不限于：持续推进、坚决拥护、全面从严、开放包容、深化交流、坚实支撑、常态化阶段、里程碑式突破、核心变量变化、边际变化、定价逻辑、方向性调整、精细化管理、合理充裕、存量博弈、虹吸效应、平抑波动、持续跟踪进展、关注官方通报、关注后续外溢、引发广泛关注、实际效果待实测验证、展现意愿。\n"
        "2. one_line_takeaway 禁止直接复读或截断原标题（例如标题写“央行8000亿MLF”，精华不能再写“央行开展8000亿MLF”），必须直接点破“到底干了啥、谁受影响”。\n"
        "3. why_it_matters 用大白话讲清楚：这件事和普通投资者/行业里的人有什么实际关系、谁得利谁难受、下一步会卡在哪。\n"
        "4. next_week_watch 必须写具体可验证的数字、时间或指标（如“看下周一两融成交能不能冲上1.8万亿”），严禁写“继续观察/持续关注后续动态”。\n"
        "5. 下周走向预测（next_week_outlook）必须给 4~5 条硬核、具体、敢亮方向的推演，写明如果出现什么具体信号怎么走（if_up_trigger），踩到什么红线怎么小心（if_down_trigger）。\n"
        "6. 禁止任何表情符号 emoji，只输出严格 JSON 对象：\n"
        "{\n"
        '  "week_theme": "大白话一句话点透这周最大主线（<=32字）",\n'
        '  "executive_thesis": ["3条大白话总结这周最核心的3件事，每条<=55字"],\n'
        '  "keywords": ["4到6个本周高频关键词"],\n'
        '  "sectors_summary": {\n'
        '    "macro_finance": "大白话总结本周钱和市场板块",\n'
        '    "geopolitics": "大白话总结本周国际局势板块",\n'
        '    "tech_ai": "大白话总结本周科技与AI板块",\n'
        '    "industry_society": "大白话总结本周产业和社会板块"\n'
        "  },\n"
        '  "items": [\n'
        '    {"id": "对应id", "plain_title": "帮用户把长公文/绕口新闻改写成<=26字的直白短标题", "one_line_takeaway": "大概看一句话点破干了啥(<=45字，不许复读标题)", "why_it_matters": "细看大白话：到底有啥实际影响(55-105字)", "next_week_watch": "具体可验证的下周信号(<=45字)"}\n'
        "  ],\n"
        '  "cross_sector_threads": [\n'
        '    {"title": "大白话跨板块联动标题", "from_sector": "macro_finance|geopolitics|tech_ai|industry_society", "to_sector": "macro_finance|geopolitics|tech_ai|industry_society", "logic": "一句话讲清这几件事是怎么互相咬合影响的"}\n'
        "  ],\n"
        '  "next_week_catalysts": [\n'
        '    {"date": "YYYY-MM-DD", "title": "下周重点时间点或事件", "sector_id": "macro_finance|geopolitics|tech_ai|industry_society", "why_watch": "直白点明当天盯什么数据/表态", "action_hint": "直白行动提示"}\n'
        "  ],\n"
        '  "next_week_outlook": [\n'
        '    {"id": "outlook_1", "sector_id": "macro_finance|geopolitics|tech_ai|industry_society", "topic": "要判断的方向主题（<=20字）", "direction": "up|down|volatile|watch", "direction_label": "直白结论标签如 先涨后分化/来回拉扯/偏顺风", "confidence_pct": 65, "plain_forecast": "大白话推演下周大概率怎么走、为什么（55-100字）", "if_up_trigger": "顺风剧本：如果出现什么具体数字/动作就偏强", "if_down_trigger": "逆风红线：如果踩到什么具体坑就要小心", "watch_time": "关键验证时间窗口", "linked_prediction_id": "从站内预测题目里匹配最相关的一条prediction_id，没有则写null"}\n'
        "  ]\n"
        "}"
    )

    res = call_gemini_json(
        scope="weekly_digest",
        prompt=prompt,
        tier="tier1",
        temperature=0.25,
        timeout_ms=42_000,
        base_dir=base_path,
    )
    if not res.ok or not isinstance(res.data, dict):
        return fallback

    data = res.data
    items_by_id = {it["id"]: it for it in items}
    overrides: Dict[str, Dict[str, str]] = {}
    for row in data.get("items") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        rid = str(row["id"])
        orig_it = items_by_id.get(rid) or {}
        orig_title = str(orig_it.get("title") or "")
        pt = _clean_text(row.get("plain_title") or "", 64)
        ot_raw = _scrub_cliches(row.get("one_line_takeaway") or "", fallback="", max_len=110)
        if ot_raw and orig_title and _is_title_parrot(ot_raw, orig_title):
            ot_raw = ""
        why_raw = _scrub_cliches(row.get("why_it_matters") or "", fallback="", max_len=240)
        watch_raw = _scrub_cliches(row.get("next_week_watch") or "", fallback="", max_len=120)
        overrides[rid] = {
            "plain_title": pt,
            "one_line_takeaway": ot_raw,
            "why_it_matters": why_raw,
            "next_week_watch": watch_raw,
        }

    sectors_summary = dict(fallback["sectors_summary"])
    if isinstance(data.get("sectors_summary"), dict):
        for sid in SECTOR_IDS:
            val = _scrub_cliches(data["sectors_summary"].get(sid) or "", fallback="", max_len=110)
            if val:
                sectors_summary[sid] = val

    thesis = [
        cleaned
        for x in (data.get("executive_thesis") or [])
        if isinstance(x, str)
        for cleaned in [_scrub_cliches(x, fallback="", max_len=120)]
        if len(cleaned) >= 8
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
            logic_clean = _scrub_cliches(th["logic"], fallback="", max_len=140)
            if not logic_clean:
                continue
            threads.append(
                {
                    "title": _clean_text(th["title"], 60),
                    "from_sector": fs if fs in SECTOR_IDS else "geopolitics",
                    "to_sector": ts if ts in SECTOR_IDS else "macro_finance",
                    "logic": logic_clean,
                }
            )

    catalysts: List[Dict[str, str]] = []
    for cat in (data.get("next_week_catalysts") or [])[:4]:
        if isinstance(cat, dict) and cat.get("title"):
            sid = str(cat.get("sector_id") or "macro_finance")
            why_w = _scrub_cliches(cat.get("why_watch") or "", fallback="到点盯紧公布数值或官方原话跟预期差多少", max_len=110)
            catalysts.append(
                {
                    "date": _clean_text(cat.get("date") or "下周", 24),
                    "title": _clean_text(cat["title"], 70),
                    "sector_id": sid if sid in SECTOR_IDS else "macro_finance",
                    "why_watch": why_w,
                    "action_hint": _clean_text(cat.get("action_hint") or "去前瞻验证押一个判断", 60),
                }
            )

    valid_pred_ids = {p["prediction_id"] for p in open_preds}
    outlooks: List[Dict[str, Any]] = []
    for idx_o, out_item in enumerate((data.get("next_week_outlook") or [])[:5]):
        if not isinstance(out_item, dict) or not out_item.get("topic") or not out_item.get("plain_forecast"):
            continue
        sid = str(out_item.get("sector_id") or "macro_finance")
        if sid not in SECTOR_IDS:
            sid = "macro_finance"
        direction = str(out_item.get("direction") or "watch").lower()
        if direction not in _VALID_OUTLOOK_DIRECTIONS:
            direction = "watch"
        try:
            conf = max(35, min(88, int(out_item.get("confidence_pct") or 60)))
        except (TypeError, ValueError):
            conf = 60
        forecast_clean = _scrub_cliches(out_item.get("plain_forecast"), fallback="", max_len=180)
        up_clean = _scrub_cliches(out_item.get("if_up_trigger"), fallback="放量突破或数据明显超预期时再顺势跟进", max_len=120)
        down_clean = _scrub_cliches(out_item.get("if_down_trigger"), fallback="若低于底线预期或再度冲击则先降仓防守", max_len=120)
        if not forecast_clean:
            continue
        raw_pid = out_item.get("linked_prediction_id")
        pid = str(raw_pid).strip() if isinstance(raw_pid, str) and raw_pid.strip() in valid_pred_ids else _match_prediction_id(str(out_item.get("topic") or ""), sid, open_preds)
        outlooks.append(
            {
                "id": _clean_text(out_item.get("id") or f"outlook_{idx_o + 1}", 36),
                "sector_id": sid,
                "topic": _clean_text(out_item["topic"], 44),
                "direction": direction,
                "direction_label": _clean_text(out_item.get("direction_label") or "盯关键信号再动手", 22),
                "confidence_pct": conf,
                "plain_forecast": forecast_clean,
                "if_up_trigger": up_clean,
                "if_down_trigger": down_clean,
                "watch_time": _clean_text(out_item.get("watch_time") or "下周重要窗口", 32),
                "linked_prediction_id": pid,
            }
        )

    theme_clean = _scrub_cliches(data.get("week_theme") or "", fallback="", max_len=70)
    return {
        "generation_mode": "ai_weekly_assisted_v1",
        "model_used": res.model_used,
        "week_theme": theme_clean or fallback["week_theme"],
        "executive_thesis": thesis or fallback["executive_thesis"],
        "keywords": keywords or fallback["keywords"],
        "sectors_summary": sectors_summary,
        "cross_sector_threads": threads or fallback["cross_sector_threads"],
        "next_week_catalysts": catalysts or fallback["next_week_catalysts"],
        "next_week_outlook": outlooks or fallback["next_week_outlook"],
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
                "plain_title": ov.get("plain_title") or raw_it.get("plain_title") or raw_it["title"],
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
        "next_week_outlook": synth.get("next_week_outlook") or [],
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
