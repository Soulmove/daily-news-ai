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
    login_count INTEGER NOT NULL DEFAULT 0,
    invited_by_user_id INTEGER,
    invited_by_code TEXT NOT NULL DEFAULT '',
    extra_qa_quota INTEGER NOT NULL DEFAULT 0
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
    early_multiplier REAL NOT NULL DEFAULT 1.0,
    reason_tag TEXT NOT NULL DEFAULT '',
    brier_score REAL,
    points_awarded INTEGER NOT NULL DEFAULT 0,
    settled_at TEXT,
    challenger_ref TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (prediction_id, user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pred_crowd_pid ON prediction_crowd_votes(prediction_id);

CREATE TABLE IF NOT EXISTS daily_predictions (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL DEFAULT 'auto_market',
    category TEXT NOT NULL DEFAULT 'market',
    title TEXT NOT NULL,
    question TEXT NOT NULL,
    win_rule TEXT NOT NULL DEFAULT '',
    lose_rule TEXT NOT NULL DEFAULT '',
    ticker TEXT NOT NULL DEFAULT '',
    base_price REAL,
    target_price REAL,
    ai_prob_pct REAL NOT NULL DEFAULT 50,
    created_at TEXT NOT NULL,
    lock_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    outcome TEXT,
    settled_value REAL,
    settled_at TEXT,
    proposer_user_id INTEGER,
    proposer_username TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_daily_pred_status_due ON daily_predictions(status, due_at);
CREATE INDEX IF NOT EXISTS idx_daily_pred_created ON daily_predictions(created_at DESC);

CREATE TABLE IF NOT EXISTS prediction_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'market',
    title TEXT NOT NULL,
    question TEXT NOT NULL,
    win_rule TEXT NOT NULL DEFAULT '',
    lose_rule TEXT NOT NULL DEFAULT '',
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    published_prediction_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    reviewed_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pred_proposals_status ON prediction_proposals(status, id DESC);

CREATE TABLE IF NOT EXISTS user_prediction_profiles (
    user_id INTEGER NOT NULL,
    season_key TEXT NOT NULL,
    insight_points INTEGER NOT NULL DEFAULT 0,
    settled_count INTEGER NOT NULL DEFAULT 0,
    hit_count INTEGER NOT NULL DEFAULT 0,
    brier_sum REAL NOT NULL DEFAULT 0,
    current_streak INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    rank_tier TEXT NOT NULL DEFAULT '见习观察员',
    bonus_qa_quota INTEGER NOT NULL DEFAULT 0,
    bonus_qa_expires_at TEXT NOT NULL DEFAULT '',
    unlocked_referral_bonus INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, season_key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pred_profiles_season_pts ON user_prediction_profiles(season_key, insight_points DESC);

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
    revoked INTEGER NOT NULL DEFAULT 0,
    owner_user_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_invite_codes_state ON invite_codes(revoked, used_by_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_invite_codes_owner ON invite_codes(owner_user_id, id DESC);

-- Stage-3 scarcity invite waitlist
CREATE TABLE IF NOT EXISTS invite_waitlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact TEXT NOT NULL,
    focus_areas TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    assigned_code TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    reviewed_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_invite_waitlist_status ON invite_waitlist(status, id DESC);

-- Structured 1-click content reactions (zero open-text UGC risk)
CREATE TABLE IF NOT EXISTS content_reactions (
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    reaction_key TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (target_type, target_id, reaction_key)
);

CREATE TABLE IF NOT EXISTS content_reaction_votes (
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    voter_key TEXT NOT NULL,
    reaction_key TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (target_type, target_id, voter_key)
);
CREATE INDEX IF NOT EXISTS idx_reaction_votes_target ON content_reaction_votes(target_type, target_id);

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

-- Live online presence sessions & daily IP visit frequency analytics (0004_presence_and_traffic.sql)
CREATE TABLE IF NOT EXISTS presence_sessions (
    session_key TEXT PRIMARY KEY,
    ip TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    username TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    is_logged_in INTEGER NOT NULL DEFAULT 0,
    platform TEXT NOT NULL DEFAULT 'desktop',
    current_tab TEXT NOT NULL DEFAULT 'today',
    user_agent TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_seen_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_presence_last_seen ON presence_sessions(last_seen_ms DESC);
CREATE INDEX IF NOT EXISTS idx_presence_logged_seen ON presence_sessions(is_logged_in, last_seen_ms DESC);

CREATE TABLE IF NOT EXISTS daily_ip_visits (
    day_cst TEXT NOT NULL,
    ip TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT '',
    visit_count INTEGER NOT NULL DEFAULT 0,
    auth_visit_count INTEGER NOT NULL DEFAULT 0,
    guest_visit_count INTEGER NOT NULL DEFAULT 0,
    heartbeat_count INTEGER NOT NULL DEFAULT 0,
    last_user_id INTEGER,
    last_username TEXT NOT NULL DEFAULT '',
    usernames_json TEXT NOT NULL DEFAULT '[]',
    platforms_json TEXT NOT NULL DEFAULT '[]',
    last_tab TEXT NOT NULL DEFAULT 'today',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (day_cst, ip)
);
CREATE INDEX IF NOT EXISTS idx_daily_ip_day_visits ON daily_ip_visits(day_cst, visit_count DESC, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_daily_ip_day_seen ON daily_ip_visits(day_cst, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS hourly_visit_stats (
    day_cst TEXT NOT NULL,
    hour_cst INTEGER NOT NULL,
    total_visits INTEGER NOT NULL DEFAULT 0,
    auth_visits INTEGER NOT NULL DEFAULT 0,
    guest_visits INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day_cst, hour_cst)
);

CREATE TABLE IF NOT EXISTS hourly_ip_seen (
    day_cst TEXT NOT NULL,
    hour_cst INTEGER NOT NULL,
    ip TEXT NOT NULL,
    PRIMARY KEY (day_cst, hour_cst, ip)
);

-- 24h AI Token Metering & Daily 21:00 CST Settlement Snapshots (0005_ai_usage_telemetry.sql)
CREATE TABLE IF NOT EXISTS ai_usage_events (
    id TEXT PRIMARY KEY,
    ts_cst TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'worker',
    scope TEXT NOT NULL DEFAULT 'worker_qa',
    tier TEXT NOT NULL DEFAULT 'tier1',
    primary_model TEXT NOT NULL DEFAULT '',
    model_canonical TEXT NOT NULL DEFAULT '',
    model_actual TEXT NOT NULL DEFAULT '',
    is_fallback INTEGER NOT NULL DEFAULT 0,
    key_slot TEXT NOT NULL DEFAULT '',
    key_fingerprint TEXT NOT NULL DEFAULT '',
    ok INTEGER NOT NULL DEFAULT 1,
    error_code TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    token_source TEXT NOT NULL DEFAULT 'exact',
    latency_ms INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_ts ON ai_usage_events(ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_model_ts ON ai_usage_events(model_canonical, ts_ms DESC);

CREATE TABLE IF NOT EXISTS ai_daily_21h_snapshots (
    settlement_day TEXT PRIMARY KEY,
    window_start_cst TEXT NOT NULL,
    window_end_cst TEXT NOT NULL,
    frozen_at_cst TEXT NOT NULL,
    source_r2_updated_at TEXT NOT NULL DEFAULT '',
    total_tokens INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_calls INTEGER NOT NULL DEFAULT 0,
    ok_calls INTEGER NOT NULL DEFAULT 0,
    error_calls INTEGER NOT NULL DEFAULT 0,
    fallback_calls INTEGER NOT NULL DEFAULT 0,
    snapshot_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_snap_day ON ai_daily_21h_snapshots(settlement_day DESC);
