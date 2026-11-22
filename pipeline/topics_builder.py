"""Algorithmic dynamic topic clustering, 4-stage lifecycle state machine, and historical topic archive builder."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pipeline.dedup import (
    entities_conflict,
    extract_tokens,
    get_publisher_family,
    is_omnibus_digest_title,
    smart_truncate,
    strip_raw_urls_and_domain_tails,
    title_similarity,
)
from pipeline.entities import ENTITY_BY_ID, match_entities_with_reasons
from pipeline.manifest import load_json_if_exists
from pipeline.time_utils import now_shanghai, parse_iso_datetime, to_iso_shanghai

LIFECYCLE_LABELS = {
    "starting": "刚开始",
    "ongoing": "进行中",
    "ending_soon": "即将完结",
    "ended": "已完结",
}

_FLUFF_NOISE_RE = re.compile(
    r"(?:围巾|座驾|同框|开了个玩笑|人字拖|戒了|全妆|三角梅|打卡|演唱会|剧场版|小雪节气|帮信罪|刑拘|midterm\s*fluff|"
    r"首支单曲|斗破苍穹|今日小雪|大雪节气|立冬节气|冬至节气)",
    re.I,
)
_TRIVIAL_TOPIC_RE = re.compile(
    r"(?:手环|出货|车漆|预售|实车上路|无伪装|主控|单曲|剧场版|小雪|节气|赴.{1,8}调研|调研.{1,10}工作|"
    r"营销公司|新配色|配色|跑分|蓝牙耳机|智能手表|换电|打卡|促销|买赠|限时优惠|首款.{0,12}SSD)",
    re.I,
)
_CONCLUDED_SIGNAL_RE = re.compile(
    r"(?:圆满闭幕|正式闭幕|落下帷幕|闭幕|落幕|圆满结束|收官|峰会成果|深圳展望|挂牌上市后|IPO后|上市次日|"
    r"首日.{0,6}收|次日股价|首周定价|顺利回收|圆满完成|签署联合声明|已正式退市|宣布取消|"
    r"签署.{0,12}协定|正式签署|自贸协定|达成协议|三大象征意义|照片并肯定|返美后)",
    re.I,
)
_WINDING_DOWN_SIGNAL_RE = re.compile(
    r"(?:加时磋商|第二天加时|进入.{0,4}加时|最终草案|终稿表决|最后阶段|即将闭幕|进入尾声|收官阶段|继续延期|被迫.{0,2}加时|拖堂)",
    re.I,
)
_APEC_STRAY_RE = re.compile(
    r"(?:英伟达|nvidia|黄仁勋|alice\s*huang|走私|数据中心.*(?:重税|巨税|关税)|公海条约|加州.*调查)",
    re.I,
)
_GTA_GAMING_RE = re.compile(r"(?:gta\s*6|gta6|侠盗猎车手|文娱史上最成功发售)", re.I)
_SOVEREIGN_BOND_RE = re.compile(r"(?:主权债券|发行.*国债|国债发行)", re.I)
_HOTLIST_NO_TIME_SOURCES = {"zhihu", "baidu", "weibo", "toutiao", "tencent-hot", "tieba", "douyin", "hupu", "coolapk"}
_BROAD_CLUSTER_ENTITIES = {
    "ent_ai_infra_tools",
    "ent_us_tariffs_trade",
    "ent_geopolitics_energy",
}
_THEATER_RU_UA_RE = re.compile(
    r"(?:俄乌|乌克兰|俄罗斯|基辅|泽连斯基|莫斯科|克里米亚|扎波罗热|敖德萨|基利亚|顿巴斯|波罗的海|芬兰湾|sparta\s*ii|北约|波兰|普京|330千伏|普拉沃贝雷日纳|俄罗斯军队|俄军)",
    re.I,
)
_THEATER_US_IRAN_RE = re.compile(
    r"(?:美伊|伊朗|霍尔木兹|波斯湾|巴林|美军基地|中央司令部|centcom|封锁.{0,8}伊朗|革命卫队|阿联酋|f-35|以色列|黎巴嫩|也门|胡塞|中东|塔斯尼姆)",
    re.I,
)
_MATH_RIEMANN_RE = re.compile(r"(?:黎曼猜想|riemann|数论|素数|圣杯.{0,8}数学|数学证明|数学家.{0,12}lean)", re.I)
_TENSORLEAN_GPU_RE = re.compile(r"(?:tensorlean|certik|哥伦比亚大学|gpu\s*内核|deepseek.{0,10}内核|flashattention|cuda)", re.I)
_FED_MACRO_RE = re.compile(r"(?:美联储|fomc|鲍威尔|利率路径|联邦基金|降息|加息|黄金|金价|美元走强)", re.I)
_MILITARY_BLOCKADE_RE = re.compile(
    r"(?:中央司令部|centcom|封锁|革命卫队|无人机袭击|美军基地|战斗机|空袭|导弹|触雷|"
    r"伊朗.*(?:袭击|打击)|发动.*(?:袭击|打击)|军事资产|美军部队|中东.*袭击|对伊朗.*打击|新一轮袭击)",
    re.I,
)
_ACTIVE_UPCOMING_SIGNAL_RE = re.compile(
    r"(?:全区合练|合练|准备发射|即将发射|发射在即|加时|磋商|谈判继续|继续谈判|草案|酝酿|推进中|即将推出|开放测试|筹备|待公布)",
    re.I,
)
_AGENCY_ONLY_RE = re.compile(
    r"^(?:据)?(?:伊朗|俄罗斯|美国|法国|德国|日本|韩国|以色列|土耳其)?[^，,：:]{2,18}(?:通讯社|社|电台|电视台|日报|时报|新闻|消息|外媒|媒体|电)(?:报道|消息|称)?$"
)
_AGGREGATOR_PREFIX_RE = re.compile(
    r"^(?:凤凰网|央视网|央视新闻|新华网|新华社|新浪财经|新浪科技|腾讯新闻|网易新闻|界面新闻|澎湃新闻|财联社|每日经济新闻|第一财经|21世纪经济报道|红星新闻|极目新闻)\s*(?:[丨|：:]\s*)+"
)
_BROAD_COMPANY_ENTITIES = {
    "ent_huawei",
    "ent_apple",
    "ent_xiaomi",
    "ent_bytedance",
    "ent_tencent",
    "ent_alibaba",
    "ent_google",
    "ent_microsoft",
    "ent_amazon",
    "ent_meta",
    "ent_tesla",
    "ent_byd",
    "ent_baidu",
    "ent_jd",
}
_NON_STORY_ANCHOR_ENTITIES = _BROAD_CLUSTER_ENTITIES | _BROAD_COMPANY_ENTITIES

_GENERIC_NEWS_TOKS = {
    "发布", "官方", "最新", "公司", "回应", "宣布", "推出", "增长", "同比", "亿元", "全球",
    "中国", "美国", "市场", "今日", "消息", "表示", "曝光", "预计", "正式", "全新", "升级",
    "支持", "首款", "首批", "累计", "突破", "实现", "启动", "推进", "工作", "合作", "项目",
    "汽车", "手机", "芯片", "技术", "产品", "系统", "服务", "行业", "企业", "报道", "称",
    "日电", "发生", "完成", "合同", "方面", "目前", "可能", "正在", "首次", "今年", "去年",
    "明年", "全国", "国际", "媒体", "显示", "时间", "问题", "情况", "影响", "进行", "开展",
    "通过", "成为", "重要", "持续", "引发", "关注", "继续", "地区", "机构", "部门", "相关",
    "the", "and", "for", "with", "from", "new", "says", "after", "over", "into",
}

_WIRE_DATELINE_RE = re.compile(
    r"^(?:【[^】]{1,24}】\s*|"
    r"(?:财联社|新华网|新华社|央视新闻|人民网|金十数据|法布财经|格隆汇)\s*(?:\d{1,2}月\d{1,2}日)?电[，,：:\s]*(?:据[^，,：:]{2,26}(?:消息|报道|称)[，,：:\s]*)?|"
    r"(?:据)?(?:俄罗斯卫星网|俄罗斯卫星通讯社|卫星通讯社|俄新社|伊朗塔斯尼姆通讯社|塔斯尼姆通讯社|路透社|彭博社|法新社|美联社|韩联社|共同社|央视新闻|新华社|中国地震台网(?:正式测定)?)(?:报道|消息|称)?\s*[：:，,\s]*|"
    r"\d{1,2}月\d{1,2}日\d{1,2}时(?:\d{1,2}分)?[，,\s]*(?:在)?|"
    r"(?:外电|快讯|报道称|独家|最新|消息称|外媒称|官方|欧洲地中海地震中心|美国地质调查局(?:（USGS）)?)\s*[:：]\s*)"
)


def _theater_conflict(ta: str, tb: str) -> bool:
    ru_a, ir_a = bool(_THEATER_RU_UA_RE.search(ta)), bool(_THEATER_US_IRAN_RE.search(ta))
    ru_b, ir_b = bool(_THEATER_RU_UA_RE.search(tb)), bool(_THEATER_US_IRAN_RE.search(tb))
    return (ru_a and not ir_a and ir_b and not ru_b) or (ir_a and not ru_a and ru_b and not ir_b)


def _subtopic_conflict(ta: str, tb: str) -> bool:
    """Prevent conflating Russia-Ukraine vs US-Iran, Riemann pure-math vs TensorLean GPU kernels, Fed policy vs military ops, GTA6 vs sovereign bonds, or APEC vs stray NVIDIA/UN articles."""
    if _theater_conflict(ta, tb):
        return True
    riem_a, gpu_a = bool(_MATH_RIEMANN_RE.search(ta)), bool(_TENSORLEAN_GPU_RE.search(ta))
    riem_b, gpu_b = bool(_MATH_RIEMANN_RE.search(tb)), bool(_TENSORLEAN_GPU_RE.search(tb))
    if (riem_a and not gpu_a and gpu_b and not riem_b) or (gpu_a and not riem_a and riem_b and not gpu_b):
        return True
    fed_a, mil_a = bool(_FED_MACRO_RE.search(ta)), bool(_MILITARY_BLOCKADE_RE.search(ta))
    fed_b, mil_b = bool(_FED_MACRO_RE.search(tb)), bool(_MILITARY_BLOCKADE_RE.search(tb))
    if (fed_a and not mil_a and mil_b and not fed_b) or (mil_a and not fed_a and fed_b and not mil_b):
        return True
    gta_a, bond_a = bool(_GTA_GAMING_RE.search(ta)), bool(_SOVEREIGN_BOND_RE.search(ta))
    gta_b, bond_b = bool(_GTA_GAMING_RE.search(tb)), bool(_SOVEREIGN_BOND_RE.search(tb))
    if (gta_a and not bond_a and bond_b and not gta_b) or (bond_a and not gta_a and gta_b and not bond_b):
        return True
    apec_re = re.compile(r"(?:apec|深圳峰会|中美元首)", re.I)
    apec_a = bool(apec_re.search(ta))
    apec_b = bool(apec_re.search(tb))
    stray_a = bool(_APEC_STRAY_RE.search(ta)) and not apec_a
    stray_b = bool(_APEC_STRAY_RE.search(tb)) and not apec_b
    if (apec_a and stray_b) or (apec_b and stray_a):
        return True
    return False


def _is_minor_quake(text: str) -> bool:
    """Filter out routine minor earthquakes (<5.0 magnitude with no casualties/damage) from topics."""
    t = str(text or "")
    if "地震" not in t:
        return False
    if any(k in t for k in ("遇难", "伤亡", "死亡", "失联", "倒塌", "重灾", "救灾响应", "海啸预警")):
        return False
    m = re.search(r"(\d+(?:\.\d+)?)\s*级", t)
    if m:
        try:
            mag = float(m.group(1))
            return mag < 5.0
        except ValueError:
            pass
    return False


def _clean_node_summary(raw_summary: str, title: str = "", max_len: int = 160) -> str:
    s = strip_raw_urls_and_domain_tails(str(raw_summary or "").strip())
    for _ in range(3):
        s2 = _AGGREGATOR_PREFIX_RE.sub("", s).strip()
        s2 = _WIRE_DATELINE_RE.sub("", s2).strip()
        if s2 == s:
            break
        s = s2
    s = re.sub(r"\s+(?:凤凰网|央视网|新浪财经|腾讯新闻|网易新闻|澎湃新闻|界面新闻)\s*$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    s = smart_truncate(s, max_len)
    if not s or s == title:
        return ""
    return s

_CATEGORY_BADGE_MAP = {
    "global": "国际与地缘主线",
    "finance": "资本与宏观主线",
    "tech": "前沿科技主线",
    "general": "全网热点追踪",
}

_ENTITY_ALIAS_TOKEN_CACHE: Optional[Set[str]] = None


def _get_entity_alias_tokens() -> Set[str]:
    global _ENTITY_ALIAS_TOKEN_CACHE
    if _ENTITY_ALIAS_TOKEN_CACHE is not None:
        return _ENTITY_ALIAS_TOKEN_CACHE
    toks: Set[str] = set()
    for ent in ENTITY_BY_ID.values():
        toks.update(extract_tokens(ent.canonical_name))
        for al in ent.aliases or ():
            toks.update(extract_tokens(al))
    _ENTITY_ALIAS_TOKEN_CACHE = toks
    return toks


def _storyline_tokens(title: str) -> Set[str]:
    """Return event-specific tokens excluding generic filler, bare numbers, and conglomerate entity names."""
    alias_toks = _get_entity_alias_tokens()
    return {
        tok
        for tok in extract_tokens(title)
        if tok not in _GENERIC_NEWS_TOKS
        and tok not in alias_toks
        and not re.fullmatch(r"\d+(?:\.\d+)?%?", tok)
    }


def classify_itinerary_tag(title: str) -> str:
    t = str(title or "").lower()
    if any(k in t for k in ("闭幕", "落幕", "收官", "结束", "联合声明", "公报", "深圳展望")):
        return "阶段收束"
    if any(k in t for k in ("机场", "抵深", "抵达", "迎接", "下榻", "arrives", "tarmac")):
        return "抵访接待"
    if any(k in t for k in ("晚宴", "招待会", "同框", "握手", "banquet", "dinner")):
        return "高层互动"
    if any(k in t for k in ("三边", "三国", "trilateral", "双边", "会晤", "会谈", "talks", "bilateral")):
        return "高层会谈"
    if any(k in t for k in ("协议", "关税", "自贸", "合作", "演讲", "speech", "deal", "tariff", "trade")):
        return "经贸与声明"
    if any(k in t for k in ("回收", "星舰", "筷子", "发布", "上线", "推出", "ipo", "定价", "募资")):
        return "重大里程碑"
    return "最新进展"


def _normalize_node_timestamp(raw_ts: Any, fallback_dt: datetime) -> Tuple[Optional[str], Optional[datetime], str]:
    dt = parse_iso_datetime(raw_ts)
    if dt is not None:
        return to_iso_shanghai(dt), dt, "published"
    txt = str(raw_ts or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt):
        try:
            d_obj = datetime.strptime(txt, "%Y-%m-%d").replace(tzinfo=fallback_dt.tzinfo, hour=12)
            return to_iso_shanghai(d_obj), d_obj, "estimated"
        except Exception:
            pass
    return None, None, "estimated"


def _clean_publisher_name(raw_name: Any, title: str, url: str) -> str:
    from pipeline.verifier import _clean_source_display_name

    return _clean_source_display_name(raw_name, title, url)


def _node_from_event(ev: dict, now_dt: datetime) -> Optional[dict]:
    title = strip_raw_urls_and_domain_tails(str(ev.get("title") or "").strip())
    if not title or is_omnibus_digest_title(title) or _FLUFF_NOISE_RE.search(title) or _is_minor_quake(title):
        return None
    srcs = ev.get("sources") if isinstance(ev.get("sources"), list) else []
    src0 = srcs[0] if srcs else {}
    url = str(src0.get("url") or "").strip()
    pub_name = _clean_publisher_name(
        src0.get("publisher_name") or src0.get("source_name"),
        str(src0.get("title") or title),
        url,
    )
    raw_ts = ev.get("latest_reported_at") or ev.get("first_reported_at") or src0.get("published_at")
    ts_iso, ts_dt, time_source = _normalize_node_timestamp(raw_ts, now_dt)
    if ts_iso is None:
        raw_fallback = ev.get("fetched_at") or ev.get("latest_fact_update_at")
        ts_iso, ts_dt, _ = _normalize_node_timestamp(raw_fallback, now_dt)
        time_source = "estimated"
    if not ts_iso:
        ts_iso = to_iso_shanghai(now_dt)
        ts_dt = now_dt
        time_source = "estimated"
    summary = _clean_node_summary(str(ev.get("fact_summary") or ev.get("summary") or ""), title, 160)
    eids = list(ev.get("entity_ids") or [])
    if not eids:
        eids = [m["entity_id"] for m in match_entities_with_reasons(f"{title} {summary[:80]}")][:4]
    pfams = {
        str(s.get("publisher_family") or get_publisher_family(str(s.get("source_id") or ""), str(s.get("url") or "")))
        for s in srcs
        if not s.get("is_reprint_copy")
    } or {pub_name}
    return {
        "time": ts_iso,
        "_ts_dt": ts_dt,
        "time_source": time_source,
        "stage_tag": classify_itinerary_tag(title),
        "title": title,
        "title_en": str(ev.get("title_en") or ""),
        "summary": summary,
        "summary_en": str(ev.get("summary_en") or ""),
        "source_name": pub_name,
        "publisher_name": pub_name,
        "url": url or None,
        "event_id": ev.get("event_id"),
        "category": ev.get("category") or "global",
        "entity_ids": eids,
        "importance": ev.get("importance") or "normal",
        "publisher_families": pfams,
        "source_count": max(1, int(ev.get("independent_publisher_count") or len(pfams))),
    }


def _node_from_raw_item(it: dict, cat: str, now_dt: datetime) -> Optional[dict]:
    sid = str(it.get("source_id") or "").lower()
    if sid in _HOTLIST_NO_TIME_SOURCES or it.get("source_kind") in {"market_ticker", "discussion"}:
        return None
    raw_pub = it.get("published_at")
    if not raw_pub:
        return None
    ts_iso, ts_dt, time_source = _normalize_node_timestamp(raw_pub, now_dt)
    if ts_iso is None or ts_dt is None or time_source != "published":
        return None
    if (now_dt - ts_dt) > timedelta(hours=96):
        return None
    title = strip_raw_urls_and_domain_tails(str(it.get("title") or "").strip())
    url = str(it.get("canonical_url") or it.get("url") or "").strip()
    if not title or not url or len(title) < 6 or is_omnibus_digest_title(title) or _FLUFF_NOISE_RE.search(title) or _is_minor_quake(title):
        return None
    pub_name = _clean_publisher_name(it.get("publisher_name") or it.get("source_name") or sid, title, url)
    summary = _clean_node_summary(str(it.get("excerpt") or ""), title, 140)
    eids = list(it.get("entity_ids") or [])
    if not eids:
        eids = [m["entity_id"] for m in match_entities_with_reasons(f"{title} {summary[:80]}")][:4]
    pfam = str(it.get("publisher_family") or get_publisher_family(sid, url) or pub_name)
    return {
        "time": ts_iso,
        "_ts_dt": ts_dt,
        "time_source": "published",
        "stage_tag": classify_itinerary_tag(title),
        "title": title,
        "summary": summary,
        "source_name": pub_name,
        "publisher_name": pub_name,
        "url": url,
        "event_id": None,
        "category": it.get("category") or cat or "global",
        "entity_ids": eids,
        "importance": "normal",
        "publisher_families": {pfam},
        "source_count": 1,
    }


def _clean_stored_nodes(raw_nodes: List[dict], *, keep_hotlist_if_scarce: bool = False) -> List[dict]:
    """Normalize persisted timeline nodes while preserving genuine restored timelines."""
    filtered: List[dict] = []
    all_normalized: List[dict] = []
    for old_n in raw_nodes or []:
        if not isinstance(old_n, dict):
            continue
        nt = strip_raw_urls_and_domain_tails(str(old_n.get("title") or "").strip())
        if not nt or _FLUFF_NOISE_RE.search(nt) or is_omnibus_digest_title(nt) or _is_minor_quake(nt):
            continue
        n_copy = dict(old_n)
        n_copy["title"] = nt
        if n_copy.get("summary"):
            n_copy["summary"] = _clean_node_summary(str(n_copy.get("summary") or ""), nt, 160)
        pub = _clean_publisher_name(n_copy.get("publisher_name") or n_copy.get("source_name"), nt, str(n_copy.get("url") or ""))
        n_copy["publisher_name"] = pub
        n_copy["source_name"] = pub
        n_copy.setdefault("time_source", "published" if n_copy.get("time") else "estimated")
        if not n_copy.get("stage_tag"):
            n_copy["stage_tag"] = classify_itinerary_tag(nt)
        all_normalized.append(n_copy)
        src_low = str(old_n.get("source_name") or old_n.get("publisher_name") or "").lower()
        is_hot = any(h in src_low for h in ("知乎", "百度热搜", "微博", "今日头条")) and not old_n.get("event_id")
        if not is_hot:
            filtered.append(n_copy)
    if keep_hotlist_if_scarce and len(filtered) < 4 and len(all_normalized) >= len(filtered):
        return all_normalized
    return filtered


def _dedupe_timeline_nodes(nodes: List[dict], *, max_nodes: int = 60) -> List[dict]:
    """Deduplicate nodes by URL/title similarity, keeping the richest version, and return newest-first."""
    sorted_cands = sorted(
        nodes,
        key=lambda n: (
            1 if n.get("event_id") else 0,
            1 if n.get("time_source") == "published" else 0,
            str(n.get("time") or ""),
        ),
        reverse=True,
    )
    kept: List[dict] = []
    seen_urls: Set[str] = set()
    for n in sorted_cands:
        t = str(n.get("title") or "").strip()
        u = str(n.get("url") or "").strip()
        if not t or _FLUFF_NOISE_RE.search(t) or is_omnibus_digest_title(t):
            continue
        if u and u in seen_urls:
            continue
        if any(title_similarity(t, str(prev.get("title") or "")) >= 0.54 for prev in kept):
            continue
        if u:
            seen_urls.add(u)
        clean_n = {
            k: v
            for k, v in n.items()
            if not k.startswith("_") and k not in {"publisher_families", "entity_ids", "importance", "source_count", "category"}
        }
        kept.append(clean_n)
        if len(kept) >= max_nodes:
            break
    kept.sort(key=lambda n: str(n.get("time") or ""), reverse=True)
    return kept


def _safe_clip_headline(text: str, max_len: int = 42) -> str:
    txt = str(text or "").strip().rstrip("。！？!?，；;：:…‘“(")
    # Strip trailing incomplete relative clauses or dangling attribution fragments
    txt = re.sub(r"[，,]\s*(?:该设施|该项目|该系统|该公司|相关报道|称受保护|并更新|同时称)[^，,。]{0,16}$", "", txt).strip()
    if len(txt) > max_len:
        # Prefer splitting at a clean Chinese/English clause delimiter so NO word/number/unit is chopped in half
        # Skip splitting right after a pure quoted slogan (e.g. “...”！GTA 6...) that leaves the subject orphaned
        def _is_orphaned_quote(prefix: str) -> bool:
            ps = prefix.strip()
            return ps.startswith(("“", "「")) and ps.endswith(("”", "」"))

        clause_breaks = [
            m.start()
            for m in re.finditer(r"[，,；;：:。！？!?——|｜]", txt)
            if 12 <= m.start() <= max_len + 4 and not _is_orphaned_quote(txt[: m.start()])
        ]
        if clause_breaks:
            txt = txt[: clause_breaks[-1]].strip()
        elif any(k in txt for k in ("《", "GTA", "！”", "！」")) and len(txt) <= max(max_len + 12, 54):
            # Keep the full subject clause after the closing quote when total length is modest
            pass
        else:
            cut = max_len
            while cut < len(txt) and cut < max_len + 8 and (
                (txt[cut].isascii() and (txt[cut].isalnum() or txt[cut] in ".%_-"))
                or txt[cut] in "米伏吨万亿%号级市省国人"
            ):
                cut += 1
            sub = txt[:cut]
            if cut < len(txt) and txt[cut].isascii() and txt[cut].isalnum():
                sub = re.sub(r"[A-Za-z0-9._-]+$", "", sub)
            if sum(1 for c in sub if "\u4e00" <= c <= "\u9fff") < 4:
                ws = sub.rfind(" ")
                if ws >= 12:
                    sub = sub[:ws]
            sub = re.sub(r"\d+(?:[.．]\d*)?[千百十]?$", "", sub).strip()
            txt = sub
    # Strip any unclosed opening paren/quote left behind
    if txt.count("（") > txt.count("）"):
        txt = re.sub(r"（[^）]*$", "", txt)
    if txt.count("(") > txt.count(")"):
        txt = re.sub(r"\([^)]*$", "", txt)
    if txt.count("“") > txt.count("”"):
        txt = re.sub(r"“[^”]*$", "", txt)
    if txt.count("「") > txt.count("」"):
        txt = re.sub(r"「[^」]*$", "", txt)
    if txt.count("《") > txt.count("》"):
        txt = re.sub(r"《[^》]*$", "", txt)
    # Repair percent drops left bare like "重挫10.02"
    txt = re.sub(r"(?:重挫|暴跌|大跌|跌超|上涨|暴涨|飙升|涨超)\s*\d+(?:\.\d+)?$", lambda m: f"{m.group(0)}%", txt)
    cleaned = txt.rstrip("，；：、的在给于与向和‘“「《(- ").rstrip("。！？!?….")
    if re.fullmatch(r"[\d.\s%+-]+", cleaned):
        return ""
    return cleaned


def _clean_headline_phrase(raw_title: str) -> str:
    txt = strip_raw_urls_and_domain_tails(str(raw_title or "").strip())
    for _ in range(3):
        stripped = _WIRE_DATELINE_RE.sub("", txt).strip()
        stripped = _AGGREGATOR_PREFIX_RE.sub("", stripped).strip()
        if stripped == txt:
            break
        txt = stripped
    # If leading attribution segment ("据XX社：...") precedes colon, keep only the actual fact clause
    m_colon = re.match(r"^([^：:]{2,26})[：:](.+)$", txt)
    if m_colon:
        lhs, rhs = m_colon.group(1).strip(), m_colon.group(2).strip()
        if (_AGENCY_ONLY_RE.match(lhs) or lhs.startswith("据") or lhs.endswith(("电", "消息", "报道", "称"))) and len(rhs) >= 8:
            txt = rhs
    txt = txt.rstrip("。！？!?，；;：:….")
    if len(txt) > 38:
        parts = [p.strip(" ，；：") for p in re.split(r"[；;。]|(?<=\D)[:：](?=\D)", txt) if p.strip()]
        if parts and 10 <= len(parts[0]) <= 40 and not _AGENCY_ONLY_RE.match(parts[0]):
            candidate = f"{parts[0]}：{parts[1]}" if len(parts) > 1 and len(parts[0]) + len(parts[1]) <= 40 else parts[0]
            txt = candidate
        elif len(parts) > 1 and _AGENCY_ONLY_RE.match(parts[0]) and len(parts[1]) >= 8:
            txt = parts[1]
        elif "，" in txt:
            segs = [s.strip() for s in txt.split("，") if s.strip()]
            acc = segs[0]
            for nxt_s in segs[1:]:
                if len(acc) + len(nxt_s) + 1 <= 40 and not nxt_s.startswith(("该", "称", "并")):
                    acc = f"{acc}，{nxt_s}"
                else:
                    break
            if len(acc) >= 10 and not _AGENCY_ONLY_RE.match(acc):
                txt = acc
    clipped = _safe_clip_headline(txt, max_len=42)
    return clipped if len(clipped) >= 6 else _safe_clip_headline(strip_raw_urls_and_domain_tails(str(raw_title or "").strip()), max_len=42)


def _match_canonical_topic_theme(joined: str) -> Optional[Tuple[str, str, str]]:
    """Recognize major news themes cleanly so topics get crisp titles and never split into duplicates or cross-contaminate."""
    j = joined.lower()
    if any(k in j for k in ("apec", "中美元首", "习特会", "深圳峰会")) or (
        any(k in j for k in ("特朗普", "trump")) and any(k in j for k in ("访华", "习近平", "深圳"))
    ):
        return "topic_apec_trump_china", "特朗普访华与 2026 深圳 APEC 峰会", "国际主线专题"
    if any(k in j for k in ("anthropic",)) and any(k in j for k in ("ipo", "上市", "募资", "破发", "发行价")):
        return "topic_anthropic_ipo", "Anthropic 超级 IPO 与一级市场定价检验", "资本与宏观主线"
    if ("黄仁勋" in j or "英伟达" in j or "nvidia" in j) and any(k in j for k in ("出口管制", "芯片出口", "辞任", "过渡", "重税", "8-k", "colette")):
        return "topic_nvidia_export_gov", "英伟达业绩、出口管制与管理层过渡", "前沿科技主线"
    if ("美联储" in j or "fomc" in j) and any(k in j for k in ("加息", "利率", "金价", "黄金", "降息", "纪要")) and not _MILITARY_BLOCKADE_RE.search(j):
        return "topic_fed_gold_macro", "美联储利率路径、美元走强与黄金大宗异动", "资本与宏观主线"
    if any(k in j for k in ("spacex", "星舰")) and any(k in j for k in ("回收", "筷子", "xai", "缺钱", "马斯克")):
        return "topic_spacex_musk", "SpaceX 星舰回收、xAI 与马斯克商业生态", "前沿科技主线"
    if any(k in j for k in ("神舟二十四", "神舟24")) and any(k in j for k in ("发射", "航天员", "酒泉", "出征", "空间站", "合练")):
        return "topic_shenzhou_24", "神舟二十四号载人航天全区合练与发射任务", "前沿科技主线"
    if "雅安" in j and "地震" in j:
        return "topic_yaan_quake", "四川雅安地震震情与应急响应进展", "全网热点追踪"
    if any(k in j for k in ("cop31", "联合国气候变化大会", "气候大会", "安塔利亚")):
        return "topic_cop31_climate", "COP31 安塔利亚气候大会加时磋商与化石燃料案文博弈", "国际与地缘主线"
    if _THEATER_RU_UA_RE.search(j) and any(k in j for k in ("袭击", "打击", "爆炸", "电网", "变电站", "停电", "港口", "船", "导弹", "恢复", "和平", "330千伏")):
        return "topic_ru_ua_front", "俄乌战局：能源电网、黑海港口及波罗的海俄船动态", "国际与地缘主线"
    if _THEATER_US_IRAN_RE.search(j) and any(k in j for k in ("基地", "无人机", "触雷", "谈判", "外交官", "袭击", "封锁", "战机", "海峡")):
        return "topic_us_iran_gulf", "美伊中东军事冲突：巴林美军基地遇袭与霍尔木兹海峡封锁", "国际与地缘主线"
    if _TENSORLEAN_GPU_RE.search(j):
        return "topic_tensorlean_gpu", "哥伦比亚大学与 CertiK 发布 TensorLean 验证 GPU 内核", "前沿科技主线"
    if _MATH_RIEMANN_RE.search(j):
        return "topic_riemann_lean", "Lean 社区探索黎曼猜想 AI 形式化验证研究", "前沿科技主线"
    if any(k in j for k in ("fsd v15", "fsd", "完全自动驾驶")) and any(k in j for k in ("特斯拉", "tesla", "中国", "欧洲", "robotaxi", "cybercab")):
        return "topic_tesla_fsd_v15", "特斯拉 FSD v15 全自动驾驶与 Cybercab 全球推进", "前沿科技主线"
    if "反蒸馏" in j or ("蒸馏" in j and any(k in j for k in ("openai", "anthropic", "google", "thinking"))):
        return "topic_ai_anti_distill", "大模型反蒸馏技术攻防与隐私合规争议", "前沿科技主线"
    if any(k in j for k in ("欧盟", "欧洲")) and any(k in j for k in ("印尼", "印度尼西亚")) and any(k in j for k in ("贸易协定", "自贸")):
        return "topic_eu_indonesia_fta", "欧盟与印度尼西亚签署双边自由贸易协定", "国际与地缘主线"
    if any(k in j for k in ("欧盟", "欧洲议会")) and any(k in j for k in ("多年期预算", "削减预算", "预算")):
        return "topic_eu_budget_trade", "欧盟多年期财政预算博弈与财政框架争议", "国际与地缘主线"
    if "ink" in j or "inkling" in j or "thinking machines" in j:
        return "topic_thinking_machines_inkling", "Thinking Machines 发布 Inkling 系列高效推理模型", "前沿科技主线"
    if _GTA_GAMING_RE.search(j):
        return "topic_gta6_launch", "《GTA 6》发行首日销售额破纪录：“文娱史上最成功发售”", "全网热点追踪"
    if "amazon" in j or ("亚马逊" in j and "相框" in j):
        return "topic_amazon_devices", "亚马逊发布家用智能相框与黑色星期五硬件促销", "前沿科技主线"
    return None


def _derive_topic_entity_ids(deduped_tl: List[dict], final_title: str, is_curated: bool = False) -> List[str]:
    """Attach ONLY entities strictly grounded in this topic's timeline titles (>=2 node hits or headline hit)."""
    counts: Dict[str, int] = {}
    for nd in deduped_tl:
        nt = str(nd.get("title") or "")
        for m in match_entities_with_reasons(nt):
            eid = str(m["entity_id"])
            counts[eid] = counts.get(eid, 0) + 1
    title_hits = {str(m["entity_id"]) for m in match_entities_with_reasons(final_title)}
    min_hits = 1 if is_curated and len(deduped_tl) <= 3 else 2
    verified = [
        eid
        for eid, cnt in sorted(counts.items(), key=lambda kv: (kv[0] in title_hits, kv[1]), reverse=True)
        if eid in title_hits or cnt >= min_hits
    ]
    return verified[:6]


