"""Task weights, completion rewards, and the Vice Shop."""

SQL = """
ALTER TABLE habit_tasks ADD COLUMN weight TEXT NOT NULL DEFAULT 'medium'
    CHECK (weight IN ('trivial', 'minor', 'medium', 'major'));

ALTER TABLE task_completions ADD COLUMN reward_points INTEGER NOT NULL DEFAULT 0
    CHECK (reward_points >= 0);

CREATE TABLE vice_offerings (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL CHECK (price >= 0),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE vice_claims (
    id TEXT PRIMARY KEY,
    offering_id TEXT REFERENCES vice_offerings(id) ON DELETE SET NULL,
    offering_name_snapshot TEXT NOT NULL,
    price_paid INTEGER NOT NULL CHECK (price_paid >= 0),
    claimed_at TEXT NOT NULL
);
CREATE INDEX ix_vice_claims_offering ON vice_claims(offering_id);
"""
