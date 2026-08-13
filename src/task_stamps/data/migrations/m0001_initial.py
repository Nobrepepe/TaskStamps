"""Initial schema."""

SQL = """
CREATE TABLE assets (
    id TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL,
    current_version_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE asset_versions (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(id),
    relative_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX ix_asset_versions_asset ON asset_versions(asset_id);

CREATE TABLE worlds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    cover_asset_version_id TEXT REFERENCES asset_versions(id),
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE characters (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    portrait_asset_version_id TEXT REFERENCES asset_versions(id),
    default_sound_asset_version_id TEXT REFERENCES asset_versions(id),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ready')),
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX ix_characters_world ON characters(world_id);

CREATE TABLE character_stamps (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES characters(id),
    sequence_number INTEGER NOT NULL CHECK (sequence_number BETWEEN 1 AND 15),
    image_asset_version_id TEXT REFERENCES asset_versions(id),
    sound_asset_version_id TEXT REFERENCES asset_versions(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (character_id, sequence_number)
);

CREATE TABLE habit_tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    weekday_mask INTEGER NOT NULL DEFAULT 0,
    pool_type TEXT NOT NULL DEFAULT 'all' CHECK (pool_type IN ('all', 'world')),
    world_id TEXT REFERENCES worlds(id),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE character_assignments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES habit_tasks(id),
    character_id TEXT NOT NULL REFERENCES characters(id),
    current_streak INTEGER NOT NULL DEFAULT 0 CHECK (current_streak BETWEEN 0 AND 15),
    started_on TEXT NOT NULL,
    ended_on TEXT,
    end_reason TEXT,
    dropped_due_date TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_assignments_active_task
    ON character_assignments(task_id) WHERE is_active = 1;
CREATE UNIQUE INDEX ux_assignments_active_character
    ON character_assignments(character_id) WHERE is_active = 1;
CREATE INDEX ix_assignments_task ON character_assignments(task_id);
CREATE INDEX ix_assignments_character ON character_assignments(character_id);

CREATE TABLE task_completions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES habit_tasks(id),
    assignment_id TEXT NOT NULL REFERENCES character_assignments(id),
    character_id TEXT NOT NULL REFERENCES characters(id),
    stamp_id TEXT NOT NULL REFERENCES character_stamps(id),
    completion_date TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    streak_number INTEGER NOT NULL CHECK (streak_number BETWEEN 1 AND 15),
    task_name_snapshot TEXT NOT NULL,
    character_name_snapshot TEXT NOT NULL,
    world_name_snapshot TEXT NOT NULL,
    is_reversed INTEGER NOT NULL DEFAULT 0,
    reversed_at TEXT
);
CREATE UNIQUE INDEX ux_completions_task_date
    ON task_completions(task_id, completion_date) WHERE is_reversed = 0;
CREATE INDEX ix_completions_date ON task_completions(completion_date);
CREATE INDEX ix_completions_assignment ON task_completions(assignment_id);

CREATE TABLE stamp_placements (
    id TEXT PRIMARY KEY,
    completion_id TEXT NOT NULL UNIQUE REFERENCES task_completions(id),
    board_date TEXT NOT NULL,
    x_normalized REAL NOT NULL CHECK (x_normalized BETWEEN 0 AND 1),
    y_normalized REAL NOT NULL CHECK (y_normalized BETWEEN 0 AND 1),
    rotation_degrees REAL NOT NULL,
    scale REAL NOT NULL,
    z_index INTEGER NOT NULL,
    image_asset_version_id TEXT NOT NULL REFERENCES asset_versions(id),
    sound_asset_version_id TEXT REFERENCES asset_versions(id),
    created_at TEXT NOT NULL
);
CREATE INDEX ix_placements_date ON stamp_placements(board_date);

CREATE TABLE pause_periods (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES habit_tasks(id),
    started_on TEXT NOT NULL,
    ended_on TEXT
);
CREATE INDEX ix_pause_periods_task ON pause_periods(task_id);

CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    serialized_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""
