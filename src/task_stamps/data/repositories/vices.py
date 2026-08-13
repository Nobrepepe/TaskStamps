from __future__ import annotations

import sqlite3
from datetime import date, datetime

from task_stamps.data.repositories.base import BaseRepository
from task_stamps.domain.models import ViceClaim, ViceOffering
from task_stamps.utilities.ids import new_id


def _row_to_offering(row: sqlite3.Row) -> ViceOffering:
    return ViceOffering(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        price=row["price"],
        quantity=row["quantity"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_claim(row: sqlite3.Row) -> ViceClaim:
    return ViceClaim(
        id=row["id"],
        offering_id=row["offering_id"],
        offering_name_snapshot=row["offering_name_snapshot"],
        price_paid=row["price_paid"],
        claimed_at=datetime.fromisoformat(row["claimed_at"]),
    )


class ViceRepository(BaseRepository):
    def create(self, name: str, description: str, price: int, quantity: int) -> ViceOffering:
        offering_id = new_id()
        now = self.now_iso()
        self.db.execute(
            "INSERT INTO vice_offerings(id, name, description, price, quantity, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (offering_id, name, description, price, quantity, now, now),
        )
        return self.get(offering_id)

    def get(self, offering_id: str) -> ViceOffering:
        row = self.db.query_one(
            "SELECT * FROM vice_offerings WHERE id = ?", (offering_id,)
        )
        if row is None:
            raise KeyError(f"vice offering not found: {offering_id}")
        return _row_to_offering(row)

    def list(self) -> list[ViceOffering]:
        return [
            _row_to_offering(row)
            for row in self.db.query_all(
                "SELECT * FROM vice_offerings ORDER BY name COLLATE NOCASE"
            )
        ]

    def update(
        self, offering_id: str, name: str, description: str, price: int, quantity: int
    ) -> ViceOffering:
        self.db.execute(
            "UPDATE vice_offerings SET name = ?, description = ?, price = ?, quantity = ?, "
            "updated_at = ? WHERE id = ?",
            (name, description, price, quantity, self.now_iso(), offering_id),
        )
        return self.get(offering_id)

    def delete(self, offering_id: str) -> None:
        self.db.execute("DELETE FROM vice_offerings WHERE id = ?", (offering_id,))

    def decrement(self, offering_id: str) -> bool:
        cursor = self.db.execute(
            "UPDATE vice_offerings SET quantity = quantity - 1, updated_at = ? "
            "WHERE id = ? AND quantity > 0",
            (self.now_iso(), offering_id),
        )
        return cursor.rowcount == 1

    def create_claim(self, offering: ViceOffering) -> ViceClaim:
        claim_id = new_id()
        self.db.execute(
            "INSERT INTO vice_claims(id, offering_id, offering_name_snapshot, price_paid, claimed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (claim_id, offering.id, offering.name, offering.price, self.now_iso()),
        )
        row = self.db.query_one("SELECT * FROM vice_claims WHERE id = ?", (claim_id,))
        assert row is not None
        return _row_to_claim(row)

    def points_balance(self) -> int:
        row = self.db.query_one(
            "SELECT "
            "COALESCE((SELECT SUM(reward_points) FROM task_completions WHERE is_reversed = 0), 0) "
            "- COALESCE((SELECT SUM(price_paid) FROM vice_claims), 0) "
            "- COALESCE((SELECT SUM(points_deducted) FROM task_penalties), 0) AS balance"
        )
        return max(0, int(row["balance"])) if row else 0

    def charge_task_penalty(
        self, task_id: str, penalty_date: date, reason: str, points: int
    ) -> int:
        """Record one idempotent penalty, capped at the available balance."""
        existing = self.db.query_one(
            "SELECT points_deducted FROM task_penalties "
            "WHERE task_id = ? AND penalty_date = ? AND reason = ?",
            (task_id, penalty_date.isoformat(), reason),
        )
        if existing is not None:
            return int(existing["points_deducted"])
        deducted = min(max(points, 0), self.points_balance())
        self.db.execute(
            "INSERT INTO task_penalties(id, task_id, penalty_date, reason, "
            "points_assessed, points_deducted, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                new_id(), task_id, penalty_date.isoformat(), reason,
                max(points, 0), deducted, self.now_iso(),
            ),
        )
        return deducted

    def consecutive_misses(self, task_id: str) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS count FROM task_penalties "
            "WHERE task_id = ? AND reason = 'missed' AND penalty_date > "
            "COALESCE((SELECT MAX(completion_date) FROM task_completions "
            "WHERE task_id = ? AND is_reversed = 0), '0001-01-01')",
            (task_id, task_id),
        )
        return int(row["count"]) if row else 0
