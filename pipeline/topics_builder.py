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
    r"(?:围巾|座驾|同框|开了个玩笑|人字拖|戒了|全妆|三角梅|打卡|演唱会|剧场版|小雪节气|帮信罪|刑拘|midterm\s*fluff)",
    re.I,
)
_CONCLUDED_SIGNAL_RE = re.compile(
    r"(?:圆满闭幕|正式闭幕|落下帷幕|闭幕|落幕|圆满结束|收官|挂牌上市后|IPO后|已正式退市|宣布取消)",
    re.I,
)
_HOTLIST_NO_TIME_SOURCES = {"zhihu", "baidu", "weibo", "toutiao", "tencent-hot", "tieba", "douyin", "hupu", "coolapk"}
_BROAD_CLUSTER_ENTITIES = {
    "ent_ai_infra_tools",
    "ent_us_tariffs_trade",
}

_CATEGORY_BADGE_MAP = {
    "global": "国际与地缘主线",
    "finance": "资本与宏观主线",
    "tech": "前沿科技主线",
    "general": "全网热点追踪",
}


def classify_itinerary_tag(title: str) -> str:
    t = str(title or "").lower()
    if any(k in t for k in ("闭幕", "落幕", "收官", "结束", "联合声明", "公报")):
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
    # Strictly ignore items with NO genuine published_at (prevents scrape timestamp posing as event time)
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
        if any(title_similarity(t, str(prev.get("title") or "")) >= 0.56 for prev in kept):
            continue
        if u:
            seen_urls.add(u)
        clean_n = {k: v for k, v in n.items() if not k.startswith("_") and k not in {"publisher_families", "entity_ids", "importance", "source_count", "category"}}
        kept.append(clean_n)
        if len(kept) >= max_nodes:
            break
    kept.sort(key=lambda n: str(n.get("time") or ""), reverse=True)
    return kept


def _infer_cluster_topic_id(nodes: List[dict], eids: Set[str], category: str) -> str:
    joined = " ".join(str(n.get("title") or "") for n in nodes[:8]).lower()
    if any(k in joined for k in ("apec", "中美元首", "习特会", "深圳峰会")) or (
        any(k in joined for k in ("特朗普", "trump")) and any(k in joined for k in ("访华", "习近平", "深圳"))
    ):
        return "topic_apec_trump_china"
    core_eids = sorted(e for e in eids if e not in _BROAD_CLUSTER_ENTITIES)[:2]
    if core_eids:
        sig = f"{category}:{'+'.join(core_eids)}"
    else:
        toks = sorted(extract_tokens(" ".join(str(n.get("title") or "") for n in nodes[:4])))[:4]
        sig = f"{category}:{'_'.join(toks)}"
    digest = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:10]
    return f"topic_auto_{digest}"


def _build_cluster_headline(nodes: List[dict], eids: Set[str]) -> Tuple[str, str, str]:
    """Build concise Chinese topic title, subtitle, and badge deterministically."""
    joined = " ".join(str(n.get("title") or "") for n in nodes[:8]).lower()
    if any(k in joined for k in ("apec", "中美元首", "深圳峰会")) and any(k in joined for k in ("特朗普", "trump", "访华", "习近平")):
        return (
            "特朗普访华与 2026 深圳 APEC 峰会专题追踪",
            "自动聚合中美元首双边/多边会晤、关税与 AI 治理声明等核心进展",
            "国际主线专题",
        )
    # Use top entities + richest core node title
    ranked = sorted(
        nodes,
        key=lambda n: (1 if n.get("event_id") else 0, n.get("source_count", 1), str(n.get("time") or "")),
        reverse=True,
    )
    anchor_title = smart_truncate(str(ranked[0].get("title") or "全网突发焦点追踪"), 34)
    ent_labels: List[str] = []
    for eid in sorted(eids):
        if eid in _BROAD_CLUSTER_ENTITIES:
            continue
        ed = ENTITY_BY_ID.get(eid)
        if ed:
            short = re.sub(r"\s*\([^)]+\)\s*", "", ed.canonical_name).split("/")[0].strip()
            if short and short not in ent_labels:
                ent_labels.append(short)
        if len(ent_labels) >= 2:
            break
    if ent_labels and all(lbl.lower() not in anchor_title.lower() for lbl in ent_labels):
        title = f"{' · '.join(ent_labels)}：{anchor_title}"
    else:
        title = anchor_title
    title = smart_truncate(title, 42)
    pub_cnt = len({str(n.get("publisher_name") or n.get("source_name") or "") for n in nodes if n.get("source_name")})
    subtitle = f"算法自动聚类 · 覆盖 {pub_cnt} 家信源、共 {len(nodes)} 条实时脉络更新"
    cat = str(ranked[0].get("category") or "global")
    return title, subtitle, _CATEGORY_BADGE_MAP.get(cat, "全网焦点专题")


