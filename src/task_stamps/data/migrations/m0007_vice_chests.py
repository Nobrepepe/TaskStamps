"""Streak and Boss chests replace the vice point economy."""

SQL = """
CREATE TABLE vice_rewards (
    id TEXT PRIMARY KEY,
    task_weight TEXT NOT NULL CHECK (task_weight IN ('minor', 'medium', 'major')),
    tier INTEGER NOT NULL CHECK (tier IN (5, 10, 15)),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX ix_vice_rewards_slot ON vice_rewards(task_weight, tier, is_archived);

CREATE TABLE vice_chests (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('streak', 'boss')),
    reward_id TEXT REFERENCES vice_rewards(id),
    reward_name_snapshot TEXT,
    completion_id TEXT REFERENCES task_completions(id),
    boss_date TEXT,
    granted_at TEXT NOT NULL,
    claimed_at TEXT,
    CHECK ((source = 'streak' AND completion_id IS NOT NULL AND boss_date IS NULL
            AND reward_id IS NOT NULL)
        OR (source = 'boss' AND boss_date IS NOT NULL AND completion_id IS NULL))
);
CREATE UNIQUE INDEX ux_vice_chests_completion ON vice_chests(completion_id)
    WHERE completion_id IS NOT NULL;
CREATE UNIQUE INDEX ux_vice_chests_boss ON vice_chests(boss_date)
    WHERE boss_date IS NOT NULL;
CREATE INDEX ix_vice_chests_reward ON vice_chests(reward_id, claimed_at);

CREATE TABLE task_misses (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES habit_tasks(id),
    miss_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (task_id, miss_date)
);
CREATE INDEX ix_task_misses_task_date ON task_misses(task_id, miss_date);

INSERT INTO task_misses(id, task_id, miss_date, created_at)
    SELECT id, task_id, penalty_date, created_at FROM task_penalties
    WHERE reason = 'missed';

DROP TABLE task_penalties;
DROP TABLE vice_claims;
DROP TABLE vice_offerings;
ALTER TABLE task_completions DROP COLUMN reward_points
"""
