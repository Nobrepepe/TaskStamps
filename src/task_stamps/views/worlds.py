"""Worlds browser, character gallery, character profile and editor."""

from __future__ import annotations

import flet as ft

from task_stamps.components.common import (
    MUTED_TEXT,
    STATUS_COLORS,
    card,
    confirm_dialog,
    framed_image,
    portrait_image,
    progress_dots,
    section_title,
    stamp_image,
    status_chip,
)
from task_stamps.domain.enums import (
    STAMPS_PER_CHARACTER,
    CharacterStatus,
)
from task_stamps.domain.exceptions import TaskStampsError, WorldArchiveError, CharacterEditError
from task_stamps.domain.models import Character, World
from task_stamps.views.base import View

_IMAGE_EXTS = ["png", "jpg", "jpeg", "webp"]
_SOUND_EXTS = ["wav", "mp3", "ogg"]


class WorldsView(View):
    def build(self) -> ft.Control:
        self.selected_world_id: str | None = None
        self.header_host = ft.Container(
            padding=ft.padding.only(left=24, right=24, top=18, bottom=8)
        )
        self.body_host = ft.Container(
            expand=True, padding=ft.padding.only(left=24, right=24, bottom=20)
        )
        return ft.Column([self.header_host, self.body_host], expand=True, spacing=0)

    def refresh(self) -> None:
        if self.selected_world_id is None:
            self._render_worlds()
        else:
            self._render_gallery(self.selected_world_id)
        self.page.update()

    # ==== worlds browser ====================================================

    def _render_worlds(self) -> None:
        container = self.app.container
        hub_mode = container.worldhub.hub_mode()
        header_action: ft.Control
        if hub_mode:
            header_action = ft.Text(
                "Content is managed by World Hub — the library is read-only. "
                "Updates arrive through Settings → World Hub content.",
                size=12, color=MUTED_TEXT,
            )
        else:
            header_action = ft.FilledButton(
                "New world", icon=ft.Icons.ADD,
                on_click=lambda _: self._open_world_editor(None),
            )
        self.header_host.content = ft.Row(
            [
                ft.Text("Worlds", size=20, weight=ft.FontWeight.W_600),
                ft.Container(expand=True),
                header_action,
            ]
        )
        worlds = container.worlds.list()
        cards = [self._world_card(world) for world in worlds]
        if not cards:
            cards.append(
                ft.Container(
                    padding=32,
                    content=ft.Text(
                        "No worlds yet. Create one, then add characters with "
                        "a portrait and 15 stamps.",
                        color=MUTED_TEXT,
                    ),
                )
            )
        gallery = ft.Row(
            [ft.Container(c, width=300) for c in cards],
            wrap=True,
            spacing=14,
            run_spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.body_host.content = ft.Column(
            [gallery],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def _world_card(self, world: World) -> ft.Control:
        container = self.app.container
        stats = container.characters.world_stats(world.id)
        cover_src = self.app.img_src(world.cover_asset_version_id)
        counts = (
            f"{stats['total']} characters · {stats['available']} available · "
            f"{stats['assigned']} assigned · {stats['draft']} draft"
        )
        body = ft.Column(
            [
                framed_image(cover_src, 268, 4 / 3, icon=ft.Icons.PUBLIC_OUTLINED),
                ft.Text(world.name, size=15, weight=ft.FontWeight.W_600),
                ft.Text(world.description, size=12, color=MUTED_TEXT, max_lines=2),
                ft.Text(counts, size=11, color=MUTED_TEXT),
                ft.Row(
                    [
                        ft.TextButton(
                            "Open", on_click=lambda _, w=world: self._open_gallery(w.id)
                        ),
                    ] + ([] if container.worldhub.hub_mode() else [
                        ft.TextButton(
                            "Edit", on_click=lambda _, w=world: self._open_world_editor(w)
                        ),
                        ft.TextButton(
                            "Archive",
                            on_click=lambda _, w=world: self._archive_world(w),
                            style=ft.ButtonStyle(color="#A65D57"),
                        ),
                    ]),
                    spacing=0,
                ),
            ],
            spacing=6,
        )
        return card(body)

    def _open_world_editor(self, world: World | None) -> None:
        container = self.app.container
        name_field = ft.TextField(label="Name", value=world.name if world else "", width=360)
        description_field = ft.TextField(
            label="Description (optional)",
            value=world.description if world else "",
            width=360,
            multiline=True,
            min_lines=2,
        )
        cover_holder = ft.Container(
            content=framed_image(
                self.app.img_src(world.cover_asset_version_id) if world else None,
                200,
                4 / 3,
                icon=ft.Icons.PUBLIC_OUTLINED,
            )
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Edit world" if world else "New world"),
            content=ft.Column(
                [name_field, description_field, cover_holder], tight=True, spacing=12
            ),
        )

        def import_cover(_) -> None:
            if world is None:
                self.app.notify("Save the world first, then add a cover image.")
                return

            def handle(path: str) -> None:
                try:
                    updated = container.library_service.import_world_cover(world.id, path)
                except TaskStampsError as error:
                    self.app.error(error)
                    return
                cover_holder.content = framed_image(
                    self.app.img_src(updated.cover_asset_version_id), 200, 4 / 3
                )
                self.page.update()

            self.app.pick_file(_IMAGE_EXTS, handle)

        def save(_) -> None:
            try:
                if world is None:
                    container.library_service.create_world(
                        name_field.value or "", description_field.value or ""
                    )
                else:
                    container.library_service.update_world(
                        world.id, name_field.value or "", description_field.value or ""
                    )
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.page.close(dialog)
            self.refresh()

        dialog.actions = [
            ft.TextButton("Import cover…", on_click=import_cover),
            ft.TextButton("Cancel", on_click=lambda _: self.page.close(dialog)),
            ft.FilledButton("Save", on_click=save),
        ]
        self.page.open(dialog)

    def _archive_world(self, world: World) -> None:
        container = self.app.container

        def do_archive(confirmed: bool) -> None:
            try:
                container.library_service.archive_world(world.id, confirmed=confirmed)
            except WorldArchiveError as error:
                confirm_dialog(
                    self.page,
                    "Archive world?",
                    error.user_message,
                    lambda: do_archive(True),
                    confirm_label="Archive anyway",
                )
                return
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.notify(f"World '{world.name}' archived. History is preserved.")
            self.refresh()

        confirm_dialog(
            self.page,
            "Archive world?",
            f"Archive '{world.name}'? Its characters leave the assignment pools; "
            "all history stays intact.",
            lambda: do_archive(False),
            confirm_label="Archive",
        )

    # ==== character gallery ==================================================

    def _open_gallery(self, world_id: str) -> None:
        self.selected_world_id = world_id
        self.refresh()

    def _render_gallery(self, world_id: str) -> None:
        container = self.app.container
        world = container.worlds.get(world_id)
        self.header_host.content = ft.Row(
            [
                ft.IconButton(
                    ft.Icons.ARROW_BACK,
                    on_click=lambda _: self._close_gallery(),
                    tooltip="Back to worlds",
                ),
                ft.Text(world.name, size=20, weight=ft.FontWeight.W_600),
                ft.Container(expand=True),
                ft.Text(
                    "Managed by World Hub — read-only.", size=12, color=MUTED_TEXT,
                ) if container.worldhub.hub_mode() else ft.FilledButton(
                    "New character",
                    icon=ft.Icons.ADD,
                    on_click=lambda _: self._create_character(world_id),
                ),
            ]
        )
        characters = container.characters.list(world_id=world_id)
        cards = [self._character_card(character) for character in characters]
        if not cards:
            cards.append(
                ft.Container(
                    padding=32,
                    content=ft.Text("No characters in this world yet.", color=MUTED_TEXT),
                )
            )
        gallery = ft.Row(
            [ft.Container(c, width=220) for c in cards],
            wrap=True,
            spacing=14,
            run_spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.body_host.content = ft.Column(
            [gallery],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def _close_gallery(self) -> None:
        self.selected_world_id = None
        self.refresh()

    def _character_card(self, character: Character) -> ft.Control:
        container = self.app.container
        assignment = container.assignments.active_for_character(character.id)
        subtitle = ""
        if assignment is not None:
            task = container.tasks.get(assignment.task_id)
            subtitle = f"On '{task.name}' · streak {assignment.current_streak}/15"
        body = ft.Column(
            [
                portrait_image(self.app.img_src(character.portrait_asset_version_id), width=188),
                ft.Row(
                    [
                        ft.Text(character.name, size=14, weight=ft.FontWeight.W_600),
                        status_chip(
                            character.status.value, STATUS_COLORS[character.status.value]
                        ),
                    ],
                    spacing=8,
                ),
                ft.Text(subtitle, size=11, color=MUTED_TEXT),
            ],
            spacing=6,
        )
        return card(body, on_click=lambda _, c=character: self._open_profile(c.id))

    def _create_character(self, world_id: str) -> None:
        name_field = ft.TextField(label="Name", width=320, autofocus=True)
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("New character"),
            content=name_field,
        )

        def create(_) -> None:
            try:
                character = self.app.container.library_service.create_character(
                    world_id, name_field.value or ""
                )
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.page.close(dialog)
            self.refresh()
            self._open_editor(character.id)

        dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda _: self.page.close(dialog)),
            ft.FilledButton("Create", on_click=create),
        ]
        self.page.open(dialog)

    # ==== character profile ====================================================

    def _open_profile(self, character_id: str) -> None:
        container = self.app.container
        character = container.characters.get(character_id)
        world = container.worlds.get(character.world_id)
        progress = container.streak_service.character_progress(character_id)
        stamps = container.characters.stamps_for(character_id)

        assignment_line = "Not assigned."
        if progress.assignment is not None:
            task = container.tasks.get(progress.assignment.task_id)
            if progress.assignment.is_active:
                assignment_line = (
                    f"Assigned to '{task.name}' — streak "
                    f"{progress.current_streak}/{STAMPS_PER_CHARACTER}"
                )
            else:
                reason = (
                    progress.assignment.end_reason.value
                    if progress.assignment.end_reason
                    else "ended"
                )
                assignment_line = (
                    f"Last run on '{task.name}': {reason} at streak "
                    f"{progress.current_streak}"
                )

        next_preview: ft.Control = ft.Text("—", color=MUTED_TEXT)
        if progress.next_stamp_number and progress.assignment and progress.assignment.is_active:
            next_stamp = stamps[progress.next_stamp_number - 1]
            next_preview = stamp_image(
                self.app.img_src(next_stamp.image_asset_version_id), width=110
            )

        grid_items: list[ft.Control] = []
        for stamp in stamps:
            state_opacity = 1.0
            border_color = "#E2E0DB"
            if progress.assignment is not None and progress.assignment.is_active:
                if stamp.sequence_number in progress.used_stamp_numbers:
                    border_color = "#7C8B74"
                elif stamp.sequence_number == progress.next_stamp_number:
                    border_color = "#C2A36B"
                else:
                    state_opacity = 0.45
            item = ft.Container(
                content=ft.Column(
                    [
                        stamp_image(
                            self.app.img_src(stamp.image_asset_version_id), width=82
                        ),
                        ft.Text(str(stamp.sequence_number), size=11, color=MUTED_TEXT),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                opacity=state_opacity,
                border=ft.border.all(2, border_color),
                border_radius=8,
                padding=3,
                ink=True,
                on_click=lambda _, sequence=stamp.sequence_number: (
                    self._open_profile_stamp_dialog(
                        character_id,
                        sequence,
                        lambda: (
                            self.page.close(dialog),
                            self._open_profile(character_id),
                        ),
                    )
                ),
                tooltip=f"Open stamp #{stamp.sequence_number}",
            )
            grid_items.append(item)

        history_rows: list[ft.Control] = []
        for assignment in container.assignments.history_for_character(character_id, limit=6):
            task = container.tasks.get(assignment.task_id)
            outcome = "active" if assignment.is_active else (
                assignment.end_reason.value if assignment.end_reason else "ended"
            )
            history_rows.append(
                ft.Text(
                    f"'{task.name}': {outcome}, streak {assignment.current_streak}",
                    size=13,
                    color=MUTED_TEXT,
                )
            )
        if not history_rows:
            history_rows.append(ft.Text("Never assigned yet.", size=13, color=MUTED_TEXT))

        portrait_panel = ft.Container(
            content=portrait_image(
                self.app.img_src(character.portrait_asset_version_id), width=None
            ),
            width=390,
            height=620,
        )
        details = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            character.name,
                            size=22,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                        ),
                        status_chip(
                            character.status.value,
                            STATUS_COLORS[character.status.value],
                        ),
                    ],
                    spacing=10,
                ),
                ft.Text(world.name, size=14, color=MUTED_TEXT),
                ft.Text(character.description, size=14, color=MUTED_TEXT),
                ft.Text(assignment_line, size=14),
                ft.Row(
                    [
                        ft.Column(
                            [section_title("Next stamp"), next_preview],
                            spacing=6,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Column(
                            [
                                section_title("Collection progress"),
                                progress_dots(
                                    progress.used_stamp_numbers,
                                    progress.next_stamp_number,
                                    size=16,
                                ),
                            ],
                            spacing=6,
                            expand=True,
                        ),
                    ],
                    spacing=20,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                section_title("Stamp collection"),
                ft.Row(grid_items, wrap=True, spacing=6, run_spacing=6),
                section_title("Assignment history"),
                *history_rows,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            width=570,
            height=620,
        )
        content = ft.Row(
            [portrait_panel, details],
            spacing=22,
            height=620,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        dialog = ft.AlertDialog(title=ft.Text("Character"), content=content)

        def archive(_) -> None:
            def do_archive(confirmed: bool) -> None:
                try:
                    container.library_service.archive_character(
                        character_id, confirmed=confirmed
                    )
                except CharacterEditError as error:
                    confirm_dialog(
                        self.page,
                        "Archive character?",
                        error.user_message,
                        lambda: do_archive(True),
                        confirm_label="Archive anyway",
                    )
                    return
                except TaskStampsError as error:
                    self.app.error(error)
                    return
                self.page.close(dialog)
                self.app.notify(f"'{character.name}' archived.")
                self.refresh()

            do_archive(False)

        if container.worldhub.hub_mode():
            dialog.actions = [
                ft.TextButton("Close", on_click=lambda _: self.page.close(dialog)),
            ]
        else:
            dialog.actions = [
                ft.TextButton("Archive", on_click=archive, style=ft.ButtonStyle(color="#A65D57")),
                ft.TextButton(
                    "Edit",
                    on_click=lambda _: (self.page.close(dialog), self._open_editor(character_id)),
                ),
                ft.TextButton("Close", on_click=lambda _: self.page.close(dialog)),
            ]
        self.page.open(dialog)

    def _open_profile_stamp_dialog(
        self, character_id: str, sequence: int, on_close
    ) -> None:
        """Large stamp preview and asset controls opened from the profile."""
        container = self.app.container
        library = container.library_service
        content_host = ft.Container(width=520, height=470)
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Stamp #{sequence}", size=20, weight=ft.FontWeight.W_600),
            content=content_host,
        )

        def rebuild() -> None:
            stamp = container.characters.stamp_by_sequence(character_id, sequence)
            if stamp is None:
                self.page.close(dialog)
                return

            def import_image(_) -> None:
                self.app.pick_file(
                    _IMAGE_EXTS,
                    lambda path: self._safe(
                        lambda: library.import_stamp_image(
                            character_id, sequence, path
                        ),
                        rebuild,
                    ),
                )

            def import_sound(_) -> None:
                self.app.pick_file(
                    _SOUND_EXTS,
                    lambda path: self._safe(
                        lambda: library.import_stamp_sound(
                            character_id, sequence, path
                        ),
                        rebuild,
                    ),
                )

            def play_sound(_) -> None:
                self.app.play_sound_version(
                    stamp.sound_asset_version_id, force=True
                )

            def remove_sound(_) -> None:
                self._safe(
                    lambda: library.remove_stamp_sound(character_id, sequence),
                    rebuild,
                )

            controls: list[ft.Control] = [
                ft.FilledTonalButton(
                    "Upload image…",
                    icon=ft.Icons.UPLOAD_OUTLINED,
                    on_click=import_image,
                ),
                ft.FilledTonalButton(
                    "Upload sound…",
                    icon=ft.Icons.MUSIC_NOTE_OUTLINED,
                    on_click=import_sound,
                ),
            ]
            if stamp.sound_asset_version_id:
                controls.extend(
                    [
                        ft.TextButton(
                            "Play sound",
                            icon=ft.Icons.PLAY_ARROW_OUTLINED,
                            on_click=play_sound,
                        ),
                        ft.TextButton(
                            "Remove sound",
                            icon=ft.Icons.DELETE_OUTLINE,
                            on_click=remove_sound,
                        ),
                    ]
                )

            content_host.content = ft.Column(
                [
                    stamp_image(
                        self.app.img_src(stamp.image_asset_version_id), width=500
                    ),
                    ft.Text(
                        "Unique sound assigned"
                        if stamp.sound_asset_version_id
                        else "No unique sound assigned",
                        size=13,
                        color=MUTED_TEXT,
                    ),
                    ft.Row(controls, spacing=8, wrap=True),
                ],
                spacing=14,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
            self.page.update()

        def close(_) -> None:
            self.page.close(dialog)
            on_close()

        dialog.actions = [ft.TextButton("Close", on_click=close)]
        rebuild()
        self.page.open(dialog)

    # ==== character editor =======================================================

    def _open_editor(self, character_id: str) -> None:
        container = self.app.container
        content_host = ft.Container(width=760, height=680)
        dialog = ft.AlertDialog(title=ft.Text("Edit character"), content=content_host)

        def rebuild() -> None:
            content_host.content = self._build_editor_content(character_id, rebuild)
            self.page.update()

        def close(_) -> None:
            self.page.close(dialog)
            self.refresh()

        dialog.actions = [ft.TextButton("Done", on_click=close)]
        content_host.content = self._build_editor_content(character_id, rebuild)
        self.page.open(dialog)

    def _build_editor_content(self, character_id: str, rebuild) -> ft.Control:
        container = self.app.container
        library = container.library_service
        character = container.characters.get(character_id)
        worlds = container.worlds.list()
        stamps = container.characters.stamps_for(character_id)
        missing = STAMPS_PER_CHARACTER - container.characters.stamp_image_count(character_id)

        name_field = ft.TextField(label="Name", value=character.name, width=250)
        description_field = ft.TextField(
            label="Description", value=character.description, width=250,
            multiline=True, min_lines=2,
        )
        world_dropdown = ft.Dropdown(
            label="World",
            value=character.world_id,
            width=250,
            options=[ft.dropdown.Option(world.id, world.name) for world in worlds],
        )

        def save_fields(_) -> None:
            try:
                library.update_character(
                    character_id,
                    name=name_field.value or "",
                    description=description_field.value or "",
                    world_id=world_dropdown.value,
                )
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.notify("Character saved.")
            rebuild()

        def import_portrait(_) -> None:
            self.app.pick_file(
                _IMAGE_EXTS, lambda path: self._safe(lambda: library.import_portrait(character_id, path), rebuild)
            )

        def import_default_sound(_) -> None:
            self.app.pick_file(
                _SOUND_EXTS,
                lambda path: self._safe(lambda: library.import_default_sound(character_id, path), rebuild),
            )

        def remove_default_sound(_) -> None:
            self._safe(lambda: library.remove_default_sound(character_id), rebuild)

        def test_default_sound(_) -> None:
            self.app.play_sound_version(character.default_sound_asset_version_id, force=True)

        sound_controls: list[ft.Control] = [
            ft.TextButton("Import sound…", on_click=import_default_sound)
        ]
        if character.default_sound_asset_version_id:
            sound_controls += [
                ft.IconButton(ft.Icons.PLAY_ARROW_OUTLINED, on_click=test_default_sound, tooltip="Test"),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=remove_default_sound, tooltip="Remove"),
            ]

        header = ft.Row(
            [
                ft.Column(
                    [
                        portrait_image(
                            self.app.img_src(character.portrait_asset_version_id), width=130
                        ),
                        ft.TextButton("Import portrait…", on_click=import_portrait),
                    ],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Column(
                    [
                        name_field,
                        world_dropdown,
                        description_field,
                        ft.Row(
                            [section_title("Default sound"), *sound_controls],
                            spacing=4,
                        ),
                        ft.FilledButton("Save details", on_click=save_fields),
                    ],
                    spacing=8,
                ),
            ],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        readiness = (
            ft.Text("Ready — all 15 stamps present.", size=12, color="#7C8B74")
            if character.status == CharacterStatus.READY
            else ft.Text(
                f"Draft — {missing} stamp image{'s' if missing != 1 else ''} still missing. "
                "Draft characters cannot be assigned.",
                size=12,
                color="#A65D57",
            )
        )

        slots = [self._stamp_slot(character_id, stamp, rebuild) for stamp in stamps]
        stamp_grid = ft.GridView(
            controls=slots,
            expand=True,
            max_extent=180,
            child_aspect_ratio=0.9,
            spacing=10,
            run_spacing=10,
            padding=ft.padding.only(right=4, bottom=8),
        )

        return ft.Column(
            [
                header,
                readiness,
                section_title("Stamps (15 required, landscape 4:3)"),
                stamp_grid,
            ],
            spacing=10,
            expand=True,
        )

    def _stamp_slot(self, character_id: str, stamp, rebuild) -> ft.Control:
        container = self.app.container
        library = container.library_service
        sequence = stamp.sequence_number
        has_image = stamp.image_asset_version_id is not None

        def import_image(_) -> None:
            self.app.pick_file(
                _IMAGE_EXTS,
                lambda path: self._safe(
                    lambda: library.import_stamp_image(character_id, sequence, path), rebuild
                ),
            )

        def import_sound(_) -> None:
            self.app.pick_file(
                _SOUND_EXTS,
                lambda path: self._safe(
                    lambda: library.import_stamp_sound(character_id, sequence, path), rebuild
                ),
            )

        def play_sound(_) -> None:
            self.app.play_sound_version(stamp.sound_asset_version_id, force=True)

        def remove_sound(_) -> None:
            self._safe(lambda: library.remove_stamp_sound(character_id, sequence), rebuild)

        buttons = [
            ft.IconButton(
                ft.Icons.UPLOAD_OUTLINED, on_click=import_image, tooltip="Import image",
                icon_size=16,
            ),
            ft.IconButton(
                ft.Icons.MUSIC_NOTE_OUTLINED, on_click=import_sound,
                tooltip="Import sound", icon_size=16,
            ),
        ]
        if stamp.sound_asset_version_id:
            buttons += [
                ft.IconButton(
                    ft.Icons.PLAY_ARROW_OUTLINED, on_click=play_sound,
                    tooltip="Test sound", icon_size=16,
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE, on_click=remove_sound,
                    tooltip="Remove sound", icon_size=16,
                ),
            ]

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(f"#{sequence}", size=11, color=MUTED_TEXT),
                    stamp_image(self.app.img_src(stamp.image_asset_version_id), width=144),
                    ft.Row(buttons, spacing=0),
                ],
                spacing=3,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            border=ft.border.all(2, "#E2E0DB" if has_image else "#C97B72"),
            border_radius=8,
            padding=6,
            tooltip=None if has_image else "Required image missing",
        )

    def _safe(self, action, rebuild) -> None:
        try:
            action()
        except TaskStampsError as error:
            self.app.error(error)
            return
        rebuild()
