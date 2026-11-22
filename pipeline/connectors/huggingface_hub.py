"""Hugging Face Hub official model cards, weights license & availability connector."""

from __future__ import annotations

from datetime import timedelta
import re
import time
from typing import Any, Dict, List, Optional, Tuple

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

_HF_PIPELINE_TAG_ZH: Dict[str, Tuple[str, str]] = {
    "image-text-to-text": ("图文多模态理解与对话生成", "支持输入图像与文本并生成精准分析回复，适用于视觉问答、图表解析与多模态代理"),
    "video-text-to-text": ("视频与多模态语义理解", "可联合解析视频帧与指令文本，用于视频内容总结、动作理解与长时序检索"),
    "image-text-to-video": ("文生/图生高清视频生成", "根据参考图片与文本提示生成连贯视频画面，适用于数字内容创作与镜头合成"),
    "text-to-video": ("文本生成视频模型", "直接由自然语言提示生成多帧连续视频序列，支持高帧率动态场景表达"),
    "text-to-image": ("文生图扩散视觉生成", "高效率文生图模型，适用于海报创意设计、高分辨率图像渲染与可控编辑"),
    "image-to-image": ("图像重绘与风格编辑", "支持局部修图、超分辨率重建与多风格图像迁移任务"),
    "text-generation": ("通用大语言文本生成", "具备代码编写、逻辑推理、多轮对话与长文本理解能力的开源对话/基座模型"),
    "automatic-speech-recognition": ("高精度语音识别转写 (ASR)", "将多语种音频流或本地录音实时转写为高精度带标点文本，适用于会议纪要与语音助手"),
    "text-to-speech": ("自然语音合成 (TTS)", "高拟真度多音色文本转语音模型，用于有声播报与实时语音交互"),
    "feature-extraction": ("向量表征与特征提取", "用于语义向量编码、稀疏自编码器分析或 RAG 知识库高维特征检索"),
    "sentence-similarity": ("语义相似度匹配引擎", "计算句对相关性得分，专为检索重排与知识库召回优化"),
    "image-classification": ("图像分类与识别模型", "面向视觉物体归类与质检场景的高效率判别模型"),
    "question-answering": ("智能问答抽取模型", "面向长文档精准抽取答案与结构化信息"),
    "summarization": ("长文本自动摘要模型", "自动提炼长篇报告、论文与新闻资讯核心要点"),
    "translation": ("多语种神经机器翻译", "面向跨语言长句、技术文档与资讯的高精度互译"),
    "fill-mask": ("掩码语义理解基座模型", "用于预训练语义表示学习与文本填空预测任务"),
    "any-to-any": ("全模态任意输入输出模型", "打通文本、图像、音频及视频联合表征与跨模态端到端推理"),
}


_HF_ORG_ZH: Dict[str, str] = {
    "qwen": "阿里通义千问 (Qwen)",
    "deepseek-ai": "DeepSeek",
    "tencent": "腾讯混元",
    "moonshotai": "月之暗面 (Kimi)",
    "zai-org": "智谱 AI (GLM)",
    "baichuan-inc": "百川智能",
    "bytedance-seed": "字节跳动 Seed",
    "minimaxai": "MiniMax",
    "mistralai": "Mistral AI",
    "nvidia": "英伟达 (NVIDIA)",
    "microsoft": "微软 (Microsoft)",
    "stabilityai": "Stability AI",
    "google": "Google / DeepMind",
    "meta-llama": "Meta Llama",
}


def format_hf_tool_summary(
    pipeline_tag: str,
    downloads: Any,
    model_id: str = "",
    tags: Optional[List[str]] = None,
) -> str:
    tag = str(pipeline_tag or "").strip().lower()
    task_label, use_case = _HF_PIPELINE_TAG_ZH.get(
        tag,
        ("开源多模态与深度学习模型", "支持 Transformers / vLLM 等主流推理框架部署"),
    )
    mid = str(model_id or "").strip()
    org_part, name_part = (mid.split("/", 1) + [""])[:2] if "/" in mid else ("", mid)
    org_zh = _HF_ORG_ZH.get(org_part.lower(), org_part)

    traits: List[str] = []
    combined_low = f"{mid} {' '.join(tags or [])}".lower()
    size_m = re.search(r"(\d+(?:\.\d+)?)\s*([bt])\b", name_part, re.I)
    if size_m:
        traits.append(f"{size_m.group(1)}{size_m.group(2).upper()} 参数档")
    if "moe" in combined_low or re.search(r"-a\d+b\b", name_part.lower()):
        traits.append("MoE 稀疏激活")
    if "thinking" in combined_low or "-r1" in combined_low or "reason" in combined_low:
        traits.append("长链推理强化")
    elif "coder" in combined_low or "code" in combined_low:
        traits.append("代码工程专项")
    elif "vl" in name_part.lower() or "vision" in combined_low or "omni" in combined_low:
        traits.append("跨模态视觉感知")
    elif "instruct" in combined_low or "chat" in combined_low:
        traits.append("指令微调对话版")

    formats = [fmt.upper() for fmt in ("gguf", "fp8", "awq", "gptq", "mlx") if fmt in combined_low]
    if formats:
        traits.append(f"支持 {'/'.join(formats[:2])} 量化")

    if isinstance(downloads, (int, float)) and downloads > 0:
        if downloads >= 10_000:
            dl_txt = f"近期下载 {downloads / 10_000:.1f} 万次"
        else:
            dl_txt = f"近期下载 {int(downloads)} 次"
    else:
        dl_txt = "近期新发布权重"

    prefix = f"{org_zh} 旗下 {name_part}" if (org_zh and name_part) else (name_part or task_label)
    trait_str = f"（{' · '.join(traits[:3])}）" if traits else ""
    if name_part:
        return f"{prefix}{trait_str}：{task_label}；{use_case}（{dl_txt}）"
    return f"{task_label}；{use_case}（{dl_txt}）"


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
            if downloads is not None and int(downloads) < 10:
                continue
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
                        "tags": [str(t) for t in tags[:12] if isinstance(t, str)],
                        "official_url": card_url,
                        "release_url": card_url,
                        "docs_url": card_url,
                        "summary": format_hf_tool_summary(pipeline_tag, downloads, model_id=model_id, tags=tags),
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
