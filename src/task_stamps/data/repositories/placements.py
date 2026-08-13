from __future__ import annotations

import sqlite3
from datetime import date, datetime

from task_stamps.data.repositories.base import BaseRepository
from task_stamps.domain.models import BoardStamp, StampPlacement
from task_stamps.utilities.ids import new_id


def _row_to_placement(row: sqlite3.Row) -> StampPlacement:
    return StampPlacement(
        id=row["id"],
        completion_id=row["completion_id"],
        board_date=date.fromisoformat(row["board_date"]),
        x_normalized=row["x_normalized"],
        y_normalized=row["y_normalized"],
        rotation_degrees=row["rotation_degrees"],
        scale=row["scale"],
        z_index=row["z_index"],
        image_asset_version_id=row["image_asset_version_id"],
        sound_asset_version_id=row["sound_asset_version_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


_BOARD_SQL = """
    SELECT p.*,
           c.task_id            AS c_task_id,
           c.completion_date    AS c_completion_date,
           c.completed_at       AS c_completed_at,
           c.streak_number      AS c_streak_number,
           c.task_name_snapshot AS c_task_name,
           c.character_name_snapshot AS c_character_name,
           img.relative_path    AS image_path,
           snd.relative_path    AS sound_path
    FROM stamp_placements p
    JOIN task_completions c ON c.id = p.completion_id
    JOIN asset_versions img ON img.id = p.image_asset_version_id
    LEFT JOIN asset_versions snd ON snd.id = p.sound_asset_version_id
"""


def _row_to_board_stamp(row: sqlite3.Row) -> BoardStamp:
    return BoardStamp(
        placement=_row_to_placement(row),
        completion_id=row["completion_id"],
        task_id=row["c_task_id"],
        completion_date=date.fromisoformat(row["c_completion_date"]),
        completed_at=datetime.fromisoformat(row["c_completed_at"]),
        streak_number=row["c_streak_number"],
        task_name_snapshot=row["c_task_name"],
        character_name_snapshot=row["c_character_name"],
        image_relative_path=row["image_path"],
        sound_relative_path=row["sound_path"],
    )


class PlacementRepository(BaseRepository):
    def create(
        self,
        *,
        completion_id: str,
        board_date: date,
        x_normalized: float,
        y_normalized: float,
        rotation_degrees: float,
        scale: float,
        z_index: int,
        image_asset_version_id: str,
        sound_asset_version_id: str | None,
    ) -> StampPlacement:
        placement_id = new_id()
        self.db.execute(
            "INSERT INTO stamp_placements(id, completion_id, board_date, x_normalized, "
            "y_normalized, rotation_degrees, scale, z_index, image_asset_version_id, "
            "sound_asset_version_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                placement_id,
                completion_id,
                board_date.isoformat(),
                x_normalized,
                y_normalized,
                rotation_degrees,
                scale,
                z_index,
                image_asset_version_id,
                sound_asset_version_id,
                self.now_iso(),
            ),
        )
        row = self.db.query_one(
            "SELECT * FROM stamp_placements WHERE id = ?", (placement_id,)
        )
        assert row is not None
        return _row_to_placement(row)

    def list_for_date(self, board_date: date) -> list[StampPlacement]:
        rows = self.db.query_all(
            "SELECT * FROM stamp_placements WHERE board_date = ? ORDER BY z_index",
            (board_date.isoformat(),),
        )
        return [_row_to_placement(row) for row in rows]

    def board_for_date(self, board_date: date) -> list[BoardStamp]:
        rows = self.db.query_all(
            _BOARD_SQL + " WHERE p.board_date = ? ORDER BY p.z_index",
            (board_date.isoformat(),),
        )
        return [_row_to_board_stamp(row) for row in rows]

    def board_for_range(self, start: date, end_inclusive: date) -> list[BoardStamp]:
        rows = self.db.query_all(
            _BOARD_SQL + " WHERE p.board_date BETWEEN ? AND ? "
            "ORDER BY p.board_date, p.z_index",
            (start.isoformat(), end_inclusive.isoformat()),
        )
        return [_row_to_board_stamp(row) for row in rows]

    def count_for_date(self, board_date: date) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS n FROM stamp_placements WHERE board_date = ?",
            (board_date.isoformat(),),
        )
        return int(row["n"]) if row else 0

    def get_for_completion(self, completion_id: str) -> StampPlacement | None:
        row = self.db.query_one(
            "SELECT * FROM stamp_placements WHERE completion_id = ?", (completion_id,)
        )
        return _row_to_placement(row) if row else None

    def delete_for_completion(self, completion_id: str) -> None:
        self.db.execute(
            "DELETE FROM stamp_placements WHERE completion_id = ?", (completion_id,)
        )

    def boards_with_task(self, task_id: str, limit: int = 10) -> list[date]:
        rows = self.db.query_all(
            "SELECT DISTINCT p.board_date FROM stamp_placements p "
            "JOIN task_completions c ON c.id = p.completion_id "
            "WHERE c.task_id = ? ORDER BY p.board_date DESC LIMIT ?",
            (task_id, limit),
        )
        return [date.fromisoformat(row["board_date"]) for row in rows]
