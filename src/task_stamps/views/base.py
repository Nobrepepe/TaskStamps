from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from task_stamps.app import TaskStampsApp


class View:
    """Base for the five main screens. Views call services only — no
    business rules live in Flet event handlers."""

    def __init__(self, app: "TaskStampsApp") -> None:
        self.app = app

    @property
    def page(self) -> ft.Page:
        return self.app.page

    def build(self) -> ft.Control:
        raise NotImplementedError

    def refresh(self) -> None:  # called when shown
        pass

    def on_resize(self) -> None:  # called on window resize; keeps the screen
        self.refresh()
