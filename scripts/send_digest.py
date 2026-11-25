"""Optional zero-infrastructure Daily Digest Push (Bark / Feishu / WeCom / DingTalk / Telegram / Generic Webhook).

Silently exits 0 if no push secrets are configured in environment.
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
    site_url = os.environ.get("SITE_PUBLIC_URL", "https://mirrorinfo.xyz/").rstrip("/") + "/"

    lines = [f"【镜信 MirrorBrief 情报速览 · {batch_id}】"]

    topics_path = root / "data/topics.json"
    if topics_path.exists():
        tdoc = json.loads(topics_path.read_text(encoding="utf-8"))
        topics = tdoc.get("topics") or []
        if topics:
            lines.append("\n🔥 重点专题:")
            for tp in topics[:2]:
                tl = tp.get("timeline") or []
                latest_node = tl[-1]["title"] if tl else tp["subtitle"]
                lines.append(f"• {tp['title']}（{tp.get('source_count', 0)} 源）：{latest_node}")

    cat_names = {"global": "全球/宏观", "finance": "财经/市场", "tech": "科技/AI", "general": "社会/热点"}
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


def _post_webhook(url: str, text: str) -> bool:
    try:
        if "feishu.cn" in url or "larksuite.com" in url:
            payload = {"msg_type": "text", "content": {"text": text}}
        elif "qyapi.weixin.qq.com" in url or "oapi.dingtalk.com" in url:
            payload = {"msgtype": "text", "text": {"content": text}}
        else:
            payload = {"text": text, "content": text}
        r = requests.post(url, json=payload, timeout=10)
        print(f"Webhook digest push HTTP {r.status_code}")
        return 200 <= r.status_code < 300
    except Exception as exc:
        print(f"Webhook digest push failed (non-blocking): {exc}")
        return False


def send_digest(base_dir: Path | str = ".") -> bool:
    bark_url = (os.environ.get("BARK_URL") or "").strip()
    feishu_url = (os.environ.get("FEISHU_WEBHOOK") or "").strip()
    wecom_url = (os.environ.get("WECOM_WEBHOOK") or "").strip()
    digest_url = (os.environ.get("DIGEST_WEBHOOK_URL") or "").strip()
    tg_token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    tg_chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

    has_any = any([bark_url, feishu_url, wecom_url, digest_url, (tg_token and tg_chat)])
    if not has_any:
        print("No private push secrets configured (BARK_URL / FEISHU_WEBHOOK / WECOM_WEBHOOK / TELEGRAM_BOT_TOKEN); skipping.")
        return False

    text = build_digest_markdown(base_dir)
    site_url = os.environ.get("SITE_PUBLIC_URL", "https://mirrorinfo.xyz/").rstrip("/") + "/"
    sent = False

    if bark_url:
        try:
            body_short = "\n".join(text.splitlines()[:8])
            r = requests.post(
                bark_url,
                json={"title": "镜信 MirrorBrief 简报更新", "body": body_short, "url": site_url, "group": "镜信"},
                timeout=10,
            )
            print(f"Bark digest push HTTP {r.status_code}")
            sent = sent or (200 <= r.status_code < 300)
        except Exception as exc:
            print(f"Bark digest push failed (non-blocking): {exc}")

    for wh in dict.fromkeys(u for u in (feishu_url, wecom_url, digest_url) if u):
        sent = _post_webhook(wh, text) or sent

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
