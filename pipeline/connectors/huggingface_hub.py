"""Hugging Face Hub official model cards, weights license & availability connector."""

from __future__ import annotations

from datetime import timedelta
import time
from typing import Any, Dict, List, Optional

from pipeline.connectors.base import HttpCacheStore, polite_get
from pipeline.id_utils import make_raw_item_id
from pipeline.time_utils import now_shanghai, parse_iso_datetime, parse_published_at, to_iso_shanghai

DEFAULT_HF_ORGS = [
    {"org": "Qwen", "name": "Qwen (通义千问)", "entity_id": "ent_qwen_alibaba"},
    {"org": "deepseek-ai", "name": "DeepSeek", "entity_id": "ent_deepseek"},
    {"org": "tencent", "name": "Tencent Hunyuan", "entity_id": "ent_tencent_hunyuan"},
    {"org": "moonshotai", "name": "Moonshot (Kimi)", "entity_id": "ent_kimi_moonshot"},
    {"org": "zai-org", "name": "Zhipu AI (GLM)", "entity_id": "ent_zhipu_glm"},
    {"org": "baichuan-inc", "name": "Baichuan", "entity_id": "ent_ai_infra_tools"},
    {"org": "ByteDance-Seed", "name": "ByteDance Seed", "entity_id": "ent_bytedance_doubao"},
    {"org": "MiniMaxAI", "name": "MiniMax", "entity_id": "ent_minimax"},
    {"org": "mistralai", "name": "Mistral AI", "entity_id": "ent_mistral"},
    {"org": "nvidia", "name": "NVIDIA", "entity_id": "ent_nvidia"},
    {"org": "microsoft", "name": "Microsoft", "entity_id": "ent_microsoft"},
    {"org": "stabilityai", "name": "Stability AI", "entity_id": "ent_ai_infra_tools"},
    {"org": "google", "name": "Google / Gemma", "entity_id": "ent_google"},
    {"org": "meta-llama", "name": "Meta Llama", "entity_id": "ent_meta"},
]


def _extract_license(tags: List[str]) -> Optional[str]:
    for t in tags:
        if isinstance(t, str) and t.startswith("license:"):
            lic = t.split(":", 1)[1].strip()
            if lic.lower() == "other":
                return "自定义开源许可 (详见模型卡)"
            return lic
    return None


