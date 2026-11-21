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
from pipeline.dedup import smart_truncate
from pipeline.id_utils import canonicalize_url, make_raw_item_id
from pipeline.manifest import atomic_write_json, load_json_if_exists
from pipeline.time_utils import SHANGHAI_TZ, now_shanghai, parse_published_at, to_iso_shanghai

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
    r"(?:ai|大模型|gemini|neon|carbon|hydrogen|openai|gpt|claude|anthropic|qwen|千问|kimi|混元|workbuddy|电脑操控|计算机控制|元宝|豆包|seedance|manus|minimax|智谱|glm|cursor|windsurf|antigravity|mcp|千亿.*大模型|腾讯.*ai|deepseek|算力|英伟达|nvidia|芯片|gpu|开源|agent|智能体|机器人)",
    re.I,
)
_GEO_PRIORITY_RE = re.compile(
    r"(?:导弹|空袭|无人机|击落|战机|航母|油轮|触雷|海峡|霍尔木兹|红海|"
    r"停火|和平协议|俄乌|美伊|以色列|加沙|波兰|北约|外交|元首|白宫|峰会|联合国)",
    re.I,
)
_FIN_KW_RE = re.compile(
    r"(?:a股|美股|港股|美联储|央行|降息|加息|黄金|原油|汇率|人民币|美元指数|美元汇率|纳指|标普|沪指|创业板|涨停|跌停|财报|ipo|关税|国债|cpi|非农|板块|回购|比特币|以太坊|\bBTC\b|\bETH\b|加密货币)",
    re.I,
)
_CRYPTO_KW_RE = re.compile(r"(?:比特币|以太坊|\bBTC\b|\bETH\b|加密货币|虚拟货币|币安)", re.I)
_DOMESTIC_RE = re.compile(
    r"(?:a股|沪指|深成指|创业板|上期所|深交所|上交所|北交所|国务院|发改委|工信部|央行|证监会|人民币|沪深|中芯|比亚迪|宁德时代|华为|腾讯|阿里|回购股份|股份有限公司|人民日报|新华社|央视新闻|商务部)",
    re.I,
)
_GLOBAL_KW_RE = re.compile(
    r"(?:特朗普|拜登|白宫|欧盟|联合国|apec|峰会|外交|中东|俄乌|停火|制裁|总统|首相|外交部|美商务部|美国商务部|访华|日央行|欧洲央行)",
    re.I,
)


def _clean(raw: Any, max_len: int = 240) -> str:
    if not raw:
        return ""
    s = html.unescape(_HTML_RE.sub(" ", str(raw)))
    return smart_truncate(s, max_len=max_len)


_NON_TECH_CONSUMER_OR_CRIME_RE = re.compile(
    r"(?:帮信罪|刑拘|逮捕|派出所|警方|涉案|诈骗案|Steam|黑五.*游戏|游戏新史低|重制版|导剪版|折扣促销)",
    re.I,
)


def _classify_wire_item(title: str, content: str, default_cat: str) -> str:
    text = f"{title} {content}"
    if _NON_TECH_CONSUMER_OR_CRIME_RE.search(title):
        return "general"
    if _AI_KW_RE.search(text):
        return "tech"
    if _CRYPTO_KW_RE.search(title) and not _GEO_PRIORITY_RE.search(title):
        return "finance"
    if _GEO_PRIORITY_RE.search(text):
        return "global"
    is_domestic_ministry = bool(re.search(r"(?:发改委|工信部|商务部|人民日报|新华社)", title) and not re.search(r"(?:美国商务部|美商务部)", title))
    if is_domestic_ministry:
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


def _fetch_wallstreetcn_channel(channel: str, label: str, default_cat: str, fetched_iso: str) -> Dict[str, Any]:
    url = f"https://api-one.wallstcn.com/apiv1/content/lives?channel={channel}&limit=25"
    items: List[dict] = []
    err: Optional[str] = None
    try:
        r = requests.get(url, headers=_HEADERS, timeout=(4, 7))
        if r.status_code != 200:
            err = f"HTTP {r.status_code}"
        else:
            data = r.json()
            rows = (data.get("data") or {}).get("items") or []
            for row in rows:
                content = _clean(row.get("content_text") or row.get("content"), max_len=280)
                title = _clean(row.get("title"), max_len=160)
                if not title and content:
                    # Extract 【Headline】 if present
                    m = re.match(r"【([^】]{4,80})】", content)
                    title = m.group(1) if m else _clean(content, 88)
                if not title or len(title) < 4:
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
                if not title or len(title) < 4:
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
                if not title or not canon:
                    continue
                pub_iso, pub_src = parse_published_at(p_el.text.strip() if (p_el is not None and p_el.text) else None, feed_id)
                excerpt = _clean(d_el.text if d_el is not None else "", max_len=240)
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
        lambda: _fetch_cls_telegraph(fetched_iso),
        lambda: _fetch_rss_flash("36kr-newsflash", "36氪 7×24 科技快讯", "tech", "https://36kr.com/feed-newsflash", "36kr", fetched_iso),
        lambda: _fetch_rss_flash("ithome-rss", "IT之家 实时快讯", "tech", "https://www.ithome.com/rss/", "ithome", fetched_iso),
    ]

    all_items: List[dict] = []
    platforms_by_category: Dict[str, List[dict]] = {"finance": [], "global": [], "tech": [], "general": []}
    source_reports: List[dict] = []
    ok_cnt = 0
    errors: List[str] = []

    with ThreadPoolExecutor(max_workers=7) as pool:
        futs = [pool.submit(fn) for fn in tasks]
        for fut in as_completed(futs):
            res = fut.result()
            its = res["items"]
            err = res["error"]
            if err:
                errors.append(f"{res['id']}: {err}")
                st = "error"
            elif not its:
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
        "tos_note": "聚合华尔街见闻、财联社、36氪、IT之家公开实时快讯接口，用于 7×24 零延迟消息流。",
        "items": all_items,
        "platforms_by_category": platforms_by_category,
        "source_reports": source_reports,
    }


