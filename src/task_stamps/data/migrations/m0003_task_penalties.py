"""Point penalties for missed tasks and same-day pauses."""

SQL = """
CREATE TABLE task_penalties (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES habit_tasks(id),
    penalty_date TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('missed', 'scheduled_pause')),
    points_assessed INTEGER NOT NULL CHECK (points_assessed >= 0),
    points_deducted INTEGER NOT NULL CHECK (points_deducted >= 0),
    created_at TEXT NOT NULL,
    UNIQUE (task_id, penalty_date, reason)
);
CREATE INDEX ix_task_penalties_task_date ON task_penalties(task_id, penalty_date);
"""
