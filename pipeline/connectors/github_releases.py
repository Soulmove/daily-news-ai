"""GitHub Releases API connector for core AI infrastructure & open-source model repositories."""

from __future__ import annotations

from datetime import timedelta
import re
import time
from typing import Any, Dict, List, Optional

from pipeline.connectors.base import HttpCacheStore, polite_get
from pipeline.id_utils import make_raw_item_id
from pipeline.time_utils import now_shanghai, parse_iso_datetime, parse_published_at, to_iso_shanghai

DEFAULT_WATCHED_REPOS = [
    {"repo": "vllm-project/vllm", "name": "vLLM", "entity_id": "ent_ai_infra_tools", "category": "AI 推理引擎"},
    {"repo": "ggml-org/llama.cpp", "name": "llama.cpp", "entity_id": "ent_ai_infra_tools", "category": "端侧/本地推理"},
    {"repo": "huggingface/transformers", "name": "Transformers", "entity_id": "ent_ai_infra_tools", "category": "模型加载框架"},
    {"repo": "pytorch/pytorch", "name": "PyTorch", "entity_id": "ent_ai_infra_tools", "category": "深度学习框架"},
    {"repo": "sgl-project/sglang", "name": "SGLang", "entity_id": "ent_ai_infra_tools", "category": "结构化生成引擎"},
    {"repo": "ollama/ollama", "name": "Ollama", "entity_id": "ent_ai_infra_tools", "category": "本地大模型运行器"},
    {"repo": "modelcontextprotocol/python-sdk", "name": "MCP Python SDK", "entity_id": "ent_anthropic", "category": "Agent 协议 SDK"},
    {"repo": "anthropics/anthropic-sdk-python", "name": "Anthropic SDK", "entity_id": "ent_anthropic", "category": "模型官方 SDK"},
    {"repo": "openai/openai-python", "name": "OpenAI SDK", "entity_id": "ent_openai", "category": "模型官方 SDK"},
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
                        "summary": notes or "详见官方 Release 说明。",
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
