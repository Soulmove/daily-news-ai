-- MirrorBrief (镜信) D1 Schema Migration 0004: Live Online Presence & Daily IP Visit Frequency Analytics

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