def _compute_lifecycle(
    nodes: List[dict],
    started_at_iso: str,
    now_dt: datetime,
    *,
    has_upcoming_catalyst: bool = False,
) -> Tuple[str, str, Optional[str]]:
    pub_dts = [parse_iso_datetime(n.get("time")) for n in nodes if n.get("time") and n.get("time_source") != "estimated"]
    pub_dts = [d for d in pub_dts if d is not None]
    if not pub_dts:
        all_dts = [parse_iso_datetime(n.get("time")) for n in nodes if n.get("time")]
        pub_dts = [d for d in all_dts if d is not None]
    last_dt = max(pub_dts) if pub_dts else now_dt
    start_dt = parse_iso_datetime(started_at_iso) or (min(pub_dts) if pub_dts else now_dt)
    idle_hours = max(0.0, (now_dt - last_dt).total_seconds() / 3600.0)
    age_hours = max(0.0, (now_dt - start_dt).total_seconds() / 3600.0)

    recent_titles = " ".join(str(n.get("title") or "") for n in nodes[:4])
    has_concluded = bool(_CONCLUDED_SIGNAL_RE.search(recent_titles))

    if idle_hours > 60.0 or (has_concluded and idle_hours >= 18.0 and not has_upcoming_catalyst):
        return "ended", LIFECYCLE_LABELS["ended"], to_iso_shanghai(last_dt)
    if idle_hours >= 24.0 or (has_concluded and idle_hours >= 6.0 and not has_upcoming_catalyst):
        return "ending_soon", LIFECYCLE_LABELS["ending_soon"], None
    if age_hours <= 18.0 and len(nodes) <= 6 and idle_hours <= 12.0:
        return "starting", LIFECYCLE_LABELS["starting"], None
    return "ongoing", LIFECYCLE_LABELS["ongoing"], None


