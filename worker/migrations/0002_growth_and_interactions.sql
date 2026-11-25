-- MirrorBrief (镜信) Cold-Start Growth, Waitlist & Structured Reactions Migration (0002)

ALTER TABLE users ADD COLUMN invited_by_user_id INTEGER;
ALTER TABLE users ADD COLUMN invited_by_code TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN extra_qa_quota INTEGER NOT NULL DEFAULT 0;

ALTER TABLE invite_codes ADD COLUMN owner_user_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_invite_codes_owner ON invite_codes(owner_user_id, id DESC);

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
