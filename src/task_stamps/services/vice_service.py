"""Vice Shop inventory management and point spending."""

from __future__ import annotations

from task_stamps.data.database import Database
from task_stamps.data.repositories.vices import ViceRepository
from task_stamps.domain.exceptions import ValidationError
from task_stamps.domain.models import ViceClaim, ViceOffering


class ViceService:
    def __init__(self, db: Database, vices: ViceRepository) -> None:
        self.db = db
        self.vices = vices

    @property
    def balance(self) -> int:
        return self.vices.points_balance()

    def list_offerings(self) -> list[ViceOffering]:
        return self.vices.list()

    def save_offering(
        self,
        offering_id: str | None,
        name: str,
        description: str,
        price: int,
        quantity: int,
    ) -> ViceOffering:
        name = name.strip()
        if not name:
            raise ValidationError("A Vice needs a name.")
        if price < 0:
            raise ValidationError("Price cannot be negative.")
        if quantity < 0:
            raise ValidationError("Inventory cannot be negative.")
        if offering_id is None:
            return self.vices.create(name, description.strip(), price, quantity)
        return self.vices.update(
            offering_id, name, description.strip(), price, quantity
        )

    def remove_offering(self, offering_id: str) -> None:
        self.vices.delete(offering_id)

    def claim(self, offering_id: str) -> ViceClaim:
        with self.db.transaction():
            offering = self.vices.get(offering_id)
            if offering.quantity <= 0:
                raise ValidationError("This Vice is out of stock.")
            if self.vices.points_balance() < offering.price:
                raise ValidationError("You do not have enough points for this Vice.")
            if not self.vices.decrement(offering_id):
                raise ValidationError("This Vice is out of stock.")
            return self.vices.create_claim(offering)
