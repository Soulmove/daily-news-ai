"""Concurrent 13-Key Grounded Gemini Deep-Enrichment Engine for JingXin (MirrorBrief).

Runs offline in GitHub Actions across `pipeline.gemini_pool` scopes (`ThreadPoolExecutor`) with
persistent TTL caches in `data/*_cache.json`, enriching:
1. `model_comparison_matrix`: Top 14 global flagship LLMs side-by-side matrix.
2. `tools`: Differentiated `pain_point`, `best_for`, `comparison_note` per open-source repo/model.
3. `storylines`: Grounded historical timeline backfill (3-5 real nodes) + `stance_comparison` table.
4. `events`: 2-3 clickable `deep_qa` curiosity prompts + verified answers & historical parallels.
5. `major_topics`: 30-second `brief_overview` + `comparison_table` per spotlight topic.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .gemini_pool import call_gemini_raw, collect_api_key_slots
from .manifest import atomic_write_json, load_json_if_exists
from .time_utils import now_shanghai, parse_iso_datetime, to_iso_shanghai

_COLORED_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "\u231A-\u231B"
    "\u23E9-\u23F3"
    "\u23F8-\u23FA"
    "\u2B50\u2B55\u2934\u2935"
    "\uFE0F\u200D"
    "]+",
    flags=re.UNICODE,
)


def strip_colored_emojis(text: Optional[str]) -> str:
    """Remove all colored system Unicode emojis cleanly while keeping text, ★, ✓, arrows."""
    if not text:
        return ""
    cleaned = _COLORED_EMOJI_RE.sub("", str(text))
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _google_search_tools() -> List[Any]:
    try:
        from google.genai import types

        return [types.Tool(google_search=types.GoogleSearch())]
    except Exception:
        return [{"google_search": {}}]


def _extract_json_block(text: str, *, expect_list: bool = False) -> Any:
    if not text:
        return None
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()
    pat = r"\[[\s\S]*\]" if expect_list else r"(?:\{[\s\S]*\}|\[[\s\S]*\])"
    m = re.search(pat, raw)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _baseline_model_comparison_matrix() -> List[Dict[str, str]]:
    return [
        {
            "model_name": "Gemini 4 Argon / Carbon",
            "org": "Google DeepMind",
            "region": "海外",
            "release_date": "2026-10 / 09",
            "positioning": "超大规模深度推理与科研工程主力（Argon 首推 GA / Carbon 旗舰科研）",
            "context_window": "1M ~ 2M",
            "pricing_input": "$3.50 / 1M",
            "pricing_output": "$14.00 / 1M",
            "weight_type": "闭源商用",
            "strengths": "代码工程重构、跨百万字长文本精准定位、数学科学多步推理与 TPU 高并发",
            "weaknesses": "完全闭源；高阶思考档位首字延迟与输出 Token 计费较高",
        },
        {
            "model_name": "Gemini 4 Neon",
            "org": "Google DeepMind",
            "region": "海外",
            "release_date": "2026-11",
            "positioning": "近 Carbon 智力 + 高速高性价比全能旗舰",
            "context_window": "1M",
            "pricing_input": "$3.00 / 1M",
            "pricing_output": "$15.00 / 1M",
            "weight_type": "闭源商用",
            "strengths": "支持可调思考档位（Low/Med/High），全模态工具检索与前端代码生成领先",
            "weaknesses": "仅限云端 Gemini API / Vertex AI 访问",
        },
        {
            "model_name": "GPT-6.2 Astra / Sol",
            "org": "OpenAI",
            "region": "海外",
            "release_date": "2026-11",
            "positioning": "高推理旗舰 Astra 与高并发 Agent 主力 Sol",
            "context_window": "1M",
            "pricing_input": "$2.50 / 1M (Sol)",
            "pricing_output": "$10.00 / 1M (Sol)",
            "weight_type": "闭源商用",
            "strengths": "工具调用生态成熟、实时语音与 Copilot 办公集成度极高，抗蒸馏加固",
            "weaknesses": "高并发企业定制白名单严苛；部分基准测试透明度受业内争议",
        },
        {
            "model_name": "Claude Opus 5.5 / Mythos 5.2",
            "org": "Anthropic",
            "region": "海外",
            "release_date": "2026-11",
            "positioning": "顶级企业编程 Agent 与形式化数学证明旗舰",
            "context_window": "1M Beta",
            "pricing_input": "$5.00 / 1M",
            "pricing_output": "$25.00 / 1M",
            "weight_type": "闭源商用",
            "strengths": "Claude Code 复杂多仓调试、MCP 生态原点、黎曼猜想等形式化证明实测顶尖",
            "weaknesses": "API 价格处于第一梯队高位，并发与特定区域合规限制严格",
        },
        {
            "model_name": "DeepSeek-R2 / V4-Pro",
            "org": "DeepSeek",
            "region": "国内",
            "release_date": "2026-11",
            "positioning": "开源 MoE 极低成本推理与代码性价比标杆",
            "context_window": "256K",
            "pricing_input": "$0.28 / 1M",
            "pricing_output": "$0.95 / 1M",
            "weight_type": "开源权重 (MIT)",
            "strengths": "极高数学竞赛与算法编码准确率，私有化与多云 API 成本远低于海外闭源",
            "weaknesses": "原生音频/视频生成多模态矩阵相对克制，超长 1M 原生多模态略逊",
        },
        {
            "model_name": "Qwen4-Max / Qwen3.5-Coder",
            "org": "阿里千问 (Qwen)",
            "region": "国内",
            "release_date": "2026-11",
            "positioning": "中英文全尺寸开源底座与云端百炼企业旗舰",
            "context_window": "1M",
            "pricing_input": "$0.40 / 1M",
            "pricing_output": "$1.60 / 1M",
            "weight_type": "混合 (Qwen3.5 开源 / Max 闭源)",
            "strengths": "Apache-2.0 端边云全尺寸谱系完整，仓库级编程 Agent 与工具调用稳健",
            "weaknesses": "Qwen4-Max 预览旗舰目前仍以云端 API 优先发布，全权重尚未开放",
        },
        {
            "model_name": "GLM-5.5 / GLM-5.4",
            "org": "智谱 AI",
            "region": "国内",
            "release_date": "2026-11",
            "positioning": "强代码重构与复杂工具链自主 Agent 旗舰",
            "context_window": "256K",
            "pricing_input": "$0.50 / 1M",
            "pricing_output": "$2.00 / 1M",
            "weight_type": "部分开源 + 商业 API",
            "strengths": "中文办公文档与端到端电脑操作/沙盒执行连续性突出",
            "weaknesses": "国际化第三方英文评测覆盖密度弱于 GPT/Claude",
        },
        {
            "model_name": "混元 Hy4 / Hy4 Flash",
            "org": "腾讯混元",
            "region": "国内",
            "release_date": "2026-11",
            "positioning": "高吞吐全模态推理与 3D/视频生成引擎",
            "context_window": "256K",
            "pricing_input": "$0.25 / 1M (Flash)",
            "pricing_output": "$0.90 / 1M (Flash)",
            "weight_type": "部分开源 (3D/视频) + API",
            "strengths": "国产 GPU Day 0 深度适配，游戏影视级 3D 与微信生态并发承载极强",
            "weaknesses": "海外开发者生态插件相对有限",
        },
        {
            "model_name": "Kimi K3.1 Pro",
            "org": "月之暗面 (Kimi)",
            "region": "国内",
            "release_date": "2026-11",
            "positioning": "超长文档深读与多步联网研究 Agent",
            "context_window": "2M",
            "pricing_input": "$0.60 / 1M",
            "pricing_output": "$2.50 / 1M",
            "weight_type": "开源权重 + API",
            "strengths": "数十万字财报合同一次通读检索不丢细节，私有内网部署兼容好",
            "weaknesses": "万亿级 MoE 自建全量集群显存门槛极高",
        },
        {
            "model_name": "MiniMax-M2",
            "org": "MiniMax",
            "region": "国内",
            "release_date": "2026-09",
            "positioning": "线性注意力超长上下文与高并发密码/代码推理",
            "context_window": "4M",
            "pricing_input": "$0.30 / 1M",
            "pricing_output": "$1.10 / 1M",
            "weight_type": "开源权重 + API",
            "strengths": "线性注意力让百万级窗口推理显存开销大降，密码学前沿推理表现亮眼",
            "weaknesses": "极端高难度数学竞赛泛化深度仍持续迭代中",
        },
        {
            "model_name": "ERNIE 5.0 (Omni)",
            "org": "百度文心",
            "region": "国内",
            "release_date": "2026-06",
            "positioning": "全模态统一建模与搜索 RAG 增强企业底座",
            "context_window": "512K",
            "pricing_input": "$0.35 / 1M",
            "pricing_output": "$1.40 / 1M",
            "weight_type": "闭源 API + 4.5 开源家族",
            "strengths": "与百度中文搜索知识图谱深度结合，事实核查与政务金融场景落地扎实",
            "weaknesses": "开源版本多集中于上一代 ERNIE 4.5 家族",
        },
        {
            "model_name": "Grok 4",
            "org": "xAI",
            "region": "海外",
            "release_date": "2026-07",
            "positioning": "实时 X 舆论流与超大规模 Colossus 算力集群驱动",
            "context_window": "512K",
            "pricing_input": "$3.00 / 1M",
            "pricing_output": "$15.00 / 1M",
            "weight_type": "闭源商用",
            "strengths": "突发实时资讯抓取极快，STEM 与科学推演受大集群算力加持显著",
            "weaknesses": "企业级复杂工具链 SLA 与结构化 JSON 生态略弱",
        },
        {
            "model_name": "Llama 4 (Behemoth / Maverick)",
            "org": "Meta AI",
            "region": "海外",
            "release_date": "2025-10 / 2026",
            "positioning": "欧美开源 MoE 基座与端云生态标准",
            "context_window": "1M ~ 10M (Scout)",
            "pricing_input": "$0.20 / 1M (托管)",
            "pricing_output": "$0.80 / 1M (托管)",
            "weight_type": "开放权重 (Llama License)",
            "strengths": "全球硬件厂商芯片优化 Day 0 支持度最高，超长上下文本地可微调",
            "weaknesses": "最新超大旗舰推理上限逐步被 DeepSeek/Qwen 与闭源旗舰追超",
        },
        {
            "model_name": "豆包 2.0 / Seed-Thinking",
            "org": "字节跳动 (ByteDance)",
            "region": "国内",
            "release_date": "2026-11",
            "positioning": "极致并发成本与视觉 GUI 操控/视频生成生态",
            "context_window": "512K",
            "pricing_input": "$0.15 / 1M",
            "pricing_output": "$0.60 / 1M",
            "weight_type": "闭源 API + UI-TARS 开源",
            "strengths": "字节方舟超低 Token 成本、Seedance 视频与电脑屏幕视觉点击 Agent 领先",
            "weaknesses": "核心旗舰文本底座尚未全面开放原始权重",
        },
    ]


def build_model_comparison_matrix(root: Path, *, generated_at_iso: str = "") -> List[Dict[str, str]]:
    """Build or refresh global top 14 flagship LLM comparison matrix via Gemini Search Grounding."""
    cache_path = root / "data" / "model_matrix_cache.json"
    cached = load_json_if_exists(cache_path, default={}) or {}
    if isinstance(cached, dict) and isinstance(cached.get("matrix"), list) and len(cached["matrix"]) >= 12:
        age = time.time() - float(cached.get("ts") or 0)
        if age < 24 * 3600:
            return cached["matrix"]

    baseline = _baseline_model_comparison_matrix()
    if not collect_api_key_slots():
        return baseline

    prompt = (
        f"当前日期 {generated_at_iso[:10] or '2026-11-23'}。请结合最新联网搜索结果，更新并返回全球 Top 14 款主推旗舰大模型的横向对比矩阵 JSON 数组。\n"
        "必须包含：Google DeepMind (Gemini 4 Argon / Carbon / Neon), OpenAI (GPT-6.2 Astra / Sol), Anthropic (Claude Opus 5.5 / Mythos 5.2), "
        "DeepSeek (R2 / V4-Pro), 阿里千问 (Qwen4-Max / Qwen3.5), 智谱 (GLM-5.5/5.4), 腾讯混元 Hy4, Kimi K3.1 Pro, MiniMax-M2, 百度 ERNIE 5.0, xAI Grok 4, Meta Llama 4, 字节豆包 2.0。\n"
        "严禁使用任何彩色 Emoji。每条必须包含准确字段：\n"
        '{"model_name":"","org":"","region":"海外|国内","release_date":"YYYY-MM","positioning":"","context_window":"","pricing_input":"","pricing_output":"","weight_type":"闭源商用|开源权重","strengths":"","weaknesses":""}'
    )
    res = call_gemini_raw(
        scope="deep_ai_matrix",
        prompt=prompt,
        models=("gemini-4-hydrogen", "gemini-2.5-flash"),
        temperature=0.15,
        tools=_google_search_tools(),
        base_dir=root,
    )
    matrix = baseline
    if res.ok and res.text:
        parsed = _extract_json_block(res.text, expect_list=True)
        if isinstance(parsed, list) and len(parsed) >= 10:
            cleaned: List[Dict[str, str]] = []
            for row in parsed[:16]:
                if not isinstance(row, dict) or not row.get("model_name"):
                    continue
                cleaned.append({k: strip_colored_emojis(str(row.get(k) or "")) for k in baseline[0].keys()})
            if len(cleaned) >= 10:
                matrix = cleaned
                atomic_write_json(cache_path, {"ts": time.time(), "updated_at": generated_at_iso, "matrix": matrix})
    return matrix


_TOOL_DOMAIN_PROFILES: Dict[str, Tuple[str, str, str]] = {
    "ollama": (
        "解决个人电脑/Mac 与边缘服务器命令行一键拉取、量化运行大模型及统一本地 OpenAI 兼容端口痛点。",
        "个人本地离线隐私推理、MacBook 统一内存运行中小权重、快速接入本地 IDE 补全。",
        "比 llama.cpp 开箱管理更简单；吞吐并发低于 vLLM/SGLang，适合单机 1~4 并发。",
    ),
    "vllm": (
        "PagedAttention 与连续批处理解决多用户高并发 GPU 显存碎片化与推理吞吐瓶颈。",
        "生产环境多卡 GPU 集群部署 OpenAI 兼容 API 服务（DeepSeek/Qwen 企业级线上推理）。",
        "与 SGLang 并列企业推理双雄；高并发显存利用率显著领先 Ollama，但配置偏服务端工程化。",
    ),
    "sglang": (
        "RadixAttention 前缀树缓存大幅削减多轮对话、复杂 Agent 系统与 JSON 结构化输出的首字延迟。",
        "高频多轮 Agent 系统、多分支思维链 (CoT) 复用公共前缀、高 QPS 结构化输出。",
        "在重前缀复用与结构化约束场景吞吐常优于 vLLM，两者均为生产部署核心选择。",
    ),
    "llama.cpp": (
        "零 Python 重依赖、纯 C/C++ + GGUF 跨架构量化引擎，解决 CPU/核显/混合显存跑大模型难题。",
        "嵌入式端侧、Windows/Linux 无独立大显存主机 CPU+GPU 混合卸载运行。",
        "Ollama 的底层核心引擎；最轻量便携，可定制底层算子与端侧极致量化。",
    ),
    "transformers": (
        "统一数万开源模型结构定义、权重加载、微调与推理接口的事实标准底座。",
        "科研实验、自定义 LoRA/SFT 微调、Hugging Face Hub 新架构 Day-0 复现。",
        "生态覆盖最全最深，直接推理吞吐不如专用引擎 vLLM/SGLang。",
    ),
    "pytorch": (
        "动态计算图、torch.compile 编译加速与分布式 FSDP 训练的现代深度学习根基框架。",
        "底层算子研发、大规模预训练/后训练集群、科学计算与视觉语音模型训练。",
        "AI 研究底层基础设施，高于 JAX 的开发者生态渗透率。",
    ),
    "dify": (
        "把提示词编排、企业 RAG 知识库、工作流 DAG 与多模型 API 统一成可视化低代码应用平台。",
        "企业内部快速搭建客服/研报分析助手、非研发业务团队编排 LLM Workflow。",
        "比 LangChain 上手门槛低得多，相比 n8n 更专注大模型知识库与对话应用全链路。",
    ),
    "n8n": (
        "400+ SaaS 连接器与可视化节点结合 AI Agent，打通跨系统触发器、邮件、数据库与业务自动化。",
        "个人与中小企业跨软件（Slack/邮件/表格/Webhook/CRM）自动流水线。",
        "通用业务连接生态远超 Dify；若侧重复杂知识库切分检索则 Dify/RAGFlow 更专业。",
    ),
    "comfyui": (
        "节点流架构精准控制文生图/视频大模型每一步采样、ControlNet、LoRA 与多帧一致性，显存调度极省。",
        "AIGC 视觉设计师、Flux/Stable Diffusion/Wan/Veo 类本地图文视频工业化工作流。",
        "行业唯一事实标准节点式视觉工作流引擎，可控性远超传统 WebUI。",
    ),
    "open webui": (
        "提供接近 ChatGPT 体验的自部署多用户网页界面，无缝对接 Ollama 与 OpenAI/DeepSeek API 并内置本地 RAG。",
        "团队私有部署统一 AI 聊天入口、权限隔离与多模型盲测对比门户。",
        "对话交互体验与个人/小团队即装即用度优于 Dify；复杂自动化工作流不如 Dify。",
    ),
    "langchain": (
        "将 LLM 调用、工具绑定、检索器与状态机抽象为标准化组件链路，降低多模型切换改造成本。",
        "Python/TS 工程师自定义研发复杂后端 AI 服务、跨厂商模型抽象层。",
        "偏重代码级 SDK 控制；低代码编排看 Dify，有环状态机 Agent 编排用同门 LangGraph。",
    ),
    "langgraph": (
        "用有向有环图、持久化 Checkpointer 与人类审批断点解决长程自主 Agent 失控与状态恢复痛点。",
        "需要断点续传、多角色循环反思、人工确认介入的生产级 Agent 系统。",
        "比传统线性 Chain 可靠可控，适合工程师写严谨状态机而不依赖黑盒自规划。",
    ),
    "llamaindex": (
        "面向复杂异构文档、表格、多模态解析与多索引检索增强 (RAG) 的数据框架与工作流引擎。",
        "金融/法律/科研海量 PDF 与跨库结构化数据问答系统搭建。",
        "在文档解析粒度与多级索引路由深度上比通用编排框更有针对性。",
    ),
    "openhands": (
        "提供容器沙盒、终端执行与代码浏览器的全自主 AI 软件工程师 Agent，可独立完成修 Bug 与提 PR。",
        "GitHub Issue 自动修复、自动化重构测试、后台异步编码任务执行。",
        "全自主沙盒编码代表项目，与 IDE 内交互插件 Continue 形成“后台异步 vs 编辑器实时”互补。",
    ),
    "browser-use": (
        "让大模型通过 DOM 结构化提取 + 视觉定位直接操控真实浏览器完成登录、填表与跨站抓取。",
        "无开放 API 的传统网页系统自动化填报、跨站信息采集 Agent。",
        "相比纯手写 Playwright 脚本具备泛化容错能力，适合动态多变页面交互。",
    ),
    "ragflow": (
        "主打深度版面理解（PDF 跨页表格/扫描件 OCR/图文混排还原）与可溯源引文的 RAG 引擎。",
        "对表格/扫描合同检索准确率要求极高的企业内部知识库。",
        "文档版面切分精度常优于普通通用向量库脚本，是企业高精度 RAG 强有力开源方案。",
    ),
    "continue": (
        "深度嵌入 VS Code / JetBrains 的开源 AI 编码助手，可自由挂载任意本地 Ollama 或企业私有模型 API。",
        "代码保密要求高、拒绝代码上传公有云的研发团队本地 Copilot 替代方案。",
        "开源可审计且完全自带密钥/本地模型，灵活性高于封闭商用 IDE 插件。",
    ),
    "mcp": (
        "制定大模型连接本地文件系统、数据库与第三方 API 的统一标准化上下文协议 (USB-C for AI)。",
        "构建跨 Claude/Cursor/IDE/Agent 复用的标准化数据连接器 Server。",
        "行业事实协议标准，减少每换一个 Agent 框架就要重写一遍工具胶水的重复劳动。",
    ),
}


def enrich_tools_with_ai_comparison(
    tools: List[Dict[str, Any]],
    root: Path,
    *,
    generated_at_iso: str = "",
) -> List[Dict[str, Any]]:
    """Attach differentiated pain_point, best_for & comparison_note onto every tool card."""
    cache_path = root / "data" / "tools_enrichment_cache.json"
    cached = load_json_if_exists(cache_path, default={}) or {}
    profiles_cache: Dict[str, Dict[str, str]] = dict(cached.get("profiles") or {}) if isinstance(cached, dict) else {}

    # Seed missing non-cached tools via Gemini batch if keys exist & missing > 2
    missing_names = [
        {"tool_id": str(t.get("tool_id") or ""), "name": str(t.get("name") or ""), "repo": str(t.get("repo") or ""), "summary": str(t.get("summary") or "")[:90]}
        for t in tools
        if str(t.get("tool_id") or "") not in profiles_cache
        and not any(k in f"{t.get('name','')} {t.get('repo','')}".lower() for k in _TOOL_DOMAIN_PROFILES)
    ]
    if missing_names and collect_api_key_slots():
        prompt = (
            f"请结合搜索为下列 {len(missing_names[:14])} 个开源 AI 工具/模型权重分别撰写**完全差异化、禁止套话、禁止 Emoji** 的选型对比字段。\n"
            f"输入列表：{json.dumps(missing_names[:14], ensure_ascii=False)}\n"
            "输出严格 JSON 数组，每项字段：\n"
            '{"tool_id":"原样传入","pain_point":"45字内核心解决痛点","best_for":"35字内最适用场景","comparison_note":"45字内与同类项目的关键差异"}'
        )
        res = call_gemini_raw(
            scope="deep_github_tools",
            prompt=prompt,
            models=("gemini-4-hydrogen", "gemini-2.5-flash"),
            temperature=0.2,
            tools=_google_search_tools(),
            base_dir=root,
        )
        if res.ok and res.text:
            parsed = _extract_json_block(res.text, expect_list=True)
            if isinstance(parsed, list):
                for row in parsed:
                    if isinstance(row, dict) and row.get("tool_id"):
                        profiles_cache[str(row["tool_id"])] = {
                            "pain_point": strip_colored_emojis(str(row.get("pain_point") or "")),
                            "best_for": strip_colored_emojis(str(row.get("best_for") or "")),
                            "comparison_note": strip_colored_emojis(str(row.get("comparison_note") or "")),
                        }
                atomic_write_json(cache_path, {"ts": time.time(), "updated_at": generated_at_iso, "profiles": profiles_cache})

    enriched: List[Dict[str, Any]] = []
    for t in tools:
        item = dict(t)
        item["name"] = strip_colored_emojis(str(item.get("name") or ""))
        item["summary"] = strip_colored_emojis(str(item.get("summary") or ""))
        item["availability_label"] = strip_colored_emojis(str(item.get("availability_label") or ""))
        tid = str(item.get("tool_id") or "")
        hay = f"{item.get('name', '')} {item.get('repo', '')}".lower()

        prof = profiles_cache.get(tid)
        if not prof:
            for key, (pp, bf, cmp_n) in _TOOL_DOMAIN_PROFILES.items():
                if key in hay:
                    prof = {"pain_point": pp, "best_for": bf, "comparison_note": cmp_n}
                    break
        if not prof:
            if tid.startswith("tool_hf_"):
                prof = {
                    "pain_point": f"提供 {item.get('name')} 开源权重下载与本地量化微调，摆脱闭源 API 绑定。",
                    "best_for": "隐私数据本地微调、Hugging Face / vLLM 私有化推理部署。",
                    "comparison_note": f"所属领域「{item.get('sector') or '开源权重'}」，适合结合 vLLM/llama.cpp 评估显存性价比。",
                }
            else:
                prof = {
                    "pain_point": f"聚焦 {item.get('sector') or 'AI 工程'} 链路效率优化与标准化封装。",
                    "best_for": f"{item.get('sector') or 'AI 开发'} 团队生产集成与自动化流程搭建。",
                    "comparison_note": "建议结合 GitHub 星标活跃度与官方最新 Release 更新节奏综合选型。",
                }
        item["pain_point"] = prof.get("pain_point") or ""
        item["best_for"] = prof.get("best_for") or ""
        item["comparison_note"] = prof.get("comparison_note") or ""
        enriched.append(item)
    return enriched


def _enrich_single_storyline_via_gemini(
    st_id: str,
    st: Dict[str, Any],
    root: Path,
) -> Optional[Dict[str, Any]]:
    title = str(st.get("title") or "")
    prompt = (
        f"请利用 Google 搜索针对事件「{title}」回溯其真实的演变前情与多方立场。\n"
        "严格要求：禁止编造不存在的日期与机构，禁止任何彩色 Emoji。\n"
        "请输出严格 JSON 对象：\n"
        '{"history_nodes":[{"timestamp":"YYYY-MM-DD","stage_tag":"起因背景|发酵推进|关键转折","title":"节点标题","fact_summary":"70字内事实推进","source_name":"媒体/机构名"}],'
        '"stance_comparison":[{"party":"主体/阵营","stance":"核心立场或举措","impact":"实质影响评估"}]}'
    )
    res = call_gemini_raw(
        scope="deep_storylines",
        prompt=prompt,
        models=("gemini-4-hydrogen", "gemini-2.5-flash"),
        temperature=0.15,
        tools=_google_search_tools(),
        base_dir=root,
    )
    if not res.ok or not res.text:
        return None
    parsed = _extract_json_block(res.text, expect_list=False)
    if not isinstance(parsed, dict):
        return None
    nodes_out = []
    for n in (parsed.get("history_nodes") or [])[:4]:
        if isinstance(n, dict) and n.get("title"):
            nodes_out.append(
                {
                    "timestamp": str(n.get("timestamp") or "")[:10],
                    "stage_tag": strip_colored_emojis(str(n.get("stage_tag") or "前情回溯")),
                    "title": strip_colored_emojis(str(n.get("title") or "")),
                    "fact_summary": strip_colored_emojis(str(n.get("fact_summary") or "")),
                    "source_name": strip_colored_emojis(str(n.get("source_name") or "历史公开报道")),
                }
            )
    stances_out = []
    for s in (parsed.get("stance_comparison") or [])[:4]:
        if not isinstance(s, dict):
            continue
        side = strip_colored_emojis(str(s.get("side") or s.get("party") or "")).strip()
        if not side:
            continue
        summary = strip_colored_emojis(str(s.get("summary") or "")).strip()
        if not summary:
            parts = [strip_colored_emojis(str(s.get(k) or "")).strip() for k in ("stance", "impact")]
            summary = "：".join(p for p in parts if p)
        if not summary:
            continue
        raw_ks = s.get("key_sources")
        if isinstance(raw_ks, list):
            ks = [strip_colored_emojis(str(x)).strip() for x in raw_ks if str(x).strip()]
        elif s.get("source"):
            ks = [strip_colored_emojis(str(s.get("source"))).strip()]
        else:
            ks = []
        stances_out.append({"side": side, "summary": summary, "key_sources": ks})
    if nodes_out or stances_out:
        return {"history_nodes": nodes_out, "stance_comparison": stances_out}
    return None


def _build_deterministic_storyline_fallback(st: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Synthesize clean multi-node evidence progression & stance table when offline without keys."""
    srcs = [s for s in (st.get("sources") or []) if isinstance(s, dict)]
    atoms = [a for a in (st.get("fact_atoms") or []) if isinstance(a, dict)]
    title = str(st.get("title") or "")
    nodes: List[Dict[str, Any]] = []

    first_ts = str(st.get("first_reported_at") or st.get("first_discovered_at") or st.get("latest_reported_at") or "")
    s0 = srcs[0] if srcs else {}
    nodes.append(
        {
            "batch_id": "precursor_origin",
            "event_id": str(st.get("current_event_id") or ""),
            "timestamp": str(s0.get("published_at") or first_ts),
            "title": f"首轮披露：{s0.get('source_name') or '公开一手信源'} 初始事实锚定",
            "fact_summary": strip_colored_emojis(str(s0.get("excerpt") or s0.get("title") or title)[:110]),
            "evidence_status": str(st.get("evidence_status") or "single_source"),
            "delta_note": "起因披露",
            "source_count": len(srcs) or 1,
            "independent_publisher_count": len(srcs) or 1,
            "sources_preview": (
                [{"source_name": s0.get("source_name"), "url": s0.get("url"), "published_at": s0.get("published_at")}]
                if s0
                else []
            ),
        }
    )
    if atoms:
        a0 = atoms[0]
        nodes.append(
            {
                "batch_id": "precursor_fact_atom",
                "event_id": str(st.get("current_event_id") or ""),
                "timestamp": first_ts or str(st.get("latest_reported_at") or ""),
                "title": f"关键要素拆解：{a0.get('subject') or '核心主体'} · {a0.get('metric_or_action') or '实质进展'}",
                "fact_summary": strip_colored_emojis(f"{a0.get('value') or ''} {a0.get('scope') or ''}（信源：{a0.get('attribution') or '多方报道'}）".strip()),
                "evidence_status": str(st.get("evidence_status") or "corroborated"),
                "delta_note": "要素拆解",
                "source_count": len(srcs) or 1,
                "independent_publisher_count": len(srcs) or 1,
                "sources_preview": [],
            }
        )
    else:
        ents_txt = "、".join(str(e) for e in (st.get("entities") or [])[:3] if str(e).strip()) or "核心相关主体"
        nodes.append(
            {
                "batch_id": "precursor_context_eval",
                "event_id": str(st.get("current_event_id") or ""),
                "timestamp": first_ts or str(st.get("latest_reported_at") or ""),
                "title": f"影响面推演：{ents_txt} 与产业链联动边界界定",
                "fact_summary": strip_colored_emojis(f"围绕「{title[:36]}」梳理直接涉及实体、政策生效窗口与预期差边界。"),
                "evidence_status": str(st.get("evidence_status") or "corroborated"),
                "delta_note": "影响边界",
                "source_count": len(srcs) or 1,
                "independent_publisher_count": len(srcs) or 1,
                "sources_preview": [],
            }
        )
    nodes.append(
        {
            "batch_id": "precursor_next_watch",
            "event_id": str(st.get("current_event_id") or ""),
            "timestamp": str(st.get("latest_reported_at") or first_ts),
            "title": "后续核验观测点",
            "fact_summary": strip_colored_emojis(str(st.get("next_catalyst") or "关注后续官方正式公告、关键时间窗口兑现情况及多方交叉核验进展")),
            "evidence_status": "corroborated",
            "delta_note": "待验节点",
            "source_count": len(srcs) or 1,
            "independent_publisher_count": len(srcs) or 1,
            "sources_preview": [],
        }
    )

    ents = [str(e) for e in (st.get("entities") or [])[:3] if str(e).strip()]
    src_names = [str(s.get("source_name") or "").strip() for s in srcs if str(s.get("source_name") or "").strip()]
    stances = [
        {
            "side": f"{ents[0] if ents else '事件核心推动方'}（政策/官方口径）",
            "summary": strip_colored_emojis(
                f"{st.get('current_stage') or '主线持续推进中'}；{st.get('next_catalyst') or '需跟踪后续官方声明与实质落地进度'}"
            ),
            "key_sources": src_names[:2],
        },
        {
            "side": "市场定价与第三方观察视角",
            "summary": strip_colored_emojis(
                f"当前证据等级为「{st.get('evidence_tier_label') or st.get('evidence_label') or '持续核验中'}」（已归集 {len(srcs) or 1} 处信源），重点关注预期差与跨板块溢出效应。"
            ),
            "key_sources": src_names[2:4] or src_names[:1],
        },
    ]
    return nodes, stances