def _matches_existing_topic(cand: dict, topic: dict) -> bool:
    cand_eids = set(cand.get("entity_ids") or []) - _BROAD_CLUSTER_ENTITIES
    tp_eids = set(topic.get("entity_ids") or []) - _BROAD_CLUSTER_ENTITIES
    cand_title = str(cand.get("title") or "")
    tp_titles = [str(topic.get("title") or "")] + [str(n.get("title") or "") for n in (topic.get("timeline") or [])[:6]]
    if any(entities_conflict(cand_title, t) for t in tp_titles[:3] if t):
        return False
    cand_toks = extract_tokens(cand_title)
    tp_toks = extract_tokens(" ".join(tp_titles[:4]))
    if any(title_similarity(cand_title, t) >= 0.26 for t in tp_titles if t) or len(cand_toks & tp_toks) >= 4:
        return True
    if cand_eids and tp_eids:
        shared = cand_eids & tp_eids
        if len(shared) >= 2:
            return True
        if len(shared) == 1 and len(cand_toks & tp_toks) >= 2:
            return True
    return False


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

    # Load previous active + historical archive topics so multi-day stories & concluded topics persist cleanly
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
                archived_by_id[tp["topic_id"]] = dict(tp)

    # Upcoming unresolved catalysts indexed by entity_id & event_id
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

    # Sort candidates chronologically descending so newest briefing items seed anchors first
    candidates.sort(key=lambda c: (1 if c.get("event_id") else 0, str(c.get("time") or "")), reverse=True)

    # 2. Hydrate existing active topics & attach matching new candidates
    topic_buckets: Dict[str, dict] = {}
    unmatched: List[dict] = []
    for tp in prev_active:
        tid = str(tp["topic_id"])
        # Scrub old hotlist/bogus fetch-time nodes if migrating from legacy preset topic
        clean_old_nodes = []
        for old_n in tp.get("timeline") or []:
            if not isinstance(old_n, dict):
                continue
            src_low = str(old_n.get("source_name") or old_n.get("publisher_name") or "").lower()
            if any(h in src_low for h in ("知乎", "百度热搜", "微博", "今日头条")) and not old_n.get("event_id"):
                continue
            nt = strip_raw_urls_and_domain_tails(str(old_n.get("title") or ""))
            if not nt or _FLUFF_NOISE_RE.search(nt) or is_omnibus_digest_title(nt):
                continue
            n_copy = dict(old_n)
            n_copy["title"] = nt
            if not n_copy.get("publisher_name"):
                n_copy["publisher_name"] = _clean_publisher_name(n_copy.get("source_name"), nt, str(n_copy.get("url") or ""))
                n_copy["source_name"] = n_copy["publisher_name"]
            n_copy.setdefault("time_source", "published")
            clean_old_nodes.append(n_copy)
        tp_eids = list(tp.get("entity_ids") or [])
        if not tp_eids:
            tp_eids = [
                m["entity_id"]
                for m in match_entities_with_reasons(" ".join(str(n.get("title") or "") for n in clean_old_nodes[:5]))
            ][:5]
        topic_buckets[tid] = {
            **tp,
            "entity_ids": tp_eids,
            "raw_nodes": clean_old_nodes,
            "new_candidates": [],
            "event_ids": list(tp.get("event_ids") or []),
            "started_at": tp.get("started_at") or min((str(n.get("time")) for n in clean_old_nodes if n.get("time")), default=generated_at_iso),
        }

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
        else:
            unmatched.append(cand)

    # 3. Auto-cluster unmatched candidates using connected components (entities + token overlap)
    n_un = len(unmatched)
    adj: List[Set[int]] = [set() for _ in range(n_un)]
    cand_toks = [extract_tokens(c["title"]) for c in unmatched]
    cand_eids = [set(c.get("entity_ids") or []) - _BROAD_CLUSTER_ENTITIES for c in unmatched]

    for i in range(n_un):
        for j in range(i + 1, n_un):
            ti, tj = unmatched[i]["title"], unmatched[j]["title"]
            if entities_conflict(ti, tj):
                continue
            sim = title_similarity(ti, tj)
            tok_overlap = len(cand_toks[i] & cand_toks[j])
            if sim >= 0.24 or tok_overlap >= 4:
                adj[i].add(j)
                adj[j].add(i)
                continue
            shared_e = cand_eids[i] & cand_eids[j]
            if shared_e and (len(shared_e) >= 2 or tok_overlap >= 2):
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
        pub_fams: Set[str] = set()
        cluster_eids: Set[str] = set()
        has_high_event = False
        for cn in comp_nodes:
            pub_fams.update(cn.get("publisher_families") or {cn.get("publisher_name") or "wire"})
            cluster_eids.update(cn.get("entity_ids") or [])
            if cn.get("event_id") and (cn.get("importance") == "high" or cn.get("source_count", 1) >= 2):
                has_high_event = True
        source_total = max(len(pub_fams), max((cn.get("source_count", 1) for cn in comp_nodes), default=1))
        # Qualify as a breaking/developing topic: multi-source convergence or >=3 corroborated nodes
        if not (
            (has_high_event and source_total >= 2)
            or (len(comp_nodes) >= 3 and source_total >= 2)
        ):
            continue

        cat_counts: Dict[str, int] = {}
        for cn in comp_nodes:
            c_name = str(cn.get("category") or "global")
            cat_counts[c_name] = cat_counts.get(c_name, 0) + (2 if cn.get("event_id") else 1)
        dominant_cat = max(cat_counts.items(), key=lambda kv: kv[1])[0]
        tid = _infer_cluster_topic_id(comp_nodes, cluster_eids, dominant_cat)
        if tid in archived_by_id:
            # Re-awakened historical topic! Bring it back into active buckets
            base_tp = dict(archived_by_id.pop(tid))
            merged_raw = list(base_tp.get("timeline") or []) + comp_nodes
            topic_buckets[tid] = {
                **base_tp,
                "entity_ids": list(dict.fromkeys(list(base_tp.get("entity_ids") or []) + sorted(cluster_eids))),
                "raw_nodes": merged_raw,
                "event_ids": list(dict.fromkeys(list(base_tp.get("event_ids") or []) + [cn["event_id"] for cn in comp_nodes if cn.get("event_id")])),
                "started_at": base_tp.get("started_at") or min((str(cn.get("time")) for cn in comp_nodes if cn.get("time")), default=generated_at_iso),
            }
        elif tid in topic_buckets:
            tb = topic_buckets[tid]
            tb["raw_nodes"].extend(comp_nodes)
            tb["event_ids"].extend([cn["event_id"] for cn in comp_nodes if cn.get("event_id") and cn["event_id"] not in tb["event_ids"]])
        else:
            t_title, t_sub, t_badge = _build_cluster_headline(comp_nodes, cluster_eids)
            topic_buckets[tid] = {
                "topic_id": tid,
                "title": t_title,
                "subtitle": t_sub,
                "badge": t_badge,
                "category": dominant_cat,
                "entity_ids": sorted(cluster_eids)[:6],
                "event_ids": [cn["event_id"] for cn in comp_nodes if cn.get("event_id")],
                "started_at": min((str(cn.get("time")) for cn in comp_nodes if cn.get("time")), default=generated_at_iso),
                "is_auto_clustered": True,
                "raw_nodes": comp_nodes,
            }

    # 4. Finalize lifecycle state machine + active vs historical archive separation
    active_topics: List[dict] = []
    for tid, tb in topic_buckets.items():
        deduped_tl = _dedupe_timeline_nodes(tb.get("raw_nodes") or [], max_nodes=60)
        if not deduped_tl:
            continue
        tb_eids = set(tb.get("entity_ids") or [])
        tb_ev_ids = {str(x) for x in (tb.get("event_ids") or [])}
        has_cat_win = bool((tb_eids - _BROAD_CLUSTER_ENTITIES) & upcoming_eids) or bool(tb_ev_ids & upcoming_ev_ids)
        lc_status, lc_label, ended_at = _compute_lifecycle(
            deduped_tl,
            str(tb.get("started_at") or generated_at_iso),
            now_dt,
            has_upcoming_catalyst=has_cat_win,
        )
        latest_ts = str(deduped_tl[0].get("time") or generated_at_iso)
        pub_set = {str(n.get("publisher_name") or n.get("source_name") or "") for n in deduped_tl if n.get("source_name")}
        finalized = {
            "topic_id": tid,
            "title": tb.get("title") or _build_cluster_headline(deduped_tl, tb_eids)[0],
            "title_en": tb.get("title_en") or "",
            "subtitle": tb.get("subtitle") or _build_cluster_headline(deduped_tl, tb_eids)[1],
            "badge": tb.get("badge") or _CATEGORY_BADGE_MAP.get(str(tb.get("category") or "global"), "全网焦点专题"),
            "category": tb.get("category") or "global",
            "lifecycle_status": lc_status,
            "lifecycle_label": lc_label,
            "started_at": tb.get("started_at") or latest_ts,
            "ended_at": ended_at,
            "updated_at": latest_ts,
            "total_mentions": max(len(deduped_tl), int(tb.get("total_mentions") or 0)),
            "source_count": len(pub_set),
            "entity_ids": list(tb.get("entity_ids") or [])[:6],
            "event_ids": list(dict.fromkeys(tb.get("event_ids") or [])),
            "is_auto_clustered": bool(tb.get("is_auto_clustered", True)),
            "timeline": deduped_tl,
        }
        if lc_status == "ended":
            finalized["archived"] = True
            archived_by_id[tid] = finalized
        else:
            finalized["archived"] = False
            active_topics.append(finalized)

    # Also promote genuinely concluded multi-node storylines into archived_topics if not already represented
    active_ev_ids = {eid for tp in active_topics for eid in (tp.get("event_ids") or [])}
    st_iter = storylines.values() if isinstance(storylines, dict) else (storylines or [])
    for st in st_iter:
        if not isinstance(st, dict):
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
        if idle_st_h < 60.0:
            continue
        arch_tid = f"topic_st_{st.get('storyline_id') or hashlib.sha1(str(st.get('canonical_title') or '').encode('utf-8')).hexdigest()[:8]}"
        if arch_tid in archived_by_id:
            continue
        norm_nodes = []
        for n in tl_st:
            nt = strip_raw_urls_and_domain_tails(str(n.get("title") or ""))
            if not nt:
                continue
            norm_nodes.append(
                {
                    "time": n.get("published_at") or n.get("fetched_at") or st.get("latest_reported_at"),
                    "time_source": "published" if n.get("published_at") else "estimated",
                    "stage_tag": classify_itinerary_tag(nt),
                    "title": nt,
                    "summary": smart_truncate(str(n.get("summary") or ""), 150),
                    "source_name": _clean_publisher_name(n.get("source_name"), nt, str(n.get("url") or "")),
                    "publisher_name": _clean_publisher_name(n.get("source_name"), nt, str(n.get("url") or "")),
                    "url": n.get("url"),
                    "event_id": n.get("event_id"),
                }
            )
        norm_nodes.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
        if not norm_nodes:
            continue
        archived_by_id[arch_tid] = {
            "topic_id": arch_tid,
            "title": smart_truncate(str(st.get("canonical_title") or norm_nodes[0]["title"]), 42),
            "subtitle": f"历史归档专题 · 共沉淀 {len(norm_nodes)} 条时间线节点",
            "badge": _CATEGORY_BADGE_MAP.get(str(st.get("category") or "global"), "历史专题"),
            "category": st.get("category") or "global",
            "lifecycle_status": "ended",
            "lifecycle_label": LIFECYCLE_LABELS["ended"],
            "started_at": st.get("first_seen_at") or norm_nodes[-1]["time"],
            "ended_at": to_iso_shanghai(last_st_dt),
            "updated_at": to_iso_shanghai(last_st_dt),
            "total_mentions": len(norm_nodes),
            "source_count": len({x["publisher_name"] for x in norm_nodes}),
            "entity_ids": list(st.get("entity_ids") or [])[:6],
            "event_ids": list(st_ev_ids),
            "is_auto_clustered": True,
            "archived": True,
            "timeline": norm_nodes[:60],
        }

    # Active topics ordering: actively developing stages first, then recency & breadth (concluded summits no longer monopolize top slot!)
    status_priority = {"starting": 3, "ongoing": 2, "ending_soon": 1}
    active_topics.sort(
        key=lambda tp: (
            status_priority.get(str(tp.get("lifecycle_status") or "ongoing"), 2),
            str(tp.get("updated_at") or ""),
            int(tp.get("source_count") or 0),
            len(tp.get("timeline") or []),
        ),
        reverse=True,
    )
    active_topics = active_topics[:8]

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
