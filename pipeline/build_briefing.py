"""V2 Briefing Builder: grounded Gemini AI curation, same-batch simulated perspectives, and V1 reconciliation."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from pipeline.connectors.base import repair_mojibake
from pipeline.dedup import (
    _MARKET_PRICE_RE,
    _SOCIAL_HOTLIST_IDS,
    _source_rank_key,
    deduplicate_raw_items,
    entities_conflict,
    extract_tokens,
    get_publisher_family,
    has_authoritative_primary_source,
    is_consumer_promo_or_fluff,
    is_hotlist_aggregator_source,
    is_omnibus_digest_title,
    score_cluster_for_briefing,
    smart_truncate,
    title_similarity,
)
from pipeline.entities import ENTITY_REGISTRY, match_entities_with_reasons
from pipeline.gemini_pool import (
    call_gemini_json,
    count_healthy_keys,
    get_ordered_key_slots,
    get_quota_summary,
)
from pipeline.id_utils import canonicalize_url, is_generic_quote_or_homepage_url, make_raw_item_id
from pipeline.manifest import (
    atomic_write_json,
    load_json_if_exists,
    load_manifest,
    prune_old_archives,
    save_manifest,
    upsert_history_index,
)
from pipeline.sources import CATEGORIES, CATEGORY_FILES, CATEGORY_LABELS, SOURCE_BY_ID
from pipeline.time_utils import (
    SHANGHAI_TZ,
    format_batch_id,
    now_shanghai,
    parse_iso_datetime,
    to_iso_shanghai,
)
from pipeline.v3_builder import build_v3_artifacts
from pipeline.verifier import dedupe_attribution_prefixes, validate_published_briefing, verify_and_enrich_event

PRIMARY_MODEL = os.environ.get("GEMINI_MODEL", "gemini-4-hydrogen")
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
SECONDARY_FALLBACK_MODEL = "gemini-2.0-flash"
_LAST_USED_MODEL = PRIMARY_MODEL

PERSPECTIVE_ROLES = [
    "产业供应链观察员（关注上下游传导与落地周期）",
    "买方风控分析师（关注估值前提、流动性与反身性风险）",
    "宏观政策研究员（关注监管导向与跨市场外溢）",
    "技术架构工程师（关注工程可行性与安全边界）",
    "一线消费与民生观察者（关注价格体感与就业影响）",
    "历史周期比较研究者（关注类似事件的长期样本）",
]


def _collect_api_keys(category: str) -> List[str]:
    slots = get_ordered_key_slots(f"briefing:{category}")
    return [s.secret for s in slots]


def _load_raw_batch(
    root: Path, raw_path: Optional[str] = None
) -> Tuple[str, str, str, Dict[str, List[dict]], Dict[str, Any]]:
    manifest = load_manifest(root)
    raw_info = manifest.get("raw", {}) if isinstance(manifest, dict) else {}
    target_dir = Path(raw_path) if raw_path else Path(raw_info.get("latest_path", "."))
    abs_dir = root / target_dir if not target_dir.is_absolute() else target_dir

    meta = load_json_if_exists(abs_dir / "meta.json", default={})
    if isinstance(meta, dict) and meta.get("batch_id"):
        input_batch_id = meta["batch_id"]
        input_cutoff_at = meta["fetched_at"]
    else:
        parts = target_dir.as_posix().strip("/").split("/")
        if len(parts) >= 4 and parts[-2] and parts[-1]:
            dt = parse_iso_datetime(f"{parts[-2]}T{parts[-1].replace('-', ':')}:00+08:00") or now_shanghai()
        else:
            dt = now_shanghai()
        input_batch_id = format_batch_id("raw", dt)
        input_cutoff_at = to_iso_shanghai(dt)

    connectors_payload = load_json_if_exists(abs_dir / "connectors.json", default=None)
    if not isinstance(connectors_payload, dict):
        connectors_payload = load_json_if_exists(root / "data/connectors_latest.json", default={})
    if not isinstance(connectors_payload, dict):
        connectors_payload = {}

    raw_by_cat: Dict[str, List[dict]] = {}
    for cat in CATEGORIES:
        data = load_json_if_exists(abs_dir / CATEGORY_FILES[cat], default=[])
        if not isinstance(data, list):
            data = []
        normalized_items: List[dict] = []
        for plat in data:
            if not isinstance(plat, dict):
                continue
            sid = plat.get("id", "unknown")
            sdef = SOURCE_BY_ID.get(sid)
            sname = plat.get("name") or (sdef.name if sdef else sid)
            skind = plat.get("kind") or (sdef.kind if sdef else "news")
            citable = sdef.citable_as_news if sdef else (sid != "xueqiu-hotstock")
            for idx, it in enumerate(plat.get("items", []), start=1):
                if not isinstance(it, dict):
                    continue
                title = str(it.get("title") or "").strip()
                canon = canonicalize_url(it.get("canonical_url") or it.get("url"))
                if not title or not canon:
                    continue
                item_id = it.get("item_id") or make_raw_item_id(sid, canon, title)
                normalized_items.append(
                    {
                        "item_id": item_id,
                        "source_id": sid,
                        "source_name": sname,
                        "source_kind": skind,
                        "source_tier": it.get("source_tier") or "aggregator_lead",
                        "citable_as_news": citable,
                        "category": cat,
                        "title": title,
                        "url": canon,
                        "canonical_url": canon,
                        "published_at": it.get("published_at"),
                        "published_at_source": it.get("published_at_source"),
                        "fetched_at": it.get("fetched_at") or input_cutoff_at,
                        "excerpt": it.get("excerpt"),
                        "thumbnail_url": it.get("thumbnail_url"),
                        "deep_fetch_status": it.get("deep_fetch_status"),
                        "metric_label": it.get("metric_label"),
                        "rank": it.get("rank", idx),
                    }
                )
        raw_by_cat[cat] = normalized_items

    # Merge independent first-party connector items into their matching categories
    for cit in connectors_payload.get("items") or []:
        if isinstance(cit, dict) and cit.get("category") in raw_by_cat:
            canon = canonicalize_url(cit.get("canonical_url") or cit.get("url"))
            if canon:
                raw_by_cat[cit["category"]].append(cit)

    return input_batch_id, input_cutoff_at, target_dir.as_posix().rstrip("/") + "/", raw_by_cat, connectors_payload


def _prepare_prompt_catalog(
    raw_items: List[dict], limit: int = 140
) -> Tuple[str, Dict[str, dict], Dict[str, dict], Dict[str, Any]]:
    citable = [x for x in raw_items if x.get("citable_as_news", True) and x.get("source_kind") != "market_ticker"]
    clustered = deduplicate_raw_items(citable)

    # Task 2 candidate prioritization (relevance + independence + first-party + depth + freshness)
    scored_clusters: List[Tuple[float, List[str], dict]] = []
    for cl in clustered:
        ent_matches = match_entities_with_reasons(f"{cl.get('title', '')} {cl.get('excerpt') or ''}")
        sc, reasons = score_cluster_for_briefing(cl, watched_match_count=len(ent_matches))
        scored_clusters.append((sc, reasons, cl))

    scored_clusters.sort(key=lambda pair: pair[0], reverse=True)
    selected = scored_clusters[:limit]
    rejected = [
        {"title": cl.get("title"), "score": sc, "reason": "低于候选池截断阈值" if sc > 0 else "无关注命中且单源仅标题"}
        for sc, _, cl in scored_clusters[limit : limit + 30]
    ]

    ref_lookup: Dict[str, dict] = {}
    id_lookup: Dict[str, dict] = {}
    lines: List[str] = []

    ref_num = 1
    for sc, reasons, cluster in selected:
        sources = cluster.get("related_sources") or [cluster]
        cluster_refs: List[str] = []
        for s in sources[:4]:
            ref_id = f"R{ref_num:03d}"
            ref_num += 1
            raw_obj = {
                "item_id": s.get("item_id") or cluster.get("item_id"),
                "source_id": s.get("source_id") or cluster.get("source_id"),
                "source_name": s.get("source_name") or cluster.get("source_name"),
                "source_kind": s.get("source_kind") or cluster.get("source_kind", "news"),
                "source_tier": s.get("source_tier") or cluster.get("source_tier") or "aggregator_lead",
                "publisher_family": s.get("publisher_family"),
                "is_reprint_copy": bool(s.get("is_reprint_copy", False)),
                "citable_as_news": True,
                "title": s.get("title") or cluster.get("title"),
                "url": s.get("url") or cluster.get("url"),
                "canonical_url": s.get("url") or cluster.get("canonical_url"),
                "published_at": s.get("published_at") or cluster.get("published_at"),
                "published_at_source": s.get("published_at_source") or cluster.get("published_at_source"),
                "fetched_at": s.get("fetched_at") or cluster.get("fetched_at"),
                "excerpt": s.get("excerpt") or cluster.get("excerpt"),
                "thumbnail_url": s.get("thumbnail_url") or cluster.get("thumbnail_url"),
                "deep_fetch_status": s.get("deep_fetch_status"),
            }
            ref_lookup[ref_id] = raw_obj
            if raw_obj["item_id"]:
                id_lookup[raw_obj["item_id"]] = raw_obj
            cluster_refs.append(ref_id)

        pub = cluster.get("published_at") or "发布时间未知"
        depth = "一手/正文首段" if cluster.get("deep_fetch_status") == "extracted_body_lead" or any(s.get("source_tier") in {"first_party", "tech_material"} for s in sources) else ("含摘要" if cluster.get("excerpt") else "仅标题")
        excerpt_part = f" | 摘要: {cluster['excerpt']}" if cluster.get("excerpt") else ""
        src_names = "、".join(dict.fromkeys(s.get("source_name") or s.get("source_id", "") for s in sources[:4]))
        indep_cnt = cluster.get("independent_publisher_count", len(sources))
        lines.append(
            f"[{','.join(cluster_refs)}] (评分:{sc} 独立源:{indep_cnt} {depth}) 来源:{src_names} | 时间:{pub} | 标题:{cluster['title']}{excerpt_part}"
        )

    audit = {
        "total_clusters": len(clustered),
        "selected_for_prompt": len(selected),
        "omitted_sample": rejected,
    }
    return "\n".join(lines), ref_lookup, id_lookup, audit


def _build_ai_prompt(category: str, input_cutoff_at: str, catalog_text: str) -> str:
    label = CATEGORY_LABELS[category]
    return f"""你是 Insight Pro 的严肃新闻编辑与信息核查助手。
当前板块：{label} ({category})
输入数据截止时间（Asia/Shanghai）：{input_cutoff_at}

【严格事实与引用纪律 — 必须遵守】：
1. 只能依据下面提供的素材条目输出，禁止编造任何素材中未提及的数字、日期、金额、百分比或公司动作。
2. 若素材标注为 `(仅标题)`，说明没有正文或摘要：`fact_summary` 只能客观复述标题已明确表达的事实，禁止脑补任何未经原文提及的具体数字、日期或因果，也不要输出“原始素材仅含标题”“R001”等采编术语！
3. 每条新闻事件必须填写 `source_refs`（例如 `["R001", "R005"]`），只能引用下方方括号内真实存在的 R 编号；禁止输出 URL，禁止输出可信度百分比。
4. 严格区分事实与判断，且严守【专有名词与直接因果保真铁律】：
   - `fact_summary`：只写素材里已出现的可核验事实，**必须完整保留原文中的核心专有名词、涉事对手方、产品别名、关键高管/船只/城市名及核心争议条款**（例如：产品/别名「比亚迪 Ti7 / 方程豹钛7」、起诉方「捷豹路虎卫士外观侵权」、临时接替人选「Colette Kress」、涉事企业「新加坡 Megaspeed」、遇袭俄船「Sparta II」、气候大会举办地「土耳其安塔利亚」与「草案删去淘汰化石燃料」争议），**严禁把具体机构、人名、地名或争议焦点的实质细节概括丢掉！**
   - `ai_analysis`：写出本事件**不同于同类新闻的独特影响链路、具体受益/受损对象与直接因果约束**（1–2 句，**禁止**「凸显了…」「反映出…」「标志着重大转折」「加速智能化普及」「引发广泛关注」等八股套话）。
   - `unverified_claims`：数组，列出素材中带有传闻、匿名爆料或未获官方证实的说法；无则填 `[]`。
   - `speculation_or_outlook`：可选前瞻观察点，须给出具体的待核实数字/日期/监管或产品信号；素材不足时填 `null`，不要硬凑预测。
5. 事实精确度与限定词要求：
   - **涨跌幅与交易时段**：股价或并购消息必须保留直接诱因（如监管调查、财报、并购报价）、交易时段限定（如盘后/盘前/收盘）及交易双方的涨跌影响，不可把并购方下跌或盘后波动概括为日内普涨。
   - **发行/募资口径**：涉及 IPO 或融资，必须严格区分基础发行规模、绿鞋/超额配售选择权（未行使不得写为已募集）及私募配售；涉及法律和解需写明“原则性和解/尚待签署与批准”等生效前提；涉及呼吁或提议需写明核心结论（如董事会拒绝或接受）。
   - **第三方评测与单方宣称**：厂商自报或缺乏独立出处的评测分数（如红队单项测试、未证实榜单名次）必须明确标注测试边界与单方归因，不得写成行业公认指标。
   - **事件真实时间**：填写 `event_date`（`YYYY-MM-DD` 或 `null`）标明事件实际发生日期；若报道只是旧事件回顾/多周前决议重提，必须置 `"is_stale_rehash": true` 且不得将其写成今日突发冲击。
