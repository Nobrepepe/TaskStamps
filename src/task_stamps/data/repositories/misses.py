from __future__ import annotations

from datetime import date

from task_stamps.data.repositories.base import BaseRepository
from task_stamps.utilities.ids import new_id


class MissRepository(BaseRepository):
    """Scheduled days that went unmet. Three consecutive misses auto-pause a
    task; a completion on a later date resets the count."""

    def record(self, task_id: str, miss_date: date) -> None:
        existing = self.db.query_one(
            "SELECT 1 FROM task_misses WHERE task_id = ? AND miss_date = ?",
            (task_id, miss_date.isoformat()),
        )
        if existing is not None:
            return
        self.db.execute(
            "INSERT INTO task_misses(id, task_id, miss_date, created_at) "
            "VALUES (?, ?, ?, ?)",
            (new_id(), task_id, miss_date.isoformat(), self.now_iso()),
        )

    def consecutive_misses(self, task_id: str) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS count FROM task_misses "
            "WHERE task_id = ? AND miss_date > "
            "COALESCE((SELECT MAX(completion_date) FROM task_completions "
            "WHERE task_id = ? AND is_reversed = 0), '0001-01-01')",
            (task_id, task_id),
        )
        return int(row["count"]) if row else 0
