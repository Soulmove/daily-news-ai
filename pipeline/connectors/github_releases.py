"""GitHub Releases API connector for core AI infrastructure & open-source model repositories."""

from __future__ import annotations

from datetime import timedelta
import os
import re
import time
from typing import Any, Dict, List, Optional

from pipeline.connectors.base import HttpCacheStore, polite_get
from pipeline.id_utils import make_raw_item_id
from pipeline.time_utils import now_shanghai, parse_iso_datetime, parse_published_at, to_iso_shanghai

DEFAULT_WATCHED_REPOS = [
    {"repo": "langgenius/dify", "name": "Dify", "entity_id": "ent_ai_infra_tools", "category": "Agentic 应用与工作流平台", "fallback_stars": 115000, "fallback_license": "Apache-2.0", "fallback_summary": "开源 LLM 应用开发平台，内置可视化 Agent 工作流 DAG、企业级 RAG 管道与多模型 API 统一网关。"},
    {"repo": "n8n-io/n8n", "name": "n8n", "entity_id": "ent_ai_infra_tools", "category": "AI 工作流自动化", "fallback_stars": 102000, "fallback_license": "Sustainable Use", "fallback_summary": "支持 400+ 系统连接器的可自托管 AI 工作流自动化编排平台，原生集成多步 LLM Agent 节点与触发器。"},
    {"repo": "comfyanonymous/ComfyUI", "name": "ComfyUI", "entity_id": "ent_ai_infra_tools", "category": "节点式多模态视觉引擎", "fallback_stars": 88000, "fallback_license": "GPL-3.0", "fallback_summary": "高性能节点图式文生图/文生视频推理界面，精准调控 Flux/Wan/Veo 采样器与低显存分块调度。"},
    {"repo": "open-webui/open-webui", "name": "Open WebUI", "entity_id": "ent_ai_infra_tools", "category": "开源模型对话门户", "fallback_stars": 92000, "fallback_license": "MIT", "fallback_summary": "功能完善的自部署 AI 对话与知识库门户，开箱兼容 Ollama 与 OpenAI/DeepSeek API，支持多用户权限管控。"},
    {"repo": "langchain-ai/langchain", "name": "LangChain", "entity_id": "ent_ai_infra_tools", "category": "LLM Agent 开发框架", "fallback_stars": 112000, "fallback_license": "MIT", "fallback_summary": "大模型应用开发标准组件库，提供统一模型调用接口、工具绑定协议与可观测评估链。"},
    {"repo": "langchain-ai/langgraph", "name": "LangGraph", "entity_id": "ent_ai_infra_tools", "category": "有环状态机 Agent 编排", "fallback_stars": 18000, "fallback_license": "MIT", "fallback_summary": "专为有状态、可恢复与人机协同长程多 Agent 系统设计的有向有环图状态机编排框架。"},
    {"repo": "ollama/ollama", "name": "Ollama", "entity_id": "ent_ai_infra_tools", "category": "本地大模型运行器", "fallback_stars": 187000, "fallback_license": "MIT", "fallback_summary": "一行命令在 macOS/Windows/Linux 本地拉取并量化运行 DeepSeek/Qwen/Llama 等主流开源模型权重。"},
    {"repo": "huggingface/transformers", "name": "Transformers", "entity_id": "ent_ai_infra_tools", "category": "模型加载与微调底座", "fallback_stars": 169000, "fallback_license": "Apache-2.0", "fallback_summary": "涵盖文本、视觉、音频与多模态大模型定义、权重加载及分布式微调训练的开源基础库。"},
    {"repo": "pytorch/pytorch", "name": "PyTorch", "entity_id": "ent_ai_infra_tools", "category": "深度学习核心框架", "fallback_stars": 105000, "fallback_license": "BSD-3-Clause", "fallback_summary": "主流 AI 训练与推理底层框架，支持 torch.compile 编译加速与超大规模集群并行训练。"},
    {"repo": "vllm-project/vllm", "name": "vLLM", "entity_id": "ent_ai_infra_tools", "category": "高并发推理引擎", "fallback_stars": 97000, "fallback_license": "Apache-2.0", "fallback_summary": "基于 PagedAttention 的高吞吐低延迟大模型推理与 OpenAI API 服务引擎，生产级显存利用率标杆。"},
    {"repo": "ggml-org/llama.cpp", "name": "llama.cpp", "entity_id": "ent_ai_infra_tools", "category": "端侧/混合量化推理", "fallback_stars": 136000, "fallback_license": "MIT", "fallback_summary": "零 Python 依赖的 C/C++ + GGUF 跨硬件极轻量量化推理引擎，支持 CPU 与 GPU 混合卸载执行。"},
    {"repo": "run-llama/llama_index", "name": "LlamaIndex", "entity_id": "ent_ai_infra_tools", "category": "异构文档 RAG 框架", "fallback_stars": 44000, "fallback_license": "MIT", "fallback_summary": "聚焦企业复杂文档解析、多模态结构化索引路由与 Agentic Workflow 的检索增强数据框架。"},
    {"repo": "All-Hands-AI/OpenHands", "name": "OpenHands", "entity_id": "ent_ai_infra_tools", "category": "自主 AI 软件工程师", "fallback_stars": 58000, "fallback_license": "MIT", "fallback_summary": "具备隔离容器沙盒、终端执行与代码编辑器的自主软件开发 Agent，可自动完成代码修改与单测修复。"},
    {"repo": "browser-use/browser-use", "name": "Browser-Use", "entity_id": "ent_ai_infra_tools", "category": "浏览器视觉操控 Agent", "fallback_stars": 62000, "fallback_license": "MIT", "fallback_summary": "结合 DOM 结构解析与视觉识别，让大模型像人类一样自主操作真实浏览器执行复杂任务。"},
    {"repo": "infiniflow/ragflow", "name": "RAGFlow", "entity_id": "ent_ai_infra_tools", "category": "深度文档版面 RAG 引擎", "fallback_stars": 56000, "fallback_license": "Apache-2.0", "fallback_summary": "基于深度文档版面理解的企业级开源 RAG 引擎，精准还原复杂 PDF 跨页表格并支持逐句溯源引文。"},
    {"repo": "continuedev/continue", "name": "Continue", "entity_id": "ent_ai_infra_tools", "category": "开源 IDE 编程助手", "fallback_stars": 28000, "fallback_license": "Apache-2.0", "fallback_summary": "可嵌入 VS Code / JetBrains 且完全自定义模型与本地 Ollama 接口的开源代码补全及 Agent 助手。"},
    {"repo": "sgl-project/sglang", "name": "SGLang", "entity_id": "ent_ai_infra_tools", "category": "结构化生成引擎", "fallback_stars": 38900, "fallback_license": "Apache-2.0", "fallback_summary": "依托 RadixAttention 前缀树缓存技术的高性能大模型与 Agent 结构化推理服务引擎。"},
    {"repo": "modelcontextprotocol/python-sdk", "name": "MCP Python SDK", "entity_id": "ent_anthropic", "category": "Agent 协议标准 SDK", "fallback_stars": 24900, "fallback_license": "MIT", "fallback_summary": "Model Context Protocol 官方 Python SDK，统一大模型连接外部数据源、工具和系统上下文接口。"},
    {"repo": "anthropics/anthropic-sdk-python", "name": "Anthropic SDK", "entity_id": "ent_anthropic", "category": "模型官方 SDK", "fallback_stars": 4100, "fallback_license": "MIT", "fallback_summary": "Claude 官方 Python 客户端 SDK，支持扩展思维链、计算机操控 Tool Use 与 Prompt Caching。"},
    {"repo": "openai/openai-python", "name": "OpenAI SDK", "entity_id": "ent_openai", "category": "模型官方 SDK", "fallback_stars": 32200, "fallback_license": "Apache-2.0", "fallback_summary": "OpenAI Responses API 与推理模型官方 Python 客户端 SDK，行业标准 API 兼容接口模板。"},
]

