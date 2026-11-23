"""Zero-Lag 7x24 China & Global Real-Time Flash Wire Collector (WallStreetCN, CLS, 36Kr, ITHome).

Works directly from BOTH GitHub Actions (overseas) AND Tencent Cloud (domestic China),
providing sub-10-minute real-time flash wire updates into `data/live_wire.json` and the main pipeline.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import html
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import requests

from pipeline.connectors.base import HttpCacheStore
from pipeline.dedup import is_consumer_promo_or_fluff, is_hotlist_aggregator_source, smart_truncate, strip_raw_urls_and_domain_tails
from pipeline.heavy_classifier import (
    GEO_MILITARY_HEAVY_RE,
    HEAVY_NOISE_EXCLUDE_RE,
    heavy_topic_key,
    infer_heavy_reason_tag,
    sync_today_heavy_into_live_wire,
)
from pipeline.id_utils import canonicalize_url, make_raw_item_id
from pipeline.manifest import atomic_write_json, load_json_if_exists
from pipeline.time_utils import SHANGHAI_TZ, now_shanghai, parse_iso_datetime, parse_published_at, to_iso_shanghai

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
}

_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_AI_KW_RE = re.compile(
    r"(?:(?<![A-Za-z])ai(?![A-Za-z])|大模型|gemini|openai|gpt-\d|chatgpt|claude|anthropic|qwen|千问|kimi|混元|workbuddy|电脑操控|计算机控制|元宝|豆包|seedance|manus|minimax|智谱|glm-?\d|cursor|windsurf|antigravity|千亿.*大模型|腾讯.*ai|deepseek|算力|英伟达|nvidia|芯片|gpu|开源模型|agent|智能体|具身智能|人形机器人)",
    re.I,
)
_GEO_PRIORITY_RE = re.compile(
    r"(?:导弹|空袭|无人机|击落|战机|航母|油轮|触雷|海峡|霍尔木兹|红海|联合巡逻|海警|海军|国防部?|南海|北部湾|中越|联演|军演|边防|领海|"
    r"停火|和平协议|俄乌|美伊|以色列|加沙|波兰|北约|外交|元首|白宫|峰会|联合国)",
    re.I,
)
_FIN_KW_RE = re.compile(
    r"(?:a股|美股|港股|美联储|央行|降息|加息|黄金|原油|汇率|人民币|美元指数|美元汇率|纳指|标普|沪指|创业板|涨停|跌停|财报|ipo|关税|国债|cpi|非农|板块|回购|比特币|以太坊|\bBTC\b|\bETH\b|加密货币)",
    re.I,
)
_CRYPTO_KW_RE = re.compile(r"(?:比特币|以太坊|\bBTC\b|\bETH\b|加密货币|虚拟货币|币安)", re.I)
_DOMESTIC_RE = re.compile(
    r"(?:a股|沪指|深成指|创业板|上期所|深交所|上交所|北交所|国务院|发改委|工信部|央行|证监会|人民币|沪深|中芯|比亚迪|宁德时代|华为|腾讯|阿里|回购股份|股份有限公司|商务部)",
    re.I,
)
_GLOBAL_KW_RE = re.compile(
    r"(?:特朗普|拜登|白宫|欧盟|联合国|apec|峰会|外交|中东|俄乌|停火|制裁|总统|首相|外交部|美商务部|美国商务部|访华|日央行|欧洲央行|联合巡逻|北部湾|中越|中俄|中美|防长|国防)",
    re.I,
)


def _clean(raw: Any, max_len: int = 240) -> str:
    if not raw:
        return ""
    s = html.unescape(_HTML_RE.sub(" ", str(raw)))
    s = strip_raw_urls_and_domain_tails(s)
    return smart_truncate(s, max_len=max_len)


_PURE_WIRE_FLUFF_RE = re.compile(
    r"(?:斗破苍穹|剧场版|动画电影|首支单曲|主题曲|今日小雪|小雪节气|大雪节气|立冬节气|冬至节气|长城坦克首支单曲)",
    re.I,
)
_NON_TECH_CONSUMER_OR_CRIME_RE = re.compile(
    r"(?:帮信罪|刑拘|逮捕|派出所|警方|涉案|诈骗案|Steam|黑五.*游戏|游戏新史低|重制版|导剪版|折扣促销|"
    r"剧场版|动画电影|动漫|斗破苍穹|演唱会|首支单曲|主题曲|音乐节|票房|"
    r"长城坦克|坦克\d{2,3}|越野车|节气|小雪|大雪|立冬|冬至|天气预报)",
    re.I,
)
_DISASTER_SOCIETY_RE = re.compile(
    r"(?:地震|地震台网|地质调查局|\bUSGS\b|余震|震中|台风|强台风|暴雨|山洪|海啸|火山喷发|泥石流|灾情|救援人员|人员伤亡)",
    re.I,
)
_DISASTER_FOREIGN_RE = re.compile(
    r"(?:\bUSGS\b|日本|印尼|印度尼西亚|菲律宾|土耳其|智利|希腊|意大利|加州|阿拉斯加|堪察加|Timor|Chile|Indonesia|Japan|Greece|Turkey|Alaska|California)",
    re.I,
)
_GAMING_ENT_RE = re.compile(
    r"(?:《?gta\s*6》?|gta\s*v|gta6|侠盗猎车手|xbox|ps5|playstation|任天堂|nintendo|switch\s*2?|steam|帧率|\d+\s*fps|主机游戏|电子游戏|rockstar|r\s*星|电竞|黑神话|原神|王者荣耀)",
    re.I,
)
_STOCK_CORP_TITLE_RE = re.compile(
    r"(?:股价|财报|市值|ipo|上市|收购|融资|涨停|跌停|美股|a股|港股)",
    re.I,
)
_MACRO_STRATEGIST_RE = re.compile(
    r"(?:(?:首席)?(?:投资|市场|宏观|财富)?策略师|经济学家|财富管理|财富经理|彭博经济研究|Bloomberg Economics|交易热潮|IPO.*交易)",
    re.I,
)


def _classify_wire_item(title: str, content: str, default_cat: str) -> str:
    cleaned_content = re.sub(r"[（(][^）)]*现汇率约合[^）)]*[）)]", "", str(content or ""))
    text = f"{title} {cleaned_content}"
    if _NON_TECH_CONSUMER_OR_CRIME_RE.search(title):
        return "general"
    if _GAMING_ENT_RE.search(title) and not _STOCK_CORP_TITLE_RE.search(title):
        return "tech"
    if _DISASTER_SOCIETY_RE.search(title):
        return "global" if _DISASTER_FOREIGN_RE.search(title) else "general"
    if _MACRO_STRATEGIST_RE.search(title):
        return "finance"
    if _AI_KW_RE.search(text):
        return "tech"
    if _CRYPTO_KW_RE.search(title) and not _GEO_PRIORITY_RE.search(title):
        return "finance"
    if _GEO_PRIORITY_RE.search(text):
        return "global"
    is_domestic_ministry = bool(re.search(r"(?:发改委|工信部|商务部)", title) and not re.search(r"(?:美国商务部|美商务部)", title))
    if is_domestic_ministry and not _GEO_PRIORITY_RE.search(text) and not _GLOBAL_KW_RE.search(text):
        return "finance" if _FIN_KW_RE.search(text) else "general"
    if _FIN_KW_RE.search(text):
        return "finance"
    if _GLOBAL_KW_RE.search(text):
        return "global"
    if default_cat == "global" and _DOMESTIC_RE.search(text) and not _GLOBAL_KW_RE.search(text):
        return "finance"
    return default_cat


def _epoch_to_shanghai_iso(ts_val: Any) -> Optional[str]:
    try:
        num = float(ts_val)
        if num > 1e12:
            num /= 1000.0
        if num < 1_500_000_000:
            return None
        dt = datetime.fromtimestamp(num, tz=timezone.utc).astimezone(SHANGHAI_TZ)
        return to_iso_shanghai(dt)
    except Exception:
        return None


def _extract_wire_image(row: Dict[str, Any]) -> Optional[str]:
    candidates: List[Any] = [
        row.get("image_uri"),
        row.get("image"),
        row.get("img"),
        row.get("shareimg"),
    ]
    for list_k in ("image_uris", "images"):
        imgs = row.get(list_k)
        if isinstance(imgs, list) and imgs:
            first = imgs[0]
            candidates.append(first.get("url") if isinstance(first, dict) else first)
    for c in candidates:
        if isinstance(c, str):
            u = c.strip()
            if u.startswith("//"):
                u = "https:" + u
            if u.startswith(("http://", "https://")) and not re.search(r"(?:1x1|pixel|favicon|logo|\.svg)", u, re.I):
                return u
    return None


def _fetch_wallstreetcn_channel(channel: str, label: str, default_cat: str, fetched_iso: str) -> Dict[str, Any]:
    endpoints = (
        f"https://api-one.wallstcn.com/apiv1/content/lives?channel={channel}&limit=25",
        f"https://api-one-wscn.awtmt.com/apiv1/content/lives?channel={channel}&limit=25",
    )
    items: List[dict] = []
    err: Optional[str] = None
    resp_ok: Optional[requests.Response] = None
    try:
        for url in endpoints:
            try:
                r = requests.get(
                    url,
                    headers={**_HEADERS, "Referer": "https://wallstreetcn.com/"},
                    timeout=(6, 10),
                )
                if r.status_code == 200:
                    resp_ok = r
                    err = None
                    break
                err = f"HTTP {r.status_code}"
            except Exception as exc_one:
                err = f"{type(exc_one).__name__}: {str(exc_one)[:80]}"
                continue
        if resp_ok is not None:
            data = resp_ok.json()
            rows = (data.get("data") or {}).get("items") or []
            for row in rows:
                content = _clean(row.get("content_text") or row.get("content"), max_len=280)
                title = _clean(row.get("title"), max_len=160)
                if not title and content:
                    # Extract 【Headline】 if present
                    m = re.match(r"【([^】]{4,80})】", content)
                    title = m.group(1) if m else _clean(content, 88)
                if not title or len(title) < 4 or _PURE_WIRE_FLUFF_RE.search(title) or is_consumer_promo_or_fluff(title, content):
                    continue
                uri = row.get("uri") or f"https://wallstreetcn.com/livenews/{row.get('id', '')}"
                canon = canonicalize_url(uri) or f"https://wallstreetcn.com/livenews/{row.get('id', '')}"
                pub_iso = _epoch_to_shanghai_iso(row.get("display_time")) or fetched_iso
                score = int(row.get("score") or 1)
                cat = _classify_wire_item(title, content, default_cat)
                items.append(
                    {
                        "item_id": make_raw_item_id(f"wscn-{channel}", canon, title),
                        "source_id": f"wscn-{channel}",
                        "source_name": label,
                        "category": cat,
                        "source_kind": "news",
                        "source_tier": "direct_media",
                        "publisher_family": "wallstreetcn",
                        "citable_as_news": True,
                        "title": title,
                        "url": canon,
                        "canonical_url": canon,
                        "published_at": pub_iso,
                        "published_at_source": "upstream_api",
                        "fetched_at": fetched_iso,
                        "excerpt": content if content != title else None,
                        "thumbnail_url": _extract_wire_image(row),
                        "metric_label": "重要快讯" if score >= 2 else None,
                        "importance": "high" if score >= 2 else "normal",
                    }
                )
    except Exception as exc:
        err = f"{type(exc).__name__}: {str(exc)[:80]}"
    return {
        "id": f"wscn-{channel}",
        "name": label,
        "category": default_cat,
        "items": items,
        "error": err,
    }


def _fetch_cls_telegraph(fetched_iso: str) -> Dict[str, Any]:
    url = "https://www.cls.cn/nodeapi/telegraphList?app=CailianpressWeb&os=web&rn=25&sv=8.4.6"
    items: List[dict] = []
    err: Optional[str] = None
    try:
        r = requests.get(url, headers={**_HEADERS, "Referer": "https://www.cls.cn/telegraph"}, timeout=(4, 7))
        if r.status_code != 200:
            err = f"HTTP {r.status_code}"
        else:
            data = r.json()
            rows = (data.get("data") or {}).get("roll_data") or []
            for row in rows:
                content = _clean(row.get("content") or row.get("brief"), max_len=280)
                title = _clean(row.get("title"), max_len=160)
                if not title and content:
                    m = re.match(r"【([^】]{4,80})】", content)
                    title = m.group(1) if m else _clean(content, 88)
                if not title or len(title) < 4 or _PURE_WIRE_FLUFF_RE.search(title) or is_consumer_promo_or_fluff(title, content):
                    continue
                rid = row.get("id") or ""
                canon = canonicalize_url(row.get("shareurl") or f"https://www.cls.cn/detail/{rid}") or f"https://www.cls.cn/detail/{rid}"
                pub_iso = _epoch_to_shanghai_iso(row.get("ctime")) or fetched_iso
                level = str(row.get("level") or "C").upper()
                is_high = level in {"A", "B"}
                cat = _classify_wire_item(title, content, "finance")
                items.append(
                    {
                        "item_id": make_raw_item_id("cls-live", canon, title),
                        "source_id": "cls-live",
                        "source_name": "财联社 7×24 电报",
                        "category": cat,
                        "source_kind": "news",
                        "source_tier": "direct_media",
                        "publisher_family": "cls",
                        "citable_as_news": True,
                        "title": title,
                        "url": canon,
                        "canonical_url": canon,
                        "published_at": pub_iso,
                        "published_at_source": "upstream_api",
                        "fetched_at": fetched_iso,
                        "excerpt": content if content != title else None,
                        "thumbnail_url": _extract_wire_image(row),
                        "metric_label": "加红电报" if is_high else None,
                        "importance": "high" if is_high else "normal",
                    }
                )
    except Exception as exc:
        err = f"{type(exc).__name__}: {str(exc)[:80]}"
    return {
        "id": "cls-live",
        "name": "财联社 7×24 电报",
        "category": "finance",
        "items": items,
        "error": err,
    }


def _fetch_sina_7x24_telegraph(fetched_iso: str) -> Dict[str, Any]:
    url = "https://zhibo.sina.com.cn/api/zhibo/feed?zhibo_id=152&tag_id=0&page=1&page_size=25&type=0"
    items: List[dict] = []
    err: Optional[str] = None
    try:
        import json as _json

        r = requests.get(
            url,
            headers={**_HEADERS, "Referer": "https://finance.sina.com.cn/7x24/"},
            timeout=(6, 10),
        )
        if r.status_code != 200:
            err = f"HTTP {r.status_code}"
        else:
            data = r.json()
            rows = (((data.get("result") or {}).get("data") or {}).get("feed") or {}).get("list") or []
            for row in rows:
                if not isinstance(row, dict) or int(row.get("is_delete") or 0) == 1:
                    continue
                content = _clean(row.get("rich_text"), max_len=280)
                if not content or len(content) < 6 or _PURE_WIRE_FLUFF_RE.search(content):
                    continue
                m = re.match(r"【([^】]{4,80})】", content)
                title = m.group(1) if m else _clean(content, 88)
                if not title or len(title) < 4 or _PURE_WIRE_FLUFF_RE.search(title) or is_consumer_promo_or_fluff(title, content):
                    continue
                ext_doc = None
                try:
                    ext_raw = row.get("ext")
                    if isinstance(ext_raw, str) and ext_raw.strip().startswith("{"):
                        ext_doc = _json.loads(ext_raw).get("docurl")
                except Exception:
                    ext_doc = None
                rid = str(row.get("id") or "")
                raw_url = row.get("docurl") or ext_doc or f"https://finance.sina.com.cn/7x24/?id={rid}"
                canon = canonicalize_url(raw_url) or f"https://finance.sina.com.cn/7x24/?id={rid}"
                ct_raw = str(row.get("create_time") or "").strip()
                pub_iso = fetched_iso
                if ct_raw:
                    try:
                        pub_iso = to_iso_shanghai(datetime.strptime(ct_raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI_TZ))
                    except Exception:
                        pub_iso = fetched_iso
                is_high = int(row.get("is_focus") or 0) == 1
                cat = _classify_wire_item(title, content, "finance")
                items.append(
                    {
                        "item_id": make_raw_item_id("sina-7x24", canon, title),
                        "source_id": "sina-7x24",
                        "source_name": "新浪财经 7×24 电报",
                        "category": cat,
                        "source_kind": "news",
                        "source_tier": "direct_media",
                        "publisher_family": "sina",
                        "citable_as_news": True,
                        "title": title,
                        "url": canon,
                        "canonical_url": canon,
                        "published_at": pub_iso,
                        "published_at_source": "upstream_api",
                        "fetched_at": fetched_iso,
                        "excerpt": content if content != title else None,
                        "thumbnail_url": _extract_wire_image(row),
                        "metric_label": "焦点快讯" if is_high else None,
                        "importance": "high" if is_high else "normal",
                    }
                )
    except Exception as exc:
        err = f"{type(exc).__name__}: {str(exc)[:80]}"
    return {
        "id": "sina-7x24",
        "name": "新浪财经 7×24 电报",
        "category": "finance",
        "items": items,
        "error": err,
    }


def _fetch_rss_flash(feed_id: str, label: str, default_cat: str, url: str, family: str, fetched_iso: str) -> Dict[str, Any]:
    items: List[dict] = []
    err: Optional[str] = None
    try:
        r = requests.get(url, headers=_HEADERS, timeout=(4, 7))
        if r.status_code != 200:
            err = f"HTTP {r.status_code}"
        else:
            root = ET.fromstring(r.content)
            for node in root.findall(".//item")[:20]:
                t_el = node.find("title")
                l_el = node.find("link")
                p_el = node.find("pubDate")
                d_el = node.find("description")
                title = _clean(t_el.text if t_el is not None else "", max_len=170)
                link = (l_el.text or "").strip() if l_el is not None else ""
                canon = canonicalize_url(link)
                if not title or not canon or _PURE_WIRE_FLUFF_RE.search(title) or is_consumer_promo_or_fluff(title, raw_desc):
                    continue
                pub_iso, pub_src = parse_published_at(p_el.text.strip() if (p_el is not None and p_el.text) else None, feed_id)
                raw_desc = d_el.text if d_el is not None else ""
                excerpt = _clean(raw_desc, max_len=240)
                thumb_url: Optional[str] = None
                enc = node.find("enclosure")
                if enc is not None and (enc.attrib.get("type") or "").startswith("image/") and enc.attrib.get("url"):
                    thumb_url = enc.attrib["url"].strip()
                if not thumb_url and raw_desc:
                    img_m = re.search(r"""<img[^>]+src=["']([^"']+)["']""", raw_desc, re.I)
                    if img_m and img_m.group(1).startswith(("http://", "https://")):
                        thumb_url = img_m.group(1).strip()
                cat = _classify_wire_item(title, excerpt, default_cat)
                items.append(
                    {
                        "item_id": make_raw_item_id(feed_id, canon, title),
                        "source_id": feed_id,
                        "source_name": label,
                        "category": cat,
                        "source_kind": "news",
                        "source_tier": "direct_media",
                        "publisher_family": family,
                        "citable_as_news": True,
                        "title": title,
                        "url": canon,
                        "canonical_url": canon,
                        "published_at": pub_iso or fetched_iso,
                        "published_at_source": pub_src,
                        "fetched_at": fetched_iso,
                        "excerpt": excerpt if excerpt and excerpt != title else None,
                        "thumbnail_url": thumb_url,
                        "metric_label": None,
                        "importance": "high" if _AI_KW_RE.search(title) else "normal",
                    }
                )
    except Exception as exc:
        err = f"{type(exc).__name__}: {str(exc)[:80]}"
    return {
        "id": feed_id,
        "name": label,
        "category": default_cat,
        "items": items,
        "error": err,
    }


def fetch_china_realtime_wires(cache: Optional[HttpCacheStore] = None) -> Dict[str, Any]:
    """Concurrently fetch 7x24 Chinese real-time financial & tech flash wires."""
    del cache
    t0 = time.monotonic()
    fetched_iso = to_iso_shanghai(now_shanghai())

    tasks = [
        lambda: _fetch_wallstreetcn_channel("global-channel", "华尔街见闻 7×24 全球", "global", fetched_iso),
        lambda: _fetch_wallstreetcn_channel("a-stock-channel", "华尔街见闻 A股快讯", "finance", fetched_iso),
        lambda: _fetch_wallstreetcn_channel("us-stock-channel", "华尔街见闻 美股快讯", "finance", fetched_iso),
        lambda: _fetch_wallstreetcn_channel("tech-channel", "华尔街见闻 科技/AI快讯", "tech", fetched_iso),
        lambda: _fetch_sina_7x24_telegraph(fetched_iso),
        lambda: _fetch_rss_flash("ithome-rss", "IT之家 实时快讯", "tech", "https://www.ithome.com/rss/", "ithome", fetched_iso),
    ]

    all_items: List[dict] = []
    seen_channel_urls: set[str] = set()
    platforms_by_category: Dict[str, List[dict]] = {"finance": [], "global": [], "tech": [], "general": []}
    source_reports: List[dict] = []
    ok_cnt = 0
    errors: List[str] = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(fn) for fn in tasks]
        for fut in as_completed(futs):
            res = fut.result()
            raw_its = res["items"]
            its: List[dict] = []
            for it in raw_its:
                cu = canonicalize_url(it.get("canonical_url") or it.get("url"))
                if cu and cu in seen_channel_urls:
                    continue
                if cu:
                    seen_channel_urls.add(cu)
                its.append(it)
            err = res["error"]
            if err:
                errors.append(f"{res['id']}: {err}")
                st = "error"
            elif not raw_its:
                st = "empty"
            else:
                ok_cnt += 1
                st = "ok"
            all_items.extend(its)
            latest_ts = max((it.get("published_at") for it in its if it.get("published_at")), default=fetched_iso)
            cat = res["category"]
            platforms_by_category.setdefault(cat, []).append(
                {
                    "id": res["id"],
                    "name": res["name"],
                    "kind": "news",
                    "status": st,
                    "upstream_status": "realtime_wire",
                    "upstream_updated_at": latest_ts,
                    "fetched_at": fetched_iso,
                    "last_success_at": latest_ts if st == "ok" else None,
                    "items": its,
                }
            )
            source_reports.append(
                {
                    "id": res["id"],
                    "name": res["name"],
                    "category": cat,
                    "kind": "news",
                    "status": st,
                    "item_count": len(its),
                    "pub_date_coverage": 1.0 if its else 0.0,
                    "upstream_updated_at": latest_ts,
                    "last_success_at": latest_ts if st == "ok" else None,
                    "error_message": err,
                }
            )

    latency_ms = int((time.monotonic() - t0) * 1000)
    overall = "ok" if ok_cnt >= 3 else ("partial" if ok_cnt > 0 else "error")
    return {
        "connector_id": "china-realtime-wires",
        "connector_name": f"7×24 国内/全球实时电报快讯 ({ok_cnt}/{len(tasks)})",
        "source_tier": "direct_media",
        "status": overall,
        "fetched_at": fetched_iso,
        "latency_ms": latency_ms,
        "item_count": len(all_items),
        "calendar_count": 0,
        "error_message": "; ".join(errors[:4]) if errors else None,
        "tos_note": "聚合华尔街见闻与 IT 之家稳定公开实时快讯接口，用于 7×24 零延迟消息流。",
        "items": all_items,
        "platforms_by_category": platforms_by_category,
        "source_reports": source_reports,
    }


_WIRE_S_TIER_RE = re.compile(
    r"(?:(?:沪深北|三大|沪深)交易所.{0,18}(?:融资保证金|降费|让利|做市|稳市)|"
    r"上交所.{0,12}(?:做市|降费)|深交所.{0,12}(?:做市|征求意见)|中国结算.{0,10}暂免|"
    r"证监会.{0,12}(?:重大政策|修订|调整融资|组合政策)|"
    r"(?:人民银行|中国人民银行|中国央行|美联储).{0,12}(?:降准|降息|LPR|利率决议|加息|FOMC)|"
    r"(?:美伊|以伊|中东|俄乌).{0,16}(?:遇袭|袭击|击落|正式封锁|达成停火|签署和平协议)|"
    r"中美元首.{0,16}(?:协议|联合声明|关税)|"
    r"菲尔兹奖.{0,12}黎曼|梅纳德.{0,12}黎曼|BepiColombo|进入水星轨道|神舟.{0,8}(?:发射|升空)|星舰.{0,8}回收)",
    re.I,
)
_WIRE_S_EXCLUDE_RE = re.compile(r"(?:台湾|台湾地区|只要.*诉求|立场明确|呼吁对话|传递想法|保持密切对话)")
_WIRE_NOISE_HEAVY_RE = re.compile(
    r"(?:降价通知|api\s*降价|限时降价|促销|优惠|夜盘普遍|夜盘微涨|夜盘涨|夜盘跌|盘前微涨|盘前涨|盘前跌|"
    r"早间要闻|要闻汇总|盘前必读|早报汇总|午间公告|复盘汇总|联盟.{0,8}成立|协会.{0,8}成立|发展联盟|正式成立|行业论坛|"
    r"中间价|上海钢联|现货报价|提议设|提议(?:将|用).{0,24}限制|呼吁限制|涨停|持续活跃|短剧|影视股|概念股拉升|盘中拉升|探底回升|重仓股曝光)",
    re.I,
)
_WIRE_A_TIER_RE = re.compile(
    r"(?:自贸协定|百亿美元并购|法院禁售|出口管制|实体清单|重大漏洞|CVE|IPO.*(?:首日|募资)|"
    r"主动ETF|股市稳定基金|平准基金|440亿|黎曼猜想|Mathlib|(?:涨价|提价).{0,8}45%|"
    r"央行.*(?:降准|降息|利率|货币政策|LPR|纪要)|国务院.*印发|证监会|美联储|FOMC|中美元首|关税|"
    r"(?:暴跌|飙升|重挫)\s*[4-9](?:\.\d+)?%|"
    r"(?:发布|上线|推出|开源).{0,14}(?:GPT-?\d|Claude|Gemini\s*\d|DeepSeek|Qwen|GLM-\d|Kimi)|英伟达|SpaceX)",
    re.I,
)


def _infer_wire_heavy_reason_tag(title: str, excerpt: str = "", category: str = "") -> str:
    """Return concise human-readable category reason via unified heavy_classifier."""
    del category
    return infer_heavy_reason_tag(title, excerpt)
_EXCHANGE_REFORM_CLUSTER_RE = re.compile(
    r"(?:沪深北交易所|沪深交易所|上交所.{0,10}(?:做市|降费)|深交所.{0,10}(?:做市|征求意见)|中国结算.{0,10}债券)",
    re.I,
)


def _classify_wire_severity(
    title: str,
    excerpt: str,
    source_id: str,
    source_name: str,
) -> tuple[str, str]:
    """Classify wire item severity into S / A / B using authoritative sources + substantive impact."""
    if (
        is_hotlist_aggregator_source(source_id, source_name)
        or is_consumer_promo_or_fluff(title, excerpt)
        or _WIRE_NOISE_HEAVY_RE.search(title)
        or HEAVY_NOISE_EXCLUDE_RE.search(title)
    ):
        return "B", "常规动态"
    if _WIRE_S_EXCLUDE_RE.search(title):
        return "A" if _WIRE_A_TIER_RE.search(title) else "B", "常规动态"
    blob = f"{title} {excerpt}"
    if _WIRE_S_TIER_RE.search(title) or (_EXCHANGE_REFORM_CLUSTER_RE.search(title) and not _WIRE_S_EXCLUDE_RE.search(blob)):
        return "S", "S级突发重磅"
    if GEO_MILITARY_HEAVY_RE.search(title):
        return "A", "A级突发重磅"
    if _WIRE_A_TIER_RE.search(blob):
        return "A", "A级要闻"
    return "B", "常规动态"


def refresh_live_wire_file(base_dir: Path | str = ".", extra_items: Optional[List[dict]] = None) -> Dict[str, Any]:
    """Fetch fresh 7x24 flash wires and merge with existing overseas items into `data/live_wire.json`."""
    root = Path(base_dir)
    res = fetch_china_realtime_wires()
    fetched_iso = res["fetched_at"]
    now_dt = now_shanghai()

    prev_doc = load_json_if_exists(root / "data/live_wire.json", default={})
    prev_items = prev_doc.get("items", []) if isinstance(prev_doc, dict) else []

    merged: List[dict] = []
    seen_keys: set[str] = set()
    seen_urls: set[str] = set()
    seen_entries: List[Tuple[str, str, int]] = []  # (norm_title, pub_iso, merged_idx)

    _WIRE_CLUSTERS = (
        ("孙正义", "海力士"),
        ("软银", "海力士"),
        ("openai", "蒸馏"),
        ("apec", "深圳"),
        ("美伊", "谈判"),
        ("黄仁勋", "聘用"),
        ("黄仁勋", "董事会"),
        ("英伟达", "sec"),
        ("主动etf", "上市"),
        ("主动etf", "申赎"),
        ("主动etf", "建仓"),
        ("主动etf", "18只"),
        ("韩国", "稳定基金"),
        ("韩国", "稳市"),
        ("韩国", "稳定股市"),
        ("韩国", "平准"),
        ("融资保证金", "80%"),
        ("融资保证金", "沪深"),
        ("美股", "期货"),
        ("纳指", "英伟达"),
    )

    def _wire_titles_similar(norm_a: str, norm_b: str) -> bool:
        if not norm_a or not norm_b:
            return False
        if norm_a == norm_b:
            return True
        if len(norm_a) >= 12 and len(norm_b) >= 12 and (norm_a.startswith(norm_b[:16]) or norm_b.startswith(norm_a[:16])):
            return True
        for a, b in _WIRE_CLUSTERS:
            if a in norm_a and b in norm_a and a in norm_b and b in norm_b:
                return True
        if len(norm_a) >= 10 and len(norm_b) >= 10:
            bg_a = {norm_a[i : i + 2] for i in range(len(norm_a) - 1)}
            bg_b = {norm_b[i : i + 2] for i in range(len(norm_b) - 1)}
            union = bg_a | bg_b
            if union and (len(bg_a & bg_b) / len(union)) >= 0.44:
                return True
        return False

    def _within_two_hours(iso_a: str, iso_b: str) -> bool:
        dt_a = parse_iso_datetime(iso_a)
        dt_b = parse_iso_datetime(iso_b)
        if dt_a is None or dt_b is None:
            return True
        return abs((dt_a - dt_b).total_seconds()) <= 7200

    def _format_merged_sources(src_list: List[str]) -> str:
        clean_s = list(dict.fromkeys([s.strip() for s in src_list if s and s.strip()]))
        if not clean_s:
            return "实时快讯"
        if len(clean_s) == 1:
            return clean_s[0]
        if len(clean_s) == 2:
            return f"{clean_s[0]} / {clean_s[1]} · 2 源合并"
        return f"{clean_s[0]} / {clean_s[1]} 等 {len(clean_s)} 源合并"

    def _add(it: dict) -> None:
        title = str(it.get("title") or "").strip()
        excerpt_clean = _clean(it.get("excerpt") or "", 240)
        if not title or len(title) < 4 or _PURE_WIRE_FLUFF_RE.search(title) or is_consumer_promo_or_fluff(title, excerpt_clean):
            return
        canon_u = canonicalize_url(it.get("url") or it.get("canonical_url")) or ""
        if canon_u and canon_u in seen_urls:
            return
        norm_full = re.sub(r"[\s\-_·:：,，.。!！?？()（）\[\]【】'\"]+", "", title.lower())
        k = norm_full[:28]
        if not k or k in seen_keys:
            return
        pub = str(it.get("published_at") or it.get("fetched_at") or fetched_iso)
        src_id = str(it.get("source_id") or "")
        src_name = str(it.get("source_name") or "实时快讯")
        for prev_norm, prev_pub, prev_idx in seen_entries:
            if _within_two_hours(pub, prev_pub) and _wire_titles_similar(norm_full, prev_norm):
                # Coalesce duplicate cross-source wire into existing cluster item
                target = merged[prev_idx]
                base_srcs = target.setdefault("_merged_sources", [target.get("source_name") or "实时快讯"])
                raw_short = src_name.split(" · ")[0].split(" 等 ")[0]
                if raw_short and raw_short not in base_srcs:
                    base_srcs.append(raw_short)
                    target["source_name"] = _format_merged_sources(base_srcs)
                return
        if canon_u:
            seen_urls.add(canon_u)
        seen_keys.add(k)
        cat_norm = _classify_wire_item(title, excerpt_clean, str(it.get("category") or "general"))
        if it.get("synced_from_today") and not HEAVY_NOISE_EXCLUDE_RE.search(title):
            sev_tier = "S" if it.get("severity_tier") == "S" else "A"
            reason_tag = str(it.get("heavy_reason_tag") or "").strip() or _infer_wire_heavy_reason_tag(title, excerpt_clean, cat_norm)
        else:
            sev_tier, _ = _classify_wire_severity(title, excerpt_clean, src_id, src_name)
            reason_tag = _infer_wire_heavy_reason_tag(title, excerpt_clean, cat_norm) if sev_tier in {"S", "A"} else None
        idx_new = len(merged)
        seen_entries.append((norm_full, pub, idx_new))
        entry_obj = {
            "id": str(it.get("item_id") or it.get("id") or f"lw_{idx_new}"),
            "title": title,
            "excerpt": excerpt_clean,
            "category": cat_norm,
            "source_name": src_name,
            "_merged_sources": [s.strip() for s in str(it.get("source_name") or "实时快讯").split(" · ")[0].split(" 等 ")[0].split("/") if s.strip()],
            "url": canon_u or str(it.get("url") or it.get("canonical_url") or ""),
            "published_at": pub,
            "thumbnail_url": it.get("thumbnail_url"),
            "severity_tier": sev_tier,
            "heavy_reason_tag": reason_tag,
            "importance": "high" if sev_tier in {"S", "A"} else "normal",
            "tag": str(it.get("metric_label") or it.get("tag") or ""),
        }
        if it.get("synced_from_today"):
            entry_obj["synced_from_today"] = True
        merged.append(entry_obj)

    for it in res.get("items") or []:
        _add(it)
    for it in extra_items or []:
        _add(it)
    for it in prev_items:
        if isinstance(it, dict):
            _add(it)

    for item in merged:
        item.pop("_merged_sources", None)
    merged.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    merged = merged[:120]

    # Calibrate 7x24 wire heavy alerts (<= 15, zero semantic duplicates or multi-post topic clones among heavy picks)
    high_indices = [idx for idx, it in enumerate(merged) if it.get("importance") == "high"]
    selected_high: List[int] = []
    heavy_norms: List[str] = []
    seen_topic_keys: set[str] = set()
    s_first = [idx for idx in high_indices if merged[idx].get("severity_tier") == "S"] + [
        idx for idx in high_indices if merged[idx].get("severity_tier") != "S"
    ]
    for idx in s_first:
        n_cur = re.sub(r"[\s\-_·:：,，.。!！?？()（）\[\]【】'\"]+", "", str(merged[idx].get("title") or "").lower())
        tkey = heavy_topic_key(n_cur)
        if tkey and tkey in seen_topic_keys:
            continue
        if any(_wire_titles_similar(n_cur, prev_n) for prev_n in heavy_norms):
            continue
        if len(selected_high) < 12:
            selected_high.append(idx)
            heavy_norms.append(n_cur)
            if tkey:
                seen_topic_keys.add(tkey)
    keep_high = set(selected_high)
    for idx in high_indices:
        if idx not in keep_high:
            merged[idx]["severity_tier"] = "B"
            merged[idx]["importance"] = "normal"
            merged[idx]["heavy_reason_tag"] = None
        elif not merged[idx].get("heavy_reason_tag"):
            merged[idx]["heavy_reason_tag"] = _infer_wire_heavy_reason_tag(
                str(merged[idx].get("title") or ""),
                str(merged[idx].get("excerpt") or ""),
                str(merged[idx].get("category") or ""),
            )

    # Fast-Track Promotion: cluster <12h authoritative S-tier wires into breaking_highlights for immediate homepage surfacing
    breaking_highlights: List[Dict[str, Any]] = []
    policy_cluster_items: List[Dict[str, Any]] = []
    other_s_items: List[Dict[str, Any]] = []
    for item in merged:
        if item.get("severity_tier") != "S":
            continue
        pub_dt = None
        try:
            pub_raw = str(item.get("published_at") or "")
            if pub_raw:
                pub_dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=SHANGHAI_TZ)
        except Exception:
            pub_dt = None
        if pub_dt is not None and (now_dt - pub_dt).total_seconds() > 12 * 3600:
            continue
        blob = f"{item.get('title') or ''} {item.get('excerpt') or ''}"
        if _EXCHANGE_REFORM_CLUSTER_RE.search(blob) and "台湾" not in blob:
            policy_cluster_items.append(item)
        else:
            other_s_items.append(item)

    if policy_cluster_items:
        # Prefer the strongest headline mentioning 融资保证金 / 释放 4000 亿 as the cluster lead
        lead = max(
            policy_cluster_items,
            key=lambda x: (
                1 if ("保证金" in str(x.get("title") or "") or "4000亿" in str(x.get("title") or "")) else 0,
                str(x.get("published_at") or ""),
            ),
        )
        related_titles = [
            str(x.get("title") or "")
            for x in policy_cluster_items
            if x is not lead and str(x.get("title") or "")
        ][:4]
        breaking_highlights.append(
            {
                "id": f"brk_{lead['id']}",
                "title": lead["title"],
                "excerpt": lead.get("excerpt") or "",
                "category": lead.get("category") or "finance",
                "severity_tier": "S",
                "breaking_label": "刚刚突发 · 重磅",
                "source_name": lead.get("source_name") or "权威电报",
                "url": lead.get("url") or "",
                "published_at": lead.get("published_at") or fetched_iso,
                "related_count": len(related_titles),
                "related_titles": related_titles,
            }
        )

    for item in other_s_items:
        if len(breaking_highlights) >= 3:
            break
        breaking_highlights.append(
            {
                "id": f"brk_{item['id']}",
                "title": item["title"],
                "excerpt": item.get("excerpt") or "",
                "category": item.get("category") or "finance",
                "severity_tier": "S",
                "breaking_label": "刚刚突发 · 重磅",
                "source_name": item.get("source_name") or "权威电报",
                "url": item.get("url") or "",
                "published_at": item.get("published_at") or fetched_iso,
                "related_count": 0,
                "related_titles": [],
            }
        )

    doc = {
        "schema_version": "5.1",
        "updated_at": fetched_iso,
        "status": res["status"],
        "sources_online": res["connector_name"],
        "total": len(merged),
        "breaking_highlights": breaking_highlights,
        "items": merged,
    }
    try:
        manifest_disk = load_json_if_exists(root / "data/manifest.json", default={}) or {}
        smart_cats = (manifest_disk.get("smart") or {}).get("categories") if isinstance(manifest_disk, dict) else {}
        cat_docs: Dict[str, dict] = {}
        has_any_events = False
        for c in ("finance", "global", "tech", "general"):
            c_rel = ""
            if isinstance(smart_cats, dict) and isinstance(smart_cats.get(c), dict):
                c_rel = str(smart_cats[c].get("path") or "").lstrip("./")
            cand_paths = [root / c_rel] if c_rel else []
            cand_paths.append(root / f"analysis_{c}.json")
            c_doc = None
            for cp in cand_paths:
                if cp.exists():
                    loaded = load_json_if_exists(cp, default={})
                    if isinstance(loaded, dict) and loaded.get("events"):
                        c_doc = loaded
                        break
            if isinstance(c_doc, dict) and c_doc.get("events"):
                cat_docs[c] = c_doc
                has_any_events = True
            else:
                cat_docs[c] = {"events": []}
        if has_any_events:
            doc = sync_today_heavy_into_live_wire(cat_docs, doc, now_dt)
    except Exception:
        pass
    atomic_write_json(root / "data/live_wire.json", doc)
    return doc


if __name__ == "__main__":
    out = refresh_live_wire_file(".")
    print(f"[live_wire] updated_at={out['updated_at']} total={out['total']} status={out['status']}")
