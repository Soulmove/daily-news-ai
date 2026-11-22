"""Global AI Model & Open-Source Progress Tracker (data/ai_progress.json)."""

from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .ai_lineage_catalog import HISTORICAL_BASELINE_MILESTONES, LAB_V9_METADATA
from .entities import ENTITY_BY_ID
from .gemini_pool import call_gemini_raw
from .manifest import atomic_write_json, load_json_if_exists
from .time_utils import now_shanghai, parse_iso_datetime, to_iso_shanghai

_LAB_CATALOG: List[Dict[str, Any]] = [
    {
        "company_id": "google",
        "company_name": "Google DeepMind",
        "company_name_en": "Google DeepMind",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Gemini 4 Carbon / Neon / Hydrogen · Omni · Project Genie 4",
        "open_source_line": "DiffusionGemma / Gemma 系列 / Modern Web Guidance 1.0",
        "access_limits": "Neon 定价 $3/$15 百万 Token，旗舰 Carbon 更高；免费 AI Studio 限频；Genie 4 仍为预览",
        "access_limits_en": "Neon API $3/$15 per 1M tokens; free AI Studio rate-limited; Genie 4 in preview",
    },
    {
        "company_id": "anthropic",
        "company_name": "Anthropic",
        "company_name_en": "Anthropic",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Claude Fable 5.2 / Mythos 5.2 · Claude Code",
        "open_source_line": "MCP 协议生态与 Agent 工具链",
        "access_limits": "闭源商用为主，高阶模型价格偏高且存在并发与区域限制",
        "access_limits_en": "Closed-weight commercial API with premium pricing and regional limits",
    },
    {
        "company_id": "openai",
        "company_name": "OpenAI",
        "company_name_en": "OpenAI",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "GPT-6.2 Astra / Sol · GPT-6 Cyber · GPT-Images 2.6",
        "open_source_line": "Codex CLI / OpenAI SDK",
        "access_limits": "闭源订阅与 API 计费，Cyber 等垂直版需企业白名单审批",
        "access_limits_en": "Closed API & subscription tiers; specialized variants like Cyber gated to approved orgs",
    },
    {
        "company_id": "qwen",
        "company_name": "阿里千问 (Qwen)",
        "company_name_en": "Alibaba Qwen",
        "region": "国内",
        "region_en": "China",
        "flagship_model": "Qwen4-Max-Preview · Qwen 开源家族",
        "open_source_line": "Hugging Face / ModelScope 开放多尺寸权重（支持商用）",
        "access_limits": "Preview 旗舰以云端 API 为主；本地运行大尺寸版需高显存",
        "access_limits_en": "Max Preview via cloud API; large local open-weight models need high VRAM",
    },
    {
        "company_id": "kimi",
        "company_name": "月之暗面 (Kimi)",
        "company_name_en": "Moonshot AI (Kimi)",
        "region": "国内",
        "region_en": "China",
        "flagship_model": "Kimi K3.1 Pro",
        "open_source_line": "开放完整权重与长上下文/搜索 Agent 生态",
        "access_limits": "完整权重自部署需多卡集群，个人用户建议用量化版或托管 API",
        "access_limits_en": "Full weights require multi-GPU servers; consumers should use quantized builds or API",
    },
    {
        "company_id": "tencent_hunyuan",
        "company_name": "腾讯混元 (Hunyuan)",
        "company_name_en": "Tencent Hunyuan",
        "region": "国内",
        "region_en": "China",
        "flagship_model": "混元 Hy4 Flash · 混元视频/3D",
        "open_source_line": "混元 3D / 视频开源生态",
        "access_limits": "算力供给紧张或影响超大参数下一代发布节奏，Flash 档主打高性价比",
        "access_limits_en": "Compute supply may pace ultra-large next-gen; Flash focuses on speed/cost",
    },
    {
        "company_id": "deepseek",
        "company_name": "DeepSeek",
        "company_name_en": "DeepSeek",
        "region": "国内",
        "region_en": "China",
        "flagship_model": "DeepSeek 推理与代码开源系列",
        "open_source_line": "MIT 协议开放权重，极低推理成本",
        "access_limits": "高峰时段官方网页与 API 偶发排队，可随时自建或切第三方算力",
        "access_limits_en": "Peak-hour official API queuing; MIT weights allow easy self-hosting",
    },
    {
        "company_id": "microsoft",
        "company_name": "微软 (Microsoft)",
        "company_name_en": "Microsoft AI / Copilot",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Copilot / Phi-4 / Windows AI",
        "open_source_line": "Phi 系列小模型开放权重；Win11 Copilot 为闭源端侧整合",
        "access_limits": "Windows 11 Copilot、Azure AI Foundry 与 GitHub Copilot 分级订阅",
        "access_limits_en": "Integrated in Windows 11 Copilot, Azure AI & GitHub Copilot tiers",
    },
    {
        "company_id": "meta",
        "company_name": "Meta AI",
        "company_name_en": "Meta AI / Llama",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Llama 系列 / Meta AI",
        "open_source_line": "Llama 社区许可开源旗舰与端侧轻量系列",
        "access_limits": "部分多模态模型受区域与商业规模许可条款限制",
        "access_limits_en": "Community license terms & regional rollouts apply",
    },
    {
        "company_id": "nvidia",
        "company_name": "英伟达 (NVIDIA)",
        "company_name_en": "NVIDIA AI / Omniverse / CUDA",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Nemotron / Cosmos / Omniverse / TensorRT",
        "open_source_line": "Nemotron 开放权重、Cosmos 世界模型与本地/集群推理加速工具",
        "access_limits": "部分企业微服务（NIM）与物理仿真栈需 NVIDIA GPU 环境支持",
        "access_limits_en": "NVIDIA GPU environment required for TensorRT-LLM / NIM / Omniverse stacks",
    },
    {
        "company_id": "xai",
        "company_name": "xAI / Grok",
        "company_name_en": "xAI / Grok",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Grok 系列模型 / Colossus 集群",
        "open_source_line": "早期 Grok-1 开放权重",
        "access_limits": "旗舰版本通过 xAI API 与 X Premium+ 提供访问",
        "access_limits_en": "Flagship models available via xAI API & X Premium+",
    },
    {
        "company_id": "bytedance_doubao",
        "company_name": "字节豆包 (Seed)",
        "company_name_en": "ByteDance Seed / Doubao",
        "region": "国内",
        "region_en": "China",
        "flagship_model": "豆包大模型 / Seedance 视频 / UI-TARS",
        "open_source_line": "ByteDance Seed 开源多模态与 Agent 系列",
        "access_limits": "主要通过火山引擎方舟与豆包端提供服务",
        "access_limits_en": "Commercial API via Volcano Engine Ark & Doubao consumer app",
    },
    {
        "company_id": "zhipu_glm",
        "company_name": "智谱 AI (GLM)",
        "company_name_en": "Zhipu AI (GLM)",
        "region": "国内",
        "region_en": "China",
        "flagship_model": "GLM-4 / GLM-Z1 推理与编程系列",
        "open_source_line": "THUDM / zai-org GitHub 与 Hugging Face 开源权重",
        "access_limits": "旗舰 API 计费，开源小尺寸支持商用",
        "access_limits_en": "Commercial API & open-weight GLM releases on Hugging Face",
    },
    {
        "company_id": "minimax",
        "company_name": "MiniMax / 海螺",
        "company_name_en": "MiniMax",
        "region": "国内",
        "region_en": "China",
        "flagship_model": "MiniMax 文本推理 / 海螺视频 / 语音大模型",
        "open_source_line": "MiniMax 开放权重系列",
        "access_limits": "API 按用量计费，部分权重在 Hugging Face 公开",
        "access_limits_en": "Metered API access & selected open-weight checkpoints",
    },
    {
        "company_id": "baidu_ernie",
        "company_name": "百度文心 (ERNIE)",
        "company_name_en": "Baidu ERNIE",
        "region": "国内",
        "region_en": "China",
        "flagship_model": "文心大模型 ERNIE 系列 / X1 深度思考",
        "open_source_line": "ERNIE 开源家族与飞桨部署生态",
        "access_limits": "通过千帆大模型平台与文心一言提供调用",
        "access_limits_en": "Available via Baidu Qianfan & ERNIE platform",
    },
    {
        "company_id": "huawei_pangu",
        "company_name": "华为盘古 / 昇腾",
        "company_name_en": "Huawei Pangu / Ascend",
        "region": "国内",
        "region_en": "China",
        "flagship_model": "盘古大模型 / openPangu 开源权重",
        "open_source_line": "openPangu 开源权重与昇腾 CANN 算子库",
        "access_limits": "面向昇腾 NPU 与华为云政企部署场景",
        "access_limits_en": "Optimized for Huawei Ascend NPUs and Huawei Cloud",
    },
    {
        "company_id": "mistral",
        "company_name": "Mistral AI",
        "company_name_en": "Mistral AI",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Mistral Large / Codestral / Pixtral",
        "open_source_line": "Apache 2.0 开源中小尺寸权重",
        "access_limits": "部分旗舰模型为商业闭源许可",
        "access_limits_en": "Apache 2.0 open weights + commercial frontier endpoints",
    },
    {
        "company_id": "apple_ai",
        "company_name": "Apple Intelligence",
        "company_name_en": "Apple Intelligence",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Apple Foundation Models / Private Cloud Compute",
        "open_source_line": "OpenELM / MLX 端侧推理框架",
        "access_limits": "深度绑定 Apple Silicon 硬件生态，部分地区受限",
        "access_limits_en": "Deeply integrated with Apple Silicon devices; regional rollouts apply",
    },
    {
        "company_id": "amazon_aws",
        "company_name": "Amazon AI (Nova)",
        "company_name_en": "Amazon AI / AWS Bedrock",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Amazon Nova 系列 / Bedrock",
        "open_source_line": "AWS 推理生态与企业微调栈",
        "access_limits": "依托 Amazon Bedrock 企业云服务调用",
        "access_limits_en": "Served via Amazon Bedrock managed endpoints",
    },
    {
        "company_id": "perplexity",
        "company_name": "Perplexity AI",
        "company_name_en": "Perplexity AI",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Sonar 搜索推理模型与 AI 浏览器生态",
        "open_source_line": "R1-1776 等检索微调开源衍生权重",
        "access_limits": "Pro 订阅与 Sonar API 计费",
        "access_limits_en": "Consumer Pro tiers & Sonar search API",
    },
    {
        "company_id": "cursor",
        "company_name": "Cursor (Anysphere)",
        "company_name_en": "Cursor / Anysphere",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Cursor Tab / Composer 编程 Agent",
        "open_source_line": "闭源 IDE 与定制低延迟补全模型",
        "access_limits": "订阅制 IDE 工具链，支持接入多家闭源/开源后端",
        "access_limits_en": "Commercial AI code editor subscription",
    },
    {
        "company_id": "stability",
        "company_name": "Stability AI",
        "company_name_en": "Stability AI",
        "region": "海外",
        "region_en": "Global",
        "flagship_model": "Stable Diffusion / Stable Audio / Stable Video",
        "open_source_line": "部分社区许可图像与音频生成权重",
        "access_limits": "大型商用部署需遵循 Stability 社区/企业许可门槛",
        "access_limits_en": "Community vs enterprise commercial license thresholds apply",
    },
    {
        "company_id": "indie_opensource",
        "company_name": "独立实验室 & 开源黑马",
        "company_name_en": "Indie Labs & Open-Source Researchers",
        "region": "全球开源",
        "region_en": "Open Source",
        "flagship_model": "Thinking Machines / Edge0 / RadixArk / vLLM / llama.cpp",
        "open_source_line": "个人电脑大模型、端侧小模型、本地推理引擎、音乐/3D/机器人 Harness",
        "access_limits": "迭代极快、部分项目缺图形界面，使用前需确认开源协议与本机显存",
        "access_limits_en": "Fast-moving research drops; verify license and local GPU/RAM requirements",
    },
]

