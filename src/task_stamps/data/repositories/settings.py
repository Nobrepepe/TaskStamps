from __future__ import annotations

import json
from typing import Any

from task_stamps.data.repositories.base import BaseRepository


class SettingsRepository(BaseRepository):
    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.query_one(
            "SELECT serialized_value FROM app_settings WHERE key = ?", (key,)
        )
        if row is None:
            return default
        return json.loads(row["serialized_value"])

    def set(self, key: str, value: Any) -> None:
        self.db.execute(
            "INSERT INTO app_settings(key, serialized_value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET serialized_value = excluded.serialized_value, "
            "updated_at = excluded.updated_at",
            (key, json.dumps(value), self.now_iso()),
        )

    def all(self) -> dict[str, Any]:
        rows = self.db.query_all("SELECT key, serialized_value FROM app_settings")
        return {row["key"]: json.loads(row["serialized_value"]) for row in rows}
