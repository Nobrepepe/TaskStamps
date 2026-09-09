"""Today: daily Boss banner, recessed stamp board, and completion flow."""

from __future__ import annotations

import threading

import flet as ft

from task_stamps.components.board import build_board
from task_stamps.components.common import portrait_image
from task_stamps.components.stamp_details import show_stamp_details
from task_stamps.components.theme import (
    ACCENT_2,
    BG,
    BG_2,
    MUTED,
    MUTED_2,
    SERIF,
    TEXT,
    TEXT_DIM,
    eyebrow,
    hairline,
    style_dialog,
    text_action,
)
from task_stamps.domain.enums import CHEST_TIERS, CHEST_WEIGHTS
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.services.completion_service import CompletionResult
from task_stamps.views.base import View


class TodayView(View):
    def build(self) -> ft.Control:
        self.banner_host = ft.Container()
        self.progress_host = ft.Container()
        self.board_host = ft.Container(alignment=ft.alignment.center)
        self.caption_host = ft.Container()
        self.root = ft.Column(
            [
                self.banner_host,
                self.progress_host,
                ft.Container(height=26),
                self.board_host,
                self.caption_host,
            ],
            expand=True,
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
        )
        return ft.Container(content=self.root, expand=True, alignment=ft.alignment.top_left)

    def _content_width(self) -> float:
        return max(0.0, (self.page.width or 1100) - self.app.rail_width)

    def _board_area(self) -> tuple[float, float]:
        page_w = self.page.width or 1100
        available_w = max(360, page_w - self.app.rail_width - 112)
        return available_w, available_w * 9 / 16

    def refresh(self, animate_last: bool = False) -> None:
        container = self.app.container
        today = container.clock.today()
        available = len(container.completion_service.available_tasks_today())
        count = container.board_service.stamp_count(today)
        boss = (
            container.boss_service.daily_boss(today)
            if container.settings_service.boss_banner_enabled
            else None
        )
        self._render_banner(boss, count, available)

        stamps = container.board_service.load_board(today)
        board_w, board_h = self._board_area()
        board = build_board(
            stamps,
            board_w,
            board_h,
            container.settings_service.board_background_color,
            on_stamp_click=lambda stamp: show_stamp_details(self.app, stamp, self.refresh),
            on_board_click=self.open_add_panel,
            empty_hint="No stamps yet — complete a task to place the first one.",
        )
        if animate_last and stamps and not container.settings_service.reduced_animation:
            self._animate_last_stamp(board)
        self.board_host.width = self._content_width()
        self.board_host.content = board
        action: ft.Control
        if available:
            action = text_action("Complete a task →", lambda _: self.open_add_panel(), size=14)
        elif stamps:
            last = stamps[-1]
            action = ft.Text(
                f"{last.character_name_snapshot} placed stamp {last.streak_number} of 15.",
                size=13,
                color=MUTED,
            )
        else:
            action = ft.Text("No tasks are waiting today.", size=13, color=MUTED)
        self.caption_host.width = self._content_width()
        self.caption_host.padding = ft.padding.only(left=56, right=56, top=14)
        self.caption_host.content = ft.Row(
            [
                ft.Text(
                    "The layout is saved once. This board will look exactly like this forever.",
                    size=13,
                    color=MUTED,
                    expand=True,
                ),
                action,
            ],
            spacing=24,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.page.update()

    def _render_banner(self, boss, stamp_count: int, available: int) -> None:
        width = self._content_width()
        if boss is None:
            self.banner_host.visible = False
            self.progress_host.visible = False
            return
        self.banner_host.visible = True
        self.progress_host.visible = True
        subtitle = (
            f"{stamp_count} stamp{'s have' if stamp_count != 1 else ' has'} landed. "
            + (f"{available} task{'s are' if available != 1 else ' is'} still waiting on you."
               if available else "Every scheduled task is complete.")
        )
        ratio = min(1.0, boss.strikes_landed / boss.strikes_target) if boss.strikes_target else 0.0
        progress_width = width * ratio
        dot = ft.Container(
            width=7,
            height=7,
            bgcolor=ACCENT_2,
            border_radius=4,
            left=max(0, progress_width - 3.5),
            top=-2,
            opacity=1.0 if self.app.container.settings_service.reduced_animation else 0.55,
        )
        if not self.app.container.settings_service.reduced_animation:
            dot.animate_opacity = ft.Animation(1800, ft.AnimationCurve.EASE_IN_OUT)

            def breathe(_=None) -> None:
                if dot.page is None:
                    return
                dot.opacity = 0.55 if dot.opacity and dot.opacity > 0.7 else 1.0
                dot.update()

            dot.on_animation_end = breathe
            threading.Timer(0.08, lambda: breathe()).start()
        art = ft.ShaderMask(
            content=ft.Image(
                src="/" + boss.image_relative_path,
                width=width * 0.44,
                height=295,
                fit=ft.ImageFit.CONTAIN,
            ),
            width=width * 0.44,
            height=295,
            right=width * 0.02,
            top=-25,
            shader=ft.LinearGradient(
                begin=ft.alignment.top_center,
                end=ft.alignment.bottom_center,
                colors=["#00000000", "#FF000000", "#FF000000", "#00000000"],
                stops=[0, 0.12, 0.82, 1],
            ),
            blend_mode=ft.BlendMode.DST_IN,
        )
        left = ft.Container(
            left=56,
            bottom=30,
            width=width * 0.52,
            content=ft.Column(
                [
                    eyebrow("Today"),
                    ft.Text(
                        boss.date.strftime("%A, %d %B %Y"),
                        size=33,
                        color=TEXT,
                        font_family=SERIF,
                        style=ft.TextStyle(height=1.06),
                    ),
                    ft.Text(subtitle, size=13.5, color=TEXT_DIM),
                ],
                spacing=8,
            ),
        )
        right = ft.Container(
            right=56,
            bottom=30,
            content=ft.Column(
                [
                    eyebrow(f"{boss.world_name} · Day {boss.day_number}", TEXT_DIM),
                    ft.Text(boss.name, size=30, color=TEXT, font_family=SERIF),
                ],
                spacing=7,
                horizontal_alignment=ft.CrossAxisAlignment.END,
            ),
        )
        self.banner_host.width = width
        self.banner_host.height = 246
        self.banner_host.clip_behavior = ft.ClipBehavior.HARD_EDGE
        self.banner_host.content = ft.Stack(
            [
                ft.Container(
                    width=width,
                    height=246,
                    gradient=ft.RadialGradient(
                        center=ft.alignment.Alignment(0.4, -0.12),
                        radius=0.9,
                        colors=["#452DBEC4", "#1245BEC4", "#0012100f"],
                        stops=[0, 0.46, 0.76],
                    ),
                ),
                art,
                ft.Container(
                    width=width,
                    height=246,
                    gradient=ft.LinearGradient(
                        begin=ft.alignment.center_left,
                        end=ft.alignment.center_right,
                        colors=[BG, "#D112100f", "#0012100f"],
                        stops=[0.04, 0.30, 0.56],
                    ),
                ),
                ft.Container(
                    width=width,
                    height=246,
                    gradient=ft.LinearGradient(
                        begin=ft.alignment.bottom_center,
                        end=ft.alignment.top_center,
                        colors=[BG, "#8012100f", "#0012100f"],
                        stops=[0, 0.14, 0.44],
                    ),
                ),
                ft.Container(
                    right=0,
                    bottom=0,
                    width=width * 0.46,
                    height=148,
                    gradient=ft.LinearGradient(
                        begin=ft.alignment.bottom_center,
                        end=ft.alignment.top_center,
                        colors=["#E612100f", "#9E12100f", "#0012100f"],
                    ),
                ),
                left,
                right,
                ft.Container(left=0, bottom=0, width=width, height=3, bgcolor="#1Ff4ece1"),
                ft.Container(
                    left=0,
                    bottom=0,
                    width=progress_width,
                    height=3,
                    gradient=ft.LinearGradient(colors=["#66b48ade", ACCENT_2]),
                ),
                dot,
            ],
            width=width,
            height=246,
        )
        remaining = boss.strikes_remaining
        state = (
            f"Boss defeated. All {boss.strikes_target} strikes landed."
            if boss.defeated
            else f"{boss.strikes_landed} of {boss.strikes_target} strikes landed. "
                 f"{remaining} task{'s' if remaining != 1 else ''} remain today."
        )
        self.progress_host.width = width
        self.progress_host.padding = ft.padding.only(left=56, right=56, top=14)
        self.progress_host.content = ft.Row(
            [
                ft.Text(state, size=13.5, color=TEXT_DIM, expand=True),
                ft.Text(
                    f"{boss.strikes_landed} / {boss.strikes_target}",
                    size=19,
                    color=TEXT,
                    font_family=SERIF,
                    no_wrap=True,
                ),
            ]
        )

    def _animate_last_stamp(self, board: ft.Container) -> None:
        stack: ft.Stack = board.content  # type: ignore[assignment]
        control: ft.Container = stack.controls[-1]  # type: ignore[assignment]
        control.scale = 1.14
        control.opacity = 0.0
        control.offset = ft.Offset(0, -0.07)
        settle = ft.Animation(620, ft.AnimationCurve.EASE_OUT_CUBIC)
        control.animate_scale = settle
        control.animate_opacity = settle
        control.animate_offset = settle

        def finish() -> None:
            control.scale = 1.0
            control.opacity = 1.0
            control.offset = ft.Offset(0, 0)
            try:
                self.page.update()
            except Exception:
                pass

        threading.Timer(0.06, finish).start()

    def open_add_panel(self) -> None:
        self._add_dialog = style_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Complete a task"),
                content=ft.Container(width=470, content=self._build_task_list()),
            )
        )
        self._add_dialog.actions = [
            ft.TextButton("Close", on_click=lambda _: self.app.close_dialog(self._add_dialog))
        ]
        self.app.open_dialog(self._add_dialog)

    def _build_task_list(self) -> ft.Control:
        available = self.app.container.completion_service.available_tasks_today()
        if not available:
            return ft.Container(
                padding=24,
                content=ft.Text(
                    "Nothing to complete right now. Active scheduled tasks appear here when "
                    "they have an assigned character and are not completed yet.",
                    color=TEXT_DIM,
                ),
            )
        rows: list[ft.Control] = [hairline()]
        for item in available:
            earns_chest = (
                item.task.weight in CHEST_WEIGHTS
                and item.next_stamp_number in CHEST_TIERS
            )
            row = ft.Container(
                padding=ft.padding.symmetric(vertical=13),
                ink=True,
                on_click=lambda _, task_id=item.task.id: self._complete(task_id),
                content=ft.Row(
                    [
                        portrait_image(self.app.img_src(item.portrait_version_id), width=48),
                        ft.Column(
                            [
                                ft.Text(item.task.name, size=20, color=TEXT, font_family=SERIF),
                                ft.Text(
                                    f"{item.character_name} · streak {item.current_streak}/15 · "
                                    f"next stamp #{item.next_stamp_number}"
                                    + (" · chest at this stamp" if earns_chest else ""),
                                    size=12,
                                    color=MUTED_2,
                                ),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                    ],
                    spacing=14,
                ),
            )
            rows.extend([row, hairline()])
        return ft.Column(rows, tight=True, scroll=ft.ScrollMode.AUTO, height=min(390, 84 * len(available)))

    def _complete(self, task_id: str) -> None:
        try:
            result = self.app.container.completion_service.complete_task(task_id)
        except TaskStampsError as error:
            self.app.error(error)
            if hasattr(self, "_add_dialog"):
                self._add_dialog.content = ft.Container(width=470, content=self._build_task_list())
                self.page.update()
            return
        if hasattr(self, "_add_dialog"):
            self.app.close_dialog(self._add_dialog)
        # The Boss chest is minted once per defeat, so its arrival *is* the
        # "newly defeated" signal the sound waits on.
        boss = self.app.container.boss_service.daily_boss()
        self.refresh(animate_last=True)
        self.app.refresh_chest_count()
        self.app.play_completion_sounds(
            result.sound_version_id,
            boss.sound_relative_path if result.boss_chest_granted and boss else None,
        )
        self._show_undo_snack(result)
        self._announce_rollover(result)

    def _show_undo_snack(self, result: CompletionResult) -> None:
        completion = result.completion
        self.page.open(
            ft.SnackBar(
                content=ft.Text(
                    f"{completion.task_name_snapshot}: stamp {completion.streak_number} placed"
                    + (f" · chest earned: {result.chest.reward_name_snapshot}" if result.chest else "")
                    + (" · Boss chest sealed!" if result.boss_chest_granted else ""),
                    color=TEXT,
                ),
                bgcolor=BG_2,
                action="Undo",
                duration=8000,
                on_action=lambda _: self._undo(completion.id),
            )
        )

    def _undo(self, completion_id: str) -> None:
        try:
            self.app.container.completion_service.undo_completion(completion_id)
        except TaskStampsError as error:
            self.app.error(error)
            return
        self.app.notify("Completion undone — the task is available again today.")
        self.app.refresh_chest_count()
        self.refresh()

    def _announce_rollover(self, result: CompletionResult) -> None:
        if not result.assignment_completed:
            return
        if result.new_assignment is not None:
            character = self.app.container.characters.get(result.new_assignment.character_id)
            message = f"All 15 stamps collected. {character.name} now carries this task."
        else:
            message = "All 15 stamps collected. No eligible character is available, so the task moved back to drafts."
        dialog = style_dialog(
            ft.AlertDialog(title=ft.Text("Character complete"), content=ft.Text(message, color=TEXT_DIM))
        )
        dialog.actions = [ft.TextButton("Close", on_click=lambda _: self.app.close_dialog(dialog))]
        self.app.open_dialog(dialog)
