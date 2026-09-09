from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from task_stamps.data.repositories.base import BaseRepository
from task_stamps.domain.enums import AssetType
from task_stamps.domain.models import Asset, AssetVersion
from task_stamps.utilities.ids import new_id

# Every column that may reference an asset version; used to protect
# referenced files from cleanup.
_REFERENCING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("worlds", "cover_asset_version_id"),
    ("characters", "portrait_asset_version_id"),
    ("characters", "boss_image_asset_version_id"),
    ("characters", "boss_sound_asset_version_id"),
    ("characters", "default_sound_asset_version_id"),
    ("character_stamps", "image_asset_version_id"),
    ("character_stamps", "sound_asset_version_id"),
    ("stamp_placements", "image_asset_version_id"),
    ("stamp_placements", "sound_asset_version_id"),
    ("daily_bosses", "image_asset_version_id"),
    ("daily_bosses", "sound_asset_version_id"),
)

# Settings that hold an asset version id. These live in app_settings as a
# JSON-encoded string rather than in a column, so cleanup has to look for them
# here too — otherwise it deletes the global sounds and leaves the setting
# pointing at a version that no longer exists.
_REFERENCING_SETTINGS: tuple[str, ...] = (
    "fallback_sound_version_id",
    "boss_fallback_sound_version_id",
)


def _row_to_asset(row: sqlite3.Row) -> Asset:
    return Asset(
        id=row["id"],
        asset_type=AssetType(row["asset_type"]),
        current_version_id=row["current_version_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_version(row: sqlite3.Row) -> AssetVersion:
    return AssetVersion(
        id=row["id"],
        asset_id=row["asset_id"],
        relative_path=row["relative_path"],
        file_name=row["file_name"],
        mime_type=row["mime_type"],
        file_size=row["file_size"],
        checksum=row["checksum"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class AssetRepository(BaseRepository):
    def create_asset(self, asset_type: AssetType) -> Asset:
        asset_id = new_id()
        self.db.execute(
            "INSERT INTO assets(id, asset_type, created_at) VALUES (?, ?, ?)",
            (asset_id, asset_type.value, self.now_iso()),
        )
        return self.get_asset(asset_id)

    def get_asset(self, asset_id: str) -> Asset:
        row = self.db.query_one("SELECT * FROM assets WHERE id = ?", (asset_id,))
        if row is None:
            raise KeyError(f"asset not found: {asset_id}")
        return _row_to_asset(row)

    def add_version(
        self,
        *,
        version_id: str,
        asset_id: str,
        relative_path: str,
        file_name: str,
        mime_type: str,
        file_size: int,
        checksum: str,
    ) -> AssetVersion:
        self.db.execute(
            "INSERT INTO asset_versions(id, asset_id, relative_path, file_name, mime_type, "
            "file_size, checksum, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version_id,
                asset_id,
                relative_path,
                file_name,
                mime_type,
                file_size,
                checksum,
                self.now_iso(),
            ),
        )
        self.db.execute(
            "UPDATE assets SET current_version_id = ? WHERE id = ?",
            (version_id, asset_id),
        )
        return self.get_version(version_id)

    def get_version(self, version_id: str) -> AssetVersion:
        row = self.db.query_one(
            "SELECT * FROM asset_versions WHERE id = ?", (version_id,)
        )
        if row is None:
            raise KeyError(f"asset version not found: {version_id}")
        return _row_to_version(row)

    def find_version(self, version_id: str | None) -> AssetVersion | None:
        if version_id is None:
            return None
        row = self.db.query_one(
            "SELECT * FROM asset_versions WHERE id = ?", (version_id,)
        )
        return _row_to_version(row) if row else None

    def is_version_referenced(self, version_id: str) -> bool:
        for table, column in _REFERENCING_COLUMNS:
            row = self.db.query_one(
                f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (version_id,)
            )
            if row is not None:
                return True
        placeholders = ", ".join("?" for _ in _REFERENCING_SETTINGS)
        row = self.db.query_one(
            f"SELECT 1 FROM app_settings WHERE key IN ({placeholders}) "
            "AND serialized_value = ? LIMIT 1",
            (*_REFERENCING_SETTINGS, json.dumps(version_id)),
        )
        return row is not None

    def unreferenced_versions(self) -> list[AssetVersion]:
        conditions = [
            f"NOT EXISTS (SELECT 1 FROM {table} WHERE {column} = av.id)"
            for table, column in _REFERENCING_COLUMNS
        ]
        placeholders = ", ".join("?" for _ in _REFERENCING_SETTINGS)
        # A settings value is the id JSON-encoded, which for an id is just the
        # id in double quotes.
        conditions.append(
            f"NOT EXISTS (SELECT 1 FROM app_settings WHERE key IN ({placeholders}) "
            "AND serialized_value = '\"' || av.id || '\"')"
        )
        rows = self.db.query_all(
            "SELECT av.* FROM asset_versions av WHERE " + " AND ".join(conditions),
            _REFERENCING_SETTINGS,
        )
        return [_row_to_version(row) for row in rows]

    def delete_version(self, version_id: str) -> None:
        self.db.execute(
            "UPDATE assets SET current_version_id = NULL WHERE current_version_id = ?",
            (version_id,),
        )
        self.db.execute("DELETE FROM asset_versions WHERE id = ?", (version_id,))
