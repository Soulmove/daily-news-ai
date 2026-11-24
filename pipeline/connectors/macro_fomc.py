"""Federal Reserve official FOMC Calendar & Monetary Policy Press Releases connector."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
import time
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from pipeline.connectors.base import HttpCacheStore, polite_get
from pipeline.id_utils import make_raw_item_id
from pipeline.time_utils import SHANGHAI_TZ, now_shanghai, parse_iso_datetime, parse_published_at, to_iso_shanghai

FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FOMC_RSS_URL = "https://www.federalreserve.gov/feeds/press_monetary.xml"
MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _build_fomc_row(
    year: int,
    m1_num: int,
    d1: int,
    m2_num: int,
    d2: int,
    ref_dt: datetime,
) -> Optional[Dict[str, Any]]:
    ny_tz = ZoneInfo("America/New_York")
    try:
        dt_ny = datetime(year, m2_num, d2, 14, 0, tzinfo=ny_tz)
        dt_cst = dt_ny.astimezone(SHANGHAI_TZ)
    except ValueError:
        return None
    date_key = f"{year}-{m2_num:02d}-{d2:02d}"
    span_label = (
        f"{year}-{m1_num:02d}-{d1:02d}~{m2_num:02d}-{d2:02d}"
        if m1_num != m2_num
        else f"{year}-{m2_num:02d}-{d1:02d}~{d2:02d}"
    )
    is_past = dt_cst < (ref_dt - timedelta(days=2))
    has_sep = m2_num in {3, 6, 9, 12}
    watch_var = (
        "联邦基金目标利率区间、季度经济预测摘要 (SEP 点阵图) 与主席新闻发布会"
        if has_sep
        else ("美联储货币政策框架/战略讨论专题会议（按官网暂定日程，重点关注声明文本）" if (year >= 2027 and m2_num == 10) else "联邦基金目标利率目标区间、FOMC 决议声明措辞与鲍威尔新闻发布会")
    )
    pre_exp = (
        f"按美联储官网最新修订排期（{'2027暂定日程已不含12月传统会期，改列11月中旬；' if year >= 2027 else ''}不含付费利率期货一致预期数值）"
    )
    return {
        "calendar_id": f"cal_fomc_{date_key}",
        "title": f"美联储 FOMC {'季度点阵图与' if has_sep else ''}议息会议（北京时间 {dt_cst.month} 月 {dt_cst.day} 日 {dt_cst:%H:%M} · 美东 {span_label}）",
        "scheduled_at": to_iso_shanghai(dt_cst),
        "original_time_note": f"{date_key} 14:00 America/New_York（已折算 Asia/Shanghai）",
        "timezone": "Asia/Shanghai",
        "certainty": "confirmed_official",
        "certainty_label": "已召开 / 历史会议" if is_past else "官方已排期确认",
        "is_past": is_past,
        "category": "global",
        "event_type": "central_bank",
        "event_type_label": "央行与宏观",
        "region": "us",
        "region_label": "美国",
        "country": "美国",
        "city": "华盛顿",
        "location_display": "美国·华盛顿",
        "entity_ids": ["ent_macro_fomc"],
        "storyline_id": None,
        "watch_variable": watch_var,
        "pre_expectation": pre_exp,
        "actual_result": None,
        "source_name": "Federal Reserve 官方 FOMC 日历",
        "source_url": FOMC_CALENDAR_URL,
    }


def _parse_fomc_upcoming_dates(html_text: str, *, reference_dt: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Extract scheduled FOMC meetings strictly from official `.panel` + `.row.fomc-meeting` DOM rows
    (ignoring minutes release dates, Last Update footers, notation votes, and 2028 tentative prose notes).
    """
    ref_dt = reference_dt or now_shanghai()
    upcoming: List[Dict[str, Any]] = []
    past_recent: List[Dict[str, Any]] = []
    seen_dates = set()

    if "fomc-meeting" in html_text:
        panel_blocks = re.split(r'(?=<div[^>]+class="[^"]*panel\s+panel-default)', html_text)
        for pb in panel_blocks:
            head_m = re.search(r'class="[^"]*panel-heading[^"]*"[^>]*>(.*?)</div>', pb, re.S)
            if not head_m:
                continue
            head_txt = " ".join(re.sub(r"<[^>]+>", " ", head_m.group(1)).split())
            yr_m = re.search(r"\b(202[4-9])\s+FOMC\s+Meetings\b", head_txt, re.I)
            if not yr_m:
                continue
            year = int(yr_m.group(1))
            starts = [m.start() for m in re.finditer(r'<div[^>]+class="[^"]*row\s+fomc-meeting[^"]*"', pb)]
            for i, st in enumerate(starts):
                end = starts[i + 1] if i + 1 < len(starts) else len(pb)
                chunk = pb[st:end]
                mon_m = re.search(r'fomc-meeting__month[^>]*>(.*?)</div>', chunk, re.S)
                dat_m = re.search(r'fomc-meeting__date[^>]*>(.*?)</div>', chunk, re.S)
                if not mon_m or not dat_m:
                    continue
                mon_txt = " ".join(re.sub(r"<[^>]+>", " ", mon_m.group(1)).split()).lower()
                dat_txt = " ".join(re.sub(r"<[^>]+>", " ", dat_m.group(1)).split()).lower()
                if any(skip in (mon_txt + " " + dat_txt) for skip in ("notation", "cancel")):
                    continue
                # Extract 2-day date span e.g. '27-28', '17-18*', '30-1'
                span_m = re.search(r"\b(\d{1,2})\s*[-–]\s*(\d{1,2})\b", dat_txt)
                if not span_m:
                    continue
                d1, d2 = int(span_m.group(1)), int(span_m.group(2))
                mon_parts = [p.strip() for p in re.split(r"[/\-]", mon_txt) if p.strip()]
                m1_num = MONTH_NAMES.get(mon_parts[0]) if mon_parts else None
                m2_num = MONTH_NAMES.get(mon_parts[-1]) if mon_parts else None
                if not m1_num or not m2_num:
                    continue
                row = _build_fomc_row(year, m1_num, d1, m2_num, d2, ref_dt)
                if not row:
                    continue
                date_key = row["calendar_id"]
                if date_key in seen_dates:
                    continue
                seen_dates.add(date_key)
                if row["is_past"]:
                    sched_dt = parse_iso_datetime(row["scheduled_at"])
                    # Exclude stale >60d past meetings (never show 2025 in late 2026)
                    if sched_dt and (ref_dt - sched_dt) <= timedelta(days=60):
                        past_recent.append(row)
                else:
                    upcoming.append(row)
    else:
        # Fallback for simplified text snippets (e.g. unit tests without Fed HTML markup)
        clean = re.sub(r"<[^>]+>", " ", html_text)
        clean = re.sub(r"\s+", " ", clean)
        year_blocks = re.finditer(
            r"(202[5-8])\s+FOMC Meetings(.*?)(?=202[4-9]\s+FOMC Meetings|Notation Votes|$)",
            clean,
            flags=re.IGNORECASE,
        )
        for m in year_blocks:
            year = int(m.group(1))
            seg = m.group(2)
            for dm in re.finditer(
                r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s*[-–]\s*(?:(January|February|March|April|May|June|July|August|September|October|November|December)\s+)?(\d{1,2})\b",
                seg,
                flags=re.IGNORECASE,
            ):
                m1_num = MONTH_NAMES.get(dm.group(1).lower())
                m2_num = MONTH_NAMES.get((dm.group(3) or dm.group(1)).lower())
                d1, d2 = int(dm.group(2)), int(dm.group(4))
                if not m1_num or not m2_num:
                    continue
                row = _build_fomc_row(year, m1_num, d1, m2_num, d2, ref_dt)
                if not row or row["calendar_id"] in seen_dates:
                    continue
                seen_dates.add(row["calendar_id"])
                if row["is_past"]:
                    past_recent.append(row)
                else:
                    upcoming.append(row)

    upcoming.sort(key=lambda x: x["scheduled_at"])
    past_recent.sort(key=lambda x: x["scheduled_at"], reverse=True)
    # Show near-term next 4 scheduled FOMC meetings (~180d horizon) + 1 recent past meeting to avoid drowning out other catalysts
    return upcoming[:4] + past_recent[:1]


