"""Global AI Model & Open-Source Progress Tracker (data/ai_progress.json)."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

from .time_utils import now_shanghai

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
]


def _infer_company(title: str) -> tuple[str, str, str]:
    t = title.lower()
    if any(k in t for k in ("google", "gemini", "gemma", "deepmind", "genie")):
        return "google", "Google DeepMind", "海外"
    if any(k in t for k in ("anthropic", "claude")):
        return "anthropic", "Anthropic", "海外"
    if any(k in t for k in ("openai", "gpt-", "chatgpt", "sora", "codex")):
        return "openai", "OpenAI", "海外"
    if any(k in t for k in ("qwen", "千问", "通义", "阿里")):
        return "qwen", "阿里千问 (Qwen)", "国内"
    if any(k in t for k in ("kimi", "moonshot", "月之暗面")):
        return "kimi", "月之暗面 (Kimi)", "国内"
    if any(k in t for k in ("混元", "hunyuan", "腾讯")):
        return "tencent_hunyuan", "腾讯混元 (Hunyuan)", "国内"
    if any(k in t for k in ("deepseek", "深度求索")):
        return "deepseek", "DeepSeek", "国内"
    return "indie_opensource", "独立实验室 & 开源黑马", "全球开源"


def _infer_what_it_does_zh(title: str, summary: str) -> str:
    t = f"{title} {summary}".lower()
    if any(k in t for k in ("vllm", "llama.cpp", "ollama", "推理引擎", "inference")):
        return "开源本地/服务器推理加速工具：帮开发者和普通电脑更快、更省显存地运行各类开源大模型。"
    if any(k in t for k in ("3d", "hair", "video", "视频", "music", "音乐", "image", "图像", "ar ")):
        return "多模态生成/创作模型：用于文字生成图像、视频、音乐或 3D 资产，降低设计与创作门槛。"
    if any(k in t for k in ("robot", "具身", "机器人", "world model", "世界模型")):
        return "具身智能/世界模型工具：用于在虚拟或物理环境中训练机器人感知、规划与执行任务。"
    if any(k in t for k in ("agent", "coding", "编程", "code", "sdk", "cli", "harness")):
        return "AI 编程与智能体（Agent）工具：自动读写代码、调用外部工具并执行多步骤复杂任务。"
    if any(k in t for k in ("small", "mini", "flash", "nano", "27b", "7b", "8b", "端侧", "个人电脑")):
        return "轻量高效/端侧模型：主打低成本、高速度或支持个人电脑离线部署，适合日常高频使用。"
    return (summary[:110] + "…") if len(summary) > 110 else (summary or "前沿 AI 模型或工具更新，提升推理、开发或多模态自动化效率。")


def _query_gemini_google_search_ai_weekly() -> List[Dict[str, Any]]:
    """Use Gemini + Google Search Grounding rotating across ALL configured keys to catch zero-lag global & China AI releases."""
    key_names = (
        "KEY_TECH", "KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_6", "KEY_7", "KEY_8",
        "GOOGLE_API_KEY", "KEY_FINANCE", "KEY_GLOBAL", "KEY_GENERAL",
    )
    keys: List[str] = []
    for kn in key_names:
        val = (os.environ.get(kn) or "").strip()
        if val and val not in keys:
            keys.append(val)
    if not keys:
        return []
    try:
        from google import genai
        from google.genai import types

        today = now_shanghai().strftime("%Y-%m-%d")
        prompt = (
            f"今天是 {today}。请通过 Google 搜索整理最近 7 天（尤其过去 24–72 小时内最新刚发布）全球与中国最重磅的 8–12 条 AI 模型与开源项目进展"
            "（务必重点搜索并核查：Google Gemini 4 Neon/Carbon/Hydrogen/Gemma、OpenAI GPT-6.2 Astra/Sol/Codex、Anthropic Claude Fable/Mythos 5.x、阿里 Qwen4、月之暗面 Kimi K3、DeepSeek V4、腾讯混元 Hy4、xAI Grok、Meta Llama，以及 GitHub/Hugging Face 爆火的独立开源模型/推理引擎/多模态/机器人项目）。\n"
            "每条必须用小白能一眼看懂的中文说清「它具体能干什么」和「使用限制/门槛」。\n"
            "仅输出严格 JSON 数组，每项包含字段：\n"
            '{"date":"YYYY-MM-DD","company_name":"机构或研究员名","region":"海外|国内|全球开源","category":"旗舰模型|开源权重|多模态|Agent工具|推理引擎","title":"中文标题","title_en":"English title","what_it_does":"一句话小白说明它能干什么","what_it_does_en":"One-sentence English explanation","who_cares":"适用人群","limitations":"限制/收费/硬件门槛","limitations_en":"Limitations in English","source_name":"来源","source_url":"https://...","is_open_source":true}'
        )
        for api_key in keys[:6]:
            client = genai.Client(api_key=api_key)
            for model_name in ("gemini-4-hydrogen", "gemini-2.5-flash"):
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            tools=[types.Tool(google_search=types.GoogleSearch())],
                            temperature=0.2,
                        ),
                    )
                    txt = (resp.text or "").strip()
                    m = re.search(r"\[[\s\S]*\]", txt)
                    if not m:
                        continue
                    arr = json.loads(m.group(0))
                    if isinstance(arr, list) and arr:
                        cleaned: List[Dict[str, Any]] = []
                        for i, row in enumerate(arr[:14]):
                            if not isinstance(row, dict) or not row.get("title"):
                                continue
                            cid, cname, reg = _infer_company(f"{row.get('company_name', '')} {row.get('title', '')}")
                            cleaned.append(
                                {
                                    "id": f"ai_gsearch_{today}_{i}",
                                    "date": str(row.get("date") or today)[:10],
                                    "company_id": cid,
                                    "company_name": str(row.get("company_name") or cname),
                                    "region": str(row.get("region") or reg),
                                    "category": str(row.get("category") or "AI 进展"),
                                    "category_en": "AI Release",
                                    "title": str(row.get("title")),
                                    "title_en": str(row.get("title_en") or row.get("title")),
                                    "what_it_does": str(row.get("what_it_does") or ""),
                                    "what_it_does_en": str(row.get("what_it_does_en") or ""),
                                    "who_cares": str(row.get("who_cares") or "AI 开发者与普通用户"),
                                    "limitations": str(row.get("limitations") or "详见官方说明与许可证"),
                                    "limitations_en": str(row.get("limitations_en") or "See official docs for limits"),
                                    "source_name": str(row.get("source_name") or "Google Search Grounding"),
                                    "source_url": str(row.get("source_url") or ""),
                                    "is_open_source": bool(row.get("is_open_source")),
                                }
                            )
                        return cleaned
                except Exception:
                    continue
    except Exception:
        return []
    return []


def build_ai_progress_artifact(
    *,
    batch_id: str,
    generated_at_iso: str,
    cat_docs: Dict[str, dict],
    tech_tools: List[dict],
) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    seen_titles: set[str] = set()

    def _add_item(it: Dict[str, Any]) -> None:
        key = re.sub(r"\W+", "", str(it.get("title") or "").lower())[:26]
        if not key or key in seen_titles:
            return
        seen_titles.add(key)
        items.append(it)

    grounded = _query_gemini_google_search_ai_weekly()
    for g in grounded:
        _add_item(g)

    ai_kw_re = re.compile(
        r"(?:模型|开源|gemini|neon|carbon|hydrogen|claude|fable|mythos|gpt|astra|qwen|千问|kimi|混元|deepseek|diffusion|llama|vllm|ollama|agent|openai|anthropic|huggingface|github|强化学习)",
        re.I,
    )
    ai_release_re = re.compile(
        r"(?:release|launch|announc|introduc|open[- ]source|weights|发布|开源|上线|推出|升级|preview|neon|astra|fable|mythos|qwen4|deepseek|kimi|genie|gemma)",
        re.I,
    )
    for cat in ("tech", "general", "finance", "global"):
        for ev in (cat_docs.get(cat) or {}).get("events") or []:
            title = str(ev.get("title") or "").strip()
            if not title or not ai_kw_re.search(title):
                continue
            if any(bad in title.lower() for bad in ("听证会", "诈骗", "fcc", "fda", "围巾", "座驾", "中期选举", "ipo", "募资", "发行价", "灰市", "selling pressure", "股票", "股价", "后悔当年")):
                continue
            cid, cname, reg = _infer_company(title)
            src0 = (ev.get("sources") or [{}])[0]
            pub_date = str(ev.get("first_reported_at") or ev.get("latest_reported_at") or generated_at_iso)[:10]
            summary = str(ev.get("fact_summary") or ev.get("summary") or "")
            is_os = any(k in title.lower() for k in ("开源", "open", "github", "hugging", "vllm", "llama.cpp", "gemma", "权重"))
            _add_item(
                {
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
                    "who_cares": "AI 开发者、科技观察者与普通效率用户",
                    "limitations": "详见原文披露的接口配额、开源协议或硬件运行要求。",
                    "limitations_en": "Refer to official release notes for quotas, license, and hardware specs.",
                    "source_name": str(src0.get("source_name") or "镜信科技快讯"),
                    "source_url": str(src0.get("url") or ""),
                    "event_id": ev.get("event_id"),
                    "is_open_source": is_os,
                }
            )

    # Also ingest freshly crawled direct-RSS AI lab announcements & 7x24 flash wire AI drops (zero-lag)
    try:
        from pathlib import Path
        from .bilingual import ensure_zh_headline
        from .manifest import load_json_if_exists

        raw_pool: List[dict] = []
        conn_doc = load_json_if_exists(Path("data/connectors_latest.json"), default={})
        if isinstance(conn_doc, dict):
            raw_pool.extend(conn_doc.get("items") or [])
        lw_doc = load_json_if_exists(Path("data/live_wire.json"), default={})
        if isinstance(lw_doc, dict):
            raw_pool.extend(lw_doc.get("items") or [])

        for raw_it in raw_pool:
            if not isinstance(raw_it, dict):
                continue
            rtitle = str(raw_it.get("title") or "").strip()
            if not rtitle or not ai_kw_re.search(rtitle) or not ai_release_re.search(rtitle):
                continue
            if any(bad in rtitle.lower() for bad in ("听证会", "诈骗", "fcc", "fda", "围巾", "座驾", "中期选举", "ipo", "募资", "发行价", "灰市", "selling pressure", "股票", "股价", "lawsuit", "sues")):
                continue
            cid, cname, reg = _infer_company(rtitle)
            pub_date = str(raw_it.get("published_at") or raw_it.get("fetched_at") or generated_at_iso)[:10]
            excerpt = str(raw_it.get("excerpt") or "")
            zh_title = ensure_zh_headline(rtitle, "tech")
            is_os = any(k in rtitle.lower() for k in ("开源", "open", "github", "hugging", "vllm", "llama.cpp", "gemma", "权重"))
            _add_item(
                {
                    "id": f"ai_raw_{raw_it.get('item_id') or raw_it.get('id') or len(items)}",
                    "date": pub_date,
                    "company_id": cid,
                    "company_name": cname,
                    "region": reg,
                    "category": "开源突破" if is_os else "最新动态",
                    "category_en": "Open Source" if is_os else "Latest Release",
                    "title": zh_title,
                    "title_en": rtitle,
                    "what_it_does": _infer_what_it_does_zh(zh_title, excerpt),
                    "what_it_does_en": excerpt[:160] or rtitle,
                    "who_cares": "AI 开发者、科研人员与前沿用户",
                    "limitations": "详见官方发布说明与接口配额。",
                    "limitations_en": "See official release notes and API pricing.",
                    "source_name": str(raw_it.get("source_name") or "直连 AI 雷达"),
                    "source_url": str(raw_it.get("url") or raw_it.get("canonical_url") or ""),
                    "is_open_source": is_os,
                }
            )
    except Exception:
        pass

    for tool in tech_tools[:12]:
        name = str(tool.get("name") or "").strip()
        ver = str(tool.get("version") or "").strip()
        if not name:
            continue
        title = f"开源生态更新：{name} {ver}".strip()
        cid, cname, reg = _infer_company(f"{name} {tool.get('summary') or ''}")
        pub_date = str(tool.get("version_published_at") or generated_at_iso)[:10]
        summary = str(tool.get("summary") or "").strip()
        _add_item(
            {
                "id": f"ai_tool_{tool.get('tool_id') or name}",
                "date": pub_date,
                "company_id": cid,
                "company_name": cname,
                "region": reg,
                "category": "开源工具/仓库",
                "category_en": "Open-Source Repo",
                "title": title,
                "title_en": f"Open-source release: {name} {ver}".strip(),
                "what_it_does": _infer_what_it_does_zh(title, summary),
                "what_it_does_en": summary[:160] or f"Latest open-source version of {name}.",
                "who_cares": "开发者、开源爱好者与私有化部署团队",
                "limitations": f"许可证：{tool.get('license') or '见仓库说明'}；部署需参考官方环境要求。",
                "limitations_en": f"License: {tool.get('license') or 'See repo'}; check runtime specs.",
                "source_name": str(tool.get("source_name") or "GitHub / Hugging Face"),
                "source_url": str(tool.get("release_url") or tool.get("official_url") or ""),
                "is_open_source": True,
            }
        )

    for m in _CURATED_AI_MILESTONES:
        _add_item(dict(m))

    items.sort(key=lambda x: (str(x.get("date") or ""), 1 if not x["id"].startswith("ai_tool_") else 0), reverse=True)

    companies: List[Dict[str, Any]] = []
    for lab in _LAB_CATALOG:
        cid = lab["company_id"]
        lab_items = [it for it in items if it.get("company_id") == cid]
        companies.append(
            {
                **lab,
                "recent_count": len(lab_items),
                "latest_date": lab_items[0]["date"] if lab_items else generated_at_iso[:10],
                "latest_headline": lab_items[0]["title"] if lab_items else lab["flagship_model"],
                "items": lab_items[:6],
            }
        )

    # Build Weekly AI Digest Summary: pick 6 diverse high-signal model/open-source releases across different labs!
    weekly_highlights: List[Dict[str, Any]] = []
    company_counts: Dict[str, int] = {}
    for it in items:
        if it["id"].startswith("ai_tool_"):
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
        for it in items:
            if it["id"] not in used_ids and not it["id"].startswith("ai_tool_"):
                weekly_highlights.append(it)
                if len(weekly_highlights) >= 6:
                    break
    open_source_count = sum(1 for it in items if it.get("is_open_source"))
    china_count = sum(1 for it in items if it.get("region") == "国内")
    global_count = sum(1 for it in items if it.get("region") == "海外")

    return {
        "schema_version": "4.0",
        "generated_at": generated_at_iso,
        "batch_id": batch_id,
        "search_grounded": bool(grounded),
        "weekly_digest": {
            "period_label": f"近 7 日全球 AI 大事周报（截至 {generated_at_iso[:10]}）",
            "period_label_en": f"Weekly Global AI Digest (as of {generated_at_iso[:10]})",
            "summary": (
                f"本周共收录 {len(items)} 项国内外 AI 关键进展（海外 {global_count} · 国内 {china_count} · 开源生态 {open_source_count}）。"
                "主线聚焦三大方向：1）中美头部旗舰模型进入新一轮迭代与商业化验证；"
                "2）端侧中小参数与开源推理引擎持续拉低个人电脑本地运行门槛；"
                "3）多模态世界模型与编程 Agent 加速落地真实开发工作流。"
            ),
            "summary_en": (
                f"Tracked {len(items)} AI milestones this week ({global_count} global, {china_count} China, {open_source_count} open-source). "
                "Key themes: flagship model competition, local/edge open-weight breakthroughs, and multimodal & coding agents entering production."
            ),
            "highlights": weekly_highlights,
        },
        "companies": companies,
        "timeline": items[:28],
    }