def _match_region_tag(text_low: str) -> Optional[Tuple[str, str]]:
    if re.search(r"cop31|气候大会|气候变化大会|安塔利亚|联合国气候|全球|gta\s*6|gta6|opec", text_low, re.I):
        return "global", "全球"
    if re.search(r"apec|中美元首|习特会", text_low, re.I) or ("中美" in text_low and any(k in text_low for k in ("峰会", "会晤", "深圳", "访华"))):
        return "china", "中美·亚太"
    if any(k in text_low for k in ("神舟", "北京", "深圳", "广州", "上海", "中国", "中国人民银行", "人大", "政协", "雅安", "华为", "比亚迪", "方程豹", "腾讯", "阿里", "deepseek", "千问")):
        return "china", "中国"
    if any(k in text_low for k in ("美联储", "fomc", "anthropic", "openai", "英伟达", "nvidia", "特斯拉", "tesla", "spacex", "谷歌", "google", "微软", "亚马逊", "amazon", "thinking machines", "lean", "黎曼", "vmware", "美国", "纳指")):
        return "us", "美国"
    if _THEATER_US_IRAN_RE.search(text_low) or any(k in text_low for k in ("霍尔木兹", "中东", "沙特", "阿联酋", "巴林", "以色列", "伊朗")):
        return "middle_east", "中东"
    if _THEATER_RU_UA_RE.search(text_low) or any(k in text_low for k in ("欧盟", "欧洲议会", "欧洲", "英国", "波兰", "芬兰湾", "俄罗斯", "乌克兰")):
        return "europe_ru_ua", "欧洲·俄乌"
    if any(k in text_low for k in ("泰国", "印尼", "印度尼西亚", "韩国", "日本", "海力士", "软银", "东南亚")):
        return "apac", "亚太"
    return None


