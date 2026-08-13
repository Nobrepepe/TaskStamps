"""Settings screen: sound, animation, calendar, board background, data tools."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from task_stamps.components.common import MUTED_TEXT, card, section_title
from task_stamps.domain.enums import AssetType
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.services.settings_service import BOARD_BACKGROUNDS
from task_stamps.views.base import View

_SOUND_EXTS = ["wav", "mp3", "ogg"]
_BACKUP_EXTS = ["zip"]


class SettingsView(View):
    def build(self) -> ft.Control:
        self.body = ft.Column(
            spacing=14, scroll=ft.ScrollMode.AUTO, expand=True
        )
        header = ft.Container(
            padding=ft.padding.only(left=24, right=24, top=18, bottom=8),
            content=ft.Text("Settings", size=20, weight=ft.FontWeight.W_600),
        )
        return ft.Column(
            [header, ft.Container(self.body, padding=ft.padding.symmetric(horizontal=24), expand=True)],
            expand=True,
            spacing=0,
        )

    def refresh(self) -> None:
        settings = self.app.container.settings_service
        container = self.app.container

        sound_switch = ft.Switch(
            label="Sound enabled",
            value=settings.sound_enabled,
            on_change=lambda e: self._set(lambda: setattr(settings, "sound_enabled", e.control.value)),
        )
        volume_slider = ft.Slider(
            min=0,
            max=100,
            value=settings.master_volume * 100,
            label="{value}%",
            width=280,
            on_change_end=lambda e: self._set(
                lambda: setattr(settings, "master_volume", e.control.value / 100)
            ),
        )
        fallback_label = ft.Text(
            "Set" if settings.fallback_sound_version_id else "Not set",
            size=12,
            color=MUTED_TEXT,
        )

        def import_fallback(_) -> None:
            def handle(path: str) -> None:
                try:
                    version = container.asset_service.import_file(path, AssetType.SOUND)
                except TaskStampsError as error:
                    self.app.error(error)
                    return
                settings.fallback_sound_version_id = version.id
                self.refresh()

            self.app.pick_file(_SOUND_EXTS, handle)

        def test_fallback(_) -> None:
            self.app.play_sound_version(None, force=True)

        def clear_fallback(_) -> None:
            settings.fallback_sound_version_id = None
            self.refresh()

        fallback_row = ft.Row(
            [
                ft.Text("Global stamp sound:", size=13),
                fallback_label,
                ft.TextButton("Import…", on_click=import_fallback),
                ft.TextButton("Test", on_click=test_fallback),
                ft.TextButton("Clear", on_click=clear_fallback),
            ],
            spacing=8,
        )

        animation_switch = ft.Switch(
            label="Reduced animation",
            value=settings.reduced_animation,
            on_change=lambda e: self._set(
                lambda: setattr(settings, "reduced_animation", e.control.value)
            ),
        )
        week_dropdown = ft.Dropdown(
            label="Calendar week starts on",
            value=settings.week_start,
            width=220,
            options=[
                ft.dropdown.Option("monday", "Monday"),
                ft.dropdown.Option("sunday", "Sunday"),
            ],
            on_change=lambda e: self._set(lambda: setattr(settings, "week_start", e.control.value)),
        )
        background_dropdown = ft.Dropdown(
            label="Daily board background",
            value=settings.board_background,
            width=220,
            options=[ft.dropdown.Option(name) for name in BOARD_BACKGROUNDS],
            on_change=lambda e: self._set(
                lambda: setattr(settings, "board_background", e.control.value)
            ),
        )

        def create_backup(_) -> None:
            try:
                path = container.backup_service.create_backup()
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.notify(f"Backup created: {path.name}")

        def restore_backup(_) -> None:
            def handle(path: str) -> None:
                try:
                    container.backup_service.restore_backup(Path(path))
                except TaskStampsError as error:
                    self.app.error(error)
                    return
                self.app.notify(
                    "Backup restored (a safety backup of the previous data was kept)."
                )
                self.app.refresh_current()

            self.app.pick_file(_BACKUP_EXTS, handle)

        def export_json(_) -> None:
            try:
                path = container.backup_service.export_json()
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.notify(f"Data exported: {path.name}")

        def confirm_factory_reset(_) -> None:
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Reset all data?"),
                content=ft.Text(
                    "This permanently deletes every world, character, task, "
                    "completion, setting, and imported asset. Backups and logs "
                    "will be kept. This cannot be undone."
                ),
            )

            def cancel(_=None) -> None:
                self.page.close(dialog)

            def reset(_=None) -> None:
                try:
                    container.backup_service.factory_reset()
                except TaskStampsError as error:
                    self.page.close(dialog)
                    self.app.error(error)
                    return
                self.page.close(dialog)
                self.app.show_fresh_start()
                self.app.notify("All data was reset. Welcome to a new game.")

            dialog.actions = [
                ft.TextButton("Cancel", on_click=cancel),
                ft.FilledButton("Reset all data", on_click=reset),
            ]
            self.page.open(dialog)

        def cleanup_assets(_) -> None:
            try:
                removed = container.asset_service.cleanup_unreferenced_versions()
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.notify(f"Removed {removed} unreferenced asset file(s).")

        self.body.controls = [
            card(
                ft.Column(
                    [
                        section_title("Sound"),
                        sound_switch,
                        ft.Row([ft.Text("Master volume", size=13), volume_slider]),
                        fallback_row,
                    ],
                    spacing=8,
                )
            ),
            card(
                ft.Column(
                    [
                        section_title("Interface"),
                        animation_switch,
                        ft.Row([week_dropdown, background_dropdown], spacing=14),
                    ],
                    spacing=8,
                )
            ),
            card(
                ft.Column(
                    [
                        section_title("Data"),
                        ft.Text(
                            f"Data directory: {container.config.data_dir}",
                            size=12,
                            color=MUTED_TEXT,
                            selectable=True,
                        ),
                        ft.Row(
                            [
                                ft.FilledTonalButton("Create backup", on_click=create_backup),
                                ft.FilledTonalButton("Restore backup…", on_click=restore_backup),
                                ft.FilledTonalButton("Export JSON", on_click=export_json),
                            ],
                            spacing=10,
                            wrap=True,
                        ),
                        ft.Row(
                            [
                                ft.TextButton(
                                    "Clean up unused asset files", on_click=cleanup_assets
                                ),
                                ft.TextButton(
                                    "Reset all data…",
                                    icon=ft.Icons.DELETE_FOREVER_OUTLINED,
                                    on_click=confirm_factory_reset,
                                ),
                            ],
                            spacing=10,
                            wrap=True,
                        ),
                    ],
                    spacing=10,
                )
            ),
        ]
        self.page.update()

    def _set(self, setter) -> None:
        try:
            setter()
        except (TaskStampsError, ValueError) as error:
            self.app.error(error)
