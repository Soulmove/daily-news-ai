"""Unit tests for Cloudflare R2 incremental sync, private digest push, and SQLite->D1 migration."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts.migrate_sqlite_to_d1 import (
    aes256gcm_encrypt_json,
    export_sqlite_to_d1_sql,
    pbkdf2_sha256_hash,
)
from scripts.send_digest import build_digest_markdown, send_digest
from scripts.sync_to_r2 import (
    cache_control_for_key,
    collect_sync_files,
    sync_to_r2,
)


class CloudflareScriptsTests(unittest.TestCase):
    def test_sync_to_r2_ordering_and_cache_control(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir(parents=True)
            (root / "archives" / "smart" / "2026-11-25-18").mkdir(parents=True)
            (root / "archives" / "raw" / "2026-11-25-18-00").mkdir(parents=True)
            (root / "history").mkdir(parents=True)

            (root / "analysis_finance.json").write_text('{"events":[]}', encoding="utf-8")
            (root / "data" / "live_wire.json").write_text('{"items":[]}', encoding="utf-8")
            (root / "data" / "market_quotes.json").write_text('{"quotes":{}}', encoding="utf-8")
            (root / "history" / "smart_index.json").write_text("[]", encoding="utf-8")
            (root / "archives" / "smart" / "index.json").write_text("[]", encoding="utf-8")
            (root / "archives" / "smart" / "2026-11-25-18" / "analysis_finance.json").write_text(
                '{"events":[]}', encoding="utf-8"
            )
            (root / "archives" / "raw" / "2026-11-25-18-00" / "meta.json").write_text("{}", encoding="utf-8")
            (root / "data" / "manifest.json").write_text(
                json.dumps(
                    {
                        "smart": {
                            "categories": {
                                "finance": {"path": "archives/smart/2026-11-25-18/analysis_finance.json"}
                            }
                        },
                        "raw": {"meta_path": "archives/raw/2026-11-25-18-00/meta.json"},
                    }
                ),
                encoding="utf-8",
            )

            files = collect_sync_files(root, scope="full")
            rels = [p.as_posix() for p in files]
            self.assertGreater(len(rels), 5)
            # Atomic invariant: data/manifest.json MUST always be strictly last
            self.assertEqual(rels[-1], "data/manifest.json")

            # Verify Cache-Control policy
            self.assertEqual(cache_control_for_key("data/manifest.json"), "public, max-age=60")
            self.assertEqual(cache_control_for_key("data/live_wire.json"), "public, max-age=60")
            self.assertEqual(cache_control_for_key("archives/smart/index.json"), "public, max-age=60")
            self.assertEqual(
                cache_control_for_key("archives/smart/2026-11-25-18/analysis_finance.json"),
                "public, max-age=31536000, immutable",
            )
            self.assertEqual(
                cache_control_for_key("archives/raw/2026-11-25-18-00/meta.json"),
                "public, max-age=31536000, immutable",
            )

    def test_sync_to_r2_graceful_skip_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=True):
                res = sync_to_r2(tmp)
                self.assertEqual(res["uploaded"], 0)
                self.assertEqual(res["failed"], 0)

    def test_send_digest_bark_feishu_wecom_telegram_and_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir(parents=True)
            (root / "data" / "manifest.json").write_text(
                json.dumps({"smart": {"latest_batch_id": "2026-11-25-18"}}), encoding="utf-8"
            )
            (root / "analysis_global.json").write_text(
                json.dumps({"events": [{"title": "测试事件 A"}]}), encoding="utf-8"
            )

            # Empty env -> silent False
            with patch.dict(os.environ, {}, clear=True):
                self.assertFalse(send_digest(root))

            # Bark + Feishu + WeCom + Telegram configured -> posts to all 4
            posted = []

            class _Resp:
                status_code = 200

            def _fake_post(url: str, json=None, timeout=10):
                posted.append((url, json))
                return _Resp()

            with patch.dict(
                os.environ,
                {
                    "SITE_PUBLIC_URL": "https://mirrorinfo.xyz/",
                    "BARK_URL": "https://api.day.app/testkey/",
                    "FEISHU_WEBHOOK": "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
                    "WECOM_WEBHOOK": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xyz",
                    "TELEGRAM_BOT_TOKEN": "123:tok",
                    "TELEGRAM_CHAT_ID": "999",
                },
                clear=True,
            ), patch("scripts.send_digest.requests.post", side_effect=_fake_post):
                ok = send_digest(root)
                self.assertTrue(ok)
                self.assertEqual(len(posted), 4)
                urls = [u for u, _ in posted]
                self.assertIn("https://api.day.app/testkey/", urls)
                self.assertTrue(any("feishu.cn" in u for u in urls))
                self.assertTrue(any("qyapi.weixin.qq.com" in u for u in urls))
                self.assertTrue(any("api.telegram.org" in u for u in urls))

            md = build_digest_markdown(root)
            self.assertIn("https://mirrorinfo.xyz/", md)
            self.assertNotIn("Insight Pro", md)

    def test_migrate_sqlite_crypto_format_and_sql(self) -> None:
        h = pbkdf2_sha256_hash("TestPass123!")
        self.assertTrue(h.startswith("pbkdf2_sha256$65000$"))
        self.assertEqual(len(h.split("$")), 4)

        try:
            import cryptography  # type: ignore  # noqa: F401
            has_crypto = True
        except ImportError:
            has_crypto = False

        with tempfile.TemporaryDirectory() as tmp:
            db_p = Path(tmp) / "insight.db"
            ov_p = Path(tmp) / "editorial_overrides.json"
            ov_p.write_text(
                json.dumps(
                    {
                        "updated_at": "2026-11-25T18:00:00+08:00",
                        "items": {
                            "k1": {
                                "key": "k1",
                                "target_type": "event",
                                "event_id": "ev_1",
                                "title": "置顶测试",
                                "severity_override": "S",
                                "pinned": True,
                                "hidden": False,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            conn = sqlite3.connect(str(db_p))
            conn.executescript(
                """
                CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, display_name TEXT, email TEXT, phone TEXT, role TEXT, password_hash TEXT, encrypted_password TEXT, is_active INTEGER, token_version INTEGER, email_digest_enabled INTEGER, digest_last_sent_date TEXT, avatar TEXT, created_at TEXT, last_login_at TEXT, last_login_ip TEXT, login_count INTEGER);
                CREATE TABLE user_states (user_id INTEGER PRIMARY KEY, encrypted_payload TEXT, watchlist_count INTEGER, bookmarks_count INTEGER, read_later_count INTEGER, notes_count INTEGER, predictions_count INTEGER, muted_count INTEGER, payload_bytes INTEGER, updated_at TEXT);
                CREATE TABLE push_configs (id TEXT PRIMARY KEY, encrypted_config TEXT, updated_at TEXT);
                CREATE TABLE site_settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
                CREATE TABLE feedback_messages (id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT, device_id TEXT, contact TEXT, category TEXT, content TEXT, page_url TEXT, ip TEXT, status TEXT, admin_reply TEXT, replied_by TEXT, replied_at TEXT, created_at TEXT);
                CREATE TABLE prediction_crowd_votes (prediction_id TEXT, user_id INTEGER, prob_pct REAL, updated_at TEXT);
                INSERT INTO site_settings VALUES ('monitor_public', 'true', '2026-11-25T18:00:00+08:00');
                """
            )
            conn.commit()
            conn.close()

            sql = export_sqlite_to_d1_sql(
                db_p,
                old_fernet_key="unused",
                new_aes_key="new-secret-key",
                overrides_path=ov_p,
            )
            self.assertIn("INSERT OR REPLACE INTO site_settings", sql)
            self.assertIn("INSERT OR REPLACE INTO editorial_overrides", sql)
            if has_crypto:
                tok = aes256gcm_encrypt_json({"ok": True}, "new-secret-key")
                self.assertTrue(tok.startswith("aes256gcm$"))


if __name__ == "__main__":
    unittest.main()