def _classify_topic_region_and_orgs(
    title: str,
    nodes: List[dict],
    entity_ids: List[str],
    category: str,
) -> Tuple[str, str, List[str], str]:
    """Return structured (region, region_label, primary_orgs, domain_tag) for UI categorization."""
    title_low = str(title or "").lower()
    node_titles_low = [str(n.get("title") or "").lower() for n in nodes[:8]]
    joined_low = f"{title_low} " + " ".join(node_titles_low)

    matched_reg = _match_region_tag(title_low) or _match_region_tag(" ".join(node_titles_low[:6]))
    if matched_reg:
        region, region_label = matched_reg
    else:
        region, region_label = "global", "全球"

    orgs: List[str] = []
    # Explicit keyword checks against topic title first, requiring >=2 node hits for body-only mentions
    org_patterns = [
        ("anthropic", "Anthropic"),
        ("openai", "OpenAI"),
        ("英伟达|nvidia", "英伟达"),
        ("特斯拉|tesla", "特斯拉"),
        ("spacex", "SpaceX"),
        ("google|谷歌|deepmind", "Google"),
        ("微软|microsoft", "微软"),
        ("亚马逊|amazon", "亚马逊"),
        ("美联储|fomc", "美联储"),
        ("欧洲议会|欧盟", "欧盟"),
        ("神舟|中国航天", "中国航天"),
        ("cop31|unfccc|气候变化大会|气候公约", "联合国 UNFCCC"),
        ("apec", "APEC 峰会"),
        (r"gta\s*6|gta6|rockstar|r星", "Rockstar / Take-Two"),
        ("tensorlean|certik", "CertiK / 哥伦比亚大学"),
        ("lean|黎曼", "Lean 社区"),
        ("thinking machines", "Thinking Machines"),
        ("比亚迪|方程豹", "比亚迪"),
        ("华为|huawei", "华为"),
        ("腾讯|tencent", "腾讯"),
        ("阿里巴巴|通义|qwen", "阿里巴巴"),
        ("deepseek", "DeepSeek"),
    ]
    for pat, label in org_patterns:
        in_title = bool(re.search(pat, title_low, re.I))
        node_hits = sum(1 for nt_l in node_titles_low if re.search(pat, nt_l, re.I))
        if (in_title or node_hits >= 2) and label not in orgs:
            orgs.append(label)
        if len(orgs) >= 2:
            break
    if not orgs:
        for eid in entity_ids[:2]:
            ed = ENTITY_BY_ID.get(eid)
            if ed:
                short_name = re.sub(r"\s*\([^)]+\)\s*", "", ed.canonical_name).split("/")[0].strip()
                if short_name and short_name not in orgs:
                    orgs.append(short_name)

    if any(k in joined_low for k in ("战", "袭击", "导弹", "封锁", "峰会", "会晤", "外交", "协定", "cop31", "预算")):
        domain_tag = "地缘与外交"
    elif any(k in joined_low for k in ("美联储", "ipo", "利率", "黄金", "金价", "美元", "比特币", "纳指", "稀土")):
        domain_tag = "宏观与金融"
    elif any(k in joined_low for k in ("神舟", "航天", "发射", "卫星", "星舰")):
        domain_tag = "航空航天"
    elif category == "tech" or any(k in joined_low for k in ("ai", "模型", "gpu", "fsd", "lean", "算力", "芯片", "gta")):
        domain_tag = "AI 与科技"
    else:
        domain_tag = "全球焦点"
    return region, region_label, orgs, domain_tag