_PRERELEASE_TAG_RE = re.compile(r"(?:rc\d*|alpha|beta|preview|dev\d*)\b", re.I)


_RAW_NOISE_LINE_RE = re.compile(
    r"^(?:What's Changed|Highlights|TL;DR|Bug Fixes|Release Notes|New Features|Full Changelog(?:\s*:.*)?|Website(?:\s*:.*)?|Attestations(?:\s*:.*)?|Checksums(?:\s*:.*)?|Backwards Incompatible Changes|Deprecations|Features|Improvements|New models|"
    r"v?\d+\.\d+(?:\.\d+)?\s*(?:\(\d{4}-\d{2}-\d{2}\))?\s*|"
    r"\|.*\|.*|.*\b\d[\d,]*\s+(?:commits?|PRs?|contributors?)\b.*|.*\bby\s+@\S+.*|.*@(?:dependabot|github-actions)\[bot\].*|"
    r"(?:model|feat|fix|chore|refactor|ci|docs|test|build|perf|style|sycl|cuda|metal|vulkan|rpc|ggml|llm|cmd(?:/[a-z]+)?)\s*[:：].*|\S+\s+https?:\/\/github\.com\/.*|"
    r"[A-Za-z][A-Za-z0-9 _/-]{1,28}\s*:\s*)$",
    re.I,
)


