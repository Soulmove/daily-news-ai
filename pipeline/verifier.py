"""Deterministic V3 verification gate: independent identities, separated timestamps, claim boundaries & structured facts."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from pipeline.connectors.base import repair_mojibake
from pipeline.dedup import entities_conflict, extract_tokens, get_publisher_family, is_omnibus_digest_title, title_similarity
from pipeline.time_utils import parse_iso_datetime
from pipeline.entities import ENTITY_REGISTRY, match_entities_with_reasons
from pipeline.id_utils import (
    canonicalize_url,
    ensure_unique_event_id,
    is_generic_quote_or_homepage_url,
    make_event_id,
    make_storyline_id,
)

EVIDENCE_LABELS = {
    "official_confirmed": "一手官方/披露已证实",
    "multi_source": "多独立来源提及（待核官方全文）",
    "single_source": "单一独立来源线索",
    "needs_verification": "待核实 / 出处不足",
}

_RUMOR_PREFIX_RE = re.compile(r"(?:传闻|爆料|消息称|报道称|据称|据悉|网传|未确认|拟|传出)")


def dedupe_attribution_prefixes(text: str) -> str:
    """Idempotently collapse repeated attribution prefixes & recover UTF-8 mojibake."""
    cleaned = repair_mojibake(str(text or ""))
    cleaned = re.sub(r"(?:报道称：\s*){2,}", "报道称：", cleaned)
    cleaned = re.sub(
        r"(?:【据关联报道/尚未见官方披露确认】\s*){2,}",
        "【据关联报道/尚未见官方披露确认】",
        cleaned,
    )
    cleaned = cleaned.replace("原始素材仅含标题，细节待查原文。", "").strip()
    return cleaned
_PRODUCT_STAGE_PATTERNS = [
    ("ga", "正式可用 (GA)", re.compile(r"(?:正式发布|正式上线|全面开放|开源权重|正式商用|general availability|\bga\b|v\d+\.\d+)", re.I)),
    ("beta", "测试开放 (Beta)", re.compile(r"(?:公测|内测|测试版|预览版|\bpreview\b|\bbeta\b|pre-release|\brc\d*\b)", re.I)),
    ("waitlist", "候补申请 (Waitlist)", re.compile(r"(?:\bwaitlist\b|候补|申请试用|预约体验)", re.I)),
    ("announced", "已宣布 (Announced)", re.compile(r"(?:首次亮相|正式公布|官方宣布|\bannounced\b)", re.I)),
]


_CROSS_LINGUAL_TOPIC_PAIRS: Tuple[Tuple[Tuple[str, ...], Tuple[str, ...]], ...] = (
    (("缅甸", "罗兴亚"), ("myanmar", "burma", "rohingya")),
    (("国际法院", "海牙"), ("icj", "world court", "international court", "hague", "genocide")),
    (("和解", "赔偿", "诉讼", "成瘾"), ("settle", "settlement", "lawsuit", "addiction", "suit")),
    (("霍尔木兹", "海峡"), ("hormuz", "strait")),
    (("伊朗", "美伊"), ("iran", "tehran")),
    (("油轮", "触雷", "航运"), ("tanker", "mine", "shipping", "vessel")),
    (("美联储", "联储", "议息"), ("fed", "fomc", "federal reserve", "powell")),
    (("加息", "降息", "利率"), ("rate hike", "rate cut", "interest rate", "bps")),
    (("以色列", "加沙"), ("israel", "gaza", "idf")),
    (("乌克兰", "俄乌", "泽连斯基", "普京"), ("ukraine", "russia", "kyiv", "moscow", "zelensky", "putin")),
    (("芯片", "半导体", "出口限制"), ("chip", "semiconductor", "gpu", "export")),
    (("并购", "收购", "洽购"), ("acquir", "buyout", "merger", "takeover")),
    (("关税", "贸易战"), ("tariff", "trade")),
)

_GOOGLE_NEWS_PREFIX_RE = re.compile(r"google\s*news", re.I)


def _clean_source_display_name(raw_name: Any, fallback_title: str = "") -> str:
    s = str(raw_name or "").strip()
    if s and not _GOOGLE_NEWS_PREFIX_RE.search(s):
        return s
    m = re.search(r"\s[-–—|｜]\s([^|\-–—｜]{2,36})$", str(fallback_title or "").strip())
    if m:
        cand = m.group(1).strip()
        if cand and not _GOOGLE_NEWS_PREFIX_RE.search(cand) and not cand.isdigit():
            return cand
    return "综合资讯"


def _has_cross_lingual_match(event_text: str, raw_text: str) -> bool:
    ev_low = (event_text or "").lower()
    raw_low = (raw_text or "").lower()
    if not ev_low or not raw_low:
        return False
    # Only engage cross-lingual match when event contains CJK and source text is predominantly non-CJK
    if len(re.findall(r"[\u4e00-\u9fff]", ev_low)) < 2:
        return False
    if len(re.findall(r"[\u4e00-\u9fff]", raw_low)) >= 4:
        return False

    raw_tokens = extract_tokens(raw_text)
    ev_tokens = extract_tokens(event_text)
    shared = ev_tokens & raw_tokens
    if any(len(t) >= 3 and t.isascii() and t not in {"sec", "usd", "ipo", "ceo", "cfo", "gdp", "news"} for t in shared):
        return True

    # Topic / proper-noun glossary bridges (Myanmar/ICJ, YouTube settlement, Hormuz, Fed, etc.)
    for zh_keys, en_keys in _CROSS_LINGUAL_TOPIC_PAIRS:
        if any(zk in ev_low for zk in zh_keys) and any(ek in raw_low for ek in en_keys):
            return True

    # Shared numeric scale bridge (e.g. "30亿" <-> "3 billion" / "$3b", "14%" <-> "14%")
    if ("30亿" in ev_low or "30 亿" in ev_low) and re.search(r"(?:\$?\s*3\s*(?:b\b|bn\b|billion)|3,000\s*m)", raw_low):
        return True
    ev_nums = {n for n in re.findall(r"\d+(?:\.\d+)?", ev_low) if len(n) >= 2}
    raw_nums = {n for n in re.findall(r"\d+(?:\.\d+)?", raw_low) if len(n) >= 2}
    if ev_nums and (ev_nums & raw_nums):
        return True
    return False


def _has_semantic_correspondence(event_text: str, raw_item: dict) -> bool:
    """Verify cited item reasonably relates to the generated event without crossing entity boundaries."""
    raw_title = str(raw_item.get("title") or "")
    if is_omnibus_digest_title(raw_title) and not is_omnibus_digest_title(event_text):
        return False
    if entities_conflict(event_text, raw_title, item_b=raw_item):
        return False
    raw_text = f"{raw_title} {raw_item.get('excerpt') or ''}"
    sim = title_similarity(event_text, raw_text)
    if sim >= 0.24:
        return True
    ev_tokens = extract_tokens(event_text)
    raw_tokens = extract_tokens(raw_text)
    shared = ev_tokens & raw_tokens
    non_generic_ascii = [t for t in shared if len(t) >= 4 and t.isascii() and t not in {"sec", "usd", "ai", "ipo", "ceo", "cfo", "gdp", "news"}]
    if non_generic_ascii and len(shared) >= 2:
        return True
    if _has_cross_lingual_match(event_text, raw_text):
        return True
    return len(shared) >= 3


_TECH_STAGE_CONTEXT_RE = re.compile(
    r"(?:模型|开源|ai\b|gemini|neon|carbon|hydrogen|gpt|claude|qwen|千问|kimi|deepseek|混元|vllm|llama|sdk|api|软件|芯片|算法|算力|agent|智能体|版本|github|hugging\s*face)",
    re.I,
)
_NON_TECH_POLITICAL_RE = re.compile(
    r"(?:总统|首相|总理|外交|海峡|霍尔木兹|欧盟|脱欧|关税|峰会|选举|国会|参议院|众议院|停火|军队|导弹|制裁|会晤|访华|中东)",
    re.I,
)


STAGE_CONFIDENCE_THRESHOLD = 0.70


def infer_material_stage(
    text: str,
    category: str = "tech",
    min_confidence: float = STAGE_CONFIDENCE_THRESHOLD,
) -> Optional[Dict[str, Any]]:
    """Classify product/model release stage strictly with confidence gating (threshold >= 0.70)."""
    if category not in {"tech"}:
        return None
    if _NON_TECH_POLITICAL_RE.search(text) and not _TECH_STAGE_CONTEXT_RE.search(text):
        return None
    if not _TECH_STAGE_CONTEXT_RE.search(text):
        return None
    for code, label, pat in _PRODUCT_STAGE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        conf = 0.68
        if _TECH_STAGE_CONTEXT_RE.search(text[:80]):
            conf += 0.10
        if m.start() < 90:
            conf += 0.10
        if re.search(r"(?:v\d+\.\d+|开源权重|\bapi\b|\bsdk\b|大模型|发布|上线|general availability)", text, re.I):
            conf += 0.08
        if _NON_TECH_POLITICAL_RE.search(text):
            conf -= 0.18
        if re.search(r"(?:可能|或将|传闻|rumor|reportedly|planned)", text, re.I) and code in {"announced", "beta", "ga"}:
            conf -= 0.12
        conf = round(max(0.0, min(0.99, conf)), 2)
        if conf < min_confidence:
            return None
        return {"stage": code, "label": label, "confidence": conf}
    return None


def extract_structured_fact_atoms(
    *,
    title: str,
    fact_summary: str,
    entities: List[str],
    sources: List[dict],
    evidence_status: str,
    first_discovered_at: str,
    category: str = "tech",
) -> List[Dict[str, Any]]:
    """
    Produce structured fact records (subject, action/metric, value/unit/period, attribution, source locator, revision)
    strictly bounded to observed source text so financial scopes and paper vs independent results never blend.
    """
    atoms: List[Dict[str, Any]] = []
    primary_subject = entities[0] if entities else "相关主体"
    stage = infer_material_stage(f"{title} {fact_summary}", category=category)

    # Detect quantitative metrics with explicit period/scope qualifier
    combined = f"{title} {fact_summary}"
    qty_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(万亿参数|亿参数|亿美元|亿元|万美元|万元|%|GWh|nm|TB|GB)",
        combined,
    )
    period = "同比 (YoY)" if "同比" in combined else ("环比 (QoQ)" if "环比" in combined else ("季度口径" if ("季" in combined or "Q" in combined) else ("至2030/远期预测" if "2030" in combined else "单次披露/未注明周期")))
    scope = "订单/合同/意向" if any(k in combined for k in ("订单", "意向", "合约", "采购")) else ("营收/业绩" if any(k in combined for k in ("营收", "收入", "利润", "财报")) else ("模型/产品/技术指标" if stage else "新闻事件陈述"))

    top_src = sources[0] if sources else None
    atoms.append(
        {
            "atom_id": f"fa_{abs(hash((title, primary_subject))) % 10**8}",
            "subject": primary_subject,
            "metric_or_action": title,
            "value": qty_match.group(1) if qty_match else (stage["label"] if stage else None),
            "unit": qty_match.group(2) if qty_match else ("可用状态" if stage else None),
            "period": period,
            "scope": scope,
            "fact_status": (
                "first_party_confirmed"
                if evidence_status == "official_confirmed"
                else ("reported_unconfirmed_by_filing" if _RUMOR_PREFIX_RE.search(combined) or evidence_status == "single_source" else "multi_source_reported")
            ),
            "attribution": top_src["source_name"] if top_src else "未核验出处",
            "source_ref": top_src["item_id"] if top_src else None,
            "source_url": top_src["url"] if top_src else None,
            "source_excerpt_or_locator": (top_src.get("excerpt") or top_src.get("title") or "")[:180] if top_src else "无合格出处定位",
            "published_at": top_src.get("published_at") if top_src else None,
            "discovered_at": first_discovered_at,
            "revision": 1,
        }
    )
    return atoms


def verify_and_enrich_event(
    raw_event: dict,
    *,
    category: str,
    input_batch_id: str,
    fetched_at_iso: str,
    ref_lookup: Dict[str, dict],
    id_lookup: Dict[str, dict],
    prev_events: List[dict],
    prev_batch_id: Optional[str],
    require_semantic_match: bool = True,
    used_event_ids: Optional[Set[str]] = None,
    identity_index: Optional[Dict[str, Any]] = None,
    sec_entity_status: Optional[Dict[str, dict]] = None,
    ordinal: int = 0,
) -> dict:
    """
    Verify an AI/reconciled event against the raw snapshot & first-party connectors:
      - Separates article_id, event_id, storyline_id (fixes omnibus event ID collisions)
      - Separates first_discovered_at, first_reported_at, latest_fact_update_at, latest_reported_at, fetched_at
      - Enforces reprint deduplication in independent_publisher_count
      - Enforces consistent unconfirmed-claim attribution across title, summary, and body
    """
    title = str(raw_event.get("title") or "").strip()
    fact_summary = str(raw_event.get("fact_summary") or raw_event.get("summary") or "").strip()
    ai_analysis = str(raw_event.get("ai_analysis") or raw_event.get("impact") or raw_event.get("comment") or "").strip()
    speculation = str(raw_event.get("speculation_or_outlook") or raw_event.get("prediction") or "").strip() or None

    raw_unverified = raw_event.get("unverified_claims")
    if isinstance(raw_unverified, list):
        unverified_claims = [str(x).strip() for x in raw_unverified if str(x).strip()]
    elif isinstance(raw_unverified, str) and raw_unverified.strip():
        unverified_claims = [raw_unverified.strip()]
    else:
        unverified_claims = []

    refs = raw_event.get("source_refs")
    if not isinstance(refs, list):
        refs = []
    explicit_ids = raw_event.get("item_ids")
    if isinstance(explicit_ids, list):
        refs = list(refs) + list(explicit_ids)

    valid_sources: List[dict] = []
    rejected_refs: List[dict] = []
    cross_lingual_candidates: List[Tuple[str, dict, str]] = []
    seen_item_ids: Set[str] = set()
    seen_canon_urls: Set[str] = set()
    event_match_text = f"{title} {fact_summary[:120]}"

    def _build_source_record(raw_item: dict, canon_url: str, *, recovered: bool = False) -> dict:
        item_title = str(raw_item.get("title") or "")
        pub_name = _clean_source_display_name(
            raw_item.get("publisher_name") or raw_item.get("source_name") or raw_item.get("source_id"),
            item_title or title,
        )
        return {
            "item_id": raw_item["item_id"],
            "article_id": raw_item["item_id"],
            "source_id": raw_item.get("source_id"),
            "source_name": pub_name,
            "publisher_name": pub_name,
            "source_status": "recovered_cross_lingual" if recovered else "ok",
            "source_kind": raw_item.get("source_kind", "news"),
            "source_tier": raw_item.get("source_tier") or "aggregator_lead",
            "publisher_family": raw_item.get("publisher_family") or get_publisher_family(raw_item.get("source_id", ""), canon_url),
            "is_reprint_copy": bool(raw_item.get("is_reprint_copy", False)),
            "title": raw_item.get("title"),
            "url": canon_url,
            "published_at": raw_item.get("published_at"),
            "published_at_source": raw_item.get("published_at_source"),
            "fetched_at": raw_item.get("fetched_at") or fetched_at_iso,
            "excerpt": raw_item.get("excerpt"),
            "thumbnail_url": raw_item.get("thumbnail_url"),
            "deep_fetch_status": raw_item.get("deep_fetch_status"),
        }

    for ref in refs:
        ref_key = str(ref).strip()
        if not ref_key:
            continue
        raw_item = ref_lookup.get(ref_key) or id_lookup.get(ref_key)
        if not raw_item:
            rejected_refs.append({"ref": ref_key, "reason": "引用 ID 不存在于当前输入批次"})
            continue
        item_id = raw_item["item_id"]
        if item_id in seen_item_ids:
            continue
        if raw_item.get("citable_as_news") is False or raw_item.get("source_kind") == "market_ticker":
            rejected_refs.append({"ref": ref_key, "reason": "行情/热股榜单页不能作为新闻事实依据"})
            continue
        canon_url = canonicalize_url(raw_item.get("canonical_url") or raw_item.get("url"))
        if not canon_url or is_generic_quote_or_homepage_url(canon_url, raw_item.get("source_id", "")):
            rejected_refs.append({"ref": ref_key, "reason": "来源链接为空、占位符(#)或泛化首页"})
            continue
        if require_semantic_match and not _has_semantic_correspondence(event_match_text, raw_item):
            raw_t = str(raw_item.get("title") or "")
            if (
                not is_omnibus_digest_title(raw_t)
                and not entities_conflict(event_match_text, raw_t, item_b=raw_item)
                and len(re.findall(r"[\u4e00-\u9fff]", raw_t)) < 4
            ):
                cross_lingual_candidates.append((ref_key, raw_item, canon_url))
            rejected_refs.append({"ref": ref_key, "reason": "引用条目与事件标题语义相关性不足"})
            continue
        if canon_url in seen_canon_urls:
            continue

        seen_item_ids.add(item_id)
        seen_canon_urls.add(canon_url)
        valid_sources.append(_build_source_record(raw_item, canon_url))

    # Recover valid cross-lingual cited refs when semantic matching dropped every ref on a real ZH/EN event
    if not valid_sources and cross_lingual_candidates:
        recovered_refs = set()
        for ref_key, raw_item, canon_url in cross_lingual_candidates[:4]:
            iid = raw_item["item_id"]
            if iid in seen_item_ids or canon_url in seen_canon_urls:
                continue
            seen_item_ids.add(iid)
            seen_canon_urls.add(canon_url)
            valid_sources.append(_build_source_record(raw_item, canon_url, recovered=True))
            recovered_refs.add(ref_key)
        if recovered_refs:
            rejected_refs = [r for r in rejected_refs if r.get("ref") not in recovered_refs]

    # Pre-resolved sources fallback (reconcile / unit tests)
    if not valid_sources and isinstance(raw_event.get("sources"), list):
        for s in raw_event["sources"]:
            if not isinstance(s, dict):
                continue
            canon_url = canonicalize_url(s.get("url"))
            sid = s.get("source_id", "")
            if not canon_url or is_generic_quote_or_homepage_url(canon_url, sid):
                continue
            item_id = s.get("item_id") or ""
            if item_id in seen_item_ids:
                continue
            seen_item_ids.add(item_id)
            pre_title = repair_mojibake(str(s.get("title") or ""))
            pub_name = _clean_source_display_name(s.get("publisher_name") or s.get("source_name") or sid, pre_title or title)
            valid_sources.append(
                {
                    "item_id": item_id,
                    "article_id": item_id,
                    "source_id": sid,
                    "source_name": pub_name,
                    "publisher_name": pub_name,
                    "source_status": s.get("source_status") or "ok",
                    "source_kind": s.get("source_kind", "news"),
                    "source_tier": s.get("source_tier") or "aggregator_lead",
                    "publisher_family": s.get("publisher_family") or get_publisher_family(sid, canon_url),
                    "is_reprint_copy": bool(s.get("is_reprint_copy", False)),
                    "title": pre_title,
                    "url": canon_url,
                    "published_at": s.get("published_at"),
                    "published_at_source": s.get("published_at_source"),
                    "fetched_at": s.get("fetched_at") or fetched_at_iso,
                    "excerpt": repair_mojibake(str(s.get("excerpt") or "")) or None,
                    "thumbnail_url": s.get("thumbnail_url"),
                    "deep_fetch_status": s.get("deep_fetch_status"),
                }
            )

    # Re-sort citations so first-party / direct media always outrank community forums & omnibus hotlists
    _COMMUNITY_IDS = {"coolapk", "tieba", "v2ex-share", "zhihu", "weibo", "douyin", "hupu"}
    valid_sources.sort(
        key=lambda s: (
            0 if s.get("source_tier") == "first_party" else (1 if s.get("source_tier") in {"direct_media", "tech_material"} else 2),
            1 if (s.get("source_id") in _COMMUNITY_IDS or s.get("source_kind") == "discussion" or s.get("source_id") == "aihot" or s.get("is_reprint_copy")) else 0,
            0 if s.get("excerpt") else 1,
            0 if s.get("thumbnail_url") else 1,
        )
    )

    # Detect syndicated reprints inside valid_sources cleanly so count isn't inflated
    seen_pub_titles: List[str] = []
    for s in valid_sources:
        stitle = str(s.get("title") or "")
        if any(title_similarity(stitle, pt) >= 0.85 for pt in seen_pub_titles):
            s["is_reprint_copy"] = True
        else:
            seen_pub_titles.append(stitle)

    distinct_families = {
        s.get("publisher_family") or get_publisher_family(s.get("source_id") or "")
        for s in valid_sources
        if s.get("source_id")
    }
    independent_families = {
        s.get("publisher_family") or get_publisher_family(s.get("source_id") or "")
        for s in valid_sources
        if s.get("source_id") and not s.get("is_reprint_copy")
    }
    if not independent_families and distinct_families:
        independent_families = distinct_families

    reprint_count = sum(1 for s in valid_sources if s.get("is_reprint_copy"))
    has_first_party = any(s.get("source_tier") in {"first_party", "tech_material"} and s.get("source_kind") in {"official_filing", "regulatory_release", "repo_release", "model_card"} for s in valid_sources)
    has_body_lead = any(s.get("deep_fetch_status") == "extracted_body_lead" for s in valid_sources)
    has_excerpt = any(bool(s.get("excerpt")) for s in valid_sources)

    if has_first_party and has_body_lead:
        material_depth = "first_party_and_body"
    elif has_first_party:
        material_depth = "first_party_or_metadata"
    elif has_body_lead:
        material_depth = "body_lead_extracted"
    elif has_excerpt:
        material_depth = "title_and_excerpt"
    else:
        material_depth = "title_only"

    if len(valid_sources) == 0:
        evidence_status = "needs_verification"
        reason_parts = ["未匹配到可供核验的原始新闻原文出处"]
        if rejected_refs:
            reason_parts.append("部分链接无效或非原文新闻页，暂不作为直达出处")
        evidence_reason = "；".join(reason_parts) + "，已归入待核实线索区"
    elif has_first_party:
        evidence_status = "official_confirmed"
        evidence_reason = f"包含官方/监管/代码仓库一手出处（独立来源 {len(independent_families)} 家），请仍以原文披露范围为准"
    elif len(independent_families) >= 2:
        evidence_status = "multi_source"
        depth_desc = "含摘要或正文首段" if (has_excerpt or has_body_lead) else "仅基于标题素材"
        evidence_reason = (
            f"已有 {len(independent_families)} 家独立媒体族"
            + (f"（另识别 {reprint_count} 条高度相似转载）" if reprint_count else "")
            + f"提及（{depth_desc}）；多源转载不代表官方公告已证实"
        )
    else:
        evidence_status = "single_source"
        depth_desc = "含摘要/首段" if (has_excerpt or has_body_lead) else "仅基于标题素材"
        evidence_reason = (
            f"目前仅见 1 家独立来源（共 {len(valid_sources)} 条引用含转载，{depth_desc}），尚未见独立渠道交叉或官方确认"
        )

    # Resolve canonical entities cleanly from text without letting stale canonical names self-perpetuate
    raw_entities = raw_event.get("entities")
    entities_list = [str(e).strip() for e in raw_entities if str(e).strip()][:6] if isinstance(raw_entities, list) else []
    canonical_name_set = {ed.canonical_name for ed in ENTITY_REGISTRY}
    non_canonical_hints = [e for e in entities_list if e not in canonical_name_set]
    matched_entity_objs = match_entities_with_reasons(f"{title} {fact_summary[:140]}", non_canonical_hints)
    # Normalize & merge entity alias variants (e.g. '英伟达' + '英伟达 (NVIDIA)' -> single canonical name)
    _ENTITY_CANON_MAP: Dict[str, str] = {}
    for ent_def in ENTITY_REGISTRY:
        cname = str(getattr(ent_def, "canonical_name", "") or "").strip()
        if not cname:
            continue
        _ENTITY_CANON_MAP[cname.lower()] = cname
        for al in getattr(ent_def, "aliases", ()) or ():
            a_low = str(al or "").strip().lower()
            if len(a_low) >= 2 and a_low not in ("ai", "us", "hk", "美元", "黄金"):
                _ENTITY_CANON_MAP[a_low] = cname

    matched_canonicals = {m["canonical_name"] for m in matched_entity_objs}
    cleaned_entities: List[str] = []
    seen_ent_norm: set[str] = set()
    for raw_e in entities_list:
        es = str(raw_e or "").strip()
        if not es:
            continue
        if es in canonical_name_set and es not in matched_canonicals:
            continue
        canonical_resolved = _ENTITY_CANON_MAP.get(es.lower(), es)
        # Do not merge distinct person names or short generic labels unless mapped in ENTITY_REGISTRY
        norm_key = canonical_resolved.lower()
        if norm_key not in seen_ent_norm:
            seen_ent_norm.add(norm_key)
            cleaned_entities.append(canonical_resolved)

    # Scrub internal pipeline jargon / placeholder tags / [R075] refs from public summaries
    _INTERNAL_JARGON_RE = re.compile(
        r"(?:\[?R\d{2,4}\]?\s*[:：]?\s*|"
        r"[（(]\s*[、,，]?\s*(?:原始素材多?)?仅含?标题\s*[)）]|"
        r"[、,，]?\s*(?:原始素材多?)?仅含?标题(?:[，,。；:\s]*(?:细节待查原文|具体[^。；;]*))?[。.]?\s*|"
        r"已拦截\s*\d+\s*条无效引用(?:（[^）]*）)?[；;，,]?\s*)",
        re.I,
    )
    fact_summary = _INTERNAL_JARGON_RE.sub("", fact_summary).strip()
    if ai_analysis:
        ai_analysis = _INTERNAL_JARGON_RE.sub("", str(ai_analysis)).strip() or None
    evidence_reason = _INTERNAL_JARGON_RE.sub("", evidence_reason).strip()
    if matched_entity_objs:
        for m in matched_entity_objs:
            if m["canonical_name"] not in cleaned_entities and len(cleaned_entities) < 6:
                cleaned_entities.append(m["canonical_name"])
    entities_list = cleaned_entities[:6]
    entity_ids = [m["entity_id"] for m in matched_entity_objs]

    # Claim-boundary & SEC EDGAR cross-corroboration on executive turnover claims
    title = dedupe_attribution_prefixes(title)
    fact_summary = dedupe_attribution_prefixes(fact_summary) or title
    indep_news_count = len(independent_families)
    title_is_speculative = bool(
        re.search(r"(?:传闻|爆料|网传|知情人士|消息人士|考虑|拟于|或将|可能|据称|被指)", title)
    )

    contradictions: List[str] = []
    regulatory_note: Optional[str] = None
    is_exec_turnover_claim = bool(
        re.search(r"(?:辞任|辞职|卸任|离职|接替|任命.*ceo|换帅)", title, re.I)
        and not re.search(r"(?:暴跌|重挫|抛售潮|拒绝复职|国会听证|会计做法)", title)
    )
    if sec_entity_status and is_exec_turnover_claim:
        for eid in entity_ids:
            sec_st = sec_entity_status.get(eid)
            if not sec_st:
                continue
            if not sec_st.get("has_recent_502_officer_change"):
                latest_8k = sec_st.get("latest_8k_date") or "近期"
                if indep_news_count >= 3 and not title_is_speculative:
                    regulatory_note = (
                        f"已获 {indep_news_count} 家独立媒体报道；截至 SEC EDGAR 最新 8-K（{latest_8k}）暂未见 Item 5.02 新增披露，请以公司官方文件为准。"
                    )
                else:
                    contradictions.append(
                        f"截至 SEC EDGAR 抓取时刻（最新 8-K 日期：{latest_8k}），未检索到 Item 5.02 高管辞任正式监管披露；该消息目前仍属媒体/社区传闻阶段。"
                    )
            elif any(g in f"{title} {fact_summary}" for g in ("婚外情", "间谍", "丑闻", "重返", "施压")):
                if indep_news_count >= 3 and not title_is_speculative:
                    regulatory_note = "SEC 8-K (Item 5.02) 已记录高管变动，具体衍生原因或复职进展以董事会及官方公告为准。"
                else:
                    contradictions.append(
                        "SEC 8-K (Item 5.02) 已确认高管人事变动申报，但关于具体离任原因或重返职位的衍生传闻未见官方监管文件背书。"
                    )

    broadly_confirmed_event = (
        indep_news_count >= 2
        and not contradictions
        and not title_is_speculative
    )
    needs_rumor_qualifier = (
        evidence_status != "official_confirmed"
        and (
            bool(contradictions)
            or (bool(unverified_claims) and not broadly_confirmed_event)
        )
    )
    attribution_warning = None
    if needs_rumor_qualifier:
        attribution_warning = (
            contradictions[0]
            if contradictions
            else "该事件包含未获官方披露证实的说法，标题与摘要已保留报道归因限定。"
        )
        if not _RUMOR_PREFIX_RE.search(title) and not title.startswith("【待官方证实"):
            title = f"报道称：{title}"
        if (
            fact_summary
            and "尚未见官方披露确认" not in fact_summary
            and "待官方" not in fact_summary
            and "报道称" not in fact_summary
            and "传闻" not in fact_summary
        ):
            fact_summary = f"【据关联报道/尚未见官方披露确认】{fact_summary}"
        title = dedupe_attribution_prefixes(title)
        fact_summary = dedupe_attribution_prefixes(fact_summary)

    # Bug B fix: Strictly separate event timestamps; prevent bundled historical filings from pulling new 8-K dates back months
    pub_dates = sorted([s["published_at"] for s in valid_sources if s.get("published_at")])
    first_reported_at = pub_dates[0] if pub_dates else None
    latest_reported_at = pub_dates[-1] if pub_dates else None
    if has_first_party and len(pub_dates) >= 2:
        d0 = parse_iso_datetime(pub_dates[0])
        d1 = parse_iso_datetime(pub_dates[-1])
        if d0 and d1 and (d1 - d0).days > 14:
            summary_blob = f"{title} {fact_summary}"
            matched_dates = [
                p for p in pub_dates
                if p[:10] in summary_blob or f"{int(p[5:7])}月{int(p[8:10])}日" in summary_blob
            ]
            if matched_dates:
                first_reported_at = matched_dates[0]
            else:
                first_reported_at = latest_reported_at

    # Cross-batch match against previous smart batch AND persistent identity_index
    followup = None
    prev_first_discovered = None
    prev_storyline_id = None
    best_prev = None
    best_sim = 0.0
    curr_item_ids = {s.get("item_id") for s in valid_sources if s.get("item_id")}

    if prev_events and prev_batch_id:
        for pe in prev_events:
            pe_item_ids = {s.get("item_id") for s in pe.get("sources", []) if s.get("item_id")}
            # Note: shared omnibus article IDs alone do NOT match two distinct events!
            # Only match by shared ID if title similarity >= 0.35 or same single-article primary source
            title_sim = title_similarity(title, pe.get("title", ""))
            if pe_item_ids and curr_item_ids and (pe_item_ids & curr_item_ids) and title_sim >= 0.35:
                best_prev = pe
                best_sim = max(title_sim, 0.9)
                break
            if title_sim > best_sim:
                best_sim = title_sim
                best_prev = pe

        if best_prev is not None and best_sim >= 0.42:
            prev_first_discovered = best_prev.get("first_discovered_at") or best_prev.get("fetched_at")
            prev_storyline_id = best_prev.get("storyline_id")
            prev_src_count = len(best_prev.get("sources", []))
            curr_src_count = len(valid_sources)
            prev_indep = best_prev.get("independent_publisher_count") or prev_src_count
            delta_indep = len(independent_families) - prev_indep
            delta_total = curr_src_count - prev_src_count
            if delta_indep > 0:
                delta_note = f"较上期新增 {delta_indep} 家独立来源报道"
            elif delta_total > 0:
                delta_note = f"新增 {delta_total} 条跟进/转载出处（核心事实待对比差异）"
            elif best_prev.get("fact_summary") != fact_summary:
                delta_note = "同一事件在最新批次出现表述修订或信息补充"
            else:
                delta_note = "在上期简报中已出现，本批持续关注（暂无新增独立变化）"
            followup = {
                "is_continuing": True,
                "prev_batch_id": prev_batch_id,
                "prev_event_id": best_prev.get("event_id"),
                "prev_title": best_prev.get("title"),
                "delta_note": delta_note,
            }

    # Bug A fix: Event ID derived from semantic event fingerprint, guaranteed unique in batch
    base_event_id = make_event_id(category, valid_sources[0]["item_id"] if valid_sources else None, title, entities_list)
    if used_event_ids is not None:
        event_id = ensure_unique_event_id(base_event_id, used_event_ids, category=category, title=title, ordinal=ordinal)
    else:
        event_id = base_event_id

    storyline_id = prev_storyline_id or make_storyline_id(category, title, entities_list)
    first_discovered_at = prev_first_discovered or fetched_at_iso
    # Only treat latest_reported_at as latest_fact_update_at when the event actually has new/substantive non-reprint facts
    has_substantive_fact_update = followup is None or (best_prev and best_prev.get("fact_summary") != fact_summary)
    latest_fact_update_at = (
        latest_reported_at if has_substantive_fact_update else (best_prev.get("latest_fact_update_at") if best_prev else first_reported_at)
    )
    # Backward-compatible published_at prefers factual origin over late syndicate reprint time
    honest_published_at = first_reported_at if len(valid_sources) == reprint_count + 1 and latest_reported_at != first_reported_at else (latest_fact_update_at or first_reported_at)

    fact_atoms = extract_structured_fact_atoms(
        title=title,
        fact_summary=fact_summary,
        entities=entities_list,
        sources=valid_sources,
        evidence_status=evidence_status,
        first_discovered_at=first_discovered_at,
        category=category,
    )

    stage_info = infer_material_stage(f"{title} {fact_summary}", category=category)

    # Event occurrence date & stale-rehash detection (Issues #38, #39)
    fetched_dt = parse_iso_datetime(fetched_at_iso)
    raw_ev_date = str(raw_event.get("event_date") or "").strip()
    event_date: Optional[str] = raw_ev_date[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw_ev_date) else None
    event_date_source = "llm_extracted" if event_date else "reported_timestamp"
    if not event_date:
        dm_full = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", f"{title} {fact_summary}")
        if dm_full:
            try:
                yr, mo, dy = int(dm_full.group(1)), int(dm_full.group(2)), int(dm_full.group(3))
                if 2020 <= yr <= 2030 and 1 <= mo <= 12 and 1 <= dy <= 31:
                    event_date = f"{yr:04d}-{mo:02d}-{dy:02d}"
                    event_date_source = "text_explicit_date"
            except Exception:
                pass
    if not event_date and first_reported_at:
        event_date = first_reported_at[:10]
        event_date_source = "first_reported_at"
    elif not event_date:
        event_date = next((str(s.get("event_date"))[:10] for s in valid_sources if s.get("event_date")), None)
        if event_date:
            event_date_source = "source_event_date"

    is_stale_rehash = bool(raw_event.get("is_stale_rehash", False))
    if not is_stale_rehash and event_date and fetched_dt:
        ev_dt = parse_iso_datetime(f"{event_date}T00:00:00+08:00")
        if ev_dt is not None and (fetched_dt - ev_dt).days > 14:
            is_stale_rehash = True

    if has_first_party:
        time_trust_level = "verified_official"
    elif any(s.get("published_at") and s.get("published_at_source") != "search_grounding" for s in valid_sources):
        time_trust_level = "article_timestamp"
    elif any(s.get("published_at") for s in valid_sources):
        time_trust_level = "search_grounding"
    else:
        time_trust_level = "fetch_fallback"

    # Sentiment consistency guard (#48)
    raw_sentiment = raw_event.get("sentiment")
    sentiment = raw_sentiment
    bear_hits = bool(re.search(r"(?:暴跌|重挫|下挫|大跌|跳水|破发|抹去.*涨幅|调查|泄密|隐私泄露|空袭|触雷|违约|停飞)", title))
    bull_hits = bool(re.search(r"(?:暴涨|飙升|大涨|创新高|创纪录.*募资|和平协议|停火协议|降息|正式开源)", title))
    if bear_hits and not bull_hits and raw_sentiment == "Bullish":
        sentiment = "Bearish"
    elif bull_hits and not bear_hits and raw_sentiment == "Bearish":
        sentiment = "Bullish"
    elif bear_hits and bull_hits and raw_sentiment in {"Bullish", "Bearish"}:
        sentiment = "Mixed"

    # Quality & transparent downweight reasons (#27, #50)
    downweight_reasons: List[str] = []
    if attribution_warning:
        downweight_reasons.append("含未证实归因限定 (-10)")
    if material_depth == "title_only":
        downweight_reasons.append("仅含标题素材 (-8)")
    if is_stale_rehash:
        downweight_reasons.append("旧事重提 (>14天)")
    if honest_published_at and fetched_dt:
        pub_dt_chk = parse_iso_datetime(honest_published_at)
        if pub_dt_chk is not None:
            age_h = (fetched_dt - pub_dt_chk).total_seconds() / 3600.0
            if age_h > 168:
                downweight_reasons.append("发布超过7天 (-36)")
            elif age_h > 48:
                downweight_reasons.append("发布超过48小时 (-18)")

    quality_flags: List[str] = []
    if is_stale_rehash:
        quality_flags.append("stale_rehash")
    if time_trust_level == "fetch_fallback":
        quality_flags.append("missing_pub_time")
    if any(s.get("degraded") for s in valid_sources):
        quality_flags.append("degraded_source")

    primary_src = valid_sources[0] if valid_sources else None
    primary_publisher = (
        str(primary_src.get("publisher_name") or primary_src.get("source_name") or "").strip()
        if primary_src
        else None
    )
    source_status = (
        "recovered_cross_lingual"
        if valid_sources and all(s.get("source_status") == "recovered_cross_lingual" for s in valid_sources)
        else ("ok" if valid_sources else "missing")
    )

    return {
        "schema_version": "4.1",
        "event_id": event_id,
        "storyline_id": storyline_id,
        "article_ids": [s["item_id"] for s in valid_sources],
        "legacy_event_ids": [raw_event["event_id"]] if raw_event.get("event_id") and raw_event.get("event_id") != event_id else [],
        "title": title,
        "category": category,
        "entities": entities_list,
        "entity_ids": entity_ids,
        "entity_confidences": {
            m["canonical_name"]: m.get("confidence", 1.0)
            for m in matched_entity_objs
            if m.get("canonical_name")
        },
        "matched_entities": matched_entity_objs,
        "importance": raw_event.get("importance", "normal") if raw_event.get("importance") in {"high", "medium", "normal"} else "normal",
        "sentiment": sentiment,
        "special_note": raw_event.get("special_note"),
        "material_stage": stage_info["stage"] if stage_info else None,
        "material_stage_label": stage_info["label"] if stage_info else None,
        "material_stage_confidence": stage_info["confidence"] if stage_info else None,
        "thumbnail_url": (
            raw_event.get("thumbnail_url")
            or next((s.get("thumbnail_url") for s in valid_sources if s.get("thumbnail_url")), None)
        ),
        "publisher_name": primary_publisher,
        "source_status": source_status,
        "evidence_status": evidence_status,
        "evidence_label": EVIDENCE_LABELS[evidence_status],
        "evidence_status_reason": evidence_reason,
        "attribution_warning": attribution_warning,
        "regulatory_note": regulatory_note,
        "contradictions": contradictions,
        "downweight_reasons": downweight_reasons,
        "quality_flags": quality_flags,
        "material_depth": material_depth,
        "source_count": len(valid_sources),
        "platform_count": len(distinct_families),
        "independent_publisher_count": len(independent_families),
        "reprint_count": reprint_count,
        "published_at": honest_published_at,
        "event_date": event_date,
        "event_time": first_reported_at or honest_published_at or event_date,
        "stale": is_stale_rehash,
        "event_date_source": event_date_source,
        "is_stale_rehash": is_stale_rehash,
        "time_trust_level": time_trust_level,
        "time_confidence": time_trust_level,
        "first_discovered_at": first_discovered_at,
        "first_reported_at": first_reported_at,
        "latest_fact_update_at": latest_fact_update_at,
        "latest_reported_at": latest_reported_at,
        "fetched_at": fetched_at_iso,
        "input_batch_id": input_batch_id,
        "fact_summary": fact_summary,
        "fact_atoms": fact_atoms,
        "ai_analysis": ai_analysis,
        "unverified_claims": unverified_claims,
        "speculation_or_outlook": speculation,
        "sources": valid_sources,
        "verification": {
            "all_refs_valid": len(rejected_refs) == 0 and len(valid_sources) > 0,
            "has_primary_url": len(valid_sources) > 0,
            "rejected_refs": rejected_refs,
            "has_first_party": has_first_party,
        },
        "followup": followup,
        "is_new_in_batch": followup is None,
        "update_kind": (
            "new_discovery"
            if followup is None
            else ("new_fact_update" if has_substantive_fact_update else "continuing_coverage")
        ),
    }


def validate_published_briefing(doc: dict) -> Tuple[bool, List[str]]:
    """Pre-publish V3 sanity gate: metadata, unique event_ids, storylines, valid non-# URLs."""
    errors: List[str] = []
    for field in ("batch_id", "input_batch_id", "input_cutoff_at", "generated_at", "category"):
        if not doc.get(field):
            errors.append(f"Missing required metadata field: {field}")

    events = doc.get("events", [])
    if not isinstance(events, list) or len(events) == 0:
        errors.append("Briefing contains 0 events")
        return False, errors

    seen_event_ids: Set[str] = set()
    verified_count = 0
    for idx, ev in enumerate(events):
        ev_id = ev.get("event_id")
        if not ev_id:
            errors.append(f"Event {idx} missing event_id")
        elif ev_id in seen_event_ids:
            errors.append(f"Duplicate event_id {ev_id} detected in category {doc.get('category')}")
        else:
            seen_event_ids.add(ev_id)

        if not ev.get("storyline_id"):
            errors.append(f"Event {idx} ({ev.get('title')}) missing storyline_id")

        status = ev.get("evidence_status")
        sources = ev.get("sources", [])
        if status != "needs_verification":
            if not sources:
                errors.append(f"Event {idx} ({ev.get('title')}) marked {status} but has 0 sources")
            for s in sources:
                u = s.get("url", "")
                if not canonicalize_url(u) or is_generic_quote_or_homepage_url(u, s.get("source_id", "")):
                    errors.append(f"Event {idx} has invalid source URL: {u!r}")
            verified_count += 1

    if verified_count == 0:
        errors.append("No verified events with valid primary URLs in briefing")

    return len(errors) == 0, errors
