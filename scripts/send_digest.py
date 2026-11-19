"""Optional zero-infrastructure Daily Digest Push (Feishu / WeCom / DingTalk / Telegram / Generic Webhook).

Silently exits 0 if no webhook/telegram secrets are configured in environment.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import requests


def build_digest_markdown(base_dir: Path | str = ".") -> str:
    root = Path(base_dir)
    manifest = json.loads((root / "data/manifest.json").read_text(encoding="utf-8"))
    smart = manifest.get("smart") or {}
    batch_id = smart.get("latest_batch_id", "latest")
    site_url = os.environ.get("SITE_PUBLIC_URL", "https://soulmove.github.io/daily-news-ai/").rstrip("/") + "/"

    lines = [f"【Insight Pro 情报速览 · {batch_id}】"]

    topics_path = root / "data/topics.json"
    if topics_path.exists():
        tdoc = json.loads(topics_path.read_text(encoding="utf-8"))
        topics = tdoc.get("topics") or []
        if topics:
            lines.append("\n🔥 超级专题:")
            for tp in topics[:2]:
                tl = tp.get("timeline") or []
                latest_node = tl[-1]["title"] if tl else tp["subtitle"]
                lines.append(f"• {tp['title']}（{tp.get('source_count', 0)} 源）：{latest_node}")

    cat_names = {"global": "国际/宏观", "finance": "财经/市场", "tech": "科技/AI", "general": "社会/热点"}
    for cat in ["global", "finance", "tech", "general"]:
        p = root / f"analysis_{cat}.json"
        if not p.exists():
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        evs = (doc.get("events") or [])[:2]
        if evs:
            lines.append(f"\n📌 {cat_names[cat]}:")
            for ev in evs:
                lines.append(f"• {ev['title']}")

    lines.append(f"\n🌐 完整工作台：{site_url}")
    return "\n".join(lines)


def send_digest(base_dir: Path | str = ".") -> bool:
    webhook_url = (os.environ.get("DIGEST_WEBHOOK_URL") or "").strip()
    tg_token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    tg_chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

    if not webhook_url and not (tg_token and tg_chat):
        print("No DIGEST_WEBHOOK_URL or TELEGRAM_BOT_TOKEN configured; skipping digest push.")
        return False

    text = build_digest_markdown(base_dir)
    sent = False

    if webhook_url:
        try:
            # Compatible with Feishu, DingTalk, WeCom & generic JSON webhooks
            if "feishu.cn" in webhook_url or "larksuite.com" in webhook_url:
                payload = {"msg_type": "text", "content": {"text": text}}
            elif "qyapi.weixin.qq.com" in webhook_url or "oapi.dingtalk.com" in webhook_url:
                payload = {"msgtype": "text", "text": {"content": text}}
            else:
                payload = {"text": text, "content": text}
            r = requests.post(webhook_url, json=payload, timeout=10)
            print(f"Webhook digest push HTTP {r.status_code}")
            sent = sent or (200 <= r.status_code < 300)
        except Exception as exc:
            print(f"Webhook digest push failed (non-blocking): {exc}")

    if tg_token and tg_chat:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                json={"chat_id": tg_chat, "text": text, "disable_web_page_preview": True},
                timeout=10,
            )
            print(f"Telegram digest push HTTP {r.status_code}")
            sent = sent or (200 <= r.status_code < 300)
        except Exception as exc:
            print(f"Telegram digest push failed (non-blocking): {exc}")

    return sent


if __name__ == "__main__":
    send_digest(".")