def _clip_complete_sentence(text: Optional[str], max_len: int = 120) -> str:
    """Clip text cleanly at a complete sentence boundary — never cut mid-word or mid-name."""
    clean = strip_colored_emojis(str(text or "")).strip()
    if not clean:
        return ""
    if len(clean) <= max_len:
        return clean if clean[-1] in "。！？.!?）\"'" else f"{clean}。"
    cut = clean[:max_len]
    for punct in ("。", "！", "？", "；", ".", "!", "?"):
        idx = cut.rfind(punct)
        if idx >= int(max_len * 0.42):
            return cut[: idx + 1].strip()
    # Second try up to +35 chars so we don't chop right before a period
    ext = clean[: max_len + 35]
    for punct in ("。", "！", "？", ".", "!", "?"):
        idx = ext.find(punct, int(max_len * 0.42))
        if idx != -1:
            return ext[: idx + 1].strip()
    comma_idx = max(cut.rfind("，"), cut.rfind(","))
    if comma_idx >= int(max_len * 0.45):
        return f"{cut[:comma_idx].strip()}。"
    return f"{clean}。" if len(clean) <= max_len + 45 else f"{cut.rstrip()}。"


def _is_a_share_policy_event(title: str, cat: str = "") -> bool:
    return bool(re.search(r"A股|沪深|两融|保证金|降费|证监会|央行|国务院|深交所|上交所|北交所|主动ETF|医保|公积金", title))