def _infer_topic_category(nodes: List[dict], title: str, fallback_cat: str) -> str:
    low = f"{title} " + " ".join(str(n.get("title") or "") for n in nodes[:4]).lower()
    if any(k in low for k in ("地震", "暴雨", "台风", "救援")):
        return "general"
    if any(k in low for k in ("战机", "导弹", "空袭", "俄军", "乌军", "美伊", "霍尔木兹", "伊朗", "克里米亚", "扎波罗热", "芬兰湾", "cop31", "外交", "贸易协定", "多年期预算")):
        return "global"
    if any(k in low for k in ("神舟", "航天", "fsd", "gpu", "tensorlean", "lean", "黎曼", "anthropic", "openai", "大模型", "ai", "芯片")) and "ipo" not in low:
        return "tech"
    if any(k in low for k in ("ipo", "破发", "美联储", "利率", "金价", "纳指", "财报", "募资")):
        return "finance"
    return fallback_cat or "global"


def _infer_cluster_topic_id(nodes: List[dict], eids: Set[str], category: str) -> str:
    joined = " ".join(str(n.get("title") or "") for n in nodes[:8])
    canon = _match_canonical_topic_theme(joined)
    if canon:
        return canon[0]
    core_eids = sorted(e for e in eids if e not in _NON_STORY_ANCHOR_ENTITIES)[:2]
    story_toks = sorted(_storyline_tokens(" ".join(str(n.get("title") or "") for n in nodes[:4])))[:4]
    if core_eids:
        sig = f"{category}:{'+'.join(core_eids)}:{'_'.join(story_toks[:2])}"
    else:
        sig = f"{category}:{'_'.join(story_toks)}"
    digest = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:10]
    return f"topic_auto_{digest}"


