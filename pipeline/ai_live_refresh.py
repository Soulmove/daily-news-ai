"""Real-time first-hand AI radar collector & incremental merger for InfoFocus."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests

from pipeline.ai_radar_builder import (
    AI_KW_RE,
    AI_NOISE_RE,
    AI_RELEASE_RE,
    _BOILERPLATE_WHAT_RE,
    _LAB_CATALOG,
    _infer_company,
    _infer_what_it_does_zh,
    classify_ai_milestone_dim,
    detect_is_open_source,
    is_first_hand_ai_source,
    is_foreign_subject_blocked,
    is_similar_ai_release,
    normalize_ai_timestamp,
)
from pipeline.build_briefing import _smart_truncate
from pipeline.connectors.base import HttpCacheStore
from pipeline.dedup import is_omnibus_digest_title, strip_raw_urls_and_domain_tails
from pipeline.connectors.direct_rss import DIRECT_RSS_FEEDS, fetch_direct_rss_media
from pipeline.connectors.github_releases import fetch_github_releases
from pipeline.connectors.huggingface_hub import fetch_huggingface_models
from pipeline.manifest import atomic_write_json
from pipeline.time_utils import now_shanghai, parse_published_at, to_iso_shanghai


FIRST_HAND_RSS_IDS = {
    "rss-google-ai-blog",
    "rss-deepmind-blog",
    "rss-openai-news",
    "rss-hf-blog",
    "rss-nvidia-blog",
    "rss-github-changelog",
}

_ZH_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_FUNDING_RE = re.compile(r"(?:融资|估值|领投|IPO|千亿|百亿|funding|valuation|series\s+[a-d])", re.I)


def _has_zh(text: str) -> bool:
    return bool(_ZH_CHAR_RE.search(str(text or "")))


def _norm_url_key(url: Any) -> str:
    raw = str(url or "").strip().lower()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        host = parsed.netloc.removeprefix("www.")
        path = parsed.path.rstrip("/")
        return f"{host}{path}"
    except Exception:
        return raw


def _norm_title_key(title: Any) -> str:
    cleaned = re.sub(r"^【[^】]{1,24}】\s*", "", str(title or "").strip())
    cleaned = re.sub(r"[\s\-_·:：,，.。!！?？()（）\[\]【】'\"“”‘’/]+", "", cleaned).lower()
    return cleaned[:48]


def _sort_key_iso_desc(date_str: Any) -> Tuple[str, int, str]:
    """Group by YYYY-MM-DD day bucket first so date-only items stay on their actual day rather than sinking below older timestamps."""
    raw = str(date_str or "").strip()
    if not raw:
        return ("", 0, "")
    day = raw[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return (day, 0, raw + "T00:00:00+08:00")
    return (day, 1, raw)


def _summarize_release(title: str, excerpt: str, source_name: str, *, is_open_source: bool, is_first_hand: bool) -> Tuple[str, str]:
    del source_name, is_open_source, is_first_hand
    clean_excerpt = strip_raw_urls_and_domain_tails(re.sub(r"\s+", " ", str(excerpt or "").strip()))
    zh = _infer_what_it_does_zh(title, clean_excerpt, is_tool_release=False)
    en = _smart_truncate(clean_excerpt, 180) if clean_excerpt and clean_excerpt != title else ""
    return zh, en


def extract_ai_release_item(raw_it: Dict[str, Any], generated_at_iso: str) -> Optional[Dict[str, Any]]:
    """Convert a raw news/connector/wire item into an AiProgressItem if relevant."""
    title = strip_raw_urls_and_domain_tails(str(raw_it.get("title") or "").strip())
    if len(title) < 4 or is_omnibus_digest_title(title) or AI_NOISE_RE.search(title) or is_foreign_subject_blocked(title):
        return None

    excerpt = strip_raw_urls_and_domain_tails(str(raw_it.get("excerpt") or raw_it.get("summary") or "").strip())
    if excerpt and (AI_NOISE_RE.search(excerpt) or is_foreign_subject_blocked(title, excerpt)):
        return None

    source_id = str(raw_it.get("source_id") or "").strip()
    source_name = str(raw_it.get("publisher_name") or raw_it.get("source_name") or source_id or "AI Radar").strip()
    url = str(raw_it.get("canonical_url") or raw_it.get("url") or raw_it.get("source_url") or "").strip()
    is_first_hand = bool(raw_it.get("is_first_hand")) or is_first_hand_ai_source(source_id, source_name, url)

    combined = f"{title} {excerpt[:220]}"
    if not is_first_hand:
        if not (AI_KW_RE.search(title) and AI_RELEASE_RE.search(combined)):
            return None
    else:
        if source_id in {"rss-github-changelog", "rss-nvidia-blog"}:
            if not re.search(r"(?:copilot|\bai\b|model|llm|agent|cuda|tensor|blackwell|rubin|nemotron|nim|inference|大模型|模型)", title, re.I):
                return None
        elif source_id not in {"huggingface-hub", "hf-daily-papers", "github-releases"} and not AI_KW_RE.search(combined):
            if not any(k in source_id.lower() for k in ("openai", "deepmind", "google-ai", "hf-blog")):
                return None

    comp_id, comp_name, region = _infer_company(title, url, source_name)
    pub_date = normalize_ai_timestamp(
        raw_it.get("published_at") or raw_it.get("date") or raw_it.get("fetched_at") or generated_at_iso,
        generated_at_iso,
    )
    is_open_source = detect_is_open_source(title, excerpt, url=url, company_id=comp_id, source_id=source_id)

    if _FUNDING_RE.search(title):
        category, category_en = "资本与商业", "Funding & Strategy"
    elif is_open_source:
        category, category_en = "开源突破", "Open Source"
    elif is_first_hand:
        category, category_en = "官方一手发布", "First-Hand Official"
    else:
        category, category_en = "模型与产品", "Model & Product"

    dim_id, dim_zh, dim_en = classify_ai_milestone_dim(title, excerpt, is_open_source=is_open_source, category=category)

    what_zh, what_en = _summarize_release(
        title,
        excerpt,
        source_name,
        is_open_source=is_open_source,
        is_first_hand=is_first_hand,
    )
    from pipeline.bilingual import _translate_zh_to_en_glossary, is_mostly_english

    raw_id = str(raw_it.get("item_id") or raw_it.get("id") or _norm_title_key(title))
    item_id = raw_id if raw_id.startswith("ai_") else f"ai_live_{raw_id}"
    title_en_raw = str(raw_it.get("title_en") or "").strip()
    title_en = title_en_raw if (title_en_raw and is_mostly_english(title_en_raw)) else _translate_zh_to_en_glossary(title, [comp_name])
    what_en_clean = (
        what_en
        if (what_en and is_mostly_english(str(what_en)))
        else (_translate_zh_to_en_glossary(str(what_zh), [comp_name]) if what_zh else "")
    )

    return {
        "id": item_id,
        "date": pub_date,
        "company_id": comp_id,
        "company_name": comp_name,
        "region": region,
        "category": category,
        "category_en": category_en,
        "title": title,
        "title_en": title_en,
        "what_it_does": what_zh,
        "what_it_does_en": what_en_clean,
        "who_cares": "",
        "limitations": "",
        "limitations_en": "",
        "source_name": source_name,
        "source_url": url or None,
        "event_id": raw_it.get("event_id"),
        "is_open_source": is_open_source,
        "is_first_hand": is_first_hand,
        "source_tier": "first_party" if is_first_hand else "realtime_wire",
        "milestone_dim": dim_id,
        "milestone_dim_label": dim_zh,
        "milestone_dim_label_en": dim_en,
        "related_sources": ([{"source_name": source_name, "url": url, "is_first_hand": is_first_hand}] if source_name else []),
    }


def _fetch_hf_daily_papers(fetched_iso: str) -> List[dict]:
    items: List[dict] = []
    try:
        resp = requests.get(
            "https://huggingface.co/api/daily_papers?limit=10",
            headers={"User-Agent": "InfoFocusBot/3.0"},
            timeout=(3, 5),
        )
        if resp.status_code != 200:
            return []
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        ranked = sorted(
            [r for r in rows if isinstance(r, dict)],
            key=lambda r: int(((r.get("paper") or {}).get("upvotes") or 0)),
            reverse=True,
        )
        for row in ranked:
            paper = row.get("paper") or {}
            pid = str(paper.get("id") or "").strip()
            ptitle = str(row.get("title") or paper.get("title") or "").strip()
            if not pid or not ptitle:
                continue
            upvotes = int(paper.get("upvotes") or 0)
            if upvotes < 12:
                continue
            pub_raw = row.get("publishedAt") or paper.get("publishedAt") or fetched_iso
            pub_iso, _ = parse_published_at(pub_raw, "hf-daily-papers")
            summary = re.sub(r"\s+", " ", str(paper.get("summary") or row.get("summary") or "").strip())[:240]
            items.append(
                {
                    "item_id": f"hf_paper_{pid}",
                    "source_id": "hf-daily-papers",
                    "source_name": f"Hugging Face Daily Papers (▲{upvotes})",
                    "title": f"[HF Paper] {ptitle}",
                    "url": f"https://huggingface.co/papers/{pid}",
                    "canonical_url": f"https://huggingface.co/papers/{pid}",
                    "published_at": pub_iso or fetched_iso,
                    "fetched_at": fetched_iso,
                    "excerpt": summary,
                    "is_open_source": True,
                    "is_first_hand": True,
                }
            )
            if len(items) >= 4:
                break
    except Exception:
        return []
    return items


def fetch_first_hand_ai_drops(cache_dir: Optional[Path] = None) -> List[dict]:
    """Fetch official AI lab RSS, Hugging Face Hub + Daily Papers, and GitHub Releases quickly."""
    fetched_iso = to_iso_shanghai(now_shanghai())
    cache = HttpCacheStore(cache_dir) if cache_dir is not None else None
    official_feeds = [f for f in DIRECT_RSS_FEEDS if f.get("id") in FIRST_HAND_RSS_IDS]

    collected: List[dict] = []

    def _run_hf() -> List[dict]:
        res = fetch_huggingface_models(cache=cache)
        return list(res.get("items") or [])

    def _run_gh() -> List[dict]:
        res = fetch_github_releases(cache=cache)
        return list(res.get("items") or [])

    def _run_rss() -> List[dict]:
        if not official_feeds:
            return []
        res = fetch_direct_rss_media(feeds=official_feeds)
        return list(res.get("items") or [])

    tasks = [
        _run_hf,
        lambda: _fetch_hf_daily_papers(fetched_iso),
        _run_gh,
        _run_rss,
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(fn) for fn in tasks]
        for fut in as_completed(futs):
            try:
                collected.extend(fut.result() or [])
            except Exception:
                continue

    return collected


def _empty_doc(generated_at_iso: str) -> Dict[str, Any]:
    companies = []
    for spec in _LAB_CATALOG:
        companies.append(
            {
                "company_id": spec["company_id"],
                "company_name": spec["company_name"],
                "company_name_en": spec.get("company_name_en") or spec["company_name"],
                "region": spec["region"],
                "region_en": spec.get("region_en") or spec["region"],
                "flagship_model": spec["flagship_model"],
                "open_source_line": spec["open_source_line"],
                "access_limits": spec["access_limits"],
                "access_limits_en": spec.get("access_limits_en") or spec["access_limits"],
                "recent_count": 0,
                "latest_date": "",
                "latest_headline": "",
                "items": [],
            }
        )
    return {
        "schema_version": "4.0",
        "generated_at": generated_at_iso,
        "live_updated_at": generated_at_iso,
        "batch_id": f"live-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "search_grounded": False,
        "weekly_digest": {
            "period_label": f"近 7 日全球 AI 大事周报（截至 {generated_at_iso[:10]}）",
            "period_label_en": f"Weekly Global AI Digest (as of {generated_at_iso[:10]})",
            "summary": "",
            "summary_en": "",
            "highlights": [],
        },
        "companies": companies,
        "timeline": [],
    }


def merge_live_ai_items_into_doc(
    doc: Optional[Dict[str, Any]],
    live_raw_items: List[dict],
    generated_at_iso: str,
) -> Tuple[Dict[str, Any], List[str]]:
    """Merge live wire and first-hand official drops into an AiProgressDoc."""
    base = deepcopy(doc) if isinstance(doc, dict) and doc.get("companies") else _empty_doc(generated_at_iso)

    by_company: Dict[str, Dict[str, Any]] = {}
    for comp in base.get("companies") or []:
        cid = comp.get("company_id")
        if cid:
            by_company[cid] = comp

    for spec in _LAB_CATALOG:
        cid = spec["company_id"]
        if cid not in by_company:
            comp = {
                "company_id": cid,
                "company_name": spec["company_name"],
                "company_name_en": spec.get("company_name_en") or spec["company_name"],
                "region": spec["region"],
                "region_en": spec.get("region_en") or spec["region"],
                "flagship_model": spec["flagship_model"],
                "open_source_line": spec["open_source_line"],
                "access_limits": spec["access_limits"],
                "access_limits_en": spec.get("access_limits_en") or spec["access_limits"],
                "model_lineage": list(spec.get("model_lineage") or []),
                "recent_count": 0,
                "latest_date": "",
                "latest_headline": "",
                "items": [],
            }
            by_company[cid] = comp
            base["companies"].append(comp)
        else:
            comp = by_company[cid]
            comp["flagship_model"] = spec["flagship_model"]
            comp["open_source_line"] = spec["open_source_line"]
            comp["access_limits"] = spec["access_limits"]
            comp["access_limits_en"] = spec.get("access_limits_en") or spec["access_limits"]
            comp["model_lineage"] = list(spec.get("model_lineage") or [])

    seen_urls: Dict[str, Dict[str, Any]] = {}
    seen_titles: Dict[str, Dict[str, Any]] = {}
    seen_ids: Set[str] = set()

    def _register(item: Dict[str, Any]) -> None:
        # Ensure first-hand metadata is hydrated even on legacy batch items
        if "is_first_hand" not in item:
            item["is_first_hand"] = is_first_hand_ai_source(
                "",
                str(item.get("source_name") or ""),
                str(item.get("source_url") or ""),
            )
            item["source_tier"] = "first_party" if item["is_first_hand"] else item.get("source_tier") or "batch_digest"
        seen_ids.add(str(item.get("id") or ""))
        uk = _norm_url_key(item.get("source_url"))
        tk = _norm_title_key(item.get("title"))
        if uk:
            seen_urls[uk] = item
        if tk:
            seen_titles[tk] = item

    def _find_similar_title_match(title: str, url: str) -> Optional[Dict[str, Any]]:
        tk = _norm_title_key(title)
        if tk and tk in seen_titles:
            return seen_titles[tk]
        for old_it in seen_titles.values():
            if is_similar_ai_release(
                title,
                url,
                str(old_it.get("title") or ""),
                str(old_it.get("source_url") or ""),
            ):
                return old_it
        return None

    new_ids: List[str] = []
    mutated = False

    _CANNED_WHAT_RE = re.compile(r"前沿 AI 模型研究与开发生态动态|实验室官方一线研究动态（来源：")
    _CANNED_WHO_RE = re.compile(r"^(?:AI 开发者、科研人员与前沿(?:关注者|用户)|AI 开发者、科技观察者与普通效率用户|AI 开发者与普通用户)$")
    _CANNED_LIMIT_RE = re.compile(r"^(?:具体额度、开源协议与硬件门槛以官方发布说明为准|详见官方发布说明与接口配额|详见原文披露的接口配额)")

    placeholder_curated_prefixes = (
        "ai_google_gemini4_", "ai_openai_gpt62_", "ai_deepseek_v4_", "ai_google_diffusiongemma_",
        "ai_anthropic_claude_", "ai_tencent_hy4_", "ai_qwen4_", "ai_kimi_k31_", "ai_radixark_",
        "ai_vllm_llamacpp", "ai_openai_amd_", "ai_xai_grok3_colossus", "ai_bytedance_seed_suite",
        "ai_zhipu_glm_open", "ai_minimax_hailuo", "ai_baidu_ernie_open", "ai_huawei_openpangu",
        "ai_mistral_codestral", "ai_apple_foundation_mlx", "ai_amazon_nova_bedrock",
        "ai_perplexity_sonar", "ai_cursor_composer_ide", "ai_stability_open_media",
    )
    rehomed_items: List[Dict[str, Any]] = []
    for comp in base["companies"]:
        cleaned_existing = []
        for it in comp.get("items") or []:
            it_id = str(it.get("id") or "")
            it_title = strip_raw_urls_and_domain_tails(str(it.get("title") or ""))
            if it_title != it.get("title"):
                it["title"] = it_title
                mutated = True
            it_src = str(it.get("source_name") or "")
            it_url = str(it.get("source_url") or "")
            if it_id.startswith(placeholder_curated_prefixes) or it_src.strip().lower() == "batch_digest":
                mutated = True
                continue
            if (
                is_omnibus_digest_title(it_title)
                or AI_NOISE_RE.search(f"{it_title} {it.get('title_en') or ''} {it.get('what_it_does') or ''}")
                or is_foreign_subject_blocked(it_title, str(it.get("what_it_does") or ""))
            ):
                mutated = True
                continue
            if it_title.startswith("[HF Paper]"):
                m_up = re.search(r"▲(\d+)", it_src)
                if m_up and int(m_up.group(1)) < 12:
                    mutated = True
                    continue
            if not it_id.startswith("ai_tool_") and not it.get("is_first_hand"):
                if not AI_KW_RE.search(it_title):
                    mutated = True
                    continue
            if "GitHub Changelog" in it_src and not re.search(r"(?:copilot|\bai\b|model|agent|mcp)", it_title, re.I):
                mutated = True
                continue
            w_cur = str(it.get("what_it_does") or "")
            w_cleaned = _infer_what_it_does_zh(it_title, w_cur, is_tool_release=it_id.startswith("ai_tool_"))
            if w_cleaned != w_cur.strip() or _BOILERPLATE_WHAT_RE.search(w_cur) or _CANNED_WHAT_RE.search(w_cur):
                it["what_it_does"] = w_cleaned
                mutated = True
            if _CANNED_WHO_RE.search(str(it.get("who_cares") or "").strip()):
                it["who_cares"] = ""
                mutated = True
            if _CANNED_LIMIT_RE.search(str(it.get("limitations") or "").strip()):
                it["limitations"] = ""
                it["limitations_en"] = ""
                mutated = True
            # Re-evaluate company, open-source accuracy & 5-dim classification so polluted items self-heal
            inf_cid, inf_cname, inf_reg = _infer_company(it_title, it_url, it_src)
            cur_os = detect_is_open_source(it_title, str(it.get("what_it_does") or ""), url=it_url, company_id=inf_cid)
            if bool(it.get("is_open_source")) != cur_os:
                it["is_open_source"] = cur_os
                mutated = True
            cur_dim_label = str(it.get("milestone_dim_label") or "")
            if not it.get("milestone_dim") or not cur_dim_label or any(ord(c) >= 0x2600 for c in cur_dim_label):
                dim_id, dim_zh, dim_en = classify_ai_milestone_dim(it_title, str(it.get("what_it_does") or ""), is_open_source=cur_os, category=str(it.get("category") or ""))
                it["milestone_dim"] = dim_id
                it["milestone_dim_label"] = dim_zh
                it["milestone_dim_label_en"] = dim_en
                mutated = True
            if inf_cid != comp.get("company_id") and inf_cid in by_company:
                it["company_id"] = inf_cid
                it["company_name"] = inf_cname
                it["region"] = inf_reg
                rehomed_items.append(it)
                mutated = True
                continue
            cleaned_existing.append(it)
            _register(it)
        comp["items"] = cleaned_existing
    for mv in rehomed_items:
        target = by_company.get(mv["company_id"])
        if target is not None:
            target.setdefault("items", []).insert(0, mv)
            _register(mv)
    for it in base.get("timeline") or []:
        it_title = str(it.get("title") or "")
        if AI_NOISE_RE.search(it_title):
            continue
        w_cur = str(it.get("what_it_does") or "")
        w_cleaned = _infer_what_it_does_zh(it_title, w_cur, is_tool_release=str(it.get("id") or "").startswith("ai_tool_"))
        if w_cleaned != w_cur.strip():
            it["what_it_does"] = w_cleaned
            mutated = True
        _register(it)

    for raw_it in live_raw_items:
        candidate = extract_ai_release_item(raw_it, generated_at_iso)
        if candidate is None:
            continue
        uk = _norm_url_key(candidate.get("source_url"))
        existing = (seen_urls.get(uk) if uk else None) or _find_similar_title_match(
            str(candidate.get("title") or ""),
            str(candidate.get("source_url") or ""),
        )

        if existing is not None:
            # Upgrade existing record with finer timestamp, richer title, or first-hand attribution, preserving related_sources
            rel = list(existing.get("related_sources") or [])
            if candidate.get("source_name"):
                norm_cu = _norm_url_key(candidate.get("source_url"))
                if not any(_norm_url_key(r.get("url")) == norm_cu and norm_cu for r in rel):
                    rel.append({"source_name": candidate["source_name"], "url": candidate.get("source_url") or "", "is_first_hand": bool(candidate["is_first_hand"])})
                    existing["related_sources"] = rel[:8]
                    mutated = True
            if len(str(candidate["date"])) > len(str(existing.get("date") or "")):
                existing["date"] = candidate["date"]
                mutated = True
            if len(str(candidate["title"])) > len(str(existing.get("title") or "")) and len(str(existing.get("title") or "")) <= 24:
                existing["title"] = candidate["title"]
                mutated = True
            if candidate["is_first_hand"] and not existing.get("is_first_hand"):
                existing["is_first_hand"] = True
                existing["source_tier"] = "first_party"
                if candidate.get("source_url"):
                    existing["source_url"] = candidate["source_url"]
                if candidate.get("source_name"):
                    existing["source_name"] = candidate["source_name"]
                mutated = True
            continue

        cid = candidate["company_id"]
        target_comp = by_company.get(cid) or by_company["indie_opensource"]
        target_comp.setdefault("items", []).insert(0, candidate)
        _register(candidate)
        new_ids.append(candidate["id"])
        mutated = True

    all_items: List[Dict[str, Any]] = []
    unique_global: Dict[str, Dict[str, Any]] = {}

    for comp in base["companies"]:
        deduped_comp: List[Dict[str, Any]] = []
        seen_local: Set[str] = set()
        comp_sorted = sorted(comp.get("items") or [], key=lambda x: _sort_key_iso_desc(x.get("date")), reverse=True)
        for it in comp_sorted:
            key = _norm_url_key(it.get("source_url")) or _norm_title_key(it.get("title")) or str(it.get("id"))
            it_title = str(it.get("title") or "")
            it_url = str(it.get("source_url") or "")
            dup_prev = None
            if key in seen_local:
                dup_prev = next((p for p in deduped_comp if (_norm_url_key(p.get("source_url")) or _norm_title_key(p.get("title")) or str(p.get("id"))) == key), None)
            if dup_prev is None:
                dup_prev = next(
                    (
                        prev
                        for prev in deduped_comp
                        if is_similar_ai_release(
                            it_title,
                            it_url,
                            str(prev.get("title") or ""),
                            str(prev.get("source_url") or ""),
                            company_id_a=str(comp.get("company_id") or ""),
                            company_id_b=str(comp.get("company_id") or ""),
                        )
                    ),
                    None,
                )
            if dup_prev is not None:
                rel = list(dup_prev.get("related_sources") or [])
                if it.get("source_name"):
                    norm_iu = _norm_url_key(it_url)
                    if not any(_norm_url_key(r.get("url")) == norm_iu and norm_iu for r in rel):
                        rel.append({"source_name": it.get("source_name"), "url": it_url, "is_first_hand": bool(it.get("is_first_hand"))})
                        dup_prev["related_sources"] = rel[:8]
                if it.get("is_first_hand") and not dup_prev.get("is_first_hand"):
                    dup_prev["is_first_hand"] = True
                    dup_prev["source_tier"] = "first_party"
                    if it_url:
                        dup_prev["source_url"] = it_url
                    if it.get("source_name"):
                        dup_prev["source_name"] = it.get("source_name")
                mutated = True
                continue
            seen_local.add(key)
            deduped_comp.append(it)
        if len(deduped_comp) != len(comp.get("items") or []) or len(deduped_comp) > 8:
            mutated = True
        comp["items"] = deduped_comp[:8]
        comp["recent_count"] = len(comp["items"])
        comp["latest_date"] = comp["items"][0]["date"] if comp["items"] else ""
        comp["latest_headline"] = comp["items"][0]["title"] if comp["items"] else ""
        for it in comp["items"]:
            uk = _norm_url_key(it.get("source_url")) or _norm_title_key(it.get("title")) or str(it.get("id"))
            if uk not in unique_global and not any(
                is_similar_ai_release(
                    str(it.get("title") or ""),
                    str(it.get("source_url") or ""),
                    str(prev.get("title") or ""),
                    str(prev.get("source_url") or ""),
                    company_id_a=str(it.get("company_id") or ""),
                    company_id_b=str(prev.get("company_id") or ""),
                )
                for prev in unique_global.values()
            ):
                unique_global[uk] = it

    all_items = sorted(unique_global.values(), key=lambda x: _sort_key_iso_desc(x.get("date")), reverse=True)
    base["timeline"] = all_items[:120]

    # Top highlights: prioritize newest day-bucket, then first-hand / full-timestamp items
    highlights = sorted(
        all_items,
        key=lambda x: (
            _sort_key_iso_desc(x.get("date"))[0],
            1 if x.get("is_first_hand") else 0,
            _sort_key_iso_desc(x.get("date"))[1],
            _sort_key_iso_desc(x.get("date"))[2],
        ),
        reverse=True,
    )[:8]

    digest = base.setdefault("weekly_digest", {})
    digest["highlights"] = highlights
    digest["period_label"] = f"近 7 日全球 AI 大事周报（截至 {generated_at_iso[:10]}）"
    digest["period_label_en"] = f"Weekly Global AI Digest (as of {generated_at_iso[:10]})"

    overseas_cnt = sum(1 for x in all_items if x.get("region") == "海外")
    cn_cnt = sum(1 for x in all_items if x.get("region") == "国内")
    os_cnt = sum(1 for x in all_items if x.get("is_open_source"))
    fh_cnt = sum(1 for x in all_items if x.get("is_first_hand"))
    digest["summary"] = (
        f"实时追踪 {len(all_items)} 项国内外 AI 关键进展（海外 {overseas_cnt} · 国内 {cn_cnt} · 开源 {os_cnt} · 一手官方 {fh_cnt}）。"
        f"自动聚合官方博客、Hugging Face、GitHub Releases 与 7×24 突发快讯，重大发布秒级入榜。"
    )
    digest["summary_en"] = (
        f"Tracking {len(all_items)} AI milestones ({overseas_cnt} global, {cn_cnt} China, {os_cnt} open-source, {fh_cnt} first-hand official) "
        f"from lab blogs, Hugging Face, GitHub Releases & 7×24 live wires."
    )

    if mutated:
        base["generated_at"] = generated_at_iso
        base["live_updated_at"] = generated_at_iso

    return base, new_ids


def refresh_ai_progress_live(
    web_root: Path,
    *,
    live_wire_doc: Optional[Dict[str, Any]] = None,
    include_remote_first_hand: bool = True,
    cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Incrementally refresh data/ai_progress.json from 7x24 wire + first-hand AI sources."""
    data_dir = Path(web_root) / "data"
    ai_path = data_dir / "ai_progress.json"
    wire_path = data_dir / "live_wire.json"

    generated_at_iso = to_iso_shanghai(now_shanghai())
    existing_doc: Optional[Dict[str, Any]] = None
    if ai_path.exists():
        try:
            existing_doc = json.loads(ai_path.read_text(encoding="utf-8"))
        except Exception:
            existing_doc = None

    raw_pool: List[dict] = []
    if isinstance(live_wire_doc, dict):
        raw_pool.extend(live_wire_doc.get("items") or [])
    elif wire_path.exists():
        try:
            wire_disk = json.loads(wire_path.read_text(encoding="utf-8"))
            raw_pool.extend(wire_disk.get("items") or [])
        except Exception:
            pass

    if include_remote_first_hand:
        raw_pool.extend(fetch_first_hand_ai_drops(cache_dir=cache_dir))

    merged_doc, new_ids = merge_live_ai_items_into_doc(existing_doc, raw_pool, generated_at_iso)
    # Persist if file didn't exist, new items arrived, or existing timestamps/first-hand flags were upgraded
    changed = bool(new_ids) or (not ai_path.exists()) or (existing_doc is not None and merged_doc.get("generated_at") != existing_doc.get("generated_at"))
    if changed:
        atomic_write_json(ai_path, merged_doc)

    return {
        "doc": merged_doc,
        "new_ids": new_ids,
        "changed": changed,
        "item_count": len(merged_doc.get("timeline") or []),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Incrementally refresh data/ai_progress.json from wire + first-hand sources.")
    parser.add_argument("--root", type=str, default=".", help="Project root containing data/ directory")
    parser.add_argument("--no-remote", action="store_true", help="Skip remote HuggingFace/GitHub/RSS fetches")
    args = parser.parse_args()
    root_path = Path(args.root).resolve()
    summary = refresh_ai_progress_live(
        root_path,
        include_remote_first_hand=not args.no_remote,
        cache_dir=root_path / ".cache_http",
    )
    print(f"AI radar live refresh complete: total={summary['item_count']} new={len(summary['new_ids'])} changed={summary['changed']}")

