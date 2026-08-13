from __future__ import annotations

import sqlite3
from datetime import date, datetime

from task_stamps.data.repositories.base import BaseRepository, opt_datetime
from task_stamps.domain.models import TaskCompletion
from task_stamps.utilities.ids import new_id


def _row_to_completion(row: sqlite3.Row) -> TaskCompletion:
    return TaskCompletion(
        id=row["id"],
        task_id=row["task_id"],
        assignment_id=row["assignment_id"],
        character_id=row["character_id"],
        stamp_id=row["stamp_id"],
        completion_date=date.fromisoformat(row["completion_date"]),
        completed_at=datetime.fromisoformat(row["completed_at"]),
        streak_number=row["streak_number"],
        task_name_snapshot=row["task_name_snapshot"],
        character_name_snapshot=row["character_name_snapshot"],
        world_name_snapshot=row["world_name_snapshot"],
        reward_points=row["reward_points"],
        is_reversed=bool(row["is_reversed"]),
        reversed_at=opt_datetime(row["reversed_at"]),
    )


class CompletionRepository(BaseRepository):
    def create(
        self,
        *,
        task_id: str,
        assignment_id: str,
        character_id: str,
        stamp_id: str,
        completion_date: date,
        streak_number: int,
        task_name_snapshot: str,
        character_name_snapshot: str,
        world_name_snapshot: str,
        reward_points: int,
    ) -> TaskCompletion:
        completion_id = new_id()
        self.db.execute(
            "INSERT INTO task_completions(id, task_id, assignment_id, character_id, stamp_id, "
            "completion_date, completed_at, streak_number, task_name_snapshot, "
            "character_name_snapshot, world_name_snapshot, reward_points, is_reversed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                completion_id,
                task_id,
                assignment_id,
                character_id,
                stamp_id,
                completion_date.isoformat(),
                self.now_iso(),
                streak_number,
                task_name_snapshot,
                character_name_snapshot,
                world_name_snapshot,
                reward_points,
            ),
        )
        return self.get(completion_id)

    def get(self, completion_id: str) -> TaskCompletion:
        row = self.db.query_one(
            "SELECT * FROM task_completions WHERE id = ?", (completion_id,)
        )
        if row is None:
            raise KeyError(f"completion not found: {completion_id}")
        return _row_to_completion(row)

    def exists_for_date(self, task_id: str, on_date: date) -> bool:
        row = self.db.query_one(
            "SELECT 1 FROM task_completions "
            "WHERE task_id = ? AND completion_date = ? AND is_reversed = 0",
            (task_id, on_date.isoformat()),
        )
        return row is not None

    def last_completion_date(self, assignment_id: str) -> date | None:
        row = self.db.query_one(
            "SELECT MAX(completion_date) AS d FROM task_completions "
            "WHERE assignment_id = ? AND is_reversed = 0",
            (assignment_id,),
        )
        return date.fromisoformat(row["d"]) if row and row["d"] else None

    def list_for_task(self, task_id: str, limit: int = 30) -> list[TaskCompletion]:
        rows = self.db.query_all(
            "SELECT * FROM task_completions WHERE task_id = ? AND is_reversed = 0 "
            "ORDER BY completed_at DESC LIMIT ?",
            (task_id, limit),
        )
        return [_row_to_completion(row) for row in rows]

    def list_for_assignment(self, assignment_id: str) -> list[TaskCompletion]:
        rows = self.db.query_all(
            "SELECT * FROM task_completions WHERE assignment_id = ? AND is_reversed = 0 "
            "ORDER BY streak_number",
            (assignment_id,),
        )
        return [_row_to_completion(row) for row in rows]

    def list_between(self, start: date, end: date) -> list[TaskCompletion]:
        """Return the visible completion history for an inclusive date range."""
        rows = self.db.query_all(
            "SELECT * FROM task_completions "
            "WHERE completion_date BETWEEN ? AND ? AND is_reversed = 0 "
            "ORDER BY completion_date, completed_at",
            (start.isoformat(), end.isoformat()),
        )
        return [_row_to_completion(row) for row in rows]

    def mark_reversed(self, completion_id: str) -> None:
        self.db.execute(
            "UPDATE task_completions SET is_reversed = 1, reversed_at = ? WHERE id = ?",
            (self.now_iso(), completion_id),
        )
