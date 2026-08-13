"""Spend task-completion points on user-defined rewards."""

from __future__ import annotations

import flet as ft

from task_stamps.components.common import MUTED_TEXT, card, confirm_dialog
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.domain.models import ViceOffering
from task_stamps.views.base import View


class ViceShopView(View):
    def build(self) -> ft.Control:
        self.balance_text = ft.Text(size=18, weight=ft.FontWeight.W_600)
        self.grid = ft.GridView(
            expand=True,
            max_extent=360,
            child_aspect_ratio=1.55,
            spacing=14,
            run_spacing=14,
            padding=ft.padding.only(bottom=24),
        )
        header = ft.Container(
            padding=ft.padding.only(left=24, right=24, top=18, bottom=12),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("Vice Shop", size=22, weight=ft.FontWeight.W_600),
                            self.balance_text,
                        ],
                        spacing=3,
                    ),
                    ft.Container(expand=True),
                    ft.FilledButton(
                        "Add Vice", icon=ft.Icons.ADD, on_click=lambda _: self._open_editor()
                    ),
                ]
            ),
        )
        return ft.Column(
            [
                header,
                ft.Container(
                    self.grid,
                    padding=ft.padding.only(left=24, right=24),
                    expand=True,
                ),
            ],
            expand=True,
            spacing=0,
        )

    def refresh(self) -> None:
        service = self.app.container.vice_service
        balance = service.balance
        self.balance_text.value = f"{balance} point{'s' if balance != 1 else ''} available"
        offerings = service.list_offerings()
        self.grid.controls = [self._offering_card(item, balance) for item in offerings]
        if not offerings:
            self.grid.controls = [
                ft.Container(
                    padding=32,
                    content=ft.Text(
                        "The shop is empty. Add a Vice to create your first reward.",
                        color=MUTED_TEXT,
                    ),
                )
            ]
        self.page.update()

    def _offering_card(self, offering: ViceOffering, balance: int) -> ft.Control:
        can_claim = offering.quantity > 0 and balance >= offering.price
        stock = (
            "Out of stock"
            if offering.quantity == 0
            else f"{offering.quantity} in inventory"
        )
        return card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                offering.name,
                                size=17,
                                weight=ft.FontWeight.W_600,
                                expand=True,
                            ),
                            ft.PopupMenuButton(
                                items=[
                                    ft.PopupMenuItem(
                                        text="Edit",
                                        icon=ft.Icons.EDIT_OUTLINED,
                                        on_click=lambda _, item=offering: self._open_editor(item),
                                    ),
                                    ft.PopupMenuItem(
                                        text="Remove",
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        on_click=lambda _, item=offering: self._confirm_remove(item),
                                    ),
                                ]
                            ),
                        ]
                    ),
                    ft.Text(offering.description or "No description.", color=MUTED_TEXT),
                    ft.Container(expand=True),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        f"{offering.price} point{'s' if offering.price != 1 else ''}",
                                        size=16,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(stock, size=12, color=MUTED_TEXT),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                            ft.FilledButton(
                                "Claimed",
                                icon=ft.Icons.REDEEM_OUTLINED,
                                disabled=not can_claim,
                                tooltip=(
                                    "Out of stock"
                                    if offering.quantity == 0
                                    else "Not enough points"
                                    if balance < offering.price
                                    else "Claim this Vice"
                                ),
                                on_click=lambda _, item=offering: self._claim(item),
                            ),
                        ]
                    ),
                ],
                spacing=8,
                expand=True,
            )
        )

    def _open_editor(self, offering: ViceOffering | None = None) -> None:
        name = ft.TextField(label="Name", value=offering.name if offering else "")
        description = ft.TextField(
            label="Description",
            value=offering.description if offering else "",
            multiline=True,
            min_lines=2,
        )
        price = ft.TextField(
            label="Price in points",
            value=str(offering.price) if offering else "0",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        quantity = ft.TextField(
            label="Quantity in inventory",
            value=str(offering.quantity) if offering else "1",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Edit Vice" if offering else "Add Vice"),
            content=ft.Column(
                [name, description, ft.Row([price, quantity], spacing=12)],
                width=480,
                tight=True,
                spacing=12,
            ),
        )

        def save(_) -> None:
            try:
                parsed_price = int(price.value or "")
                parsed_quantity = int(quantity.value or "")
            except ValueError:
                self.app.error(ValueError("Price and quantity must be whole numbers."))
                return
            try:
                self.app.container.vice_service.save_offering(
                    offering.id if offering else None,
                    name.value or "",
                    description.value or "",
                    parsed_price,
                    parsed_quantity,
                )
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.page.close(dialog)
            self.refresh()

        dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda _: self.page.close(dialog)),
            ft.FilledButton("Save", on_click=save),
        ]
        self.page.open(dialog)

    def _confirm_remove(self, offering: ViceOffering) -> None:
        def remove() -> None:
            self.app.container.vice_service.remove_offering(offering.id)
            self.refresh()

        confirm_dialog(
            self.page,
            "Remove Vice?",
            f"Remove '{offering.name}' from the shop? Past claims remain in the point history.",
            remove,
            confirm_label="Remove",
        )

    def _claim(self, offering: ViceOffering) -> None:
        try:
            claim = self.app.container.vice_service.claim(offering.id)
        except TaskStampsError as error:
            self.app.error(error)
            return
        self.app.notify(
            f"Claimed {claim.offering_name_snapshot} for {claim.price_paid} points."
        )
        self.refresh()
