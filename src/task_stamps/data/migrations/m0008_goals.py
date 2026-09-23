"""Goals: numeric targets walked along a ten-section track by one character
at a time, paying out a chest on a chosen reward when the target is met."""

SQL = """
CREATE TABLE character_goal_images (
    character_id TEXT NOT NULL REFERENCES characters(id),
    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 10),
    image_asset_version_id TEXT NOT NULL REFERENCES asset_versions(id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (character_id, rank)
);

CREATE TABLE goals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '',
    baseline_value REAL NOT NULL,
    target_value REAL NOT NULL,
    current_value REAL NOT NULL,
    reward_id TEXT REFERENCES vice_rewards(id),
    pool_type TEXT NOT NULL DEFAULT 'all' CHECK (pool_type IN ('all', 'world')),
    world_id TEXT REFERENCES worlds(id),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'reached', 'finished', 'removed')),
    last_reviewed_on TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    CHECK (target_value != baseline_value)
);
CREATE INDEX ix_goals_status ON goals(status);
CREATE INDEX ix_goals_reward ON goals(reward_id, status);

CREATE TABLE goal_legs (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    character_id TEXT REFERENCES characters(id),
    baseline_value REAL NOT NULL,
    target_value REAL NOT NULL,
    started_on TEXT NOT NULL,
    ended_on TEXT,
    end_reason TEXT CHECK (end_reason IN ('reached', 'rebased', 'removed')),
    end_value REAL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (goal_id, ordinal)
);
CREATE UNIQUE INDEX ux_goal_legs_active_goal ON goal_legs(goal_id) WHERE is_active = 1;
CREATE UNIQUE INDEX ux_goal_legs_active_character ON goal_legs(character_id)
    WHERE is_active = 1 AND character_id IS NOT NULL;

CREATE TABLE goal_entries (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(id),
    leg_id TEXT NOT NULL REFERENCES goal_legs(id),
    delta REAL NOT NULL,
    value_before REAL NOT NULL,
    value_after REAL NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('progress', 'reached', 'rebased')),
    previous_reviewed_on TEXT NOT NULL,
    entered_on TEXT NOT NULL,
    entered_at TEXT NOT NULL
);
CREATE INDEX ix_goal_entries_goal ON goal_entries(goal_id, entered_at);

CREATE TABLE vice_chests_v8 (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('streak', 'boss', 'goal')),
    reward_id TEXT REFERENCES vice_rewards(id),
    reward_name_snapshot TEXT,
    completion_id TEXT REFERENCES task_completions(id),
    boss_date TEXT,
    goal_leg_id TEXT REFERENCES goal_legs(id),
    granted_at TEXT NOT NULL,
    claimed_at TEXT,
    CHECK ((source = 'streak' AND completion_id IS NOT NULL AND boss_date IS NULL
            AND goal_leg_id IS NULL AND reward_id IS NOT NULL)
        OR (source = 'boss' AND boss_date IS NOT NULL AND completion_id IS NULL
            AND goal_leg_id IS NULL)
        OR (source = 'goal' AND goal_leg_id IS NOT NULL AND completion_id IS NULL
            AND boss_date IS NULL AND reward_id IS NOT NULL))
);
INSERT INTO vice_chests_v8(id, source, reward_id, reward_name_snapshot, completion_id,
                           boss_date, granted_at, claimed_at)
    SELECT id, source, reward_id, reward_name_snapshot, completion_id,
           boss_date, granted_at, claimed_at FROM vice_chests;
DROP TABLE vice_chests;
ALTER TABLE vice_chests_v8 RENAME TO vice_chests;
CREATE UNIQUE INDEX ux_vice_chests_completion ON vice_chests(completion_id)
    WHERE completion_id IS NOT NULL;
CREATE UNIQUE INDEX ux_vice_chests_boss ON vice_chests(boss_date)
    WHERE boss_date IS NOT NULL;
CREATE UNIQUE INDEX ux_vice_chests_goal_leg ON vice_chests(goal_leg_id)
    WHERE goal_leg_id IS NOT NULL;
CREATE INDEX ix_vice_chests_reward ON vice_chests(reward_id, claimed_at)
"""
