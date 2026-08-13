"""Tasks screen: filterable list, editor dialog, detail dialog."""

from __future__ import annotations

import flet as ft

from task_stamps.components.common import (
    MUTED_TEXT,
    STATUS_COLORS,
    card,
    portrait_image,
    progress_dots,
    section_title,
    status_chip,
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
        self.grid = ft.GridView(
            expand=True,
            max_extent=480,
            child_aspect_ratio=2.4,
            spacing=16,
            run_spacing=16,
            padding=ft.padding.only(bottom=24),
        )
        self.content_host = ft.Container(content=self.grid, expand=True)
        header = ft.Container(
            padding=ft.padding.only(left=24, right=24, top=18, bottom=8),
            content=ft.Row(
                [
                    ft.Text("Tasks", size=20, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    self.filter_dropdown,
                    self.world_dropdown,
                    ft.FilledButton(
                        "New task", icon=ft.Icons.ADD, on_click=lambda _: self.open_editor(None)
                    ),
                ],
                spacing=12,
            ),
        )
        body = ft.Container(
            padding=ft.padding.symmetric(horizontal=24), content=self.content_host, expand=True
        )
        return ft.Column([header, body], expand=True, spacing=0)

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
            rows.append(self._task_card(task))
        if rows:
            self.grid.controls = rows
            self.content_host.content = self.grid
        else:
            self.content_host.content = ft.Container(
                padding=32,
                content=ft.Text("No tasks match this filter.", color=MUTED_TEXT),
            )
        self.page.update()

    def _task_card(self, task: HabitTask) -> ft.Control:
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

        info = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            task.name,
                            size=16,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                            no_wrap=False,
                        ),
                    ],
                    spacing=8,
                ),
                status_chip(task.status.value, STATUS_COLORS[task.status.value]),
                ft.Text(
                    f"{task.weight.value.title()} weight",
                    size=12,
                    color=MUTED_TEXT,
                ),
                ft.Text(
                    f"{mask_label(task.weekday_mask)} · {character_name}",
                    size=12,
                    color=MUTED_TEXT,
                ),
                ft.Text(
                    f"streak {progress.current_streak}/15",
                    size=12,
                    color=MUTED_TEXT,
                ),
                ft.Text(
                    " · ".join(part for part in (today_status, next_label) if part),
                    size=12,
                    color=MUTED_TEXT,
                ),
            ],
            spacing=4,
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        return card(
            ft.Row(
                [portrait_image(portrait_src, width=112), info],
                spacing=14,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda _, t=task: self.open_detail(t.id),
        )

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
            control.bgcolor = "#7C8B74" if day in selected_days else "#EDECE7"
            control.content.color = "#FFFFFF" if day in selected_days else "#55534E"
            self.page.update()

        for day, label in enumerate(WEEKDAY_SHORT):
            chip = ft.Container(
                content=ft.Text(
                    label,
                    size=12,
                    color="#FFFFFF" if day in selected_days else "#55534E",
                ),
                bgcolor="#7C8B74" if day in selected_days else "#EDECE7",
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

        dialog = ft.AlertDialog(
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
        )

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
                    self.page.close(dialog)
                    self._show_assignment_result(saved.name, assignment.character_id)
                else:
                    self.page.close(dialog)
                    self.app.notify("Task saved.")
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.refresh()

        actions: list[ft.Control] = [
            ft.TextButton("Cancel", on_click=lambda _: self.page.close(dialog)),
            ft.TextButton("Save as draft", on_click=lambda _: save(False)),
        ]
        if task is None or task.status == TaskStatus.DRAFT:
            actions.append(ft.FilledButton("Save & activate", on_click=lambda _: save(True)))
        else:
            actions[1] = ft.FilledButton("Save", on_click=lambda _: save(False))
        dialog.actions = actions
        self.page.open(dialog)

    def _show_assignment_result(self, task_name: str, character_id: str) -> None:
        """Shows which character was randomly drawn. There is deliberately no
        reroll button — assignments persist once made."""
        character = self.app.container.characters.get(character_id)
        src = self.app.img_src(character.portrait_asset_version_id)
        dialog = ft.AlertDialog(
            title=ft.Text("Task activated"),
            content=ft.Column(
                [
                    portrait_image(src, width=120),
                    ft.Text(character.name, size=16, weight=ft.FontWeight.W_600),
                    ft.Text(
                        f"will collect stamps for '{task_name}'.",
                        color=MUTED_TEXT,
                    ),
                ],
                tight=True,
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        dialog.actions = [ft.TextButton("OK", on_click=lambda _: self.page.close(dialog))]
        self.page.open(dialog)

    # -- detail ---------------------------------------------------------------

    def open_detail(self, task_id: str) -> None:
        container = self.app.container
        task = container.tasks.get(task_id)
        today = container.clock.today()
        progress = container.streak_service.task_progress(task.id)

        portrait_src: str | None = None
        character_info: ft.Control = ft.Text(
            "No character assigned.", size=14, color=MUTED_TEXT
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
                        color=MUTED_TEXT,
                    ),
                ],
                spacing=3,
            )

        completions = container.completions.list_for_task(task.id, limit=6)
        completion_rows = [
            ft.Text(
                f"{completion.completion_date.strftime('%d %b %Y')} — stamp "
                f"{completion.streak_number} ({completion.character_name_snapshot}) · "
                f"+{completion.reward_points} points",
                size=13,
                color=MUTED_TEXT,
            )
            for completion in completions
        ] or [ft.Text("No completions yet.", size=13, color=MUTED_TEXT)]

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
                    color=MUTED_TEXT,
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
        ) if board_dates else ft.Text("No boards yet.", size=13, color=MUTED_TEXT)

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
                        status_chip(task.status.value, STATUS_COLORS[task.status.value]),
                        ft.Text(mask_label(task.weekday_mask), size=14, color=MUTED_TEXT),
                        ft.Text(
                            f"next: {next_date.strftime('%a %d %b')}" if next_date else "",
                            size=14,
                            color=MUTED_TEXT,
                        ),
                    ],
                    spacing=10,
                ),
                ft.Text(task.description or "", size=14, color=MUTED_TEXT),
                ft.Text(
                    f"{task.weight.value.title()} weight",
                    size=14,
                    color=MUTED_TEXT,
                ),
                section_title("Character"),
                character_info,
                progress_dots(
                    progress.used_stamp_numbers, progress.next_stamp_number, size=16
                ),
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
        dialog = ft.AlertDialog(
            title=ft.Text(task.name, size=22, weight=ft.FontWeight.W_600),
            content=content,
        )

        def act(action: str) -> None:
            try:
                if action == "pause":
                    deducted = container.task_service.pause(task.id)
                    if deducted:
                        self.app.notify(
                            f"Paused {task.name} and deducted {deducted} "
                            f"point{'s' if deducted != 1 else ''}."
                        )
                elif action == "resume":
                    container.task_service.resume(task.id)
                elif action == "activate":
                    assignment = container.task_service.activate(task.id)
                    self.page.close(dialog)
                    self._show_assignment_result(task.name, assignment.character_id)
                    self.refresh()
                    return
                elif action == "archive":
                    container.task_service.archive(task.id)
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.page.close(dialog)
            self.refresh()

        actions: list[ft.Control] = [
            ft.TextButton("Close", on_click=lambda _: self.page.close(dialog)),
            ft.TextButton(
                "Edit",
                on_click=lambda _: (self.page.close(dialog), self.open_editor(task.id)),
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
                    style=ft.ButtonStyle(color="#A65D57"),
                )
            )
        dialog.actions = actions
        self.page.open(dialog)
