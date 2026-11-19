"""HKEXnews & CNInfo announcement metadata connectors with honest operational limits."""

from __future__ import annotations

from datetime import timedelta
import json
import re
import time
from typing import Any, Dict, List

import requests

from pipeline.connectors.base import HttpCacheStore, _GLOBAL_LIMITER, polite_get
from pipeline.id_utils import make_raw_item_id
from pipeline.time_utils import now_shanghai, parse_iso_datetime, parse_published_at, to_iso_shanghai

DEFAULT_HKEX_WATCH = [
    {"stock_code": "00700", "name": "腾讯控股", "entity_id": "ent_tencent"},
    {"stock_code": "09988", "name": "阿里巴巴-W", "entity_id": "ent_qwen_alibaba"},
    {"stock_code": "00981", "name": "中芯国际", "entity_id": "ent_smic"},
    {"stock_code": "03690", "name": "美团-W", "entity_id": "ent_meituan"},
]

DEFAULT_CNINFO_WATCH = [
    {"code": "688256", "column": "sse", "name": "寒武纪", "entity_id": "ent_cambricon"},
    {"code": "688981", "column": "sse", "name": "中芯国际", "entity_id": "ent_smic"},
]

_HKEX_BOILERPLATE_RE = re.compile(r"(展示文件|翌日披露報表|月報表|一般授權認購新股份|更換核數師|通知信函|董事會召開日期)")


def fetch_hkex_announcements(
    cache: HttpCacheStore,
    *,
    previous_items: List[dict] | None = None,
) -> Dict[str, Any]:
    """
    Query HKEXnews official titleSearchServlet.do for recent HKEX company announcements.
    Retains metadata + official PDF/HTML link without mass PDF downloading.
    """
    now_dt = now_shanghai()
    fetched_iso = to_iso_shanghai(now_dt)
    from_date = (now_dt - timedelta(days=21)).strftime("%Y%m%d")
    to_date = now_dt.strftime("%Y%m%d")
    t0 = time.monotonic()

    items: List[dict] = []
    errors: List[str] = []
    entity_updates: Dict[str, dict] = {}

    url = (
        "https://www1.hkexnews.hk/search/titleSearchServlet.do"
        f"?sortDir=0&sortByOptions=DateTime&category=0&market=SEHK&stockId=-1"
        f"&documentType=-1&fromDate={from_date}&toDate={to_date}&title=&searchType=0"
        "&t1code=-2&t2Gcode=-2&t2code=-2&rowRange=20&lang=zh"
    )
    res = polite_get(url, cache=cache, timeout=(5, 10), expect_json=True)
    if not res.ok or not isinstance(res.json_data, dict):
        if res.status == "not_modified_304":
            kept = [
                pit for pit in (previous_items or [])
                if pit.get("source_id") == "hkexnews"
            ]
            return {
                "connector_id": "hkexnews",
                "connector_name": "港交所披露易 (HKEXnews) 上市公司公告索引",
                "source_tier": "first_party",
                "status": "cached_304",
                "fetched_at": fetched_iso,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "item_count": len(kept),
                "error_message": None,
                "tos_note": "遵守港交所网站公开索引规则：仅保留公告元数据、摘要标签与披露易官方原文入口，不批量镜像PDF。",
                "items": kept,
                "entity_updates": {},
            }
        return {
            "connector_id": "hkexnews",
            "connector_name": "港交所披露易 (HKEXnews) 上市公司公告索引",
            "source_tier": "first_party",
            "status": res.status if res.status != "ok" else "error",
            "fetched_at": fetched_iso,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "item_count": 0,
            "error_message": res.error_message,
            "tos_note": "港交所公开公告查询，仅保留元数据与原文链接。",
            "items": [],
            "entity_updates": {},
        }

    try:
        rows = json.loads(res.json_data.get("result") or "[]")
    except ValueError:
        rows = []

    watch_by_code = {w["stock_code"]: w for w in DEFAULT_HKEX_WATCH}
    # Index both watched entities AND top important general HKEX corporate filings
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("STOCK_CODE") or "").split("<br/>")[0].strip().zfill(5)
        sname = str(row.get("STOCK_NAME") or "").split("<br/>")[0].strip()
        raw_title = str(row.get("TITLE") or "").replace("<br/>", " ").strip()
        short_cat = str(row.get("SHORT_TEXT") or "").replace("<br/>", " ").strip()
        rel_link = str(row.get("FILE_LINK") or "").strip()
        if not rel_link or not raw_title:
            continue
        full_url = f"https://www1.hkexnews.hk{rel_link}" if rel_link.startswith("/") else rel_link
        pub_raw = str(row.get("DATE_TIME") or "").replace("/", "-")
        pub_iso, _ = parse_published_at(pub_raw, "hkexnews")

        watched = watch_by_code.get(code)
        if not watched:
            # Strict relevance gate: do not inject random unrelated HKEX ETFs/bulletins into the AI briefing feed
            continue
        if _HKEX_BOILERPLATE_RE.search(raw_title):
            continue
        if watched:
            title = f"[HKEX {code} {sname}] {raw_title}"
            excerpt = f"港交所披露易分类：{short_cat or '上市公司公告'}（文件大小 {row.get('FILE_INFO') or '未知'}）。"
            ent_ids = [watched["entity_id"]] if watched else []
            pub_dt = parse_iso_datetime(pub_iso) if pub_iso else None
            if not pub_dt or (now_dt - pub_dt) <= timedelta(days=14):
                items.append(
                    {
                        "item_id": make_raw_item_id("hkexnews", full_url, title),
                        "source_id": "hkexnews",
                        "source_name": "港交所披露易",
                        "source_kind": "official_filing",
                        "source_tier": "first_party",
                        "publisher_family": "hkexnews",
                        "citable_as_news": True,
                        "category": "finance",
                        "title": title,
                        "url": full_url,
                        "canonical_url": full_url,
                        "published_at": pub_iso,
                        "published_at_source": "hkex_datetime",
                        "fetched_at": fetched_iso,
                        "excerpt": excerpt,
                        "entity_ids": ent_ids,
                    }
                )
            if watched:
                upd = entity_updates.setdefault(watched["entity_id"], {"hkex_filings": []})
                upd["hkex_filings"].append(
                    {"title": raw_title, "date": pub_iso, "category": short_cat, "url": full_url}
                )

    return {
        "connector_id": "hkexnews",
        "connector_name": "港交所披露易 (HKEXnews) 上市公司公告索引",
        "source_tier": "first_party",
        "status": "ok" if items else "empty",
        "fetched_at": fetched_iso,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "item_count": len(items),
        "error_message": None,
        "tos_note": "仅索引公开公告元数据与披露易官方 PDF 直链（不镜像文件，不突破访问频率限制）。",
        "items": items,
        "entity_updates": entity_updates,
    }


