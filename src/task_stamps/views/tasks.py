"""Tasks screen: filterable list, editor dialog, detail dialog."""

from __future__ import annotations

import flet as ft

from task_stamps.components.common import (
    portrait_image,
    progress_run,
    section_title,
)
from task_stamps.components.theme import (
    BAD, BG, BG_HOVER_ALPHA, MUTED, MUTED_2, SERIF, TEXT, TEXT_DIM,
    eyebrow, hairline, style_dialog, text_action,
)
from task_stamps.domain.enums import WEEKDAY_SHORT, PoolType, TaskStatus, TaskWeight
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.domain.models import HabitTask
from task_stamps.utilities.dates import mask_label, mask_to_weekdays, weekdays_to_mask
from task_stamps.views.base import View

_FILTERS = ("All", "Today", "Active", "Paused", "Draft", "Archived")


class TasksView(View):
    def build(self) -> ft.Control:
        self.filter_dropdown = ft.Dropdown(
            value="All",
            options=[ft.dropdown.Option(name) for name in _FILTERS],
            width=140,
            on_change=lambda _: self.refresh(),
            label="Show",
        )
        self.world_dropdown = ft.Dropdown(
            value="*", width=200, on_change=lambda _: self.refresh(), label="Pool"
        )
        self.rows = ft.Column(spacing=0)
        self.content_host = ft.Container(content=self.rows)
        header = ft.Row(
            [
                ft.Column([
                    eyebrow("Library"),
                    ft.Text("Tasks", size=48, color=TEXT, font_family=SERIF,
                            style=ft.TextStyle(height=1.04)),
                    ft.Text("Recurring work and the characters carrying it.", size=15, color=TEXT_DIM),
                ], spacing=10, expand=True),
                text_action("Create a task →", lambda _: self.open_editor(None), size=14),
            ],
            vertical_alignment=ft.CrossAxisAlignment.END,
        )
        filters = ft.Row([self.filter_dropdown, self.world_dropdown], spacing=20)
        return ft.Container(
            content=ft.Column([header, filters, self.content_host], spacing=28, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.only(left=56, right=56, top=40, bottom=72),
            expand=True,
        )

    # -- list ---------------------------------------------------------------

    def refresh(self) -> None:
        container = self.app.container
        worlds = container.worlds.list(include_archived=True)
        selected_world = self.world_dropdown.value or "*"
        self.world_dropdown.options = [
            ft.dropdown.Option("*", "All pools"),
            ft.dropdown.Option("all", "All-world pools"),
        ] + [ft.dropdown.Option(world.id, world.name) for world in worlds]
        if selected_world not in [option.key for option in self.world_dropdown.options]:
            selected_world = "*"
        self.world_dropdown.value = selected_world

        tasks = container.tasks.list()
        today = container.clock.today()
        filter_name = self.filter_dropdown.value or "All"
        rows: list[ft.Control] = []
        for task in tasks:
            if filter_name in ("Active", "Paused", "Draft", "Archived"):
                if task.status.value != filter_name.lower():
                    continue
            elif filter_name == "Today":
                if task.status != TaskStatus.ACTIVE or not (
                    container.schedule_service.is_scheduled_on(task, today)
                ):
                    continue
            elif task.status == TaskStatus.ARCHIVED:
                continue  # "All" hides archived; pick the Archived filter to see them
            if selected_world == "all" and task.pool_type != PoolType.ALL_WORLDS:
                continue
            if selected_world not in ("*", "all") and task.world_id != selected_world:
                continue
            rows.extend([self._task_row(task), hairline()])
        if rows:
            self.rows.controls = [hairline(), *rows]
            self.content_host.content = self.rows
        else:
            self.content_host.content = ft.Container(
                padding=32,
                content=ft.Text("No tasks match this filter.", color=MUTED),
            )
        self.page.update()

    def _task_row(self, task: HabitTask) -> ft.Control:
        container = self.app.container
        today = container.clock.today()
        progress = container.streak_service.task_progress(task.id)
        portrait_src = None
        character_name = "—"
        if progress.assignment is not None and progress.assignment.is_active:
            character = container.characters.get(progress.assignment.character_id)
            character_name = character.name
            portrait_src = self.app.img_src(character.portrait_asset_version_id)

        if task.status == TaskStatus.ACTIVE:
            if container.completions.exists_for_date(task.id, today):
                today_status = "Done today"
            elif container.schedule_service.is_scheduled_on(task, today):
                today_status = "Due today"
            else:
                today_status = "Not scheduled today"
        else:
            today_status = task.status.value.capitalize()
        next_date = container.schedule_service.next_scheduled_date(task, today)
        next_label = (
            f"next: {next_date.strftime('%a %d %b')}"
            if next_date and task.status == TaskStatus.ACTIVE
            else ""
        )

        state_note = task.description or (
            "Paused days never count as missed." if task.status == TaskStatus.PAUSED
            else "Activate it and a character will be drawn from its selected pool."
            if task.status == TaskStatus.DRAFT else ""
        )
        dim = MUTED if task.status in (TaskStatus.DRAFT, TaskStatus.PAUSED) else TEXT_DIM
        info = ft.Column(
            [
                ft.Text(task.name, size=25, color=TEXT if task.status == TaskStatus.ACTIVE else TEXT_DIM,
                        font_family=SERIF),
                ft.Text(f"{today_status} · {mask_label(task.weekday_mask)} · held by {character_name} · "
                        f"{task.weight.value.title()} weight", size=13.5, color=dim),
                ft.Text(state_note, size=13, color=MUTED_2),
            ],
            spacing=5,
            expand=True,
        )
        right: ft.Control = (
            text_action("Activate →", lambda _, task_id=task.id: self.open_detail(task_id))
            if task.status == TaskStatus.DRAFT else
            ft.Column([
                ft.Text(spans=[ft.TextSpan(str(progress.current_streak), ft.TextStyle(font_family=SERIF, size=22, color=TEXT)),
                               ft.TextSpan(" / 15", ft.TextStyle(font_family=SERIF, size=22, color="#6f645c"))],
                        text_align=ft.TextAlign.RIGHT),
                progress_run(progress.used_stamp_numbers, progress.next_stamp_number),
                ft.Text(next_label, size=12, color=MUTED_2),
            ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.END, width=168)
        )
        row = ft.Container(
            padding=ft.padding.symmetric(vertical=22),
            ink=True,
            on_click=lambda _, t=task: self.open_detail(t.id),
            content=ft.Row([portrait_image(portrait_src, width=66), info, right], spacing=26,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )
        row.on_hover = lambda e: setattr(e.control, "bgcolor", BG_HOVER_ALPHA if e.data == "true" else None) or e.control.update()
        return row

    # -- editor ---------------------------------------------------------------

    def open_editor(self, task_id: str | None) -> None:
        container = self.app.container
        task = container.tasks.get(task_id) if task_id else None
        name_field = ft.TextField(label="Name", value=task.name if task else "", width=380)
        description_field = ft.TextField(
            label="Description (optional)",
            value=task.description if task else "",
            width=380,
            multiline=True,
            min_lines=2,
        )
        selected_days: set[int] = set(mask_to_weekdays(task.weekday_mask)) if task else set()
        day_buttons: list[ft.Container] = []

        def toggle_day(day: int, control: ft.Container) -> None:
            if day in selected_days:
                selected_days.discard(day)
            else:
                selected_days.add(day)
            control.bgcolor = TEXT if day in selected_days else None
            control.content.color = BG if day in selected_days else TEXT_DIM
            self.page.update()

        for day, label in enumerate(WEEKDAY_SHORT):
            chip = ft.Container(
                content=ft.Text(
                    label,
                    size=12,
                    color=BG if day in selected_days else TEXT_DIM,
                ),
                bgcolor=TEXT if day in selected_days else None,
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=8,
            )
            chip.on_click = lambda _, d=day, c=chip: toggle_day(d, c)
            day_buttons.append(chip)

        worlds = container.worlds.list()
        pool_dropdown = ft.Dropdown(
            label="Character pool",
            width=380,
            value=(
                task.world_id
                if task and task.pool_type == PoolType.SPECIFIC_WORLD
                else "all"
            ),
            options=[ft.dropdown.Option("all", "All worlds")]
            + [ft.dropdown.Option(world.id, world.name) for world in worlds],
        )
        weight_dropdown = ft.Dropdown(
            label="Task weight",
            width=380,
            value=(task.weight.value if task else TaskWeight.MEDIUM.value),
            options=[
                ft.dropdown.Option(TaskWeight.TRIVIAL.value, "Trivial — stamps only"),
                ft.dropdown.Option(TaskWeight.MINOR.value, "Minor"),
                ft.dropdown.Option(TaskWeight.MEDIUM.value, "Medium"),
                ft.dropdown.Option(TaskWeight.MAJOR.value, "Major"),
            ],
        )

        dialog = style_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Edit task" if task else "New task"),
            content=ft.Column(
                [
                    name_field,
                    description_field,
                    section_title("Scheduled weekdays"),
                    ft.Row(day_buttons, spacing=6),
                    pool_dropdown,
                    weight_dropdown,
                ],
                tight=True,
                spacing=14,
                width=400,
            ),
        ))

        def pool_values() -> tuple[PoolType, str | None]:
            value = pool_dropdown.value or "all"
            if value == "all":
                return PoolType.ALL_WORLDS, None
            return PoolType.SPECIFIC_WORLD, value

        def save(activate: bool) -> None:
            pool_type, world_id = pool_values()
            mask = weekdays_to_mask(selected_days)
            try:
                if task is None:
                    saved = container.task_service.create_draft(
                        name_field.value or "", description_field.value or "",
                        mask, pool_type, world_id,
                        TaskWeight(weight_dropdown.value or TaskWeight.MEDIUM.value),
                    )
                else:
                    saved = container.task_service.update_task(
                        task.id,
                        name=name_field.value or "",
                        description=description_field.value or "",
                        weekday_mask=mask,
                        pool_type=pool_type,
                        world_id=world_id,
                        weight=TaskWeight(
                            weight_dropdown.value or TaskWeight.MEDIUM.value
                        ),
                    )
                if activate:
                    assignment = container.task_service.activate(saved.id)
                    self.app.close_dialog(dialog)
                    self._show_assignment_result(saved.name, assignment.character_id)
                else:
                    self.app.close_dialog(dialog)
                    self.app.notify("Task saved.")
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.refresh()

        actions: list[ft.Control] = [
            ft.TextButton("Cancel", on_click=lambda _: self.app.close_dialog(dialog)),
            ft.TextButton("Save as draft", on_click=lambda _: save(False)),
        ]
        if task is None or task.status == TaskStatus.DRAFT:
            actions.append(ft.TextButton("Save & activate", on_click=lambda _: save(True)))
        else:
            actions[1] = ft.TextButton("Save", on_click=lambda _: save(False))
        dialog.actions = actions
        self.app.open_dialog(dialog)

    def _show_assignment_result(self, task_name: str, character_id: str) -> None:
        """Shows which character was randomly drawn. There is deliberately no
        reroll button — assignments persist once made."""
        character = self.app.container.characters.get(character_id)
        src = self.app.img_src(character.portrait_asset_version_id)
        dialog = style_dialog(ft.AlertDialog(
            title=ft.Text("Task activated"),
            content=ft.Column(
                [
                    portrait_image(src, width=120),
                    ft.Text(character.name, size=16, weight=ft.FontWeight.W_600),
                    ft.Text(
                        f"will collect stamps for '{task_name}'.",
                        color=MUTED,
                    ),
                ],
                tight=True,
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ))
        dialog.actions = [ft.TextButton("Close", on_click=lambda _: self.app.close_dialog(dialog))]
        self.app.open_dialog(dialog)

    # -- detail ---------------------------------------------------------------

    def open_detail(self, task_id: str) -> None:
        container = self.app.container
        task = container.tasks.get(task_id)
        today = container.clock.today()
        progress = container.streak_service.task_progress(task.id)

        portrait_src: str | None = None
        character_info: ft.Control = ft.Text(
            "No character assigned.", size=14, color=MUTED
        )
        if progress.assignment is not None and progress.assignment.is_active:
            character = container.characters.get(progress.assignment.character_id)
            portrait_src = self.app.img_src(character.portrait_asset_version_id)
            character_info = ft.Column(
                [
                    ft.Text(
                        character.name, size=19, weight=ft.FontWeight.W_600
                    ),
                    ft.Text(
                        f"Streak {progress.current_streak}/15 · since "
                        f"{progress.assignment.started_on.strftime('%d %b %Y')}",
                        size=14,
                        color=MUTED,
                    ),
                ],
                spacing=3,
            )

        completions = container.completions.list_for_task(task.id, limit=6)
        completion_rows = [
            ft.Text(
                f"{completion.completion_date.strftime('%d %b %Y')} — stamp "
                f"{completion.streak_number} ({completion.character_name_snapshot})",
                size=13,
                color=MUTED,
            )
            for completion in completions
        ] or [ft.Text("No completions yet.", size=13, color=MUTED)]

        history_rows: list[ft.Control] = []
        for assignment in container.assignments.history_for_task(task.id, limit=6):
            character = container.characters.get(assignment.character_id)
            outcome = "active" if assignment.is_active else (
                assignment.end_reason.value if assignment.end_reason else "ended"
            )
            extra = (
                f" (missed {assignment.dropped_due_date.strftime('%d %b')})"
                if assignment.dropped_due_date
                else ""
            )
            history_rows.append(
                ft.Text(
                    f"{character.name}: {outcome}{extra}, streak {assignment.current_streak}",
                    size=13,
                    color=MUTED,
                )
            )

        board_dates = container.placements.boards_with_task(task.id, limit=6)
        board_links = ft.Row(
            [
                ft.TextButton(
                    day.strftime("%d %b"),
                    on_click=lambda _, d=day: self.app.open_history_board(d),
                )
                for day in board_dates
            ],
            wrap=True,
        ) if board_dates else ft.Text("No boards yet.", size=13, color=MUTED)

        next_date = container.schedule_service.next_scheduled_date(task, today)
        portrait_panel = ft.Container(
            content=portrait_image(portrait_src, width=None),
            width=390,
            height=620,
        )
        details = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(task.status.value.capitalize(), size=14, color=TEXT_DIM),
                        ft.Text(mask_label(task.weekday_mask), size=14, color=MUTED),
                        ft.Text(
                            f"next: {next_date.strftime('%a %d %b')}" if next_date else "",
                            size=14,
                            color=MUTED,
                        ),
                    ],
                    spacing=10,
                ),
                ft.Text(task.description or "", size=14, color=MUTED),
                ft.Text(
                    f"{task.weight.value.title()} weight",
                    size=14,
                    color=MUTED,
                ),
                section_title("Character"),
                character_info,
                progress_run(progress.used_stamp_numbers, progress.next_stamp_number),
                section_title("Recent completions"),
                *completion_rows,
                section_title("Assignment history"),
                *history_rows,
                section_title("Recent boards"),
                board_links,
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
        dialog = style_dialog(ft.AlertDialog(
            title=ft.Text(task.name, size=22, weight=ft.FontWeight.W_600),
            content=content,
        ))

        def act(action: str) -> None:
            try:
                if action == "pause":
                    container.task_service.pause(task.id)
                elif action == "resume":
                    container.task_service.resume(task.id)
                elif action == "activate":
                    assignment = container.task_service.activate(task.id)
                    self.app.close_dialog(dialog)
                    self._show_assignment_result(task.name, assignment.character_id)
                    self.refresh()
                    return
                elif action == "archive":
                    container.task_service.archive(task.id)
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.close_dialog(dialog)
            self.app.refresh_chest_count()
            self.refresh()

        actions: list[ft.Control] = [
            ft.TextButton("Close", on_click=lambda _: self.app.close_dialog(dialog)),
            ft.TextButton(
                "Edit",
                on_click=lambda _: (self.app.close_dialog(dialog), self.open_editor(task.id)),
            ),
        ]
        if task.status == TaskStatus.ACTIVE:
            actions.append(ft.TextButton("Pause", on_click=lambda _: act("pause")))
        elif task.status == TaskStatus.PAUSED:
            actions.append(ft.TextButton("Resume", on_click=lambda _: act("resume")))
        elif task.status == TaskStatus.DRAFT:
            actions.append(ft.TextButton("Activate", on_click=lambda _: act("activate")))
        if task.status != TaskStatus.ARCHIVED:
            actions.append(
                ft.TextButton(
                    "Archive",
                    on_click=lambda _: act("archive"),
                    style=ft.ButtonStyle(color=BAD),
                )
            )
        dialog.actions = actions
        self.app.open_dialog(dialog)
