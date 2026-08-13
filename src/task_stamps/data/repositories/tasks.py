from __future__ import annotations

import sqlite3
from datetime import date, datetime

from task_stamps.data.repositories.base import BaseRepository, opt_datetime
from task_stamps.domain.enums import PoolType, TaskStatus, TaskWeight
from task_stamps.domain.models import HabitTask, PausePeriod
from task_stamps.utilities.ids import new_id


def _row_to_task(row: sqlite3.Row) -> HabitTask:
    return HabitTask(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        weekday_mask=row["weekday_mask"],
        pool_type=PoolType(row["pool_type"]),
        world_id=row["world_id"],
        status=TaskStatus(row["status"]),
        weight=TaskWeight(row["weight"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        archived_at=opt_datetime(row["archived_at"]),
    )


def _row_to_pause(row: sqlite3.Row) -> PausePeriod:
    return PausePeriod(
        id=row["id"],
        task_id=row["task_id"],
        started_on=date.fromisoformat(row["started_on"]),
        ended_on=date.fromisoformat(row["ended_on"]) if row["ended_on"] else None,
    )


class TaskRepository(BaseRepository):
    def create(
        self,
        name: str,
        description: str,
        weekday_mask: int,
        pool_type: PoolType,
        world_id: str | None,
        weight: TaskWeight,
    ) -> HabitTask:
        now = self.now_iso()
        task_id = new_id()
        self.db.execute(
            "INSERT INTO habit_tasks(id, name, description, weekday_mask, pool_type, world_id, "
            "status, weight, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)",
            (
                task_id, name, description, weekday_mask, pool_type.value,
                world_id, weight.value, now, now,
            ),
        )
        return self.get(task_id)

    def get(self, task_id: str) -> HabitTask:
        row = self.db.query_one("SELECT * FROM habit_tasks WHERE id = ?", (task_id,))
        if row is None:
            raise KeyError(f"task not found: {task_id}")
        return _row_to_task(row)

    def list(
        self, status: TaskStatus | None = None, world_id: str | None = None
    ) -> list[HabitTask]:
        sql = "SELECT * FROM habit_tasks WHERE 1 = 1"
        params: list[object] = []
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value)
        if world_id is not None:
            sql += " AND world_id = ?"
            params.append(world_id)
        sql += " ORDER BY name COLLATE NOCASE"
        return [_row_to_task(row) for row in self.db.query_all(sql, params)]

    def update(
        self,
        task_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        weekday_mask: int | None = None,
        pool_type: PoolType | None = None,
        world_id: str | None = ...,  # type: ignore[assignment]
        weight: TaskWeight | None = None,
    ) -> HabitTask:
        current = self.get(task_id)
        self.db.execute(
            "UPDATE habit_tasks SET name = ?, description = ?, weekday_mask = ?, pool_type = ?, "
            "world_id = ?, weight = ?, updated_at = ? WHERE id = ?",
            (
                name if name is not None else current.name,
                description if description is not None else current.description,
                weekday_mask if weekday_mask is not None else current.weekday_mask,
                (pool_type if pool_type is not None else current.pool_type).value,
                current.world_id if world_id is ... else world_id,
                (weight if weight is not None else current.weight).value,
                self.now_iso(),
                task_id,
            ),
        )
        return self.get(task_id)

    def set_status(self, task_id: str, status: TaskStatus) -> None:
        archived_at = self.now_iso() if status == TaskStatus.ARCHIVED else None
        self.db.execute(
            "UPDATE habit_tasks SET status = ?, archived_at = ?, updated_at = ? WHERE id = ?",
            (status.value, archived_at, self.now_iso(), task_id),
        )

    # -- pause periods ---------------------------------------------------

    def open_pause(self, task_id: str, started_on: date) -> PausePeriod:
        pause_id = new_id()
        self.db.execute(
            "INSERT INTO pause_periods(id, task_id, started_on) VALUES (?, ?, ?)",
            (pause_id, task_id, started_on.isoformat()),
        )
        row = self.db.query_one("SELECT * FROM pause_periods WHERE id = ?", (pause_id,))
        assert row is not None
        return _row_to_pause(row)

    def close_open_pause(self, task_id: str, ended_on: date) -> None:
        self.db.execute(
            "UPDATE pause_periods SET ended_on = ? WHERE task_id = ? AND ended_on IS NULL",
            (ended_on.isoformat(), task_id),
        )

    def pauses_for(self, task_id: str) -> list[PausePeriod]:
        rows = self.db.query_all(
            "SELECT * FROM pause_periods WHERE task_id = ? ORDER BY started_on",
            (task_id,),
        )
        return [_row_to_pause(row) for row in rows]