def _clean_notes(body: Optional[str], max_len: int = 320) -> str:
    if not body:
        return ""
    stripped = re.sub(r"<[^>]+>", " ", body)
    # Strip linked markdown badges first: [![alt](img)](url)
    stripped = re.sub(r"\[\s*!\[[^\]]*\]\([^)]*\)\s*\]\([^)]*\)", " ", stripped)
    stripped = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = re.sub(r"[*`]+", "", stripped)
    lines = []
    for ln in stripped.splitlines():
        clean_ln = re.sub(r"\s+", " ", ln).strip().lstrip("#*-：:;； ").strip()
        clean_ln = re.sub(r"\s*\(#?\d{3,6}\)\s*$", "", clean_ln).strip()
        if len(clean_ln) <= 5 or _RAW_NOISE_LINE_RE.match(clean_ln):
            continue
        if re.match(r"^[A-Za-z][A-Za-z0-9 _/-]{1,24}\s*[:：]\s*$", clean_ln):
            continue
        if re.match(r"^(?:sycl|cuda|metal|vulkan|rpc|ggml|model|feat|fix|chore|eval|llm|cmd)\b[^:：]{0,20}[:：]", clean_ln, re.I):
            continue
        # Clean stray unmatched closing brackets at line boundaries
        if clean_ln.count("）") > clean_ln.count("（") and clean_ln.endswith(("）", "）。")):
            clean_ln = clean_ln.rstrip("。").rstrip("）").strip()
        if clean_ln.count(")") > clean_ln.count("(") and clean_ln.endswith((")", ").")):
            clean_ln = clean_ln.rstrip(".").rstrip(")").strip()
        if len(clean_ln) > 5:
            lines.append(clean_ln)
    joined = "；".join(lines[:4]).lstrip("；;:： ")
    if joined.count("）") > joined.count("（") and joined.endswith(("）", "）。")):
        joined = joined.rstrip("。").rstrip("）").strip()
    if len(joined) > max_len:
        return joined[: max_len - 1].rstrip() + "…"
    return joined


def _normalize_gh_license(license_name: Optional[str]) -> Optional[str]:
    if not license_name:
        return None
    if license_name.upper() in {"NOASSERTION", "OTHER"}:
        return "多许可证/自定义条款 (见仓库 LICENSE)"
    return license_name