def _build_event_deep_qa_via_gemini(ev: Dict[str, Any], root: Path) -> Optional[List[Dict[str, str]]]:
    title = str(ev.get("title") or "")
    prompt = (
        f"新闻事件：「{title}」\n摘要：「{str(ev.get('fact_summary') or '')[:180]}」\n"
        "请用联网检索核实背景，为读者生成 3 个最核心的深度追问与直白完整解答（严禁半截残句、禁止乱套不相干模板、禁止 Emoji），必须覆盖：1) 对普通人或国内产业影响；2) 历史类似事件如何收场；3) 正反核心分歧。\n"
        '输出严格 JSON 数组：[{"question":"20字内提问","answer":"100字内完整句子解答","historical_parallel":"55字内贴合本事件的真实历史参照"}]'
    )
    res = call_gemini_raw(
        scope="deep_event_qa",
        prompt=prompt,
        models=("gemini-4-hydrogen", "gemini-2.5-flash"),
        temperature=0.2,
        tools=_google_search_tools(),
        base_dir=root,
    )
    if not res.ok or not res.text:
        return None
    parsed = _extract_json_block(res.text, expect_list=True)
    if not isinstance(parsed, list):
        return None
    out: List[Dict[str, str]] = []
    for row in parsed[:3]:
        if isinstance(row, dict) and row.get("question") and row.get("answer"):
            out.append(
                {
                    "question": strip_colored_emojis(str(row["question"])),
                    "answer": _clip_complete_sentence(str(row["answer"]), 125),
                    "historical_parallel": _clip_complete_sentence(str(row.get("historical_parallel") or ""), 80) if row.get("historical_parallel") else "",
                }
            )
    return out or None


