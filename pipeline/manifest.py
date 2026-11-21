"""Atomic manifest and history index management."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

MANIFEST_PATH = Path("data/manifest.json")
RAW_INDEX_PATH = Path("history/raw_index.json")
SMART_INDEX_PATH = Path("history/smart_index.json")


def atomic_write_json(path: Path | str, payload: Any, indent: int = 2) -> None:
    """Write JSON atomically using a temporary file in the same directory and os.replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=indent)
            fh.write("\n")
        try:
            os.chmod(tmp_name, 0o644)
        except OSError:
            pass
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def load_json_if_exists(path: Path | str, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    with target.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_manifest(base_dir: Path | str = ".") -> Dict[str, Any]:
    path = Path(base_dir) / MANIFEST_PATH
    data = load_json_if_exists(path, default={})
    if not isinstance(data, dict):
        return {}
    return data


def save_manifest(manifest: Dict[str, Any], base_dir: Path | str = ".") -> None:
    path = Path(base_dir) / MANIFEST_PATH
    atomic_write_json(path, manifest)


def upsert_history_index(
    index_path: Path | str,
    entry: Dict[str, Any],
    max_entries: int = 500,
) -> List[Dict[str, Any]]:
    """Prepend or update a history index entry keyed by `path` without duplicating entries."""
    target = Path(index_path)
    existing = load_json_if_exists(target, default=[])
    if not isinstance(existing, list):
        existing = []

    rel_path = entry["path"]
    filtered = [item for item in existing if isinstance(item, dict) and item.get("path") != rel_path]
    updated = [entry] + filtered
    if len(updated) > max_entries:
        updated = updated[:max_entries]

    atomic_write_json(target, updated)
    return updated


def prune_old_archives(
    root: Path | str,
    index_rel_path: str,
    *,
    keep_latest: int = 48,
) -> int:
    """Prune old archive snapshot directories beyond `keep_latest` AND clean any orphaned snapshot folders."""
    base = Path(root)
    idx_path = base / index_rel_path
    entries = load_json_if_exists(idx_path, default=[])
    if not isinstance(entries, list):
        return 0

    kept = entries[:keep_latest]
    dropped = entries[keep_latest:]
    removed = 0
    archives_root = (base / "archives").resolve()

    def _remove_snapshot_dir(rel_str: str) -> bool:
        rel = str(rel_str or "").strip().strip("/")
        if not rel or not rel.startswith("archives/"):
            return False
        target_dir = (base / rel).resolve()
        if str(target_dir).startswith(str(archives_root)) and target_dir.exists() and target_dir.is_dir():
            shutil.rmtree(target_dir, ignore_errors=True)
            parent = target_dir.parent
            if parent != archives_root and parent.exists() and not any(parent.iterdir()):
                try:
                    parent.rmdir()
                except OSError:
                    pass
            return True
        return False

    for entry in dropped:
        if isinstance(entry, dict) and _remove_snapshot_dir(str(entry.get("path") or "")):
            removed += 1

    # Sweep orphaned YYYY-MM-DD/HH-MM archive folders on disk not referenced by `kept`
    kept_rels = {
        str(e.get("path") or "").strip().strip("/")
        for e in kept
        if isinstance(e, dict) and e.get("path")
    }
    kind_subdir = "raw" if "raw" in Path(index_rel_path).name else ("smart" if "smart" in Path(index_rel_path).name else None)
    if kind_subdir:
        kind_root = (archives_root / kind_subdir).resolve()
        if kind_root.exists() and kind_root.is_dir():
            for date_dir in list(kind_root.iterdir()):
                if not date_dir.is_dir():
                    continue
                for snap_dir in list(date_dir.iterdir()):
                    if not snap_dir.is_dir():
                        continue
                    rel_snap = f"archives/{kind_subdir}/{date_dir.name}/{snap_dir.name}"
                    if rel_snap not in kept_rels:
                        shutil.rmtree(snap_dir, ignore_errors=True)
                        removed += 1
                if date_dir.exists() and not any(date_dir.iterdir()):
                    try:
                        date_dir.rmdir()
                    except OSError:
                        pass

    if len(entries) > keep_latest:
        atomic_write_json(idx_path, kept)
    return removed