_CURATED_AI_MILESTONES: List[Dict[str, Any]] = [
    {
        "id": "ai_google_gemini4_neon",
        "date": "2026-11-18",
        "company_id": "google",
        "company_name": "Google DeepMind",
        "region": "海外",
        "category": "核心中杯旗舰",
        "category_en": "Mid-Tier Powerhouse",
        "title": "Google 正式发布「Gemini 4 Neon（氖）」：近 Carbon 旗舰智力 + 百万上下文 + 档位可调思考",
        "title_en": "Google launches Gemini 4 Neon: near-Carbon intelligence at high speed with 1M unified context",
        "what_it_does": "主打高频复杂任务的甜点旗舰：原生 100 万 Token 文本/图/视频/PDF 统一上下文，专攻全仓库级编程调试、多轮工具调用、STEM 推理与 Antigravity 多 Agent 编排调度。",
        "what_it_does_en": "High-speed mid-tier powerhouse with 1M multimodal context and scalable thinking levels (high/xhigh) for agentic coding, repo debugging, and swarm orchestration.",
        "who_cares": "软件工程师、AI Agent 开发者、重度多模态研究用户",
        "limitations": "API 定价输入 $3 / 输出 $15 每百万 Token；消费端需 Gemini Advanced / AI Pro 付费订阅。",
        "limitations_en": "API priced at $3/$15 per 1M input/output tokens; consumer access requires paid Gemini AI Pro tier.",
        "source_name": "Google DeepMind / 9to5Google",
        "source_url": "https://deepmind.google/",
        "is_open_source": False,
    },
    {
        "id": "ai_openai_gpt62_astra_sol",
        "date": "2026-11-18",
        "company_id": "openai",
        "company_name": "OpenAI",
        "region": "海外",
        "category": "旗舰模型",
        "category_en": "Flagship Model",
        "title": "OpenAI 推出「GPT-6.2 Astra」与高性价比「GPT-6.2 Sol」，同步发布安全专版 GPT-6 Cyber",
        "title_en": "OpenAI releases GPT-6.2 Astra, balanced GPT-6.2 Sol & enterprise GPT-6 Cyber",
        "what_it_does": "Astra 瞄准顶尖复杂推理与多模态任务，Sol 主打日常高性价比调用，Cyber 与 Astra for Law 6.2 则切入企业网络安全与法律垂直场景。",
        "what_it_does_en": "Astra leads frontier multimodal reasoning, Sol balances cost/speed, and Cyber/Law variants serve regulated enterprise workflows.",
        "who_cares": "企业开发者、安全与法律团队、ChatGPT 重度用户",
        "limitations": "全闭源计费；GPT-6 Cyber 仅面向通过合规审批的安全组织开放。",
        "limitations_en": "Closed commercial API; GPT-6 Cyber restricted to vetted security organizations.",
        "source_name": "OpenAI 官方",
        "source_url": "https://openai.com/news/",
        "is_open_source": False,
    },
    {
        "id": "ai_google_gemini4_hydrogen",
        "date": "2026-11-18",
        "company_id": "google",
        "company_name": "Google DeepMind",
        "region": "海外",
        "category": "主力与旗舰",
        "category_en": "Flagship & Workhorse",
        "title": "Google 完善 Gemini 4 家族：轻快执行主力「Hydrogen（氢）」与重度科研旗舰「Carbon（碳）」",
        "title_en": "Google rounds out Gemini 4 family: fast execution Hydrogen & heavy-research Carbon",
        "what_it_does": "Hydrogen 负责高频自动化执行与子 Agent 并发，Carbon 专攻长周期科研难题，与最新 Neon 组成高中低三档完整梯队。",
        "what_it_does_en": "Hydrogen powers fast agent execution while Carbon tackles long-horizon research, flanking the new Gemini 4 Neon.",
        "who_cares": "开发者、投研分析师、多模态内容创作者",
        "limitations": "Google AI Studio 免费档存在每分钟/每日调用限额，重度业务需付费配额。",
        "limitations_en": "Free AI Studio tier has strict per-minute/daily quotas.",
        "source_name": "Google AI 官方",
        "source_url": "https://ai.google.dev/",
        "is_open_source": False,
    },
    {
        "id": "ai_deepseek_v4_pro",
        "date": "2026-11-17",
        "company_id": "deepseek",
        "company_name": "DeepSeek",
        "region": "国内",
        "category": "开源与极速 API",
        "category_en": "Open MoE & Fast API",
        "title": "DeepSeek 持续迭代「DeepSeek V4-Pro」与低延迟 Flash 优化，领跑 OpenRouter 开发者调用量",
        "title_en": "DeepSeek iterates on DeepSeek V4-Pro MoE & low-latency Flash, leading OpenRouter dev traffic",
        "what_it_does": "以极低推理单价与稀疏 MoE 架构提供接近海外闭源旗舰的代码与数学能力，非常适合高并发 Agent、批处理翻译和中小团队降本替代。",
        "what_it_does_en": "Ultra-low-cost MoE reasoning and coding model dominating high-volume developer workloads and budget-friendly agent pipelines.",
        "who_cares": "独立开发者、创业公司、高频 API 调用业务",
        "limitations": "高峰时段官方直连偶有排队，可通过多云/开源自建分流。",
        "limitations_en": "Official endpoint may queue during peak hours; easily routed via open weights or cloud mirrors.",
        "source_name": "DeepSeek / OpenRouter",
        "source_url": "https://www.deepseek.com/",
        "is_open_source": True,
    },
    {
        "id": "ai_google_diffusiongemma_genie4",
        "date": "2026-11-19",
        "company_id": "google",
        "company_name": "Google DeepMind",
        "region": "海外",
        "category": "开源与世界模型",
        "category_en": "Open & World Model",
        "title": "Google 更新开源模型「DiffusionGemma」与世界模型「Project Genie 4」",
        "title_en": "Google updates open-weight DiffusionGemma & Project Genie 4 world model",
        "what_it_does": "DiffusionGemma 用并行扩散机制大幅加快本地文字生成；Project Genie 4 能根据一句话生成可实时操作游玩的 3D 交互世界，用于游戏原型与机器人仿真。",
        "what_it_does_en": "DiffusionGemma speeds up local generation via diffusion; Genie 4 creates interactive 3D worlds for simulation and games.",
        "who_cares": "端侧 AI 开发者、游戏与机器人仿真团队",
        "limitations": "Project Genie 4 仍为研究预览，未开放本地权重下载。",
        "limitations_en": "Genie 4 remains a gated research preview without open weights.",
        "source_name": "Google DeepMind",
        "source_url": "https://deepmind.google/",
        "is_open_source": True,
    },
    {
        "id": "ai_anthropic_claude_fable",
        "date": "2026-11-19",
        "company_id": "anthropic",
        "company_name": "Anthropic",
        "region": "海外",
        "category": "旗舰与编程",
        "category_en": "Flagship & Coding",
        "title": "Anthropic 推进「Claude Fable / Mythos」路线与 Claude Code 生态（同步创纪录 IPO）",
        "title_en": "Anthropic advances Claude Fable/Mythos & Claude Code amid historic IPO",
        "what_it_does": "专攻复杂多文件软件工程、自动写代码修 Bug 和深度安全推理，已支持直接在 Snapchat 等第三方开发平台中驱动开发。",
        "what_it_does_en": "Industry-leading multi-file coding agents and deep reasoning integrated across third-party dev ecosystems.",
        "who_cares": "程序员、企业知识工作者、AI 产业投资者",
        "limitations": "全闭源、API 成本较高，且对部分地区网络环境有限制。",
        "limitations_en": "Closed-weight, premium API pricing, regional availability constraints.",
        "source_name": "Anthropic / TechCrunch",
        "source_url": "https://www.anthropic.com/",
        "is_open_source": False,
    },
    {
        "id": "ai_tencent_hy4_flash",
        "date": "2026-11-19",
        "company_id": "tencent_hunyuan",
        "company_name": "腾讯混元 (Hunyuan)",
        "region": "国内",
        "category": "国内模型",
        "category_en": "China Model",
        "title": "腾讯混元「Hy4 Flash」首日调用量突破 50 万亿，赋能海内外视频工具",
        "title_en": "Tencent Hunyuan Hy4 Flash tops 50T first-day calls powering global video tools",
        "what_it_does": "高速低成本轻量模型，专门用来支撑高并发实时对话、内容批量摘要以及海内外 AI 短视频工具的脚本/画面生产。",
        "what_it_does_en": "High-throughput, low-latency model built for real-time apps and batch video creation workflows.",
        "who_cares": "国内开发者、SaaS 与出海视频应用团队",
        "limitations": "受算力供给约束，下一代超大参数混元旗舰存在延期压力。",
        "limitations_en": "Compute supply bottlenecks may pace the next ultra-large Hunyuan release.",
        "source_name": "腾讯云 / 财联社",
        "source_url": "https://hunyuan.tencent.com/",
        "is_open_source": False,
    },
    {
        "id": "ai_qwen4_max_preview",
        "date": "2026-11-17",
        "company_id": "qwen",
        "company_name": "阿里千问 (Qwen)",
        "region": "国内",
        "category": "旗舰模型",
        "category_en": "Flagship Model",
        "title": "千问上线下一代旗舰预览版「Qwen4-Max-Preview」",
        "title_en": "Alibaba Qwen launches next-gen flagship Qwen4-Max-Preview",
        "what_it_does": "中文语境理解、复杂数学逻辑推理与工具调用全面升级，适合国内企业和个人平替昂贵海外模型做知识库与 Agent 办公。",
        "what_it_does_en": "Upgraded bilingual reasoning, math, and tool-use built for enterprise agents and knowledge bases.",
        "who_cares": "国内开发者、企业团队、高频办公人群",
        "limitations": "目前以阿里云云端 API 预览为主，完整开源及正式计费待公布。",
        "limitations_en": "Currently cloud API preview; full GA pricing and open-weight plans pending.",
        "source_name": "Qwen 官方 / Hugging Face",
        "source_url": "https://huggingface.co/Qwen",
        "is_open_source": False,
    },
    {
        "id": "ai_kimi_k31_pro",
        "date": "2026-11-16",
        "company_id": "kimi",
        "company_name": "月之暗面 (Kimi)",
        "region": "国内",
        "category": "开源权重",
        "category_en": "Open Weights",
        "title": "Kimi 开放「Kimi K3.1 Pro」完整权重，强化超长文档与搜索 Agent 能力",
        "title_en": "Moonshot AI opens full weights for Kimi K3.1 Pro with agentic search",
        "what_it_does": "擅长一次性通读几十万字财报/合同/论文并多轮联网深挖，开放完整权重让企业和研究者可以在私有内网部署“完全不泄密的私人 Kimi”。",
        "what_it_does_en": "Handles massive financial/legal documents and multi-step web research; open weights allow private on-premise deployment.",
        "who_cares": "投研、法律、学术研究及需要数据保密的企业",
        "limitations": "满血权重本地运行需要多卡服务器，普通用户建议用云端版或量化版。",
        "limitations_en": "Full weights need multi-GPU servers; consumers should use hosted API or quantized builds.",
        "source_name": "Moonshot AI / GitHub",
        "source_url": "https://github.com/MoonshotAI",
        "is_open_source": True,
    },
    {
        "id": "ai_radixark_daisyrose",
        "date": "2026-11-19",
        "company_id": "indie_opensource",
        "company_name": "独立实验室 & 开源黑马",
        "region": "全球开源",
        "category": "开源小模型",
        "category_en": "Open Small Model",
        "title": "RadixArk 开源强化学习小模型「DaisyRose-27B」与端侧本地大模型热潮",
        "title_en": "RadixArk open-sources RL small reasoning model DaisyRose-27B",
        "what_it_does": "用 27B 紧凑体积实现深度强化学习推理：单张消费级高端显卡或大内存 Mac 就能离线跑复杂逻辑和代码助手，彻底告别 API 月费。",
        "what_it_does_en": "Compact 27B RL reasoning model runnable locally on a single consumer GPU or Apple Silicon Mac with zero API cost.",
        "who_cares": "个人极客、隐私敏感用户、想零成本本地跑 AI 的开发者",
        "limitations": "冷门百科知识面不如千亿参数旗舰，事实类问题建议搭配联网检索。",
        "limitations_en": "Smaller world-knowledge footprint than frontier models; pair with web search for facts.",
        "source_name": "开源社区 / Hugging Face",
        "source_url": "https://huggingface.co/",
        "is_open_source": True,
    },
    {
        "id": "ai_vllm_llamacpp",
        "date": "2026-11-19",
        "company_id": "indie_opensource",
        "company_name": "独立实验室 & 开源黑马",
        "region": "全球开源",
        "category": "开源基础设施",
        "category_en": "Open Infra",
        "title": "本地与集群推理双引擎升级：vLLM v0.34.0 与 llama.cpp b12521 发布",
        "title_en": "Inference engines upgraded: vLLM v0.34.0 & llama.cpp b12521 released",
        "what_it_does": "vLLM 让服务器部署开源模型的吞吐量翻倍、显著省卡省电；llama.cpp 让普通电脑不用顶配显卡也能离线流畅跑各类开源大模型。",
        "what_it_does_en": "vLLM boosts production server GPU throughput; llama.cpp runs local models smoothly on everyday laptops.",
        "who_cares": "所有想在自己电脑或私有服务器部署开源 AI 的用户",
        "limitations": "偏底层命令行引擎，普通小白建议通过 Ollama 或 LM Studio 图形软件调用。",
        "limitations_en": "CLI developer engines; beginners can use Ollama or LM Studio UI wrappers.",
        "source_name": "GitHub Releases",
        "source_url": "https://github.com/vllm-project/vllm/releases",
        "is_open_source": True,
    },
    {
        "id": "ai_openai_amd_chip_design",
        "date": "2026-11-18",
        "company_id": "openai",
        "company_name": "OpenAI",
        "region": "海外",
        "category": "算力与多模态",
        "category_en": "Silicon & Multimodal",
        "title": "OpenAI 联手 AMD 用大模型加速下一代芯片设计，并持续迭代图像多模态",
        "title_en": "OpenAI partners with AMD on LLM-accelerated chip design alongside multimodal updates",
        "what_it_does": "用 AI 自动辅助芯片验证和底层架构优化，缩短新算力卡上市周期并拉低未来 AI 推理算力成本。",
        "what_it_does_en": "Uses LLMs to speed up hardware design verification and reduce future AI inference costs.",
        "who_cares": "芯片产业链观察者与 AI 行业从业者",
        "limitations": "属中长期底层算力合作，短期内不会立刻体现在普通聊天产品界面上。",
        "limitations_en": "Medium-to-long-term R&D milestone without immediate consumer UI changes.",
        "source_name": "Hacker News / 科技媒体",
        "source_url": "https://openai.com/",
        "is_open_source": False,
    },
    {
        "id": "ai_xai_grok3_colossus",
        "date": "2026-11-18",
        "company_id": "xai",
        "company_name": "xAI / Grok",
        "region": "海外",
        "category": "旗舰推理与超算",
        "category_en": "Reasoning & Compute",
        "title": "xAI 持续扩展 Grok 推理与实时搜索能力，依托 Colossus 万卡集群加速迭代",
        "title_en": "xAI scales Grok reasoning and live search on the Colossus supercluster",
        "what_it_does": "提供深度推理（Think）与实时 X/全网检索分析，面向代码、科研与实时新闻场景。",
        "what_it_does_en": "Delivers extended reasoning and live search across coding, research, and breaking news.",
        "who_cares": "需要实时信息检索与强推理能力的用户与 API 开发者",
        "source_name": "xAI Official",
        "source_url": "https://x.ai/news",
        "is_open_source": False,
    },
    {
        "id": "ai_bytedance_seed_suite",
        "date": "2026-11-18",
        "company_id": "bytedance_doubao",
        "company_name": "字节豆包 (Seed)",
        "region": "国内",
        "category": "多模态与视频生成",
        "category_en": "Multimodal & Video",
        "title": "字节 ByteDance Seed 迭代豆包大模型、Seedance 视频与 UI-TARS 桌面 Agent",
        "title_en": "ByteDance Seed advances Doubao models, Seedance video generation, and UI-TARS",
        "what_it_does": "覆盖高性价比企业 API（火山引擎方舟）、开源 GUI 操作 Agent 与影视级视频生成。",
        "what_it_does_en": "Provides cost-efficient enterprise APIs, open-source GUI agents, and video synthesis.",
        "who_cares": "国内应用开发者、多媒体创作者与自动化 Agent 研究者",
        "source_name": "ByteDance Seed",
        "source_url": "https://seed.bytedance.com/",
        "is_open_source": True,
    },
    {
        "id": "ai_zhipu_glm_open",
        "date": "2026-11-18",
        "company_id": "zhipu_glm",
        "company_name": "智谱 AI (GLM)",
        "region": "国内",
        "category": "开源与编程推理",
        "category_en": "Open Weights & Coding",
        "title": "智谱 AI 推进 GLM 深度推理与开源权重矩阵，强化代码与 Agent 工具调用",
        "title_en": "Zhipu AI expands GLM reasoning checkpoints and open-weight coding tool use",
        "what_it_does": "兼顾开源私有化部署（THUDM / zai-org）与 MaaS 平台工具调用工作流。",
        "what_it_does_en": "Supports self-hosted open-weight GLM deployments and structured agent tool use.",
        "who_cares": "政企私有化团队与中文代码助手开发者",
        "source_name": "Zhipu AI",
        "source_url": "https://github.com/zai-org",
        "is_open_source": True,
    },
    {
        "id": "ai_minimax_hailuo",
        "date": "2026-11-18",
        "company_id": "minimax",
        "company_name": "MiniMax / 海螺",
        "region": "国内",
        "category": "文本与音视频多模态",
        "category_en": "Reasoning & Media",
        "title": "MiniMax 持续更新开放权重长上下文模型与海螺视频、高拟真语音合成栈",
        "title_en": "MiniMax updates open-weight long-context models alongside Hailuo video & speech",
        "what_it_does": "主打超长上下文推理、海螺视频生成与多语种低延迟语音合成 API。",
        "what_it_does_en": "Focuses on long-context reasoning, Hailuo video generation, and low-latency speech synthesis.",
        "who_cares": "内容创作、出海应用与多模态交互开发者",
        "source_name": "MiniMax Official",
        "source_url": "https://www.minimaxi.com/",
        "is_open_source": True,
    },
    {
        "id": "ai_baidu_ernie_open",
        "date": "2026-11-18",
        "company_id": "baidu_ernie",
        "company_name": "百度文心 (ERNIE)",
        "region": "国内",
        "category": "推理与开源生态",
        "category_en": "Reasoning & Ecosystem",
        "title": "百度文心 ERNIE 与飞桨持续优化深度思考 X1 与多模态产业部署成本",
        "title_en": "Baidu ERNIE and PaddlePaddle lower inference costs across reasoning and multimodal tasks",
        "what_it_does": "结合千帆平台与飞桨推理优化，降低企业长文本与检索增强（RAG）调用成本。",
        "what_it_does_en": "Pairs Qianfan managed endpoints with PaddlePaddle inference optimization for enterprise RAG.",
        "who_cares": "国内搜索营销、知识库检索与飞桨生态开发者",
        "source_name": "Baidu ERNIE",
        "source_url": "https://yiyan.baidu.com/",
        "is_open_source": True,
    },
    {
        "id": "ai_huawei_openpangu",
        "date": "2026-11-18",
        "company_id": "huawei_pangu",
        "company_name": "华为盘古 / 昇腾",
        "region": "国内",
        "category": "国产算力与行业模型",
        "category_en": "Ascend Silicon & Enterprise",
        "title": "华为盘古推进 openPangu 开源权重与昇腾 Ascend NPU 全栈推理适配",
        "title_en": "Huawei Pangu expands openPangu checkpoints and native Ascend NPU inference",
        "what_it_does": "面向国产昇腾算力集群提供从底层 CANN 算子到行业大模型的自主可控方案。",
        "what_it_does_en": "Delivers full-stack sovereign inference from CANN kernels to enterprise Pangu weights.",
        "who_cares": "国产算力基础设施团队与能源、政务、制造数字化工程师",
        "source_name": "Huawei Cloud",
        "source_url": "https://www.huaweicloud.com/product/pangu.html",
        "is_open_source": True,
    },
    {
        "id": "ai_mistral_codestral",
        "date": "2026-11-18",
        "company_id": "mistral",
        "company_name": "Mistral AI",
        "region": "海外",
        "category": "欧洲开源与代码模型",
        "category_en": "Open Weights & Coding",
        "title": "Mistral AI 持续推进 Mistral Large、Codestral 与 Apache 2.0 端侧开源矩阵",
        "title_en": "Mistral AI expands Mistral Large, Codestral, and Apache 2.0 edge open weights",
        "what_it_does": "提供高性价比多语种商用 API 与合规透明的欧洲开源中小尺寸模型。",
        "what_it_does_en": "Provides multilingual enterprise APIs alongside permissive Apache 2.0 compact weights.",
        "who_cares": "注重本地合规、代码补全与低延迟推理的全球开发者",
        "source_name": "Mistral AI",
        "source_url": "https://mistral.ai/news",
        "is_open_source": True,
    },
    {
        "id": "ai_apple_foundation_mlx",
        "date": "2026-11-18",
        "company_id": "apple_ai",
        "company_name": "Apple Intelligence",
        "region": "海外",
        "category": "端侧隐私与框架",
        "category_en": "On-Device & MLX",
        "title": "Apple 深化端侧基础模型与 MLX 框架在 Apple Silicon 本地的低功耗推理",
        "title_en": "Apple advances on-device Foundation Models and MLX inference on Apple Silicon",
        "what_it_does": "让 Mac / iPhone / iPad 在统一内存上高带宽运行本地大模型并兼顾私有云计算隐私。",
        "what_it_does_en": "Enables high-bandwidth local LLM inference via MLX and privacy-preserving Private Cloud Compute.",
        "who_cares": "Mac 本地模型玩家与 iOS/macOS 原生应用开发者",
        "source_name": "Apple ML Research",
        "source_url": "https://machinelearning.apple.com/",
        "is_open_source": True,
    },
    {
        "id": "ai_amazon_nova_bedrock",
        "date": "2026-11-18",
        "company_id": "amazon_aws",
        "company_name": "Amazon AI (Nova)",
        "region": "海外",
        "category": "云基础设施与企业模型",
        "category_en": "Cloud & Bedrock",
        "title": "Amazon Nova 系列联合 AWS Bedrock 提供多模型统一托管与低延迟多模态能力",
        "title_en": "Amazon Nova and AWS Bedrock unify multi-model enterprise inference and multimodal routing",
        "what_it_does": "在单一云平台内串联 Nova、Claude 与开源权重部署、评测与企业权限治理。",
        "what_it_does_en": "Unifies Nova, Claude, and open-weight hosting with AWS IAM governance.",
        "who_cares": "AWS 企业架构师与高并发云端 AI 服务团队",
        "source_name": "AWS AI Blog",
        "source_url": "https://aws.amazon.com/bedrock/",
        "is_open_source": False,
    },
    {
        "id": "ai_perplexity_sonar",
        "date": "2026-11-18",
        "company_id": "perplexity",
        "company_name": "Perplexity AI",
        "region": "海外",
        "category": "AI 实时搜索与研究",
        "category_en": "AI Search & Research",
        "title": "Perplexity 持续迭代 Sonar 实时检索 API 与深度研究引用核验工作流",
        "title_en": "Perplexity iterates Sonar grounded-search APIs and Deep Research citation workflows",
        "what_it_does": "将实时网页抓取与多步研究报告合并，直接输出带原始出处链接的可核验结论。",
        "what_it_does_en": "Combines live web grounding with multi-step research synthesis and verifiable citations.",
        "who_cares": "投研分析、情报检索与需要实时联网 API 的开发者",
        "source_name": "Perplexity Blog",
        "source_url": "https://www.perplexity.ai/hub",
        "is_open_source": False,
    },
    {
        "id": "ai_cursor_composer_ide",
        "date": "2026-11-18",
        "company_id": "cursor",
        "company_name": "Cursor (Anysphere)",
        "region": "海外",
        "category": "AI 原生编程 IDE",
        "category_en": "AI Coding IDE",
        "title": "Cursor 强化 Composer 跨文件重构 Agent 与自研低延迟 Tab 代码预测模型",
        "title_en": "Cursor upgrades Composer multi-file agent workflows and low-latency Tab autocomplete",
        "what_it_does": "把代码库索引、后台命令执行与多步 Diff 编辑集成在统一桌面 IDE 工作流中。",
        "what_it_does_en": "Integrates codebase indexing, terminal execution, and multi-file agent diffs in one IDE.",
        "who_cares": "全栈软件工程师与追求高研发效率的技术团队",
        "source_name": "Cursor Changelog",
        "source_url": "https://www.cursor.com/changelog",
        "is_open_source": False,
    },
    {
        "id": "ai_stability_open_media",
        "date": "2026-11-18",
        "company_id": "stability",
        "company_name": "Stability AI",
        "region": "海外",
        "category": "视觉与音频生成",
        "category_en": "Image & Audio Generation",
        "title": "Stability AI 持续维护 Stable Diffusion 与 Stable Audio 本地可控视觉/音频生成生态",
        "title_en": "Stability AI maintains Stable Diffusion and Stable Audio controllable local media workflows",
        "what_it_does": "配合 ComfyUI 等节点化工作流，在消费级显卡上实现精确可控的图像、纹理与音效生成。",
        "what_it_does_en": "Powers node-based ComfyUI workflows for controllable local image, texture, and audio generation.",
        "who_cares": "视觉设计师、游戏资产美术与本地 AIGC 创作者",
        "source_name": "Stability AI",
        "source_url": "https://stability.ai/news",
        "is_open_source": True,
    },
]