def refresh_live_wire_file(base_dir: Path | str = ".", extra_items: Optional[List[dict]] = None) -> Dict[str, Any]:
    """Fetch fresh 7x24 flash wires and merge with existing overseas items into `data/live_wire.json`."""
    root = Path(base_dir)
    res = fetch_china_realtime_wires()
    fetched_iso = res["fetched_at"]

    prev_doc = load_json_if_exists(root / "data/live_wire.json", default={})
    prev_items = prev_doc.get("items", []) if isinstance(prev_doc, dict) else []

    merged: List[dict] = []
    seen_keys: set[str] = set()
    seen_norms: List[str] = []

    def _wire_titles_similar(norm_a: str, norm_b: str) -> bool:
        if not norm_a or not norm_b:
            return False
        if norm_a == norm_b:
            return True
        if len(norm_a) >= 12 and len(norm_b) >= 12 and (norm_a.startswith(norm_b[:16]) or norm_b.startswith(norm_a[:16])):
            return True
        # Known wire multi-source cluster signatures
        wire_clusters = (
            ("孙正义", "海力士"),
            ("软银", "海力士"),
            ("openai", "蒸馏"),
            ("apec", "深圳"),
            ("美伊", "谈判"),
        )
        for a, b in wire_clusters:
            if a in norm_a and b in norm_a and a in norm_b and b in norm_b:
                return True
        if len(norm_a) >= 10 and len(norm_b) >= 10:
            bg_a = {norm_a[i : i + 2] for i in range(len(norm_a) - 1)}
            bg_b = {norm_b[i : i + 2] for i in range(len(norm_b) - 1)}
            union = bg_a | bg_b
            if union and (len(bg_a & bg_b) / len(union)) >= 0.44:
                return True
        return False

    def _add(it: dict) -> None:
        title = str(it.get("title") or "").strip()
        if not title or len(title) < 4:
            return
        norm_full = re.sub(r"[\s\-_·:：,，.。!！?？()（）\[\]【】'\"]+", "", title.lower())
        k = norm_full[:28]
        if not k or k in seen_keys:
            return
        if any(_wire_titles_similar(norm_full, prev) for prev in seen_norms):
            return
        seen_keys.add(k)
        seen_norms.append(norm_full)
        pub = str(it.get("published_at") or it.get("fetched_at") or fetched_iso)
        excerpt_clean = _clean(it.get("excerpt") or "", 240)
        cat_norm = _classify_wire_item(title, excerpt_clean, str(it.get("category") or "general"))
        merged.append(
            {
                "id": str(it.get("item_id") or it.get("id") or f"lw_{len(merged)}"),
                "title": title,
                "excerpt": excerpt_clean,
                "category": cat_norm,
                "source_name": str(it.get("source_name") or "实时快讯"),
                "url": str(it.get("url") or it.get("canonical_url") or ""),
                "published_at": pub,
                "importance": str(it.get("importance") or ("high" if it.get("metric_label") else "normal")),
                "tag": str(it.get("metric_label") or ""),
            }
        )

    for it in res.get("items") or []:
        _add(it)
    for it in extra_items or []:
        _add(it)
    for it in prev_items:
        if isinstance(it, dict):
            _add(it)

    merged.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    merged = merged[:120]

    doc = {
        "schema_version": "5.0",
        "updated_at": fetched_iso,
        "status": res["status"],
        "sources_online": res["connector_name"],
        "total": len(merged),
        "items": merged,
    }
    atomic_write_json(root / "data/live_wire.json", doc)
    return doc


if __name__ == "__main__":
    out = refresh_live_wire_file(".")
    print(f"[live_wire] updated_at={out['updated_at']} total={out['total']} status={out['status']}")
