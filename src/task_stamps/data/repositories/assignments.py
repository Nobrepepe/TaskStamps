from __future__ import annotations

import sqlite3
from datetime import date, datetime

from task_stamps.data.repositories.base import BaseRepository, opt_date
from task_stamps.domain.enums import AssignmentEndReason
from task_stamps.domain.models import CharacterAssignment
from task_stamps.utilities.ids import new_id


def _row_to_assignment(row: sqlite3.Row) -> CharacterAssignment:
    return CharacterAssignment(
        id=row["id"],
        task_id=row["task_id"],
        character_id=row["character_id"],
        current_streak=row["current_streak"],
        started_on=date.fromisoformat(row["started_on"]),
        ended_on=opt_date(row["ended_on"]),
        end_reason=AssignmentEndReason(row["end_reason"]) if row["end_reason"] else None,
        dropped_due_date=opt_date(row["dropped_due_date"]),
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class AssignmentRepository(BaseRepository):
    def create(self, task_id: str, character_id: str, started_on: date) -> CharacterAssignment:
        now = self.now_iso()
        assignment_id = new_id()
        self.db.execute(
            "INSERT INTO character_assignments(id, task_id, character_id, current_streak, "
            "started_on, is_active, created_at, updated_at) VALUES (?, ?, ?, 0, ?, 1, ?, ?)",
            (assignment_id, task_id, character_id, started_on.isoformat(), now, now),
        )
        return self.get(assignment_id)

    def get(self, assignment_id: str) -> CharacterAssignment:
        row = self.db.query_one(
            "SELECT * FROM character_assignments WHERE id = ?", (assignment_id,)
        )
        if row is None:
            raise KeyError(f"assignment not found: {assignment_id}")
        return _row_to_assignment(row)

    def active_for_task(self, task_id: str) -> CharacterAssignment | None:
        row = self.db.query_one(
            "SELECT * FROM character_assignments WHERE task_id = ? AND is_active = 1",
            (task_id,),
        )
        return _row_to_assignment(row) if row else None

    def active_for_character(self, character_id: str) -> CharacterAssignment | None:
        row = self.db.query_one(
            "SELECT * FROM character_assignments WHERE character_id = ? AND is_active = 1",
            (character_id,),
        )
        return _row_to_assignment(row) if row else None

    def list_active(self) -> list[CharacterAssignment]:
        rows = self.db.query_all(
            "SELECT * FROM character_assignments WHERE is_active = 1"
        )
        return [_row_to_assignment(row) for row in rows]

    def history_for_task(self, task_id: str, limit: int = 20) -> list[CharacterAssignment]:
        rows = self.db.query_all(
            "SELECT * FROM character_assignments WHERE task_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (task_id, limit),
        )
        return [_row_to_assignment(row) for row in rows]

    def history_for_character(
        self, character_id: str, limit: int = 20
    ) -> list[CharacterAssignment]:
        rows = self.db.query_all(
            "SELECT * FROM character_assignments WHERE character_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (character_id, limit),
        )
        return [_row_to_assignment(row) for row in rows]

    def update_streak(self, assignment_id: str, streak: int) -> None:
        self.db.execute(
            "UPDATE character_assignments SET current_streak = ?, updated_at = ? WHERE id = ?",
            (streak, self.now_iso(), assignment_id),
        )

    def end(
        self,
        assignment_id: str,
        reason: AssignmentEndReason,
        ended_on: date,
        dropped_due_date: date | None = None,
    ) -> None:
        self.db.execute(
            "UPDATE character_assignments SET is_active = 0, ended_on = ?, end_reason = ?, "
            "dropped_due_date = ?, updated_at = ? WHERE id = ?",
            (
                ended_on.isoformat(),
                reason.value,
                dropped_due_date.isoformat() if dropped_due_date else None,
                self.now_iso(),
                assignment_id,
            ),
        )

    def reactivate(self, assignment_id: str, streak: int) -> None:
        """Used only by same-day undo of a stamp-15 completion."""
        self.db.execute(
            "UPDATE character_assignments SET is_active = 1, ended_on = NULL, end_reason = NULL, "
            "dropped_due_date = NULL, current_streak = ?, updated_at = ? WHERE id = ?",
            (streak, self.now_iso(), assignment_id),
        )

    def delete(self, assignment_id: str) -> None:
        """Remove an assignment that never recorded a completion (undo path)."""
        self.db.execute(
            "DELETE FROM character_assignments WHERE id = ?", (assignment_id,)
        )