FIRST_HAND_SOURCE_IDS = {
    "huggingface-hub",
    "hf-daily-papers",
    "github-releases",
    "rss-google-ai-blog",
    "rss-deepmind-blog",
    "rss-openai-news",
    "rss-hf-blog",
    "rss-nvidia-blog",
    "rss-github-changelog",
    "arxiv-api",
}

FIRST_HAND_URL_HOSTS = (
    "huggingface.co",
    "github.com",
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "blog.google",
    "deepseek.com",
    "hunyuan.tencent.com",
    "qwenlm.github.io",
    "qwen.ai",
    "moonshot.cn",
    "zhipuai.cn",
    "bigmodel.cn",
    "nvidianews.nvidia.com",
    "blogs.nvidia.com",
    "ai.meta.com",
    "mistral.ai",
    "x.ai",
    "seed.bytedance.com",
    "github.blog",
    "microsoft.com/en-us/research",
    "cursor.com",
    "perplexity.ai",
    "stability.ai",
    "machinelearning.apple.com",
    "security.apple.com",
    "aws.amazon.com",
    "huaweicloud.com",
    "yiyan.baidu.com",
    "cloud.baidu.com",
    "nio.com",
)


def is_first_hand_ai_source(source_id: str = "", source_name: str = "", url: str = "") -> bool:
    sid = str(source_id or "").strip().lower()
    if sid in FIRST_HAND_SOURCE_IDS:
        return True
    sname = str(source_name or "").lower()
    if any(
        k in sname
        for k in (
            "huggingface",
            "github releases",
            "openai",
            "anthropic",
            "deepmind",
            "google ai",
            "nvidia 官方",
            "一手",
            "官方博客",
            "官方模型",
            "蔚来官方",
            "腾讯混元官方",
            "zhipu ai 官方",
            "qwen 官方",
        )
    ):
        return True
    lower_url = str(url or "").lower()
    return any(host in lower_url for host in FIRST_HAND_URL_HOSTS)


