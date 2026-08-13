"""Today screen: the large daily stamp board and the Add Stamp flow."""

from __future__ import annotations

import threading

import flet as ft

from task_stamps.components.board import build_board
from task_stamps.components.common import MUTED_TEXT, portrait_image
from task_stamps.components.stamp_details import show_stamp_details
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.services.board_service import BoardService
from task_stamps.services.completion_service import CompletionResult
from task_stamps.services.reward_service import reward_for
from task_stamps.views.base import View


class TodayView(View):
    def build(self) -> ft.Control:
        self.date_text = ft.Text("", size=20, weight=ft.FontWeight.W_600)
        self.subtitle = ft.Text("", size=13, color=MUTED_TEXT)
        self.board_host = ft.Container(
            expand=True, alignment=ft.alignment.center, padding=16
        )
        header = ft.Container(
            padding=ft.padding.only(left=24, right=24, top=18, bottom=4),
            content=ft.Row(
                [
                    ft.Column([self.date_text, self.subtitle], spacing=2),
                    ft.Container(expand=True),
                    ft.FilledButton(
                        "Add stamp",
                        icon=ft.Icons.ADD,
                        on_click=lambda _: self.open_add_panel(),
                    ),
                ]
            ),
        )
        self.root = ft.Column([header, self.board_host], expand=True, spacing=0)
        return self.root

    # -- board rendering ---------------------------------------------------

    def _board_area(self) -> tuple[float, float]:
        page_w = self.page.width or 1100
        page_h = self.page.height or 750
        available_w = max(360, page_w - self.app.rail_width - 80)
        available_h = max(240, page_h - 130)
        return BoardService.board_size_for(available_w, available_h)

    def refresh(self, animate_last: bool = False) -> None:
        container = self.app.container
        today = container.clock.today()
        self.date_text.value = today.strftime("%A, %d %B %Y")
        available = len(container.completion_service.available_tasks_today())
        count = container.board_service.stamp_count(today)
        parts = [f"{count} stamp{'s' if count != 1 else ''} today"]
        if available:
            parts.append(f"{available} task{'s' if available != 1 else ''} ready to complete")
        self.subtitle.value = " · ".join(parts)

        stamps = container.board_service.load_board(today)
        board_w, board_h = self._board_area()
        board = build_board(
            stamps,
            board_w,
            board_h,
            container.settings_service.board_background_color,
            on_stamp_click=lambda s: show_stamp_details(self.app, s, self.refresh),
            on_board_click=self.open_add_panel,
            empty_hint="No stamps yet — complete a task to place the first one.",
        )
        if animate_last and stamps and not container.settings_service.reduced_animation:
            self._animate_last_stamp(board)
        self.board_host.content = board
        self.page.update()

    def _animate_last_stamp(self, board: ft.Container) -> None:
        """Brief drop-in: start above and enlarged, then settle with a
        bounce. Skipped entirely when reduced animation is on."""
        stack: ft.Stack = board.content  # type: ignore[assignment]
        control: ft.Container = stack.controls[-1]  # type: ignore[assignment]
        control.scale = 1.6
        control.opacity = 0.0
        control.offset = ft.Offset(0, -0.25)
        control.animate_scale = ft.Animation(340, ft.AnimationCurve.BOUNCE_OUT)
        control.animate_opacity = ft.Animation(160, ft.AnimationCurve.EASE_IN)
        control.animate_offset = ft.Animation(260, ft.AnimationCurve.EASE_OUT)

        def settle() -> None:
            control.scale = 1.0
            control.opacity = 1.0
            control.offset = ft.Offset(0, 0)
            try:
                self.page.update()
            except Exception:  # page may be closing
                pass

        threading.Timer(0.06, settle).start()

    # -- add stamp panel ------------------------------------------------------

    def open_add_panel(self) -> None:
        self._add_dialog = ft.AlertDialog(
            title=ft.Text("Complete a task"),
            content=ft.Container(width=430, content=self._build_task_list()),
        )
        self._add_dialog.actions = [
            ft.TextButton("Close", on_click=lambda _: self.page.close(self._add_dialog))
        ]
        self.page.open(self._add_dialog)

    def _build_task_list(self) -> ft.Control:
        available = self.app.container.completion_service.available_tasks_today()
        if not available:
            return ft.Container(
                padding=24,
                content=ft.Text(
                    "Nothing to complete right now. Tasks appear here when they "
                    "are active, scheduled for today, have an assigned character "
                    "and are not completed yet.",
                    color=MUTED_TEXT,
                ),
            )
        tiles: list[ft.Control] = []
        for item in available:
            src = self.app.img_src(item.portrait_version_id)
            points = reward_for(item.task.weight, item.next_stamp_number)
            tiles.append(
                ft.ListTile(
                    leading=portrait_image(src, width=42),
                    title=ft.Text(item.task.name),
                    subtitle=ft.Text(
                        f"{item.character_name} · streak {item.current_streak}/15 · "
                        f"next stamp #{item.next_stamp_number} · "
                        + (f"+{points} points" if points else "stamps only"),
                        size=12,
                        color=MUTED_TEXT,
                    ),
                    on_click=lambda _, task_id=item.task.id: self._complete(task_id),
                )
            )
        return ft.Column(tiles, tight=True, scroll=ft.ScrollMode.AUTO, height=min(360, 76 * len(tiles)))

    def _complete(self, task_id: str) -> None:
        try:
            result = self.app.container.completion_service.complete_task(task_id)
        except TaskStampsError as error:
            self.app.error(error)
            if hasattr(self, "_add_dialog"):
                self._add_dialog.content = ft.Container(
                    width=430, content=self._build_task_list()
                )
                self.page.update()
            return
        if hasattr(self, "_add_dialog"):
            self.page.close(self._add_dialog)
        self.refresh(animate_last=True)
        self.app.play_stamp_sound_version(result.sound_version_id)
        self._show_undo_snack(result)
        self._announce_rollover(result)

    def _show_undo_snack(self, result: CompletionResult) -> None:
        completion = result.completion
        snack = ft.SnackBar(
            content=ft.Text(
                f"{completion.task_name_snapshot}: stamp {completion.streak_number} placed"
                + (
                    f" · +{result.reward_points} point"
                    f"{'s' if result.reward_points != 1 else ''}."
                    if result.reward_points
                    else " · no points (Trivial)."
                )
            ),
            action="Undo",
            duration=8000,
            on_action=lambda _: self._undo(completion.id),
        )
        self.page.open(snack)

    def _undo(self, completion_id: str) -> None:
        try:
            self.app.container.completion_service.undo_completion(completion_id)
        except TaskStampsError as error:
            self.app.error(error)
            return
        self.app.notify("Completion undone — the task is available again today.")
        self.refresh()

    def _announce_rollover(self, result: CompletionResult) -> None:
        if not result.assignment_completed:
            return
        if result.new_assignment is not None:
            character = self.app.container.characters.get(
                result.new_assignment.character_id
            )
            message = (
                "All 15 stamps collected! A new character joined the task: "
                f"{character.name}."
            )
        else:
            message = (
                "All 15 stamps collected! No eligible character is available, "
                "so the task moved back to drafts."
            )
        dialog = ft.AlertDialog(title=ft.Text("Character complete"), content=ft.Text(message))
        dialog.actions = [ft.TextButton("Nice", on_click=lambda _: self.page.close(dialog))]
        self.page.open(dialog)