def fetch_huggingface_models(
    cache: HttpCacheStore,
    *,
    orgs: List[dict] | None = None,
    previous_tools: List[dict] | None = None,
    previous_items: List[dict] | None = None,
) -> Dict[str, Any]:
    """Fetch recent open-weight model releases & licenses from Hugging Face Hub API."""
    targets = orgs or DEFAULT_HF_ORGS
    now_dt = now_shanghai()
    fetched_iso = to_iso_shanghai(now_dt)
    t0 = time.monotonic()

    prev_tool_by_org = {
        str(t.get("repo") or "").split("/", 1)[0]: t for t in (previous_tools or []) if t.get("repo")
    }
    prev_items_by_org = {}
    for pit in (previous_items or []):
        pfam = str(pit.get("publisher_family") or "")
        if pfam.startswith("hf-"):
            prev_items_by_org.setdefault(pfam.replace("hf-", "", 1), []).append(pit)

    items: List[dict] = []
    tools: List[dict] = []
    errors: List[str] = []

    for spec in targets:
        org = spec["org"]
        url = f"https://huggingface.co/api/models?author={org}&sort=lastModified&direction=-1&limit=3"
        res = polite_get(url, cache=cache, timeout=(4, 8), expect_json=True)
        if not res.ok or not isinstance(res.json_data, list):
            if res.status == "not_modified_304":
                if org in prev_tool_by_org:
                    tools.append(prev_tool_by_org[org])
                for pit in prev_items_by_org.get(org, []):
                    pub_dt = parse_iso_datetime(pit.get("published_at")) if pit.get("published_at") else None
                    if pub_dt and (now_dt - pub_dt) <= timedelta(days=10):
                        items.append(pit)
                continue
            errors.append(f"{org}: {res.error_message}")
            if org in prev_tool_by_org:
                tools.append(prev_tool_by_org[org])
            continue

        added_tool_for_org = False
        added_item_for_org = False
        for m in res.json_data:
            if not isinstance(m, dict) or not m.get("id"):
                continue
            model_id = str(m["id"])
            card_url = f"https://huggingface.co/{model_id}"
            tags = m.get("tags") if isinstance(m.get("tags"), list) else []
            license_id = _extract_license(tags)
            pub_iso, _ = parse_published_at(m.get("lastModified") or m.get("createdAt"), "huggingface")
            pub_dt = parse_iso_datetime(pub_iso) if pub_iso else None
            # Exclude stale models older than 45 days (prevents year-old models from posing as new)
            if pub_dt and (now_dt - pub_dt) > timedelta(days=45):
                continue

            pipeline_tag = m.get("pipeline_tag") or "text-generation"
            downloads = m.get("downloads")
            likes = m.get("likes")
            gated = m.get("gated")
            avail_stage = "waitlist" if gated else "ga"
            avail_label = "需申请授权下载" if gated else "开源权重可用 (GA)"

            if not added_tool_for_org:
                added_tool_for_org = True
                tools.append(
                    {
                        "tool_id": f"tool_hf_{model_id.replace('/', '_').replace('.', '_').lower()}",
                        "name": model_id,
                        "repo": model_id,
                        "tool_type": f"开源模型权重 ({pipeline_tag})",
                        "sector": "AI 大模型",
                        "entity_id": spec["entity_id"],
                        "availability_stage": avail_stage,
                        "availability_label": avail_label,
                        "latest_version": f"更新于 {pub_iso[:10] if pub_iso else '近期'}",
                        "version_published_at": pub_iso,
                        "license": license_id or "详见模型卡",
                        "downloads": downloads,
                        "likes": likes,
                        "official_url": card_url,
                        "release_url": card_url,
                        "docs_url": card_url,
                        "summary": f"模型任务：{pipeline_tag}；近期下载：{downloads if downloads is not None else '未知'} 次",
                        "deployment_requirements": "需依据模型卡参数规模配置对应 GPU 显存及推理后端（vLLM / Transformers / llama.cpp）",
                        "pricing_or_cost": f"开源权重自部署（许可证：{license_id or '详见模型卡'}）",
                        "checked_at": fetched_iso,
                        "source_name": "Hugging Face Hub API",
                        "source_url": card_url,
                    }
                )

            if not added_item_for_org and pub_dt and (now_dt - pub_dt) <= timedelta(days=7):
                added_item_for_org = True
                title = f"[HF 模型卡] {model_id} 更新 ({license_id or '开源许可详见卡片'})"
                excerpt = (
                    f"Hugging Face 官方机构 {org} 更新模型 {model_id}（{avail_label}，"
                    f"许可：{license_id or '见卡片'}，近期下载：{downloads if downloads is not None else '未提供'}）。"
                )
                items.append(
                    {
                        "item_id": make_raw_item_id("huggingface-hub", card_url, title),
                        "source_id": "huggingface-hub",
                        "source_name": "Hugging Face 官方模型库",
                        "source_kind": "model_card",
                        "source_tier": "tech_material",
                        "publisher_family": f"hf-{org}",
                        "citable_as_news": True,
                        "category": "tech",
                        "title": title,
                        "url": card_url,
                        "canonical_url": card_url,
                        "published_at": pub_iso,
                        "published_at_source": "huggingface_api",
                        "fetched_at": fetched_iso,
                        "excerpt": excerpt,
                        "entity_ids": [spec["entity_id"]],
                    }
                )

    status = "ok"
    if not items and errors:
        status = "error"
    elif errors:
        status = "partial"

    return {
        "connector_id": "huggingface-hub",
        "connector_name": "Hugging Face 官方模型卡与许可证追踪",
        "source_tier": "tech_material",
        "status": status,
        "fetched_at": fetched_iso,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "item_count": len(items),
        "error_message": "; ".join(errors[:2]) if errors else None,
        "tos_note": "使用 Hugging Face 公开只读 Models API 获取模型卡元数据。",
        "items": items,
        "tech_tools": tools,
    }
