"""Details card shown when an existing stamp on a board is clicked."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import flet as ft

from task_stamps.components.theme import MUTED, SERIF, TEXT
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.domain.models import BoardStamp

if TYPE_CHECKING:
    from task_stamps.app import TaskStampsApp


def show_stamp_details(
    app: "TaskStampsApp",
    stamp: BoardStamp,
    on_undone: Callable[[], None] | None = None,
) -> None:
    page = app.page
    is_today = stamp.completion_date == app.container.clock.today()
    has_sound = bool(
        stamp.sound_relative_path
        or app.container.settings_service.fallback_sound_version_id
    )

    rows: list[ft.Control] = [
        ft.Image(
            src="/" + stamp.image_relative_path,
            width=240,
            height=180,
            fit=ft.ImageFit.CONTAIN,
        ),
        ft.Text(stamp.character_name_snapshot, size=22, color=TEXT, font_family=SERIF),
        ft.Text(f"Task: {stamp.task_name_snapshot}", color=MUTED),
        ft.Text(f"Stamp {stamp.streak_number} of 15", color=MUTED),
        ft.Text(
            "Completed "
            + stamp.completed_at.strftime("%A, %d %B %Y at %H:%M"),
            color=MUTED,
            size=12,
        ),
    ]

    dialog = ft.AlertDialog(
        title=ft.Text("Stamp details"),
        content=ft.Column(rows, tight=True, spacing=8,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
    )

    def close(_=None) -> None:
        app.close_dialog(dialog)

    def play(_=None) -> None:
        app.play_board_stamp_sound(stamp)

    def undo(_=None) -> None:
        try:
            app.container.completion_service.undo_completion(stamp.completion_id)
        except TaskStampsError as error:
            app.error(error)
            return
        app.close_dialog(dialog)
        app.notify("Completion undone — the task is available again today.")
        if on_undone:
            on_undone()

    actions: list[ft.Control] = []
    if has_sound:
        actions.append(
            ft.TextButton("Play sound", icon=ft.Icons.VOLUME_UP_OUTLINED, on_click=play)
        )
    if is_today:
        actions.append(
            ft.TextButton("Undo", icon=ft.Icons.UNDO_OUTLINED, on_click=undo)
        )
    actions.append(ft.TextButton("Close", on_click=close))
    dialog.actions = actions
    app.open_dialog(dialog)
