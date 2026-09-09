from __future__ import annotations

import sqlite3
from datetime import date, datetime

from task_stamps.data.repositories.base import BaseRepository, opt_date, opt_datetime
from task_stamps.domain.enums import ChestSource, TaskWeight
from task_stamps.domain.models import ViceChest, ViceReward
from task_stamps.utilities.ids import new_id


def _row_to_reward(row: sqlite3.Row) -> ViceReward:
    return ViceReward(
        id=row["id"],
        task_weight=TaskWeight(row["task_weight"]),
        tier=row["tier"],
        name=row["name"],
        description=row["description"],
        is_archived=bool(row["is_archived"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_chest(row: sqlite3.Row) -> ViceChest:
    return ViceChest(
        id=row["id"],
        source=ChestSource(row["source"]),
        reward_id=row["reward_id"],
        reward_name_snapshot=row["reward_name_snapshot"],
        completion_id=row["completion_id"],
        boss_date=opt_date(row["boss_date"]),
        granted_at=datetime.fromisoformat(row["granted_at"]),
        claimed_at=opt_datetime(row["claimed_at"]),
    )


class ChestRepository(BaseRepository):
    # -- rewards -----------------------------------------------------------

    def create_reward(
        self, weight: TaskWeight, tier: int, name: str, description: str
    ) -> ViceReward:
        reward_id = new_id()
        now = self.now_iso()
        self.db.execute(
            "INSERT INTO vice_rewards(id, task_weight, tier, name, description, "
            "is_archived, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
            (reward_id, weight.value, tier, name, description, now, now),
        )
        return self.get_reward(reward_id)

    def get_reward(self, reward_id: str) -> ViceReward:
        row = self.db.query_one("SELECT * FROM vice_rewards WHERE id = ?", (reward_id,))
        if row is None:
            raise KeyError(f"vice reward not found: {reward_id}")
        return _row_to_reward(row)

    def update_reward(
        self,
        reward_id: str,
        name: str,
        description: str,
        weight: TaskWeight,
        tier: int,
    ) -> ViceReward:
        self.db.execute(
            "UPDATE vice_rewards SET name = ?, description = ?, task_weight = ?, "
            "tier = ?, updated_at = ? WHERE id = ?",
            (name, description, weight.value, tier, self.now_iso(), reward_id),
        )
        return self.get_reward(reward_id)

    def delete_reward(self, reward_id: str) -> None:
        self.db.execute("DELETE FROM vice_rewards WHERE id = ?", (reward_id,))

    def archive_reward(self, reward_id: str) -> None:
        self.db.execute(
            "UPDATE vice_rewards SET is_archived = 1, updated_at = ? WHERE id = ?",
            (self.now_iso(), reward_id),
        )

    def has_chests(self, reward_id: str) -> bool:
        row = self.db.query_one(
            "SELECT 1 FROM vice_chests WHERE reward_id = ? LIMIT 1", (reward_id,)
        )
        return row is not None

    def list_rewards(self, *, include_archived: bool = False) -> list[ViceReward]:
        clause = "" if include_archived else " WHERE is_archived = 0"
        return [
            _row_to_reward(row)
            for row in self.db.query_all(
                "SELECT * FROM vice_rewards" + clause
                + " ORDER BY task_weight, tier, name COLLATE NOCASE"
            )
        ]

    def rewards_in_slot(self, weight: TaskWeight, tier: int) -> list[ViceReward]:
        """Active rewards in one slot, in a stable order so a seeded draw is
        reproducible."""
        return [
            _row_to_reward(row)
            for row in self.db.query_all(
                "SELECT * FROM vice_rewards WHERE task_weight = ? AND tier = ? "
                "AND is_archived = 0 ORDER BY created_at, id",
                (weight.value, tier),
            )
        ]

    # -- chests ------------------------------------------------------------

    def get_chest(self, chest_id: str) -> ViceChest:
        row = self.db.query_one("SELECT * FROM vice_chests WHERE id = ?", (chest_id,))
        if row is None:
            raise KeyError(f"vice chest not found: {chest_id}")
        return _row_to_chest(row)

    def grant_streak_chest(self, reward: ViceReward, completion_id: str) -> ViceChest:
        chest_id = new_id()
        self.db.execute(
            "INSERT INTO vice_chests(id, source, reward_id, reward_name_snapshot, "
            "completion_id, granted_at) VALUES (?, 'streak', ?, ?, ?, ?)",
            (chest_id, reward.id, reward.name, completion_id, self.now_iso()),
        )
        return self.get_chest(chest_id)

    def grant_boss_chest(self, day: date) -> ViceChest | None:
        """Insert the day's sealed Boss chest, or return None if it already
        exists. The partial unique index on boss_date makes this the single
        source of truth for 'the Boss was newly defeated'."""
        if self.boss_chest_for(day) is not None:
            return None
        chest_id = new_id()
        self.db.execute(
            "INSERT INTO vice_chests(id, source, boss_date, granted_at) "
            "VALUES (?, 'boss', ?, ?)",
            (chest_id, day.isoformat(), self.now_iso()),
        )
        return self.get_chest(chest_id)

    def chest_for_completion(self, completion_id: str) -> ViceChest | None:
        row = self.db.query_one(
            "SELECT * FROM vice_chests WHERE completion_id = ?", (completion_id,)
        )
        return _row_to_chest(row) if row else None

    def boss_chest_for(self, day: date) -> ViceChest | None:
        row = self.db.query_one(
            "SELECT * FROM vice_chests WHERE boss_date = ?", (day.isoformat(),)
        )
        return _row_to_chest(row) if row else None

    def oldest_sealed_boss_chest(self) -> ViceChest | None:
        row = self.db.query_one(
            "SELECT * FROM vice_chests WHERE source = 'boss' AND reward_id IS NULL "
            "ORDER BY granted_at, id LIMIT 1"
        )
        return _row_to_chest(row) if row else None

    def unclaimed_counts(self) -> dict[str, int]:
        return {
            row["reward_id"]: row["count"]
            for row in self.db.query_all(
                "SELECT reward_id, COUNT(*) AS count FROM vice_chests "
                "WHERE reward_id IS NOT NULL AND claimed_at IS NULL GROUP BY reward_id"
            )
        }

    def sealed_boss_count(self) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS count FROM vice_chests "
            "WHERE source = 'boss' AND reward_id IS NULL"
        )
        return int(row["count"]) if row else 0

    def unclaimed_total(self) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS count FROM vice_chests WHERE claimed_at IS NULL"
        )
        return int(row["count"]) if row else 0

    def claim_oldest(self, reward_id: str) -> ViceChest | None:
        row = self.db.query_one(
            "SELECT * FROM vice_chests WHERE reward_id = ? AND claimed_at IS NULL "
            "ORDER BY granted_at, id LIMIT 1",
            (reward_id,),
        )
        if row is None:
            return None
        self.db.execute(
            "UPDATE vice_chests SET claimed_at = ? WHERE id = ?",
            (self.now_iso(), row["id"]),
        )
        return self.get_chest(row["id"])

    def open_boss_chest(self, chest_id: str, reward: ViceReward) -> ViceChest:
        now = self.now_iso()
        self.db.execute(
            "UPDATE vice_chests SET reward_id = ?, reward_name_snapshot = ?, "
            "claimed_at = ? WHERE id = ? AND reward_id IS NULL",
            (reward.id, reward.name, now, chest_id),
        )
        return self.get_chest(chest_id)

    def delete_chest(self, chest_id: str) -> None:
        self.db.execute("DELETE FROM vice_chests WHERE id = ?", (chest_id,))

    def count_granted_between(self, start: date, end: date) -> int:
        # granted_at is a local ISO timestamp; date() would first convert it to
        # UTC and push an evening chest onto the wrong day, so compare the
        # local date prefix the way completion_date is compared elsewhere.
        row = self.db.query_one(
            "SELECT COUNT(*) AS count FROM vice_chests "
            "WHERE substr(granted_at, 1, 10) BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        )
        return int(row["count"]) if row else 0