def fetch_github_releases(
    cache: HttpCacheStore,
    *,
    watched_repos: List[dict] | None = None,
    previous_tools: List[dict] | None = None,
    previous_items: List[dict] | None = None,
) -> Dict[str, Any]:
    """Fetch official releases from GitHub REST API with conditional ETag caching."""
    repos = watched_repos or DEFAULT_WATCHED_REPOS
    now_dt = now_shanghai()
    fetched_iso = to_iso_shanghai(now_dt)
    t0 = time.monotonic()
    headers = {"Accept": "application/vnd.github+json"}
    gh_token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    prev_tool_by_repo = {str(t.get("repo") or ""): t for t in (previous_tools or []) if t.get("repo")}
    prev_items_by_repo = {}
    for pit in (previous_items or []):
        pfam = str(pit.get("publisher_family") or "")
        if pfam.startswith("github-"):
            prev_items_by_repo.setdefault(pfam.replace("github-", "", 1), []).append(pit)

    items: List[dict] = []
    tools: List[dict] = []
    errors: List[str] = []
    not_modified_hits = 0

    for spec in repos:
        repo = spec["repo"]
        rel_url = f"https://api.github.com/repos/{repo}/releases?per_page=2"
        repo_meta_url = f"https://api.github.com/repos/{repo}"

        res = polite_get(rel_url, headers=headers, cache=cache, timeout=(4, 8), expect_json=True)
        if res.status == "not_modified_304":
            not_modified_hits += 1
            if repo in prev_tool_by_repo:
                prev_t = dict(prev_tool_by_repo[repo])
                if prev_t.get("summary"):
                    prev_t["summary"] = _clean_notes(str(prev_t["summary"])) or "详见官方 Release 说明。"
                if not prev_t.get("stars"):
                    m_res = polite_get(repo_meta_url, headers=headers, cache=cache, timeout=(4, 8), expect_json=True)
                    if m_res.ok and isinstance(m_res.json_data, dict):
                        prev_t["stars"] = m_res.json_data.get("stargazers_count")
                        if not prev_t.get("license") and isinstance(m_res.json_data.get("license"), dict):
                            lic = m_res.json_data["license"]
                            prev_t["license"] = _normalize_gh_license(lic.get("spdx_id") or lic.get("name"))
                tools.append(prev_t)
            for pit in prev_items_by_repo.get(repo, []):
                pub_dt = parse_iso_datetime(pit.get("published_at")) if pit.get("published_at") else None
                if pub_dt and (now_dt - pub_dt) <= timedelta(days=10):
                    items.append(pit)
            continue
        if not res.ok or not isinstance(res.json_data, list):
            errors.append(f"{repo}: {res.error_message}")
            if repo in prev_tool_by_repo:
                tools.append(prev_tool_by_repo[repo])
            elif spec.get("fallback_summary"):
                tools.append(
                    {
                        "tool_id": f"tool_gh_{repo.replace('/', '_').lower()}",
                        "name": spec["name"],
                        "repo": repo,
                        "tool_type": "开源软件 / Agent 框架",
                        "sector": spec["category"],
                        "entity_id": spec["entity_id"],
                        "availability_stage": "ga",
                        "availability_label": "正式可用 (GA)",
                        "latest_version": "Mainline",
                        "version_published_at": fetched_iso,
                        "license": spec.get("fallback_license") or "Open Source",
                        "stars": spec.get("fallback_stars"),
                        "official_url": f"https://github.com/{repo}",
                        "release_url": f"https://github.com/{repo}/releases",
                        "docs_url": f"https://github.com/{repo}#readme",
                        "summary": re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+", "", str(spec["fallback_summary"])).strip(),
                        "deployment_requirements": "见官方 README 与 Release 安装依赖说明",
                        "pricing_or_cost": "开源免费",
                        "checked_at": fetched_iso,
                        "source_name": "GitHub Curated Catalog",
                        "source_url": f"https://github.com/{repo}",
                    }
                )
            continue

        # Also check repo metadata (license, stars) conservatively
        license_name = None
        stars = None
        m_res = polite_get(repo_meta_url, headers=headers, cache=cache, timeout=(4, 8), expect_json=True)
        if m_res.ok and isinstance(m_res.json_data, dict):
            lic = m_res.json_data.get("license")
            if isinstance(lic, dict):
                license_name = _normalize_gh_license(lic.get("spdx_id") or lic.get("name"))
            stars = m_res.json_data.get("stargazers_count")

        releases = res.json_data
        for idx, rel in enumerate(releases):
            if not isinstance(rel, dict):
                continue
            tag = str(rel.get("tag_name") or "").strip()
            html_url = str(rel.get("html_url") or f"https://github.com/{repo}/releases").strip()
            pub_iso, _ = parse_published_at(rel.get("published_at"), "github-releases")
            is_pre = bool(rel.get("prerelease")) or bool(_PRERELEASE_TAG_RE.search(tag))
            avail_stage = "beta" if is_pre else "ga"
            notes = _clean_notes(rel.get("body"))
            title = f"[GitHub Release] {spec['name']} 发布 {tag or rel.get('name', '新版本')}"

            if idx == 0:
                tools.append(
                    {
                        "tool_id": f"tool_gh_{repo.replace('/', '_').lower()}",
                        "name": spec["name"],
                        "repo": repo,
                        "tool_type": "开源软件 / 推理框架",
                        "sector": spec["category"],
                        "entity_id": spec["entity_id"],
                        "availability_stage": avail_stage,
                        "availability_label": "预览/候选版 (Beta)" if is_pre else "正式可用 (GA)",
                        "latest_version": tag,
                        "version_published_at": pub_iso,
                        "license": license_name,
                        "stars": stars,
                        "official_url": f"https://github.com/{repo}",
                        "release_url": html_url,
                        "docs_url": f"https://github.com/{repo}#readme",
                        "summary": re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+", "", notes).strip() or "详见官方 Release 说明。",
                        "deployment_requirements": "见官方 README 与 Release 安装依赖说明",
                        "pricing_or_cost": "开源免费",
                        "checked_at": fetched_iso,
                        "source_name": "GitHub Releases API",
                        "source_url": html_url,
                    }
                )
            pub_dt = parse_iso_datetime(pub_iso) if pub_iso else None
            # Only emit the latest release per repository into the news briefing feed to avoid build-number noise (e.g. b12427 + b12428)
            if idx == 0 and pub_dt and (now_dt - pub_dt) <= timedelta(days=7):
                items.append(
                    {
                        "item_id": make_raw_item_id("github-releases", html_url, title),
                        "source_id": "github-releases",
                        "source_name": "GitHub Releases 官方版本",
                        "source_kind": "repo_release",
                        "source_tier": "tech_material",
                        "publisher_family": f"github-{repo}",
                        "citable_as_news": True,
                        "category": "tech",
                        "title": title,
                        "url": html_url,
                        "canonical_url": html_url,
                        "published_at": pub_iso,
                        "published_at_source": "github_release_api",
                        "fetched_at": fetched_iso,
                        "excerpt": f"版本 {tag}（{'Pre-release/RC' if is_pre else '正式版'} | 许可: {license_name or '详见仓库'}）。{notes}".strip(),
                        "entity_ids": [spec["entity_id"]],
                    }
                )

    # Dynamic discovery: fetch trending high-star AI/Agent repositories (>30k stars)
    seen_repos = {str(t.get("repo") or "").lower() for t in tools if t.get("repo")}
    search_url = "https://api.github.com/search/repositories?q=ai+agent+OR+llm+stars:%3E30000&sort=stars&order=desc&per_page=8"
    s_res = polite_get(search_url, headers=headers, cache=cache, timeout=(4, 8), expect_json=True)
    if s_res.ok and isinstance(s_res.json_data, dict):
        added_extra = 0
        for item in s_res.json_data.get("items") or []:
            if added_extra >= 6 or len(tools) >= 24:
                break
            if not isinstance(item, dict):
                continue
            full_name = str(item.get("full_name") or "").strip()
            if not full_name or full_name.lower() in seen_repos:
                continue
            seen_repos.add(full_name.lower())
            lic_obj = item.get("license") if isinstance(item.get("license"), dict) else {}
            stars_val = int(item.get("stargazers_count") or 0)
            if stars_val < 30000:
                continue
            desc = re.sub(r"\s+", " ", str(item.get("description") or "")).strip()[:220]
            pushed_iso, _ = parse_published_at(item.get("pushed_at"), "github-releases")
            tools.append(
                {
                    "tool_id": f"tool_gh_{full_name.replace('/', '_').lower()}",
                    "name": str(item.get("name") or full_name.split("/")[-1]),
                    "repo": full_name,
                    "tool_type": "高星 AI 开源框架",
                    "sector": "高星 AI 基础设施与 Agent",
                    "entity_id": "ent_ai_infra_tools",
                    "availability_stage": "ga",
                    "availability_label": "正式可用 (GA)",
                    "latest_version": "Mainline GA",
                    "version_published_at": pushed_iso or fetched_iso,
                    "license": _normalize_gh_license(lic_obj.get("spdx_id") or lic_obj.get("name")),
                    "stars": stars_val,
                    "official_url": str(item.get("html_url") or f"https://github.com/{full_name}"),
                    "release_url": str(item.get("html_url") or f"https://github.com/{full_name}"),
                    "docs_url": f"https://github.com/{full_name}#readme",
                    "summary": desc or "GitHub 高星开源 AI 基础设施与 Agent 工程项目。",
                    "deployment_requirements": "见官方 README 安装说明",
                    "pricing_or_cost": "开源免费",
                    "checked_at": fetched_iso,
                    "source_name": "GitHub Stars Discovery",
                    "source_url": str(item.get("html_url") or f"https://github.com/{full_name}"),
                }
            )
            added_extra += 1

    status = "ok"
    if not items and errors and not_modified_hits == 0:
        status = "error"
    elif errors:
        status = "partial"
    elif not items and not_modified_hits > 0:
        status = "cached_304"

    return {
        "connector_id": "github-releases",
        "connector_name": "GitHub Releases 官方仓库版本日志",
        "source_tier": "tech_material",
        "status": status,
        "fetched_at": fetched_iso,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "item_count": len(items),
        "error_message": "; ".join(errors[:2]) if errors else None,
        "tos_note": "使用 GitHub REST v3 公共 API（带 ETag 条件请求避免冗余额度消耗）。",
        "items": items,
        "tech_tools": tools,
    }
