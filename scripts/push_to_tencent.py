"""Optional bundle pusher with retry, status persistence (`data/push_status.json`), and Actions diagnostics."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tarfile
import time
from typing import Any, Dict, Optional

import requests

from pipeline.manifest import atomic_write_json
from pipeline.time_utils import now_shanghai, to_iso_shanghai


def _write_push_status(root: Path, payload: Dict[str, Any]) -> None:
    try:
        atomic_write_json(root / "data" / "push_status.json", payload)
    except Exception:
        pass
    summary_file = (os.environ.get("GITHUB_STEP_SUMMARY") or "").strip()
    if summary_file:
        try:
            with open(summary_file, "a", encoding="utf-8") as fh:
                fh.write("\n### 🚀 Private Server Push Status\n")
                fh.write(
                    f"- **Status**: `{payload.get('status')}` | "
                    f"**HTTP**: `{payload.get('http_status')}` | "
                    f"**Files**: `{payload.get('files_bundled')}` | "
                    f"**Bytes**: `{payload.get('bytes_sent')}`\n"
                )
                if payload.get("error"):
                    fh.write(f"- **Error**: `{payload['error']}`\n")
        except Exception:
            pass


def main() -> int:
    root = Path.cwd()
    attempted_at = to_iso_shanghai(now_shanghai())
    ingest_url = (os.environ.get("TENCENT_INGEST_URL") or "").strip()
    ingest_token = (os.environ.get("TENCENT_INGEST_TOKEN") or "").strip()
    trigger_push = os.environ.get("TRIGGER_PUSH", "0").strip()
    if not ingest_url or not ingest_token:
        msg = "TENCENT_INGEST_URL / TENCENT_INGEST_TOKEN not configured; skipping active push (server timer will pull)."
        print(msg)
        _write_push_status(
            root,
            {
                "schema_version": "4.1",
                "attempted_at": attempted_at,
                "status": "skipped",
                "http_status": None,
                "error": None,
                "note": msg,
                "files_bundled": 0,
                "bytes_sent": 0,
                "trigger_push": trigger_push,
            },
        )
        return 0

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
        "feed.xml",
    ]
    manifest_file = root / "data" / "manifest.json"
    if manifest_file.exists():
        try:
            m = json.loads(manifest_file.read_text(encoding="utf-8"))
            for info in ((m.get("smart") or {}).get("categories") or {}).values():
                if isinstance(info, dict):
                    for k in ("path", "comments_path"):
                        v = info.get(k)
                        if isinstance(v, str) and v:
                            include_paths.append(v.lstrip("./"))
            raw_m = m.get("raw") or {}
            if isinstance(raw_m.get("meta_path"), str) and raw_m["meta_path"]:
                include_paths.append(raw_m["meta_path"].lstrip("./"))
            for info in (raw_m.get("categories") or {}).values():
                if isinstance(info, dict) and isinstance(info.get("path"), str) and info["path"]:
                    include_paths.append(info["path"].lstrip("./"))
        except Exception:
            pass

    count = 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel in dict.fromkeys(include_paths):
            p = root / rel
            if p.exists():
                tf.add(p, arcname=rel)
                count += 1

    payload_bytes = buf.getvalue()
    url = ingest_url + ("&" if "?" in ingest_url else "?") + f"trigger_push={trigger_push}"

    http_status: Optional[int] = None
    last_err: Optional[str] = None
    for attempt in range(2):
        try:
            resp = requests.post(
                url,
                headers={
                    "X-Ingest-Token": ingest_token,
                    "Content-Type": "application/gzip",
                },
                data=payload_bytes,
                timeout=30,
            )
            http_status = resp.status_code
            print(f"Ingest push attempt {attempt + 1} HTTP {resp.status_code}: {resp.text[:300]}")
            if resp.status_code < 400:
                _write_push_status(
                    root,
                    {
                        "schema_version": "4.1",
                        "attempted_at": attempted_at,
                        "status": "ok",
                        "http_status": http_status,
                        "error": None,
                        "files_bundled": count,
                        "bytes_sent": len(payload_bytes),
                        "trigger_push": trigger_push,
                    },
                )
                return 0
            last_err = f"HTTP {resp.status_code}: {resp.text[:160].strip()}"
            if resp.status_code < 500:
                break
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__}: {str(exc)[:160]}"
        if attempt == 0:
            time.sleep(2.0)

    print(f"::warning::Tencent ingest push failed: {last_err}")
    _write_push_status(
        root,
        {
            "schema_version": "4.1",
            "attempted_at": attempted_at,
            "status": "failed",
            "http_status": http_status,
            "error": last_err,
            "files_bundled": count,
            "bytes_sent": len(payload_bytes),
            "trigger_push": trigger_push,
        },
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