def _build_cluster_headline(deduped_nodes: List[dict], eids: Set[str]) -> Tuple[str, str, str]:
    """Build concise storyline title (never truncated news sentence) + accurate post-dedup subtitle."""
    joined = " ".join(str(n.get("title") or "") for n in deduped_nodes[:8])
    canon = _match_canonical_topic_theme(joined)
    if canon:
        _, c_title, c_badge = canon
        pub_cnt = len({str(n.get("publisher_name") or n.get("source_name") or "") for n in deduped_nodes if n.get("source_name") or n.get("publisher_name")})
        return (
            c_title,
            f"覆盖 {max(1, pub_cnt)} 家信源、共 {len(deduped_nodes)} 条独立脉络进展",
            c_badge,
        )
    # Pick the consensus Chinese node (most coherent with cluster core) rather than arbitrary newest outlier
    if len(deduped_nodes) > 1:
        node_toks = [_storyline_tokens(str(n.get("title") or "")) for n in deduped_nodes[:12]]
        best_idx = 0
        best_score = (-1, -1)
        for idx, nd in enumerate(deduped_nodes[:12]):
            has_zh = 1 if any("\u4e00" <= c <= "\u9fff" for c in str(nd.get("title") or "")) else 0
            cohesion = sum(1 for jdx, toks_j in enumerate(node_toks) if jdx != idx and (len(node_toks[idx] & toks_j) >= 2 or title_similarity(str(nd.get("title") or ""), str(deduped_nodes[jdx].get("title") or "")) >= 0.25))
            sc = (has_zh, cohesion)
            if sc > best_score:
                best_score = sc
                best_idx = idx
        anchor_raw = str(deduped_nodes[best_idx].get("title") or "全网突发焦点追踪")
    else:
        anchor_raw = str((deduped_nodes[0] if deduped_nodes else {}).get("title") or "全网突发焦点追踪")
    anchor_phrase = _clean_headline_phrase(anchor_raw) or "全网突发焦点追踪"
    # Never blindly prepend unrelated entity prefixes (like 英伟达：Anthropic / 英伟达：亚马逊相框)
    title = _safe_clip_headline(anchor_phrase, max_len=42)
    pub_cnt = len({str(n.get("publisher_name") or n.get("source_name") or "") for n in deduped_nodes if n.get("source_name") or n.get("publisher_name")})
    subtitle = f"覆盖 {max(1, pub_cnt)} 家信源、共 {len(deduped_nodes)} 条独立脉络进展"
    cat = _infer_topic_category(deduped_nodes, title, str((deduped_nodes[0] if deduped_nodes else {}).get("category") or "global"))
    return title, subtitle, _CATEGORY_BADGE_MAP.get(cat, "全网焦点专题")


def _compute_lifecycle(
    nodes: List[dict],
    started_at_iso: str,
    now_dt: datetime,
    *,
    has_upcoming_catalyst: bool = False,
    topic_title: str = "",
    topic_id: str = "",
) -> Tuple[str, str, Optional[str]]:
    pub_dts = [parse_iso_datetime(n.get("time")) for n in nodes if n.get("time") and n.get("time_source") != "estimated"]
    pub_dts = [d for d in pub_dts if d is not None]
    if not pub_dts:
        all_dts = [parse_iso_datetime(n.get("time")) for n in nodes if n.get("time")]
        pub_dts = [d for d in all_dts if d is not None]
    last_dt = max(pub_dts) if pub_dts else now_dt
    first_node_dt = min(pub_dts) if pub_dts else now_dt
    start_dt = parse_iso_datetime(started_at_iso) or first_node_dt
    if first_node_dt < start_dt:
        start_dt = first_node_dt

    idle_hours = max(0.0, (now_dt - last_dt).total_seconds() / 3600.0)
    span_hours = max(0.0, (last_dt - start_dt).total_seconds() / 3600.0)
    age_hours = max(0.0, (now_dt - start_dt).total_seconds() / 3600.0)

    recent_titles = f"{topic_title} " + " ".join(str(n.get("title") or "") for n in nodes[:5])
    has_upcoming_active = bool(_ACTIVE_UPCOMING_SIGNAL_RE.search(recent_titles))
    has_winding_down = bool(_WINDING_DOWN_SIGNAL_RE.search(recent_titles))
    has_concluded = bool(_CONCLUDED_SIGNAL_RE.search(recent_titles)) and not (has_upcoming_active and idle_hours < 24.0)

    if (
        topic_id == "topic_apec_trump_china"
        and age_hours >= 42.0
        and any(k in recent_titles for k in ("闭幕", "落幕", "照片", "三大象征意义", "赞扬", "峰会成果", "返美"))
    ):
        return "ended", LIFECYCLE_LABELS["ended"], to_iso_shanghai(last_dt)

    if idle_hours >= 36.0 or (has_concluded and idle_hours >= 6.0 and not has_upcoming_catalyst) or (has_concluded and idle_hours >= 12.0):
        return "ended", LIFECYCLE_LABELS["ended"], to_iso_shanghai(last_dt)
    if has_winding_down or idle_hours >= 6.5 or (has_concluded and idle_hours >= 1.5):
        return "ending_soon", LIFECYCLE_LABELS["ending_soon"], None
    if len(nodes) <= 6 and age_hours <= 30.0 and span_hours <= 24.0:
        return "starting", LIFECYCLE_LABELS["starting"], None
    return "ongoing", LIFECYCLE_LABELS["ongoing"], None


def _matches_existing_topic(cand: dict, topic: dict) -> bool:
    cand_title = str(cand.get("title") or "")
    tp_title = str(topic.get("title") or "")
    is_curated = bool(topic.get("is_curated") or not topic.get("is_auto_clustered", True))
    core_nodes = (topic.get("timeline") or topic.get("raw_nodes") or [])[: (4 if is_curated else 3)]
    tp_titles = [tp_title] + [str(n.get("title") or "") for n in core_nodes]
    if any(entities_conflict(cand_title, t) or _subtopic_conflict(cand_title, t) for t in tp_titles[:3] if t):
        return False

    cand_canon = _match_canonical_topic_theme(cand_title)
    if cand_canon and cand_canon[0] == str(topic.get("topic_id") or ""):
        return True

    cand_story = _storyline_tokens(cand_title)
    tp_story = _storyline_tokens(" ".join(tp_titles[:3]))
    story_overlap = len(cand_story & tp_story)

    if any(title_similarity(cand_title, t) >= 0.38 and len(cand_story & _storyline_tokens(t)) >= 2 for t in tp_titles if t):
        return True
    if story_overlap >= 5:
        return True

    cand_eids = set(cand.get("entity_ids") or [])
    tp_eids = set(topic.get("entity_ids") or [])
    shared_spec = (cand_eids - _NON_STORY_ANCHOR_ENTITIES) & (tp_eids - _NON_STORY_ANCHOR_ENTITIES)
    shared_any = (cand_eids - _BROAD_CLUSTER_ENTITIES) & (tp_eids - _BROAD_CLUSTER_ENTITIES)

    if len(shared_spec) >= 2 and story_overlap >= 2:
        return True
    if len(shared_any) >= 1 and story_overlap >= 4:
        return True
    # Also bridge by domain-matched curated topic keywords when entity matches & storyline shares concrete signal
    if len(shared_spec) >= 1 and story_overlap >= 2 and is_curated:
        return True
    return False


def _filter_coherent_auto_nodes(tp_title: str, nodes: List[dict]) -> List[dict]:
    """Prune stray off-topic nodes that leaked into a persisted auto-clustered topic via transitive linkage."""
    if len(nodes) <= 2:
        return nodes
    # Pick medoid node (most similar to other nodes in the cluster) as true storyline core
    node_toks = [_storyline_tokens(str(n.get("title") or "")) for n in nodes]
    node_eids = [{str(m["entity_id"]) for m in match_entities_with_reasons(str(n.get("title") or ""))} - _NON_STORY_ANCHOR_ENTITIES for n in nodes]
    scores = []
    for i, ni in enumerate(nodes):
        s_i = sum(
            1
            for j in range(len(nodes))
            if i != j
            and (
                len(node_toks[i] & node_toks[j]) >= 2
                or title_similarity(str(ni.get("title") or ""), str(nodes[j].get("title") or "")) >= 0.28
                or len(node_eids[i] & node_eids[j]) >= 2
            )
        )
        scores.append((s_i, 1 if any("\u4e00" <= c <= "\u9fff" for c in str(ni.get("title") or "")) else 0))
    medoid_idx = max(range(len(nodes)), key=lambda i: scores[i])
    core_toks = set(node_toks[medoid_idx]) | _storyline_tokens(_clean_headline_phrase(tp_title))
    core_title = str(nodes[medoid_idx].get("title") or tp_title)
    core_eids = set(node_eids[medoid_idx])
    coherent: List[dict] = []
    for idx, n in enumerate(nodes):
        nt = str(n.get("title") or "")
        if entities_conflict(nt, core_title) or _subtopic_conflict(nt, core_title) or _is_minor_quake(nt):
            continue
        if (
            idx == medoid_idx
            or len(node_toks[idx] & core_toks) >= 2
            or title_similarity(nt, core_title) >= 0.24
            or (core_eids and len(node_eids[idx] & core_eids) >= 1 and len(node_toks[idx] & core_toks) >= 1)
        ):
            coherent.append(n)
    return coherent


def _count_recent_nodes(nodes: List[dict], now_dt: datetime) -> Tuple[int, int]:
    """Count (recent_6h_count, today_count) for frontend topic delta badges."""
    recent_6h = 0
    today_cnt = 0
    today_date = now_dt.date()
    for nd in nodes:
        dt = parse_iso_datetime(nd.get("time"))
        if dt is None:
            continue
        age_sec = (now_dt - dt).total_seconds()
        if 0 <= age_sec <= 6 * 3600:
            recent_6h += 1
        if dt.date() == today_date or (0 <= age_sec <= 24 * 3600):
            today_cnt += 1
    return recent_6h, today_cnt


