from __future__ import annotations

from datetime import date, datetime

from task_stamps.data.database import Database
from task_stamps.utilities.clock import Clock


class BaseRepository:
    def __init__(self, db: Database, clock: Clock) -> None:
        self.db = db
        self.clock = clock

    def now_iso(self) -> str:
        return self.clock.now().isoformat()


def opt_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def opt_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
