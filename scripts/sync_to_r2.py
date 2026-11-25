"""Incremental Cloudflare R2 S3-API uploader with immutable archive caching & atomic manifest publish.

Uploads active data/*.json, root JSONs, history/*.json, and archives/ to R2 (`mirrorbrief-data`),
skipping unchanged files via ETag==MD5 matching, and ALWAYS uploading `data/manifest.json` VERY LAST.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse
import xml.etree.ElementTree as ET

import requests


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def guess_content_type(rel_path: str) -> str:
    if rel_path.endswith(".json"):
        return "application/json; charset=utf-8"
    if rel_path.endswith(".xml"):
        return "application/xml; charset=utf-8"
    if rel_path.endswith(".ics"):
        return "text/calendar; charset=utf-8"
    if rel_path.endswith(".txt"):
        return "text/plain; charset=utf-8"
    guessed, _ = mimetypes.guess_type(rel_path)
    return guessed or "application/octet-stream"


def cache_control_for_key(rel_path: str) -> str:
    """Return strict Cache-Control header: immutable 1-year for timestamped archives, 60s for active data."""
    clean = rel_path.lstrip("./")
    if (clean.startswith("archives/smart/20") or clean.startswith("archives/raw/20")) and clean.endswith(".json"):
        return "public, max-age=31536000, immutable"
    return "public, max-age=60"


def collect_sync_files(base_dir: Path, scope: str = "full", full_archives: bool = False) -> List[Path]:
    """Collect ordered relative paths to sync, guaranteeing `data/manifest.json` is strictly LAST."""
    ordered: List[Path] = []
    seen = set()

    def add_rel(rel: str) -> None:
        clean = rel.lstrip("./")
        p = base_dir / clean
        if clean not in seen and p.is_file():
            seen.add(clean)
            ordered.append(Path(clean))

    # 1. Core active files (manifest.json deferred strictly to the end)
    root_jsons = (
        ["data_general.json", "data_global.json", "data_tech.json", "data_finance.json"]
        if scope == "raw"
        else [
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
    )
    for rj in root_jsons:
        add_rel(rj)

    data_dir = base_dir / "data"
    if data_dir.exists():
        for fp in sorted(data_dir.rglob("*")):
            if fp.is_file():
                rel = fp.relative_to(base_dir).as_posix()
                if rel != "data/manifest.json":
                    add_rel(rel)

    history_dir = base_dir / "history"
    if history_dir.exists():
        for fp in sorted(history_dir.rglob("*.json")):
            if fp.is_file():
                add_rel(fp.relative_to(base_dir).as_posix())

    # 2. Referenced archive batches + index files
    add_rel("archives/smart/index.json")
    add_rel("archives/raw/index.json")

    manifest_file = base_dir / "data" / "manifest.json"
    if manifest_file.exists():
        try:
            m = json.loads(manifest_file.read_text(encoding="utf-8"))
            for section_key in ("raw", "smart"):
                sec = m.get(section_key) or {}
                if isinstance(sec.get("meta_path"), str) and sec["meta_path"]:
                    add_rel(sec["meta_path"])
                for info in (sec.get("categories") or {}).values():
                    if isinstance(info, dict):
                        for k in ("path", "comments_path"):
                            if isinstance(info.get(k), str) and info[k]:
                                add_rel(info[k])
        except Exception:
            pass

    archives_dir = base_dir / "archives"
    if archives_dir.exists():
        if full_archives:
            for fp in sorted(archives_dir.rglob("*.json")):
                if fp.is_file():
                    add_rel(fp.relative_to(base_dir).as_posix())
        else:
            # Also sync the 3 newest timestamped folders in smart/ and raw/ for timeline browsing
            for kind in ("raw", "smart"):
                kdir = archives_dir / kind
                if kdir.exists():
                    subs = sorted([d for d in kdir.iterdir() if d.is_dir() and d.name.startswith("20")], reverse=True)[:3]
                    for sub in subs:
                        for fp in sorted(sub.glob("*.json")):
                            add_rel(fp.relative_to(base_dir).as_posix())

    # 3. VERY LAST: data/manifest.json so readers never see partial batches
    if manifest_file.exists():
        seen.discard("data/manifest.json")
        ordered.append(Path("data/manifest.json"))

    return ordered


class _SigV4Client:
    """Minimal dependency-free S3v4 R2 client fallback when boto3 is not installed locally."""

    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        parsed = urlparse(self.endpoint)
        self.host = parsed.netloc
        self.scheme = parsed.scheme or "https"

    def _sign_headers(self, method: str, canonical_uri: str, query_str: str, payload: bytes, extra_headers: Dict[str, str]) -> Dict[str, str]:
        now = dt.datetime.now(dt.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(payload).hexdigest()

        headers_lower = {
            "host": self.host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        for k, v in extra_headers.items():
            headers_lower[k.lower()] = v.strip()

        sorted_keys = sorted(headers_lower.keys())
        canonical_headers = "".join(f"{k}:{headers_lower[k]}\n" for k in sorted_keys)
        signed_headers = ";".join(sorted_keys)
        canonical_req = f"{method}\n{canonical_uri}\n{query_str}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

        scope = f"{date_stamp}/auto/s3/aws4_request"
        string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{hashlib.sha256(canonical_req.encode('utf-8')).hexdigest()}"

        def _hmac(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        k_date = _hmac(("AWS4" + self.secret_key).encode("utf-8"), date_stamp)
        k_region = _hmac(k_date, "auto")
        k_service = _hmac(k_region, "s3")
        k_signing = _hmac(k_service, "aws4_request")
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        auth = f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, SignedHeaders={signed_headers}, Signature={signature}"
        return {**extra_headers, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash, "Authorization": auth}

    def list_etags(self) -> Dict[str, str]:
        etags: Dict[str, str] = {}
        token: Optional[str] = None
        while True:
            params = [("list-type", "2"), ("max-keys", "1000")]
            if token:
                params.append(("continuation-token", token))
            params.sort()
            qs = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in params)
            uri = f"/{self.bucket}"
            headers = self._sign_headers("GET", uri, qs, b"", {})
            r = requests.get(f"{self.scheme}://{self.host}{uri}?{qs}", headers=headers, timeout=20)
            if not r.ok:
                break
            root = ET.fromstring(r.text)
            ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
            for c in root.findall(".//s3:Contents", ns) or root.findall(".//Contents"):
                k_el = c.find("s3:Key", ns) or c.find("Key")
                e_el = c.find("s3:ETag", ns) or c.find("ETag")
                if k_el is not None and e_el is not None and k_el.text and e_el.text:
                    etags[k_el.text] = e_el.text.strip('"')
            trunc = root.find("s3:IsTruncated", ns) or root.find("IsTruncated")
            next_tok = root.find("s3:NextContinuationToken", ns) or root.find("NextContinuationToken")
            if trunc is not None and trunc.text == "true" and next_tok is not None and next_tok.text:
                token = next_tok.text
            else:
                break
        return etags

    def put_object(self, key: str, body: bytes, content_type: str, cache_control: str) -> None:
        uri = f"/{self.bucket}/{quote(key, safe='/')}"
        extra = {"Content-Type": content_type, "Cache-Control": cache_control}
        headers = self._sign_headers("PUT", uri, "", body, extra)
        r = requests.put(f"{self.scheme}://{self.host}{uri}", headers=headers, data=body, timeout=30)
        r.raise_for_status()


def _create_backend(endpoint: str, bucket: str, access_key: str, secret_key: str):
    try:
        import boto3  # type: ignore

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name="auto",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        def list_etags() -> Dict[str, str]:
            out: Dict[str, str] = {}
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get("Contents") or []:
                    k = obj.get("Key")
                    etag = str(obj.get("ETag") or "").strip('"')
                    if k and etag:
                        out[k] = etag
            return out

        def put_object(key: str, body: bytes, content_type: str, cache_control: str) -> None:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                CacheControl=cache_control,
            )

        return list_etags, put_object
    except ImportError:
        cli = _SigV4Client(endpoint, bucket, access_key, secret_key)
        return cli.list_etags, cli.put_object


def sync_to_r2(
    base_dir: Path | str = ".",
    *,
    scope: str = "full",
    full_archives: bool = False,
    dry_run: bool = False,
    max_workers: int = 8,
) -> Dict[str, int]:
    root = Path(base_dir)
    endpoint = (os.environ.get("R2_ENDPOINT") or "").strip()
    access_key = (os.environ.get("R2_ACCESS_KEY_ID") or "").strip()
    secret_key = (os.environ.get("R2_SECRET_ACCESS_KEY") or "").strip()
    bucket = (os.environ.get("R2_BUCKET") or "mirrorbrief-data").strip()

    if not endpoint or not access_key or not secret_key:
        print("R2 credentials not configured (R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY); skipping R2 sync.")
        return {"total": 0, "uploaded": 0, "skipped": 0, "failed": 0}

    files = collect_sync_files(root, scope=scope, full_archives=full_archives)
    if not files:
        print("No data files found to sync to R2.")
        return {"total": 0, "uploaded": 0, "skipped": 0, "failed": 0}

    list_etags, put_object = _create_backend(endpoint, bucket, access_key, secret_key)
    remote_etags = list_etags()

    manifest_item: Optional[Path] = None
    non_manifest: List[Path] = []
    for f in files:
        key = f.as_posix()
        if key == "data/manifest.json":
            manifest_item = f
        else:
            non_manifest.append(f)

    uploaded = 0
    skipped = 0
    failed = 0

    def _upload_one(rel: Path) -> Tuple[str, str]:
        key = rel.as_posix()
        data = (root / rel).read_bytes()
        digest = md5_hex(data)
        if remote_etags.get(key) == digest:
            return "skipped", key
        if not dry_run:
            put_object(key, data, guess_content_type(key), cache_control_for_key(key))
        return "uploaded", key

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = [pool.submit(_upload_one, rel) for rel in non_manifest]
        for fut in as_completed(futs):
            try:
                status, _k = fut.result()
                if status == "uploaded":
                    uploaded += 1
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                print(f"::warning::R2 upload error: {exc}")

    # Publish data/manifest.json VERY LAST only if critical uploads didn't fail
    if manifest_item is not None and failed == 0:
        try:
            st, _ = _upload_one(manifest_item)
            if st == "uploaded":
                uploaded += 1
            else:
                skipped += 1
        except Exception as exc:
            failed += 1
            print(f"::warning::R2 manifest upload failed: {exc}")

    print(f"R2 sync complete: bucket={bucket}, total={len(files)}, uploaded={uploaded}, skipped={skipped}, failed={failed}")
    summary_file = (os.environ.get("GITHUB_STEP_SUMMARY") or "").strip()
    if summary_file:
        try:
            with open(summary_file, "a", encoding="utf-8") as fh:
                fh.write("\n### ☁️ Cloudflare R2 Incremental Sync\n")
                fh.write(f"- **Bucket**: `{bucket}` | **Uploaded**: `{uploaded}` | **Unchanged Skipped**: `{skipped}` | **Failed**: `{failed}`\n")
        except Exception:
            pass

    return {"total": len(files), "uploaded": uploaded, "skipped": skipped, "failed": failed}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Incremental Cloudflare R2 sync for MirrorBrief")
    parser.add_argument("--scope", choices=("raw", "full"), default="full")
    parser.add_argument("--full-archives", action="store_true", help="Upload all historical archives/ folders incrementally")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    res = sync_to_r2(
        args.base_dir,
        scope=args.scope,
        full_archives=args.full_archives,
        dry_run=args.dry_run,
    )
    return 0 if res["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
