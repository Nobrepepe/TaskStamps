from __future__ import annotations

import sqlite3
from datetime import date, datetime

from task_stamps.data.repositories.base import BaseRepository
from task_stamps.domain.enums import STAMPS_PER_CHARACTER, CharacterStatus, PoolType
from task_stamps.domain.models import Character, CharacterStamp
from task_stamps.utilities.ids import new_id


def _row_to_character(row: sqlite3.Row) -> Character:
    return Character(
        id=row["id"],
        world_id=row["world_id"],
        name=row["name"],
        description=row["description"],
        portrait_asset_version_id=row["portrait_asset_version_id"],
        boss_image_asset_version_id=row["boss_image_asset_version_id"],
        boss_sound_asset_version_id=row["boss_sound_asset_version_id"],
        default_sound_asset_version_id=row["default_sound_asset_version_id"],
        status=CharacterStatus(row["status"]),
        is_archived=bool(row["is_archived"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_stamp(row: sqlite3.Row) -> CharacterStamp:
    return CharacterStamp(
        id=row["id"],
        character_id=row["character_id"],
        sequence_number=row["sequence_number"],
        image_asset_version_id=row["image_asset_version_id"],
        sound_asset_version_id=row["sound_asset_version_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class CharacterRepository(BaseRepository):
    def create(self, world_id: str, name: str, description: str = "") -> Character:
        now = self.now_iso()
        character_id = new_id()
        self.db.execute(
            "INSERT INTO characters(id, world_id, name, description, status, is_archived, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, 'draft', 0, ?, ?)",
            (character_id, world_id, name, description, now, now),
        )
        # Pre-create the 15 numbered stamp slots.
        for sequence in range(1, STAMPS_PER_CHARACTER + 1):
            self.db.execute(
                "INSERT INTO character_stamps(id, character_id, sequence_number, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (new_id(), character_id, sequence, now, now),
            )
        return self.get(character_id)

    def get(self, character_id: str) -> Character:
        row = self.db.query_one("SELECT * FROM characters WHERE id = ?", (character_id,))
        if row is None:
            raise KeyError(f"character not found: {character_id}")
        return _row_to_character(row)

    def list(
        self, world_id: str | None = None, include_archived: bool = False
    ) -> list[Character]:
        sql = "SELECT * FROM characters WHERE 1 = 1"
        params: list[object] = []
        if world_id is not None:
            sql += " AND world_id = ?"
            params.append(world_id)
        if not include_archived:
            sql += " AND is_archived = 0"
        sql += " ORDER BY name COLLATE NOCASE"
        return [_row_to_character(row) for row in self.db.query_all(sql, params)]

    def update(
        self,
        character_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        world_id: str | None = None,
        portrait_asset_version_id: str | None = ...,  # type: ignore[assignment]
        boss_image_asset_version_id: str | None = ...,  # type: ignore[assignment]
        boss_sound_asset_version_id: str | None = ...,  # type: ignore[assignment]
        default_sound_asset_version_id: str | None = ...,  # type: ignore[assignment]
    ) -> Character:
        current = self.get(character_id)
        self.db.execute(
            "UPDATE characters SET name = ?, description = ?, world_id = ?, "
            "portrait_asset_version_id = ?, boss_image_asset_version_id = ?, "
            "boss_sound_asset_version_id = ?, default_sound_asset_version_id = ?, updated_at = ? "
            "WHERE id = ?",
            (
                name if name is not None else current.name,
                description if description is not None else current.description,
                world_id if world_id is not None else current.world_id,
                current.portrait_asset_version_id
                if portrait_asset_version_id is ...
                else portrait_asset_version_id,
                current.boss_image_asset_version_id
                if boss_image_asset_version_id is ...
                else boss_image_asset_version_id,
                current.boss_sound_asset_version_id
                if boss_sound_asset_version_id is ...
                else boss_sound_asset_version_id,
                current.default_sound_asset_version_id
                if default_sound_asset_version_id is ...
                else default_sound_asset_version_id,
                self.now_iso(),
                character_id,
            ),
        )
        return self.get(character_id)

    def boss_pool(self) -> list[Character]:
        rows = self.db.query_all(
            "SELECT * FROM characters WHERE is_archived = 0 "
            "AND boss_image_asset_version_id IS NOT NULL "
            "ORDER BY created_at, id"
        )
        return [_row_to_character(row) for row in rows]

    def set_status(self, character_id: str, status: CharacterStatus) -> None:
        self.db.execute(
            "UPDATE characters SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, self.now_iso(), character_id),
        )

    def set_archived(self, character_id: str, archived: bool) -> None:
        self.db.execute(
            "UPDATE characters SET is_archived = ?, updated_at = ? WHERE id = ?",
            (1 if archived else 0, self.now_iso(), character_id),
        )

    # -- stamps ----------------------------------------------------------

    def stamps_for(self, character_id: str) -> list[CharacterStamp]:
        rows = self.db.query_all(
            "SELECT * FROM character_stamps WHERE character_id = ? ORDER BY sequence_number",
            (character_id,),
        )
        return [_row_to_stamp(row) for row in rows]

    def stamp_by_sequence(self, character_id: str, sequence: int) -> CharacterStamp | None:
        row = self.db.query_one(
            "SELECT * FROM character_stamps WHERE character_id = ? AND sequence_number = ?",
            (character_id, sequence),
        )
        return _row_to_stamp(row) if row else None

    def get_stamp(self, stamp_id: str) -> CharacterStamp:
        row = self.db.query_one("SELECT * FROM character_stamps WHERE id = ?", (stamp_id,))
        if row is None:
            raise KeyError(f"stamp not found: {stamp_id}")
        return _row_to_stamp(row)

    def set_stamp_image(
        self, character_id: str, sequence: int, image_asset_version_id: str | None
    ) -> None:
        self.db.execute(
            "UPDATE character_stamps SET image_asset_version_id = ?, updated_at = ? "
            "WHERE character_id = ? AND sequence_number = ?",
            (image_asset_version_id, self.now_iso(), character_id, sequence),
        )

    def set_stamp_sound(
        self, character_id: str, sequence: int, sound_asset_version_id: str | None
    ) -> None:
        self.db.execute(
            "UPDATE character_stamps SET sound_asset_version_id = ?, updated_at = ? "
            "WHERE character_id = ? AND sequence_number = ?",
            (sound_asset_version_id, self.now_iso(), character_id, sequence),
        )

    def stamp_image_count(self, character_id: str) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS n FROM character_stamps "
            "WHERE character_id = ? AND image_asset_version_id IS NOT NULL",
            (character_id,),
        )
        return int(row["n"]) if row else 0

    # -- eligibility -----------------------------------------------------

    def eligible_character_ids(
        self, pool_type: PoolType, world_id: str | None
    ) -> list[str]:
        """Characters that are ready, unarchived, fully stamped, in an
        unarchived world, and not held by any active assignment."""
        sql = """
            SELECT c.id FROM characters c
            JOIN worlds w ON w.id = c.world_id AND w.is_archived = 0
            WHERE c.is_archived = 0
              AND c.status = 'ready'
              AND (SELECT COUNT(*) FROM character_stamps s
                   WHERE s.character_id = c.id
                     AND s.image_asset_version_id IS NOT NULL) = ?
              AND NOT EXISTS (SELECT 1 FROM character_assignments a
                              WHERE a.character_id = c.id AND a.is_active = 1)
        """
        params: list[object] = [STAMPS_PER_CHARACTER]
        if pool_type == PoolType.SPECIFIC_WORLD:
            sql += " AND c.world_id = ?"
            params.append(world_id)
        sql += " ORDER BY c.id"
        return [row["id"] for row in self.db.query_all(sql, params)]

    def reserved_character_ids(self, on_date: date, exclude_task_id: str | None) -> list[str]:
        """Characters whose 15-stamp run finished today.

        They stay reserved from other tasks until the day's undo window
        closes, so undoing stamp 15 can always restore them.
        """
        sql = (
            "SELECT DISTINCT character_id FROM character_assignments "
            "WHERE end_reason = 'completed' AND ended_on = ?"
        )
        params: list[object] = [on_date.isoformat()]
        if exclude_task_id is not None:
            sql += " AND task_id != ?"
            params.append(exclude_task_id)
        return [row["character_id"] for row in self.db.query_all(sql, params)]

    def world_stats(self, world_id: str) -> dict[str, int]:
        total = self.db.query_one(
            "SELECT COUNT(*) AS n FROM characters WHERE world_id = ? AND is_archived = 0",
            (world_id,),
        )["n"]
        draft = self.db.query_one(
            "SELECT COUNT(*) AS n FROM characters "
            "WHERE world_id = ? AND is_archived = 0 AND status = 'draft'",
            (world_id,),
        )["n"]
        assigned = self.db.query_one(
            "SELECT COUNT(DISTINCT a.character_id) AS n FROM character_assignments a "
            "JOIN characters c ON c.id = a.character_id "
            "WHERE c.world_id = ? AND a.is_active = 1",
            (world_id,),
        )["n"]
        eligible = len(self.eligible_character_ids(PoolType.SPECIFIC_WORLD, world_id))
        return {
            "total": int(total),
            "draft": int(draft),
            "assigned": int(assigned),
            "available": int(eligible),
        }
