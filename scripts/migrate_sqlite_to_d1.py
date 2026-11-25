"""Migrate Tencent Cloud SQLite (insight.db + editorial_overrides.json) to Cloudflare D1 SQL.

Produces byte-for-byte Web Crypto compatible PBKDF2-SHA256 password hashes & AES-256-GCM
encrypted payloads matching `worker/src/crypto.ts`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
from typing import Any, Dict, List, Optional


PBKDF2_ITERATIONS = 65_000


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def pbkdf2_sha256_hash(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return f"pbkdf2_sha256${iterations}${b64url_encode(salt)}${b64url_encode(dk)}"


def aes256gcm_encrypt_json(obj: Any, secret_key: str) -> str:
    key = hashlib.sha256((secret_key or "mirrorbrief-dev-fallback-key").encode("utf-8")).digest()
    iv = os.urandom(12)
    plain = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

        ct = AESGCM(key).encrypt(iv, plain, None)
    except ImportError as exc:
        raise RuntimeError(
            "The 'cryptography' package is required to run migrate_sqlite_to_d1.py (pip install cryptography)."
        ) from exc
    return f"aes256gcm${b64url_encode(iv)}${b64url_encode(ct)}"


def _fernet_decrypt_json(token: str, old_fernet_key: str, default: Any = None) -> Any:
    if not token:
        return default
    if token.startswith("aes256gcm$"):
        return default
    try:
        from cryptography.fernet import Fernet  # type: ignore

        key_bytes = old_fernet_key.encode("utf-8")
        f = Fernet(key_bytes)
        dec = f.decrypt(token.encode("utf-8"))
        return json.loads(dec.decode("utf-8"))
    except Exception:
        return default


def sql_lit(val: Any) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val).replace("'", "''")
    return f"'{s}'"


def export_sqlite_to_d1_sql(
    sqlite_path: Path,
    *,
    old_fernet_key: str,
    new_aes_key: str,
    overrides_path: Optional[Path] = None,
) -> str:
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    lines: List[str] = [
        "-- Auto-generated MirrorBrief Tencent SQLite -> Cloudflare D1 Migration SQL",
        "-- Run with: npx wrangler d1 execute mirrorbrief-db --remote --file=d1_migration.sql",
        "PRAGMA foreign_keys = OFF;",
    ]

    # 1. Users (re-hash from decrypted plaintext password when available)
    users = conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
    for u in users:
        ud = dict(u)
        plain_pw = ""
        enc_pw = str(ud.get("encrypted_password") or "")
        if enc_pw:
            obj = _fernet_decrypt_json(enc_pw, old_fernet_key, default={})
            if isinstance(obj, dict):
                plain_pw = str(obj.get("pw") or "")
        if plain_pw:
            pw_hash = pbkdf2_sha256_hash(plain_pw)
            new_enc_pw = aes256gcm_encrypt_json({"pw": plain_pw}, new_aes_key)
        else:
            # Keep existing hash marker (user can reset password cleanly via OTP/admin)
            pw_hash = str(ud.get("password_hash") or "")
            new_enc_pw = ""
        lines.append(
            "INSERT OR REPLACE INTO users "
            "(id, username, display_name, email, phone, role, password_hash, encrypted_password, "
            "is_active, token_version, email_digest_enabled, digest_last_sent_date, avatar, "
            "created_at, last_login_at, last_login_ip, login_count) VALUES ("
            + ", ".join(
                [
                    sql_lit(ud["id"]),
                    sql_lit(ud["username"]),
                    sql_lit(ud.get("display_name", "")),
                    sql_lit(ud.get("email", "")),
                    sql_lit(ud.get("phone", "")),
                    sql_lit(ud.get("role", "user")),
                    sql_lit(pw_hash),
                    sql_lit(new_enc_pw),
                    sql_lit(ud.get("is_active", 1)),
                    sql_lit(ud.get("token_version", 1)),
                    sql_lit(ud.get("email_digest_enabled", 1)),
                    sql_lit(ud.get("digest_last_sent_date", "")),
                    sql_lit(ud.get("avatar", "")),
                    sql_lit(ud.get("created_at", "")),
                    sql_lit(ud.get("last_login_at")),
                    sql_lit(ud.get("last_login_ip")),
                    sql_lit(ud.get("login_count", 0)),
                ]
            )
            + ");"
        )

    # 2. User states (Fernet -> AES-256-GCM)
    states = conn.execute("SELECT * FROM user_states ORDER BY user_id ASC").fetchall()
    for s in states:
        sd = dict(s)
        dec_state = _fernet_decrypt_json(str(sd.get("encrypted_payload") or ""), old_fernet_key, default=None)
        if dec_state is None:
            continue
        new_enc_state = aes256gcm_encrypt_json(dec_state, new_aes_key)
        lines.append(
            "INSERT OR REPLACE INTO user_states "
            "(user_id, encrypted_payload, watchlist_count, bookmarks_count, read_later_count, "
            "notes_count, predictions_count, muted_count, payload_bytes, updated_at) VALUES ("
            + ", ".join(
                [
                    sql_lit(sd["user_id"]),
                    sql_lit(new_enc_state),
                    sql_lit(sd.get("watchlist_count", 0)),
                    sql_lit(sd.get("bookmarks_count", 0)),
                    sql_lit(sd.get("read_later_count", 0)),
                    sql_lit(sd.get("notes_count", 0)),
                    sql_lit(sd.get("predictions_count", 0)),
                    sql_lit(sd.get("muted_count", 0)),
                    sql_lit(len(new_enc_state.encode("utf-8"))),
                    sql_lit(sd.get("updated_at", "")),
                ]
            )
            + ");"
        )

    # 3. Push configs (Fernet -> AES-256-GCM)
    for pc in conn.execute("SELECT * FROM push_configs").fetchall():
        pd = dict(pc)
        dec_cfg = _fernet_decrypt_json(str(pd.get("encrypted_config") or ""), old_fernet_key, default=None)
        if dec_cfg is not None:
            new_cfg = aes256gcm_encrypt_json(dec_cfg, new_aes_key)
            lines.append(
                f"INSERT OR REPLACE INTO push_configs (id, encrypted_config, updated_at) VALUES ({sql_lit(pd['id'])}, {sql_lit(new_cfg)}, {sql_lit(pd['updated_at'])});"
            )

    # 4. Site settings, Feedback, Crowd Votes, Audit Logs, Push Logs
    for ss in conn.execute("SELECT * FROM site_settings").fetchall():
        sd = dict(ss)
        lines.append(
            f"INSERT OR REPLACE INTO site_settings (key, value, updated_at) VALUES ({sql_lit(sd['key'])}, {sql_lit(sd['value'])}, {sql_lit(sd['updated_at'])});"
        )

    for fb in conn.execute("SELECT * FROM feedback_messages ORDER BY id ASC").fetchall():
        fd = dict(fb)
        lines.append(
            "INSERT OR REPLACE INTO feedback_messages "
            "(id, user_id, username, device_id, contact, category, content, page_url, ip, "
            "status, admin_reply, replied_by, replied_at, created_at) VALUES ("
            + ", ".join(
                sql_lit(fd.get(c, ""))
                for c in (
                    "id", "user_id", "username", "device_id", "contact", "category",
                    "content", "page_url", "ip", "status", "admin_reply", "replied_by",
                    "replied_at", "created_at",
                )
            )
            + ");"
        )

    for cv in conn.execute("SELECT * FROM prediction_crowd_votes").fetchall():
        cd = dict(cv)
        lines.append(
            f"INSERT OR REPLACE INTO prediction_crowd_votes (prediction_id, user_id, prob_pct, updated_at) VALUES ({sql_lit(cd['prediction_id'])}, {sql_lit(cd['user_id'])}, {sql_lit(cd['prob_pct'])}, {sql_lit(cd['updated_at'])});"
        )

    # 5. Optional editorial_overrides.json
    if overrides_path and overrides_path.exists():
        try:
            ov_doc = json.loads(overrides_path.read_text(encoding="utf-8"))
            for k, item in (ov_doc.get("items") or {}).items():
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "INSERT OR REPLACE INTO editorial_overrides "
                    "(override_key, target_type, event_id, title, title_fingerprint, "
                    "severity_override, heavy_reason_tag, pinned, hidden, updated_by, updated_at) VALUES ("
                    + ", ".join(
                        [
                            sql_lit(item.get("key") or k),
                            sql_lit(item.get("target_type", "event")),
                            sql_lit(item.get("event_id", "")),
                            sql_lit(item.get("title", "")),
                            sql_lit(item.get("title_fingerprint", "")),
                            sql_lit(item.get("severity_override")),
                            sql_lit(item.get("heavy_reason_tag")),
                            sql_lit(bool(item.get("pinned"))),
                            sql_lit(bool(item.get("hidden"))),
                            sql_lit(item.get("updated_by", "")),
                            sql_lit(item.get("updated_at", "")),
                        ]
                    )
                    + ");"
                )
        except Exception:
            pass

    lines.append("PRAGMA foreign_keys = ON;")
    conn.close()
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Export Tencent SQLite insight.db into Cloudflare D1 SQL")
    parser.add_argument("--sqlite", required=True, help="Path to insight.db")
    parser.add_argument("--overrides", default="", help="Optional path to editorial_overrides.json")
    parser.add_argument("--old-key", default=os.environ.get("INSIGHT_ENCRYPTION_KEY", ""), help="Old Fernet INSIGHT_ENCRYPTION_KEY")
    parser.add_argument("--new-key", default=os.environ.get("DATA_ENCRYPTION_KEY", ""), help="New Worker DATA_ENCRYPTION_KEY")
    parser.add_argument("--out", default="d1_migration.sql", help="Output SQL file path")
    args = parser.parse_args(argv)

    if not args.new_key:
        print("Error: --new-key (or DATA_ENCRYPTION_KEY env) is required", file=sys.stderr)
        return 1

    sql_text = export_sqlite_to_d1_sql(
        Path(args.sqlite),
        old_fernet_key=args.old_key,
        new_aes_key=args.new_key,
        overrides_path=Path(args.overrides) if args.overrides else None,
    )
    out_p = Path(args.out)
    out_p.write_text(sql_text, encoding="utf-8")
    print(f"Wrote D1 migration SQL to {out_p} ({len(sql_text.splitlines())} statements/lines).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
