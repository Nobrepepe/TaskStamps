from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from task_stamps.data.repositories.base import BaseRepository


@dataclass(frozen=True)
class DailyBossRecord:
    boss_date: date
    character_id: str
    image_asset_version_id: str
    sound_asset_version_id: str | None
    created_at: datetime


def _record(row: sqlite3.Row) -> DailyBossRecord:
    return DailyBossRecord(
        boss_date=date.fromisoformat(row["boss_date"]),
        character_id=row["character_id"],
        image_asset_version_id=row["image_asset_version_id"],
        sound_asset_version_id=row["sound_asset_version_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class BossRepository(BaseRepository):
    def find(self, day: date) -> DailyBossRecord | None:
        row = self.db.query_one(
            "SELECT * FROM daily_bosses WHERE boss_date = ?", (day.isoformat(),)
        )
        return _record(row) if row else None

    def latest_before(self, day: date) -> DailyBossRecord | None:
        row = self.db.query_one(
            "SELECT * FROM daily_bosses WHERE boss_date < ? "
            "ORDER BY boss_date DESC LIMIT 1",
            (day.isoformat(),),
        )
        return _record(row) if row else None

    def create(
        self,
        day: date,
        character_id: str,
        image_asset_version_id: str,
        sound_asset_version_id: str | None,
    ) -> DailyBossRecord:
        self.db.execute(
            "INSERT INTO daily_bosses(boss_date, character_id, image_asset_version_id, "
            "sound_asset_version_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                day.isoformat(),
                character_id,
                image_asset_version_id,
                sound_asset_version_id,
                self.now_iso(),
            ),
        )
        record = self.find(day)
        assert record is not None
        return record
