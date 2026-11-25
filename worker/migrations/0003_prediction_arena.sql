-- MirrorBrief (镜信) D1 Schema Migration 0003: Daily Prediction Arena, Structured Reason Tags, User Proposals & Season Calibration Profiles

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

ALTER TABLE prediction_crowd_votes ADD COLUMN early_multiplier REAL NOT NULL DEFAULT 1.0;
ALTER TABLE prediction_crowd_votes ADD COLUMN reason_tag TEXT NOT NULL DEFAULT '';
ALTER TABLE prediction_crowd_votes ADD COLUMN brier_score REAL;
ALTER TABLE prediction_crowd_votes ADD COLUMN points_awarded INTEGER NOT NULL DEFAULT 0;
ALTER TABLE prediction_crowd_votes ADD COLUMN settled_at TEXT;
ALTER TABLE prediction_crowd_votes ADD COLUMN challenger_ref TEXT NOT NULL DEFAULT '';

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