def normalize_ai_timestamp(raw_ts: Any, fallback_iso: str) -> str:
    txt = str(raw_ts or "").strip()
    if not txt:
        return str(fallback_iso or "")[:19] + "+08:00" if len(str(fallback_iso or "")) >= 19 else str(fallback_iso or "")[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt):
        return txt
    try:
        from datetime import datetime, timezone, timedelta
        bj = timezone(timedelta(hours=8))
        norm = txt.replace("Z", "+00:00").replace(" ", "T", 1) if " " in txt and "T" not in txt else txt.replace("Z", "+00:00")
        dt = datetime.fromisoformat(norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=bj)
        else:
            dt = dt.astimezone(bj)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    except Exception:
        return txt[:19] if len(txt) >= 19 else txt[:10]


AI_NOISE_RE = re.compile(
    r"(?:回购股份|减持股份|增持股份|质押股份|股份回购|分红派息|限售股解禁|股票交易异常波动|年度股东大会|董事会决议公告|可转债|中标公告|业绩快报|成份股|指数纳入|调入.*股|港股通|"
    r"black friday|geforce now|win11.*copilot|windows\s*11.*copilot|强制集成.*copilot|"
    r"小鹏|理想汽车|小米汽车|车机|智能座舱|购车金融|"
    r"开源鸿蒙|openharmony|harmonyos|南水北调|水利|水文|国家水网|调水工程|天河.*(?:工程|调水|水文|水网)|"
    r"影石|insta360|大疆|麦克风|耳机|相机|固件升级|充电宝|路由器|显示器|键盘|鼠标|tech outages.*y2k|outages.*ai agent style|"
    r"套餐|买赠|优惠券|代金券|促销|折扣|限免|会员价|小米\s*mimo.*套餐|mimo.*套餐|学生教师优惠|9\.9元|元/月|优惠上线|"
    r"调查问卷|大肥鱼|chatterfly|neonclipping|youtube\s*shorts.*剪辑|输入法.*内测|艺术中心.*抗议|抗议.*ai|提示词技巧|回答更简短|透明度评分低于|透明度低于|"
    r"演唱会|剧场版|小雪节气|长城坦克|坦克\d+|"
    r"国家中医药管理局|中医药|认证中心|未与任何.{0,6}合作|亦未开展测评|辟谣通告|严正声明|"
    r"投资者是否应|是否值得购买|值得买入吗|\bspcx\b|目标价|股价表现|空头机构|估值泡沫|"
    r"微信香港钱包|微信支付|支付宝|信用卡|消费券|手游|主机游戏|steam|帮信罪|刑事拘留)",
    re.I,
)

_FOREIGN_SUBJECT_BLOCK_RE = re.compile(
    r"(?:signal|telegram|whatsapp|firefox|safari|微信|浏览器).{0,26}(?:屏蔽|阻止|阻断|禁用|拦截|限制|拒绝)"
    r".{0,26}(?:截图|截屏|读取|读屏|siri|gemini|claude|gpt|copilot|ai)",
    re.I,
)

_EXPLICIT_OPEN_SOURCE_RE = re.compile(
    r"(?:开源|开放权重|开放完整权重|\bopen[- ]?source\b|\bopen[- ]?weights?\b|"
    r"apache[- ]?2\.0|apache\s+license|\bmit\s*(?:license|协议)\b|\bbsd[- ]?3\b|"
    r"\bllama\.cpp\b|\bvllm\b|\bsglang\b|\bollama\b|comfyui|diffusers|"
    r"openpangu|diffusiongemma|openelm|r1-1776|开源生态|开源模型权重)",
    re.I,
)

_CLOSED_ONLY_SIGNAL_RE = re.compile(
    r"(?:gpt-6|gpt-5|claude\s*fable|claude\s*mythos|claude\s*4|gemini\s*4|genie\s*4|sora\b|"
    r"copilot\s*集成|反蒸馏|封禁账户|解散.*团队|网络安全诉讼|诉讼|提示词|评测.*简短|pcc\s*隐私云)",
    re.I,
)


def is_foreign_subject_blocked(title: str, summary: str = "") -> bool:
    """Block 3rd-party software stories (e.g. Signal blocking Gemini screen capture) from posing as lab R&D."""
    return bool(_FOREIGN_SUBJECT_BLOCK_RE.search(f"{title} {summary}"))


def detect_is_open_source(
    title: str,
    summary: str = "",
    url: str = "",
    company_id: str = "",
    source_id: str = "",
) -> bool:
    """Accurate open-source detector: NEVER matches 'open' inside 'OpenAI'."""
    t_no_openai = re.sub(r"open\s*ai", " ", f"{title} {summary}", flags=re.I)
    lower_url = str(url or "").strip().lower()
    sid = str(source_id or "").strip().lower()

    has_explicit_open = bool(_EXPLICIT_OPEN_SOURCE_RE.search(t_no_openai))
    is_open_repo_url = bool(
        re.search(r"github\.com/[^/\s]+/[^/\s]+|huggingface\.co/[^/\s]+/[^/\s]+", lower_url)
    )
    if company_id in {"openai", "anthropic"}:
        if _CLOSED_ONLY_SIGNAL_RE.search(t_no_openai) and not has_explicit_open:
            return False
        return bool(
            has_explicit_open
            or re.search(r"github\.com/(?:openai|anthropics)/[^/\s]+", lower_url)
        )

    if _CLOSED_ONLY_SIGNAL_RE.search(t_no_openai) and not has_explicit_open:
        return False

    if sid in {"github-releases", "huggingface-hub"}:
        return True
    if is_open_repo_url and any(k in t_no_openai.lower() for k in ("权重", "weights", "model", "cli", "sdk", "inference", "repo", "release")):
        return True
    return has_explicit_open


_DIM_LABELS: Dict[str, Tuple[str, str]] = {
    "flagship_release": ("🚀 旗舰模型发布", "Flagship Model"),
    "research_breakthrough": ("🧠 算法与科研突破", "Research & Math"),
    "api_agent_eng": ("🛠️ API 与 Agent 工程", "API & Agent Eng"),
    "open_source_eco": ("🔓 开源权重与生态", "Open Source"),
    "commercial_governance": ("⚖️ 商业化与安全治理", "Governance & Commercial"),
}


def classify_ai_milestone_dim(
    title: str,
    summary: str = "",
    *,
    is_open_source: bool = False,
    category: str = "",
) -> Tuple[str, str, str]:
    """Classify any AI milestone into the 5 canonical evolution dimensions."""
    blob = f"{title} {summary} {category}".lower()
    if any(k in blob for k in ("反蒸馏", "隐私", "安全治理", "pcc", "诉讼", "融资", "ipo", "商业化", "商用", "hebbia", "定价", "封禁")):
        dim = "commercial_governance"
    elif any(k in blob for k in ("黎曼", "形式化", "lean", "密码分析", "nist", "medchembench", "基准", "benchmark", "论文", "arxiv", "世界模型", "genie 4", "nwm 3.0", "科研", "算法")):
        dim = "research_breakthrough"
    elif any(k in blob for k in ("tool retrieval", "工具检索", "agent", "智能体", "sdk", "api", "copilot", "ide", "composer", "claude code", "mcp", "rag", "bedrock", "sonar", "工作流", "ui-tars")):
        dim = "api_agent_eng"
    elif is_open_source or any(k in blob for k in ("开源", "open-source", "open weights", "apache", "mit", "vllm", "llama.cpp", "sglang", "ollama", "hugging face", "github", "权重")):
        dim = "open_source_eco"
    else:
        dim = "flagship_release"
    zh, en = _DIM_LABELS[dim]
    return dim, zh, en
AI_KW_RE = re.compile(
    r"(?:大模型|语言模型|多模态模型|推理模型|基础模型|世界模型.*(?:genie|cosmos)|生成式|开源模型|开源权重|"
    r"\bai\b|\bllm\b|gemini|neon|carbon|hydrogen|claude|fable|mythos|gpt|astra|grok|xai|"
    r"qwen|千问|通义|kimi|混元|hy4|workbuddy|元宝|豆包|seedance|manus|minimax|智谱|glm|文心|ernie|盘古|openpangu|"
    r"mistral|llama|deepseek|深度求索|diffusion|vllm|sglang|llama\.cpp|ollama|hugging\s*face|\bmcp\b|"
    r"coding\s*agent|ai\s*agent|智能体|电脑操控|计算机控制|computer use|openai|anthropic|deepmind|cursor|perplexity|强化学习)",
    re.I,
)
AI_RELEASE_RE = re.compile(
    r"(?:release|launch|announc|introduc|open[- ]source|weights|rollout|available|发布|开源|上线|推出|升级|开放|融资|千亿|百亿|突破|操控|preview|neon|astra|fable|mythos|qwen4|deepseek|kimi|genie|gemma|workbuddy|hunyuan|grok)",
    re.I,
)