def fetch_cninfo_announcements() -> Dict[str, Any]:
    """
    Query CNInfo official hisAnnouncement/query endpoint for watched A-share semiconductor stocks.
    Records metadata & official static link cleanly without bulk PDF download.
    """
    now_dt = now_shanghai()
    fetched_iso = to_iso_shanghai(now_dt)
    t0 = time.monotonic()
    items: List[dict] = []
    errors: List[str] = []
    entity_updates: Dict[str, dict] = {}

    endpoint = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.cninfo.com.cn/new/disclosure",
    }

    for target in DEFAULT_CNINFO_WATCH:
        _GLOBAL_LIMITER.wait(endpoint)
        try:
            resp = requests.post(
                endpoint,
                data={
                    "pageNum": "1",
                    "pageSize": "5",
                    "column": target["column"],
                    "tabName": "fulltext",
                    "plate": "",
                    "searchkey": target["name"],
                    "secid": "",
                    "category": "",
                    "trade": "",
                    "seDate": "",
                    "sortName": "",
                    "sortType": "",
                    "isHLtitle": "false",
                },
                headers=headers,
                timeout=(4, 8),
            )
            if resp.status_code != 200:
                errors.append(f"{target['code']}: HTTP {resp.status_code}")
                continue
            data = resp.json()
            anns = data.get("announcements") or []
            added_news_for_target = False
            for ann in anns[:3]:
                if not isinstance(ann, dict):
                    continue
                sec_code = str(ann.get("secCode") or target["code"])
                if sec_code != target["code"]:
                    continue
                raw_title = str(ann.get("announcementTitle") or "").strip()
                adj_url = str(ann.get("adjunctUrl") or "").strip()
                if not raw_title or not adj_url:
                    continue
                full_url = f"https://static.cninfo.com.cn/{adj_url.lstrip('/')}"
                pub_iso, _ = parse_published_at(ann.get("announcementTime"), "cninfo")
                pub_dt = parse_iso_datetime(pub_iso) if pub_iso else None
                title = f"[巨潮 {sec_code} {target['name']}] {raw_title}"
                upd = entity_updates.setdefault(target["entity_id"], {"hkex_filings": []})
                upd["hkex_filings"].append(
                    {"title": raw_title, "date": pub_iso, "category": "巨潮公告", "url": full_url}
                )
                # Keep at most 1 non-boilerplate recent announcement per company in the daily briefing feed
                is_cninfo_boilerplate = bool(_HKEX_BOILERPLATE_RE.search(raw_title)) or "核数师" in raw_title or "独立董事" in raw_title
                if (
                    not added_news_for_target
                    and not is_cninfo_boilerplate
                    and (not pub_dt or (now_dt - pub_dt) <= timedelta(days=7))
                ):
                    added_news_for_target = True
                    items.append(
                        {
                            "item_id": make_raw_item_id("cninfo", full_url, title),
                            "source_id": "cninfo",
                            "source_name": "巨潮资讯官方公告",
                            "source_kind": "official_filing",
                            "source_tier": "first_party",
                            "publisher_family": "cninfo",
                            "citable_as_news": True,
                            "category": "finance",
                            "title": title,
                            "url": full_url,
                            "canonical_url": full_url,
                            "published_at": pub_iso,
                            "published_at_source": "cninfo_epoch",
                            "fetched_at": fetched_iso,
                            "excerpt": f"巨潮资讯法定披露：{target['name']} ({sec_code}.SH) 公告元数据索引，正文见官方 PDF 入口。",
                            "entity_ids": [target["entity_id"]],
                        }
                    )
        except Exception as exc:
            errors.append(f"{target['code']}: {type(exc).__name__}")

    status = "ok" if items else ("empty" if not errors else "error")
    return {
        "connector_id": "cninfo",
        "connector_name": "巨潮资讯 A 股公告元数据索引",
        "source_tier": "first_party",
        "status": status,
        "fetched_at": fetched_iso,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "item_count": len(items),
        "error_message": "; ".join(errors[:2]) if errors else None,
        "tos_note": "仅抓取法定公告标题、时间与官方 static.cninfo.com.cn PDF 链接，不转存收费或批量下载全文 PDF。",
        "items": items,
        "entity_updates": entity_updates,
    }