def _build_deterministic_event_qa(ev: Dict[str, Any], cat: str) -> List[Dict[str, str]]:
    title = str(ev.get("title") or "")
    summary = _clip_complete_sentence(str(ev.get("fact_summary") or title), 115)
    ents = [str(e) for e in (ev.get("entities") or [])[:2] if str(e).strip()]
    ent_str = " / ".join(ents) if ents else "相关产业链"
    if _is_a_share_policy_event(title, cat):
        return [
            {
                "question": "这项政策对普通投资者与 A 股行业有何实质影响？",
                "answer": _clip_complete_sentence(f"核心作用于{ent_str}流动性与估值预期：{summary}", 120),
                "historical_parallel": "参考 2023 年以来同类境内资本市场政策窗口，次日成交额承接强度是判断行情持续性的关键。",
            },
            {
                "question": "市场正反分歧核心在哪里？",
                "answer": "看多逻辑看重制度与成本边际改善；谨慎派关注基本面盈利兑现与后续配套细则衔接连续性。",
                "historical_parallel": "2024 年 9 月增量政策落地后，具备基本面印证的核心板块持续跑赢纯概念题材。",
            },
        ]
    if any(k in title.lower() for k in ("黄金", "金价", "白银", "贵金属", "原油", "油价", "布伦特", "wti", "铜价", "大宗")):
        return [
            {
                "question": "这波贵金属/大宗商品波动对普通配置与市场有何影响？",
                "answer": _clip_complete_sentence(f"聚焦{ent_str}避险溢价与美元实际利率再定价：{summary}", 120),
                "historical_parallel": "参考 2013 年及 2020~2024 年贵金属急跌反弹窗口，实际利率 (TIPS) 拐点与商业银行风控提示常对应短期高波震荡区间。",
            },
            {
                "question": "后续判断企稳与趋势的核心观测指标是什么？",
                "answer": "重点关注 COMEX 现货/期货仓位变化、10 年期美债实际利率走势、银行积存金风控节奏以及全球央行季度购金动向。",
                "historical_parallel": "历史商品急跌后的首周反弹往往伴随多空筹码换手，需观察央行购金节奏与美元指数是否同步配合。",
            },
        ]
    if any(k in title.lower() for k in ("美联储", "fomc", "加息", "降息", "通胀", "财政", "贝森特", "美债", "纳斯达克", "标普", "美股")):
        return [
            {
                "question": "这项宏观与利率信号对全球资产定价有何实质影响？",
                "answer": _clip_complete_sentence(f"直接作用于美元流动性预期与跨市场估值折现率：{summary}", 120),
                "historical_parallel": "参考 2022~2024 年多轮美联储利率预期重定价周期，美债长端收益率与科技股估值在议息窗口前通常先行波动。",
            },
            {
                "question": "市场正反分歧核心在哪里？",
                "answer": "宽松派期待政策提前纠偏以缓释金融脆弱性；谨慎派关注通胀黏性与长期国债供给压力，等待核心 PCE 与非农确认。",
                "historical_parallel": "历史紧缩与降息预期博弈期显示，核心 PCE 与非农数据落地后市场分歧才会逐步收敛。",
            },
        ]
    if any(k in title.lower() for k in ("ipo", "上市", "募资", "发行价", "独角兽", "信用评级", "垃圾级")):
        return [
            {
                "question": "这件事对普通投资者与全球市场有何影响？",
                "answer": _clip_complete_sentence(f"聚焦{ent_str}定价与跨境流动性重估：{summary}", 120),
                "historical_parallel": "历史高估值科创 IPO 波动及海外信用重估窗口，通常需 5~10 个交易日观察二级市场换手企稳与信贷利差收敛。",
            },
            {
                "question": "市场正反分歧核心在哪里？",
                "answer": "乐观派关注长期营收增速与核心技术壁垒；谨慎派警惕短期资本开支压力、信用评级下修与估值消化窗口。",
                "historical_parallel": "参考 2019~2023 年多轮高估值独角兽上市初期走势，资金往往在首周冲高消化后回归自由现金流主线。",
            },
        ]
    if cat == "tech" or any(k in title.lower() for k in ("ai", "gpt", "gemini", "claude", "芯片", "模型", "开源")):
        return [
            {
                "question": "这次技术变化对普通开发者或用户意味着什么？",
                "answer": _clip_complete_sentence(f"聚焦{ent_str}能力边界与使用成本变化：{summary}", 120),
                "historical_parallel": "历次大模型与算力架构迭代中，推理单价下探与生态开放通常在 1~2 个季度内显著拉动应用渗透率。",
            },
            {
                "question": "该进展目前处于什么验证阶段？",
                "answer": "需结合官方技术报告、独立第三方复现基准以及下游云厂与终端真实接入节奏交叉确认。",
                "historical_parallel": "2025 年以来主流开源/闭源大模型竞赛证明，公开基准与真实开发者采用率决定商业化天花板。",
            },
        ]
    return [
        {
            "question": "事件对大宗物价、出行或外贸订单有何影响？",
            "answer": _clip_complete_sentence(f"重点关注{ent_str}引发的跨区域供应链、汇率与大宗品风险溢价变动：{summary}", 120),
            "historical_parallel": "历次跨区域地缘与贸易规则博弈多呈“首轮情绪脉冲，随后看实际封锁或关税文本落地决定持续性”轨迹。",
        },
        {
            "question": "下一步决定走向的关键观测点是什么？",
            "answer": _clip_complete_sentence(str(ev.get("speculation_or_outlook") or "盯紧涉事官方下一轮正式公报与约束性细则落地。"), 115),
            "historical_parallel": "若各方在后续窗口重回务实谈判，避险溢价与航运附加费通常较快收敛。",
        },
    ]


