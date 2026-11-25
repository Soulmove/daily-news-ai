-- MirrorBrief (镜信) D1 Database Schema (0001_init.sql)
-- Compatible with migrated Tencent Cloud SQLite data + new invite codes, rate limits & edge 7x24 wire.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',
    password_hash TEXT NOT NULL,
    encrypted_password TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    token_version INTEGER NOT NULL DEFAULT 1,
    email_digest_enabled INTEGER NOT NULL DEFAULT 1,
    digest_last_sent_date TEXT NOT NULL DEFAULT '',
    avatar TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    last_login_at TEXT,
    last_login_ip TEXT,
    login_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

CREATE TABLE IF NOT EXISTS verification_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target TEXT NOT NULL COLLATE NOCASE,
    channel TEXT NOT NULL,
    purpose TEXT NOT NULL,
    code TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    ip TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vcode_target ON verification_codes(target, purpose, used);

CREATE TABLE IF NOT EXISTS user_states (
    user_id INTEGER PRIMARY KEY,
    encrypted_payload TEXT NOT NULL,
    watchlist_count INTEGER NOT NULL DEFAULT 0,
    bookmarks_count INTEGER NOT NULL DEFAULT 0,
    read_later_count INTEGER NOT NULL DEFAULT 0,
    notes_count INTEGER NOT NULL DEFAULT 0,
    predictions_count INTEGER NOT NULL DEFAULT 0,
    muted_count INTEGER NOT NULL DEFAULT 0,
    payload_bytes INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS push_configs (
    id TEXT PRIMARY KEY,
    encrypted_config TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS push_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    batch_id TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    error_msg TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_push_created ON push_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS site_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS registration_guards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reg_guard_device ON registration_guards(device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reg_guard_ip ON registration_guards(ip, created_at DESC);

CREATE TABLE IF NOT EXISTS feedback_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT NOT NULL DEFAULT '',
    device_id TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'suggestion',
    content TEXT NOT NULL,
    page_url TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    admin_reply TEXT NOT NULL DEFAULT '',
    replied_by TEXT NOT NULL DEFAULT '',
    replied_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback_messages(created_at DESC);

CREATE TABLE IF NOT EXISTS prediction_crowd_votes (
    prediction_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    prob_pct REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (prediction_id, user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pred_crowd_pid ON prediction_crowd_votes(prediction_id);

-- One-time Invite Codes for invite_only / private_gate modes
CREATE TABLE IF NOT EXISTS invite_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT 'admin',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL DEFAULT '',
    used_by_user_id INTEGER,
    used_by_username TEXT NOT NULL DEFAULT '',
    used_at TEXT NOT NULL DEFAULT '',
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_invite_codes_state ON invite_codes(revoked, used_by_user_id, created_at DESC);

-- Sliding-window D1 rate limit buckets
CREATE TABLE IF NOT EXISTS rate_limits (
    scope TEXT NOT NULL,
    bucket_key TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope, bucket_key, window_start)
);
CREATE INDEX IF NOT EXISTS idx_rate_limits_window ON rate_limits(window_start);

-- 7x24 Real-time Wire updated every 2 minutes by Cloudflare Cron Trigger
CREATE TABLE IF NOT EXISTS live_wire_items (
    id TEXT PRIMARY KEY,
    dedup_key TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'finance',
    title TEXT NOT NULL,
    excerpt TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    importance TEXT NOT NULL DEFAULT 'normal',
    severity_tier TEXT NOT NULL DEFAULT 'B',
    heavy_reason_tag TEXT,
    metric_label TEXT,
    thumbnail_url TEXT
);
CREATE INDEX IF NOT EXISTS idx_wire_pub ON live_wire_items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_wire_dedup ON live_wire_items(dedup_key);

-- Editorial overrides & heavy news scheduling managed by admins
CREATE TABLE IF NOT EXISTS editorial_overrides (
    override_key TEXT PRIMARY KEY,
    target_type TEXT NOT NULL DEFAULT 'event',
    event_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    title_fingerprint TEXT NOT NULL DEFAULT '',
    severity_override TEXT,
    heavy_reason_tag TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    hidden INTEGER NOT NULL DEFAULT 0,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