def _topic_heat_score(tp: dict) -> Tuple[int, str, int]:
    status_priority = {"ongoing": 3, "starting": 2, "ending_soon": 1}
    st_prio = status_priority.get(str(tp.get("lifecycle_status") or "ongoing"), 2)
    nodes = tp.get("timeline") or []
    src_cnt = int(tp.get("source_count") or 1)
    has_ev = 1 if tp.get("event_ids") else 0
    curated_bonus = 4 if (tp.get("is_curated") or not tp.get("is_auto_clustered", True)) else 0
    heat = len(nodes) * 2 + src_cnt * 3 + has_ev * 4 + curated_bonus
    return st_prio, str(tp.get("updated_at") or ""), heat


def build_dynamic_topics(
    root: Path,
    *,
    batch_id: str,
    generated_at_iso: str,
    cat_docs: Dict[str, dict],
    storylines: Dict[str, dict],
    raw_items_by_cat: Optional[Dict[str, List[dict]]] = None,
    calendar_events: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """Build dynamic auto-clustered topics with 4-stage lifecycle and persistent historical topic archive."""
    now_dt = parse_iso_datetime(generated_at_iso) or now_shanghai()

    prev_topics_doc = load_json_if_exists(root / "data/topics.json", default={}) or {}
    prev_history_doc = load_json_if_exists(root / "data/topics_history.json", default={}) or {}

    prev_active: List[dict] = []
    seen_prev_ids: Set[str] = set()
    for tp in prev_topics_doc.get("topics") or []:
        if isinstance(tp, dict) and tp.get("topic_id") and tp["topic_id"] not in seen_prev_ids:
            seen_prev_ids.add(tp["topic_id"])
            prev_active.append(dict(tp))

    archived_by_id: Dict[str, dict] = {}
    for src_list in (prev_history_doc.get("archived_topics"), prev_topics_doc.get("archived_topics")):
        for tp in src_list or []:
            if isinstance(tp, dict) and tp.get("topic_id"):
                tp_copy = dict(tp)
                raw_old_tl = _clean_stored_nodes(tp_copy.get("timeline") or [], keep_hotlist_if_scarce=True)
                arch_old_title = str(tp_copy.get("title") or "")
                # Purge cross-theater / cross-subtopic contamination & minor quakes persisted inside old archives
                raw_old_tl = [
                    n for n in raw_old_tl
                    if not _is_minor_quake(str(n.get("title") or ""))
                    and not (arch_old_title and _subtopic_conflict(arch_old_title, str(n.get("title") or "")))
                ]
                is_cur_arch = bool(tp_copy.get("is_curated") or not tp_copy.get("is_auto_clustered", True))
                if not is_cur_arch:
                    raw_old_tl = _filter_coherent_auto_nodes(arch_old_title, raw_old_tl)
                clean_arch_tl = _dedupe_timeline_nodes(raw_old_tl, max_nodes=60)
                if len(clean_arch_tl) < 3 or _is_minor_quake(arch_old_title):
                    continue
                canon_arch = _match_canonical_topic_theme(" ".join(str(n.get("title") or "") for n in clean_arch_tl[:8]))
                re_t, re_s, _ = _build_cluster_headline(clean_arch_tl, set(tp_copy.get("entity_ids") or []))
                final_arch_title = re_t if not is_cur_arch else (canon_arch[1] if canon_arch else arch_old_title)
                key_tid = canon_arch[0] if (canon_arch and not is_cur_arch) else tp["topic_id"]
                arch_pubs = {str(n.get("publisher_name") or n.get("source_name") or "") for n in clean_arch_tl if n.get("source_name") or n.get("publisher_name")}
                if not is_cur_arch and len(arch_pubs) < 2 and key_tid not in {"topic_gta6_launch", "topic_eu_indonesia_fta"}:
                    continue
                if key_tid in archived_by_id:
                    merged_tl = _dedupe_timeline_nodes(list(archived_by_id[key_tid].get("timeline") or []) + clean_arch_tl, max_nodes=60)
                    clean_arch_tl = merged_tl
                    arch_pubs = {str(n.get("publisher_name") or n.get("source_name") or "") for n in clean_arch_tl if n.get("source_name") or n.get("publisher_name")}
                    re_t, re_s, _ = _build_cluster_headline(clean_arch_tl, set(tp_copy.get("entity_ids") or []))
                arch_eids = _derive_topic_entity_ids(clean_arch_tl, final_arch_title, is_curated=is_cur_arch)
                arch_cat = _infer_topic_category(clean_arch_tl, final_arch_title, str(tp_copy.get("category") or "global"))
                reg_k, reg_lbl, p_orgs, dom_tag = _classify_topic_region_and_orgs(final_arch_title, clean_arch_tl, arch_eids, arch_cat)
                tp_copy["topic_id"] = key_tid
                tp_copy["title"] = final_arch_title
                tp_copy["subtitle"] = re_s if not is_cur_arch else f"历史归档专题 · 覆盖 {max(1, len(arch_pubs))} 家信源、共 {len(clean_arch_tl)} 条独立脉络进展"
                tp_copy["category"] = arch_cat
                tp_copy["entity_ids"] = arch_eids
                tp_copy["region"] = reg_k
                tp_copy["region_label"] = reg_lbl
                tp_copy["primary_orgs"] = p_orgs
                tp_copy["domain_tag"] = dom_tag
                tp_copy["timeline"] = clean_arch_tl
                tp_copy["total_mentions"] = len(clean_arch_tl)
                tp_copy["source_count"] = max(1, len(arch_pubs))
                archived_by_id[key_tid] = tp_copy

    upcoming_eids: Set[str] = set()
    upcoming_ev_ids: Set[str] = set()
    for ce in calendar_events or []:
        if isinstance(ce, dict) and not ce.get("is_past"):
            upcoming_eids.update(ce.get("entity_ids") or [])
            for eid_ref in ce.get("event_ids") or []:
                upcoming_ev_ids.add(str(eid_ref))
            if ce.get("event_id"):
                upcoming_ev_ids.add(str(ce["event_id"]))

    # 1. Gather current batch candidates from smart events + valid published raw items
    candidates: List[dict] = []
    for doc in cat_docs.values():
        if not isinstance(doc, dict):
            continue
        for ev in doc.get("events") or []:
            node = _node_from_event(ev, now_dt)
            if node is not None:
                candidates.append(node)
    for cat_k, lst in (raw_items_by_cat or {}).items():
        if not isinstance(lst, list):
            continue
        for it in lst:
            node = _node_from_raw_item(it, cat_k, now_dt)
            if node is not None:
                candidates.append(node)

    candidates.sort(key=lambda c: (1 if c.get("event_id") else 0, str(c.get("time") or "")), reverse=True)

    # 2. Hydrate existing active topics & self-heal mis-archived upcoming/ongoing topics
    topic_buckets: Dict[str, dict] = {}
    unmatched: List[dict] = []
    # Rescue any unfinished upcoming/negotiation topics (e.g. 神舟二十四号合练, COP31 加时) wrongly ended in archive
    for arch_tid_k in list(archived_by_id.keys()):
        atp = archived_by_id[arch_tid_k]
        at_nodes = atp.get("timeline") or []
        at_upd = parse_iso_datetime(atp.get("updated_at") or atp.get("ended_at"))
        at_blob = f"{atp.get('title') or ''} " + " ".join(str(n.get("title") or "") for n in at_nodes[:5])
        if (
            not atp.get("is_curated")
            and at_upd
            and (now_dt - at_upd).total_seconds() < 24 * 3600
            and _ACTIVE_UPCOMING_SIGNAL_RE.search(at_blob)
        ):
            prev_active.append(archived_by_id.pop(arch_tid_k))

    for tp in prev_active:
        tid = str(tp["topic_id"])
        tp_title_raw = str(tp.get("title") or "")
        if _is_minor_quake(tp_title_raw):
            continue
        is_curated = bool(tp.get("is_curated") or not tp.get("is_auto_clustered", True))
        clean_old_nodes = _clean_stored_nodes(tp.get("timeline") or [], keep_hotlist_if_scarce=is_curated)
        # Strip contaminated nodes (e.g. Iran blockade out of Fed topic, or stray NVIDIA out of APEC) & re-route them
        kept_old_nodes: List[dict] = []
        for n in clean_old_nodes:
            nt_s = str(n.get("title") or "")
            if _is_minor_quake(nt_s) or _FLUFF_NOISE_RE.search(nt_s):
                continue
            if tp_title_raw and _subtopic_conflict(tp_title_raw, nt_s):
                unmatched.append(n)
                continue
            kept_old_nodes.append(n)
        clean_old_nodes = kept_old_nodes
        if not clean_old_nodes:
            continue
        if not is_curated:
            clean_old_nodes = _filter_coherent_auto_nodes(tp_title_raw, clean_old_nodes)
            if len(clean_old_nodes) < 3:
                unmatched.extend(clean_old_nodes)
                continue
        canon_active = _match_canonical_topic_theme(" ".join(str(n.get("title") or "") for n in clean_old_nodes[:8]))
        if tid == "topic_ai_ipo_models":
            tid = "topic_anthropic_ipo"
        elif canon_active and not is_curated:
            tid = canon_active[0]
        tp_eids = _derive_topic_entity_ids(clean_old_nodes, canon_active[1] if canon_active else tp_title_raw, is_curated=is_curated)
        if tid in topic_buckets:
            tb_exist = topic_buckets[tid]
            tb_exist["raw_nodes"].extend(clean_old_nodes)
            tb_exist["event_ids"] = list(dict.fromkeys(list(tb_exist.get("event_ids") or []) + list(tp.get("event_ids") or [])))
            tb_exist["entity_ids"] = list(dict.fromkeys(list(tb_exist.get("entity_ids") or []) + tp_eids))
            continue
        topic_buckets[tid] = {
            **tp,
            "topic_id": tid,
            "is_curated": is_curated,
            "entity_ids": tp_eids,
            "raw_nodes": clean_old_nodes,
            "new_candidates": [],
            "event_ids": list(tp.get("event_ids") or []),
            "started_at": tp.get("started_at") or min((str(n.get("time")) for n in clean_old_nodes if n.get("time")), default=generated_at_iso),
        }

    # Track fresh matches on archived topics so >=2 recent developments can re-awaken a historical topic
    archived_hits: Dict[str, List[dict]] = {}
    for cand in candidates:
        matched_tid: Optional[str] = None
        for tid, tb in topic_buckets.items():
            if _matches_existing_topic(cand, tb):
                matched_tid = tid
                break
        if matched_tid:
            tb = topic_buckets[matched_tid]
            tb["raw_nodes"].append(cand)
            tb["new_candidates"].append(cand)
            if cand.get("event_id") and cand["event_id"] not in tb["event_ids"]:
                tb["event_ids"].append(cand["event_id"])
            for eid in cand.get("entity_ids") or []:
                if eid not in tb["entity_ids"]:
                    tb["entity_ids"].append(eid)
            continue

        matched_arch: Optional[str] = None
        cand_dt = cand.get("_ts_dt")
        if cand_dt and (now_dt - cand_dt) <= timedelta(hours=12):
            for arch_tid, arch_tp in archived_by_id.items():
                if _matches_existing_topic(cand, arch_tp):
                    matched_arch = arch_tid
                    break
        if matched_arch:
            archived_hits.setdefault(matched_arch, []).append(cand)
        else:
            unmatched.append(cand)

    for arch_tid, hits in archived_hits.items():
        if len(hits) >= 2 and arch_tid in archived_by_id:
            base_tp = dict(archived_by_id.pop(arch_tid))
            merged_raw = list(base_tp.get("timeline") or []) + hits
            topic_buckets[arch_tid] = {
                **base_tp,
                "raw_nodes": merged_raw,
                "new_candidates": hits,
                "event_ids": list(dict.fromkeys(list(base_tp.get("event_ids") or []) + [h["event_id"] for h in hits if h.get("event_id")])),
                "started_at": base_tp.get("started_at") or min((str(h.get("time")) for h in merged_raw if h.get("time")), default=generated_at_iso),
            }
        else:
            unmatched.extend(hits)

    # 3. Auto-cluster unmatched candidates using connected components on storyline tokens & non-conglomerate entities
    n_un = len(unmatched)
    adj: List[Set[int]] = [set() for _ in range(n_un)]
    cand_story_toks = [_storyline_tokens(c["title"]) for c in unmatched]
    cand_spec_eids = [set(c.get("entity_ids") or []) - _NON_STORY_ANCHOR_ENTITIES for c in unmatched]
    cand_any_eids = [set(c.get("entity_ids") or []) - _BROAD_CLUSTER_ENTITIES for c in unmatched]
    cand_canon = [_match_canonical_topic_theme(c["title"]) for c in unmatched]

    for i in range(n_un):
        for j in range(i + 1, n_un):
            ti, tj = unmatched[i]["title"], unmatched[j]["title"]
            if entities_conflict(ti, tj) or _subtopic_conflict(ti, tj):
                continue
            if cand_canon[i] and cand_canon[j] and cand_canon[i][0] == cand_canon[j][0]:
                adj[i].add(j)
                adj[j].add(i)
                continue
            sim = title_similarity(ti, tj)
            story_overlap = len(cand_story_toks[i] & cand_story_toks[j])
            if (sim >= 0.38 and story_overlap >= 2) or story_overlap >= 5:
                adj[i].add(j)
                adj[j].add(i)
                continue
            shared_spec = cand_spec_eids[i] & cand_spec_eids[j]
            if (len(shared_spec) >= 2 and story_overlap >= 2) or (len(shared_spec) >= 1 and story_overlap >= 3):
                adj[i].add(j)
                adj[j].add(i)
                continue
            shared_any = cand_any_eids[i] & cand_any_eids[j]
            if len(shared_any) >= 1 and story_overlap >= 4:
                adj[i].add(j)
                adj[j].add(i)

    visited = [False] * n_un
    for i in range(n_un):
        if visited[i]:
            continue
        stack = [i]
        comp_indices: List[int] = []
        visited[i] = True
        while stack:
            cur = stack.pop()
            comp_indices.append(cur)
            for nxt in adj[cur]:
                if not visited[nxt]:
                    visited[nxt] = True
                    stack.append(nxt)
        comp_nodes = [unmatched[idx] for idx in comp_indices]
        deduped_cand = _dedupe_timeline_nodes(comp_nodes, max_nodes=60)
        if not deduped_cand:
            continue
        dedup_pubs = {str(n.get("publisher_name") or n.get("source_name") or "") for n in deduped_cand if n.get("source_name") or n.get("publisher_name")}
        has_high_ev = any(cn.get("event_id") and cn.get("importance") == "high" for cn in comp_nodes)
        max_ev_src = max((int(cn.get("source_count") or 1) for cn in comp_nodes), default=1)
        unique_ev_ids = {cn["event_id"] for cn in comp_nodes if cn.get("event_id")}
        has_briefing_ev = bool(unique_ev_ids)

        # Strict Iron Rule 2 & 7 post-dedup qualification: require >=3 unique nodes (>=2 publishers)
        if len(deduped_cand) < 3 or len(dedup_pubs) < 2:
            continue
        if not has_briefing_ev and not (len(deduped_cand) >= 4 and len(dedup_pubs) >= 3):
            continue

        trivial_hits = sum(1 for n in deduped_cand if _TRIVIAL_TOPIC_RE.search(str(n.get("title") or "")))
        if _TRIVIAL_TOPIC_RE.search(str(deduped_cand[0].get("title") or "")) or trivial_hits * 2 >= len(deduped_cand):
            continue

        cluster_eids: Set[str] = set()
        for cn in comp_nodes:
            cluster_eids.update(cn.get("entity_ids") or [])
        cat_counts: Dict[str, int] = {}
        for cn in comp_nodes:
            c_name = str(cn.get("category") or "global")
            cat_counts[c_name] = cat_counts.get(c_name, 0) + (2 if cn.get("event_id") else 1)
        dominant_cat = max(cat_counts.items(), key=lambda kv: kv[1])[0]
        tid = _infer_cluster_topic_id(deduped_cand, cluster_eids, dominant_cat)
        if tid in archived_by_id:
            base_tp = dict(archived_by_id.pop(tid))
            merged_raw = list(base_tp.get("timeline") or []) + comp_nodes
            topic_buckets[tid] = {
                **base_tp,
                "entity_ids": list(dict.fromkeys(list(base_tp.get("entity_ids") or []) + sorted(cluster_eids))),
                "raw_nodes": merged_raw,
                "event_ids": list(dict.fromkeys(list(base_tp.get("event_ids") or []) + [cn["event_id"] for cn in comp_nodes if cn.get("event_id")])),
                "started_at": base_tp.get("started_at") or min((str(cn.get("time")) for cn in deduped_cand if cn.get("time")), default=generated_at_iso),
            }
        elif tid in topic_buckets:
            tb = topic_buckets[tid]
            tb["raw_nodes"].extend(comp_nodes)
            tb["event_ids"].extend([cn["event_id"] for cn in comp_nodes if cn.get("event_id") and cn["event_id"] not in tb["event_ids"]])
        else:
            t_title, t_sub, t_badge = _build_cluster_headline(deduped_cand, cluster_eids)
            topic_buckets[tid] = {
                "topic_id": tid,
                "title": t_title,
                "subtitle": t_sub,
                "badge": t_badge,
                "category": dominant_cat,
                "entity_ids": sorted(cluster_eids)[:6],
                "event_ids": [cn["event_id"] for cn in comp_nodes if cn.get("event_id")],
                "started_at": min((str(cn.get("time")) for cn in deduped_cand if cn.get("time")), default=generated_at_iso),
                "is_auto_clustered": True,
                "is_curated": False,
                "has_high_ev": has_high_ev,
                "max_ev_src": max_ev_src,
                "raw_nodes": comp_nodes,
            }

    # 4. Finalize lifecycle state machine + active vs historical archive separation
    active_topics: List[dict] = []
    for tid, tb in topic_buckets.items():
        deduped_tl = _dedupe_timeline_nodes(tb.get("raw_nodes") or [], max_nodes=60)
        is_curated = bool(tb.get("is_curated") or not tb.get("is_auto_clustered", True))
        if len(deduped_tl) < 3:
            continue
        pub_set = {str(n.get("publisher_name") or n.get("source_name") or "") for n in deduped_tl if n.get("source_name") or n.get("publisher_name")}
        if len(pub_set) < 2 and not is_curated:
            continue
        if not is_curated:
            if _TRIVIAL_TOPIC_RE.search(str(deduped_tl[0].get("title") or "")) or _TRIVIAL_TOPIC_RE.search(str(tb.get("title") or "")):
                continue

        tb_ev_ids = {str(x) for x in (tb.get("event_ids") or [])}
        auto_title, auto_sub, auto_badge = _build_cluster_headline(deduped_tl, set(tb.get("entity_ids") or []))
        final_title = str(tb.get("title") or auto_title) if is_curated else auto_title
        final_sub = str(tb.get("subtitle") or auto_sub) if is_curated and not re.search(r"共\s*\d+\s*条|覆盖\s*\d+\s*家", str(tb.get("subtitle") or "")) else auto_sub
        clean_eids = _derive_topic_entity_ids(deduped_tl, final_title, is_curated=is_curated)
        final_cat = _infer_topic_category(deduped_tl, final_title, str(tb.get("category") or "global"))
        reg_k, reg_lbl, p_orgs, dom_tag = _classify_topic_region_and_orgs(final_title, deduped_tl, clean_eids, final_cat)
        has_cat_win = bool((set(clean_eids) - _NON_STORY_ANCHOR_ENTITIES) & upcoming_eids) or bool(tb_ev_ids & upcoming_ev_ids) or bool(_ACTIVE_UPCOMING_SIGNAL_RE.search(final_title))

        lc_status, lc_label, ended_at = _compute_lifecycle(
            deduped_tl,
            str(tb.get("started_at") or generated_at_iso),
            now_dt,
            has_upcoming_catalyst=has_cat_win,
            topic_title=final_title,
            topic_id=tid,
        )
        recent_6h, today_cnt = _count_recent_nodes(deduped_tl, now_dt)
        latest_ts = str(deduped_tl[0].get("time") or generated_at_iso)
        earliest_ts = str(deduped_tl[-1].get("time") or latest_ts)
        started_at = str(tb.get("started_at") or earliest_ts)
        if earliest_ts and earliest_ts < started_at:
            started_at = earliest_ts

        finalized = {
            "topic_id": tid,
            "title": final_title,
            "title_en": tb.get("title_en") or "",
            "subtitle": final_sub,
            "badge": tb.get("badge") or auto_badge,
            "category": final_cat,
            "region": reg_k,
            "region_label": reg_lbl,
            "primary_orgs": p_orgs,
            "domain_tag": dom_tag,
            "lifecycle_status": lc_status,
            "lifecycle_label": lc_label,
            "started_at": started_at,
            "ended_at": ended_at,
            "updated_at": latest_ts,
            "total_mentions": len(deduped_tl),
            "source_count": max(1, len(pub_set)),
            "recent_6h_count": recent_6h,
            "today_count": today_cnt,
            "entity_ids": clean_eids,
            "event_ids": list(dict.fromkeys(tb.get("event_ids") or [])),
            "is_auto_clustered": not is_curated,
            "is_curated": is_curated,
            "timeline": deduped_tl,
        }
        if lc_status == "ended":
            finalized["archived"] = True
            archived_by_id[tid] = finalized
        else:
            dup_act = next(
                (a for a in active_topics if title_similarity(str(a.get("title") or ""), final_title) >= 0.52),
                None,
            )
            if dup_act is not None:
                merged_dup = _dedupe_timeline_nodes(list(dup_act.get("timeline") or []) + deduped_tl, max_nodes=60)
                dup_act["timeline"] = merged_dup
                dup_act["total_mentions"] = len(merged_dup)
                dup_act["event_ids"] = list(dict.fromkeys(list(dup_act.get("event_ids") or []) + finalized["event_ids"]))
            else:
                finalized["archived"] = False
                active_topics.append(finalized)

    # Also promote genuinely concluded multi-node storylines (>=3 post-dedup nodes, idle >=20h) into archived_topics
    active_ev_ids = {eid for tp in active_topics for eid in (tp.get("event_ids") or [])}
    st_iter = storylines.values() if isinstance(storylines, dict) else (storylines or [])
    for st in st_iter:
        if not isinstance(st, dict):
            continue
        st_title = str(st.get("canonical_title") or st.get("title") or "").strip()
        if not st_title or _TRIVIAL_TOPIC_RE.search(st_title) or _FLUFF_NOISE_RE.search(st_title) or _is_minor_quake(st_title):
            continue
        tl_st = st.get("timeline") or []
        if len(tl_st) < 3:
            continue
        st_ev_ids = {str(n.get("event_id") or "") for n in tl_st if n.get("event_id")}
        if st_ev_ids & active_ev_ids:
            continue
        last_st_dt = parse_iso_datetime(st.get("latest_reported_at") or st.get("last_updated_at"))
        if not last_st_dt:
            continue
        idle_st_h = (now_dt - last_st_dt).total_seconds() / 3600.0
        if idle_st_h < 20.0:
            continue
        arch_tid = f"topic_st_{st.get('storyline_id') or hashlib.sha1(st_title.encode('utf-8')).hexdigest()[:8]}"
        if arch_tid in archived_by_id:
            continue
        raw_st_nodes = []
        for n in tl_st:
            nt = strip_raw_urls_and_domain_tails(str(n.get("title") or ""))
            if not nt or _FLUFF_NOISE_RE.search(nt) or is_omnibus_digest_title(nt) or _is_minor_quake(nt):
                continue
            pub_n = _clean_publisher_name(n.get("source_name"), nt, str(n.get("url") or ""))
            raw_st_nodes.append(
                {
                    "time": n.get("published_at") or n.get("fetched_at") or st.get("latest_reported_at"),
                    "time_source": "published" if n.get("published_at") else "estimated",
                    "stage_tag": classify_itinerary_tag(nt),
                    "title": nt,
                    "summary": _clean_node_summary(str(n.get("summary") or ""), nt, 150),
                    "source_name": pub_n,
                    "publisher_name": pub_n,
                    "url": n.get("url"),
                    "event_id": n.get("event_id"),
                }
            )
        dedup_st = _dedupe_timeline_nodes(raw_st_nodes, max_nodes=60)
        if len(dedup_st) < 3:
            continue
        st_pubs = {str(x.get("publisher_name") or "") for x in dedup_st if x.get("publisher_name")}
        if len(st_pubs) < 2:
            continue
        canon_st = _match_canonical_topic_theme(" ".join(str(n.get("title") or "") for n in dedup_st[:6]))
        arch_tid = canon_st[0] if canon_st else arch_tid
        if arch_tid in archived_by_id:
            continue
        clean_title = canon_st[1] if canon_st else (_clean_headline_phrase(st_title) or st_title)
        st_eids = _derive_topic_entity_ids(dedup_st, clean_title, is_curated=False)
        st_cat = _infer_topic_category(dedup_st, clean_title, str(st.get("category") or "global"))
        reg_k, reg_lbl, p_orgs, dom_tag = _classify_topic_region_and_orgs(clean_title, dedup_st, st_eids, st_cat)
        archived_by_id[arch_tid] = {
            "topic_id": arch_tid,
            "title": clean_title,
            "subtitle": f"历史归档专题 · 覆盖 {len(st_pubs)} 家信源、共 {len(dedup_st)} 条独立脉络进展",
            "badge": _CATEGORY_BADGE_MAP.get(st_cat, "历史专题"),
            "category": st_cat,
            "region": reg_k,
            "region_label": reg_lbl,
            "primary_orgs": p_orgs,
            "domain_tag": dom_tag,
            "lifecycle_status": "ended",
            "lifecycle_label": LIFECYCLE_LABELS["ended"],
            "started_at": st.get("first_seen_at") or dedup_st[-1]["time"],
            "ended_at": to_iso_shanghai(last_st_dt),
            "updated_at": to_iso_shanghai(last_st_dt),
            "total_mentions": len(dedup_st),
            "source_count": len(st_pubs),
            "entity_ids": st_eids,
            "event_ids": list(st_ev_ids),
            "is_auto_clustered": True,
            "is_curated": False,
            "archived": True,
            "timeline": dedup_st,
        }

    # Rank active topics: multi-node ongoing topics FIRST, then starting, then ending_soon.
    # Same-day fresh topics (idle < 12h) are NEVER forced to 'ended'; keep active list cleanly capped while archiving ONLY stale overflow.
    active_topics.sort(
        key=lambda tp: (
            _topic_heat_score(tp)[0],
            _topic_heat_score(tp)[2],
            _topic_heat_score(tp)[1],
        ),
        reverse=True,
    )
    kept_active: List[dict] = []
    overflow_stale: List[dict] = []
    for tp in active_topics:
        upd_dt = parse_iso_datetime(tp.get("updated_at")) or now_dt
        idle_h = max(0.0, (now_dt - upd_dt).total_seconds() / 3600.0)
        is_cur_tp = bool(tp.get("is_curated") or not tp.get("is_auto_clustered", True))
        if len(kept_active) < 8 or (len(kept_active) < 10 and (idle_h < 12.0 or is_cur_tp)):
            kept_active.append(tp)
        else:
            overflow_stale.append(tp)
    active_topics = kept_active
    for ov in overflow_stale:
        upd_dt = parse_iso_datetime(ov.get("updated_at")) or now_dt
        if (now_dt - upd_dt).total_seconds() < 12 * 3600:
            # Never label same-day breaking event as 'ended' in history archive; keep it ending_soon only if genuinely idle
            continue
        ov_copy = dict(ov)
        ov_copy["lifecycle_status"] = "ended"
        ov_copy["lifecycle_label"] = LIFECYCLE_LABELS["ended"]
        ov_copy["archived"] = True
        ov_copy["ended_at"] = ov_copy.get("ended_at") or ov_copy.get("updated_at")
        archived_by_id[str(ov_copy["topic_id"])] = ov_copy

    # Global active vs archived + archive-internal deduplication (ZERO 3~4x duplicates across active & archive!)
    active_id_set = {str(tp.get("topic_id") or "") for tp in active_topics}
    active_titles = [str(tp.get("title") or "") for tp in active_topics]
    for tid_k in list(archived_by_id.keys()):
        arch_tp = archived_by_id[tid_k]
        arch_title = str(arch_tp.get("title") or "")
        arch_upd = parse_iso_datetime(arch_tp.get("updated_at") or arch_tp.get("ended_at"))
        if tid_k in active_id_set or _is_minor_quake(arch_title):
            del archived_by_id[tid_k]
            continue
        if any(title_similarity(arch_title, at) >= 0.42 for at in active_titles if at):
            del archived_by_id[tid_k]
            continue

    # Second pass inside archived_by_id: collapse near-duplicate archived topics by title similarity or shared nodes
    sorted_arch_raw = sorted(
        archived_by_id.values(),
        key=lambda tp: (len(tp.get("timeline") or []), str(tp.get("ended_at") or tp.get("updated_at") or "")),
        reverse=True,
    )
    archived_list: List[dict] = []
    for cand_a in sorted_arch_raw:
        ca_title = str(cand_a.get("title") or "")
        ca_urls = {str(n.get("url") or "") for n in (cand_a.get("timeline") or []) if n.get("url")}
        dup_arch = next(
            (
                prev_a
                for prev_a in archived_list
                if title_similarity(ca_title, str(prev_a.get("title") or "")) >= 0.42
                or len(ca_urls & {str(n.get("url") or "") for n in (prev_a.get("timeline") or []) if n.get("url")}) >= 2
            ),
            None,
        )
        if dup_arch is not None:
            merged_tl = _dedupe_timeline_nodes(list(dup_arch.get("timeline") or []) + list(cand_a.get("timeline") or []), max_nodes=60)
            dup_arch["timeline"] = merged_tl
            dup_arch["total_mentions"] = len(merged_tl)
        else:
            archived_list.append(cand_a)
        if len(archived_list) >= 60:
            break

    archived_list.sort(key=lambda tp: str(tp.get("ended_at") or tp.get("updated_at") or ""), reverse=True)

    return {
        "schema_version": "4.1",
        "generated_at": generated_at_iso,
        "batch_id": batch_id,
        "topics": active_topics,
        "archived_topics": archived_list,
    }
