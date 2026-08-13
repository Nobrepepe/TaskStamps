from __future__ import annotations

import sqlite3
from datetime import datetime

from task_stamps.data.repositories.base import BaseRepository
from task_stamps.domain.models import World
from task_stamps.utilities.ids import new_id


def _row_to_world(row: sqlite3.Row) -> World:
    return World(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        cover_asset_version_id=row["cover_asset_version_id"],
        is_archived=bool(row["is_archived"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class WorldRepository(BaseRepository):
    def create(self, name: str, description: str = "") -> World:
        now = self.now_iso()
        world_id = new_id()
        self.db.execute(
            "INSERT INTO worlds(id, name, description, is_archived, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            (world_id, name, description, now, now),
        )
        return self.get(world_id)

    def get(self, world_id: str) -> World:
        row = self.db.query_one("SELECT * FROM worlds WHERE id = ?", (world_id,))
        if row is None:
            raise KeyError(f"world not found: {world_id}")
        return _row_to_world(row)

    def find(self, world_id: str | None) -> World | None:
        if world_id is None:
            return None
        row = self.db.query_one("SELECT * FROM worlds WHERE id = ?", (world_id,))
        return _row_to_world(row) if row else None

    def list(self, include_archived: bool = False) -> list[World]:
        sql = "SELECT * FROM worlds"
        if not include_archived:
            sql += " WHERE is_archived = 0"
        sql += " ORDER BY name COLLATE NOCASE"
        return [_row_to_world(row) for row in self.db.query_all(sql)]

    def update(
        self,
        world_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        cover_asset_version_id: str | None = ...,  # type: ignore[assignment]
    ) -> World:
        world = self.get(world_id)
        new_cover = (
            world.cover_asset_version_id
            if cover_asset_version_id is ...
            else cover_asset_version_id
        )
        self.db.execute(
            "UPDATE worlds SET name = ?, description = ?, cover_asset_version_id = ?, updated_at = ? "
            "WHERE id = ?",
            (
                name if name is not None else world.name,
                description if description is not None else world.description,
                new_cover,
                self.now_iso(),
                world_id,
            ),
        )
        return self.get(world_id)

    def set_archived(self, world_id: str, archived: bool) -> None:
        self.db.execute(
            "UPDATE worlds SET is_archived = ?, updated_at = ? WHERE id = ?",
            (1 if archived else 0, self.now_iso(), world_id),
        )