_FIRST_PARTY_HOST_LAB: Tuple[Tuple[str, str], ...] = (
    ("deepmind.google", "google"),
    ("blog.google", "google"),
    ("ai.google.dev", "google"),
    ("ai.google", "google"),
    ("anthropic.com", "anthropic"),
    ("openai.com", "openai"),
    ("x.ai", "xai"),
    ("deepseek.com", "deepseek"),
    ("hunyuan.tencent.com", "tencent_hunyuan"),
    ("qwen.ai", "qwen"),
    ("qwenlm.github.io", "qwen"),
    ("moonshot.cn", "kimi"),
    ("zhipuai.cn", "zhipu_glm"),
    ("bigmodel.cn", "zhipu_glm"),
    ("z.ai", "zhipu_glm"),
    ("minimaxi.com", "minimax"),
    ("mistral.ai", "mistral"),
    ("perplexity.ai", "perplexity"),
    ("cursor.com", "cursor"),
    ("stability.ai", "stability"),
    ("ai.meta.com", "meta"),
    ("blogs.nvidia.com", "nvidia"),
    ("nvidianews.nvidia.com", "nvidia"),
    ("machinelearning.apple.com", "apple_ai"),
)

_CODE_ORG_LAB: Tuple[Tuple[str, str], ...] = (
    ("qwen", "qwen"),
    ("qwenlm", "qwen"),
    ("deepseek-ai", "deepseek"),
    ("moonshotai", "kimi"),
    ("tencent", "tencent_hunyuan"),
    ("xai-org", "xai"),
    ("google-deepmind", "google"),
    ("google", "google"),
    ("anthropics", "anthropic"),
    ("openai", "openai"),
    ("meta-llama", "meta"),
    ("facebookresearch", "meta"),
    ("mistralai", "mistral"),
    ("nvidia", "nvidia"),
    ("bytedance-seed", "bytedance_doubao"),
    ("bytedance", "bytedance_doubao"),
    ("thudm", "zhipu_glm"),
    ("zai-org", "zhipu_glm"),
    ("minimax-ai", "minimax"),
    ("paddlepaddle", "baidu_ernie"),
    ("apple", "apple_ai"),
    ("stability-ai", "stability"),
    ("microsoft", "microsoft"),
)

_CONGLOMERATE_AI_CTX_RE = re.compile(
    r"(?:模型|大模型|\bai\b|\bllm\b|智能体|agent|开源|权重|多模态|推理|编程|copilot|混元|hy4|workbuddy|"
    r"元宝|千问|qwen|通义|万相|豆包|seed|盘古|openpangu|昇腾|文心|ernie|gemini|gemma|deepmind|genie|"
    r"genie\s*\d|apple intelligence|coreml|mlx|bedrock|nova|nemotron|cosmos|phi-\d)",
    re.I,
)

for _lab_entry in _LAB_CATALOG:
    _v9_meta = LAB_V9_METADATA.get(_lab_entry["company_id"]) or {}
    if _v9_meta.get("flagship_model"):
        _lab_entry["flagship_model"] = _v9_meta["flagship_model"]
    if _v9_meta.get("model_lineage"):
        _lab_entry["model_lineage"] = list(_v9_meta["model_lineage"])

_LAB_META_BY_ID: Dict[str, Dict[str, Any]] = {spec["company_id"]: spec for spec in _LAB_CATALOG}


def _match_url_first_party_lab(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or "").lower().removeprefix("www.")
        path = (parsed.path or "").lower()
    except Exception:
        return None
    if not host or host in {"news.google.com", "google.com"}:
        return None
    for dom, cid in _FIRST_PARTY_HOST_LAB:
        if host == dom or host.endswith("." + dom):
            return cid
    if host in {"huggingface.co", "github.com"}:
        first_seg = next((seg for seg in path.split("/") if seg), "")
        for org_prefix, cid in _CODE_ORG_LAB:
            if first_seg == org_prefix:
                return cid
    return None


def _lab_result(cid: str) -> tuple[str, str, str]:
    spec = _LAB_META_BY_ID.get(cid) or _LAB_META_BY_ID["indie_opensource"]
    return spec["company_id"], spec["company_name"], spec["region"]


def _match_lab_signature(txt_low: str, xai_aliases: Tuple[str, ...]) -> Optional[str]:
    if any(re.search(rf"(?<![a-z0-9]){re.escape(al)}(?![a-z0-9])", txt_low) for al in xai_aliases):
        return "xai"
    if any(k in txt_low for k in ("anthropic", "claude")):
        return "anthropic"
    if any(k in txt_low for k in ("openai", "gpt-", "chatgpt", "sora", "codex")):
        return "openai"
    if any(k in txt_low for k in ("deepseek", "深度求索")):
        return "deepseek"
    if any(k in txt_low for k in ("kimi", "moonshot", "月之暗面")):
        return "kimi"
    if any(k in txt_low for k in ("qwen", "千问", "通义", "万相")):
        return "qwen"
    if any(k in txt_low for k in ("混元", "hunyuan", "workbuddy", "腾讯元宝", "hy4")):
        return "tencent_hunyuan"
    if any(k in txt_low for k in ("豆包", "doubao", "seedance", "bytedance seed", "ui-tars")):
        return "bytedance_doubao"
    if any(k in txt_low for k in ("智谱", "zhipu", "glm-4", "glm-5", "glm-z", "chatglm", "bigmodel")):
        return "zhipu_glm"
    if any(k in txt_low for k in ("minimax", "海螺ai", "海螺视频", "hailuo")):
        return "minimax"
    if any(k in txt_low for k in ("文心", "ernie")):
        return "baidu_ernie"
    if any(k in txt_low for k in ("openpangu", "盘古大模型", "华为盘古", "昇腾", "ascend")):
        return "huawei_pangu"
    if any(k in txt_low for k in ("mistral", "codestral", "pixtral", "mixtral")):
        return "mistral"
    if "perplexity" in txt_low:
        return "perplexity"
    if re.search(r"(?<![a-z0-9])cursor(?![a-z0-9])|anysphere", txt_low):
        return "cursor"
    if any(k in txt_low for k in ("stability ai", "stable diffusion", "stable video", "stable audio")):
        return "stability"
    if any(k in txt_low for k in ("gemini", "gemma", "deepmind", "project genie", "genie 4", "diffusiongemma")):
        return "google"
    if any(k in txt_low for k in ("nemotron", "cosmos", "omniverse", "tensorrt", "blackwell", "rubin")):
        return "nvidia"
    if any(k in txt_low for k in ("llama.cpp", "ggml", "ollama", "vllm", "sglang", "comfyui", "open-webui", "dify", "langchain")):
        return "indie_opensource"
    if any(k in txt_low for k in ("phi-4", "phi4", "copilot", "azure ai")):
        return "microsoft"
    if any(k in txt_low for k in ("llama", "meta ai", "metaai")):
        return "meta"
    if any(k in txt_low for k in ("apple intelligence", "openelm", "coreml", "ferret")):
        return "apple_ai"
    if any(k in txt_low for k in ("amazon nova", "aws bedrock", "bedrock")):
        return "amazon_aws"
    return None


def _infer_company(title: str, url: str = "", source_name: str = "") -> tuple[str, str, str]:
    # 1. Subject-first inspection so comparison titles (e.g. "GPT-6.2 ... 透明度低于Claude") attribute to primary subject!
    clean_src = "" if "google news" in (source_name or "").lower() else (source_name or "")
    subject_clause = re.split(r"(?:，|,|；|;|\bvs\.?\b|\bversus\b|低于|高于|相比|对比|超越|不如)", str(title or ""), maxsplit=1)[0].strip()
    xai_aliases = tuple(ENTITY_BY_ID["ent_xai"].aliases) if "ent_xai" in ENTITY_BY_ID else ("xai", "x.ai", "grok")

    if subject_clause:
        subj_cid = _match_lab_signature(subject_clause.lower(), xai_aliases)
        if subj_cid:
            return _lab_result(subj_cid)

    t = f"{title} {clean_src}".lower()
    has_ai_ctx = bool(_CONGLOMERATE_AI_CTX_RE.search(t))

    full_cid = _match_lab_signature(t, xai_aliases)
    if full_cid:
        return _lab_result(full_cid)

    # Conglomerate names matched ONLY when AI/model context is present
    if has_ai_ctx:
        if any(k in t for k in ("谷歌",)) or re.search(r"(?<![a-z0-9])google(?![a-z0-9])", t):
            return _lab_result("google")
        if any(k in t for k in ("微软", "microsoft")):
            return _lab_result("microsoft")
        if any(k in t for k in ("英伟达", "nvidia")):
            return _lab_result("nvidia")
        if re.search(r"(?<![a-z0-9])meta(?![a-z0-9])", t):
            return _lab_result("meta")
        if any(k in t for k in ("阿里", "alibaba")):
            return _lab_result("qwen")
        if any(k in t for k in ("腾讯", "tencent")):
            return _lab_result("tencent_hunyuan")
        if any(k in t for k in ("字节", "bytedance", "火山引擎")):
            return _lab_result("bytedance_doubao")
        if any(k in t for k in ("百度", "baidu")):
            return _lab_result("baidu_ernie")
        if any(k in t for k in ("华为", "huawei")):
            return _lab_result("huawei_pangu")
        if any(k in t for k in ("苹果", "apple")):
            return _lab_result("apple_ai")
        if any(k in t for k in ("亚马逊", "amazon", "aws")):
            return _lab_result("amazon_aws")

    # 2. First-party URL host/org fallback (safe: excludes news.google.com and aggregators)
    url_lab = _match_url_first_party_lab(url)
    if url_lab:
        return _lab_result(url_lab)

    return _lab_result("indie_opensource")


_BOILERPLATE_WHAT_RE = re.compile(
    r"(?:前沿 AI 模型或产品能力更新：关注核心推理性能提升|"
    r"大模型安全、隐私合规与防泄漏动态|大模型安全与对抗评估进展|"
    r"领域专项评测基准发布：用于量化评估|AI 科研与生命科学模型进展：面向生物酶|"
    r"前沿 AI 算法与数学推理突破：验证模型|开源模型与开发者生态进展：展现开放权重|"
    r"AI 编程与智能体（Agent）工具进展：支持工程代码|"
    r"大模型资本与算力投入动态：反映前沿实验室|下一代模型路线图与发布传闻核验|"
    r"资本战略与产业融资动态（来源：|前沿 AI 模型研究与开发生态动态|实验室官方一线研究动态（来源：)"
)


def _infer_what_it_does_zh(title: str, summary: str, *, is_tool_release: bool = False) -> str:
    from .dedup import strip_raw_urls_and_domain_tails, title_similarity

    clean_sum = strip_raw_urls_and_domain_tails(re.sub(r"\s+", " ", str(summary or "").strip()))
    clean_sum = re.sub(r"^【[^】]{4,80}】\s*", "", clean_sum).strip()
    clean_sum = re.sub(r"\s*[A-Za-z0-9-]+\.(?:ai|com|org|io|net|cn|co|dev|app)\s*$", "", clean_sum, flags=re.I).strip()
    clean_sum = re.sub(r"\s+(?:新华网|人民网|央视新闻|环球网|财联社|Reuters|Bloomberg)$", "", clean_sum).strip()
    clean_title = strip_raw_urls_and_domain_tails(re.sub(r"\s+", " ", str(title or "").strip()))
    if _BOILERPLATE_WHAT_RE.search(clean_sum):
        clean_sum = ""

    norm_sum = re.sub(r"[\W_]+", "", clean_sum).lower()
    norm_title = re.sub(r"[\W_]+", "", clean_title).lower()
    cjk_count = sum(1 for ch in clean_sum if "\u4e00" <= ch <= "\u9fff")
    is_echo = (
        not clean_sum
        or clean_sum == clean_title
        or (norm_title and norm_sum == norm_title)
        or (len(norm_title) >= 8 and norm_sum.startswith(norm_title[:12]))
        or (len(clean_title) >= 10 and clean_sum.startswith(clean_title[:16]))
        or (len(clean_sum) >= 8 and title_similarity(clean_sum, clean_title) >= 0.60)
    )
    if not is_echo and cjk_count >= 8:
        return (clean_sum[:118] + "…") if len(clean_sum) > 118 else clean_sum

    t = f"{clean_title} {clean_sum}".lower()
    if any(k in t for k in ("隐私泄露", "隐私数据", "零数据保留", "诱饵请求", "反蒸馏", "抗蒸馏", "distillation")):
        return "大模型安全、隐私合规与防泄漏动态：聚焦零数据保留机制校验、抗蒸馏防护与调用链审计。"
    if is_tool_release or re.search(r"(?:agent\s*sdk|工具套件|workflow\s*harness|cli\s*tool)", t):
        if any(k in t for k in ("vllm", "llama.cpp", "ollama", "sglang", "推理引擎", "inference engine")):
            return "开源本地/服务器推理加速工具：帮开发者更快、更省显存地部署和运行开源大模型。"
        if re.search(r"(?:agent\s*sdk|工具套件|workflow\s*harness|cli\s*tool)", t):
            return "AI 编程与智能体（Agent）工具进展：支持工程代码协同、开发脚手架测试与自动化多步骤任务执行。"
    return ""


