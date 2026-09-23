from __future__ import annotations

import sqlite3
from datetime import date, datetime

from task_stamps.data.repositories.base import BaseRepository, opt_date, opt_datetime
from task_stamps.domain.enums import (
    GoalEntryOutcome,
    GoalLegEndReason,
    GoalStatus,
    PoolType,
)
from task_stamps.domain.models import Goal, GoalEntry, GoalLeg
from task_stamps.utilities.ids import new_id


def _row_to_goal(row: sqlite3.Row) -> Goal:
    return Goal(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        unit=row["unit"],
        baseline_value=row["baseline_value"],
        target_value=row["target_value"],
        current_value=row["current_value"],
        reward_id=row["reward_id"],
        pool_type=PoolType(row["pool_type"]),
        world_id=row["world_id"],
        status=GoalStatus(row["status"]),
        last_reviewed_on=date.fromisoformat(row["last_reviewed_on"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        finished_at=opt_datetime(row["finished_at"]),
    )


def _row_to_leg(row: sqlite3.Row) -> GoalLeg:
    return GoalLeg(
        id=row["id"],
        goal_id=row["goal_id"],
        ordinal=row["ordinal"],
        character_id=row["character_id"],
        baseline_value=row["baseline_value"],
        target_value=row["target_value"],
        started_on=date.fromisoformat(row["started_on"]),
        ended_on=opt_date(row["ended_on"]),
        end_reason=GoalLegEndReason(row["end_reason"]) if row["end_reason"] else None,
        end_value=row["end_value"],
        is_active=bool(row["is_active"]),
    )


def _row_to_entry(row: sqlite3.Row) -> GoalEntry:
    return GoalEntry(
        id=row["id"],
        goal_id=row["goal_id"],
        leg_id=row["leg_id"],
        delta=row["delta"],
        value_before=row["value_before"],
        value_after=row["value_after"],
        outcome=GoalEntryOutcome(row["outcome"]),
        previous_reviewed_on=date.fromisoformat(row["previous_reviewed_on"]),
        entered_on=date.fromisoformat(row["entered_on"]),
        entered_at=datetime.fromisoformat(row["entered_at"]),
    )


class GoalRepository(BaseRepository):
    # -- goals -------------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        description: str,
        unit: str,
        baseline_value: float,
        target_value: float,
        reward_id: str,
        pool_type: PoolType,
        world_id: str | None,
        reviewed_on: date,
    ) -> Goal:
        goal_id = new_id()
        now = self.now_iso()
        self.db.execute(
            "INSERT INTO goals(id, name, description, unit, baseline_value, target_value, "
            "current_value, reward_id, pool_type, world_id, status, last_reviewed_on, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
            (
                goal_id, name, description, unit, baseline_value, target_value,
                baseline_value, reward_id, pool_type.value, world_id,
                reviewed_on.isoformat(), now, now,
            ),
        )
        return self.get(goal_id)

    def get(self, goal_id: str) -> Goal:
        row = self.db.query_one("SELECT * FROM goals WHERE id = ?", (goal_id,))
        if row is None:
            raise KeyError(f"goal not found: {goal_id}")
        return _row_to_goal(row)

    def list(self, *, include_removed: bool = False) -> list[Goal]:
        clause = "" if include_removed else " WHERE status != 'removed'"
        return [
            _row_to_goal(row)
            for row in self.db.query_all(
                "SELECT * FROM goals" + clause + " ORDER BY created_at, id"
            )
        ]

    def update(self, goal_id: str, **fields: object) -> Goal:
        """Write the given columns. Enum and date values are stored by value."""
        if not fields:
            return self.get(goal_id)
        columns = []
        params: list[object] = []
        for column, value in fields.items():
            columns.append(f"{column} = ?")
            if isinstance(value, (GoalStatus, PoolType)):
                value = value.value
            elif isinstance(value, (date, datetime)):
                value = value.isoformat()
            params.append(value)
        columns.append("updated_at = ?")
        params.extend([self.now_iso(), goal_id])
        self.db.execute(f"UPDATE goals SET {', '.join(columns)} WHERE id = ?", params)
        return self.get(goal_id)

    def delete(self, goal_id: str) -> None:
        """Hard delete; only for goals that never earned a chest."""
        self.db.execute("DELETE FROM goal_entries WHERE goal_id = ?", (goal_id,))
        self.db.execute("DELETE FROM goal_legs WHERE goal_id = ?", (goal_id,))
        self.db.execute("DELETE FROM goals WHERE id = ?", (goal_id,))

    def has_chests(self, goal_id: str) -> bool:
        row = self.db.query_one(
            "SELECT 1 FROM vice_chests c JOIN goal_legs l ON l.id = c.goal_leg_id "
            "WHERE l.goal_id = ? LIMIT 1",
            (goal_id,),
        )
        return row is not None

    # -- legs --------------------------------------------------------------

    def create_leg(
        self,
        goal_id: str,
        character_id: str | None,
        baseline_value: float,
        target_value: float,
        started_on: date,
    ) -> GoalLeg:
        row = self.db.query_one(
            "SELECT COALESCE(MAX(ordinal), 0) AS n FROM goal_legs WHERE goal_id = ?",
            (goal_id,),
        )
        leg_id = new_id()
        now = self.now_iso()
        self.db.execute(
            "INSERT INTO goal_legs(id, goal_id, ordinal, character_id, baseline_value, "
            "target_value, started_on, is_active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (
                leg_id, goal_id, int(row["n"]) + 1, character_id, baseline_value,
                target_value, started_on.isoformat(), now, now,
            ),
        )
        return self.get_leg(leg_id)

    def get_leg(self, leg_id: str) -> GoalLeg:
        row = self.db.query_one("SELECT * FROM goal_legs WHERE id = ?", (leg_id,))
        if row is None:
            raise KeyError(f"goal leg not found: {leg_id}")
        return _row_to_leg(row)

    def active_leg(self, goal_id: str) -> GoalLeg | None:
        row = self.db.query_one(
            "SELECT * FROM goal_legs WHERE goal_id = ? AND is_active = 1", (goal_id,)
        )
        return _row_to_leg(row) if row else None

    def active_leg_for_character(self, character_id: str) -> GoalLeg | None:
        row = self.db.query_one(
            "SELECT * FROM goal_legs WHERE character_id = ? AND is_active = 1",
            (character_id,),
        )
        return _row_to_leg(row) if row else None

    def legs_for_goal(self, goal_id: str) -> list[GoalLeg]:
        return [
            _row_to_leg(row)
            for row in self.db.query_all(
                "SELECT * FROM goal_legs WHERE goal_id = ? ORDER BY ordinal", (goal_id,)
            )
        ]

    def legs_without_character(self) -> list[GoalLeg]:
        return [
            _row_to_leg(row)
            for row in self.db.query_all(
                "SELECT l.* FROM goal_legs l JOIN goals g ON g.id = l.goal_id "
                "WHERE l.is_active = 1 AND l.character_id IS NULL "
                "AND g.status IN ('active', 'reached') ORDER BY l.created_at"
            )
        ]

    def set_leg_character(self, leg_id: str, character_id: str | None) -> None:
        self.db.execute(
            "UPDATE goal_legs SET character_id = ?, updated_at = ? WHERE id = ?",
            (character_id, self.now_iso(), leg_id),
        )

    def set_leg_target(self, leg_id: str, target_value: float) -> None:
        self.db.execute(
            "UPDATE goal_legs SET target_value = ?, updated_at = ? WHERE id = ?",
            (target_value, self.now_iso(), leg_id),
        )

    def end_leg(
        self,
        leg_id: str,
        reason: GoalLegEndReason,
        ended_on: date,
        end_value: float,
    ) -> None:
        self.db.execute(
            "UPDATE goal_legs SET is_active = 0, ended_on = ?, end_reason = ?, "
            "end_value = ?, updated_at = ? WHERE id = ?",
            (ended_on.isoformat(), reason.value, end_value, self.now_iso(), leg_id),
        )

    def reopen_leg(self, leg_id: str) -> None:
        """Used only by same-day undo of the entry that ended the leg."""
        self.db.execute(
            "UPDATE goal_legs SET is_active = 1, ended_on = NULL, end_reason = NULL, "
            "end_value = NULL, updated_at = ? WHERE id = ?",
            (self.now_iso(), leg_id),
        )

    def delete_leg(self, leg_id: str) -> None:
        self.db.execute("DELETE FROM goal_legs WHERE id = ?", (leg_id,))

    # -- entries -----------------------------------------------------------

    def add_entry(
        self,
        *,
        goal_id: str,
        leg_id: str,
        delta: float,
        value_before: float,
        value_after: float,
        outcome: GoalEntryOutcome,
        previous_reviewed_on: date,
        entered_on: date,
    ) -> GoalEntry:
        entry_id = new_id()
        self.db.execute(
            "INSERT INTO goal_entries(id, goal_id, leg_id, delta, value_before, value_after, "
            "outcome, previous_reviewed_on, entered_on, entered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry_id, goal_id, leg_id, delta, value_before, value_after,
                outcome.value, previous_reviewed_on.isoformat(),
                entered_on.isoformat(), self.now_iso(),
            ),
        )
        return self.get_entry(entry_id)

    def get_entry(self, entry_id: str) -> GoalEntry:
        row = self.db.query_one("SELECT * FROM goal_entries WHERE id = ?", (entry_id,))
        if row is None:
            raise KeyError(f"goal entry not found: {entry_id}")
        return _row_to_entry(row)

    def entries_for_goal(self, goal_id: str, limit: int = 20) -> list[GoalEntry]:
        """Newest first. entered_at ties (same clock tick) fall back to rowid."""
        return [
            _row_to_entry(row)
            for row in self.db.query_all(
                "SELECT * FROM goal_entries WHERE goal_id = ? "
                "ORDER BY entered_at DESC, rowid DESC LIMIT ?",
                (goal_id, limit),
            )
        ]

    def delete_entry(self, entry_id: str) -> None:
        self.db.execute("DELETE FROM goal_entries WHERE id = ?", (entry_id,))
