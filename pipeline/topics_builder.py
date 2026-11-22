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
    r"首日.{0,6}收|次日股价|首周定价|顺利回收|圆满完成|签署联合声明|已正式退市|宣布取消)",
    re.I,
)
_HOTLIST_NO_TIME_SOURCES = {"zhihu", "baidu", "weibo", "toutiao", "tencent-hot", "tieba", "douyin", "hupu", "coolapk"}
_BROAD_CLUSTER_ENTITIES = {
    "ent_ai_infra_tools",
    "ent_us_tariffs_trade",
}
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
    r"^(?:【[^】]{1,20}】\s*|(?:财联社|新华网|新华社|央视新闻|人民网|金十数据|法布财经|格隆汇)\s*(?:\d{1,2}月\d{1,2}日)?电[，,：:\s]*(?:据[^，,：:]{2,22}(?:消息|报道|称)[，,：:\s]*)?|(?:外电|快讯|报道称|独家|最新|消息称|外媒称|官方|欧洲地中海地震中心|美国地质调查局(?:（USGS）)?)\s*[:：]\s*)"
)

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
    if not title or is_omnibus_digest_title(title) or _FLUFF_NOISE_RE.search(title):
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
    summary = strip_raw_urls_and_domain_tails(str(ev.get("fact_summary") or ev.get("summary") or "").strip())
    summary = smart_truncate(summary, 160)
    if summary == title:
        summary = ""
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
    if not title or not url or len(title) < 6 or is_omnibus_digest_title(title) or _FLUFF_NOISE_RE.search(title):
        return None
    pub_name = _clean_publisher_name(it.get("publisher_name") or it.get("source_name") or sid, title, url)
    summary = strip_raw_urls_and_domain_tails(str(it.get("excerpt") or "").strip())
    summary = smart_truncate(summary, 140)
    if summary == title:
        summary = ""
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
        if not nt or _FLUFF_NOISE_RE.search(nt) or is_omnibus_digest_title(nt):
            continue
        n_copy = dict(old_n)
        n_copy["title"] = nt
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


def _safe_clip_headline(text: str, max_len: int = 36) -> str:
    txt = str(text or "").strip().rstrip("。！？!?，；;：:…‘“(")
    if len(txt) <= max_len:
        return txt
    # Prefer clean boundary for English vs Chinese so we never chop mid-word or leave dangling quotes
    sub = txt[:max_len]
    if sum(1 for c in sub if "\u4e00" <= c <= "\u9fff") < 4:
        ws = sub.rfind(" ")
        if ws >= 12:
            sub = sub[:ws]
    return sub.rstrip("，；：、‘“(- ").rstrip("。！？!?….")


def _clean_headline_phrase(raw_title: str) -> str:
    txt = strip_raw_urls_and_domain_tails(str(raw_title or "").strip())
    for _ in range(2):
        stripped = _WIRE_DATELINE_RE.sub("", txt).strip()
        if stripped == txt:
            break
        txt = stripped
    txt = txt.rstrip("。！？!?，；;：:….")
    if len(txt) > 34:
        parts = [p.strip(" ，；：") for p in re.split(r"[；;。]|(?<=\D)[:：](?=\D)", txt) if p.strip()]
        if parts and len(parts[0]) >= 10:
            candidate = f"{parts[0]}：{parts[1]}" if len(parts) > 1 and len(parts[0]) + len(parts[1]) <= 34 else parts[0]
            txt = candidate
        elif "，" in txt:
            c0 = txt.split("，", 1)[0].strip()
            if len(c0) >= 12:
                txt = c0
    return _safe_clip_headline(txt, max_len=36)