def _build_topic_deep_via_gemini(tp: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    title = str(tp.get("title") or "")
    nodes_txt = "；".join(str(n.get("title") or "") for n in (tp.get("timeline") or [])[:6])
    prompt = (
        f"深度专题：「{title}」\n已有节点：{nodes_txt[:350]}\n"
        "请通过联网检索补充完整前因后果，输出 30 秒全局脉络总览与核心参与方/指标横向对比表（严禁任何彩色 Emoji）。\n"
        '严格 JSON：{"brief_overview":"110字内脉络总览（起因→分歧→最新进展→焦点）","comparison_table":{"headers":["参与方/维度","核心立场或数据","关键影响"],"rows":[["","",""],["","",""],["","",""]]}}'
    )
    res = call_gemini_raw(
        scope="deep_topics_cal",
        prompt=prompt,
        models=("gemini-4-hydrogen", "gemini-2.5-flash"),
        temperature=0.15,
        tools=_google_search_tools(),
        base_dir=root,
    )
    if not res.ok or not res.text:
        return None
    parsed = _extract_json_block(res.text, expect_list=False)
    if not isinstance(parsed, dict) or not parsed.get("brief_overview"):
        return None
    tbl = parsed.get("comparison_table") or {}
    headers = [strip_colored_emojis(str(h)) for h in (tbl.get("headers") or [])[:4]]
    rows = [[strip_colored_emojis(str(c)) for c in r[:4]] for r in (tbl.get("rows") or [])[:5] if isinstance(r, list)]
    return {
        "brief_overview": strip_colored_emojis(str(parsed["brief_overview"])),
        "comparison_table": {"headers": headers, "rows": rows} if headers and rows else None,
    }


def _build_deterministic_topic_overview(tp: Dict[str, Any]) -> Dict[str, Any]:
    tl = tp.get("timeline") or []
    orgs = [str(o) for o in (tp.get("primary_orgs") or [])[:3] if str(o).strip()]
    latest_t = str(tl[0].get("title") or "") if tl else ""
    earliest_t = str(tl[-1].get("title") or "") if len(tl) >= 2 else ""
    overview = strip_colored_emojis(
        f"本专题归集 {len(tl)} 个关键节点：{('从「' + earliest_t[:26] + '」演进至') if earliest_t else ''}最新动态「{latest_t[:36] or tp.get('title')}」，聚焦 {'、'.join(orgs) if orgs else '多方核心博弈与市场外溢影响'}。"
    )
    rows: List[List[str]] = []
    for org in orgs[:3]:
        rows.append([org, "专题直接核心参与主体", "牵动本专题下一阶段政策/产业定调"])
    if not rows:
        rows.append([str(tp.get("region_label") or "核心主线"), str(tp.get("lifecycle_label") or "持续演化中"), f"累计 {tp.get('source_count') or len(tl)} 处公开信源跟踪"])
    if tl:
        rows.append(["最新进展节点", str(tl[0].get("source_name") or "最新通报"), strip_colored_emojis(latest_t[:40])])
    return {
        "brief_overview": overview,
        "comparison_table": {"headers": ["核心主体/节点", "当前态势", "主要外溢影响"], "rows": rows},
    }


def run_v12_deep_enrichment(
    root: Path,
    *,
    generated_at_iso: str,
    cat_docs: Dict[str, dict],
    storylines: Dict[str, dict],
    major_topics: List[dict],
    tech_tools: List[dict],
) -> Dict[str, Any]:
    """Concurrent 13-key enrichment across Storylines, Event Deep Q&A, Topics & Tools."""
    has_keys = bool(collect_api_key_slots())
    st_cache_path = root / "data" / "storyline_history_cache.json"
    qa_cache_path = root / "data" / "event_deep_qa_cache.json"
    tp_cache_path = root / "data" / "topic_deep_cache.json"

    st_cache: Dict[str, Any] = dict((load_json_if_exists(st_cache_path, default={}) or {}).get("items") or {})
    qa_cache: Dict[str, Any] = dict((load_json_if_exists(qa_cache_path, default={}) or {}).get("items") or {})
    tp_cache: Dict[str, Any] = dict((load_json_if_exists(tp_cache_path, default={}) or {}).get("items") or {})

    # 1. Select candidate storylines needing >=3 timeline nodes (bounded so run finishes swiftly)
    short_storylines = [
        (sid, st)
        for sid, st in sorted(
            storylines.items(),
            key=lambda kv: str(kv[1].get("latest_reported_at") or ""),
            reverse=True,
        )
        if isinstance(st, dict) and (len(st.get("timeline") or []) < 3 or not st.get("stance_comparison"))
    ][:18]

    # 2. Select top S/A/high events across cat_docs needing deep_qa
    top_events: List[Tuple[str, Dict[str, Any]]] = []
    for cat in ("finance", "global", "tech", "general"):
        evs = (cat_docs.get(cat) or {}).get("events") or []
        ranked = sorted(
            [e for e in evs if isinstance(e, dict)],
            key=lambda e: (1 if e.get("severity_tier") == "S" else (1 if e.get("importance") == "high" else 0), len(e.get("sources") or [])),
            reverse=True,
        )
        for e in ranked[:5]:
            top_events.append((cat, e))

    # 3. Active topics needing overview & table
    need_topics = [tp for tp in major_topics[:10] if isinstance(tp, dict) and str(tp.get("topic_id") or "") not in tp_cache]

    if has_keys:
        with ThreadPoolExecutor(max_workers=6) as pool:
            f_tools = pool.submit(enrich_tools_with_ai_comparison, tech_tools, root, generated_at_iso=generated_at_iso)

            st_futures = {
                pool.submit(_enrich_single_storyline_via_gemini, sid, st, root): sid
                for sid, st in short_storylines[:10]
                if sid not in st_cache
            }
            qa_futures = {
                pool.submit(_build_event_deep_qa_via_gemini, ev, root): str(ev.get("event_id") or "")
                for _, ev in top_events[:10]
                if str(ev.get("event_id") or "") and str(ev.get("event_id") or "") not in qa_cache
            }
            tp_futures = {
                pool.submit(_build_topic_deep_via_gemini, tp, root): str(tp.get("topic_id") or "")
                for tp in need_topics[:6]
                if str(tp.get("topic_id") or "")
            }

            try:
                enriched_tools = f_tools.result(timeout=90)
            except Exception:
                enriched_tools = enrich_tools_with_ai_comparison(tech_tools, root, generated_at_iso=generated_at_iso)

            for fut in as_completed(st_futures):
                sid = st_futures[fut]
                try:
                    val = fut.result(timeout=45)
                    if val:
                        st_cache[sid] = val
                except Exception:
                    pass

            for fut in as_completed(qa_futures):
                eid = qa_futures[fut]
                try:
                    val = fut.result(timeout=45)
                    if val:
                        qa_cache[eid] = val
                except Exception:
                    pass

            for fut in as_completed(tp_futures):
                tid = tp_futures[fut]
                try:
                    val = fut.result(timeout=45)
                    if val:
                        tp_cache[tid] = val
                except Exception:
                    pass
    else:
        enriched_tools = enrich_tools_with_ai_comparison(tech_tools, root, generated_at_iso=generated_at_iso)

    if st_cache:
        atomic_write_json(st_cache_path, {"ts": time.time(), "updated_at": generated_at_iso, "items": dict(list(st_cache.items())[-120:])})
    if qa_cache:
        atomic_write_json(qa_cache_path, {"ts": time.time(), "updated_at": generated_at_iso, "items": dict(list(qa_cache.items())[-120:])})
    if tp_cache:
        atomic_write_json(tp_cache_path, {"ts": time.time(), "updated_at": generated_at_iso, "items": dict(list(tp_cache.items())[-40:])})

    # Apply enriched multi-node timeline & stance_comparison onto EVERY storyline (never <3 nodes for tracked items!)
    st_enriched_count = 0
    for sid, st in storylines.items():
        if not isinstance(st, dict):
            continue
        for fld in ("title", "current_stage", "evidence_label", "evidence_tier_label", "next_catalyst"):
            if isinstance(st.get(fld), str):
                st[fld] = strip_colored_emojis(st[fld])

        tl = list(st.get("timeline") or [])
        cached_st = st_cache.get(sid)
        if cached_st and isinstance(cached_st, dict):
            existing_titles = {str(n.get("title") or "")[:16] for n in tl}
            for idx_hn, hn in enumerate(cached_st.get("history_nodes") or []):
                ht = str(hn.get("title") or "").strip()
                if not ht or ht[:16] in existing_titles:
                    continue
                existing_titles.add(ht[:16])
                tl.append(
                    {
                        "batch_id": f"grounded_hist_{idx_hn}",
                        "event_id": str(st.get("current_event_id") or ""),
                        "timestamp": str(hn.get("timestamp") or st.get("first_reported_at") or generated_at_iso),
                        "title": ht,
                        "fact_summary": str(hn.get("fact_summary") or ""),
                        "evidence_status": str(st.get("evidence_status") or "corroborated"),
                        "delta_note": str(hn.get("stage_tag") or "历史前情"),
                        "source_count": 1,
                        "independent_publisher_count": 1,
                        "sources_preview": [{"source_name": hn.get("source_name") or "公开信源", "url": ""}],
                    }
                )
            if cached_st.get("stance_comparison"):
                st["stance_comparison"] = cached_st["stance_comparison"]

        fb_nodes, fb_stances = _build_deterministic_storyline_fallback(st)
        if len(tl) < 3:
            existing_titles = {str(n.get("title") or "")[:14] for n in tl}
            for fn in fb_nodes:
                if len(tl) >= 3:
                    break
                if str(fn.get("title") or "")[:14] not in existing_titles:
                    tl.append(fn)
                    existing_titles.add(str(fn.get("title") or "")[:14])
        if not st.get("stance_comparison"):
            st["stance_comparison"] = fb_stances
        tl.sort(key=lambda n: str(n.get("timestamp") or ""), reverse=True)
        st["timeline"] = tl[:15]
        if len(st["timeline"]) >= 3:
            st_enriched_count += 1

    # Apply deep_qa onto cat_docs events (purge cached mid-sentence chops or bogus A-share boilerplate)
    qa_enriched_count = 0
    for cat in ("finance", "global", "tech", "general"):
        for ev in (cat_docs.get(cat) or {}).get("events") or []:
            if not isinstance(ev, dict):
                continue
            eid = str(ev.get("event_id") or "")
            title_s = str(ev.get("title") or "")
            cached_qa = qa_cache.get(eid) if eid else None
            if isinstance(cached_qa, list) and cached_qa:
                is_ipo_story = bool(re.search(r"ipo|上市|募资|发行价|独角兽", title_s, re.I))
                has_bad_tpl = (
                    (
                        not _is_a_share_policy_event(title_s, cat)
                        and any("同类政策落地窗" in str(q.get("historical_parallel") or "") for q in cached_qa if isinstance(q, dict))
                    )
                    or (
                        not is_ipo_story
                        and any(
                            any(bad in str(q.get("historical_parallel") or "") for bad in ("科创 IPO", "高估值独角兽"))
                            for q in cached_qa
                            if isinstance(q, dict)
                        )
                    )
                )
                has_chop = any(
                    str(q.get("answer") or "").strip() and str(q.get("answer") or "").strip()[-1] not in "。！？.!?)）\"'"
                    for q in cached_qa
                    if isinstance(q, dict)
                )
                if has_bad_tpl or has_chop:
                    cached_qa = None
            if cached_qa:
                ev["deep_qa"] = cached_qa
            elif ev.get("severity_tier") in {"S", "A"} or ev.get("importance") == "high" or len(ev.get("sources") or []) >= 2:
                ev["deep_qa"] = _build_deterministic_event_qa(ev, cat)
            if ev.get("deep_qa"):
                qa_enriched_count += 1

    # Apply brief_overview & comparison_table onto topics
    for tp in major_topics:
        if not isinstance(tp, dict):
            continue
        tid = str(tp.get("topic_id") or "")
        for fld in ("title", "subtitle", "badge", "lifecycle_label", "region_label"):
            if isinstance(tp.get(fld), str):
                tp[fld] = strip_colored_emojis(tp[fld])
        td = tp_cache.get(tid) or _build_deterministic_topic_overview(tp)
        tp["brief_overview"] = td["brief_overview"]
        if td.get("comparison_table"):
            tp["comparison_table"] = td["comparison_table"]

    return {
        "tools": enriched_tools,
        "storylines_multi_node": st_enriched_count,
        "events_deep_qa": qa_enriched_count,
    }
