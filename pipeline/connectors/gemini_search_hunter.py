"""Proactive AI & Global Breaking News Hunter powered by GitHub Actions Gemini + Google Search Grounding.

Runs automatically inside GitHub Actions using configured repository Secrets (rotating across
KEY_1..8, KEY_TECH, KEY_GLOBAL, KEY_FINANCE, KEY_GENERAL, GOOGLE_API_KEY), so end-users
never need to enter their own API keys on the frontend.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.connectors.base import HttpCacheStore
from pipeline.id_utils import canonicalize_url, make_raw_item_id
from pipeline.time_utils import now_shanghai, to_iso_shanghai


_KEY_NAMES = (
    "KEY_TECH", "KEY_GLOBAL", "KEY_FINANCE", "KEY_GENERAL", "GOOGLE_API_KEY",
    "KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_6", "KEY_7", "KEY_8",
)


def _collect_all_keys() -> List[str]:
    keys: List[str] = []
    for name in _KEY_NAMES:
        val = (os.environ.get(name) or "").strip()
        if val and val not in keys:
            keys.append(val)
    return keys


def fetch_gemini_search_breaking_news(
    cache: Optional[HttpCacheStore] = None,
    *,
    base_dir: Path | str = ".",
) -> Dict[str, Any]:
    """Use Gemini Google Search Grounding in CI to catch zero-lag AI models, GitHub drops & global events."""
    del cache
    t0 = time.monotonic()
    fetched_dt = now_shanghai()
    fetched_iso = to_iso_shanghai(fetched_dt)
    keys = _collect_all_keys()
    root = Path(base_dir)
    stamp_path = root / ".http_cache" / "gemini_hunter_last.json"

    if not keys:
        return {
            "connector_id": "gemini-search-hunter",
            "connector_name": "GitHub 云端 AI 搜索雷达 (待密钥环境触发)",
            "source_tier": "direct_media",
            "status": "ok",
            "fetched_at": fetched_iso,
            "latency_ms": 0,
            "item_count": 0,
            "calendar_count": 0,
            "error_message": None,
            "tos_note": "仅在配置了仓库 Gemini Secrets 的 GitHub Actions 环境中自动联网检索，不消耗用户端密钥。",
            "items": [],
        }

    # Throttle to max 1 proactive search cycle per 40 minutes to stay comfortably inside free-tier quotas (20 RPD/key)
    try:
        if stamp_path.exists():
            prev = json.loads(stamp_path.read_text(encoding="utf-8"))
            age_sec = time.time() - float(prev.get("ts") or 0)
            if age_sec < 2400 and isinstance(prev.get("items"), list):
                return {
                    "connector_id": "gemini-search-hunter",
                    "connector_name": f"GitHub 云端 AI 搜索雷达 (缓存复用 {len(prev['items'])} 条)",
                    "source_tier": "direct_media",
                    "status": "cached_304",
                    "fetched_at": fetched_iso,
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                    "item_count": len(prev["items"]),
                    "calendar_count": 0,
                    "error_message": None,
                    "tos_note": "由 GitHub Actions 定时调用 Google Search Grounding 自动采集并推送腾讯云。",
                    "items": prev["items"],
                }
    except Exception:
        pass

    today_str = fetched_dt.strftime("%Y-%m-%d")
    prompt = (
        f"当前北京时间日期为 {today_str}。请利用 Google 搜索检索过去 24 小时内最新发生的全球重大突发与前沿科技动态，"
        "重点查明：1) Google Gemini（如 Neon/Carbon/Hydrogen/Gemma）、OpenAI、Anthropic Claude、阿里千问 Qwen、DeepSeek、Kimi、腾讯混元最新模型或 GitHub 热门开源 AI 工具发布；"
        "2) 美联储、A股/美股/黄金关税与重大外交峰会突发。\n"
        "请输出严格 JSON 数组（8–12 条），每条字段：\n"
        '{"category":"tech|finance|global","title":"简洁准确的中文新闻标题","summary":"80字内中文事实摘要","source_name":"原始媒体/官方机构名","url":"https://真实原文URL","published_date":"YYYY-MM-DD"}'
    )

    items: List[dict] = []
    used_err: Optional[str] = None
    try:
        from google import genai
        from google.genai import types

        for api_key in keys[:6]:
            client = genai.Client(api_key=api_key)
            for model_name in ("gemini-4-hydrogen", "gemini-2.5-flash"):
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            tools=[types.Tool(google_search=types.GoogleSearch())],
                            temperature=0.15,
                        ),
                    )
                    m = re.search(r"\[[\s\S]*\]", resp.text or "")
                    if not m:
                        continue
                    rows = json.loads(m.group(0))
                    if not isinstance(rows, list):
                        continue
                    for r in rows[:14]:
                        if not isinstance(r, dict) or not r.get("title"):
                            continue
                        title = str(r["title"]).strip()
                        canon = canonicalize_url(r.get("url"))
                        if not canon or "vertexaisearch.cloud.google.com" in canon:
                            continue
                        cat = str(r.get("category") or "tech").lower()
                        if cat not in {"tech", "finance", "global", "general"}:
                            cat = "tech"
                        src_name = str(r.get("source_name") or "Google Search AI Radar").strip()
                        excerpt = str(r.get("summary") or "").strip()
                        items.append(
                            {
                                "item_id": make_raw_item_id("gemini-search", canon, title),
                                "source_id": "gemini-search-hunter",
                                "source_name": f"{src_name} (AI搜索雷达)",
                                "category": cat,
                                "source_kind": "news",
                                "source_tier": "direct_media",
                                "publisher_family": f"gsearch-{re.sub(r'[^a-z0-9]', '', src_name.lower())[:16] or 'web'}",
                                "citable_as_news": True,
                                "title": title,
                                "url": canon,
                                "canonical_url": canon,
                                "published_at": fetched_iso,
                                "published_at_source": "search_grounding",
                                "fetched_at": fetched_iso,
                                "excerpt": excerpt or None,
                                "metric_label": "AI 搜索雷达",
                            }
                        )
                    if items:
                        break
                except Exception as exc:
                    used_err = f"{type(exc).__name__}: {str(exc)[:80]}"
            if items:
                break
    except Exception as exc:
        used_err = f"{type(exc).__name__}: {str(exc)[:80]}"

    if items:
        try:
            stamp_path.parent.mkdir(parents=True, exist_ok=True)
            stamp_path.write_text(
                json.dumps({"ts": time.time(), "items": items}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    return {
        "connector_id": "gemini-search-hunter",
        "connector_name": f"GitHub 云端 AI 搜索雷达 ({len(items)} 条)",
        "source_tier": "direct_media",
        "status": "ok" if items else ("error" if used_err else "empty"),
        "fetched_at": fetched_iso,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "item_count": len(items),
        "calendar_count": 0,
        "error_message": None if items else used_err,
        "tos_note": "通过 GitHub Actions 内置密钥调用 Google Search Grounding 自动采集全球新闻与开源动态。",
        "items": items,
    }
