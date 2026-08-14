"""Flet application shell: navigation, shared helpers, startup checks."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Callable

import flet as ft

from task_stamps.container import AppContainer, build_container
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.utilities.logging_setup import get_logger
from task_stamps.views.calendar import CalendarView, open_history_board_dialog
from task_stamps.views.settings import SettingsView
from task_stamps.views.stats import StatsView
from task_stamps.views.tasks import TasksView
from task_stamps.views.today import TodayView
from task_stamps.views.vice_shop import ViceShopView
from task_stamps.views.worlds import WorldsView

logger = get_logger("app")

RAIL_WIDTH = 92


class TaskStampsApp:
    def __init__(self, container: AppContainer, page: ft.Page) -> None:
        self.container = container
        self.page = page
        self.rail_width = RAIL_WIDTH

        page.title = "Task Stamps"
        page.padding = 0
        page.bgcolor = "#FAF9F6"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.theme = ft.Theme(color_scheme_seed="#7C8B74", use_material3=True)
        page.window.min_width = 760
        page.window.min_height = 560

        self.file_picker = ft.FilePicker(on_result=self._on_file_picked)
        self._picker_callback: Callable[[str], None] | None = None
        page.overlay.append(self.file_picker)

        self.views = [
            TodayView(self),
            TasksView(self),
            CalendarView(self),
            StatsView(self),
            WorldsView(self),
            ViceShopView(self),
            SettingsView(self),
        ]
        self.current_index = 0
        self.content_host = ft.Container(expand=True)

        self.rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=RAIL_WIDTH,
            bgcolor="#F1EFEA",
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.TODAY_OUTLINED, selected_icon=ft.Icons.TODAY, label="Today"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.CHECK_CIRCLE_OUTLINED,
                    selected_icon=ft.Icons.CHECK_CIRCLE,
                    label="Tasks",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                    selected_icon=ft.Icons.CALENDAR_MONTH,
                    label="Calendar",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.INSIGHTS_OUTLINED,
                    selected_icon=ft.Icons.INSIGHTS,
                    label="Stats",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.PUBLIC_OUTLINED, selected_icon=ft.Icons.PUBLIC, label="Worlds"
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.STORE_OUTLINED,
                    selected_icon=ft.Icons.STORE,
                    label="Vice Shop",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS,
                    label="Settings",
                ),
            ],
            on_change=self._on_nav_change,
        )

        page.add(
            ft.Row(
                [self.rail, ft.VerticalDivider(width=1, color="#E2E0DB"), self.content_host],
                expand=True,
                spacing=0,
            )
        )

        page.on_resized = self._on_resized
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

    def _on_nav_change(self, event: ft.ControlEvent) -> None:
        self._show_view(int(event.control.selected_index))

    def _show_view(self, index: int) -> None:
        self.current_index = index
        view = self.views[index]
        if not hasattr(view, "_root_control"):
            view._root_control = view.build()  # type: ignore[attr-defined]
        self.content_host.content = view._root_control  # type: ignore[attr-defined]
        view.refresh()
        self.page.update()

    def refresh_current(self) -> None:
        self.views[self.current_index].refresh()

    def show_fresh_start(self) -> None:
        """Discard cached view state and return to the empty Today screen."""
        self.views = [
            TodayView(self),
            TasksView(self),
            CalendarView(self),
            StatsView(self),
            WorldsView(self),
            ViceShopView(self),
            SettingsView(self),
        ]
        self.rail.selected_index = 0
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
        self.page.open(ft.SnackBar(content=ft.Text(message), duration=5000))

    def error(self, error: Exception) -> None:
        message = getattr(error, "user_message", None) or str(error)
        logger.warning("User-facing error: %s", message)
        self.page.open(
            ft.SnackBar(content=ft.Text(message), bgcolor="#8C5B55", duration=6000)
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