6. 如果有效素材较少，请宁缺毋滥（输出 8–14 条高质量事件即可），**严禁把多家无关公司的日常公告硬拼成一条拼盘要闻**（如「某公司回购、另公司增资、第三家高管辞职」必须拆开或仅选重大项），禁止收录消费硬件带货报价（显示器/耳机/家电多少元）、游戏打折/帧率、领导晒照片花边或发布会场地抗议；涉及股票/黄金/比特币等行情综述必须优先引用专业财经媒体与官方信源，禁止把无时间戳热搜旧拼盘当成突发大事件。
7. **严格划分 `importance`（绝不滥用 `"high"`）**：仅限具备**权威媒体/监管一手信源**、且属于央行/监管重磅政策（如降准降息、三大交易所调整保证金）、重磅军事外交协定、百亿美元以上并购/重大法院禁令、代际 AI/科学突破的最近 24 小时事件，才可标为 `"high"`；仅有百度热搜/头条/微博/知乎讨论、单家公司常规增资/人事变动、或超过 24 小时无最新实质推进的旧闻，一律只标 `"medium"` 或 `"normal"`。
8. 对于跨多日、多场次的超级重磅事件（例如大国元首访问行程与重要峰会），**标题必须保留核心人物姓名、地点与具体日程节点**，按关键节点拆分清晰（例如「抵访接待/机场会面」「重要双边/三边会谈」「实质经贸协议」），切忌把 10 篇重磅报道压缩成 1 条连人物和日程都看不见的笼统概括！
9. 若核心事件已被 ≥3 家权威媒体实况报道（如公开接待、演讲、已签协议），不要因为个别外媒附带了衍生猜测就把整条核心事实混进 `unverified_claims`；仅将真正未证实的猜测单独放入 `unverified_claims`。
10. 提取 3 条最值得关注的关键变化 `key_changes`，每条也必须附带 `source_refs`。

输入素材列表：
{catalog_text}

请严格返回纯 JSON（不要 Markdown 代码块）：
{{
  "key_changes": [
    {{
      "headline": "一句话概括关键变化",
      "detail": "基于素材的简洁事实说明（不超过60字）",
      "source_refs": ["R001"]
    }}
  ],
  "overview_sections": [
    {{
      "title": "核心脉络",
      "points": [
        {{ "text": "要点描述", "source_refs": ["R001"] }}
      ]
    }}
  ],
  "events": [
    {{
      "title": "清晰准确的中文事件标题",
      "event_date": "YYYY-MM-DD",
      "is_stale_rehash": false,
      "entities": ["具体公司/机构/人物/国家专有名词（禁写国内商业银行、黄金品牌等泛行业词）"],
      "importance": "high",
      "sentiment": "Bullish/Bearish/Mixed/Neutral",
      "fact_summary": "客观事实摘要（严格不超出素材）",
      "ai_analysis": "AI 分析与影响解读",
      "unverified_claims": [],
      "speculation_or_outlook": null,
      "source_refs": ["R001", "R002"]
    }}
  ]
}}"""


def _build_comments_prompt(category: str, events: List[dict]) -> str:
    label = CATEGORY_LABELS[category]
    event_lines = [
        f"- [{ev['event_id']}] {ev['title']}（事实：{ev['fact_summary'][:90]}）"
        for ev in events[:10]
    ]
    return f"""请针对【{label}】本批次已核验的事件，生成 6 条不同专业观察视角的 AI 辩证研判（Pro/Con 正反推演）。
注意：这些内容明确标注为 AI 模拟观点，不代表真实用户或特定名人的真实发言，请围绕事实与未决风险拆解。

事件列表：
{chr(10).join(event_lines)}

可选视角角色：
{chr(10).join(f'- {r}' for r in PERSPECTIVE_ROLES)}