def fetch_macro_fomc(cache: HttpCacheStore) -> Dict[str, Any]:
    """Fetch official FOMC meeting schedule and monetary policy RSS items."""
    fetched_iso = to_iso_shanghai(now_shanghai())
    t0 = time.monotonic()

    items: List[dict] = []
    calendar_events: List[dict] = []
    errors: List[str] = []

    cal_res = polite_get(FOMC_CALENDAR_URL, cache=None, timeout=(5, 10))
    if cal_res.ok and cal_res.text:
        calendar_events = _parse_fomc_upcoming_dates(cal_res.text)
    elif not cal_res.ok:
        errors.append(f"FOMC日历: {cal_res.error_message}")

    rss_res = polite_get(FOMC_RSS_URL, cache=cache, timeout=(5, 10))
    if rss_res.ok and rss_res.text:
        try:
            root = ET.fromstring(rss_res.text)
            for item_el in root.findall(".//item")[:5]:
                title = " ".join((item_el.findtext("title") or "").split())
                link = (item_el.findtext("link") or "").strip()
                pub_raw = item_el.findtext("pubDate")
                desc = " ".join(re.sub(r"<[^>]+>", " ", (item_el.findtext("description") or "")).split())
                pub_iso, _ = parse_published_at(pub_raw, "fed-fomc")
                if not title or not link:
                    continue
                items.append(
                    {
                        "item_id": make_raw_item_id("fed-fomc", link, title),
                        "source_id": "fed-fomc",
                        "source_name": "美联储 (Federal Reserve) 官方发布",
                        "source_kind": "regulatory_release",
                        "source_tier": "first_party",
                        "publisher_family": "federalreserve",
                        "citable_as_news": True,
                        "category": "global",
                        "title": f"[Fed] {title}",
                        "url": link,
                        "canonical_url": link,
                        "published_at": pub_iso,
                        "published_at_source": "fed_rss",
                        "fetched_at": fetched_iso,
                        "excerpt": desc[:280],
                        "entity_ids": ["ent_macro_fomc"],
                    }
                )
        except ET.ParseError as exc:
            errors.append(f"FOMC RSS XML错误: {exc}")
    elif rss_res.status != "not_modified_304" and not rss_res.ok:
        errors.append(f"FOMC RSS: {rss_res.error_message}")

    status = "ok"
    if not items and not calendar_events and errors:
        status = "error"
    elif errors:
        status = "partial"

    return {
        "connector_id": "fed-fomc",
        "connector_name": "美联储 FOMC 官方议息日历与政策声明",
        "source_tier": "first_party",
        "status": status,
        "fetched_at": fetched_iso,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "item_count": len(items),
        "calendar_count": len(calendar_events),
        "error_message": "; ".join(errors[:2]) if errors else None,
        "tos_note": "美联储公开政府信息页面与 RSS，保留官方时间及原文跳转。",
        "items": items,
        "calendar_events": calendar_events,
    }