# Synonym-group clusters so ZH & EN variants of the exact same event collapse (e.g. "OpenAI 反蒸馏" == "Combatting adversarial distillation")
_AI_TOPIC_CONCEPT_CLUSTERS = (
    (("openai",), ("蒸馏", "distill")),
    (("openai",), ("medchembench", "化学基准")),
    (("anthropic", "claude"), ("黎曼", "riemann")),
    (("anthropic",), ("sdk",)),
    (("gemini", "google", "谷歌"), ("工具检索", "tool retrieval", "tool search")),
    (("gemini 4 neon", "gemini4 neon", "gemini 4「neon"), ("neon", "氖")),
    (("genie 4", "project genie"), ("世界模型", "world model")),
    (("minimax",), ("密码分析", "nist", "cryptanalysis")),
    (("混元", "hunyuan", "tencent"), ("hy4", "混元4")),
    (("智谱", "zhipu", "glm"), ("glm-5.3", "glm-5.4", "glm-5.5")),
    (("workbuddy",), ("电脑操控", "桌面", "computeruse")),
    (("win11", "windows11"), ("copilot",)),
    (("deepseek",), ("千亿",)),
    (("零数据保留", "诱饵请求", "隐私泄露", "隐私漏洞"), ("隐私", "zero", "诱饵")),
)


def is_similar_ai_release(
    title_a: str,
    url_a: str,
    title_b: str,
    url_b: str,
    company_id_a: str = "",
    company_id_b: str = "",
) -> bool:
    """Detect duplicate AI milestones across different publishers/languages/phrasings."""
    ua = str(url_a or "").strip().lower().rstrip("/")
    ub = str(url_b or "").strip().lower().rstrip("/")
    if ua and ub and ua == ub:
        try:
            pa = urlparse(ua)
            # Only treat identical URL as same article when it points to a specific article path (not bare root/index URLs like /news or /)
            if len([seg for seg in (pa.path or "").split("/") if seg]) >= 2 or pa.fragment or pa.query:
                return True
        except Exception:
            pass
    raw_a = str(title_a or "").lower()
    raw_b = str(title_b or "").lower()
    for grp1, grp2 in _AI_TOPIC_CONCEPT_CLUSTERS:
        a_hit = any(k in raw_a for k in grp1) and any(k in raw_a for k in grp2)
        b_hit = any(k in raw_b for k in grp1) and any(k in raw_b for k in grp2)
        if a_hit and b_hit:
            return True
    na = re.sub(r"^【[^】]{1,24}】\s*", "", str(title_a or "").strip())
    nb = re.sub(r"^【[^】]{1,24}】\s*", "", str(title_b or "").strip())
    na = re.sub(r"[\s\-_·:：,，.。!！?？()（）\[\]【】'\"“”‘’/]+", "", na).lower()
    nb = re.sub(r"[\s\-_·:：,，.。!！?？()（）\[\]【】'\"“”‘’/]+", "", nb).lower()
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 12 and len(nb) >= 12 and (na.startswith(nb[:16]) or nb.startswith(na[:16])):
        return True
    same_org = bool(company_id_a and company_id_b and company_id_a == company_id_b)
    thresh = 0.36 if same_org else 0.44
    if len(na) >= 10 and len(nb) >= 10:
        bga = {na[i : i + 2] for i in range(len(na) - 1)}
        bgb = {nb[i : i + 2] for i in range(len(nb) - 1)}
        union = bga | bgb
        if union and (len(bga & bgb) / len(union)) >= thresh:
            return True
    return False


_AI_SEARCH_CACHE_TTL_SEC = 4 * 3600  # Reuse weekly Gemini Search grounding across 4h window


def _query_gemini_google_search_ai_weekly(base_dir: Path | str = ".") -> List[Dict[str, Any]]:
    """Opt-in Gemini + Google Search Grounding (disabled by default to preserve free API quotas)."""
    if os.environ.get("ENABLE_GEMINI_AI_SEARCH", "0").strip() != "1":
        return []
    root = Path(base_dir)
    cache_path = root / "data" / "ai_radar_search_cache.json"
    cached = load_json_if_exists(cache_path, default={}) or {}
    if isinstance(cached, dict) and isinstance(cached.get("items"), list):
        age_sec = time.time() - float(cached.get("ts") or 0)
        if age_sec < _AI_SEARCH_CACHE_TTL_SEC and cached["items"]:
            return cached["items"]

    today = now_shanghai().strftime("%Y-%m-%d")
    prompt = (
        f"今天是 {today}。请通过 Google 搜索整理最近 7 天（尤其过去 24–72 小时内最新刚发布）全球与中国最重磅的 8–12 条 AI 模型与开源项目进展"
        "（务必重点搜索并核查：Google Gemini、OpenAI GPT-6.2、Anthropic Claude、xAI Grok、阿里千问 Qwen、月之暗面 Kimi、DeepSeek、腾讯混元、字节豆包、智谱 GLM、Mistral、Meta Llama，以及 GitHub/Hugging Face 热门开源项目）。\n"
        "每条仅写基于搜索结果的可核查事实；不知道的使用限制可留空 string，严禁编造基准分或占位套话。\n"
        "仅输出严格 JSON 数组，每项包含字段：\n"
        '{"date":"YYYY-MM-DD","company_name":"机构或研究员名","region":"海外|国内|全球开源","category":"旗舰模型|开源权重|多模态|Agent工具|推理引擎","title":"中文标题","title_en":"English title","what_it_does":"一句话中文说明它能干什么","what_it_does_en":"One-sentence English explanation","who_cares":"适用人群(没有可留空)","limitations":"限制/收费/硬件门槛(没有可留空)","limitations_en":"Limitations in English","source_name":"来源","source_url":"https://...","is_open_source":true}'
    )
    try:
        from google.genai import types
        search_tools = [types.Tool(google_search=types.GoogleSearch())]
    except Exception:
        search_tools = [{"google_search": {}}]

    res = call_gemini_raw(
        scope="ai_radar",
        prompt=prompt,
        models=("gemini-4-hydrogen", "gemini-2.5-flash"),
        temperature=0.2,
        tools=search_tools,
        base_dir=root,
    )
    if not res.ok or not res.text:
        return cached["items"] if isinstance(cached.get("items"), list) else []

    m = re.search(r"\[[\s\S]*\]", res.text)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    if not isinstance(arr, list) or not arr:
        return []

    cleaned: List[Dict[str, Any]] = []
    for i, row in enumerate(arr[:14]):
        if not isinstance(row, dict) or not row.get("title"):
            continue
        row_title = str(row["title"]).strip()
        if AI_NOISE_RE.search(row_title):
            continue
        cid, cname, reg = _infer_company(f"{row.get('company_name', '')} {row_title}", str(row.get("source_url") or ""), str(row.get("source_name") or ""))
        cleaned.append(
            {
                "id": f"ai_gsearch_{today}_{i}",
                "date": str(row.get("date") or today)[:10],
                "company_id": cid,
                "company_name": str(row.get("company_name") or cname),
                "region": str(row.get("region") or reg),
                "category": str(row.get("category") or "AI 进展"),
                "category_en": "AI Release",
                "title": row_title,
                "title_en": str(row.get("title_en") or row_title),
                "what_it_does": str(row.get("what_it_does") or ""),
                "what_it_does_en": str(row.get("what_it_does_en") or ""),
                "who_cares": str(row.get("who_cares") or ""),
                "limitations": str(row.get("limitations") or ""),
                "limitations_en": str(row.get("limitations_en") or ""),
                "source_name": str(row.get("source_name") or "Google Search Grounding"),
                "source_url": str(row.get("source_url") or ""),
                "is_open_source": bool(row.get("is_open_source")),
            }
        )
    if cleaned:
        try:
            atomic_write_json(cache_path, {"schema_version": "4.1", "ts": time.time(), "updated_at": to_iso_shanghai(now_shanghai()), "items": cleaned})
        except Exception:
            pass
    return cleaned


def _clean_hf_and_tool_record(tool: Dict[str, Any], generated_at_iso: str) -> Optional[Dict[str, Any]]:
    """Convert a tech_tool record into a clean AI milestone, stripping noisy HF commit timestamps."""
    name = str(tool.get("name") or "").strip()
    if not name:
        return None
    ver_raw = str(tool.get("latest_version") or tool.get("version") or "").strip()
    turl = str(tool.get("release_url") or tool.get("official_url") or "").strip()
    tsrc = str(tool.get("source_name") or "GitHub / Hugging Face").strip()
    is_hf = "hugging face" in tsrc.lower() or "huggingface.co" in turl.lower()
    raw_summary = str(tool.get("summary") or "").strip()
    lic = str(tool.get("license") or "").strip()
    downloads = int(tool.get("downloads") or 0)

    # Filter routine HF daily sync noise (`更新于 ...`) unless it is a major popular release
    clean_ver = re.sub(r"更新于\s*\d{4}-\d{2}-\d{2}(?:[T\s]\S*)?", "", ver_raw).strip()
    if is_hf and ver_raw.startswith("更新于") and downloads < 100000:
        return None

    short_name = name.split("/")[-1].strip() if "/" in name else name
    if is_hf:
        lic_hint = f" ({lic.upper()})" if lic and lic.upper() not in ("NOASSERTION", "OTHER") else ""
        dl_hint = f" · 近期下载 {round(downloads / 10000, 1)} 万" if downloads >= 10000 else ""
        title = f"开源模型权重：{short_name}{lic_hint}".strip()
        summary = re.sub(r"^Hugging\s*Face\s*官方模型卡[^：:]*[：:]\s*", "", raw_summary).strip()
        if dl_hint and dl_hint.strip(" ·") not in summary:
            summary = f"{summary.rstrip('。')}（{dl_hint.strip(' ·')}）。" if summary else f"{short_name} 开源模型权重发布{dl_hint}。"
    else:
        title = f"开源工具更新：{short_name} {clean_ver}".strip()
        summary = raw_summary

    cid, cname, reg = _infer_company(f"{name} {tool.get('repo') or ''}", turl, tsrc)
    pub_date = normalize_ai_timestamp(tool.get("version_published_at") or generated_at_iso, generated_at_iso)
    return {
        "id": f"ai_tool_{tool.get('tool_id') or short_name}",
        "date": pub_date,
        "company_id": cid,
        "company_name": cname,
        "region": reg,
        "category": "开源权重" if is_hf else "开源工具/仓库",
        "category_en": "Open Weights" if is_hf else "Open-Source Repo",
        "title": title,
        "title_en": f"Open-source release: {short_name} {clean_ver}".strip(),
        "what_it_does": _infer_what_it_does_zh(title, summary, is_tool_release=not is_hf),
        "what_it_does_en": summary[:160] if summary else "",
        "who_cares": "",
        "limitations": f"许可证：{lic}" if lic and lic.upper() != "NOASSERTION" else "",
        "limitations_en": f"License: {lic}" if lic and lic.upper() != "NOASSERTION" else "",
        "source_id": "huggingface-hub" if is_hf else ("github-releases" if "github" in turl.lower() else ""),
        "source_name": tsrc,
        "source_url": turl,
        "is_first_hand": True,
        "source_tier": "first_party",
        "is_open_source": True,
    }


