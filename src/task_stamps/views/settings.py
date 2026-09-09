"""Settings screen: sound, animation, calendar, board background, data tools."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from task_stamps.components.common import section_title
from task_stamps.components.theme import BAD, MUTED, SERIF, TEXT, TEXT_DIM, eyebrow, hairline
from task_stamps.domain.enums import AssetType
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.services.settings_service import BOARD_BACKGROUNDS
from task_stamps.views.base import View

_SOUND_EXTS = ["wav", "mp3", "ogg"]
_BACKUP_EXTS = ["zip"]


def _group(content: ft.Control) -> ft.Control:
    return ft.Column([content, hairline()], spacing=18)


class SettingsView(View):
    def _worldhub_card(self) -> ft.Control:
        """World Hub content: install, link, preview, activate, roll back."""
        container = self.app.container
        hub = container.worldhub
        status = hub.status()

        if status["hub_mode"]:
            receipt = status["receipt"] or {}
            summary = (
                f"Hub mode — “{receipt.get('productionName', 'unknown production')}” "
                f"revision {receipt.get('productionRevision', '?')}, "
                f"publication {str(status['publication_id'])[:8]}…, "
                f"imported {str(receipt.get('importedAt', ''))[:10]}."
            )
        else:
            summary = (
                "Legacy mode — content is authored in this app. Install a World Hub "
                "publication to make World Hub the content source."
            )
        linked = status["linked_folder"] or "No production folder linked."

        def show_preview(staged) -> None:
            preview = hub.preview(staged)
            lines: list[str] = []
            if preview.already_active:
                lines.append("This publication is already active.")
            if preview.added_worlds:
                lines.append("Worlds added: " + ", ".join(preview.added_worlds))
            if preview.updated_worlds:
                lines.append("Worlds updated: " + ", ".join(preview.updated_worlds))
            if preview.added_characters:
                lines.append("Characters added: " + ", ".join(preview.added_characters))
            if preview.updated_characters:
                lines.append("Characters updated: " + ", ".join(preview.updated_characters))
            if preview.retired_characters:
                lines.append(
                    "Characters retiring (kept for history): "
                    + ", ".join(preview.retired_characters)
                )
            if preview.affected_assignments:
                lines.append(
                    "Active tasks will be reassigned from: "
                    + ", ".join(preview.affected_assignments)
                )
            if preview.changed_assets:
                lines.append(f"{preview.changed_assets} artwork file(s) changed.")
            if not lines:
                lines.append("No visible content changes.")

            def activate(_) -> None:
                try:
                    hub.activate(staged)
                except TaskStampsError as error:
                    self.app.error(error)
                    return
                self.app.close_dialog(dialog)
                self.app.notify("The publication is now active.")
                self.refresh()

            def cancel(_) -> None:
                staged.cleanup()
                self.app.close_dialog(dialog)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Activate “{preview.production_name}”?"),
                content=ft.Column(
                    [ft.Text(line, size=13) for line in lines]
                    + [ft.Text(
                        "Tasks, streaks, completions, boards, and chests are never touched. "
                        "If anything fails, the current content stays active.",
                        size=12, color=MUTED,
                    )],
                    tight=True, spacing=6, width=460,
                ),
                actions=[
                    ft.TextButton("Activate", on_click=activate),
                    ft.TextButton("Cancel", on_click=cancel),
                ],
            )
            self.app.open_dialog(dialog)

        def install_zip(_) -> None:
            def handle(path: str) -> None:
                try:
                    staged = hub.stage_zip(Path(path))
                except Exception as error:  # PackageError carries a user message
                    self.app.error(error)
                    return
                show_preview(staged)

            self.app.pick_file(["zip"], handle)

        def link_folder(_) -> None:
            def handle(path: str) -> None:
                try:
                    hub.link_folder(Path(path))
                except Exception as error:
                    self.app.error(error)
                    return
                self.app.notify("Production folder linked.")
                self.refresh()

            self.app.pick_directory(handle)

        def check_update(_) -> None:
            try:
                staged = hub.stage_linked_folder()
            except Exception as error:
                self.app.error(error)
                return
            show_preview(staged)

        def roll_back(_) -> None:
            try:
                hub.rollback()
            except Exception as error:
                self.app.error(error)
                return
            self.app.notify("Rolled back to the previous publication.")
            self.refresh()

        actions = [
            ft.TextButton("Install publication ZIP…", on_click=install_zip),
            ft.TextButton("Link production folder…", on_click=link_folder),
        ]
        if status["linked_folder"]:
            actions.append(ft.TextButton("Check for update", on_click=check_update))
        if status["previous_publication_id"]:
            actions.append(ft.TextButton("Roll back", on_click=roll_back))

        return _group(
            ft.Column(
                [
                    section_title("World Hub content"),
                    ft.Text(summary, size=13),
                    ft.Text(f"Linked folder: {linked}", size=12, color=MUTED, selectable=True),
                    ft.Row(actions, spacing=10, wrap=True),
                ],
                spacing=10,
            )
        )

    def build(self) -> ft.Control:
        self.body = ft.Column(
            spacing=14, scroll=ft.ScrollMode.AUTO, expand=True
        )
        header = ft.Container(
            padding=ft.padding.only(left=56, right=56, top=40, bottom=20),
            content=ft.Column([eyebrow("Preferences"), ft.Text("Settings", size=48, color=TEXT, font_family=SERIF),
                               ft.Text("Tune the archive, its sound, and your local data.", size=15, color=TEXT_DIM)], spacing=10),
        )
        return ft.Column(
            [header, ft.Container(self.body, padding=ft.padding.only(left=56, right=56, bottom=72), expand=True)],
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
            color=MUTED,
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

        boss_sound_id = settings.boss_fallback_sound_version_id

        def import_boss_sound(_) -> None:
            def handle(path: str) -> None:
                try:
                    version = container.asset_service.import_file(path, AssetType.SOUND)
                except TaskStampsError as error:
                    self.app.error(error)
                    return
                settings.boss_fallback_sound_version_id = version.id
                self.refresh()

            self.app.pick_file(_SOUND_EXTS, handle)

        def clear_boss_sound(_) -> None:
            settings.boss_fallback_sound_version_id = None
            self.refresh()

        boss_sound_controls: list[ft.Control] = [
            ft.Text("Global Boss sound:", size=13),
            ft.Text("Set" if boss_sound_id else "Not set", size=12, color=MUTED),
            ft.TextButton("Import…", on_click=import_boss_sound),
        ]
        if boss_sound_id:
            boss_sound_controls.extend([
                ft.TextButton(
                    "Test",
                    on_click=lambda _: self.app.play_sound_version(
                        boss_sound_id, force=True
                    ),
                ),
                ft.TextButton("Clear", on_click=clear_boss_sound),
            ])
        boss_sound_row = ft.Column(
            [
                ft.Row(boss_sound_controls, spacing=8),
                ft.Text(
                    "Plays when a Boss with no defeat sound of its own is beaten.",
                    size=12,
                    color=MUTED,
                ),
            ],
            spacing=2,
        )

        animation_switch = ft.Switch(
            label="Reduced animation",
            value=settings.reduced_animation,
            on_change=lambda e: self._set(
                lambda: setattr(settings, "reduced_animation", e.control.value)
            ),
        )
        boss_switch = ft.Switch(
            label="Show the daily Boss banner",
            value=settings.boss_banner_enabled,
            on_change=lambda e: self._set(
                lambda: setattr(settings, "boss_banner_enabled", e.control.value)
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
                self.app.close_dialog(dialog)

            def reset(_=None) -> None:
                try:
                    container.backup_service.factory_reset()
                except TaskStampsError as error:
                    self.app.close_dialog(dialog)
                    self.app.error(error)
                    return
                self.app.close_dialog(dialog)
                self.app.show_fresh_start()
                self.app.notify("All data was reset. Welcome to a new game.")

            dialog.actions = [
                ft.TextButton("Cancel", on_click=cancel),
                ft.TextButton("Reset all data", on_click=reset, style=ft.ButtonStyle(color=BAD)),
            ]
            self.app.open_dialog(dialog)

        def cleanup_assets(_) -> None:
            try:
                removed = container.asset_service.cleanup_unreferenced_versions()
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.notify(f"Removed {removed} unreferenced asset file(s).")

        self.body.controls = [
            self._worldhub_card(),
            _group(
                ft.Column(
                    [
                        section_title("Sound"),
                        sound_switch,
                        ft.Row([ft.Text("Master volume", size=13), volume_slider]),
                        fallback_row,
                        boss_sound_row,
                    ],
                    spacing=8,
                )
            ),
            _group(
                ft.Column(
                    [
                        section_title("Interface"),
                        animation_switch,
                        boss_switch,
                        ft.Row([week_dropdown, background_dropdown], spacing=14),
                    ],
                    spacing=8,
                )
            ),
            _group(
                ft.Column(
                    [
                        section_title("Data"),
                        ft.Text(
                            f"Data directory: {container.config.data_dir}",
                            size=12,
                            color=MUTED,
                            selectable=True,
                        ),
                        ft.Row(
                            [
                                ft.TextButton("Create backup", on_click=create_backup),
                                ft.TextButton("Restore backup…", on_click=restore_backup),
                                ft.TextButton("Export JSON", on_click=export_json),
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
