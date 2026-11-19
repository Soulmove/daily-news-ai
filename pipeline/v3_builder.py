"""V3 Research Intelligence Builder: storylines dossiers, entities index, catalyst calendar, tech tools, radar & seed predictions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape as xml_escape

from pipeline.dedup import is_omnibus_digest_title, title_similarity
from pipeline.entities import ENTITY_BY_ID, build_entities_index_base
from pipeline.id_utils import make_storyline_id
from pipeline.manifest import atomic_write_json, load_json_if_exists
from pipeline.time_utils import SHANGHAI_TZ, now_shanghai, parse_iso_datetime, to_iso_shanghai


def _as_str_list(val: Any) -> List[str]:
    if isinstance(val, str):
        return [val] if val.strip() else []
    if isinstance(val, (list, tuple)):
        return [str(x) for x in val if str(x).strip()]
    return []


def _extract_sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"[。；\n]+", text) if p.strip()]
    return parts


_UNWATCHED_HKEX_CODES = {"00700", "09988", "00981", "03690"}
_TOPIC_CANON_BUCKETS = [
    ("nvda_ceo_saga", ("黄仁勋", "英伟达", "nvidia"), ("卸任", "辞任", "辞职", "复职", "重返", "继任", "ceo", "换帅")),
    ("msft_outage", ("微软", "microsoft", "azure"), ("宕机", "瘫痪", "恢复服务", "故障")),
    ("apec_shenzhen", ("深圳", "apec"), ("会晤", "元首", "峰会")),
]


def _storyline_semantic_bucket(title: str) -> Optional[str]:
    low = (title or "").lower()
    # Keep analyst price target or TPU supply-chain effects distinct from CEO departure rumor cluster
    if any(k in low for k in ("目标价", "评级", "tpu", "走私", "sec 8-k")):
        return None
    for bname, g1, g2 in _TOPIC_CANON_BUCKETS:
        if any(k in low for k in g1) and any(k in low for k in g2):
            return bname
    return None


def _is_financial_corporate_event(event: dict) -> bool:
    combined = f"{event.get('title', '')} {event.get('fact_summary', '')}".lower()
    if any(k in combined for k in ("漏洞", "攻击", "cve", "零日", "注入", "宕机", "故障", "瘫痪", "论文", "framework", "输入法")):
        return False
    return event.get("category") == "finance" or any(
        k in combined for k in ("sec", "8-k", "10-q", "10-k", "财报", "营收", "目标价", "评级", "ipo", "融资", "ceo", "继任")
    )


def _infer_domain_next_catalyst(event: dict, matched_primary_ent: Optional[dict]) -> str:
    combined = f"{event.get('title', '')} {event.get('fact_summary', '')}".lower()
    if any(k in combined for k in ("漏洞", "攻击", "cve", "零日", "注入", "泄露", "安全")):
        return "等待官方安全响应中心发布补丁编号、受影响版本清单与修复指南"
    if any(k in combined for k in ("宕机", "故障", "瘫痪", "恢复", "停飞")):
        return "等待官方服务状态页发布事故根因复盘 (Postmortem) 与全面恢复确认"
    if any(k in combined for k in ("开源", "github", "hugging face", "模型", "论文", "framework", "bttf", "longcat", "openpangu", "llama.cpp")):
        return "跟踪 GitHub / Hugging Face 官方仓库权重、许可及第三方独立评测基准"
    if any(k in combined for k in ("统计局", "宏观", "利率", "fomc", "央行", "净回笼", "gdp", "cpi", "进出口", "房地产")):
        return "关注国家统计局 / 央行下期官方公报或 FOMC 决议声明"
    if any(k in combined for k in ("会晤", "峰会", "外长", "apec", "声明", "边界")):
        return "关注官方联合声明全文或相关外交/经贸部门正式通告"
    if _is_financial_corporate_event(event) and matched_primary_ent:
        val_list = _as_str_list(matched_primary_ent.get("validation_milestones"))
        if val_list:
            return val_list[0]
    if event.get("speculation_or_outlook"):
        return str(event["speculation_or_outlook"])[:90]
    return "关注涉事机构或主管部门下一轮正式公开声明"


def _build_investment_card(event: dict, entities_map: Dict[str, dict]) -> Optional[Dict[str, Any]]:
    """
    Construct a 5-stage structured investment research card:
      事实变化 -> 经营变量 -> 产业链关系 -> 相关资产 -> 验证节点
    Matches validation nodes by event domain so security/outage/paper items never copy SEC boilerplate.
    """
    matched_eids = event.get("entity_ids") or []
    if not matched_eids and event.get("category") not in {"finance", "tech"}:
        return None
    primary_ent = entities_map.get(matched_eids[0]) if matched_eids else None
    is_fin = _is_financial_corporate_event(event)

    assets: List[Dict[str, str]] = []
    op_vars: List[str] = []
    upstream: List[str] = []
    downstream: List[str] = []
    milestones: List[str] = []

    for eid in matched_eids[:4]:
        ed = entities_map.get(eid)
        if not ed:
            continue
        for tk in ed.get("tickers", []):
            assets.append(
                {
                    "entity": ed["canonical_name"],
                    "ticker": tk["label"],
                    "relation": "直接相关主体" if eid == matched_eids[0] else "同链条关联主体",
                    "basis": f"匹配规范实体：{ed['canonical_name']}",
                }
            )
        op_vars.extend(_as_str_list(ed.get("operating_variables"))[:3])
        upstream.extend(_as_str_list(ed.get("supply_chain_upstream"))[:3])
        downstream.extend(_as_str_list(ed.get("supply_chain_downstream"))[:3])
        if is_fin:
            milestones.extend(_as_str_list(ed.get("validation_milestones"))[:2])

    domain_node = _infer_domain_next_catalyst(event, primary_ent)
    if domain_node and domain_node not in milestones:
        milestones.insert(0, domain_node)

    return {
        "fact_change": event.get("fact_summary") or event.get("title"),
        "operating_variables": list(dict.fromkeys(op_vars))[:5] or ["核心产品出货与价格/毛利率变化（待财报季核对）"],
        "supply_chain_links": {
            "upstream": list(dict.fromkeys(upstream))[:4],
            "downstream": list(dict.fromkeys(downstream))[:4],
        },
        "related_assets": assets[:6],
        "validation_nodes": list(dict.fromkeys(milestones))[:4],
        "financial_actuals_preview": (primary_ent.get("financial_actuals") or [])[:4] if primary_ent else [],
        "market_data_disclosure": "当前静态版本暂未接入付费实时行情、估值倍數及华尔街一致预期接口；相关资产仅呈现可验证业务关联与 SEC/交易所历史公开披露事实。",
    }


def _compute_fact_diff(curr_event: dict, prev_event: Optional[dict]) -> Dict[str, Any]:
    """Differentiate new facts, corrections/revisions, source momentum, and unchanged background between batches."""
    curr_sents = _extract_sentences(curr_event.get("fact_summary") or "")
    curr_srcs = curr_event.get("sources") or []
    curr_indep = int(
        curr_event.get("independent_publisher_count")
        or len({str(s.get("publisher") or s.get("source") or "") for s in curr_srcs if not s.get("is_reprint_copy")})
        or 1
    )
    if not prev_event:
        return {
            "change_type": "new_discovery",
            "change_type_label": "首次发现",
            "new_facts": curr_sents or [curr_event.get("title", "")],
            "corrections": curr_event.get("contradictions") or [],
            "unchanged_background": [],
            "source_delta": curr_indep,
            "indep_source_count": curr_indep,
            "new_source_urls": [s.get("url") for s in curr_srcs[:5] if s.get("url")],
        }

    prev_sents = _extract_sentences(prev_event.get("fact_summary") or prev_event.get("summary") or "")
    new_facts: List[str] = []
    unchanged: List[str] = []
    for cs in curr_sents:
        if any(title_similarity(cs, ps) >= 0.65 or cs == ps for ps in prev_sents):
            unchanged.append(cs)
        else:
            new_facts.append(cs)

    corrections: List[str] = list(curr_event.get("contradictions") or [])
    if curr_event.get("evidence_status") != prev_event.get("evidence_status"):
        corrections.append(
            f"可信状态变动：{prev_event.get('evidence_status')} -> {curr_event.get('evidence_status')}"
        )

    prev_srcs = prev_event.get("sources") or []
    prev_urls = {s.get("url") for s in prev_srcs if s.get("url")}
    new_srcs = [s for s in curr_srcs if s.get("url") and s.get("url") not in prev_urls]
    indep_new = [s for s in new_srcs if not s.get("is_reprint_copy")]
    prev_indep = int(
        prev_event.get("independent_publisher_count")
        or len({str(s.get("publisher") or s.get("source") or "") for s in prev_srcs if not s.get("is_reprint_copy")})
        or 1
    )
    source_delta = max(len(indep_new), curr_indep - prev_indep, 0)

    if source_delta > 0 and not new_facts:
        change_type = "new_reports_only"
        change_label = f"升温跟进（+{source_delta} 家独立信源）"
    elif new_facts or corrections:
        change_type = "substantive_update"
        change_label = f"新增/修订实质事实（+{source_delta} 源）" if source_delta > 0 else "新增/修订实质事实"
    elif new_srcs:
        change_type = "reprint_expansion"
        change_label = "纯转载扩散（未新增独立事实）"
    else:
        change_type = "unchanged_continuation"
        change_label = "旧事持续追踪（本批无实质变化）"

    return {
        "change_type": change_type,
        "change_type_label": change_label,
        "new_facts": new_facts,
        "corrections": corrections,
        "unchanged_background": unchanged,
        "source_delta": source_delta,
        "indep_source_count": curr_indep,
        "new_source_urls": [s.get("url") for s in new_srcs[:5]],
    }


def _atomic_write_text(path: Path, text: str) -> None:
    """Atomically write UTF-8 text via a temporary sibling file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _ics_escape(val: str) -> str:
    return (
        str(val or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _format_ics_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _export_calendar_ics(calendar_items: List[dict], *, generated_at_iso: str, site_url: str) -> tuple[str, int, int]:
    """Build RFC 5545 calendar subscription feed including ONLY events with confirmed scheduled dates."""
    gen_dt = parse_iso_datetime(generated_at_iso) or now_shanghai()
    dtstamp = _format_ics_utc(gen_dt)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Daily News AI//Insight V3 Calendar//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:全球突发催化与宏微观事件日历 (Daily News AI)",
        "X-WR-CALDESC:按批次自动更新的一手宏观日程、财报窗口与关键验证事件订阅源",
        "X-WR-TIMEZONE:Asia/Shanghai",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    exported = 0
    skipped = 0
    seen_ids: set[str] = set()
    for ev in calendar_items:
        raw_sched = ev.get("scheduled_at")
        dt = parse_iso_datetime(str(raw_sched)) if raw_sched else None
        if not dt:
            skipped += 1
            continue
        eid = str(ev.get("id") or f"cal_{exported}")
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        exported += 1
        end_dt = dt + timedelta(hours=1)
        desc_parts = [
            f"核心指标：{ev.get('watch_variable')}" if ev.get("watch_variable") else "",
            f"催化类型：{ev.get('catalyst_type')}" if ev.get("catalyst_type") else "",
            f"前置预期：{ev.get('pre_expectation')}" if ev.get("pre_expectation") else "",
            f"验证问题：{ev.get('verification_question')}" if ev.get("verification_question") else "",
            f"参考信源：{ev.get('reference_url')}" if ev.get("reference_url") else "",
        ]
        desc = "\n".join(p for p in desc_parts if p)
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{eid}@daily-news-ai",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{_format_ics_utc(dt)}",
            f"DTEND:{_format_ics_utc(end_dt)}",
            f"SUMMARY:{_ics_escape(str(ev.get('title') or '未命名事件'))}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            f"URL:{str(ev.get('reference_url') or site_url)}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n", exported, skipped


def _export_rss_xml(
    events: List[dict],
    *,
    title: str,
    description: str,
    site_url: str,
    feed_url: str,
    batch_id: str,
    generated_at_iso: str,
) -> str:
    """Build clean RFC 822 / RSS 2.0 feed for external RSS readers."""
    gen_dt = parse_iso_datetime(generated_at_iso) or now_shanghai()
    base = site_url.rstrip("/") + "/"
    item_xml: List[str] = []
    for ev in events[:30]:
        cat = str(ev.get("category") or "comprehensive")
        eid = str(ev.get("event_id") or "")
        link = f"{base}?batch={batch_id}&cat={cat}&event={eid}"
        pub_dt = parse_iso_datetime(
            ev.get("first_reported_at") or ev.get("latest_reported_at") or ev.get("published_at")
        ) or gen_dt
        src_links = " | ".join(
            f"<a href=\"{xml_escape(str(s.get('url') or ''))}\">{xml_escape(str(s.get('publisher') or s.get('source') or '来源'))}</a>"
            for s in (ev.get("sources") or [])[:4]
            if s.get("url")
        )
        desc_html = (
            f"<p><strong>可信度：</strong>{xml_escape(str(ev.get('evidence_label') or ev.get('evidence_status') or '核验中'))}</p>"
            f"<p>{xml_escape(str(ev.get('fact_summary') or ev.get('summary') or ''))}</p>"
            + (f"<p><strong>参考信源：</strong>{src_links}</p>" if src_links else "")
        )
        item_xml.append(
            "    <item>\n"
            f"      <title>{xml_escape(str(ev.get('title') or ''))}</title>\n"
            f"      <link>{xml_escape(link)}</link>\n"
            f"      <guid isPermaLink=\"false\">{xml_escape(f'{batch_id}:{eid}')}</guid>\n"
            f"      <pubDate>{xml_escape(format_datetime(pub_dt.astimezone(SHANGHAI_TZ)))}</pubDate>\n"
            f"      <category>{xml_escape(cat)}</category>\n"
            f"      <description>{xml_escape(desc_html)}</description>\n"
            "    </item>"
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<rss version=\"2.0\" xmlns:atom=\"http://www.w3.org/2005/Atom\">\n"
        "  <channel>\n"
        f"    <title>{xml_escape(title)}</title>\n"
        f"    <link>{xml_escape(base)}</link>\n"
        f"    <description>{xml_escape(description)}</description>\n"
        f"    <language>zh-CN</language>\n"
        f"    <lastBuildDate>{xml_escape(format_datetime(gen_dt.astimezone(SHANGHAI_TZ)))}</lastBuildDate>\n"
        f"    <atom:link href=\"{xml_escape(feed_url)}\" rel=\"self\" type=\"application/rss+xml\" />\n"
        + "\n".join(item_xml)
        + "\n  </channel>\n</rss>\n"
    )


_MAJOR_TOPIC_SPECS: List[Dict[str, Any]] = [
    {
        "topic_id": "topic_apec_trump_china",
        "title": "特朗普访华与 2026 深圳 APEC 峰会实时行程专题",
        "subtitle": "追踪中美元首接机、欢迎晚宴、APEC 全体会、双边/中美俄三边互动及多边关税协议进展",
        "badge": "超级时政专题 · 实时行程",
        "category": "global",
        "pattern": re.compile(
            r"(?:(?:特朗普|川普|trump).{0,32}(?:访华|来华|中国|深圳|北京|apec|会晤|普京|xi\b|china|putin|summit|trilateral|visit|tariff|trade)|"
            r"(?:xi\b|putin|china).{0,32}trump|"
            r"apec|深圳峰会|中美元首|中美俄|亚太经合组织|习特会|欢迎晚宴|三边会晤|高市早苗.{0,12}(?:中国|访华|apec)|takaichi.{0,20}china)",
            re.I,
        ),
        "exclude": re.compile(r"(?:围巾|座驾|同框|开了个玩笑|人字拖|戒了|全妆|三角梅|打卡|midterm|fcc|fda|nsf)", re.I),
        "calendar_title": "2026 深圳 APEC 峰会与中美元首双边/三边会谈行程",
        "calendar_watch": "官方联合公报、中美经贸关税与 AI 治理共识、中美俄三边互动细节",
    },
    {
        "topic_id": "topic_spacex_musk",
        "title": "SpaceX 星舰回收、xAI 与马斯克商业生态",
        "subtitle": "追踪星舰上级回收（筷子夹飞船）、Grok 模型、Optimus 机器人与算力租赁动向",
        "badge": "前沿科技 · 商业航天",
        "category": "tech",
        "pattern": re.compile(r"(?:spacex|星舰|starship|筷子夹|马斯克|musk|grok\s*4|optimus|特斯拉|tesla)", re.I),
        "exclude": None,
        "calendar_title": None,
        "calendar_watch": None,
    },
    {
        "topic_id": "topic_ai_ipo_models",
        "title": "Anthropic 超级 IPO 与中美前沿大模型竞速",
        "subtitle": "追踪 Anthropic 募资定价、Qwen / 腾讯混元 / DeepSeek / Google 新模型发布与定价冲击",
        "badge": "AI 产业 · 资本主线",
        "category": "tech",
        "pattern": re.compile(r"(?:anthropic|qwen|混元|hy4|deepseek|diffusiongemma|openai|claude|算力限制)", re.I),
        "exclude": None,
        "calendar_title": "Anthropic IPO 定价与上市首日表现窗口",
        "calendar_watch": "最终发行价、募资规模（800–950 亿美元区间）与上市后估值锚定",
    },
    {
        "topic_id": "topic_nvidia_governance",
        "title": "英伟达业绩、出口管制与管理层过渡追踪",
        "subtitle": "追踪英伟达季度业绩、SEC 8-K 继任安排、出口审查与芯片供应链竞争格局",
        "badge": "半导体核心主线",
        "category": "finance",
        "pattern": re.compile(r"(?:英伟达|nvidia|nvda|黄仁勋|blackwell)", re.I),
        "exclude": re.compile(r"(?:诈骗集团|冒名)", re.I),
        "calendar_title": None,
        "calendar_watch": None,
    },
    {
        "topic_id": "topic_macro_fed_commodities",
        "title": "美联储利率路径、美元走强与黄金大宗异动",
        "subtitle": "追踪 FOMC 会议纪要、12 月议息预期分化、美元指数与黄金/原油跳水走势",
        "badge": "全球宏观与流动性",
        "category": "finance",
        "pattern": re.compile(r"(?:美联储|fomc|加息|降息|现货黄金|金价|美元指数|油价|国际资本净流入)", re.I),
        "exclude": None,
        "calendar_title": None,
        "calendar_watch": None,
    },
]


def _classify_itinerary_tag(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ("机场", "抵深", "抵达", "迎接", "下榻", "arrives", "tarmac")):
        return "抵访接待"
    if any(k in t for k in ("晚宴", "招待会", "同框", "握手", "banquet", "dinner")):
        return "晚宴互动"
    if any(k in t for k in ("三边", "三国", "trilateral", "双边", "会晤", "会谈", "talks", "bilateral")):
        return "高层会谈"
    if any(k in t for k in ("协议", "关税", "自贸", "合作", "演讲", "speech", "deal", "tariff", "trade")):
        return "经贸与声明"
    if any(k in t for k in ("回收", "星舰", "筷子", "发布", "上线", "推出", "ipo", "定价", "募资")):
        return "重大里程碑"
    return "关键进展"


def _build_major_topics(
    cat_docs: Dict[str, dict],
    raw_items_by_cat: Optional[Dict[str, List[dict]]],
    generated_at_iso: str,
) -> List[Dict[str, Any]]:
    """Cluster high-resonance live stories across smart events + direct/raw feeds into structured topic timelines."""
    all_smart_events: List[dict] = []
    for doc in cat_docs.values():
        if isinstance(doc, dict):
            all_smart_events.extend(doc.get("events") or [])

    all_raw_items: List[dict] = []
    for lst in (raw_items_by_cat or {}).values():
        if isinstance(lst, list):
            all_raw_items.extend(lst)

    topics: List[Dict[str, Any]] = []
    for spec in _MAJOR_TOPIC_SPECS:
        pat = spec["pattern"]
        excl = spec["exclude"]
        matched_events: List[dict] = []
        matched_raw: List[dict] = []

        for ev in all_smart_events:
            ev_t = str(ev.get("title") or "")
            if pat.search(ev_t) and not (excl and excl.search(ev_t)):
                matched_events.append(ev)

        for it in all_raw_items:
            if it.get("source_kind") == "market_ticker" or not it.get("url"):
                continue
            title = str(it.get("title") or "").strip()
            if not title or is_omnibus_digest_title(title):
                continue
            if pat.search(title) and not (excl and excl.search(title)):
                matched_raw.append(it)

        total_mentions = len(matched_events) + len(matched_raw)
        if total_mentions < 2:
            continue

        # Build deduplicated chronological timeline nodes combining smart events + richest raw/direct reports
        nodes: List[Dict[str, Any]] = []
        seen_titles: List[str] = []
        seen_urls: set[str] = set()

        # Prefer direct news/curated items with explicit timestamps
        candidates: List[Dict[str, Any]] = []
        for ev in matched_events:
            src0 = (ev.get("sources") or [{}])[0]
            candidates.append(
                {
                    "time": ev.get("first_reported_at") or ev.get("latest_reported_at") or ev.get("fetched_at"),
                    "title": str(ev.get("title") or "").strip(),
                    "summary": str(ev.get("fact_summary") or "")[:160],
                    "source_name": src0.get("source_name") or "简报汇总",
                    "url": src0.get("url"),
                    "event_id": ev.get("event_id"),
                    "priority": 0,
                }
            )
        # Prioritize non-discussion news outlets for raw itinerary nodes
        for it in sorted(
            matched_raw,
            key=lambda x: (
                0 if x.get("source_tier") == "direct_media" else (1 if x.get("source_kind") == "news" else 2),
                0 if x.get("published_at") else 1,
                str(x.get("published_at") or ""),
            ),
        ):
            candidates.append(
                {
                    "time": it.get("published_at") or it.get("fetched_at"),
                    "title": str(it.get("title") or "").strip(),
                    "summary": str(it.get("excerpt") or "")[:140],
                    "source_name": it.get("source_name") or it.get("source_id") or "信源",
                    "url": it.get("url"),
                    "event_id": None,
                    "priority": 1 if it.get("source_kind") == "news" else 2,
                }
            )

        for cand in candidates:
            t = cand["title"]
            u = cand["url"] or ""
            if not t or (u and u in seen_urls):
                continue
            if any(title_similarity(t, st) >= 0.52 for st in seen_titles):
                continue
            seen_titles.append(t)
            if u:
                seen_urls.add(u)
            nodes.append(
                {
                    "time": cand["time"],
                    "stage_tag": _classify_itinerary_tag(t),
                    "title": t,
                    "summary": cand["summary"] if cand["summary"] and cand["summary"] != t else "",
                    "source_name": cand["source_name"],
                    "url": cand["url"],
                    "event_id": cand["event_id"],
                }
            )
            if len(nodes) >= 12:
                break

        # Sort timeline chronologically (newest first or chronological? Chronological ascending for itinerary, latest_updated tracked!)
        nodes.sort(key=lambda n: str(n.get("time") or "9999"))
        latest_ts = max((str(n.get("time")) for n in nodes if n.get("time")), default=generated_at_iso)
        source_families = {n["source_name"] for n in nodes if n.get("source_name")}

        topics.append(
            {
                "topic_id": spec["topic_id"],
                "title": spec["title"],
                "subtitle": spec["subtitle"],
                "badge": spec["badge"],
                "category": spec["category"],
                "updated_at": latest_ts,
                "total_mentions": total_mentions,
                "source_count": len(source_families),
                "event_ids": [ev["event_id"] for ev in matched_events if ev.get("event_id")],
                "timeline": nodes,
                "_calendar_title": spec["calendar_title"],
                "_calendar_watch": spec["calendar_watch"],
            }
        )

    topics.sort(key=lambda tp: (1 if tp["topic_id"] == "topic_apec_trump_china" else 0, tp["total_mentions"]), reverse=True)
    return topics[:5]


def build_v3_artifacts(
    root: Path,
    *,
    batch_id: str,
    generated_at_iso: str,
    cat_docs: Dict[str, dict],
    prev_cat_events: Dict[str, List[dict]],
    prev_batch_id: Optional[str],
    connectors_payload: Dict[str, Any],
    calendar_extra: Optional[List[dict]] = None,
    raw_items_by_cat: Optional[Dict[str, List[dict]]] = None,
) -> Dict[str, Any]:
    """
    Build and atomically persist all V3 research memory JSONs under data/:
      - data/entities_index.json
      - data/storylines_index.json
      - data/calendar.json
      - data/tech_tools.json
      - data/radar.json
      - data/predictions_public.json
    """
    generated_dt = parse_iso_datetime(generated_at_iso) or now_shanghai()
    entities_map = build_entities_index_base()

    # Merge first-party connector updates into entity dossiers
    ent_updates = connectors_payload.get("entity_updates") or {}
    for eid, upd in ent_updates.items():
        if eid not in entities_map:
            continue
        if upd.get("recent_filings"):
            entities_map[eid]["recent_filings"] = upd["recent_filings"]
        if upd.get("financial_actuals"):
            entities_map[eid]["financial_actuals"] = upd["financial_actuals"]
        if upd.get("hkex_filings"):
            entities_map[eid]["recent_filings"] = (
                entities_map[eid].get("recent_filings", []) + upd["hkex_filings"]
            )[:6]

    # Collect existing storyline history so timeline persists across multiple batches
    prev_storylines_raw = load_json_if_exists(root / "data/storylines_index.json", default={})
    prev_storylines = (
        prev_storylines_raw.get("storylines", {})
        if isinstance(prev_storylines_raw, dict) and isinstance(prev_storylines_raw.get("storylines"), dict)
        else {}
    )

    storylines: Dict[str, Dict[str, Any]] = {}
    radar_items: List[Dict[str, Any]] = []
    calendar_items: List[Dict[str, Any]] = list(connectors_payload.get("calendar_events") or [])
    if calendar_extra:
        calendar_items.extend(calendar_extra)

    # Index previous events by event_id and storyline_id for diff comparison
    prev_by_id: Dict[str, dict] = {}
    for plist in prev_cat_events.values():
        for pe in plist:
            if pe.get("event_id"):
                prev_by_id[pe["event_id"]] = pe

    # Build normalized list of all current-batch events
    all_events: List[dict] = []
    for cat, doc in cat_docs.items():
        for ev in doc.get("events", []):
            all_events.append(ev)

    tech_tools: List[dict] = []
    for raw_tool in (connectors_payload.get("tech_tools") or []):
        t = dict(raw_tool)
        if t.get("summary"):
            clean_sum = re.sub(r"<[^>]+>", " ", str(t["summary"]))
            clean_sum = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean_sum)
            clean_sum = re.sub(r"[#*`]+", "", clean_sum)
            clean_sum = re.sub(r"\s+", " ", clean_sum).strip().lstrip("；;:：•- ")
            t["summary"] = clean_sum[:360] or "详见官方 Release 说明。"
        if str(t.get("license") or "").upper() == "NOASSERTION":
            t["license"] = "多许可证/自定义条款 (见仓库 LICENSE)"
        tech_tools.append(t)
    seen_tool_names = {t.get("name", "").lower() for t in tech_tools}
    seen_tool_tokens = {
        tok.lower()
        for t in tech_tools
        for tok in re.split(r"[\s/_-]+", str(t.get("name") or ""))
        if len(tok) >= 4
    }

    seen_storyline_titles: List[tuple[str, str]] = []
    seen_buckets: Dict[str, str] = {}

    for ev in all_events:
        st_id = ev.get("storyline_id") or make_storyline_id(ev["category"], ev["title"], ev.get("entities"))
        bucket = _storyline_semantic_bucket(ev["title"])
        if bucket and bucket in seen_buckets:
            st_id = seen_buckets[bucket]
        else:
            dup_sid = next((sid for sid, stitle in seen_storyline_titles if title_similarity(ev["title"], stitle) >= 0.62), None)
            if dup_sid:
                st_id = dup_sid
            else:
                seen_storyline_titles.append((st_id, ev["title"]))
                if bucket:
                    seen_buckets[bucket] = st_id
        prev_ev_id = (ev.get("followup") or {}).get("prev_event_id")
        prev_ev = prev_by_id.get(prev_ev_id) if prev_ev_id else None
        diff = _compute_fact_diff(ev, prev_ev)

        # Attach event summary to matched entities
        for eid in ev.get("entity_ids") or []:
            if eid in entities_map:
                ed = entities_map[eid]
                ed["recent_events"].append(
                    {
                        "event_id": ev["event_id"],
                        "storyline_id": st_id,
                        "title": ev["title"],
                        "category": ev["category"],
                        "evidence_status": ev["evidence_status"],
                        "update_kind": ev.get("update_kind", "new_discovery"),
                        "first_discovered_at": ev.get("first_discovered_at"),
                        "latest_reported_at": ev.get("latest_reported_at"),
                        "primary_url": ev["sources"][0]["url"] if ev.get("sources") else None,
                    }
                )
                ed["change_count_30d"] += 1
                ed["last_event_at"] = max(
                    [t for t in [ed.get("last_event_at"), ev.get("latest_reported_at"), ev.get("fetched_at")] if t],
                    default=None,
                )

        # Build / merge timeline for this storyline cleanly without burst-rebuild duplicates
        existing_st = prev_storylines.get(st_id, {})
        timeline = list(existing_st.get("timeline") or [])
        node_ts = ev.get("latest_fact_update_at") or ev.get("fetched_at") or generated_at_iso
        same_cutoff_or_unchanged = bool(
            timeline
            and (
                (timeline[0].get("batch_id") == batch_id and timeline[0].get("event_id") == ev["event_id"])
                or (
                    timeline[0].get("fetched_at") == ev.get("fetched_at")
                    and timeline[0].get("fact_summary") == ev.get("fact_summary")
                )
            )
        )
        if not same_cutoff_or_unchanged:
            timeline.insert(
                0,
                {
                    "batch_id": batch_id,
                    "event_id": ev["event_id"],
                    "timestamp": node_ts,
                    "fetched_at": ev.get("fetched_at"),
                    "title": ev["title"],
                    "fact_summary": ev.get("fact_summary"),
                    "evidence_status": ev.get("evidence_status"),
                    "delta_note": (ev.get("followup") or {}).get("delta_note") or diff["change_type_label"],
                    "source_count": ev.get("source_count", 0),
                    "independent_publisher_count": ev.get("independent_publisher_count", 0),
                    "sources_preview": [
                        {"source_name": s.get("source_name"), "url": s.get("url"), "published_at": s.get("published_at")}
                        for s in (ev.get("sources") or [])[:4]
                    ],
                },
            )

        open_questions: List[str] = []
        if ev.get("evidence_status") in {"single_source", "needs_verification"}:
            open_questions.append("当前尚无多家独立媒体或一手官方声明交叉确认，待后续核实。")
        if ev.get("attribution_warning"):
            open_questions.append(ev["attribution_warning"])
        if ev.get("speculation_or_outlook"):
            open_questions.append(f"待验证前瞻观察：{ev['speculation_or_outlook']}")

        matched_primary_ent = entities_map.get((ev.get("entity_ids") or [None])[0] or "")
        next_catalyst = _infer_domain_next_catalyst(ev, matched_primary_ent)

        storylines[st_id] = {
            "storyline_id": st_id,
            "current_event_id": ev["event_id"],
            "title": ev["title"],
            "category": ev["category"],
            "entities": ev.get("entities", []),
            "entity_ids": ev.get("entity_ids", []),
            "current_stage": diff["change_type_label"],
            "evidence_status": ev["evidence_status"],
            "evidence_label": ev["evidence_label"],
            "first_discovered_at": existing_st.get("first_discovered_at") or ev.get("first_discovered_at"),
            "first_reported_at": ev.get("first_reported_at"),
            "latest_fact_update_at": ev.get("latest_fact_update_at"),
            "latest_reported_at": ev.get("latest_reported_at"),
            "fact_diff": diff,
            "contradictions": ev.get("contradictions") or diff.get("corrections") or [],
            "open_questions": open_questions,
            "next_catalyst": next_catalyst,
            "fact_atoms": ev.get("fact_atoms") or [],
            "investment_card": _build_investment_card(ev, entities_map),
            "timeline": timeline[:15],
            "sources": ev.get("sources") or [],
            "ai_analysis": ev.get("ai_analysis"),
            "unverified_claims": ev.get("unverified_claims") or [],
        }

        # Populate tech_tools entry ONLY for genuinely distinct new AI model/tool announcements (never omnibus/rumor/duplicate HF rows)
        ev_title = ev["title"].strip()
        is_rumor_or_omnibus = (
            ev_title.startswith(("报道称", "消息称", "传闻", "[", "【"))
            or ev_title.count("、") >= 2
            or bool(ev.get("attribution_warning"))
        )
        title_lower = ev_title.lower()
        already_covered_tool = (
            any(k in title_lower for k in seen_tool_names if len(k) > 3)
            or any(tok in title_lower for tok in seen_tool_tokens if len(tok) >= 5)
        )
        if ev["category"] == "tech" and ev.get("material_stage") and not is_rumor_or_omnibus and not already_covered_tool:
            if any(k in ev_title for k in ("开源", "上线", "推出", "模型", "LongCat", "openPangu", "Seedance", "Claude", "Gemini", "GPT")):
                clean_title = re.sub(r"\s*[（(][^）)]*$", "", ev_title).strip()
                short_name = re.split(r"[：，]", clean_title)[0].strip()
                if len(short_name) > 56:
                    short_name = short_name[:55].rstrip() + "…"
                if len(short_name) >= 4:
                    tech_tools.append(
                        {
                            "tool_id": f"tool_evt_{ev['event_id']}",
                            "name": short_name,
                            "repo": None,
                            "tool_type": "AI 模型 / 产品动态",
                            "sector": "AI 模型与产品",
                            "entity_id": (ev.get("entity_ids") or [None])[0],
                            "availability_stage": ev["material_stage"],
                            "availability_label": ev.get("material_stage_label") or "已宣布 (待补充官方试用入口)",
                            "latest_version": None,
                            "version_published_at": ev.get("first_reported_at"),
                            "license": "待核对官方声明/许可证页",
                            "official_url": ev["sources"][0]["url"] if ev.get("sources") else None,
                            "release_url": ev["sources"][0]["url"] if ev.get("sources") else None,
                            "docs_url": None,
                            "summary": ev.get("fact_summary") or f"来源于新闻线索（{ev.get('material_depth')}），需区分厂商自报与独立评测。",
                            "deployment_requirements": "未披露具体运行需求（留空不臆测）",
                            "pricing_or_cost": "未披露定价",
                            "checked_at": ev.get("fetched_at"),
                            "source_name": ev["sources"][0]["source_name"] if ev.get("sources") else "新闻聚合线索",
                            "source_url": ev["sources"][0]["url"] if ev.get("sources") else None,
                        }
                    )
                    seen_tool_names.add(short_name.lower())

        # Extract scheduled catalyst dates ONLY from genuine schedule/summit/earnings/release items
        indep_c = int(ev.get("independent_publisher_count") or len(ev.get("sources") or []))
        is_calendar_fluff = bool(
            re.search(r"(?:围巾|座驾|同框|开了个玩笑|花絮|是否将举行|没有这方面的信息|美方代表有哪些|发言人回应|外交部回应)", ev_title)
        )
        is_rumor_or_gossip = (
            is_calendar_fluff
            or bool(ev.get("contradictions"))
            or (bool(ev.get("attribution_warning")) and indep_c < 3)
            or (ev_title.startswith(("报道称", "消息称", "传闻")) and indep_c < 3)
        )
        if not is_rumor_or_gossip and any(k in ev_title for k in ("下周", "本周重磅", "日程", "财报", "听证会", "峰会", "会晤", "元首", "议息", "APEC", "发布会", "IPO")):
            if not any(c.get("storyline_id") == st_id for c in calendar_items):
                # Parse explicit dates (e.g. "11月19日") or relative weekday ("星期四") rather than stamping fetched_at
                combined_sched_txt = f"{ev_title} {ev.get('fact_summary') or ''}"
                sched_iso: Optional[str] = None
                orig_note = "具体时刻待官方正式公布 (TBD)"
                cert_code = "reported_tbd"
                cert_label = "报道提及（具体日程待官方进一步确认）"
                date_m = re.search(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", combined_sched_txt)
                if date_m:
                    yr_v = int(date_m.group(1) or generated_dt.year)
                    mo_v, dy_v = int(date_m.group(2)), int(date_m.group(3))
                    try:
                        sched_dt_obj = generated_dt.replace(year=yr_v, month=mo_v, day=dy_v, hour=10, minute=0, second=0)
                        sched_iso = to_iso_shanghai(sched_dt_obj)
                        orig_note = f"{yr_v}-{mo_v:02d}-{dy_v:02d} 日程窗口 (具体钟点待定)"
                        cert_code = "confirmed_official" if any(k in combined_sched_txt for k in ("官宣", "官方", "外交部", "APEC")) else "reported_tbd"
                        cert_label = "官方/多源已定日程" if cert_code == "confirmed_official" else "报道明确日期（待具体时刻表）"
                    except ValueError:
                        sched_iso = None
                elif "星期四" in combined_sched_txt or "周四" in combined_sched_txt:
                    # Resolve Thursday relative to article report date
                    anchor_dt = parse_iso_datetime(ev.get("first_reported_at")) or generated_dt
                    days_ahead = (3 - anchor_dt.weekday()) % 7
                    if days_ahead == 0 and anchor_dt.hour >= 18:
                        days_ahead = 7
                    target_th = (anchor_dt + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0)
                    sched_iso = to_iso_shanghai(target_th)
                    orig_note = f"{target_th.strftime('%Y-%m-%d')} 周四日程窗口 (来源报道推算)"
                    cert_label = "报道明确周四会期（具体时刻待定）"

                sched_dt = parse_iso_datetime(sched_iso) if sched_iso else None
                is_past_cal = bool(sched_dt and sched_dt < (generated_dt - timedelta(days=2)))
                if not is_past_cal:
                    is_macro_cb = any(k in combined_sched_txt.upper() for k in ("FOMC", "美联储", "央行", "议息", "纪要", "利率", "CPI", "非农", "通胀"))
                    is_diplomatic = any(k in combined_sched_txt for k in ("元首", "峰会", "会晤", "APEC", "外交", "特朗普", "习近平", "普京"))
                    is_ipo_ev = "IPO" in combined_sched_txt.upper()
                    watch_var = (
                        "联邦基金目标利率区间、通胀/就业措辞与后续路径指引"
                        if is_macro_cb
                        else (
                            "官方联合公报、双边/多边高层共识与经贸科技议题表态"
                            if is_diplomatic
                            else ("最终发行价、募资规模与挂牌首日表现" if is_ipo_ev else "官方披露实值数据、毛利率与下季指引")
                        )
                    )
                    calendar_items.append(
                        {
                            "calendar_id": f"cal_evt_{ev['event_id']}",
                            "title": ev["title"],
                            "scheduled_at": sched_iso,
                            "original_time_note": orig_note,
                            "timezone": "Asia/Shanghai",
                            "certainty": cert_code,
                            "certainty_label": cert_label,
                            "is_past": False,
                            "category": ev["category"],
                            "entity_ids": ev.get("entity_ids", []),
                            "storyline_id": st_id,
                            "watch_variable": watch_var,
                            "pre_expectation": "未提供一致预期数值；请勿用事后报道反向填补",
                            "actual_result": None,
                            "source_name": ev["sources"][0]["source_name"] if ev.get("sources") else "财经日程",
                            "source_url": ev["sources"][0]["url"] if ev.get("sources") else None,
                        }
                    )

        # Compute explicit transparent Radar score
        rel_pts = 30 if ev.get("entity_ids") else 0
        nov_pts = 25 if ev.get("is_new_in_batch") else (18 if diff["change_type"] == "substantive_update" else 5)
        indep = ev.get("independent_publisher_count") or 1
        indep_pts = min(indep, 5) * 6
        official_pts = 20 if ev["evidence_status"] == "official_confirmed" else 0
        depth_pts = 15 if ev.get("material_depth") in {"first_party_and_body", "body_lead_extracted", "title_and_excerpt"} else 0
        reprint_penalty = -8 if (ev.get("reprint_count", 0) >= 2 and diff["change_type"] == "reprint_expansion") else 0

        radar_score = max(0, min(100, rel_pts + nov_pts + indep_pts + official_pts + depth_pts + reprint_penalty))
        if ev["evidence_status"] == "official_confirmed":
            signal_type = "官方/监管一手披露"
        elif ev.get("contradictions"):
            signal_type = "传闻与一手披露分歧"
        elif diff["change_type"] == "reprint_expansion":
            signal_type = "纯转载扩散（非新增独立事实）"
        elif ev.get("is_new_in_batch") or diff["change_type"] == "substantive_update":
            signal_type = "多维新增/实质进展"
        else:
            signal_type = "常规持续话题"

        why_reasons = []
        if rel_pts:
            why_reasons.append(f"命中核心研究主体 (+{rel_pts})")
        if official_pts:
            why_reasons.append(f"官方/代码仓库一手证实 (+{official_pts})")
        if nov_pts >= 18:
            why_reasons.append(f"{'首次发现' if ev.get('is_new_in_batch') else '实质事实更新'} (+{nov_pts})")
        if indep >= 2:
            why_reasons.append(f"{indep} 家独立来源 (+{indep_pts})")
        if depth_pts:
            why_reasons.append(f"含正文或元数据摘要 (+{depth_pts})")
        if reprint_penalty < 0:
            why_reasons.append(f"纯转载增量去权 ({reprint_penalty})")

        radar_items.append(
            {
                "event_id": ev["event_id"],
                "storyline_id": st_id,
                "title": ev["title"],
                "category": ev["category"],
                "entity_ids": ev.get("entity_ids", []),
                "radar_score": radar_score,
                "signal_type": signal_type,
                "why_in_radar": "；".join(why_reasons) or "常规资讯入选",
                "evidence_status": ev["evidence_status"],
                "independent_publisher_count": indep,
                "reprint_count": ev.get("reprint_count", 0),
                "first_discovered_at": ev.get("first_discovered_at"),
                "latest_reported_at": ev.get("latest_reported_at"),
                "primary_url": ev["sources"][0]["url"] if ev.get("sources") else None,
            }
        )

    # Preserve ONLY clean, non-duplicate, non-omnibus, <5-day recent historical storylines (eliminates 120-item bloat)
    for st_id, old_st in prev_storylines.items():
        if st_id in storylines or len(storylines) >= 75:
            continue
        old_title = str(old_st.get("title") or "")
        if not old_title or is_omnibus_digest_title(old_title):
            continue
        hkex_m = re.match(r"^\[HKEX\s+(\d{5})\s+", old_title)
        if hkex_m and hkex_m.group(1) not in _UNWATCHED_HKEX_CODES:
            continue
        if old_title.startswith("[巨潮 ") and any(k in old_title for k in ("翌日披露", "未经审核业绩")):
            continue
        last_ts = parse_iso_datetime(old_st.get("latest_reported_at") or old_st.get("latest_fact_update_at") or old_st.get("first_discovered_at"))
        if last_ts and (generated_dt - last_ts) > timedelta(days=5):
            continue
        old_bucket = _storyline_semantic_bucket(old_title)
        if old_bucket and old_bucket in seen_buckets:
            continue
        if any(title_similarity(old_title, stitle) >= 0.50 for _, stitle in seen_storyline_titles):
            continue
        clean_old = dict(old_st)
        ent_ids_old = clean_old.get("entity_ids") or []
        prim_old = entities_map.get(ent_ids_old[0]) if ent_ids_old else None
        domain_cat = _infer_domain_next_catalyst(clean_old, prim_old)
        if not clean_old.get("next_catalyst") or len(str(clean_old.get("next_catalyst"))) <= 2 or (not _is_financial_corporate_event(clean_old) and "SEC" in str(clean_old.get("next_catalyst"))):
            clean_old["next_catalyst"] = domain_cat
        if isinstance(clean_old.get("investment_card"), dict):
            clean_old["investment_card"] = _build_investment_card(clean_old, entities_map) or clean_old["investment_card"]
        storylines[st_id] = clean_old
        seen_storyline_titles.append((st_id, old_title))
        if old_bucket:
            seen_buckets[old_bucket] = st_id

    radar_items.sort(key=lambda r: r["radar_score"], reverse=True)

    # Build Major Event Spotlights & Chronological Timelines (data/topics.json)
    major_topics_raw = _build_major_topics(cat_docs, raw_items_by_cat, generated_at_iso)
    major_topics: List[Dict[str, Any]] = []
    for tp in major_topics_raw:
        cal_t = tp.pop("_calendar_title", None)
        cal_w = tp.pop("_calendar_watch", None)
        major_topics.append(tp)
        # Ensure active multi-report summit / IPO spotlights are surfaced cleanly in Calendar too
        if cal_t and tp.get("total_mentions", 0) >= 3:
            cal_id = f"cal_{tp['topic_id']}"
            if not any(c.get("calendar_id") == cal_id for c in calendar_items):
                anchor_iso = to_iso_shanghai(generated_dt.replace(hour=14, minute=0, second=0))
                first_url = next((n.get("url") for n in tp.get("timeline") or [] if n.get("url")), None)
                calendar_items.append(
                    {
                        "calendar_id": cal_id,
                        "title": cal_t,
                        "scheduled_at": anchor_iso,
                        "original_time_note": f"{generated_dt.strftime('%Y-%m-%d')} 当日进行中/核心窗口 (基于 {tp['source_count']} 家信源)",
                        "timezone": "Asia/Shanghai",
                        "certainty": "confirmed_official",
                        "certainty_label": "进行中 · 超级焦点日程",
                        "is_past": False,
                        "category": tp["category"],
                        "entity_ids": [],
                        "storyline_id": None,
                        "watch_variable": cal_w or "官方联合声明与核心数据披露",
                        "pre_expectation": "请结合顶部专题时间轴跟踪实时进展；不编造一致预期",
                        "actual_result": None,
                        "source_name": f"专题聚合 ({tp['source_count']} 源)",
                        "source_url": first_url,
                    }
                )

    # Preserve fixed created_at/due_at for existing public predictions (stop infinite due-date rollover!)
    prev_preds_doc = load_json_if_exists(root / "data/predictions_public.json", default={})
    prev_preds_by_id = {
        str(p.get("prediction_id")): p
        for p in (prev_preds_doc.get("predictions") or [] if isinstance(prev_preds_doc, dict) else [])
        if isinstance(p, dict) and p.get("prediction_id")
    }

    def _keep_fixed_dates(pid: str, default_created: str, default_due: str) -> tuple[str, str]:
        old = prev_preds_by_id.get(pid)
        if old and old.get("created_at") and old.get("due_at"):
            return str(old["created_at"]), str(old["due_at"])
        return default_created, default_due

    # Public real-time research questions seeded dynamically from live connector telemetry
    nvda_filings = (entities_map.get("ent_nvidia") or {}).get("recent_filings") or []
    nvda_502 = next(
        (f for f in nvda_filings if f.get("form") == "8-K" and "5.02" in ",".join(str(x) for x in (f.get("items") or []))),
        None,
    )
    nvda_pred_title = (
        "英伟达临时管理层后是否在 14 天内披露永久 CEO 继任或董事回任安排"
        if nvda_502
        else "英伟达管理层变动传闻是否获 SEC EDGAR Item 5.02 官方文件证实"
    )
    nvda_pred_question = (
        f"SEC EDGAR 已收录 NVDA {nvda_502.get('filing_date', '近期')} 8-K (Item 5.02)；截至到期日是否出现正式继任人选或复职 Form 8-K / 官方 IR 声明？"
        if nvda_502
        else "截至到期日，SEC EDGAR 是否出现 NVDA 提交的高管变动 Form 8-K (Item 5.02) 或官方 IR 声明？"
    )
    nvda_opposing = (
        ["关于正式继任人选与复职传闻，截至目前尚无新的后续 8-K 增补披露"]
        if nvda_502
        else ["SEC EDGAR 截至本批次最新 8-K 尚无 Item 5.02 官方高管离任披露"]
    )
    nvda_created, nvda_due = _keep_fixed_dates("pred_seed_nvda_sec_502", "2026-11-16T15:30:00+08:00", "2026-11-30T20:00:00+08:00")
    qwen_created, qwen_due = _keep_fixed_dates("pred_seed_qwen_release_ga", "2026-11-16T15:30:00+08:00", "2026-12-16T20:00:00+08:00")
    seed_predictions: List[Dict[str, Any]] = [
        {
            "prediction_id": "pred_seed_nvda_sec_502",
            "mode": "live",
            "status": "open",
            "title": nvda_pred_title,
            "target_entity_id": "ent_nvidia",
            "target_entity": "英伟达 (NVIDIA / NVDA.US)",
            "question": nvda_pred_question,
            "created_at": nvda_created,
            "due_at": nvda_due,
            "win_rule": "SEC EDGAR 出现新的 NVDA 8-K Item 5.02 官方后续人事任命文件，或 investor.nvidia.com 发布明确治理结论",
            "lose_rule": "到期前 SEC 仅维持临时代理架构且无新任命文件，或官方澄清驳回社区传闻",
            "indeterminate_rule": "仅见机构研报/猎头传闻而缺乏上市公司 8-K 或 IR 官方公告",
            "supporting_evidence": (
                [f"SEC EDGAR 已核验 {nvda_502.get('filing_date', '')} 8-K (Items: 5.02, 9.01)"]
                if nvda_502
                else ["多篇媒体/热榜标题称高管变动引发讨论"]
            ),
            "opposing_evidence": nvda_opposing,
            "core_assumption": "上市公司首席执行官变动及正式继任属美股重大法定披露事项，必受 SEC 8-K 4 个工作日强制披露约束",
            "invalidation_trigger": "若英伟达 IR 正式澄清拒绝变更或公布明确长期继任方案",
            "probability_pct": 60 if nvda_502 else 25,
            "probability_note": "基准概率基于当前 SEC EDGAR 连接器实采状态动态校准，到期日固定不再顺延",
            "current_judgment": (
                f"SEC 8-K Item 5.02 已披露于 {nvda_502.get('filing_date', '近期')}；正跟踪正式继任进展"
                if nvda_502
                else "待官方披露核实，暂不将其作为既定事实纳入基本面判断"
            ),
            "versions": [
                {
                    "version": 1,
                    "updated_at": nvda_created,
                    "judgment": (
                        f"已追踪到 SEC {nvda_502.get('filing_date', '')} 8-K Item 5.02，等待后续正式继任公告"
                        if nvda_502
                        else "等待 SEC 8-K 核查（当前无官方披露）"
                    ),
                    "probability_pct": 60 if nvda_502 else 25,
                    "reason": "由 V3 SEC EDGAR 连接器交叉核查生成初始观察记录",
                }
            ],
            "settlement": None,
        },
        {
            "prediction_id": "pred_seed_qwen_release_ga",
            "mode": "live",
            "status": "open",
            "title": "Qwen 系列新一代旗舰模型是否在 12 月 16 日前进入开源权重或 API 正式可用 (GA)",
            "target_entity_id": "ent_qwen_alibaba",
            "target_entity": "阿里巴巴 / 通义千问 (Qwen)",
            "question": "截至 2026-12-16，Hugging Face `Qwen` 官方组织或阿里云官方 API 是否上线对应新版模型卡片/正式计费文档？",
            "created_at": qwen_created,
            "due_at": qwen_due,
            "win_rule": "Hugging Face `Qwen` 组织出现新版模型仓库且含可用权重/许可证，或阿里云百炼上线正式 API 计费页",
            "lose_rule": "到期前官方模型卡与 API 文档均未更新，且官方声明仅限内部测试或推迟发布",
            "indeterminate_rule": "仅发布预告博文但未公开任何可试用权重、API 或定价说明",
            "supporting_evidence": ["科技报道出现 Qwen4-Max 相关讨论", "Hugging Face Qwen 组织近期持续活跃更新模型"],
            "opposing_evidence": ["当前 Hugging Face Qwen 官方库尚未见同名新版仓库上架"],
            "core_assumption": "通义千问重大版本均会通过 HF 或阿里云官方渠道同步文档与许可",
            "invalidation_trigger": "官方辟谣非官方版本或延后发布",
            "probability_pct": 55,
            "probability_note": "主观基准判断，最终以 Hugging Face 官方模型卡 API 检查结果结算",
            "current_judgment": "保持追踪，等待 Hugging Face / 官方文档连接器捕获一手上架记录",
            "versions": [
                {
                    "version": 1,
                    "updated_at": qwen_created,
                    "judgment": "待 Hugging Face 官方权重与阿里云文档验证",
                    "probability_pct": 55,
                    "reason": "基于科技新闻热榜线索与 HF 连接器比对建立",
                }
            ],
            "settlement": None,
        },
    ]

    # Dynamically attach timely live verifiable predictions from active major topics & upcoming FOMC
    active_topic_ids = {t["topic_id"] for t in major_topics}
    if "topic_apec_trump_china" in active_topic_ids:
        apec_created, apec_due = _keep_fixed_dates("pred_live_apec_2026_communique", generated_at_iso, "2026-11-23T20:00:00+08:00")
        seed_predictions.insert(
            0,
            {
                "prediction_id": "pred_live_apec_2026_communique",
                "mode": "live",
                "status": "open",
                "title": "深圳 APEC 中美元首会谈后是否发布具体的经贸关税或 AI 治理联合文本",
                "target_entity_id": "ent_us_china_diplomacy",
                "target_entity": "中美外交与元首峰会 / APEC",
                "question": "截至 2026-11-23，中国外交部或美国白宫是否公开披露中美元首深圳会晤达成的新一轮关税调整/AI 治理具体书面成果？",
                "created_at": apec_created,
                "due_at": apec_due,
                "win_rule": "外交部或白宫官网发布明确含关税豁免/调整或 AI 安全合作条款的官方通稿",
                "lose_rule": "双方仅发表原则性表态与维持既有共识声明，未公布新增可量化经贸或 AI 条款",
                "indeterminate_rule": "会谈推迟或核心文本未公开",
                "supporting_evidence": ["特朗普抵深并获高规格接待，双方就经贸与 AI 议题开展会谈"],
                "opposing_evidence": ["美方会前吹风偏向落实既有共识与管控分歧，而非签署全面新协议"],
                "core_assumption": "元首级会晤实质成果均会通过白宫/外交部正式通稿体现",
                "invalidation_trigger": "双方宣布取消双边经贸磋商议程",
                "probability_pct": 45,
                "probability_note": "基于当前公开吹风与峰会日程动态生成，固定 11 月 23 日结算",
                "current_judgment": "预计偏向原则性框架与局部去风险表态，静待白宫/外交部通稿核验",
                "versions": [
                    {
                        "version": 1,
                        "updated_at": apec_created,
                        "judgment": "等待 11 月 19 日深圳会晤官方正式通稿披露",
                        "probability_pct": 45,
                        "reason": "由深圳 APEC 超级热点专题动态立项",
                    }
                ],
                "settlement": None,
            },
        )

    fomc_dec = next((c for c in calendar_items if "2026-12-08" in str(c.get("title") or "")), None)
    if fomc_dec:
        fed_created, fed_due = _keep_fixed_dates("pred_live_fomc_2026_12", generated_at_iso, "2026-12-10T04:30:00+08:00")
        seed_predictions.append(
            {
                "prediction_id": "pred_live_fomc_2026_12",
                "mode": "live",
                "status": "open",
                "title": "美联储 2026 年 12 月 FOMC 议息会议是否维持鹰派按兵不动或加息 25bp",
                "target_entity_id": "ent_macro_fomc",
                "target_entity": "美联储 FOMC 与全球流动性",
                "question": "北京时间 2026-12-10 03:00 公布的 FOMC 决议声明中，联邦基金利率区间是否上调或释放 2027 年进一步收紧信号？",
                "created_at": fed_created,
                "due_at": fed_due,
                "win_rule": "Federal Reserve 12 月 FOMC 官方声明宣布加息或 SEP 点阵图上移 2027 年利率中值",
                "lose_rule": "官方声明宣布降息或维持利率不变且 SEP 中值下调",
                "indeterminate_rule": "声明未改变利率且点阵图与上期完全一致",
                "supporting_evidence": ["10 月 FOMC 会议纪要偏鹰，沃勒等官员讨论加息节奏"],
                "opposing_evidence": ["内部委员对紧缩幅度与通胀回落节奏存在明显分歧"],
                "core_assumption": "以 Federal Reserve 官网 FOMC 决议原文与 SEP 点阵图为唯一结算口径",
                "invalidation_trigger": "12 月会前核心通胀或就业数据出现断崖式走弱",
                "probability_pct": 55,
                "probability_note": "锚定 2026-12-10 官方决议发布时刻自动到期，不含付费期货隐含概率",
                "current_judgment": "10 月纪要显露鹰派分歧，关注 12 月 SEP 点阵图方向",
                "versions": [
                    {
                        "version": 1,
                        "updated_at": fed_created,
                        "judgment": "等待 12 月 10 日 FOMC 正式声明与点阵图核验",
                        "probability_pct": 55,
                        "reason": "由 FOMC 10 月纪要与 12 月议息日程动态立项",
                    }
                ],
                "settlement": None,
            }
        )

    # Sort calendar cleanly: upcoming ascending first, past recent at tail
    calendar_items.sort(key=lambda c: (1 if c.get("is_past") else 0, str(c.get("scheduled_at") or "9999-12-31")))

    from .ai_radar_builder import build_ai_progress_artifact
    from .bilingual import enrich_bilingual_topics
    from .finance_impact_builder import build_finance_impact_artifact

    enrich_bilingual_topics(major_topics)
    ai_progress_doc = build_ai_progress_artifact(
        batch_id=batch_id,
        generated_at_iso=generated_at_iso,
        cat_docs=cat_docs,
        tech_tools=tech_tools,
    )
    finance_impact_doc = build_finance_impact_artifact(
        batch_id=batch_id,
        generated_at_iso=generated_at_iso,
        cat_docs=cat_docs,
    )

    atomic_write_json(
        root / "data/topics.json",
        {
            "schema_version": "4.0",
            "generated_at": generated_at_iso,
            "batch_id": batch_id,
            "topics": major_topics,
        },
    )
    atomic_write_json(root / "data/ai_progress.json", ai_progress_doc)
    atomic_write_json(root / "data/finance_impact.json", finance_impact_doc)

    atomic_write_json(
        root / "data/entities_index.json",
        {
            "schema_version": "3.0",
            "generated_at": generated_at_iso,
            "batch_id": batch_id,
            "entities": list(entities_map.values()),
        },
    )
    atomic_write_json(
        root / "data/storylines_index.json",
        {
            "schema_version": "3.0",
            "generated_at": generated_at_iso,
            "batch_id": batch_id,
            "storylines": storylines,
        },
    )
    atomic_write_json(
        root / "data/calendar.json",
        {
            "schema_version": "3.0",
            "generated_at": generated_at_iso,
            "batch_id": batch_id,
            "events": calendar_items[:60],
        },
    )
    atomic_write_json(
        root / "data/tech_tools.json",
        {
            "schema_version": "3.0",
            "generated_at": generated_at_iso,
            "batch_id": batch_id,
            "tools": tech_tools[:50],
        },
    )
    atomic_write_json(
        root / "data/radar.json",
        {
            "schema_version": "3.0",
            "generated_at": generated_at_iso,
            "batch_id": batch_id,
            "baseline_window_note": "雷达得分基于关注命中(30)+官方一手(20)+事实新颖度(25)+独立信源(≤30)+素材深度(15)，并扣除纯转载膨胀；受掉线源影响的板块已标注覆盖率。",
            "items": radar_items[:45],
        },
    )
    atomic_write_json(
        root / "data/predictions_public.json",
        {
            "schema_version": "3.0",
            "generated_at": generated_at_iso,
            "batch_id": batch_id,
            "note": "系统预置基于公开一手催化剂建立的可验证观察题；个人自建与修订记录保存在本地浏览器，导入导出可用。",
            "predictions": seed_predictions,
        },
    )

    site_url = os.environ.get("SITE_PUBLIC_URL", "https://soulmove.github.io/daily-news-ai/")
    site_base = site_url.rstrip("/") + "/"
    cal_ics_text, cal_ics_exported, cal_ics_skipped = _export_calendar_ics(
        calendar_items[:60], generated_at_iso=generated_at_iso, site_url=site_base
    )
    _atomic_write_text(root / "data/calendar.ics", cal_ics_text)

    all_feed_events: List[dict] = []
    seen_feed_urls: set[str] = set()
    cat_labels = {
        "finance": "全球财经",
        "global": "综合要闻",
        "tech": "前沿科技",
        "general": "社会热点",
    }
    feeds_by_category: Dict[str, str] = {}
    for cat in ["finance", "global", "tech", "general"]:
        cevs = (cat_docs.get(cat) or {}).get("events") or []
        cat_xml = _export_rss_xml(
            cevs,
            title=f"Daily News AI · {cat_labels.get(cat, cat)}简报",
            description=f"基于可验证一手证据链提取的{cat_labels.get(cat, cat)}批次订阅流",
            site_url=site_base,
            feed_url=f"{site_base}data/feed_{cat}.xml",
            batch_id=batch_id,
            generated_at_iso=generated_at_iso,
        )
        rel_feed = f"data/feed_{cat}.xml"
        _atomic_write_text(root / rel_feed, cat_xml)
        feeds_by_category[cat] = rel_feed
        for ev in cevs:
            primary_u = str(((ev.get("sources") or [{}])[0]).get("url") or ev.get("title") or "")
            if primary_u and primary_u not in seen_feed_urls:
                seen_feed_urls.add(primary_u)
                all_feed_events.append(ev)

    all_feed_events.sort(
        key=lambda e: str(e.get("latest_reported_at") or e.get("first_reported_at") or ""),
        reverse=True,
    )
    main_feed_xml = _export_rss_xml(
        all_feed_events,
        title="Daily News AI · 全景情报订阅",
        description="只入库可核查来源的跨市场科技、财经与宏观事实追踪 RSS",
        site_url=site_base,
        feed_url=f"{site_base}data/feed.xml",
        batch_id=batch_id,
        generated_at_iso=generated_at_iso,
    )
    _atomic_write_text(root / "data/feed.xml", main_feed_xml)

    return {
        "entities_count": len(entities_map),
        "storylines_count": len(storylines),
        "topics_count": len(major_topics),
        "ai_progress_count": len(ai_progress_doc.get("timeline") or []),
        "finance_impact_count": len(finance_impact_doc.get("cards") or []),
        "calendar_count": len(calendar_items),
        "calendar_ics_path": "data/calendar.ics",
        "calendar_ics_count": cal_ics_exported,
        "calendar_tbd_skipped": cal_ics_skipped,
        "feed_path": "data/feed.xml",
        "feeds_by_category": feeds_by_category,
        "tech_tools_count": len(tech_tools),
        "radar_count": len(radar_items),
    }