def _norm_ai_source_url(url: str) -> str:
    raw = str(url or "").strip().lower()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        return f"{parsed.netloc.removeprefix('www.')}{parsed.path.rstrip('/')}"
    except Exception:
        return raw


def _is_within_recent_hours(date_str: str, gen_dt: Any, hours: int = 72) -> bool:
    dt = parse_iso_datetime(date_str)
    if dt is None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date_str or "").strip()):
        dt = parse_iso_datetime(f"{date_str}T12:00:00+08:00")
    if dt is None or gen_dt is None:
        return False
    delta_h = (gen_dt - dt).total_seconds() / 3600.0
    return -24.0 <= delta_h <= float(hours)


def build_ai_progress_artifact(
    *,
    batch_id: str,
    generated_at_iso: str,
    cat_docs: Dict[str, dict],
    tech_tools: List[dict],
    base_dir: Path | str = ".",
) -> Dict[str, Any]:
    from .dedup import is_omnibus_digest_title, strip_raw_urls_and_domain_tails

    items: List[Dict[str, Any]] = []
    seen_title_map: Dict[str, Dict[str, Any]] = {}
    gen_dt = parse_iso_datetime(generated_at_iso) or now_shanghai()
    cutoff_180d_iso = (gen_dt - timedelta(days=180)).strftime("%Y-%m-%d")

    _LEGACY_BAD_PREFIXES = (
        "ai_google_gemini4_", "ai_openai_gpt62_", "ai_deepseek_v4_", "ai_google_diffusiongemma_",
        "ai_anthropic_claude_", "ai_tencent_hy4_", "ai_qwen4_", "ai_kimi_k31_", "ai_radixark_",
        "ai_vllm_llamacpp", "ai_openai_amd_", "ai_xai_grok3_colossus", "ai_bytedance_seed_suite",
        "ai_zhipu_glm_open", "ai_minimax_hailuo", "ai_baidu_ernie_open", "ai_huawei_openpangu",
        "ai_mistral_codestral", "ai_apple_foundation_mlx", "ai_amazon_nova_bedrock",
        "ai_perplexity_sonar", "ai_cursor_composer_ide", "ai_stability_open_media",
    )

    def _ai_item_sort_key(it: Dict[str, Any]) -> Tuple[str, int, str, int]:
        d_raw = str(it.get("date") or "").strip()
        day = d_raw[:10]
        has_time = 0 if (not d_raw or len(d_raw) <= 10) else 1
        non_tool = 1 if not str(it.get("id") or "").startswith("ai_tool_") else 0
        return (day, has_time, d_raw, non_tool)

    def _append_related_source(target: Dict[str, Any], src_name: str, src_url: str, is_fh: bool) -> None:
        rel = list(target.get("related_sources") or [])
        norm_u = _norm_ai_source_url(src_url)
        existing_urls = {_norm_ai_source_url(str(r.get("url") or "")) for r in rel}
        existing_names = {str(r.get("source_name") or "").strip() for r in rel}
        if src_name and (norm_u and norm_u not in existing_urls or (not norm_u and src_name not in existing_names)):
            rel.append({"source_name": src_name, "url": src_url, "is_first_hand": bool(is_fh)})
        target["related_sources"] = rel[:8]

    def _add_or_merge_item(raw_it: Dict[str, Any], *, drop_noisy_hf: bool = True) -> None:
        it_id = str(raw_it.get("id") or "")
        src_name = re.sub(
            r"\s*[财新财联华尔街见闻第一财经每日经济新闻证券时报人民网新华网中新社]+$",
            "",
            str(raw_it.get("source_name") or "").strip(),
        ) or str(raw_it.get("source_name") or "")
        if it_id.startswith(_LEGACY_BAD_PREFIXES) or src_name.strip().lower() == "batch_digest":
            return

        title = strip_raw_urls_and_domain_tails(str(raw_it.get("title") or "").strip())
        title = re.sub(
            r"\s+(?:财联社|华尔街见闻|第一财经|证券时报|澎湃新闻|界面新闻|凤凰网|央视网|新浪财经|东方财富)$",
            "",
            title,
        ).strip()
        # Strip legacy noisy HF sync suffixes from carried-forward records
        if drop_noisy_hf and re.search(r"更新于\s*\d{4}-\d{2}-\d{2}", title):
            return
        url = str(raw_it.get("source_url") or "").strip()
        what = strip_raw_urls_and_domain_tails(str(raw_it.get("what_it_does") or ""))
        what = re.sub(
            r"(?:^(?:财联社|凤凰网|央视网|新浪财经)\s*[丨|：:]?\s*|\s*(?:财联社|华尔街见闻|第一财经|证券时报|澎湃新闻|界面新闻|凤凰网|央视网)$)",
            "",
            what,
        ).strip()
        is_base = bool(raw_it.get("is_baseline_milestone"))
        if not title or AI_NOISE_RE.search(f"{title} {what}") or (not is_base and is_omnibus_digest_title(title)) or is_foreign_subject_blocked(title, what):
            return

        cid = str(raw_it.get("company_id") or "")
        if not cid or cid not in _LAB_META_BY_ID:
            cid, cname, reg = _infer_company(title, url, src_name)
        else:
            # Always re-verify company attribution so misroutes never survive
            inf_cid, inf_cname, inf_reg = _infer_company(title, url, src_name)
            cid, cname, reg = inf_cid, inf_cname, inf_reg

        is_tool = it_id.startswith("ai_tool_")
        what = _infer_what_it_does_zh(title, what, is_tool_release=is_tool)
        first_hand = bool(
            raw_it.get("is_first_hand")
            or is_first_hand_ai_source(str(raw_it.get("source_id") or ""), src_name, url)
        )
        is_os = detect_is_open_source(title, what, url=url, company_id=cid, source_id=str(raw_it.get("source_id") or ""))
        dim_id, dim_zh, dim_en = classify_ai_milestone_dim(title, what, is_open_source=is_os, category=str(raw_it.get("category") or ""))
        pub_date = normalize_ai_timestamp(raw_it.get("date") or generated_at_iso, generated_at_iso)

        # Keep archive bounded cleanly (baselines always kept; news items kept for 180d)
        if not is_base and pub_date[:10] and pub_date[:10] < cutoff_180d_iso:
            return

        cand = dict(raw_it)
        cand.update(
            {
                "company_id": cid,
                "company_name": cname,
                "region": reg,
                "date": pub_date,
                "source_name": src_name,
                "source_url": url,
                "title": title,
                "what_it_does": what,
                "is_first_hand": first_hand,
                "source_tier": "first_party" if first_hand else "wire_media",
                "is_open_source": is_os,
                "milestone_dim": dim_id,
                "milestone_dim_label": dim_zh,
                "milestone_dim_label_en": dim_en,
                "is_recent_72h": _is_within_recent_hours(pub_date, gen_dt, 72),
            }
        )
        if cand.get("what_it_does_en"):
            cand["what_it_does_en"] = strip_raw_urls_and_domain_tails(str(cand["what_it_does_en"]))
        _append_related_source(cand, src_name, url, first_hand)
        for rs in raw_it.get("related_sources") or []:
            if isinstance(rs, dict):
                _append_related_source(cand, str(rs.get("source_name") or ""), str(rs.get("url") or ""), bool(rs.get("is_first_hand")))

        key = re.sub(r"\W+", "", title.lower())[:26]
        if not key:
            return

        # Match existing duplicate for smart merge (never overwrite first_hand with wire!)
        match = seen_title_map.get(key)
        if match is None:
            for prev in items:
                if is_similar_ai_release(
                    title,
                    url,
                    str(prev.get("title") or ""),
                    str(prev.get("source_url") or ""),
                    company_id_a=cid,
                    company_id_b=str(prev.get("company_id") or ""),
                ):
                    match = prev
                    break

        if match is not None:
            _append_related_source(match, src_name, url, first_hand)
            for rs in cand.get("related_sources") or []:
                _append_related_source(match, str(rs.get("source_name") or ""), str(rs.get("url") or ""), bool(rs.get("is_first_hand")))

            # Promote first-hand official source if the existing entry came from secondary wire media
            if first_hand and not match.get("is_first_hand"):
                match["is_first_hand"] = True
                match["source_tier"] = "first_party"
                if url:
                    match["source_url"] = url
                if src_name:
                    match["source_name"] = src_name
                if len(title) >= 8 and not title.lower().startswith("[hf paper]"):
                    match["title"] = title
            elif first_hand and is_first_hand_ai_source("", "", url) and not is_first_hand_ai_source("", "", str(match.get("source_url") or "")):
                match["source_url"] = url
                if src_name:
                    match["source_name"] = src_name

            # Keep finer timestamp on same day & richer non-echo summary
            if _ai_item_sort_key(cand) > _ai_item_sort_key(match):
                match["date"] = pub_date
                match["is_recent_72h"] = cand["is_recent_72h"]
            if what and (not match.get("what_it_does") or len(what) > len(str(match.get("what_it_does") or "")) + 8):
                match["what_it_does"] = what
            # Prefer a non-baseline event_id when an actual live/cat item merges with a baseline milestone
            if match.get("is_baseline_milestone") and not is_base and not match.get("event_id") and cand.get("event_id"):
                match["event_id"] = cand["event_id"]
            # Re-verify open-source & dimension after merge
            match["is_open_source"] = bool(match.get("is_open_source") or is_os) if match.get("company_id") not in {"openai", "anthropic"} else detect_is_open_source(
                str(match.get("title") or ""), str(match.get("what_it_does") or ""), url=str(match.get("source_url") or ""), company_id=str(match.get("company_id") or "")
            )
            return

        seen_title_map[key] = cand
        items.append(cand)

    root_p = Path(base_dir)
    ai_kw_re = AI_KW_RE
    ai_release_re = AI_RELEASE_RE

    # Stage 1: Prepare & prioritize fresh direct RSS / live wire first-hand announcements BEFORE wire media
    raw_pool: List[dict] = []
    try:
        conn_doc = load_json_if_exists(root_p / "data/connectors_latest.json", default={})
        if isinstance(conn_doc, dict):
            raw_pool.extend(conn_doc.get("items") or [])
        lw_doc = load_json_if_exists(root_p / "data/live_wire.json", default={})
        if isinstance(lw_doc, dict):
            raw_pool.extend(lw_doc.get("items") or [])
    except Exception:
        raw_pool = []

    raw_first_hand: List[dict] = []
    raw_wire: List[dict] = []
    for raw_it in raw_pool:
        if not isinstance(raw_it, dict):
            continue
        rsid = str(raw_it.get("source_id") or "")
        rurl = str(raw_it.get("url") or raw_it.get("canonical_url") or "")
        rsrc = str(raw_it.get("publisher_name") or raw_it.get("source_name") or "直连 AI 雷达")
        if is_first_hand_ai_source(rsid, rsrc, rurl) or raw_it.get("is_first_hand"):
            raw_first_hand.append(raw_it)
        else:
            raw_wire.append(raw_it)

    def _ingest_raw_entries(entries: List[dict], require_release_kw: bool) -> None:
        from .bilingual import ensure_zh_headline

        for raw_it in entries:
            rtitle = strip_raw_urls_and_domain_tails(str(raw_it.get("title") or "").strip())
            excerpt = strip_raw_urls_and_domain_tails(str(raw_it.get("excerpt") or "").strip())
            if not rtitle or is_omnibus_digest_title(rtitle) or AI_NOISE_RE.search(f"{rtitle} {excerpt}") or is_foreign_subject_blocked(rtitle, excerpt) or not ai_kw_re.search(rtitle):
                continue
            rsid = str(raw_it.get("source_id") or "")
            rurl = str(raw_it.get("url") or raw_it.get("canonical_url") or "")
            rsrc = str(raw_it.get("publisher_name") or raw_it.get("source_name") or "直连 AI 雷达")
            first_hand = bool(raw_it.get("is_first_hand")) or is_first_hand_ai_source(rsid, rsrc, rurl)
            if require_release_kw and not first_hand and not ai_release_re.search(rtitle):
                continue
            if any(bad in rtitle.lower() for bad in ("听证会", "诈骗", "fcc", "fda", "围巾", "座驾", "中期选举", "ipo", "募资", "发行价", "灰市", "selling pressure", "股票", "股价", "lawsuit", "sues")):
                continue
            cid, cname, reg = _infer_company(rtitle, rurl, rsrc)
            pub_date = normalize_ai_timestamp(
                raw_it.get("published_at") or raw_it.get("fetched_at") or generated_at_iso,
                generated_at_iso,
            )
            zh_title = ensure_zh_headline(rtitle, "tech")
            is_os = detect_is_open_source(zh_title, excerpt, url=rurl, company_id=cid, source_id=rsid)
            _add_or_merge_item(
                {
                    "id": f"ai_raw_{raw_it.get('item_id') or raw_it.get('id') or len(items)}",
                    "date": pub_date,
                    "company_id": cid,
                    "company_name": cname,
                    "region": reg,
                    "category": "开源突破" if is_os else ("官方一手" if first_hand else "最新动态"),
                    "category_en": "Open Source" if is_os else ("First-Hand Official" if first_hand else "Latest Release"),
                    "title": zh_title,
                    "title_en": rtitle,
                    "what_it_does": _infer_what_it_does_zh(zh_title, excerpt),
                    "what_it_does_en": excerpt[:160] if excerpt else "",
                    "who_cares": "",
                    "limitations": "",
                    "limitations_en": "",
                    "source_id": rsid,
                    "source_name": rsrc,
                    "source_url": rurl,
                    "is_first_hand": first_hand,
                    "source_tier": "first_party" if first_hand else "wire_media",
                    "is_open_source": is_os,
                }
            )

    try:
        _ingest_raw_entries(raw_first_hand, require_release_kw=False)
    except Exception:
        pass

    grounded = _query_gemini_google_search_ai_weekly(base_dir=base_dir)
    for g in grounded:
        _add_or_merge_item(g)

    # Stage 2: Ingest structured smart briefing events (inspect ALL sources so first-hand blog refs are never lost!)
    for cat in ("tech", "general", "finance", "global"):
        for ev in (cat_docs.get(cat) or {}).get("events") or []:
            title = str(ev.get("title") or "").strip()
            if not title or not ai_kw_re.search(title) or AI_NOISE_RE.search(title) or is_foreign_subject_blocked(title):
                continue
            if any(bad in title.lower() for bad in ("听证会", "诈骗", "fcc", "fda", "围巾", "座驾", "中期选举", "ipo", "募资", "发行价", "灰市", "selling pressure", "股票", "股价", "后悔当年")):
                continue
            srcs = [s for s in (ev.get("sources") or []) if isinstance(s, dict)]
            best_src = srcs[0] if srcs else {}
            first_hand = False
            for cand_s in srcs:
                c_sid = str(cand_s.get("source_id") or "")
                c_url = str(cand_s.get("url") or "")
                c_name = str(cand_s.get("publisher_name") or cand_s.get("source_name") or "")
                if is_first_hand_ai_source(c_sid, c_name, c_url):
                    best_src = cand_s
                    first_hand = True
                    break
            src_id = str(best_src.get("source_id") or "")
            src_url = str(best_src.get("url") or "")
            src_name = str(best_src.get("publisher_name") or best_src.get("source_name") or "镜信科技快讯")
            if not first_hand:
                first_hand = is_first_hand_ai_source(src_id, src_name, src_url)
            cid, cname, reg = _infer_company(title, src_url, src_name)
            pub_date = normalize_ai_timestamp(
                ev.get("latest_reported_at") or ev.get("first_reported_at") or generated_at_iso,
                generated_at_iso,
            )
            summary = str(ev.get("fact_summary") or ev.get("summary") or "")
            is_os = detect_is_open_source(title, summary, url=src_url, company_id=cid, source_id=src_id)
            ev_item: Dict[str, Any] = {
                "id": f"ai_ev_{ev.get('event_id')}",
                "date": pub_date,
                "company_id": cid,
                "company_name": cname,
                "region": reg,
                "category": "开源突破" if is_os else "模型与产品",
                "category_en": "Open Source" if is_os else "Model & Product",
                "title": title,
                "title_en": str(ev.get("title_en") or title),
                "what_it_does": _infer_what_it_does_zh(title, summary),
                "what_it_does_en": str(ev.get("summary_en") or summary[:160]),
                "who_cares": "",
                "limitations": "",
                "limitations_en": "",
                "source_id": src_id,
                "source_name": src_name,
                "source_url": src_url,
                "is_first_hand": first_hand,
                "source_tier": "first_party" if first_hand else "wire_media",
                "event_id": ev.get("event_id"),
                "is_open_source": is_os,
                "related_sources": [
                    {
                        "source_name": str(s.get("publisher_name") or s.get("source_name") or ""),
                        "url": str(s.get("url") or ""),
                        "is_first_hand": is_first_hand_ai_source(str(s.get("source_id") or ""), str(s.get("source_name") or ""), str(s.get("url") or "")),
                    }
                    for s in srcs[:5]
                    if s.get("url")
                ],
            }
            _add_or_merge_item(ev_item)

    try:
        _ingest_raw_entries(raw_wire, require_release_kw=True)
    except Exception:
        pass

    for tool in tech_tools[:24]:
        if not isinstance(tool, dict):
            continue
        cleaned_tool = _clean_hf_and_tool_record(tool, generated_at_iso)
        if cleaned_tool is not None:
            _add_or_merge_item(cleaned_tool, drop_noisy_hf=False)

    # Stage 3: Merge curated historical baselines & recovered recent flagship releases (never overwrites newer live items)
    for base_m in HISTORICAL_BASELINE_MILESTONES:
        _add_or_merge_item(dict(base_m), drop_noisy_hf=False)

    # Stage 4: Incremental merge with persistent archive (data/ai_progress_archive.json) & prior data/ai_progress.json
    for prev_rel in ("data/ai_progress_archive.json", "data/ai_progress.json"):
        try:
            prev_doc = load_json_if_exists(root_p / prev_rel, default={})
            prev_pool: List[dict] = []
            if isinstance(prev_doc, dict):
                prev_pool.extend(prev_doc.get("timeline") or [])
                for comp in prev_doc.get("companies") or []:
                    if isinstance(comp, dict):
                        prev_pool.extend(comp.get("items") or [])
            for prev_it in prev_pool:
                if not isinstance(prev_it, dict):
                    continue
                cleaned_prev = dict(prev_it)
                prev_t = strip_raw_urls_and_domain_tails(str(cleaned_prev.get("title") or ""))
                prev_sum = strip_raw_urls_and_domain_tails(str(cleaned_prev.get("what_it_does") or ""))
                if "具身智能/物理仿真模型工具" in prev_sum and "robot" not in prev_t.lower() and not str(cleaned_prev.get("id") or "").startswith("ai_tool_"):
                    prev_sum = ""
                cleaned_prev["title"] = prev_t
                cleaned_prev["what_it_does"] = prev_sum
                _add_or_merge_item(cleaned_prev)
        except Exception:
            pass

    items.sort(key=_ai_item_sort_key, reverse=True)

    # Build Archive view (up to 24 milestones per lab, up to 240 in archive timeline)
    archive_companies: List[Dict[str, Any]] = []
    archive_union: List[Dict[str, Any]] = []
    seen_arch_ids: set[str] = set()

    # Build Active view (up to 8 deduplicated items per lab, recent-first with baseline coverage -> 0 empty labs!)
    active_companies: List[Dict[str, Any]] = []
    active_union: List[Dict[str, Any]] = []
    seen_active_ids: set[str] = set()

    for lab in _LAB_CATALOG:
        cid = lab["company_id"]
        lab_all = sorted([it for it in items if it.get("company_id") == cid], key=_ai_item_sort_key, reverse=True)

        lab_arch = lab_all[:24]
        lab_active = lab_all[:8]

        archive_companies.append(
            {
                **lab,
                "recent_count": len(lab_arch),
                "archive_count": len(lab_all),
                "latest_date": lab_arch[0]["date"] if lab_arch else "",
                "latest_headline": lab_arch[0]["title"] if lab_arch else "",
                "items": lab_arch,
            }
        )
        for it in lab_arch:
            iid = str(it.get("id") or "")
            if iid and iid not in seen_arch_ids:
                seen_arch_ids.add(iid)
                archive_union.append(it)

        active_companies.append(
            {
                **lab,
                "recent_count": len(lab_active),
                "archive_count": len(lab_all),
                "latest_date": lab_active[0]["date"] if lab_active else "",
                "latest_headline": lab_active[0]["title"] if lab_active else "",
                "items": lab_active,
            }
        )
        for it in lab_active:
            iid = str(it.get("id") or "")
            if iid and iid not in seen_active_ids:
                seen_active_ids.add(iid)
                active_union.append(it)

    archive_union.sort(key=_ai_item_sort_key, reverse=True)
    active_union.sort(key=_ai_item_sort_key, reverse=True)

    weekly_highlights: List[Dict[str, Any]] = []
    company_counts: Dict[str, int] = {}
    for it in active_union:
        if str(it.get("id") or "").startswith("ai_tool_"):
            continue
        cid = str(it.get("company_id") or "")
        if company_counts.get(cid, 0) >= 1 and len(weekly_highlights) < 6:
            continue
        company_counts[cid] = company_counts.get(cid, 0) + 1
        weekly_highlights.append(it)
        if len(weekly_highlights) >= 6:
            break
    if len(weekly_highlights) < 6:
        used_ids = {x["id"] for x in weekly_highlights}
        for it in active_union:
            if it["id"] not in used_ids and not str(it.get("id") or "").startswith("ai_tool_"):
                weekly_highlights.append(it)
                if len(weekly_highlights) >= 6:
                    break

    def _build_digest_block(pool: List[Dict[str, Any]], label_prefix: str) -> Dict[str, Any]:
        os_c = sum(1 for it in pool if it.get("is_open_source"))
        cn_c = sum(1 for it in pool if it.get("region") == "国内")
        gl_c = sum(1 for it in pool if it.get("region") == "海外")
        fh_c = sum(1 for it in pool if it.get("is_first_hand"))
        return {
            "period_label": f"{label_prefix}（截至 {generated_at_iso[:10]}）",
            "period_label_en": f"Global AI Digest (as of {generated_at_iso[:10]})",
            "summary": (
                f"追踪 23 家前沿实验室共 {len(pool)} 项独立 AI 进展（海外 {gl_c} · 国内 {cn_c} · 开源生态 {os_c} · 一手官方 {fh_c}）。"
                "支持按代际演进谱系、5 大技术维度及 180 天完整历史归档库切换检索。"
            ),
            "summary_en": (
                f"Tracking {len(pool)} deduplicated AI milestones across 23 frontier labs ({gl_c} global, {cn_c} China, {os_c} open-source, {fh_c} first-hand official)."
            ),
            "highlights": weekly_highlights,
        }

    archive_doc = {
        "schema_version": "4.2",
        "generated_at": generated_at_iso,
        "batch_id": batch_id,
        "mode": "archive_180d",
        "weekly_digest": _build_digest_block(archive_union, "全球 AI 机构 180 天完整历史演进库"),
        "companies": archive_companies,
        "timeline": archive_union[:240],
    }
    try:
        if str(base_dir):
            atomic_write_json(root_p / "data/ai_progress_archive.json", archive_doc)
    except Exception:
        pass

    return {
        "schema_version": "4.2",
        "generated_at": generated_at_iso,
        "batch_id": batch_id,
        "search_grounded": bool(grounded),
        "archive_path": "data/ai_progress_archive.json",
        "archive_total": len(archive_union),
        "weekly_digest": _build_digest_block(active_union, "近 7 日全球 AI 大事与机构演进榜"),
        "companies": active_companies,
        "timeline": active_union,
    }
