"""Monthly calendar with per-day stamp counts, previews, and history boards."""

from __future__ import annotations

import calendar
from datetime import date

import flet as ft

from task_stamps.components.board import build_board
from task_stamps.components.common import BORDER_COLOR, MUTED_TEXT
from task_stamps.components.stamp_details import show_stamp_details
from task_stamps.domain.enums import WEEKDAY_SHORT
from task_stamps.domain.models import BoardStamp
from task_stamps.views.base import View

_MAX_PREVIEWS = 3


class CalendarView(View):
    def build(self) -> ft.Control:
        today = self.app.container.clock.today()
        self.year = today.year
        self.month = today.month
        self.title_text = ft.Text("", size=20, weight=ft.FontWeight.W_600)
        header = ft.Container(
            padding=ft.padding.only(left=24, right=24, top=18, bottom=8),
            content=ft.Row(
                [
                    self.title_text,
                    ft.Container(expand=True),
                    ft.IconButton(
                        ft.Icons.CHEVRON_LEFT, on_click=lambda _: self._shift(-1),
                        tooltip="Previous month",
                    ),
                    ft.TextButton("Today", on_click=lambda _: self._go_today()),
                    ft.IconButton(
                        ft.Icons.CHEVRON_RIGHT, on_click=lambda _: self._shift(1),
                        tooltip="Next month",
                    ),
                ]
            ),
        )
        self.grid_host = ft.Container(
            expand=True, padding=ft.padding.only(left=24, right=24, bottom=20)
        )
        return ft.Column([header, self.grid_host], expand=True, spacing=0)

    def _shift(self, delta: int) -> None:
        month = self.month + delta
        if month < 1:
            self.month, self.year = 12, self.year - 1
        elif month > 12:
            self.month, self.year = 1, self.year + 1
        else:
            self.month = month
        self.refresh()

    def _go_today(self) -> None:
        today = self.app.container.clock.today()
        self.year, self.month = today.year, today.month
        self.refresh()

    def refresh(self) -> None:
        container = self.app.container
        today = container.clock.today()
        self.title_text.value = f"{calendar.month_name[self.month]} {self.year}"

        first_weekday = 0 if container.settings_service.week_start == "monday" else 6
        month_calendar = calendar.Calendar(firstweekday=first_weekday)
        weeks = month_calendar.monthdatescalendar(self.year, self.month)

        first = weeks[0][0]
        last = weeks[-1][-1]
        stamps_by_date: dict[date, list[BoardStamp]] = {}
        for stamp in container.placements.board_for_range(first, last):
            stamps_by_date.setdefault(stamp.placement.board_date, []).append(stamp)

        header_labels = [
            WEEKDAY_SHORT[(first_weekday + offset) % 7] for offset in range(7)
        ]
        rows: list[ft.Control] = [
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text(label, size=11, color=MUTED_TEXT),
                        expand=True,
                        alignment=ft.alignment.center,
                    )
                    for label in header_labels
                ]
            )
        ]
        for week in weeks:
            cells = [
                self._day_cell(day, today, stamps_by_date.get(day, []))
                for day in week
            ]
            rows.append(ft.Row(cells, expand=True, spacing=6))
        self.grid_host.content = ft.Column(rows, expand=True, spacing=6)
        self.page.update()

    def _day_cell(
        self, day: date, today: date, stamps: list[BoardStamp]
    ) -> ft.Container:
        in_month = day.month == self.month
        is_future = day > today
        is_today = day == today

        children: list[ft.Control] = [
            ft.Row(
                [
                    ft.Text(
                        str(day.day),
                        size=12,
                        weight=ft.FontWeight.W_600 if is_today else None,
                        color="#3A3F44" if in_month and not is_future else "#B9B7B0",
                    ),
                    ft.Container(expand=True),
                    ft.Text(
                        str(len(stamps)) if stamps else "",
                        size=11,
                        color=MUTED_TEXT,
                    ),
                ]
            )
        ]
        if stamps:
            previews = [
                ft.Image(
                    src="/" + stamp.image_relative_path,
                    width=26,
                    height=20,
                    fit=ft.ImageFit.CONTAIN,
                )
                for stamp in stamps[:_MAX_PREVIEWS]
            ]
            children.append(ft.Row(previews, spacing=2))
            children.append(
                ft.Container(height=3, bgcolor="#7C8B74", border_radius=2, width=24)
            )
        return ft.Container(
            content=ft.Column(children, spacing=4),
            expand=True,
            padding=8,
            bgcolor="#FFFFFF" if in_month else "#F7F6F2",
            border=ft.border.all(2 if is_today else 1, "#7C8B74" if is_today else BORDER_COLOR),
            border_radius=8,
            opacity=0.55 if is_future else 1.0,
            on_click=(lambda _, d=day: self.app.open_history_board(d)) if not is_future else None,
            ink=not is_future,
        )


def open_history_board_dialog(app, day: date) -> None:
    """Read-only reproduction of a saved board (same renderer as Today)."""
    container = app.container
    stamps = container.board_service.load_board(day)
    board_w, board_h = 640.0, 360.0
    is_today = day == container.clock.today()
    board = build_board(
        stamps,
        board_w,
        board_h,
        container.settings_service.board_background_color,
        on_stamp_click=lambda s: show_stamp_details(
            app, s, on_undone=(lambda: app.refresh_current()) if is_today else None
        ),
        empty_hint="No stamps on this day.",
    )
    dialog = ft.AlertDialog(
        title=ft.Text(day.strftime("%A, %d %B %Y")),
        content=ft.Container(content=board, width=board_w, height=board_h),
    )
    dialog.actions = [ft.TextButton("Close", on_click=lambda _: app.page.close(dialog))]
    app.page.open(dialog)
