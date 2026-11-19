"""Freshness watchdog and compensation helper for GitHub Actions workflows."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from pipeline.fetch_raw import fetch_raw_snapshot
from pipeline.manifest import load_manifest
from pipeline.time_utils import now_shanghai, parse_iso_datetime


def ensure_fresh_raw_snapshot(base_dir: Path | str = ".", max_age_minutes: int = 45, schedule_source: str = "ai_compensation_crawl") -> int:
    """
    Check latest raw snapshot age. If missing or older than max_age_minutes,
    run a fresh crawl before downstream AI analysis consumes stale inputs.
    """
    root = Path(base_dir)
    manifest = load_manifest(root)
    raw = manifest.get("raw", {}) if isinstance(manifest, dict) else {}
    fetched_dt = parse_iso_datetime(raw.get("fetched_at"))
    now = now_shanghai()

    if fetched_dt is None:
        print("⚠️ No V2 raw manifest found; triggering fresh compensation crawl...")
        fetch_raw_snapshot(root, schedule_source=schedule_source)
        return 0

    age_minutes = (now - fetched_dt).total_seconds() / 60.0
    print(f"Latest raw batch {raw.get('latest_batch_id')} age: {age_minutes:.1f} min (threshold: {max_age_minutes} min)")
    if age_minutes > max_age_minutes:
        print("🔄 Raw snapshot exceeds freshness threshold; running compensation crawl first...")
        fetch_raw_snapshot(root, schedule_source=schedule_source)
    else:
        print("✅ Raw snapshot is fresh enough; proceeding with existing batch.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure raw snapshot freshness before AI briefing")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--max-age-minutes", type=int, default=45)
    parser.add_argument("--schedule-source", default="ai_compensation_crawl")
    args = parser.parse_args()
    return ensure_fresh_raw_snapshot(args.base_dir, max_age_minutes=args.max_age_minutes, schedule_source=args.schedule_source)


if __name__ == "__main__":
    sys.exit(main())
