-- MirrorBrief (镜信) D1 Schema Migration 0005: 24h AI Token Metering & Daily 21:00 CST Snapshot Telemetry

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
