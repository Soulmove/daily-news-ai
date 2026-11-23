"""Unified Heavy-Rating Classifier & Cross-Stream Alignment (Today Briefings <-> 7x24 Live Wire)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from pipeline.dedup import (
    has_authoritative_primary_source,
    is_hotlist_aggregator_source,
    smart_truncate,
    title_similarity,
)
from pipeline.time_utils import now_shanghai, parse_iso_datetime, to_iso_shanghai


HEAVY_NOISE_EXCLUDE_RE = re.compile(
    r"(?:首次覆盖.{0,18}(?:买入|增持|中性|跑赢|推荐|持有)评级|"
    r"给予.{0,10}(?:买入|增持|中性|跑赢|推荐|持有)评级|"
    r"维持.{0,12}(?:买入|增持|跑赢|推荐)评级|"
    r"(?:上调|下调)目标价至|券商研报|评级报告|"
    r"降价通知|api\s*降价|调用降价|限时降价|优惠活动|促销|"
    r"夜盘普遍|夜盘微涨|夜盘涨|夜盘跌|盘前微涨|盘前涨|盘前跌|盘前涨跌不一|"
    r"早间要闻|要闻汇总|盘前必读|早报汇总|午间公告|复盘汇总|"
    r"联盟.{0,8}成立|协会.{0,8}成立|发展联盟|正式成立|行业论坛|"
    r"中间价|上海钢联|现货报价|提议设|提议(?:将|用).{0,24}限制|呼吁限制|"
    r"涨停|持续活跃|短剧|影视股|概念股拉升|盘中拉升|探底回升|重仓股曝光|"
    r"离婚案|财产分割|离婚诉讼|和解方案|赡养费|婚变|SK集团会长.{0,12}离婚|"
    r"台湾|台湾地区|只要.*诉求|立场明确|呼吁对话|传递想法|保持密切对话)",
    re.I,
)

GEO_MILITARY_HEAVY_RE = re.compile(
    r"(?:军舰.{0,18}(?:爆炸|沉没|遇袭|被击沉)|"
    r"(?:港口|海军基地|油轮|商船|战舰).{0,16}(?:遭|遭遇|爆发).{0,14}(?:无人机|无人艇|导弹|鱼雷|水雷|袭击|爆炸)|"
    r"霍尔木兹海峡封锁|"
    r"美伊.{0,14}(?:开火|空袭|遇袭|停火|爆发冲突)|"
    r"俄乌.{0,14}(?:停火|和平协议|大规模袭击)|"
    r"中东.{0,14}(?:空袭|开火|全面升级))",
    re.I,
)

MARKET_SEMI_HEAVY_RE = re.compile(
    r"(?:(?:KOSPI|日经225|恒生指数|恒生科技|纳指|标普500|创业板指).{0,16}(?:大跌|暴跌|重挫|跌超|飙升|大涨)\s*[2-9](?:\.\d+)?%|"
    r"(?:HBM|高带宽内存).{0,18}(?:售罄|产能.{0,6}满载|锁单|涨价)|"
    r"美光.{0,16}(?:320亿|百亿|HBM)|"
    r"(?:暴跌|重挫|闪崩)超?\s*[3-9](?:\.\d+)?%)",
    re.I,
)


def _norm_title_text(title: str) -> str:
    return re.sub(r"[\s\-_·:：,，.。!！?？()（）\[\]【】'\"]+", "", (title or "").lower())


def heavy_topic_key(norm_or_title: str) -> Optional[str]:
    n = _norm_title_text(norm_or_title)
    if "韩国" in n and any(k in n for k in ("稳", "平准", "股市", "财长", "财政部")):
        return "korea_stab"
    if "主动etf" in n:
        return "cn_active_etf"
    if "黄仁勋" in n and "英伟达" in n:
        return "nvda_jensen"
    if "融资保证金" in n and "80%" in n:
        return "margin_80"
    if "黄金" in n and any(k in n for k in ("反弹", "杀跌", "突破36", "回升")):
        return "gold_rebound"
    if ("韩国" in n or "kospi" in n) and any(k in n for k in ("大跌", "跌超", "3.32", "暴跌", "重挫")):
        return "kospi_drop"
    if "美光" in n and any(k in n for k in ("hbm", "320亿", "售罄")):
        return "micron_hbm"
    if "利比亚" in n and any(k in n for k in ("军舰", "沉没", "无人艇", "无人机", "爆炸")):
        return "libya_warship"
    if "spacex" in n and "440亿" in n:
        return "spacex_44b"
    if "cop31" in n and "气候" in n:
        return "cop31_climate"
    if "加州" in n and "openai" in n:
        return "ca_sues_openai"
    if "欧盟" in n and "印尼" in n and "自贸" in n:
        return "eu_id_fta"
    return None


def infer_heavy_reason_tag(title: str, summary_or_excerpt: str = "") -> str:
    """Return qualitative Heavy category suffix prioritizing title subject."""
    def _classify(chunk: str, *, allow_fallback: bool = False) -> Optional[str]:
        if not chunk:
            return None
        if re.search(r"黄金|金价|白银|贵金属|原油|油价|布伦特|WTI|铜价|大宗", chunk, re.I):
            return "大宗与市场剧震"
        if re.search(
            r"军舰|航母|沉没|被击沉|无人艇|无人机袭击|空袭|导弹袭击|港口爆炸|停火协议|霍尔木兹|俄乌|美伊|以伊|冲突升级",
            chunk,
            re.I,
        ):
            return "地缘与军事突发"
        if re.search(
            r"证监会|沪深北|沪深交易所|上交所|深交所|主动\s*ETF|融资保证金|两融|降费|人民银行|中国央行|央行|国务院|SEC|出口管制|实体清单|关税|禁令|稳定基金|平准基金|稳市基金|反垄断|自贸协定|自由贸易协定",
            chunk,
            re.I,
        ) and not ("国内银行" in chunk or "商业银行" in chunk):
            return "监管新政"
        if re.search(
            r"黎曼猜想|Mathlib|Lean|Nature|Science|GPT-\d|Claude|Gemini|DeepSeek|Qwen|GLM|NVIDIA.*VLA|Vera\s*Rubin|可回收火箭|神舟|星舰|BepiColombo|开源.{0,10}模型|芯片架构",
            chunk,
            re.I,
        ):
            return "科研/模型里程碑"
        lead_clause = re.split(r"[，,；;。]", chunk, maxsplit=1)[0]
        leader_lead = bool(re.search(r"^(?:中美元首|习近平|特朗普|美国总统|美联储|鲍威尔|贝森特|日本央行|欧央行)", lead_clause))
        if not leader_lead and re.search(
            r"英伟达董事会|董事会|CEO|马斯克|SpaceX|特斯拉|Anthropic|OpenAI|Meta|苹果|微软|起诉",
            chunk,
            re.I,
        ):
            return "巨头重大变动"
        if re.search(
            r"中美元首|习近平|特朗普|总统|总理|财长|贝森特|美联储|FOMC|鲍威尔|欧央行|日本央行|COP31|气候大会|气候变化大会|外交部|联合宣言|联合声明",
            chunk,
            re.I,
        ):
            return "元首/央行表态"
        if re.search(r"暴跌|涨超|跌超|飙升|破发|腰斩|熔断|闪崩|危机|抛售|IPO|垃圾级|440亿|比特币|市值", chunk, re.I):
            return "市场剧震"
        return "巨头重大变动" if allow_fallback else None

    hit = _classify(title or "", allow_fallback=False)
    if hit:
        return hit
    return _classify(summary_or_excerpt or "", allow_fallback=True) or "巨头重大变动"


def _event_ts_age_hours(ev: dict, now_dt: Any) -> Tuple[str, float]:
    ts = str(ev.get("latest_reported_at") or ev.get("first_reported_at") or ev.get("published_at") or "").strip()
    dt = parse_iso_datetime(ts) if ts else None
    if dt is None:
        return to_iso_shanghai(now_dt), 0.0
    return to_iso_shanghai(dt), max(0.0, (now_dt - dt).total_seconds() / 3600.0)


def sync_today_heavy_into_live_wire(
    cat_docs: Dict[str, dict],
    wire_doc: Dict[str, Any],
    now_dt: Any = None,
    *,
    window_hours: float = 16.0,
    min_heavy: int = 8,
    max_heavy: int = 12,
    max_total: int = 165,
) -> Dict[str, Any]:
    """
    Bidirectionally align Today Heavy (S/A) events with 7x24 Live Wire Heavy picks:
      - Purge brokerage buy/rating noise, corporate family gossip & hotlist fluff from Heavy
      - Promote geopolitical/military attacks & semi/index market shocks to Heavy
      - Tag gold/commodity rebounds strictly as 大宗与市场剧震
      - Sync recent 16h Today S/A events into Live Wire Heavy (upgrading matches in place, inserting missing ones)
      - Enforce 8-12 deduplicated high-purity Heavy items while keeping <= 165 total wires
    """
    now_ref = now_dt or now_shanghai()
    items: List[Dict[str, Any]] = [dict(it) for it in (wire_doc.get("items") or []) if isinstance(it, dict)]

    # 1. Clean & unify existing wire items' heavy classification & tags
    for it in items:
        title = str(it.get("title") or "")
        exc = str(it.get("excerpt") or "")
        src_name = str(it.get("source_name") or "")
        src_id = str(it.get("source_id") or "")
        if HEAVY_NOISE_EXCLUDE_RE.search(title) or is_hotlist_aggregator_source(src_id, src_name):
            it["severity_tier"] = "B"
            it["importance"] = "normal"
            it["heavy_reason_tag"] = None
            continue
        if GEO_MILITARY_HEAVY_RE.search(title):
            it["severity_tier"] = "S" if it.get("severity_tier") == "S" else "A"
            it["importance"] = "high"
            it["heavy_reason_tag"] = "地缘与军事突发"
            continue
        if MARKET_SEMI_HEAVY_RE.search(f"{title} {exc}"):
            it["severity_tier"] = "S" if it.get("severity_tier") == "S" else "A"
            it["importance"] = "high"
            it["heavy_reason_tag"] = infer_heavy_reason_tag(title, exc)
            continue
        if it.get("importance") == "high" or it.get("severity_tier") in {"S", "A"}:
            if it.get("severity_tier") not in {"S", "A"}:
                it["severity_tier"] = "A"
            it["importance"] = "high"
            it["heavy_reason_tag"] = infer_heavy_reason_tag(title, exc)

    # 2. Collect Today Heavy events (S/A within 16h window first, then fallback S/A if needed to hit floor)
    heavy_events: List[Tuple[int, float, dict]] = []
    for cat in ("finance", "global", "tech", "general"):
        evs = (cat_docs.get(cat) or {}).get("events") or []
        for ev in evs:
            if not isinstance(ev, dict):
                continue
            tier = str(ev.get("severity_tier") or "")
            if tier not in {"S", "A"}:
                continue
            t_ev = str(ev.get("title") or "").strip()
            if not t_ev or HEAVY_NOISE_EXCLUDE_RE.search(t_ev):
                continue
            if not has_authoritative_primary_source(ev.get("sources") or []):
                continue
            _, age_h = _event_ts_age_hours(ev, now_ref)
            prio = 2 if tier == "S" else 1
            heavy_events.append((prio, -age_h, {**ev, "_cat": cat, "_age_h": age_h}))

    heavy_events.sort(key=lambda x: (x[0], x[1]), reverse=True)

    # 3. Sync recent (<16h) Today Heavy events (plus older S-tier up to min_heavy) into wire items
    for prio, _, ev in heavy_events:
        age_h = float(ev.get("_age_h") or 0.0)
        if age_h > window_hours and prio < 2:
            continue
        ev_title = str(ev.get("title") or "").strip()
        ev_summary = str(ev.get("fact_summary") or ev.get("summary") or "").strip()
        ev_tier = str(ev.get("severity_tier") or "A")
        ev_tag = str(ev.get("heavy_reason_tag") or infer_heavy_reason_tag(ev_title, ev_summary))
        ev_tkey = heavy_topic_key(ev_title)

        matched_item: Optional[Dict[str, Any]] = None
        for it in items:
            w_title = str(it.get("title") or "")
            w_tkey = heavy_topic_key(w_title)
            if (ev_tkey and w_tkey == ev_tkey) or title_similarity(ev_title, w_title) >= 0.44:
                matched_item = it
                break

        if matched_item is not None:
            if matched_item.get("severity_tier") != "S" and ev_tier == "S":
                matched_item["severity_tier"] = "S"
            elif matched_item.get("severity_tier") not in {"S", "A"}:
                matched_item["severity_tier"] = ev_tier
            matched_item["importance"] = "high"
            matched_item["heavy_reason_tag"] = ev_tag
        else:
            src0 = (ev.get("sources") or [{}])[0] if isinstance(ev.get("sources"), list) and ev.get("sources") else {}
            pub_iso, _ = _event_ts_age_hours(ev, now_ref)
            eid = str(ev.get("event_id") or "")
            items.append(
                {
                    "id": f"w_ev_{eid}" if eid else f"w_ev_{len(items)}",
                    "title": ev_title,
                    "title_en": ev.get("title_en") or "",
                    "excerpt": smart_truncate(ev_summary, 180) if ev_summary else "",
                    "category": str(ev.get("category") or ev.get("_cat") or "general"),
                    "source_name": str(src0.get("source_name") or "权威信源"),
                    "url": str(src0.get("url") or ""),
                    "published_at": pub_iso,
                    "thumbnail_url": ev.get("thumbnail_url"),
                    "severity_tier": ev_tier,
                    "heavy_reason_tag": ev_tag,
                    "importance": "high",
                    "tag": str((ev.get("entities") or [""])[0] or ""),
                    "synced_from_today": True,
                }
            )

    # 4. Deduplicate & enforce 8-12 cap on Heavy items (S-tier prioritized, then newest A-tier)
    items.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    heavy_candidates = [idx for idx, it in enumerate(items) if it.get("importance") == "high" or it.get("severity_tier") in {"S", "A"}]
    ranked_heavy = [idx for idx in heavy_candidates if items[idx].get("severity_tier") == "S"] + [
        idx for idx in heavy_candidates if items[idx].get("severity_tier") != "S"
    ]
    selected_heavy: List[int] = []
    seen_keys: set[str] = set()
    kept_titles: List[str] = []
    for idx in ranked_heavy:
        if len(selected_heavy) >= max_heavy:
            break
        t = str(items[idx].get("title") or "")
        tk = heavy_topic_key(t)
        if tk and tk in seen_keys:
            continue
        if any(title_similarity(t, pt) >= 0.42 for pt in kept_titles):
            continue
        selected_heavy.append(idx)
        kept_titles.append(t)
        if tk:
            seen_keys.add(tk)

    # If still below min_heavy and today events have additional unique S/A items, top up cleanly
    if len(selected_heavy) < min_heavy:
        for _, _, ev in heavy_events:
            if len(selected_heavy) >= min_heavy:
                break
            t = str(ev.get("title") or "").strip()
            tk = heavy_topic_key(t)
            if tk and tk in seen_keys:
                continue
            if any(title_similarity(t, pt) >= 0.42 for pt in kept_titles):
                continue
            src0 = (ev.get("sources") or [{}])[0] if isinstance(ev.get("sources"), list) and ev.get("sources") else {}
            pub_iso, _ = _event_ts_age_hours(ev, now_ref)
            eid = str(ev.get("event_id") or "")
            new_it = {
                "id": f"w_ev_{eid}" if eid else f"w_ev_{len(items)}",
                "title": t,
                "title_en": ev.get("title_en") or "",
                "excerpt": smart_truncate(str(ev.get("fact_summary") or ""), 180),
                "category": str(ev.get("category") or ev.get("_cat") or "general"),
                "source_name": str(src0.get("source_name") or "权威信源"),
                "url": str(src0.get("url") or ""),
                "published_at": pub_iso,
                "thumbnail_url": ev.get("thumbnail_url"),
                "severity_tier": str(ev.get("severity_tier") or "A"),
                "heavy_reason_tag": str(ev.get("heavy_reason_tag") or infer_heavy_reason_tag(t, str(ev.get("fact_summary") or ""))),
                "importance": "high",
                "tag": str((ev.get("entities") or [""])[0] or ""),
                "synced_from_today": True,
            }
            items.append(new_it)
            selected_heavy.append(len(items) - 1)
            kept_titles.append(t)
            if tk:
                seen_keys.add(tk)

    keep_set = set(selected_heavy)
    for idx in heavy_candidates:
        if idx not in keep_set:
            items[idx]["severity_tier"] = "B"
            items[idx]["importance"] = "normal"
            items[idx]["heavy_reason_tag"] = None

    # Sort descending by time and preserve max_total without ever dropping selected Heavy items
    items.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    if len(items) > max_total:
        heavy_kept = [it for it in items if it.get("importance") == "high"]
        normal_kept = [it for it in items if it.get("importance") != "high"][: max(0, max_total - len(heavy_kept))]
        items = sorted(heavy_kept + normal_kept, key=lambda x: str(x.get("published_at") or ""), reverse=True)[:max_total]

    # Clean & unify breaking_highlights if present so no brokerage ratings or mistagged headlines linger
    raw_highlights = wire_doc.get("breaking_highlights")
    if isinstance(raw_highlights, list):
        cleaned_hl: List[Dict[str, Any]] = []
        seen_hl_keys: set[str] = set()
        kept_hl_titles: List[str] = []
        for hl in raw_highlights:
            if not isinstance(hl, dict):
                continue
            ht = str(hl.get("title") or "").strip()
            if not ht or HEAVY_NOISE_EXCLUDE_RE.search(ht):
                continue
            h_exc = str(hl.get("excerpt") or "")
            tk = heavy_topic_key(ht)
            if tk and tk in seen_hl_keys:
                continue
            if any(title_similarity(ht, pt) >= 0.42 for pt in kept_hl_titles):
                continue
            nhl = dict(hl)
            if GEO_MILITARY_HEAVY_RE.search(ht):
                nhl["severity_tier"] = "S" if nhl.get("severity_tier") == "S" else "A"
                nhl["breaking_label"] = "地缘与军事突发"
            else:
                nhl["breaking_label"] = infer_heavy_reason_tag(ht, h_exc)
            cleaned_hl.append(nhl)
            kept_hl_titles.append(ht)
            if tk:
                seen_hl_keys.add(tk)
        wire_doc["breaking_highlights"] = cleaned_hl

    wire_doc["items"] = items
    wire_doc["total"] = len(items)
    wire_doc["high_importance_count"] = sum(1 for it in items if it.get("importance") == "high")
    return wire_doc
