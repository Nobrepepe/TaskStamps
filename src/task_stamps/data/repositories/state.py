from __future__ import annotations

from datetime import date

from task_stamps.data.repositories.base import BaseRepository

KEY_LAST_EVALUATION_DATE = "last_missed_evaluation_date"
KEY_LAST_KNOWN_DATE = "last_known_local_date"


class AppStateRepository(BaseRepository):
    def get(self, key: str) -> str | None:
        row = self.db.query_one("SELECT value FROM app_state WHERE key = ?", (key,))
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO app_state(key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (key, value, self.now_iso()),
        )

    def get_date(self, key: str) -> date | None:
        value = self.get(key)
        return date.fromisoformat(value) if value else None

    def set_date(self, key: str, value: date) -> None:
        self.set(key, value.isoformat())