def _infer_cluster_topic_id(nodes: List[dict], eids: Set[str], category: str) -> str:
    joined = " ".join(str(n.get("title") or "") for n in nodes[:8]).lower()
    if any(k in joined for k in ("apec", "中美元首", "习特会", "深圳峰会")) or (
        any(k in joined for k in ("特朗普", "trump")) and any(k in joined for k in ("访华", "习近平", "深圳"))
    ):
        return "topic_apec_trump_china"
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
    joined = " ".join(str(n.get("title") or "") for n in deduped_nodes[:8]).lower()
    if any(k in joined for k in ("apec", "中美元首", "深圳峰会")) and any(k in joined for k in ("特朗普", "trump", "访华", "习近平")):
        pub_cnt = len({str(n.get("publisher_name") or n.get("source_name") or "") for n in deduped_nodes if n.get("source_name") or n.get("publisher_name")})
        return (
            "特朗普访华与 2026 深圳 APEC 峰会",
            f"覆盖 {max(1, pub_cnt)} 家信源、共 {len(deduped_nodes)} 条独立脉络进展",
            "国际主线专题",
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

    ent_labels: List[str] = []
    anchor_low = anchor_phrase.lower()
    joined_low = " ".join(str(n.get("title") or "") for n in deduped_nodes[:6]).lower()
    for eid in sorted(eids):
        if eid in _NON_STORY_ANCHOR_ENTITIES:
            continue
        ed = ENTITY_BY_ID.get(eid)
        if not ed:
            continue
        # Only attach entity prefix if that entity actually appears in the cluster's core nodes
        hit_aliases = [al.lower() for al in (ed.aliases or ()) if len(al) >= 2]
        if hit_aliases and not any(al in joined_low for al in hit_aliases):
            continue
        if any(al in anchor_low for al in hit_aliases):
            continue
        raw_parts = [p.strip() for p in re.sub(r"\s*\([^)]+\)\s*", "", ed.canonical_name).split("/") if p.strip()]
        chosen = next((p for p in raw_parts if p.lower() in joined_low), raw_parts[0] if raw_parts else "")
        if chosen and chosen.lower() not in anchor_low and chosen not in ent_labels:
            ent_labels.append(chosen)
        if len(ent_labels) >= 1:
            break
    if ent_labels:
        title = f"{ent_labels[0]}：{anchor_phrase}"
    else:
        title = anchor_phrase
    title = _safe_clip_headline(title, max_len=38)
    pub_cnt = len({str(n.get("publisher_name") or n.get("source_name") or "") for n in deduped_nodes if n.get("source_name") or n.get("publisher_name")})
    subtitle = f"覆盖 {max(1, pub_cnt)} 家信源、共 {len(deduped_nodes)} 条独立脉络进展"
    cat = str((deduped_nodes[0] if deduped_nodes else {}).get("category") or "global")
    return title, subtitle, _CATEGORY_BADGE_MAP.get(cat, "全网焦点专题")


def _compute_lifecycle(
    nodes: List[dict],
    started_at_iso: str,
    now_dt: datetime,
    *,
    has_upcoming_catalyst: bool = False,
    topic_title: str = "",
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
    has_concluded = bool(_CONCLUDED_SIGNAL_RE.search(recent_titles))

    if idle_hours >= 36.0 or (has_concluded and idle_hours >= 6.0 and not has_upcoming_catalyst) or (has_concluded and idle_hours >= 12.0):
        return "ended", LIFECYCLE_LABELS["ended"], to_iso_shanghai(last_dt)
    if idle_hours >= 14.0 or (has_concluded and idle_hours >= 2.0):
        return "ending_soon", LIFECYCLE_LABELS["ending_soon"], None
    if span_hours >= 6.0 or len(nodes) >= 5 or age_hours > 12.0:
        return "ongoing", LIFECYCLE_LABELS["ongoing"], None
    return "starting", LIFECYCLE_LABELS["starting"], None


def _matches_existing_topic(cand: dict, topic: dict) -> bool:
    cand_title = str(cand.get("title") or "")
    tp_title = str(topic.get("title") or "")
    is_curated = bool(topic.get("is_curated") or not topic.get("is_auto_clustered", True))
    core_nodes = (topic.get("timeline") or topic.get("raw_nodes") or [])[: (4 if is_curated else 3)]
    tp_titles = [tp_title] + [str(n.get("title") or "") for n in core_nodes]
    if any(entities_conflict(cand_title, t) for t in tp_titles[:3] if t):
        return False

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
        if entities_conflict(nt, core_title):
            continue
        if (
            idx == medoid_idx
            or len(node_toks[idx] & core_toks) >= 2
            or title_similarity(nt, core_title) >= 0.24
            or (core_eids and len(node_eids[idx] & core_eids) >= 1 and len(node_toks[idx] & core_toks) >= 1)
        ):
            coherent.append(n)
    return coherent


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
                clean_arch_tl = _dedupe_timeline_nodes(
                    _clean_stored_nodes(tp_copy.get("timeline") or [], keep_hotlist_if_scarce=True),
                    max_nodes=60,
                )
                if len(clean_arch_tl) >= 3:
                    tp_copy["timeline"] = clean_arch_tl
                    tp_copy["total_mentions"] = len(clean_arch_tl)
                    pub_s = {str(n.get("publisher_name") or n.get("source_name") or "") for n in clean_arch_tl if n.get("source_name") or n.get("publisher_name")}
                    tp_copy["source_count"] = max(1, len(pub_s))
                    is_cur_arch = bool(tp_copy.get("is_curated") or not tp_copy.get("is_auto_clustered", True))
                    if not is_cur_arch:
                        arch_eids = {str(x) for x in (tp_copy.get("entity_ids") or [])}
                        old_at = str(tp_copy.get("title") or "")
                        if re.search(r"[‘“(]$|^财联社\d+月\d+日电", old_at) or len(old_at) <= 20:
                            re_t, re_s, _ = _build_cluster_headline(clean_arch_tl, arch_eids)
                            tp_copy["title"] = re_t
                            tp_copy["subtitle"] = re_s
                    archived_by_id[tp["topic_id"]] = tp_copy

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

    # 2. Hydrate existing active topics & attach matching new candidates
    topic_buckets: Dict[str, dict] = {}
    unmatched: List[dict] = []
    for tp in prev_active:
        tid = str(tp["topic_id"])
        is_curated = bool(tp.get("is_curated") or not tp.get("is_auto_clustered", True))
        clean_old_nodes = _clean_stored_nodes(tp.get("timeline") or [], keep_hotlist_if_scarce=is_curated)
        if not clean_old_nodes:
            continue
        if not is_curated:
            clean_old_nodes = _filter_coherent_auto_nodes(str(tp.get("title") or ""), clean_old_nodes)
            if len(clean_old_nodes) < 3:
                unmatched.extend(clean_old_nodes)
                continue
        tp_eids = list(tp.get("entity_ids") or [])
        if not tp_eids or not is_curated:
            tp_eids = [
                m["entity_id"]
                for m in match_entities_with_reasons(" ".join(str(n.get("title") or "") for n in clean_old_nodes[:6]))
            ][:6]
        topic_buckets[tid] = {
            **tp,
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

    for i in range(n_un):
        for j in range(i + 1, n_un):
            ti, tj = unmatched[i]["title"], unmatched[j]["title"]
            if entities_conflict(ti, tj):
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

        tb_eids = set(tb.get("entity_ids") or [])
        tb_ev_ids = {str(x) for x in (tb.get("event_ids") or [])}
        has_cat_win = bool((tb_eids - _NON_STORY_ANCHOR_ENTITIES) & upcoming_eids) or bool(tb_ev_ids & upcoming_ev_ids)

        auto_title, auto_sub, auto_badge = _build_cluster_headline(deduped_tl, tb_eids)
        final_title = str(tb.get("title") or auto_title) if is_curated else auto_title
        final_sub = str(tb.get("subtitle") or auto_sub) if is_curated and not re.search(r"共\s*\d+\s*条|覆盖\s*\d+\s*家", str(tb.get("subtitle") or "")) else auto_sub

        lc_status, lc_label, ended_at = _compute_lifecycle(
            deduped_tl,
            str(tb.get("started_at") or generated_at_iso),
            now_dt,
            has_upcoming_catalyst=has_cat_win,
            topic_title=final_title,
        )
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
            "category": tb.get("category") or "global",
            "lifecycle_status": lc_status,
            "lifecycle_label": lc_label,
            "started_at": started_at,
            "ended_at": ended_at,
            "updated_at": latest_ts,
            "total_mentions": len(deduped_tl),
            "source_count": max(1, len(pub_set)),
            "entity_ids": list(tb.get("entity_ids") or [])[:6],
            "event_ids": list(dict.fromkeys(tb.get("event_ids") or [])),
            "is_auto_clustered": not is_curated,
            "is_curated": is_curated,
            "timeline": deduped_tl,
        }
        if lc_status == "ended":
            finalized["archived"] = True
            archived_by_id[tid] = finalized
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
        if not st_title or _TRIVIAL_TOPIC_RE.search(st_title) or _FLUFF_NOISE_RE.search(st_title):
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
            if not nt or _FLUFF_NOISE_RE.search(nt) or is_omnibus_digest_title(nt):
                continue
            pub_n = _clean_publisher_name(n.get("source_name"), nt, str(n.get("url") or ""))
            raw_st_nodes.append(
                {
                    "time": n.get("published_at") or n.get("fetched_at") or st.get("latest_reported_at"),
                    "time_source": "published" if n.get("published_at") else "estimated",
                    "stage_tag": classify_itinerary_tag(nt),
                    "title": nt,
                    "summary": smart_truncate(str(n.get("summary") or ""), 150),
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
        clean_title = _clean_headline_phrase(st_title) or st_title
        archived_by_id[arch_tid] = {
            "topic_id": arch_tid,
            "title": clean_title,
            "subtitle": f"历史归档专题 · 覆盖 {len(st_pubs)} 家信源、共 {len(dedup_st)} 条独立脉络进展",
            "badge": _CATEGORY_BADGE_MAP.get(str(st.get("category") or "global"), "历史专题"),
            "category": st.get("category") or "global",
            "lifecycle_status": "ended",
            "lifecycle_label": LIFECYCLE_LABELS["ended"],
            "started_at": st.get("first_seen_at") or dedup_st[-1]["time"],
            "ended_at": to_iso_shanghai(last_st_dt),
            "updated_at": to_iso_shanghai(last_st_dt),
            "total_mentions": len(dedup_st),
            "source_count": len(st_pubs),
            "entity_ids": list(st.get("entity_ids") or [])[:6],
            "event_ids": list(st_ev_ids),
            "is_auto_clustered": True,
            "is_curated": False,
            "archived": True,
            "timeline": dedup_st,
        }

    # Rank active topics: multi-node ongoing topics FIRST, then starting, then ending_soon; preserve overflow in archive!
    active_topics.sort(
        key=lambda tp: (
            _topic_heat_score(tp)[0],
            _topic_heat_score(tp)[2],
            _topic_heat_score(tp)[1],
        ),
        reverse=True,
    )
    overflow_topics = active_topics[8:]
    active_topics = active_topics[:8]
    for ov in overflow_topics:
        ov_copy = dict(ov)
        ov_copy["lifecycle_status"] = "ended"
        ov_copy["lifecycle_label"] = LIFECYCLE_LABELS["ended"]
        ov_copy["archived"] = True
        ov_copy["ended_at"] = ov_copy.get("ended_at") or ov_copy.get("updated_at")
        archived_by_id[str(ov_copy["topic_id"])] = ov_copy

    archived_list = sorted(
        archived_by_id.values(),
        key=lambda tp: str(tp.get("ended_at") or tp.get("updated_at") or ""),
        reverse=True,
    )[:60]

    return {
        "schema_version": "4.1",
        "generated_at": generated_at_iso,
        "batch_id": batch_id,
        "topics": active_topics,
        "archived_topics": archived_list,
    }
