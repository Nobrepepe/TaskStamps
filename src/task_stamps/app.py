"""Flet application shell: navigation, shared helpers, startup checks."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Callable

import flet as ft

from task_stamps.components.theme import (
    ACCENT,
    BAD,
    BG,
    BG_2,
    LINE,
    MUTED,
    MUTED_2,
    SANS,
    SERIF,
    TEXT,
    eyebrow,
    hairline,
    style_dialog,
)
from task_stamps.container import AppContainer, build_container
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.utilities.logging_setup import get_logger
from task_stamps.views.calendar import CalendarView, open_history_board_dialog
from task_stamps.views.settings import SettingsView
from task_stamps.views.stats import StatsView
from task_stamps.views.tasks import TasksView
from task_stamps.views.today import TodayView
from task_stamps.views.vice_chests import ViceChestsView
from task_stamps.views.worlds import WorldsView

logger = get_logger("app")

RAIL_WIDTH = 178


class TaskStampsApp:
    def __init__(self, container: AppContainer, page: ft.Page) -> None:
        self.container = container
        self.page = page
        page.data = self
        self.rail_width = RAIL_WIDTH

        page.title = "Task Stamps"
        page.padding = 0
        page.bgcolor = BG
        page.theme_mode = ft.ThemeMode.DARK
        page.fonts = {
            SERIF: "fonts/InstrumentSerif-Regular.ttf",
            SANS: "fonts/Figtree-Regular.ttf",
            "Figtree Medium": "fonts/Figtree-Medium.ttf",
        }
        page.theme = ft.Theme(
            font_family=SANS,
            use_material3=True,
            focus_color=ft.Colors.with_opacity(0.42, TEXT),
        )
        page.window.min_width = 760
        page.window.min_height = 560

        self.file_picker = ft.FilePicker(on_result=self._on_file_picked)
        self._picker_callback: Callable[[str], None] | None = None
        page.overlay.append(self.file_picker)
        self._dialog_stack: list[ft.AlertDialog] = []

        self.views = [
            TodayView(self),
            TasksView(self),
            CalendarView(self),
            StatsView(self),
            WorldsView(self),
            ViceChestsView(self),
            SettingsView(self),
        ]
        self.current_index = 0
        self.content_host = ft.Container(expand=True)

        self.rail = self._build_rail()

        page.add(
            ft.Row(
                [self.rail, self.content_host],
                expand=True,
                spacing=0,
            )
        )

        page.on_resized = self._on_resized
        page.on_keyboard_event = self._on_keyboard
        try:
            page.window.on_event = self._on_window_event
        except Exception:  # older flet fallback; resize handling still works
            pass

        self._startup()

    # -- lifecycle -----------------------------------------------------------

    def _startup(self) -> None:
        try:
            drops = self.container.schedule_service.evaluate_missed_days()
        except TaskStampsError as error:
            self.error(error)
            drops = []
        self._show_view(0)
        if drops:
            names = ", ".join(event.task_name for event in drops)
            auto_paused = [event.task_name for event in drops if event.auto_paused]
            self.notify(
                f"Missed scheduled days detected — streak reset for: {names}."
                + (
                    f" Automatically paused after three misses: "
                    f"{', '.join(auto_paused)}."
                    if auto_paused
                    else ""
                )
            )

    def _on_window_event(self, event: ft.ControlEvent) -> None:
        # Re-run missed-day evaluation when the app regains focus on a new day.
        if getattr(event, "data", None) in ("focus", "restore", "show"):
            if self.container.schedule_service.date_changed_since_last_check():
                drops = self.container.schedule_service.evaluate_missed_days()
                if drops:
                    names = ", ".join(e.task_name for e in drops)
                    auto_paused = [e.task_name for e in drops if e.auto_paused]
                    self.notify(
                        f"Missed scheduled days — streak reset for: {names}."
                        + (
                            f" Automatically paused after three misses: "
                            f"{', '.join(auto_paused)}."
                            if auto_paused
                            else ""
                        )
                    )
                self.refresh_current()

    def _on_resized(self, _event: ft.ControlEvent) -> None:
        # Keep the current screen; just let it re-fit its layout.
        self.views[self.current_index].on_resize()

    def _build_rail(self) -> ft.Container:
        labels = ("Today", "Tasks", "Calendar", "Stats", "Worlds", "Vice Chests", "Settings")
        self.nav_items: list[tuple[ft.Text, ft.Container]] = []
        controls: list[ft.Control] = []
        for index, label in enumerate(labels):
            label_control = eyebrow(label, TEXT if index == 0 else MUTED_2)
            thread = ft.Container(width=2, height=13, bgcolor=ACCENT, left=-26, visible=index == 0)
            item = ft.Container(
                padding=ft.padding.symmetric(horizontal=26, vertical=9),
                ink=True,
                content=ft.Stack([label_control, thread], height=15),
                on_click=lambda _, i=index: self._show_view(i),
            )

            def hover(event, i=index) -> None:
                if i != self.current_index:
                    text_control = self.nav_items[i][0]
                    text_control.spans[0].style.color = TEXT if event.data == "true" else MUTED_2
                    text_control.update()

            item.on_hover = hover
            self.nav_items.append((label_control, thread))
            controls.append(item)
        self.chest_value = ft.Text("0", size=27, color=ACCENT, font_family=SERIF)
        return ft.Container(
            width=RAIL_WIDTH,
            bgcolor=BG,
            padding=ft.padding.only(top=34, bottom=26),
            border=ft.border.only(right=ft.BorderSide(1, LINE)),
            content=ft.Column(
                [
                    ft.Container(
                        padding=ft.padding.only(left=26, right=26, bottom=34),
                        content=ft.Text("Task\nStamps", size=23, color=TEXT, font_family=SERIF,
                                        style=ft.TextStyle(height=1.15)),
                    ),
                    *controls,
                    ft.Container(expand=True),
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=26),
                        content=ft.Column(
                            [hairline(0.7), ft.Container(height=7), eyebrow("Chests"), self.chest_value,
                             ft.Text("waiting to claim", size=12, color=MUTED)],
                            spacing=4,
                        ),
                    ),
                ],
                spacing=0,
                expand=True,
            ),
        )

    def _on_keyboard(self, event: ft.KeyboardEvent) -> None:
        if event.key == "Escape" and self._dialog_stack:
            self.close_dialog(self._dialog_stack[-1])

    def _show_view(self, index: int) -> None:
        self.current_index = index
        for item_index, (label, thread) in enumerate(self.nav_items):
            active = item_index == index
            label.spans[0].style.color = TEXT if active else MUTED_2
            thread.visible = active
        self.refresh_chest_count(update=False)
        view = self.views[index]
        if not hasattr(view, "_root_control"):
            view._root_control = view.build()  # type: ignore[attr-defined]
        self.content_host.content = view._root_control  # type: ignore[attr-defined]
        view.refresh()
        self.page.update()

    def refresh_current(self) -> None:
        self.views[self.current_index].refresh()

    def refresh_chest_count(self, *, update: bool = True) -> None:
        self.chest_value.value = str(self.container.chest_service.unclaimed_total())
        if update and self.chest_value.page is not None:
            self.chest_value.update()

    def show_fresh_start(self) -> None:
        """Discard cached view state and return to the empty Today screen."""
        self.views = [
            TodayView(self),
            TasksView(self),
            CalendarView(self),
            StatsView(self),
            WorldsView(self),
            ViceChestsView(self),
            SettingsView(self),
        ]
        self._show_view(0)

    # -- shared helpers ---------------------------------------------------------

    def img_src(self, version_id: str | None) -> str | None:
        return self.container.asset_service.relative_src(version_id)

    def play_sound_version(self, version_id: str | None, force: bool = False) -> None:
        """Play a sound version, falling back to the global default sound,
        then silence. ``force`` bypasses the mute switch (editor test button)."""
        settings = self.container.settings_service
        if not settings.sound_enabled and not force:
            return
        resolved = version_id or settings.fallback_sound_version_id
        if resolved is None:
            return
        path = self.container.asset_service.path_for_version_id(resolved)
        if path is None:
            logger.warning("Sound version %s has no readable file", resolved)
            return
        self.container.audio.play(path, settings.master_volume)

    def play_board_stamp_sound(self, stamp) -> None:
        self.play_stamp_sounds(stamp.sound_relative_path, force=True)

    def play_stamp_sounds(
        self, assigned_sound: str | None, force: bool = False
    ) -> None:
        """Play the global stamp sound, followed by the assigned sound."""
        settings = self.container.settings_service
        if not settings.sound_enabled and not force:
            return
        paths = []
        fallback_id = settings.fallback_sound_version_id
        if fallback_id:
            fallback_path = self.container.asset_service.path_for_version_id(fallback_id)
            if fallback_path:
                paths.append(fallback_path)
        if assigned_sound:
            assigned_path = self.container.config.data_dir / assigned_sound
            if assigned_path not in paths:
                paths.append(assigned_path)
        self.container.audio.play_sequence(paths, settings.master_volume)

    def play_stamp_sound_version(self, version_id: str | None) -> None:
        relative_path = self.container.asset_service.relative_path(version_id)
        self.play_stamp_sounds(relative_path)

    def play_completion_sounds(
        self, assigned_version_id: str | None, boss_relative_path: str | None = None
    ) -> None:
        settings = self.container.settings_service
        if not settings.sound_enabled:
            return
        paths = []
        for version_id in (settings.fallback_sound_version_id, assigned_version_id):
            path = self.container.asset_service.path_for_version_id(version_id)
            if path and path not in paths:
                paths.append(path)
        if boss_relative_path:
            boss_path = self.container.config.data_dir / boss_relative_path
            if boss_path not in paths:
                paths.append(boss_path)
        self.container.audio.play_sequence(paths, settings.master_volume)

    def open_dialog(self, dialog: ft.AlertDialog) -> None:
        style_dialog(dialog)
        self._dialog_stack.append(dialog)
        self.page.open(dialog)

    def close_dialog(self, dialog: ft.AlertDialog) -> None:
        if dialog in self._dialog_stack:
            self._dialog_stack.remove(dialog)
        self.page.close(dialog)

    def open_history_board(self, day: date) -> None:
        open_history_board_dialog(self, day)

    def pick_file(
        self, allowed_extensions: list[str], callback: Callable[[str], None]
    ) -> None:
        self._picker_callback = callback
        self.file_picker.pick_files(
            allow_multiple=False, allowed_extensions=allowed_extensions
        )

    def pick_directory(self, callback: Callable[[str], None]) -> None:
        self._picker_callback = callback
        self.file_picker.get_directory_path()

    def _on_file_picked(self, event: ft.FilePickerResultEvent) -> None:
        callback = self._picker_callback
        self._picker_callback = None
        if callback is None:
            return
        if event.files:
            path = event.files[0].path
            if path:
                callback(path)
        elif event.path:
            callback(event.path)

    def notify(self, message: str) -> None:
        self.page.open(
            ft.SnackBar(content=ft.Text(message, color=TEXT), bgcolor=BG_2, duration=5000)
        )

    def error(self, error: Exception) -> None:
        message = getattr(error, "user_message", None) or str(error)
        logger.warning("User-facing error: %s", message)
        self.page.open(
            ft.SnackBar(content=ft.Text(message, color=BAD), bgcolor=BG_2, duration=6000)
        )


def run() -> None:
    parser = argparse.ArgumentParser(prog="task-stamps", description="Task Stamps")
    parser.parse_args()

    container = build_container()

    def main(page: ft.Page) -> None:
        try:
            TaskStampsApp(container, page)
        except Exception:
            logger.exception("Fatal error during interface startup")
            raise

    try:
        ft.app(target=main, assets_dir=str(container.config.data_dir))
    finally:
        container.close()


if __name__ == "__main__":
    run()
