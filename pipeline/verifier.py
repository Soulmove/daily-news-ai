"""Deterministic V3 verification gate: independent identities, separated timestamps, claim boundaries & structured facts."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from pipeline.connectors.base import repair_mojibake
from pipeline.dedup import entities_conflict, extract_tokens, get_publisher_family, is_omnibus_digest_title, title_similarity
from pipeline.time_utils import parse_iso_datetime
from pipeline.entities import match_entities_with_reasons
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
    ("ga", "正式可用 (GA)", re.compile(r"(?:正式发布|正式上线|全面开放|开源权重|正式商用|general availability|ga\b|v\d+\.\d+)", re.I)),
    ("beta", "测试开放 (Beta)", re.compile(r"(?:公测|内测|测试版|预览版|preview|beta|pre-release|rc\d*)", re.I)),
    ("waitlist", "候补申请 (Waitlist)", re.compile(r"(?:waitlist|候补|申请试用|预约体验)", re.I)),
    ("announced", "已宣布 (Announced)", re.compile(r"(?:首次亮相|公布|宣布|预告|剧透|planned|announced)", re.I)),
]


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
    return len(shared) >= 3


def infer_material_stage(text: str) -> Optional[Dict[str, str]]:
    """Classify product/model release stage so announced != beta != GA."""
    for code, label, pat in _PRODUCT_STAGE_PATTERNS:
        if pat.search(text):
            return {"stage": code, "label": label}
    return None


def extract_structured_fact_atoms(
    *,
    title: str,
    fact_summary: str,
    entities: List[str],
    sources: List[dict],
    evidence_status: str,
    first_discovered_at: str,
) -> List[Dict[str, Any]]:
    """
    Produce structured fact records (subject, action/metric, value/unit/period, attribution, source locator, revision)
    strictly bounded to observed source text so financial scopes and paper vs independent results never blend.
    """
    atoms: List[Dict[str, Any]] = []
    primary_subject = entities[0] if entities else "相关主体"
    stage = infer_material_stage(f"{title} {fact_summary}")

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
    seen_item_ids: Set[str] = set()
    seen_canon_urls: Set[str] = set()
    event_match_text = f"{title} {fact_summary[:120]}"

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
            rejected_refs.append({"ref": ref_key, "reason": "引用条目与事件标题语义相关性不足"})
            continue
        if canon_url in seen_canon_urls:
            continue

        seen_item_ids.add(item_id)
        seen_canon_urls.add(canon_url)
        valid_sources.append(
            {
                "item_id": item_id,
                "article_id": item_id,
                "source_id": raw_item.get("source_id"),
                "source_name": raw_item.get("source_name") or raw_item.get("source_id"),
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
                "deep_fetch_status": raw_item.get("deep_fetch_status"),
            }
        )

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
            valid_sources.append(
                {
                    "item_id": item_id,
                    "article_id": item_id,
                    "source_id": sid,
                    "source_name": s.get("source_name") or sid,
                    "source_kind": s.get("source_kind", "news"),
                    "source_tier": s.get("source_tier") or "aggregator_lead",
                    "publisher_family": s.get("publisher_family") or get_publisher_family(sid, canon_url),
                    "is_reprint_copy": bool(s.get("is_reprint_copy", False)),
                    "title": repair_mojibake(str(s.get("title") or "")),
                    "url": canon_url,
                    "published_at": s.get("published_at"),
                    "published_at_source": s.get("published_at_source"),
                    "fetched_at": s.get("fetched_at") or fetched_at_iso,
                    "excerpt": repair_mojibake(str(s.get("excerpt") or "")) or None,
                    "deep_fetch_status": s.get("deep_fetch_status"),
                }
            )

    # Re-sort citations so primary / excerpted sources always outrank omnibus digests
    valid_sources.sort(
        key=lambda s: (
            0 if s.get("source_tier") in {"first_party", "tech_material"} else 1,
            1 if (s.get("source_id") == "aihot" or s.get("is_reprint_copy")) else 0,
            0 if s.get("excerpt") else 1,
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
        reason_parts = ["未匹配到满足校验规则的原始新闻出处"]
        if rejected_refs:
            reason_parts.append(f"已拦截 {len(rejected_refs)} 条无效引用（{rejected_refs[0]['reason']}）")
        evidence_reason = "；".join(reason_parts) + "，已进入待核实状态"
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

    # Resolve canonical entities with disambiguation
    raw_entities = raw_event.get("entities")
    entities_list = [str(e).strip() for e in raw_entities if str(e).strip()][:6] if isinstance(raw_entities, list) else []
    matched_entity_objs = match_entities_with_reasons(f"{title} {fact_summary[:140]}", entities_list)
    entity_ids = [m["entity_id"] for m in matched_entity_objs]
    if not entities_list and matched_entity_objs:
        entities_list = [m["canonical_name"] for m in matched_entity_objs[:5]]

    # SEC EDGAR cross-corroboration on extraordinary executive departure rumors
    contradictions: List[str] = []
    if sec_entity_status and any(k in title for k in ("辞任", "辞职", "卸任", "离职", "重返", "接替")):
        for eid in entity_ids:
            sec_st = sec_entity_status.get(eid)
            if not sec_st:
                continue
            if not sec_st.get("has_recent_502_officer_change"):
                latest_8k = sec_st.get("latest_8k_date") or "近期"
                contradictions.append(
                    f"截至 SEC EDGAR 抓取时刻（最新 8-K 日期：{latest_8k}），未检索到 Item 5.02 高管辞任正式监管披露；该消息目前仍属媒体/社区传闻阶段。"
                )
            elif any(g in f"{title} {fact_summary}" for g in ("婚外情", "间谍", "丑闻", "重返", "施压")):
                contradictions.append(
                    "SEC 8-K (Item 5.02) 已确认高管人事变动申报，但关于具体离任原因或重返职位的衍生传闻未见官方监管文件背书。"
                )

    # Claim-boundary consistency guard: only attach rumor prefixes to genuine rumors/contradictions,
    # NEVER poison broadly confirmed multi-source live events (e.g. televised state visits / summits)
    # solely because one minor speculative detail appeared in unverified_claims.
    title = dedupe_attribution_prefixes(title)
    fact_summary = dedupe_attribution_prefixes(fact_summary) or title
    indep_news_count = len(independent_families)
    title_is_speculative = bool(
        re.search(r"(?:传闻|爆料|网传|知情人士|消息人士|考虑|拟于|或将|可能|据称|被指)", title)
    )
    broadly_confirmed_event = (
        indep_news_count >= 3
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
    )

    stage_info = infer_material_stage(f"{title} {fact_summary}")

    return {
        "schema_version": "3.0",
        "event_id": event_id,
        "storyline_id": storyline_id,
        "article_ids": [s["item_id"] for s in valid_sources],
        "legacy_event_ids": [raw_event["event_id"]] if raw_event.get("event_id") and raw_event.get("event_id") != event_id else [],
        "title": title,
        "category": category,
        "entities": entities_list,
        "entity_ids": entity_ids,
        "matched_entities": matched_entity_objs,
        "importance": raw_event.get("importance", "normal") if raw_event.get("importance") in {"high", "medium", "normal"} else "normal",
        "sentiment": raw_event.get("sentiment"),
        "special_note": raw_event.get("special_note"),
        "material_stage": stage_info["stage"] if stage_info else None,
        "material_stage_label": stage_info["label"] if stage_info else None,
        "evidence_status": evidence_status,
        "evidence_label": EVIDENCE_LABELS[evidence_status],
        "evidence_status_reason": evidence_reason,
        "attribution_warning": attribution_warning,
        "contradictions": contradictions,
        "material_depth": material_depth,
        "source_count": len(valid_sources),
        "platform_count": len(distinct_families),
        "independent_publisher_count": len(independent_families),
        "reprint_count": reprint_count,
        "published_at": honest_published_at,
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