返回纯 JSON 数组（6 条）：
[
  {{
    "role": "角色视角名称",
    "perspective_tag": "一句话视角标签",
    "target_event_id": "对应事件ID",
    "pro_argument": "支持或乐观路径的核心假设（仅基于公开信息）",
    "con_argument": "反向质疑或证伪风险点",
    "key_unknown": "当前资料中最缺少但决定走势的核心未知数",
    "next_catalyst": "下一个可验证的时间或公开事件节点",
    "content": "60-120字的综合研判摘要",
    "stance": "谨慎/关注风险/中性拆解/长期观察"
  }}
]"""


def _call_gemini_json_with_meta(
    prompt: str,
    *,
    scope: str = "default",
    temperature: float = 0.25,
    base_dir: Path | str | None = ".",
) -> Tuple[Any, Optional[str], List[Dict[str, str]], bool]:
    global _LAST_USED_MODEL
    models = list(dict.fromkeys([PRIMARY_MODEL, FALLBACK_MODEL, "gemini-2.5-flash-lite", SECONDARY_FALLBACK_MODEL]))
    res = call_gemini_json(
        scope=scope,
        prompt=prompt,
        models=models,
        temperature=temperature,
        base_dir=base_dir,
    )
    if res.ok:
        if res.model_used:
            _LAST_USED_MODEL = res.model_used
        return res.data, res.model_used, res.per_key_errors, res.quota_exhausted
    raise RuntimeError(f"All Gemini attempts failed: {res.error_message}")


def _call_gemini_json(api_keys: List[str], prompt: str, temperature: float = 0.25) -> Any:
    del api_keys
    data, _, _, _ = _call_gemini_json_with_meta(prompt, scope="default", temperature=temperature)
    return data


def _parse_legacy_summary_sections(raw_summary: str) -> List[dict]:
    if not raw_summary:
        return []
    import re
    sections = [s.strip() for s in re.split(r"(?=【)", raw_summary) if s.strip()]
    parsed: List[dict] = []
    for sec in sections:
        m = re.match(r"【(.*?)】", sec)
        sec_title = m.group(1).strip() if m else "核心综述"
        body = re.sub(r"【.*?】", "", sec, count=1).strip()
        pts = [p.strip() for p in re.split(r"(?=\(\d+\)\.?)", body) if len(p.strip()) > 3]
        if not pts and body:
            pts = [line.strip() for line in body.splitlines() if line.strip()]
        parsed.append({"title": sec_title, "points": [{"text": p, "source_refs": []} for p in pts]})
    return parsed


def _smart_truncate(text: str, max_len: int = 180) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if "_PIPELINE_JARGON_RE" in globals():
        s = _PIPELINE_JARGON_RE.sub("", s).strip()
    return smart_truncate(s, max_len=max_len)


def _build_key_changes_from_events(events: List[dict]) -> List[dict]:
    changes: List[dict] = []
    for ev in events[:3]:
        changes.append(
            {
                "event_id": ev["event_id"],
                "storyline_id": ev.get("storyline_id"),
                "headline": ev["title"],
                "detail": _smart_truncate(ev.get("fact_summary") or "", 120),
                "evidence_status": ev["evidence_status"],
                "attribution_warning": ev.get("attribution_warning"),
                "source_count": ev["source_count"],
                "primary_url": ev["sources"][0].get("url") if ev.get("sources") else None,
                "source_name": ev["sources"][0].get("source_name") if ev.get("sources") else None,
            }
        )
    return changes


def _sync_key_changes_attribution(key_changes: List[dict], events: List[dict]) -> List[dict]:
    """Ensure Top 3 key changes inherit rumor qualifiers if their matching event gained one."""
    ev_by_url: Dict[str, dict] = {}
    for ev in events:
        for s in ev.get("sources", []):
            if s.get("url"):
                ev_by_url[s["url"]] = ev

    synced: List[dict] = []
    for kc in key_changes:
        item = dict(kc)
        matched_ev = ev_by_url.get(item.get("primary_url") or "")
        if not matched_ev and item.get("headline"):
            matched_ev = max(events, key=lambda e: title_similarity(item["headline"], e.get("title", "")), default=None)
            if matched_ev and title_similarity(item["headline"], matched_ev.get("title", "")) < 0.35:
                matched_ev = None
        if matched_ev:
            item["event_id"] = matched_ev["event_id"]
            item["storyline_id"] = matched_ev.get("storyline_id")
            if matched_ev.get("attribution_warning"):
                item["attribution_warning"] = matched_ev["attribution_warning"]
                hl = str(item.get("headline") or "")
                if not any(k in hl for k in ("报道称", "传闻", "待官方", "传言")):
                    item["headline"] = f"报道称：{hl}"
        synced.append(item)
    return synced


def _reconcile_v1_category(
    root: Path,
    cat: str,
    smart_dir: Path,
    raw_by_cat: Dict[str, List[dict]],
    input_batch_id: str,
    input_cutoff_at: str,
    generated_at_iso: str,
    batch_id: str,
    prev_events: List[dict],
    prev_batch_id: Optional[str],
    sec_entity_status: Optional[Dict[str, dict]] = None,
) -> dict:
    """Reconcile an existing V1 (or already-reconciled V2) analysis_{cat}.json against its matching raw snapshot."""
    v1_doc = load_json_if_exists(smart_dir / f"analysis_{cat}.json", default={})
    raw_entries = v1_doc.get("items") or v1_doc.get("events") if isinstance(v1_doc, dict) else None
    if not isinstance(v1_doc, dict) or not raw_entries:
        raise RuntimeError(f"Missing V1/V2 entries in {smart_dir / f'analysis_{cat}.json'}")

    # Search own category first, then cross-category raw items (since AI sometimes cross-referenced hot items)
    own_raw = [x for x in raw_by_cat.get(cat, []) if x.get("citable_as_news", True) and x.get("source_kind") != "market_ticker"]
    all_raw = own_raw + [
        x
        for c in CATEGORIES
        if c != cat
        for x in raw_by_cat.get(c, [])
        if x.get("citable_as_news", True) and x.get("source_kind") != "market_ticker"
    ]

    ref_lookup: Dict[str, dict] = {}
    id_lookup: Dict[str, dict] = {}
    for idx, r in enumerate(all_raw, start=1):
        rk = f"R{idx:04d}"
        r["_tmp_ref"] = rk
        ref_lookup[rk] = r
        id_lookup[r["item_id"]] = r

    used_event_ids: Set[str] = set()
    events: List[dict] = []
    for ordinal, item in enumerate(raw_entries):
        title = str(item.get("title") or "").strip()
        raw_summary = str(item.get("fact_summary") or item.get("summary") or item.get("comment") or "").strip()
        raw_impact = str(item.get("ai_analysis") or item.get("impact") or "").strip()
        raw_pred = str(item.get("speculation_or_outlook") or item.get("prediction") or "").strip() or None

        # Match strictly on title (not general roast comments which add unrelated joke tokens)
        query_text = title
        q_tokens = extract_tokens(query_text)
        # Collect matching raw sources without crossing entity/company boundaries or omnibus digests
        from pipeline.dedup import entities_conflict, is_omnibus_digest_title

        scored: List[Tuple[float, dict]] = []
        for r in all_raw:
            if is_omnibus_digest_title(r.get("title", "")):
                continue
            if entities_conflict(query_text, r["title"], item_b=r):
                continue
            sim = title_similarity(query_text, r["title"])
            r_tokens = extract_tokens(r["title"])
            shared_count = len(q_tokens & r_tokens)
            # Boost exact existing URL if valid and non-quote
            existing_u = canonicalize_url(item.get("url"))
            if existing_u and not is_generic_quote_or_homepage_url(existing_u, "") and r["canonical_url"] == existing_u:
                sim = max(sim, 0.99)
            if sim >= 0.42 or (sim >= 0.28 and shared_count >= 4):
                scored.append((max(sim, shared_count * 0.08), r))

        scored.sort(key=lambda x: x[0], reverse=True)
        # Keep top matches from distinct publisher families
        matched_refs: List[str] = []
        seen_platforms = set()
        top_sim = scored[0][0] if scored else 0.0
        for sim, r in scored:
            if sim < max(0.22, top_sim * 0.72):
                break
            sid = r["source_id"].split("-")[0]
            if sid not in seen_platforms:
                seen_platforms.add(sid)
                matched_refs.append(r["_tmp_ref"])
            if len(matched_refs) >= 5:
                break

        # Separate legacy V1 AI text honestly
        unverified = []
        if any(k in (title + raw_summary) for k in ("传闻", "爆料", "消息称", "未确认", "尚未公开")):
            unverified.append("条目涉及传闻或尚未获官方正式公告确认的表述，请以原文为准。")

        candidate_ev = {
            "event_id": item.get("event_id"),
            "title": title,
            "fact_summary": raw_summary,
            "ai_analysis": raw_impact or ("旧版简报未单独拆分 AI 解读，上方摘要为 V1 模型基于标题整理，请注意甄别延伸表述。" if raw_summary else ""),
            "unverified_claims": unverified,
            "speculation_or_outlook": raw_pred,
            "sentiment": item.get("sentiment"),
            "special_note": item.get("special_note"),
            "importance": item.get("importance") or ("high" if len(events) < 3 else "normal"),
            "source_refs": matched_refs,
            "sources": item.get("sources") or [],
        }
        verified_ev = verify_and_enrich_event(
            candidate_ev,
            category=cat,
            input_batch_id=input_batch_id,
            fetched_at_iso=input_cutoff_at,
            ref_lookup=ref_lookup,
            id_lookup=id_lookup,
            prev_events=prev_events,
            prev_batch_id=prev_batch_id,
            require_semantic_match=False,
            used_event_ids=used_event_ids,
            sec_entity_status=sec_entity_status,
            ordinal=ordinal,
        )
        verified_ev["legacy_v1_origin"] = bool(item.get("legacy_v1_origin", "items" in v1_doc))
        events.append(verified_ev)

    for r in all_raw:
        r.pop("_tmp_ref", None)

    summary_text = v1_doc.get("economy_summary") or v1_doc.get("summary") or ""
    overview_sections = v1_doc.get("overview_sections") or _parse_legacy_summary_sections(summary_text)
    key_changes = _build_key_changes_from_events(events)

    return {
        "schema_version": "3.0",
        "batch_id": batch_id,
        "input_batch_id": input_batch_id,
        "input_cutoff_at": input_cutoff_at,
        "generated_at": generated_at_iso,
        "published_at": to_iso_shanghai(now_shanghai()),
        "category": cat,
        "category_label": CATEGORY_LABELS[cat],
        "generation_mode": "v1_reconciled",
        "legacy_v1_notice": "该批次由 V1/V2 简报经 V3 校验规则核对升级：已拆分独立事件 ID、分离发现/披露/采集时间，并与一手监管源交叉校验。",
        "key_changes": key_changes,
        "overview_sections": overview_sections,
        "events": events,
    }


def _generate_ai_category(
    cat: str,
    raw_by_cat: Dict[str, List[dict]],
    input_batch_id: str,
    input_cutoff_at: str,
    batch_id: str,
    prev_events: List[dict],
    prev_batch_id: Optional[str],
    api_keys: List[str],
    sec_entity_status: Optional[Dict[str, dict]] = None,
    base_dir: Path | str = ".",
) -> Tuple[dict, Dict[str, Any]]:
    del api_keys
    catalog_text, ref_lookup, id_lookup, selection_audit = _prepare_prompt_catalog(raw_by_cat.get(cat, []))
    if not catalog_text:
        raise RuntimeError(f"No citable raw items available for {cat}")

    prompt = _build_ai_prompt(cat, input_cutoff_at, catalog_text)
    ai_raw, model_used, per_key_errs, _ = _call_gemini_json_with_meta(
        prompt,
        scope=f"briefing:{cat}",
        temperature=0.2,
        base_dir=base_dir,
    )
    if not isinstance(ai_raw, dict):
        raise RuntimeError(f"Gemini returned non-object JSON for {cat}")
    selection_audit["model_used"] = model_used
    if per_key_errs:
        selection_audit["gemini_key_errors"] = per_key_errs[:6]

    generated_iso = to_iso_shanghai(now_shanghai())
    used_event_ids: Set[str] = set()
    events: List[dict] = []
    for ordinal, raw_ev in enumerate(ai_raw.get("events", [])):
        if not isinstance(raw_ev, dict) or not raw_ev.get("title"):
            continue
        verified = verify_and_enrich_event(
            raw_ev,
            category=cat,
            input_batch_id=input_batch_id,
            fetched_at_iso=input_cutoff_at,
            ref_lookup=ref_lookup,
            id_lookup=id_lookup,
            prev_events=prev_events,
            prev_batch_id=prev_batch_id,
            require_semantic_match=True,
            used_event_ids=used_event_ids,
            sec_entity_status=sec_entity_status,
            ordinal=ordinal,
        )
        events.append(verified)

    # Resolve key_changes refs and enforce attribution consistency
    key_changes: List[dict] = []
    for kc in ai_raw.get("key_changes", [])[:3]:
        if not isinstance(kc, dict) or not kc.get("headline"):
            continue
        refs = kc.get("source_refs") or []
        first_valid = next((ref_lookup.get(r) or id_lookup.get(r) for r in refs if (ref_lookup.get(r) or id_lookup.get(r))), None)
        key_changes.append(
            {
                "headline": str(kc["headline"]).strip(),
                "detail": str(kc.get("detail") or "").strip(),
                "primary_url": first_valid["canonical_url"] if first_valid else None,
                "source_name": first_valid["source_name"] if first_valid else None,
            }
        )
    if key_changes:
        key_changes = _sync_key_changes_attribution(key_changes, events)
    else:
        key_changes = _build_key_changes_from_events(events)

    overview_sections = []
    for sec in ai_raw.get("overview_sections", []):
        if not isinstance(sec, dict):
            continue
        pts = []
        for p in sec.get("points", []):
            if isinstance(p, dict) and p.get("text"):
                pts.append({"text": str(p["text"]).strip(), "source_refs": p.get("source_refs", [])})
            elif isinstance(p, str) and p.strip():
                pts.append({"text": p.strip(), "source_refs": []})
        if pts:
            overview_sections.append({"title": str(sec.get("title") or "要点").strip(), "points": pts})

    doc = {
        "schema_version": "4.1",
        "batch_id": batch_id,
        "input_batch_id": input_batch_id,
        "input_cutoff_at": input_cutoff_at,
        "generated_at": generated_iso,
        "published_at": generated_iso,
        "category": cat,
        "category_label": CATEGORY_LABELS[cat],
        "generation_mode": "ai_v3_grounded",
        "model_name": model_used or PRIMARY_MODEL,
        "quality_flags": [],
        "key_changes": key_changes,
        "overview_sections": overview_sections,
        "events": events,
    }
    return doc, selection_audit


def _generate_comments_for_category(
    cat: str,
    briefing_doc: dict,
    api_keys: List[str],
    base_dir: Path | str = ".",
) -> dict:
    del api_keys
    if count_healthy_keys(base_dir) < 4:
        cdoc = _build_deterministic_dialectic_comments(cat, briefing_doc, None, {})
        cdoc["status"] = "v3_dialectic_quota_saved"
        return cdoc
    events = [ev for ev in briefing_doc.get("events", []) if ev.get("evidence_status") != "needs_verification"]
    prompt = _build_comments_prompt(cat, events)
    raw_comments, _, _, _ = _call_gemini_json_with_meta(
        prompt,
        scope=f"comments:{cat}",
        temperature=0.7,
        base_dir=base_dir,
    )
    if not isinstance(raw_comments, list):
        raw_comments = []

    clean_comments: List[dict] = []
    valid_event_ids = {ev["event_id"] for ev in briefing_doc.get("events", [])}
    ev_by_id = {ev["event_id"]: ev for ev in briefing_doc.get("events", [])}
    for idx, c in enumerate(raw_comments[:8]):
        if not isinstance(c, dict) or not c.get("content"):
            continue
        target_id = c.get("target_event_id")
        if target_id not in valid_event_ids:
            target_id = briefing_doc["events"][0]["event_id"] if briefing_doc.get("events") else None
        ev_obj = ev_by_id.get(target_id or "") or {}
        clean_comments.append(
            {
                "id": f"sim_{cat}_{idx + 1}",
                "role": str(c.get("role") or PERSPECTIVE_ROLES[idx % len(PERSPECTIVE_ROLES)]),
                "perspective_tag": str(c.get("perspective_tag") or "AI 辩证研判"),
                "target_event_id": target_id,
                "pro_argument": str(c.get("pro_argument") or "").strip() or None,
                "con_argument": str(c.get("con_argument") or "").strip() or None,
                "key_unknown": str(c.get("key_unknown") or "").strip() or None,
                "next_catalyst": str(c.get("next_catalyst") or "").strip() or None,
                "content": str(c["content"]).strip(),
                "stance": str(c.get("stance") or "中性拆解"),
                "evidence_anchor": ev_obj.get("title"),
            }
        )

    return {
        "schema_version": "3.0",
        "batch_id": briefing_doc["batch_id"],
        "input_batch_id": briefing_doc["input_batch_id"],
        "generated_at": to_iso_shanghai(now_shanghai()),
        "category": cat,
        "is_ai_simulated": True,
        "disclaimer": "以下内容由 AI 角色辩证推演生成，拆解正反依据与未知条件，不代表真实用户或特定个人发言。",
        "comments": clean_comments,
    }


def _infer_event_dialectic_slots(ev: dict) -> Tuple[str, str, str]:
    """Generate genuinely event- & domain-specific counter-arguments, key unknowns, and catalysts."""
    title = str(ev.get("title") or "")
    cat = str(ev.get("category") or "")
    ents = [str(e) for e in (ev.get("entities") or []) if str(e).strip()]
    subj = ents[0] if ents else title[:18]
    combined = f"{title} {ev.get('fact_summary') or ''}".lower()

    # Con argument: never copy evidence_status_reason; derive actual falsification risk
    con_raw = (ev.get("contradictions") or [None])[0] or (ev.get("unverified_claims") or [None])[0]
    if con_raw and "独立" not in str(con_raw):
        con_arg = str(con_raw)
    elif any(k in combined for k in ("漏洞", "攻击", "cve", "零日", "注入", "泄露")):
        con_arg = f"关注「{subj}」实际在野利用范围是否被高估，及厂商热修复/缓解措施推进速度。"
    elif any(k in combined for k in ("宕机", "故障", "瘫痪", "停飞")):
        con_arg = f"评估故障是单点配置异常还是系统性架构脆弱，若迅速恢复则长期基本面影响有限。"
    elif any(k in combined for k in ("目标价", "评级", "下调", "上调")):
        con_arg = f"卖方评级与目标价调整常滞后或掺杂短期情绪，需交叉核对实际订单与毛利率兑现。"
    elif any(k in combined for k in ("统计局", "同比", "cpi", "gdp", "出口", "央行", "净回笼", "房地产")):
        con_arg = "单月宏观读数可能受基数效应、季节排期或结构分化扰动，不宜单点外推全年趋势。"
    elif any(k in combined for k in ("开源", "模型", "发布", "agent", "芯片", "tpu")):
        con_arg = f"厂商自报榜单与评测集易存在口径差异，仍看第三方复现口碑及实际商用调用转化。"
    else:
        con_arg = f"当前公开报道偏重表层进展，围绕「{subj}」的实质执行细节与持续约束条件仍待落地。"

    # Key unknown & catalyst strictly matched to domain (never blanket SEC or CVE boilerplate!)
    if any(k in combined for k in ("漏洞", "cve", "零日", "0day", "rce", "sql注入", "代码执行", "勒索软件", "数据泄露", "黑客攻击", "安全补丁")):
        unknown = "完整 CVE 评分、受影响版本清单及官方补丁可用时间表。"
        catalyst = "等待厂商安全响应中心公布补丁编号与受影响范围清单。"
    elif any(k in combined for k in ("fsd", "自动驾驶", "智驾", "ota", "无人驾驶")):
        unknown = "功能实际开放地域、城市道路接管率表现及监管部门路测合规口径。"
        catalyst = "关注车企后续软件推送说明、监管合规通报及第三方实测表现。"
    elif any(k in combined for k in ("signal", "截屏", "加密通讯", "端到端加密", "隐私保护")):
        unknown = "系统权限限制的实际生效范围及跨平台客户端同步节奏。"
        catalyst = "关注应用后续版本更新日志及跨平台安全特性适配进展。"
    elif any(k in combined for k in ("宕机", "故障", "瘫痪", "停飞", "服务中断")) or ("恢复" in combined and any(k in combined for k in ("服务", "系统", "网络", "供电", "运行", "机场", "航班"))):
        unknown = "事故根本原因 (Root Cause)、SLA 赔付规模与冗余架构整改期限。"
        catalyst = "关注官方状态页 Postmortem 复盘报告及恢复运营通告。"
    elif any(k in combined for k in ("开源", "github", "hugging face", "paper", "framework", "论文", "黎曼", "lean")) or (
        any(k in combined for k in ("大模型", "模型发布", "评测")) and not any(k in combined for k in ("资金", "融资", "ipo", "股价", "股", "投资"))
    ):
        unknown = "完整权重许可条款、实际推理成本效率及第三方独立基准复现表现。"
        catalyst = "跟踪 GitHub / Hugging Face 模型卡更新及独立开发者压测反馈。"
    elif any(k in combined for k in ("统计局", "宏观", "利率", "fomc", "央行", "会晤", "峰会", "外长")):
        unknown = "后续财政/货币配套细则落地力度与跨国磋商的实际约束力条文。"
        catalyst = "关注下月官方宏观读数、央行货币政策例会声明或双边联合公报。"
    elif cat == "finance" or any(k in combined for k in ("sec", "8-k", "10-q", "财报", "ipo", "目标价", "ceo", "股价", "港股", "融资")):
        unknown = f"相关动作对「{subj}」季度营收指引、现金流及监管披露口径的实际影响程度。"
        catalyst = "关注公司下一次财报电话会、SEC/交易所正式公告或机构实单反馈。"
    else:
        unknown = f"事件当事方/主管机构对「{title[:16]}」的后续正式处置与公开通报详情。"
        catalyst = "关注主管部门后续正式通报及权威媒体的实证跟进。"

    return con_arg, unknown, str(ev.get("speculation_or_outlook") or catalyst)


def _build_deterministic_dialectic_comments(
    cat: str,
    briefing_doc: dict,
    prev_comments_doc: Optional[dict],
    old_id_to_new_id: Dict[str, str],
) -> dict:
    """Build deterministic, event-tailored dialectical cards during offline ground_update (zero template boilerplate)."""
    events = briefing_doc.get("events") or []
    prev_comments = prev_comments_doc.get("comments", []) if isinstance(prev_comments_doc, dict) else []
    prev_by_target: Dict[str, List[dict]] = {}
    for pc in prev_comments:
        if isinstance(pc, dict):
            mapped = old_id_to_new_id.get(pc.get("target_event_id") or "")
            if mapped:
                prev_by_target.setdefault(mapped, []).append(pc)

    out_comments: List[dict] = []
    for idx, ev in enumerate([e for e in events if e.get("evidence_status") != "needs_verification"][:6]):
        eid = ev["event_id"]
        prev_c = (prev_by_target.get(eid) or [None])[0]
        pro_arg = ev.get("fact_summary") or ev["title"]
        con_arg, unknown, catalyst = _infer_event_dialectic_slots(ev)
        # Do not carry forward legacy boilerplate "是否已通过 SEC/交易所..." from previous snapshots
        prev_unknown = prev_c.get("key_unknown") if prev_c else None
        if prev_unknown and "是否已通过 SEC/交易所正式文件或独立复现确认关键数据" in str(prev_unknown):
            prev_unknown = None

        content_text = (prev_c.get("content") if prev_c else None) or (
            f"核心依据：{_smart_truncate(str(pro_arg), 70)}；反向校验：{_smart_truncate(str(con_arg), 70)}"
        )
        out_comments.append(
            {
                "id": f"sim_v3_{cat}_{idx + 1}",
                "role": (prev_c.get("role") if prev_c else None) or PERSPECTIVE_ROLES[idx % len(PERSPECTIVE_ROLES)],
                "perspective_tag": f"AI 辩证研判 · {(ev.get('entities') or [_smart_truncate(ev['title'], 14)])[0]}",
                "target_event_id": eid,
                "pro_argument": _smart_truncate(str(pro_arg), 160),
                "con_argument": _smart_truncate(str(con_arg), 160),
                "key_unknown": _smart_truncate(str(prev_unknown or unknown), 150),
                "next_catalyst": _smart_truncate(str(catalyst), 140),
                "content": str(content_text).strip(),
                "stance": (prev_c.get("stance") if prev_c else None) or "中性拆解",
            }
        )

    return {
        "schema_version": "3.0",
        "batch_id": briefing_doc["batch_id"],
        "input_batch_id": briefing_doc["input_batch_id"],
        "generated_at": briefing_doc["generated_at"],
        "category": cat,
        "is_ai_simulated": True,
        "status": "v3_dialectic_grounded",
        "disclaimer": "以下正反辩证拆解由本批次已核验事件与监管/证据规则确定性生成（未编造外部观点），不代表真实个人或用户发言。",
        "comments": out_comments,
    }


def _ground_update_category(
    root: Path,
    cat: str,
    prev_cat_meta: dict,
    raw_by_cat: Dict[str, List[dict]],
    input_batch_id: str,
    input_cutoff_at: str,
    generated_at_iso: str,
    batch_id: str,
    prev_events: List[dict],
    prev_batch_id: Optional[str],
    sec_entity_status: Optional[Dict[str, dict]] = None,
) -> Tuple[dict, dict, Dict[str, Any]]:
    """
    Upgrade the latest existing briefing deterministically with V3 identity separation,
    independent-publisher dedup, newly deep-fetched excerpts, and live first-party connectors.
    """
    existing_path = prev_cat_meta.get("path")
    existing_doc = load_json_if_exists(root / existing_path, default={}) if existing_path else {}
    if not isinstance(existing_doc, dict) or not (existing_doc.get("events") or existing_doc.get("items")):
        existing_doc = load_json_if_exists(root / f"analysis_{cat}.json", default={}) or {}

    prev_comments_path = prev_cat_meta.get("comments_path")
    prev_comments_doc = (
        load_json_if_exists(root / prev_comments_path, default={})
        if prev_comments_path
        else load_json_if_exists(root / f"comments_{cat}.json", default={})
    )

    own_raw = [x for x in raw_by_cat.get(cat, []) if x.get("citable_as_news", True) and x.get("source_kind") != "market_ticker"]
    cross_raw = [
        x
        for c in CATEGORIES
        if c != cat
        for x in raw_by_cat.get(c, [])
        if x.get("citable_as_news", True) and x.get("source_kind") != "market_ticker"
    ]
    all_raw = own_raw + cross_raw

    # Run priority scoring audit so V3 can expose omitted high/low priority trace
    _, _, _, selection_audit = _prepare_prompt_catalog(raw_by_cat.get(cat, []))

    raw_by_url: Dict[str, dict] = {}
    id_lookup: Dict[str, dict] = {}
    ref_lookup: Dict[str, dict] = {}
    for idx, r in enumerate(all_raw, start=1):
        rk = f"R{idx:04d}"
        r_copy = dict(r)
        ref_lookup[rk] = r_copy
        if r_copy.get("item_id"):
            id_lookup[r_copy["item_id"]] = r_copy
        cu = canonicalize_url(r_copy.get("canonical_url") or r_copy.get("url"))
        if cu and cu not in raw_by_url:
            raw_by_url[cu] = r_copy

    existing_entries = list(existing_doc.get("events") or existing_doc.get("items") or []) if isinstance(existing_doc, dict) else []
    used_event_ids: Set[str] = set()
    events: List[dict] = []
    seen_urls: Set[str] = set()
    old_id_to_new_id: Dict[str, str] = {}

    if not existing_entries:
        for r in own_raw[:8]:
            existing_entries.append(
                {
                    "title": r["title"],
                    "fact_summary": r.get("excerpt") or r["title"],
                    "ai_analysis": "冷启动模式由原始抓取直接生成（未叠加模型解读）。",
                    "sources": [r],
                }
            )

    cutoff_dt = parse_iso_datetime(input_cutoff_at) or now_shanghai()

    for ordinal, item in enumerate(existing_entries):
        if not isinstance(item, dict) or not item.get("title"):
            continue
        title = repair_mojibake(str(item.get("title") or "").strip())
        # Prune stale >10d connector releases and unwatched HKEX boilerplate from daily briefing feed
        if "展示文件" in title and not item.get("entity_ids"):
            continue
        item_srcs = item.get("sources") or []
        item_ts = parse_iso_datetime(item.get("latest_reported_at") or item.get("first_reported_at") or item.get("published_at"))
        is_pure_connector = title.startswith(("[GitHub Release]", "[HF 模型卡]", "[SEC ", "[巨潮 ", "[HKEX ")) or (
            bool(item_srcs) and all(s.get("source_id") in {"github-releases", "huggingface-hub", "cninfo", "hkexnews", "sec-edgar"} for s in item_srcs if isinstance(s, dict))
        )
        if is_pure_connector and item_ts and (cutoff_dt - item_ts) > timedelta(days=10):
            continue

        old_eid = str(item.get("event_id") or "")
        q_tokens = extract_tokens(title)

        ref_ids: List[str] = []
        upgraded_excerpt: Optional[str] = None
        # 1. Re-link existing sources first, upgrading any matching live raw record (richer excerpt / deep lead)
        for es in item.get("sources") or []:
            if not isinstance(es, dict):
                continue
            cu = canonicalize_url(es.get("url"))
            if not cu or is_generic_quote_or_homepage_url(cu, es.get("source_id", "")):
                continue
            seen_urls.add(cu)
            if cu in raw_by_url:
                live_rec = raw_by_url[cu]
                ref_ids.append(live_rec["item_id"])
                if live_rec.get("excerpt") and len(str(live_rec["excerpt"])) > len(upgraded_excerpt or ""):
                    upgraded_excerpt = str(live_rec["excerpt"])
            else:
                eid_src = es.get("item_id") or make_raw_item_id(es.get("source_id", "src"), cu, es.get("title") or title)
                if eid_src not in id_lookup:
                    id_lookup[eid_src] = {**es, "item_id": eid_src, "canonical_url": cu, "citable_as_news": True}
                ref_ids.append(eid_src)

        # 2. Discover new independent coverage or deep-fetched sources in own_raw for the same event
        # Strictly exclude omnibus digests, conflicting entities (e.g. AMD filings onto NVDA), and >48h stale articles
        from pipeline.dedup import entities_conflict, is_omnibus_digest_title

        anchor_dt = None
        for r_cur in own_raw:
            cu_cur = canonicalize_url(r_cur.get("canonical_url") or r_cur.get("url"))
            if cu_cur and cu_cur in seen_urls and r_cur.get("published_at"):
                anchor_dt = parse_iso_datetime(r_cur.get("published_at"))
                if anchor_dt:
                    break

        for r in own_raw:
            r_title = r.get("title", "")
            cu = canonicalize_url(r.get("canonical_url") or r.get("url"))
            if not cu or cu in seen_urls:
                continue
            if is_omnibus_digest_title(r_title):
                continue
            if entities_conflict(title, r_title, item_b=r):
                continue
            if anchor_dt and r.get("published_at"):
                r_dt = parse_iso_datetime(r.get("published_at"))
                if r_dt and abs((anchor_dt - r_dt).total_seconds()) > 48 * 3600:
                    continue
            sim = title_similarity(title, r_title)
            shared = len(q_tokens & extract_tokens(r_title))
            if sim >= 0.50 or (sim >= 0.36 and shared >= 4):
                if r["item_id"] not in ref_ids:
                    ref_ids.append(r["item_id"])
                if r.get("excerpt") and len(str(r["excerpt"])) > len(upgraded_excerpt or ""):
                    upgraded_excerpt = str(r["excerpt"])
                seen_urls.add(cu)
            if len(ref_ids) >= 6:
                break

        raw_fact = repair_mojibake(str(item.get("fact_summary") or item.get("summary") or ""))
        if upgraded_excerpt and ("原始素材仅含标题" in raw_fact or len(raw_fact) < len(title) + 12):
            raw_fact = upgraded_excerpt

        candidate_ev = {
            "event_id": old_eid or None,
            "title": title,
            "fact_summary": raw_fact,
            "ai_analysis": repair_mojibake(str(item.get("ai_analysis") or item.get("impact") or "")),
            "unverified_claims": item.get("unverified_claims") or [],
            "speculation_or_outlook": item.get("speculation_or_outlook"),
            "entities": item.get("entities") or [],
            "importance": item.get("importance") or "normal",
            "sentiment": item.get("sentiment"),
            "special_note": item.get("special_note"),
            "thumbnail_url": item.get("thumbnail_url"),
            "event_date": item.get("event_date"),
            "source_refs": ref_ids,
            "sources": item.get("sources") or [],
        }
        verified_ev = verify_and_enrich_event(
            candidate_ev,
            category=cat,
            input_batch_id=input_batch_id,
            fetched_at_iso=input_cutoff_at,
            ref_lookup=ref_lookup,
            id_lookup=id_lookup,
            prev_events=prev_events,
            prev_batch_id=prev_batch_id,
            require_semantic_match=False,
            used_event_ids=used_event_ids,
            sec_entity_status=sec_entity_status,
            ordinal=ordinal,
        )
        if old_eid:
            old_id_to_new_id[old_eid] = verified_ev["event_id"]
        events.append(verified_ev)

    # 3. Inject up to 4 diverse, live recent first-party connector disclosures (SEC / HKEX / Fed / GitHub / HF / arXiv)
    cutoff_dt = parse_iso_datetime(input_cutoff_at) or now_shanghai()
    first_party_candidates: List[dict] = []
    for r in own_raw:
        if not (r.get("source_tier") == "first_party" or r.get("source_id") in {"sec-edgar", "github-releases", "huggingface-hub", "hkexnews", "cninfo", "fed-fomc"}):
            continue
        pub_dt = parse_iso_datetime(r.get("published_at")) if r.get("published_at") else None
        if pub_dt and (cutoff_dt - pub_dt) > timedelta(days=14):
            continue
        cu = canonicalize_url(r.get("canonical_url") or r.get("url"))
        if cu in seen_urls or any(title_similarity(r.get("title", ""), e.get("title", "")) >= 0.42 for e in events):
            continue
        first_party_candidates.append(r)
    # Pick round-robin across connectors so no single source dominates
    picked_connectors: List[dict] = []
    seen_cids: Set[str] = set()
    for pass_num in range(2):
        for r in first_party_candidates:
            cid = r.get("source_id", "")
            if pass_num == 0 and cid in seen_cids:
                continue
            if r in picked_connectors:
                continue
            picked_connectors.append(r)
            seen_cids.add(cid)
            if len(picked_connectors) >= 4:
                break
        if len(picked_connectors) >= 4:
            break

    for offset, cit in enumerate(picked_connectors):
        cu = canonicalize_url(cit.get("canonical_url") or cit.get("url"))
        if cu:
            seen_urls.add(cu)
        candidate_ev = {
            "title": cit["title"],
            "fact_summary": cit.get("excerpt") or cit["title"],
            "ai_analysis": "源自官方公开文档及一手披露记录，保持客观事实陈述。",
            "unverified_claims": [],
            "speculation_or_outlook": None,
            "entities": [],
            "importance": "high" if cit.get("source_kind") in {"official_filing", "regulatory_release"} else "medium",
            "sentiment": "Neutral",
            "source_refs": [cit["item_id"]],
        }
        verified_ev = verify_and_enrich_event(
            candidate_ev,
            category=cat,
            input_batch_id=input_batch_id,
            fetched_at_iso=input_cutoff_at,
            ref_lookup=ref_lookup,
            id_lookup=id_lookup,
            prev_events=prev_events,
            prev_batch_id=prev_batch_id,
            require_semantic_match=False,
            used_event_ids=used_event_ids,
            sec_entity_status=sec_entity_status,
            ordinal=len(events) + offset,
        )
        events.append(verified_ev)

    # 4. Surface genuinely fresh breaking clusters from own_raw so a new batch is never "0 new items"
    existing_norm_titles = [str(e.get("title") or "") for e in events]
    existing_norm_titles += [str(pe.get("title") or "") for pe in prev_events]
    clustered_own = deduplicate_raw_items(own_raw)
    fresh_promoted = 0
    scored_fresh: List[Tuple[float, dict]] = []
    for cl in clustered_own:
        t = str(cl.get("title") or "").strip()
        if not t or is_omnibus_digest_title(t) or is_consumer_promo_or_fluff(t, str(cl.get("excerpt") or "")) or _is_unrelated_company_mashup(t):
            continue
        if cl.get("source_kind") == "discussion":
            continue
        cl_srcs = cl.get("related_sources") or [cl]
        if _MARKET_PRICE_RE.search(t) and not has_authoritative_primary_source(cl_srcs):
            continue
        cu = canonicalize_url(cl.get("canonical_url") or cl.get("url"))
        if cu in seen_urls or any(title_similarity(t, et) >= 0.38 or not entities_conflict(t, et) and title_similarity(t, et) >= 0.30 for et in existing_norm_titles):
            continue
        pub_dt = parse_iso_datetime(cl.get("published_at")) if cl.get("published_at") else None
        if pub_dt and (cutoff_dt - pub_dt) > timedelta(hours=36):
            continue
        ent_hits = match_entities_with_reasons(f"{t} {cl.get('excerpt') or ''}")
        sc, _ = score_cluster_for_briefing(cl, watched_match_count=len(ent_hits))
        if sc >= 16.0 or (cl.get("independent_publisher_count", 1) >= 2 and pub_dt):
            scored_fresh.append((sc, cl))

    scored_fresh.sort(key=lambda x: x[0], reverse=True)
    promoted_events: List[dict] = []
    for sc, cl in scored_fresh[:5]:
        rel_srcs = cl.get("related_sources") or [cl]
        src_ids = [s.get("item_id") for s in rel_srcs[:4] if s.get("item_id")]
        if not src_ids:
            continue
        fresh_candidate = {
            "title": cl["title"],
            "fact_summary": cl.get("excerpt") or f"{cl['title']}（来源：{cl.get('source_name', '多源快讯')}）",
            "ai_analysis": "【本批新晋突发】由高评分最新信源聚类直采，待后续批次持续追踪进展。",
            "unverified_claims": [],
            "speculation_or_outlook": None,
            "entities": [h["canonical_name"] for h in match_entities_with_reasons(cl["title"])[:3]],
            "importance": "medium",
            "sentiment": "Neutral",
            "source_refs": src_ids,
        }
        v_fresh = verify_and_enrich_event(
            fresh_candidate,
            category=cat,
            input_batch_id=input_batch_id,
            fetched_at_iso=input_cutoff_at,
            ref_lookup=ref_lookup,
            id_lookup=id_lookup,
            prev_events=prev_events,
            prev_batch_id=prev_batch_id,
            require_semantic_match=False,
            used_event_ids=used_event_ids,
            sec_entity_status=sec_entity_status,
            ordinal=len(events) + fresh_promoted + 20,
        )
        # Explicitly anchor newly surfaced clusters as fresh in this batch
        v_fresh["is_new_in_batch"] = True
        v_fresh["update_kind"] = "new_discovery"
        promoted_events.append(v_fresh)
        existing_norm_titles.append(v_fresh["title"])
        for s in v_fresh.get("sources", []):
            cu_s = canonicalize_url(s.get("url"))
            if cu_s:
                seen_urls.add(cu_s)
        fresh_promoted += 1

    if promoted_events:
        # Place genuine fresh breaking developments near top while retaining top verified carryovers
        events = promoted_events + events

    # Guard against cumulative attribution prefix duplication and strip stale rumor prefixes from broadly confirmed multi-source events
    for ev in events:
        t_clean = dedupe_attribution_prefixes(str(ev.get("title") or ""))
        s_clean = dedupe_attribution_prefixes(str(ev.get("fact_summary") or ""))
        indep_c = int(ev.get("independent_publisher_count") or len(ev.get("sources") or []))
        if indep_c >= 3 and not ev.get("contradictions") and not re.search(r"(?:传闻|爆料|网传|知情人士|考虑|拟于|或将)", t_clean):
            t_clean = re.sub(r"^(?:报道称|消息称|据报道|外媒称)[:：]\s*", "", t_clean).strip()
            s_clean = re.sub(r"^【据关联报道/尚未见官方披露确认】\s*", "", s_clean).strip()
            ev["attribution_warning"] = None
        ev["title"] = t_clean
        ev["fact_summary"] = s_clean

    raw_kcs = existing_doc.get("key_changes") if isinstance(existing_doc, dict) else None
    key_changes = _build_key_changes_from_events(events) if promoted_events else (_sync_key_changes_attribution(raw_kcs, events) if raw_kcs else _build_key_changes_from_events(events))
    overview_sections = existing_doc.get("overview_sections", []) if isinstance(existing_doc, dict) else []

    doc = {
        "schema_version": "4.1",
        "batch_id": batch_id,
        "input_batch_id": input_batch_id,
        "input_cutoff_at": input_cutoff_at,
        "generated_at": generated_at_iso,
        "published_at": to_iso_shanghai(now_shanghai()),
        "category": cat,
        "category_label": CATEGORY_LABELS[cat],
        "generation_mode": "v3_ground_update",
        "model_name": "deterministic-v3-grounding",
        "quality_flags": ["ground_update_mode"],
        "key_changes": key_changes,
        "overview_sections": overview_sections,
        "events": events,
    }
    cdoc = _build_deterministic_dialectic_comments(cat, doc, prev_comments_doc, old_id_to_new_id)
    return doc, cdoc, selection_audit


_TRACKED_HKEX_CODES = {"00700", "09988", "00981", "03690"}
_TOPIC_PAIRS = [
    ({"黄仁勋", "英伟达"}, {"卸任", "辞任", "辞职", "复职", "重返", "继任", "ceo"}),
    ({"英伟达", "nvda", "纳指", "ai板块", "美股ai"}, {"暴跌", "重挫", "抛售潮", "14%", "抹去", "蒸发", "破发"}),
    ({"anthropic", "claude"}, {"ipo", "上市", "募资", "破发", "发行价", "935亿", "813亿"}),
    ({"gemini 4", "gemini4", "neon", "diffusiongemma"}, {"发布", "上线", "推出", "智能", "google"}),
    ({"黄金", "金价", "白银", "现货黄金"}, {"暴跌", "跳水", "大跌", "3600", "风险", "14个月新低"}),
    ({"软银", "孙正义"}, {"sk海力士", "海力士", "1万亿美元"}),
    ({"美伊", "伊朗", "霍尔木兹"}, {"柏林", "谈判", "僵局", "斡旋", "动武", "触雷", "油轮"}),
    ({"俄乌", "乌克兰", "泽连斯基", "普京"}, {"和平协议", "停火", "战后", "空袭", "波兰", "导弹"}),
    ({"微软", "azure", "microsoft"}, {"宕机", "恢复", "故障"}),
    ({"微软", "win11", "windows"}, {"copilot", "强制", "默认", "争议"}),
    ({"特朗普", "trump", "白宫"}, {"巨税", "征重税", "数据中心", "发布会", "关税"}),
    ({"apec", "深圳", "峰会"}, {"三方", "双边", "和平宣言", "元首", "会晤", "高市早苗", "落幕"}),
    ({"英国", "脱欧"}, {"欧盟", "峰会", "协议"}),
    ({"美联储", "fomc"}, {"加息", "放鹰", "分歧", "库克", "紧缩"}),
    ({"黎曼猜想", "riemann", "tensorlean"}, {"lean", "形式化", "证明", "验证"}),
    ({"特斯拉", "tesla", "fsd"}, {"fsd", "v15", "自动驾驶", "开放", "欧洲", "中国"}),
    ({"克里米亚大桥", "克里米亚"}, {"爆炸", "恢复", "通车", "通行"}),
    ({"比特币", "bitcoin", "btc"}, {"60000", "6万", "跌破", "重返", "反弹", "61000"}),
    ({"稀土", "泰国"}, {"化学品", "禁止", "出口", "稀土"}),
    ({"欧盟", "欧洲"}, {"多年期预算", "削减预算", "预算案"}),
]


_ENTITY_ALIAS_CANON: Dict[str, str] = {}
for _ed in ENTITY_REGISTRY:
    _cname = str(getattr(_ed, "canonical_name", "") or "").strip()
    if _cname:
        _ENTITY_ALIAS_CANON[_cname.lower()] = _cname
        for _al in getattr(_ed, "aliases", ()) or ():
            _al_s = str(_al or "").strip().lower()
            if len(_al_s) >= 2 and _al_s not in ("ai", "us", "hk", "美元", "黄金"):
                _ENTITY_ALIAS_CANON[_al_s] = _cname

_PIPELINE_JARGON_RE = re.compile(
    r"(?:（[^）]*原始素材[^）]*）|\([^)]*(?:R\d{2,4}|原始素材)[^)]*\)|"
    r"[（(]\s*[、,，]?\s*(?:原始素材多?)?仅含?标题\s*[)）]|"
    r"[、,，]?\s*(?:原始素材多?)?仅含?标题(?:[，,。；:\s]*(?:细节待查原文|具体[^。；;]*))?[。.]?\s*|"
    r"\[?R\d{2,4}\]?\s*(?:原始素材[^，,。；;)\s]*|[：:])?\s*|"
    r"(?:另)?据仅含标题的(?:快讯|资讯)[，,：:\s]*(?:报道|显示)?[，,]?\s*|"
    r"已拦截\s*\d+\s*条无效引用(?:（[^）]*）)?[；;，,。]*\s*)",
    re.I,
)
_GEO_KINETIC_OR_DIPLO_RE = re.compile(
    r"(?:导弹|空袭|击落(?:美军|无人)?机|无人机被击落|停火|和平协议|战区|领空|航母|军演|大使馆|"
    r"北约|联合国安理会|外交照会|总统选举|国会大厦|美伊|俄乌|以哈|巴以|半岛局势|台海|南海)",
    re.I,
)
_INTL_SUBJECT_RE = re.compile(
    r"(?:美联储|FOMC|欧央行|欧洲央行|日本央行|英格兰银行|特朗普|白宫|五角大楼|美国国会|华盛顿|"
    r"布鲁塞尔|莫斯科|基辅|德黑兰|特拉维夫|伦敦|巴黎|柏林|东京|首尔|APEC|G7|G20|IMF|WTO|关税|"
    r"出口管制|实体清单|美股|纳指|标普|道指|港股|恒指|英伟达|NVIDIA|OpenAI|Anthropic|Google|"
    r"DeepMind|Meta|微软|Microsoft|苹果|Apple|亚马逊|Amazon|特斯拉|Tesla|台积电|TSMC|ASML|SK海力士|软银|霍尔木兹|苏伊士)",
    re.I,
)
_DOMESTIC_CHINA_ENTITY_RE = re.compile(
    r"(?:发改委|工信部|商务部|财政部|证监会|(?<![欧日韩美英俄])(?<!欧洲)央行|中国人民银行|中国央行|国家统计局|国务院|教育部|卫健委|市场监管总局|工信|"
    r"人民日报|新华社|央视新闻|经济日报|国资委|住建部|交通运输部|文旅部|最高法|最高检|"
    r"A股|沪深|科创板|创业板|北交所|上交所|深交所|顺德|佛山|广东|深圳|北京|上海|杭州|成都|重庆|武汉|江苏|浙江|山东|河南)"
)
_FINANCE_MARKET_RE = re.compile(
    r"(?:股价|市值|财报|营收|净利润|毛利率|回购|减持|增持|IPO|上市|破发|债券|国债|收益率|汇率|利率|加息|降息|降准|LPR|"
    r"比特币|以太坊|BTC|ETH|加密货币|虚拟货币|Web3|"
    r"通胀|CPI|PPI|GDP|油价|金价|现货黄金|期货|上期所|证监会|SEC|8-K|10-Q|6-K|HKEX|港交所|做空|ETF|估值|FOMC)",
    re.I,
)
_TECH_AI_RE = re.compile(
    r"(?:大模型|LLM|GPT|Claude|Gemini|DeepSeek|Qwen|通义千问|Kimi|混元|OpenAI|Anthropic|Hugging Face|GitHub|"
    r"开源|SGLang|vLLM|算力|GPU|TPU|HBM|光刻机|晶圆|2nm|3nm|Copilot|Agent|智能体|自动驾驶|机器人|量子|CVE|零日漏洞)",
    re.I,
)


_GENERIC_ENTITY_NOISE_RE = re.compile(
    r"^(?:国内|海外|全球|国际|部分|多家|相关|主要|权威|一线|头部)?(?:黄金珠宝品牌|商业银行|金融科技公司|金融机构|科技公司|互联网大厂|车企|制造商|供应链|相关企业|市场分析师|行业人士|地方政府|监管机构)$"
)


def _normalize_event_entities(entities: Any) -> List[str]:
    if not isinstance(entities, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for raw_e in entities:
        s = str(raw_e or "").strip()
        if not s or len(s) > 22:
            continue
        if _GENERIC_ENTITY_NOISE_RE.match(s) or s.startswith(("国内", "多家", "部分", "相关")) and len(s) >= 6:
            continue
        canon = _ENTITY_ALIAS_CANON.get(s.lower(), s)
        k = canon.lower()
        if k not in seen:
            seen.add(k)
            out.append(canon)
    return out[:6]


def _reclassify_region_topic_events(cat_docs: Dict[str, dict]) -> None:
    """Enforce region + topic category boundaries (e.g. Iran drone -> global, domestic A-share/policy out of global)."""
    moves: List[Tuple[str, str, dict]] = []
    for cat, doc in cat_docs.items():
        evs = doc.get("events", []) or []
        for ev in evs:
            title = str(ev.get("title") or "")
            summary = str(ev.get("fact_summary") or "")
            text = f"{title} {summary[:140]}"
            target = cat
            if _GEO_KINETIC_OR_DIPLO_RE.search(title) and not re.search(
                r"(?:美联储|FOMC|利率决议|财报|营收|回购|油价|金价|指数|股价)", title
            ):
                target = "global"
            elif re.search(r"(?:比特币|以太坊|\bBTC\b|\bETH\b|加密货币|虚拟货币|现货黄金|上期所|沪金)", title, re.I) and not _GEO_KINETIC_OR_DIPLO_RE.search(title):
                target = "finance"
            elif cat == "global":
                is_us_commerce = bool(re.search(r"(?:美国商务部|美商务部|美财长|美国财政部)", title))
                if (
                    (_DOMESTIC_CHINA_ENTITY_RE.search(title) and not is_us_commerce)
                    or (
                        _DOMESTIC_CHINA_ENTITY_RE.search(text)
                        and not _INTL_SUBJECT_RE.search(text)
                        and not _GEO_KINETIC_OR_DIPLO_RE.search(text)
                    )
                ):
                    if _FINANCE_MARKET_RE.search(text):
                        target = "finance"
                    elif _TECH_AI_RE.search(text):
                        target = "tech"
                    else:
                        target = "general"
            if target != cat and target in cat_docs:
                moves.append((cat, target, ev))
    if not moves:
        return
    for src_cat, dst_cat, ev in moves:
        src_evs = cat_docs[src_cat].get("events") or []
        if len(src_evs) <= 1:
            continue
        if ev in src_evs:
            src_evs.remove(ev)
            ev["category"] = dst_cat
            dst_evs = cat_docs[dst_cat].setdefault("events", [])
            if all(existing.get("event_id") != ev.get("event_id") for existing in dst_evs):
                dst_evs.append(ev)


_MASHUP_CORP_VERB_RE = re.compile(r"(?:回购|增资|辞职|辞任|减持|增持|定增|分红|预披露|股东大会|更换|聘任)")
_MASHUP_SHARED_PREFIX_GUARD_RE = re.compile(r"(?:沪深北交易所|三大交易所|联合|集体|多只|多家|证监会)")


def _is_unrelated_company_mashup(title: str) -> bool:
    """Detect synthetic multi-company bulletin roundups like '通威股份回购、思特威增资、三安光电辞职'."""
    t = str(title or "").strip()
    if not t or _MASHUP_SHARED_PREFIX_GUARD_RE.search(t):
        return False
    parts = [p.strip() for p in re.split(r"[、,，;；]", t) if p.strip()]
    if len(parts) < 3:
        return False
    verb_parts = sum(1 for p in parts if _MASHUP_CORP_VERB_RE.search(p))
    return verb_parts >= 2


def _same_cross_category_story(ev_a: dict, ev_b: dict) -> bool:
    """Detect cross-category echoes (only same core story in titles, never collapsing distinct angles like MSFT/NVDA ratings)."""
    ta = str(ev_a.get("title") or "")
    tb = str(ev_b.get("title") or "")
    la = ta.lower()
    lb = tb.lower()
    for ent_pair in (
        ("思特威", "增资"),
        ("思特威", "15亿"),
        ("bepicolombo", "水星"),
        ("梅纳德", "黎曼"),
    ):
        if all(k in la for k in ent_pair) and all(k in lb for k in ent_pair):
            return True
    # Explicit shared macro/event-cluster topic pairs (even if headlines highlight adjacent tickers like NVDA vs Anthropic in the same market selloff)
    distinct_angle_re = re.compile(r"(?:目标价|评级|tpu|走私|法院)")
    if distinct_angle_re.search(la) == distinct_angle_re.search(lb):
        for group1, group2 in _TOPIC_PAIRS:
            if any(k in la for k in group1) and any(k in lb for k in group1):
                if any(k in la for k in group2) and any(k in lb for k in group2):
                    return True
    if entities_conflict(ta, tb, item_a=ev_a, item_b=ev_b):
        return False
    urls_a = {canonicalize_url(s.get("url")) for s in ev_a.get("sources") or [] if s.get("url")}
    urls_b = {canonicalize_url(s.get("url")) for s in ev_b.get("sources") or [] if s.get("url")}
    if urls_a & urls_b:
        return True
    sim = title_similarity(ta, tb)
    if sim >= 0.42:
        return True
    return False


def _clean_single_event_sources_and_dates(ev: dict) -> dict:
    """Strip entity-conflicting, omnibus, and >60h stale outlier sources attached to an event."""
    sources = list(ev.get("sources") or [])
    if not sources:
        return ev
    ev_title = str(ev.get("title") or "")

    clean_srcs = [
        s
        for s in sources
        if not entities_conflict(ev_title, str(s.get("title") or ""), item_b=s)
        and not is_omnibus_digest_title(str(s.get("title") or ""))
    ]
    if not clean_srcs:
        clean_srcs = [
            s for s in sources if not entities_conflict(ev_title, str(s.get("title") or ""), item_b=s)
        ] or sources[:1]

    dated = []
    for s in clean_srcs:
        dt = parse_iso_datetime(s.get("published_at")) if s.get("published_at") else None
        if dt is not None:
            dated.append((dt, s))
    if len(dated) >= 2:
        newest_dt = max(dt for dt, _ in dated)
        pruned = []
        for s in clean_srcs:
            dt = parse_iso_datetime(s.get("published_at")) if s.get("published_at") else None
            if dt is not None and (newest_dt - dt).total_seconds() > 60 * 3600:
                if title_similarity(ev_title, str(s.get("title") or "")) < 0.48:
                    continue
            pruned.append(s)
        if pruned:
            clean_srcs = pruned

    ev = dict(ev)
    ev["entities"] = _normalize_event_entities(ev.get("entities"))
    fact_s = _PIPELINE_JARGON_RE.sub("", str(ev.get("fact_summary") or "")).strip()
    if fact_s:
        ev["fact_summary"] = _smart_truncate(fact_s, 220)
    for sum_k in ("summary", "summary_zh"):
        if ev.get(sum_k):
            cleaned_sk = _PIPELINE_JARGON_RE.sub("", str(ev[sum_k])).strip()
            ev[sum_k] = _smart_truncate(cleaned_sk, 220) if cleaned_sk else ev.get("fact_summary", "")
    if ev.get("ai_analysis"):
        ai_s = _PIPELINE_JARGON_RE.sub("", str(ev["ai_analysis"])).strip()
        ev["ai_analysis"] = _smart_truncate(ai_s, 190) if ai_s else None
    if ev.get("speculation_or_outlook"):
        sp_s = _PIPELINE_JARGON_RE.sub("", str(ev["speculation_or_outlook"])).strip()
        ev["speculation_or_outlook"] = _smart_truncate(sp_s, 180) if sp_s else None
    if ev.get("evidence_status_reason"):
        rs_s = _PIPELINE_JARGON_RE.sub("", str(ev["evidence_status_reason"])).strip()
        ev["evidence_status_reason"] = rs_s or "暂缺足够一手原文链接，已归入待核实区域"

    ev["sources"] = sorted(clean_srcs, key=_source_rank_key)
    clean_srcs = ev["sources"]
    if not ev.get("thumbnail_url"):
        ev["thumbnail_url"] = next((s.get("thumbnail_url") for s in clean_srcs if s.get("thumbnail_url")), None)
    ev["source_count"] = len(clean_srcs)
    platforms = {s.get("source_id") for s in clean_srcs if s.get("source_id")}
    indep_fams = {
        s.get("publisher_family") or get_publisher_family(s.get("source_id", ""))
        for s in clean_srcs
        if not s.get("is_reprint_copy")
    }
    ev["platform_count"] = len(platforms)
    ev["independent_publisher_count"] = len(indep_fams) or (1 if clean_srcs else 0)
    ev["reprint_count"] = sum(1 for s in clean_srcs if s.get("is_reprint_copy"))

    valid_pub = [s.get("published_at") for s in clean_srcs if s.get("published_at")]
    if valid_pub:
        sorted_pub = sorted(valid_pub, key=lambda iso: (parse_iso_datetime(iso) or now_shanghai()))
        ev["first_reported_at"] = sorted_pub[0]
        ev["published_at"] = sorted_pub[0]
        ev["latest_reported_at"] = sorted_pub[-1]
        ev["latest_fact_update_at"] = sorted_pub[-1]

    has_fp = any(s.get("source_tier") == "first_party" for s in clean_srcs)
    if has_fp:
        ev["evidence_status"] = "official_confirmed"
    elif ev["independent_publisher_count"] >= 2:
        ev["evidence_status"] = "multi_source"
    elif clean_srcs:
        ev["evidence_status"] = "single_source"
    else:
        ev["evidence_status"] = "needs_verification"
    return ev


def _is_low_value_appendix_event(ev: dict) -> bool:
    """Detect noisy appended boilerplate (unwatched HKEX ETFs, secondary CNInfo notices)."""
    title = str(ev.get("title") or "")
    hkex_m = re.match(r"^\[HKEX\s+(\d{5})\s+", title)
    if hkex_m and hkex_m.group(1) not in _TRACKED_HKEX_CODES:
        return True
    if title.startswith("[巨潮 ") and any(k in title for k in ("翌日披露", "港股公告：中芯国际截至", "独立董事")):
        return True
    return False


def _compute_event_radar_score(ev: dict) -> int:
    """Compute unified transparent 0-100 radar score shared across events and radar.json."""
    rel_pts = 30 if ev.get("entity_ids") else 0
    upd_kind = ev.get("update_kind") or ""
    nov_pts = 25 if ev.get("is_new_in_batch") else (18 if upd_kind == "new_fact_update" else 5)
    indep = int(ev.get("independent_publisher_count") or 1)
    indep_pts = min(indep, 5) * 6
    official_pts = 20 if ev.get("evidence_status") == "official_confirmed" else 0
    depth_pts = 15 if ev.get("material_depth") in {"first_party_and_body", "body_lead_extracted", "title_and_excerpt"} else 0
    reprint_penalty = -8 if (int(ev.get("reprint_count") or 0) >= 2 and upd_kind == "continuing_coverage") else 0
    rumor_penalty = -10 if ev.get("attribution_warning") else 0
    title_only_penalty = -8 if ev.get("material_depth") == "title_only" else 0
    stale_penalty = -12 if ev.get("is_stale_rehash") else 0
    return max(0, min(100, rel_pts + nov_pts + indep_pts + official_pts + depth_pts + reprint_penalty + rumor_penalty + title_only_penalty + stale_penalty))


_S_MACRO_POLICY_RE = re.compile(
    r"(?:三大交易所|沪深北交易所|融资保证金比例|释放\s*\d+(?:,\d+)?亿|降准|降息|LPR|"
    r"美联储.{0,12}(?:利率决议|加息|降息|FOMC)|"
    r"中美元首.{0,16}(?:协议|联合声明|公报|关税)|"
    r"美伊.{0,14}(?:冲突|遇袭|霍尔木兹海峡封锁|停火)|"
    r"俄乌.{0,14}(?:停火|和平协议|大规模袭击)|"
    r"黎曼猜想.{0,10}证明|菲尔兹奖|BepiColombo|水星轨道|神舟.{0,8}发射)",
    re.I,
)
_S_MAJOR_TECH_CORP_RE = re.compile(
    r"(?:(?:发布|上线|推出|开源).{0,16}(?:GPT-?\d|Gemini\s*\d|Claude\s*\d|DeepSeek)|"
    r"IPO.{0,12}(?:首日|创纪录|935亿|813亿)|万亿.{0,8}危机|"
    r"英伟达.{0,12}(?:暴跌|换帅|出口管制|禁售)|星舰.{0,8}回收)",
    re.I,
)
_S_TECH_NOISE_GUARD_RE = re.compile(
    r"(?:招聘|回答更简短|透明度|反蒸馏|渠道价|遭证监会立案|信息披露违法违规|专利侵权|控股股东)"
)
_S_TIER_EVENT_RE = re.compile(f"(?:{_S_MACRO_POLICY_RE.pattern}|{_S_MAJOR_TECH_CORP_RE.pattern})", re.I)
_A_TIER_EVENT_RE = re.compile(
    r"(?:自贸协定|自由贸易协定|百亿美元并购|欧盟.{0,10}禁售|法院禁令|出口管制|实体清单|菲尔兹奖|梅纳德|BepiColombo|水星轨道|"
    r"神舟.{0,8}(?:发射|合练)|COP31|气候大会|气候变化大会|关税|黄金.{0,8}暴跌|比特币.{0,8}(?:跌破|突破)|并购|收购.{0,8}亿美元|"
    r"OpenAI|Anthropic|Google|DeepSeek|Qwen|英伟达|NVIDIA|特斯拉|FSD|SpaceX)",
    re.I,
)


def _event_age_hours(ev: dict, now_dt: Any) -> Tuple[float, float]:
    """Return (first_age_hours, latest_update_age_hours) against now_dt."""
    pub_iso = ev.get("first_reported_at") or ev.get("published_at") or ev.get("fetched_at")
    upd_iso = ev.get("latest_reported_at") or ev.get("latest_fact_update_at") or pub_iso
    pub_dt = parse_iso_datetime(str(pub_iso)) if pub_iso else None
    upd_dt = parse_iso_datetime(str(upd_iso)) if upd_iso else pub_dt
    age_h = max(0.0, (now_dt - pub_dt).total_seconds() / 3600.0) if pub_dt else 24.0
    upd_h = max(0.0, (now_dt - upd_dt).total_seconds() / 3600.0) if upd_dt else age_h
    return age_h, upd_h


def _s_tier_priority(title: str, ev: dict) -> int:
    """Return 2 for macro/policy/geopolitical/science S-tier, 1 for major tech/corp S-tier, 0 otherwise."""
    if _S_TECH_NOISE_GUARD_RE.search(title):
        return 0
    if _S_MACRO_POLICY_RE.search(title):
        return 2
    # Check Riemann/Fields formal verification proof in lead sentence as well
    lead_fact = str(ev.get("fact_summary") or "")[:90]
    if re.search(r"黎曼猜想.{0,10}证明", lead_fact):
        return 2
    if _S_MAJOR_TECH_CORP_RE.search(title):
        return 1
    return 0


def classify_event_severity(ev: dict, now_dt: Any = None) -> Tuple[str, str]:
    """
    Classify raw candidate severity BEFORE site-wide budget calibration:
      - Hotlist-only items, needs_verification, mashups, single-source rumors, and >24h un-updated items CANNOT be S or A.
    """
    now_ref = now_dt or now_shanghai()
    title = str(ev.get("title") or "")
    sources = ev.get("sources") or []
    if not has_authoritative_primary_source(sources):
        return "B", "社媒热榜聚合（不进 S/A 重磅）"
    if _is_unrelated_company_mashup(title):
        return "B", "多公司日常公告组合（降为常规）"
    if ev.get("evidence_status") == "needs_verification" or ev.get("is_stale_rehash"):
        return "B", "待核实或滞后旧闻"
    if ev.get("evidence_status") == "single_source" and ev.get("attribution_warning"):
        return "B", "单一非一手传闻（降为常规）"

    age_h, upd_h = _event_age_hours(ev, now_ref)
    is_fresh_24h = age_h <= 24.0 or upd_h <= 6.0
    is_recent_48h = age_h <= 48.0 or upd_h <= 12.0

    s_prio = _s_tier_priority(title, ev)
    if is_fresh_24h and s_prio > 0:
        return "S", "S级核心重磅"
    if is_recent_48h and not _S_TECH_NOISE_GUARD_RE.search(title) and (s_prio > 0 or _A_TIER_EVENT_RE.search(title)):
        return "A", "A级重要要闻"
    return "B", "B级常规要闻"


def calibrate_sitewide_severity_tiers(cat_docs: Dict[str, dict], now_dt: Any = None) -> None:
    """Enforce site-wide S <= 3, (S + A) <= max(3, int(25% * total)), and demote >24h stale is_new_in_batch flags."""
    now_ref = now_dt or now_shanghai()
    all_evs: List[dict] = []
    for doc in cat_docs.values():
        if isinstance(doc, dict):
            all_evs.extend(doc.get("events") or [])
    if not all_evs:
        return

    # 1. Mark stale market price contradictions (e.g., old 'BTC跌破6万' when newer authoritative report says '突破/重返6万')
    newer_btc_up = None
    for ev in all_evs:
        t = str(ev.get("title") or "")
        if re.search(r"(?:比特币|\bBTC\b).*(?:突破|重返|站上|涨超)\s*6万", t, re.I) and has_authoritative_primary_source(ev.get("sources") or []):
            dt = parse_iso_datetime(str(ev.get("latest_reported_at") or ev.get("published_at") or ""))
            if dt and (newer_btc_up is None or dt > newer_btc_up):
                newer_btc_up = dt
    if newer_btc_up is not None:
        for ev in all_evs:
            t = str(ev.get("title") or "")
            if re.search(r"(?:比特币|\bBTC\b).*跌破\s*6万", t, re.I):
                dt = parse_iso_datetime(str(ev.get("latest_reported_at") or ev.get("published_at") or ""))
                if dt is None or dt < newer_btc_up:
                    ev["is_stale_rehash"] = True

    s_candidates: List[Tuple[tuple, dict]] = []
    a_candidates: List[Tuple[tuple, dict]] = []
    for ev in all_evs:
        age_h, upd_h = _event_age_hours(ev, now_ref)
        if age_h > 24.0 and upd_h > 6.0:
            ev["is_new_in_batch"] = False

        cand_tier, _ = classify_event_severity(ev, now_ref)
        indep = int(ev.get("independent_publisher_count") or 1)
        is_off = 1 if ev.get("evidence_status") == "official_confirmed" else 0
        radar = int(ev.get("radar_score") or 0)
        s_prio = _s_tier_priority(str(ev.get("title") or ""), ev) if cand_tier == "S" else 0
        key_tuple = (
            s_prio,
            1 if ev.get("is_new_in_batch") else 0,
            is_off,
            min(indep, 6),
            radar,
            -age_h,
        )
        if cand_tier == "S":
            s_candidates.append((key_tuple, ev))
        elif cand_tier == "A":
            a_candidates.append((key_tuple, ev))
        else:
            ev["severity_tier"] = "B"
            ev["severity_label"] = "B级常规"
            ev["importance"] = "medium" if (has_authoritative_primary_source(ev.get("sources") or []) and radar >= 55) else "normal"

    s_candidates.sort(key=lambda x: x[0], reverse=True)
    total_events = len(all_evs)
    max_sa_budget = max(3, int(total_events * 0.25))

    s_count = 0
    demoted_to_a: List[Tuple[tuple, dict]] = []
    for key_t, ev in s_candidates:
        if s_count < 3 and s_count < max_sa_budget:
            ev["severity_tier"] = "S"
            ev["severity_label"] = "S级重磅"
            ev["importance"] = "high"
            s_count += 1
        else:
            demoted_to_a.append((key_t, ev))

    remaining_a = max(0, max_sa_budget - s_count)
    merged_a = [(key_t, ev) for key_t, ev in demoted_to_a] + a_candidates
    merged_a.sort(key=lambda x: x[0], reverse=True)

    a_count = 0
    for _, ev in merged_a:
        if a_count < remaining_a:
            ev["severity_tier"] = "A"
            ev["severity_label"] = "A级要闻"
            ev["importance"] = "high"
            a_count += 1
        else:
            radar = int(ev.get("radar_score") or 0)
            ev["severity_tier"] = "B"
            ev["severity_label"] = "B级常规"
            ev["importance"] = "medium" if radar >= 50 else "normal"


def _postprocess_and_prune_cross_category(
    cat_docs: Dict[str, dict],
    cat_manifest: Dict[str, dict],
    max_per_category: int = 10,
) -> None:
    """
    Remove omnibus roundups, consumer promos/fluff, hotlist-only market price recaps,
    fix cross-entity source pollution, dedupe cross-category stories, enforce S/A/B caps,
    and keep high-signal category compactness.
    """
    _reclassify_region_topic_events(cat_docs)
    for cat, doc in cat_docs.items():
        raw_evs = [_clean_single_event_sources_and_dates(ev) for ev in doc.get("events", [])]
        filtered = []
        for ev in raw_evs:
            title_s = str(ev.get("title") or "")
            sum_s = str(ev.get("fact_summary") or "")
            srcs = ev.get("sources") or []
            if is_omnibus_digest_title(title_s) or _is_low_value_appendix_event(ev):
                continue
            if is_consumer_promo_or_fluff(title_s, sum_s):
                continue
            if _MARKET_PRICE_RE.search(title_s) and not has_authoritative_primary_source(srcs):
                continue
            filtered.append(ev)
        if len(raw_evs) >= 6 and len(filtered) < 5:
            for ev in raw_evs:
                title_s = str(ev.get("title") or "")
                sum_s = str(ev.get("fact_summary") or "")
                if (
                    ev not in filtered
                    and not is_omnibus_digest_title(title_s)
                    and not is_consumer_promo_or_fluff(title_s, sum_s)
                    and not (_MARKET_PRICE_RE.search(title_s) and not has_authoritative_primary_source(ev.get("sources") or []))
                ):
                    filtered.append(ev)
                    if len(filtered) >= 6:
                        break
        deduped_local: List[dict] = []
        seen_repo_family: Set[str] = set()
        for ev in filtered:
            t = str(ev.get("title") or "")
            fam_key = None
            if t.startswith("[GitHub Release] "):
                fam_key = "gh:" + t.replace("[GitHub Release] ", "").split(" 发布 ", 1)[0].strip().lower()
            elif t.startswith("[HF 模型卡] "):
                model_part = t.replace("[HF 模型卡] ", "").split(" 更新", 1)[0].strip().lower()
                fam_key = "hf:" + model_part.split("/", 1)[0]
            if fam_key:
                if fam_key in seen_repo_family:
                    continue
                seen_repo_family.add(fam_key)
            deduped_local.append(ev)
        doc["events"] = deduped_local

    def _quality_score(ev: dict, cat_name: str) -> tuple:
        tier_rank = {"official_confirmed": 3, "multi_source": 2, "single_source": 1, "needs_verification": 0}
        cat_priority = {"finance": 3, "tech": 2, "global": 2, "general": 0}.get(cat_name, 0)
        has_auth = 1 if has_authoritative_primary_source(ev.get("sources") or []) else 0
        news_src_cnt = sum(
            1
            for s in ev.get("sources") or []
            if s.get("source_kind") not in {"discussion", "social"}
            and not is_hotlist_aggregator_source(str(s.get("source_id") or ""), str(s.get("source_name") or ""))
        )
        return (
            has_auth,
            tier_rank.get(ev.get("evidence_status", "needs_verification"), 0),
            cat_priority,
            1 if news_src_cnt > 0 else 0,
            int(ev.get("independent_publisher_count") or ev.get("source_count") or 0),
            1 if ev.get("published_at") else 0,
        )

    kept_global: List[Tuple[str, dict]] = []
    for cat in CATEGORIES:
        doc = cat_docs.get(cat)
        if not doc:
            continue
        for ev in doc.get("events", []):
            kept_global.append((cat, ev))

    drop_ids: Set[Tuple[str, str]] = set()
    for i in range(len(kept_global)):
        c1, e1 = kept_global[i]
        if (c1, e1["event_id"]) in drop_ids:
            continue
        for j in range(i + 1, len(kept_global)):
            c2, e2 = kept_global[j]
            if (c2, e2["event_id"]) in drop_ids:
                continue
            if _same_cross_category_story(e1, e2):
                s1 = _quality_score(e1, c1) + ((2,) if c1 == "global" and any(k in e1.get("title", "") for k in ("元首", "会晤", "外长", "APEC", "和平协议", "美伊")) else (0,))
                s2 = _quality_score(e2, c2) + ((2,) if c2 == "global" and any(k in e2.get("title", "") for k in ("元首", "会晤", "外长", "APEC", "和平协议", "美伊")) else (0,))
                if s1 >= s2:
                    drop_ids.add((c2, e2["event_id"]))
                else:
                    drop_ids.add((c1, e1["event_id"]))
                    break

    for cat, doc in cat_docs.items():
        evs = doc.get("events", [])
        pruned = [ev for ev in evs if (cat, ev["event_id"]) not in drop_ids]
        doc["events"] = pruned[:max_per_category]
        for ev in doc["events"]:
            if ev.get("fact_summary"):
                ev["fact_summary"] = _PIPELINE_JARGON_RE.sub("", str(ev["fact_summary"])).strip()
            if ev.get("ai_analysis"):
                ev["ai_analysis"] = _PIPELINE_JARGON_RE.sub("", str(ev["ai_analysis"])).strip() or None
            ev["radar_score"] = _compute_event_radar_score(ev)

    calibrate_sitewide_severity_tiers(cat_docs, now_dt=now_shanghai())

    for cat, doc in cat_docs.items():
        doc["key_changes"] = _sync_key_changes_attribution(doc.get("key_changes") or [], doc["events"])
        if not doc["key_changes"]:
            doc["key_changes"] = _build_key_changes_from_events(doc["events"])
        else:
            valid_ids = {e["event_id"] for e in doc["events"]}
            doc["key_changes"] = [kc for kc in doc["key_changes"] if not kc.get("event_id") or kc["event_id"] in valid_ids] or _build_key_changes_from_events(doc["events"])

        if cat in cat_manifest:
            v_cnt = sum(1 for e in doc["events"] if e["evidence_status"] != "needs_verification")
            cat_manifest[cat]["item_count"] = len(doc["events"])
            cat_manifest[cat]["verified_count"] = v_cnt
            cat_manifest[cat]["needs_verification_count"] = len(doc["events"]) - v_cnt


def build_briefing_batch(
    base_dir: Path | str = ".",
    *,
    mode: str = "ai",
    raw_path: Optional[str] = None,
    smart_path: Optional[str] = None,
    include_comments: bool = True,
) -> Dict[str, Any]:
    """Build, reconcile, or V3-ground-update a complete smart briefing and switch manifest atomically."""
    root = Path(base_dir)
    manifest = load_manifest(root)
    input_batch_id, input_cutoff_at, used_raw_rel, raw_by_cat, connectors_payload = _load_raw_batch(root, raw_path)
    sec_entity_status = connectors_payload.get("entity_updates") if isinstance(connectors_payload, dict) else {}

    if mode == "reconcile":
        if not smart_path:
            raise ValueError("--smart-path is required for --mode reconcile")
        target_smart_rel = Path(smart_path).as_posix().rstrip("/") + "/"
        abs_smart_dir = root / target_smart_rel
        parts = target_smart_rel.strip("/").split("/")
        date_str, time_str = parts[-2], parts[-1]
        batch_dt = parse_iso_datetime(f"{date_str}T{time_str.replace('-', ':')}:00+08:00") or now_shanghai()
        batch_id = format_batch_id("smart", batch_dt)
        generated_at_iso = to_iso_shanghai(batch_dt)
    else:
        batch_dt = now_shanghai()
        date_str = batch_dt.strftime("%Y-%m-%d")
        time_str = batch_dt.strftime("%H-%M")
        target_smart_rel = f"archives/smart/{date_str}/{time_str}/"
        abs_smart_dir = root / target_smart_rel
        batch_id = format_batch_id("smart", batch_dt)
        generated_at_iso = to_iso_shanghai(batch_dt)

    # Load previous smart batch for followup & per-category fallback
    prev_smart_info = manifest.get("smart", {}) if isinstance(manifest, dict) else {}
    prev_smart_cats = prev_smart_info.get("categories", {}) if isinstance(prev_smart_info, dict) else {}
    prev_batch_id = prev_smart_info.get("latest_batch_id")
    if prev_batch_id == batch_id:
        prev_batch_id = None

    cat_docs: Dict[str, dict] = {}
    comment_docs: Dict[str, dict] = {}
    cat_manifest: Dict[str, dict] = {}
    prev_cat_events: Dict[str, List[dict]] = {}
    selection_audits: Dict[str, Any] = {}
    success_cats = 0
    failed_cats = 0

    def _process_category(cat: str) -> Tuple[str, Optional[dict], Optional[dict], Optional[dict], Optional[Exception], dict]:
        cat_t0 = time.monotonic()
        print(f"⏳ [{cat}] starting mode={mode}...", flush=True)
        prev_cat_meta = prev_smart_cats.get(cat, {}) if isinstance(prev_smart_cats, dict) else {}
        prev_events: List[dict] = []
        if prev_cat_meta.get("path"):
            prev_doc = load_json_if_exists(root / prev_cat_meta["path"], default={})
            if isinstance(prev_doc, dict):
                prev_events = prev_doc.get("events") or prev_doc.get("items") or []
        prev_cat_events[cat] = prev_events

        try:
            if mode == "reconcile":
                doc = _reconcile_v1_category(
                    root,
                    cat,
                    abs_smart_dir,
                    raw_by_cat,
                    input_batch_id,
                    input_cutoff_at,
                    generated_at_iso,
                    batch_id,
                    prev_events,
                    prev_batch_id,
                    sec_entity_status=sec_entity_status,
                )
                ok, errs = validate_published_briefing(doc)
                if not ok:
                    raise RuntimeError(f"Validation failed: {errs}")
                cdoc = {
                    "schema_version": "3.0",
                    "batch_id": batch_id,
                    "input_batch_id": input_batch_id,
                    "generated_at": None,
                    "category": cat,
                    "is_ai_simulated": True,
                    "status": "not_generated",
                    "disclaimer": "该历史批次未同批生成 AI 模拟观点；为保证批次一致性，不拼接其他时段评论。",
                    "comments": [],
                }
                return cat, doc, cdoc, None, None, prev_cat_meta
            if mode == "ground_update":
                doc, cdoc, sel_audit = _ground_update_category(
                    root,
                    cat,
                    prev_cat_meta if isinstance(prev_cat_meta, dict) else {},
                    raw_by_cat,
                    input_batch_id,
                    input_cutoff_at,
                    generated_at_iso,
                    batch_id,
                    prev_events,
                    prev_batch_id,
                    sec_entity_status=sec_entity_status,
                )
                ok, errs = validate_published_briefing(doc)
                if not ok:
                    raise RuntimeError(f"Validation failed: {errs}")
                return cat, doc, cdoc, sel_audit, None, prev_cat_meta

            api_keys = _collect_api_keys(cat)
            if not api_keys:
                raise RuntimeError(f"Missing Gemini API key for category {cat}")
            doc, sel_audit = _generate_ai_category(
                cat,
                raw_by_cat,
                input_batch_id,
                input_cutoff_at,
                batch_id,
                prev_events,
                prev_batch_id,
                api_keys,
                sec_entity_status=sec_entity_status,
                base_dir=root,
            )
            ok, errs = validate_published_briefing(doc)
            if not ok:
                raise RuntimeError(f"Validation failed: {errs}")

            if include_comments:
                try:
                    cdoc = _generate_comments_for_category(cat, doc, api_keys, base_dir=root)
                except Exception as c_exc:
                    print(f"⚠️ Simulated perspectives skipped for {cat}: {c_exc}")
                    cdoc = {
                        "schema_version": "3.0",
                        "batch_id": batch_id,
                        "input_batch_id": input_batch_id,
                        "generated_at": None,
                        "category": cat,
                        "is_ai_simulated": True,
                        "status": "generation_failed",
                        "disclaimer": "本批次 AI 模拟观点生成失败（不影响新闻简报正文）。",
                        "comments": [],
                    }
            else:
                cdoc = {
                    "schema_version": "3.0",
                    "batch_id": batch_id,
                    "input_batch_id": input_batch_id,
                    "generated_at": None,
                    "category": cat,
                    "is_ai_simulated": True,
                    "status": "disabled",
                    "disclaimer": "本批次未启用 AI 模拟观点。",
                    "comments": [],
                }
            print(
                f"✅ [{cat}] finished in {time.monotonic() - cat_t0:.1f}s (model={doc.get('model_name')}, events={len(doc.get('events') or [])})",
                flush=True,
            )
            return cat, doc, cdoc, sel_audit, None, prev_cat_meta
        except Exception as exc:
            print(f"⚠️ [{cat}] errored in {time.monotonic() - cat_t0:.1f}s: {exc}", flush=True)
            return cat, None, None, None, exc, prev_cat_meta

    # Run 2 categories concurrently with slight stagger to avoid 4x simultaneous Gemini burst 503s
    def _process_staggered(cat_idx_and_name: Tuple[int, str]) -> Tuple[str, Optional[dict], Optional[dict], Optional[dict], Optional[Exception], dict]:
        idx, cat = cat_idx_and_name
        if mode == "ai" and idx > 0:
            time.sleep(min(idx * 1.0, 2.0))
        return _process_category(cat)

    if mode == "ai":
        results_map: Dict[str, tuple] = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [pool.submit(_process_staggered, (idx, cat)) for idx, cat in enumerate(CATEGORIES)]
            for fut in as_completed(futs):
                res_tuple = fut.result()
                results_map[res_tuple[0]] = res_tuple
        ordered_results = [results_map[cat] for cat in CATEGORIES]
    else:
        ordered_results = [_process_category(cat) for cat in CATEGORIES]

    fallback_v3_docs: Dict[str, dict] = {}
    for cat, doc, cdoc, sel_audit, err, prev_cat_meta in ordered_results:
        if err is None and doc is not None and cdoc is not None:
            cat_docs[cat] = doc
            comment_docs[cat] = cdoc
            if sel_audit is not None:
                selection_audits[cat] = sel_audit
            success_cats += 1
            verified_cnt = sum(1 for e in doc["events"] if e["evidence_status"] != "needs_verification")
            needs_cnt = len(doc["events"]) - verified_cnt
            cat_manifest[cat] = {
                "batch_id": batch_id,
                "path": f"{target_smart_rel}analysis_{cat}.json",
                "comments_path": f"{target_smart_rel}comments_{cat}.json",
                "input_batch_id": input_batch_id,
                "input_cutoff_at": input_cutoff_at,
                "generated_at": doc["generated_at"],
                "status": "ok",
                "is_fallback": False,
                "fallback_reason": None,
                "item_count": len(doc["events"]),
                "verified_count": verified_cnt,
                "needs_verification_count": needs_cnt,
                "has_comments": bool(cdoc.get("comments")),
            }
        else:
            failed_cats += 1
            print(f"❌ Category {cat} failed: {err}")
            if prev_cat_meta.get("path"):
                fallback_meta = dict(prev_cat_meta)
                fallback_meta["is_fallback"] = True
                fallback_meta["status"] = "fallback"
                fallback_meta["fallback_reason"] = f"本轮生成失败（{err}），已保留该分类上次成功批次数据"
                cat_manifest[cat] = fallback_meta
                loaded_prev = load_json_if_exists(root / prev_cat_meta["path"], default={})
                if isinstance(loaded_prev, dict) and loaded_prev.get("events"):
                    fallback_v3_docs[cat] = loaded_prev
            else:
                try:
                    g_doc, _ = _ground_update_category(
                        cat,
                        raw_by_cat,
                        input_batch_id,
                        input_cutoff_at,
                        batch_id,
                        [],
                        prev_batch_id,
                        sec_entity_status=sec_entity_status,
                    )
                    fallback_v3_docs[cat] = g_doc
                except Exception:
                    pass
                cat_manifest[cat] = {
                    "batch_id": None,
                    "path": None,
                    "comments_path": None,
                    "input_batch_id": input_batch_id,
                    "input_cutoff_at": input_cutoff_at,
                    "generated_at": None,
                    "status": "failed",
                    "is_fallback": False,
                    "fallback_reason": str(err),
                    "item_count": 0,
                    "verified_count": 0,
                    "needs_verification_count": 0,
                    "has_comments": False,
                }

    if success_cats == 0:
        raise RuntimeError("All categories failed; aborting atomic publish so latest manifest remains intact.")

    all_v3_docs = dict(fallback_v3_docs)
    all_v3_docs.update(cat_docs)
    _postprocess_and_prune_cross_category(all_v3_docs, cat_manifest, max_per_category=12)

    from .bilingual import enrich_bilingual_events

    bi_t0 = time.monotonic()
    print(f"🌐 Starting enrich_bilingual_events across {len(cat_docs)} categories...", flush=True)
    for doc in cat_docs.values():
        ev_list = doc.get("events") or []
        enrich_bilingual_events(ev_list)
        ev_by_id = {e.get("event_id"): e for e in ev_list if e.get("event_id")}
        for kc in doc.get("key_changes") or []:
            matched_ev = ev_by_id.get(kc.get("event_id"))
            if matched_ev:
                kc["headline"] = matched_ev.get("title") or kc.get("headline")
                kc["detail"] = _smart_truncate(matched_ev.get("fact_summary") or kc.get("detail") or "", 190)
    print(f"🌐 Finished enrich_bilingual_events in {time.monotonic() - bi_t0:.1f}s", flush=True)

    published_iso = to_iso_shanghai(now_shanghai())
    batch_status = "complete" if failed_cats == 0 else "partial"
    has_any_comments = any(bool(c.get("comments")) for c in comment_docs.values())

    quota_summary = get_quota_summary(root)
    quality_flags: List[str] = []
    if failed_cats > 0:
        quality_flags.append("partial_category_fallback")
    if mode != "ai":
        quality_flags.append(f"mode_{mode}")
    if quota_summary.get("total_configured_keys", 0) > 0 and quota_summary.get("healthy_keys", 0) == 0:
        quality_flags.append("gemini_quota_exhausted")

    batch_meta = {
        "schema_version": "4.1",
        "batch_id": batch_id,
        "input_batch_id": input_batch_id,
        "input_raw_path": used_raw_rel,
        "input_cutoff_at": input_cutoff_at,
        "generated_at": generated_at_iso,
        "published_at": published_iso,
        "status": batch_status,
        "mode": mode,
        "generation_mode": f"mode_{mode}",
        "quality_flags": quality_flags,
        "model_name": (
            next((c.get("model_name") for c in cat_docs.values() if c.get("model_name")), None)
            or (_LAST_USED_MODEL if mode == "ai" else "deterministic-v3-grounding")
        ),
        "has_comments": has_any_comments,
        "gemini_quota": quota_summary,
        "categories": cat_manifest,
    }

    # 1. Write complete immutable smart batch archive (including calibrated fallback root docs so zero uncalibrated events leak)
    abs_smart_dir.mkdir(parents=True, exist_ok=True)
    for cat, doc in all_v3_docs.items():
        if cat in cat_docs:
            doc["published_at"] = published_iso
            atomic_write_json(abs_smart_dir / f"analysis_{cat}.json", doc)
        atomic_write_json(root / f"analysis_{cat}.json", doc)
    for cat, cdoc in comment_docs.items():
        atomic_write_json(abs_smart_dir / f"comments_{cat}.json", cdoc)
        atomic_write_json(root / f"comments_{cat}.json", cdoc)
    atomic_write_json(abs_smart_dir / "batch_meta.json", batch_meta)
    if selection_audits:
        atomic_write_json(abs_smart_dir / "selection_audit.json", selection_audits)

    # 2. Build V3 research intelligence memory using complete 4-category view (including fallback docs if any category failed)
    v3_cat_docs = all_v3_docs
    v3_t0 = time.monotonic()
    print("🧠 Building V3 research memory artifacts...", flush=True)
    v3_summary = build_v3_artifacts(
        root,
        batch_id=batch_id,
        generated_at_iso=generated_at_iso,
        cat_docs=v3_cat_docs,
        prev_cat_events=prev_cat_events,
        prev_batch_id=prev_batch_id,
        connectors_payload=connectors_payload,
        raw_items_by_cat=raw_by_cat,
    )
    print(f"🧠 Finished build_v3_artifacts in {time.monotonic() - v3_t0:.1f}s", flush=True)

    # 3. Update smart history index ONLY after batch succeeded & bound archive growth
    index_entry = {
        "display": batch_dt.strftime("%Y-%m-%d %H:%M"),
        "path": target_smart_rel,
        "batch_id": batch_id,
        "input_batch_id": input_batch_id,
        "input_cutoff_at": input_cutoff_at,
        "generated_at": generated_at_iso,
        "published_at": published_iso,
        "status": batch_status,
        "has_comments": has_any_comments,
        "categories": list(cat_docs.keys()),
    }
    upsert_history_index(root / "history/smart_index.json", index_entry, max_entries=96)
    prune_old_archives(root, "history/smart_index.json", keep_latest=12)

    # 4. Atomically switch manifest.json smart + v3 pointers
    smart_degraded = bool(failed_cats > 0 or mode != "ai" or (quota_summary.get("total_configured_keys", 0) > 0 and quota_summary.get("healthy_keys", 0) == 0))
    alerts: List[Dict[str, Any]] = []
    if failed_cats > 0:
        alerts.append({"code": "partial_category_fallback", "severity": "warning", "message": f"本批次有 {failed_cats} 个板块使用上一批降级回退"})
    if quota_summary.get("total_configured_keys", 0) > 0 and quota_summary.get("healthy_keys", 0) == 0:
        alerts.append({"code": "gemini_quota_exhausted", "severity": "critical", "message": "全部 Gemini API Key 处于冷却或耗尽状态"})
    elif quota_summary.get("total_configured_keys", 0) > 0 and quota_summary.get("healthy_keys", 0) <= 2:
        alerts.append({"code": "gemini_quota_low", "severity": "warning", "message": f"可用 Gemini Key 仅剩 {quota_summary.get('healthy_keys')} 个"})

    manifest["schema_version"] = "4.1"
    manifest["site_published_at"] = published_iso
    manifest["gemini_quota"] = quota_summary
    manifest["quota"] = quota_summary
    manifest["degraded"] = smart_degraded or bool((manifest.get("raw") or {}).get("status") not in {None, "complete", "ok"})
    manifest["alerts"] = alerts
    manifest["scheduler"] = {
        "provider": "github_actions",
        "raw_cron": "7 */1 * * *",
        "smart_cron": "22 */3 * * *",
        "note": "轻量化错峰调度（Raw 每小时 / Smart 每3小时）；腾讯云仅静默拉取与静态直出。",
    }
    manifest["smart"] = {
        "latest_batch_id": batch_id,
        "latest_path": target_smart_rel,
        "meta_path": f"{target_smart_rel}batch_meta.json",
        "input_batch_id": input_batch_id,
        "input_raw_path": used_raw_rel,
        "input_cutoff_at": input_cutoff_at,
        "generated_at": generated_at_iso,
        "published_at": published_iso,
        "target_cadence_hours": 3,
        "status": batch_status,
        "generation_mode": batch_meta["generation_mode"],
        "quality_flags": quality_flags,
        "model_name": batch_meta["model_name"],
        "configured_primary_model": PRIMARY_MODEL,
        "has_comments": has_any_comments,
        "categories": cat_manifest,
    }
    manifest["v3"] = {
        "schema_version": "4.0",
        "generated_at": published_iso,
        "batch_id": batch_id,
        "entities_path": "data/entities_index.json",
        "storylines_path": "data/storylines_index.json",
        "topics_path": "data/topics.json",
        "live_wire_path": "data/live_wire.json",
        "ai_progress_path": "data/ai_progress.json",
        "finance_impact_path": "data/finance_impact.json",
        "calendar_path": "data/calendar.json",
        "tech_tools_path": "data/tech_tools.json",
        "radar_path": "data/radar.json",
        "predictions_path": "data/predictions_public.json",
        "connectors_path": "data/connectors_latest.json",
        **v3_summary,
    }
    save_manifest(manifest, root)
    print(f"[{published_iso}] Smart V3 batch {batch_id} published ({batch_status}, ok={success_cats}, failed={failed_cats}, storylines={v3_summary.get('storylines_count')})")
    return batch_meta


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Build, reconcile, or ground-update V3 AI briefing batch")
    parser.add_argument("--base-dir", default=".", help="Repository root")
    parser.add_argument("--mode", choices=["ai", "reconcile", "ground_update"], default="ai")
    parser.add_argument("--raw-path", default=None, help="Explicit raw archive directory relative to base-dir")
    parser.add_argument("--smart-path", default=None, help="Existing V1 smart archive dir (for reconcile mode)")
    parser.add_argument("--no-comments", action="store_true", help="Skip generating AI simulated perspectives")
    args = parser.parse_args(argv)
    build_briefing_batch(
        args.base_dir,
        mode=args.mode,
        raw_path=args.raw_path,
        smart_path=args.smart_path,
        include_comments=not args.no_comments,
    )


if __name__ == "__main__":
    main()
