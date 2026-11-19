"""Optional non-blocking bundle pusher: uploads fresh public JSON data to private ingest endpoint if configured in Secrets."""

from __future__ import annotations

import io
import os
import sys
import tarfile
from pathlib import Path

import requests


def main() -> int:
    ingest_url = (os.environ.get("TENCENT_INGEST_URL") or "").strip()
    ingest_token = (os.environ.get("TENCENT_INGEST_TOKEN") or "").strip()
    trigger_push = os.environ.get("TRIGGER_PUSH", "0").strip()
    if not ingest_url or not ingest_token:
        print("TENCENT_INGEST_URL / TENCENT_INGEST_TOKEN not configured; skipping active push (server timer will pull).")
        return 0

    root = Path.cwd()
    buf = io.BytesIO()
    include_paths = [
        "data",
        "history",
        "analysis_general.json",
        "analysis_global.json",
        "analysis_tech.json",
        "analysis_finance.json",
        "comments_general.json",
        "comments_global.json",
        "comments_tech.json",
        "comments_finance.json",
        "data_general.json",
        "data_global.json",
        "data_tech.json",
        "data_finance.json",
    ]
    # Also include active archive batch files referenced in data/manifest.json
    manifest_file = root / "data" / "manifest.json"
    if manifest_file.exists():
        import json

        try:
            m = json.loads(manifest_file.read_text(encoding="utf-8"))
            for info in ((m.get("smart") or {}).get("categories") or {}).values():
                if isinstance(info, dict):
                    for k in ("path", "comments_path"):
                        v = info.get(k)
                        if isinstance(v, str) and v:
                            include_paths.append(v.lstrip("./"))
        except Exception:
            pass
    count = 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel in dict.fromkeys(include_paths):
            p = root / rel
            if p.exists():
                tf.add(p, arcname=rel)
                count += 1

    url = ingest_url + ("&" if "?" in ingest_url else "?") + f"trigger_push={trigger_push}"
    resp = requests.post(
        url,
        headers={
            "X-Ingest-Token": ingest_token,
            "Content-Type": "application/gzip",
        },
        data=buf.getvalue(),
        timeout=30,
    )
    print(f"Ingest push HTTP {resp.status_code}: {resp.text[:300]}")
    return 0 if resp.status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
