"""Completion history and progress insights in the dark-archive style."""

from __future__ import annotations

import flet as ft

from task_stamps.components.theme import (
    ACCENT, FAINT, MUTED, MUTED_2, SERIF, TEXT, TEXT_DIM,
    eyebrow, eyebrow_row, hairline,
)
from task_stamps.domain.enums import WEEKDAY_NAMES, WEEKDAY_SHORT
from task_stamps.services.stats_service import RankedItem, StatsSnapshot
from task_stamps.views.base import View


class StatsView(View):
    def build(self) -> ft.Control:
        self.days = 30
        self.range_picker = ft.Dropdown(
            value="30", width=160, border=ft.InputBorder.UNDERLINE,
            options=[ft.dropdown.Option("14", "Last 14 days"), ft.dropdown.Option("30", "Last 30 days"),
                     ft.dropdown.Option("90", "Last 90 days"), ft.dropdown.Option("365", "Last year")],
            on_change=lambda event: self._set_days(event.control.value),
        )
        self.content = ft.Column(spacing=30)
        header = ft.Row([
            ft.Column([eyebrow("Patterns"), ft.Text("Stats", size=48, color=TEXT, font_family=SERIF),
                       ft.Text("See what is sticking and where your momentum grows.", size=15, color=TEXT_DIM)],
                      spacing=10, expand=True),
            self.range_picker,
        ], vertical_alignment=ft.CrossAxisAlignment.END)
        return ft.Container(
            content=ft.Column([header, self.content], spacing=34, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.only(left=56, right=56, top=40, bottom=72), expand=True,
        )

    def _set_days(self, value: str) -> None:
        self.days = int(value)
        self.refresh()

    def refresh(self) -> None:
        snapshot = self.app.container.stats_service.snapshot(self.days)
        self.content.controls = [self._empty(snapshot)] if snapshot.total == 0 else [
            self._summary(snapshot), hairline(), self._charts(snapshot), self._rankings(snapshot)
        ]
        self.page.update()

    def _empty(self, data: StatsSnapshot) -> ft.Control:
        return ft.Column([
            ft.Text("Your patterns will appear here", size=33, color=TEXT, font_family=SERIF),
            ft.Text("Complete tasks and place stamps to reveal weekday patterns, consistency, and your strongest habits.",
                    color=TEXT_DIM, size=15),
            ft.Text(f"{data.active_task_count} active task{'s' if data.active_task_count != 1 else ''} right now.",
                    color=MUTED, size=13),
        ], spacing=10)

    def _summary(self, data: StatsSnapshot) -> ft.Control:
        rate = round(data.active_days / data.possible_days * 100)
        best = f"{data.best_day[0].strftime('%b %d')} · {data.best_day[1]}" if data.best_day else "—"
        items = [("Stamps placed", str(data.total), TEXT), ("Active days", f"{data.active_days} · {rate}%", TEXT),
                 ("Current daily run", f"{data.current_run} days", TEXT), ("Best day", best, TEXT),
                 ("Chests earned", str(data.chests_earned), ACCENT)]
        return ft.ResponsiveRow([
            ft.Container(
                col={"xs": 6, "md": 4, "lg": 2.4},
                content=ft.Column([ft.Text(value, size=42, color=color, font_family=SERIF, no_wrap=True), eyebrow(label)], spacing=4),
            ) for label, value, color in items
        ], spacing=22, run_spacing=24)

    def _charts(self, data: StatsSnapshot) -> ft.Control:
        trend = data.daily[-min(14, len(data.daily)):]
        highest = max(range(7), key=lambda i: data.weekdays[i])
        lowest = min(range(7), key=lambda i: data.weekdays[i])
        return ft.ResponsiveRow([
            ft.Container(col={"xs": 12, "lg": 7}, content=ft.Column([
                eyebrow("Recent activity"), self._bars([n for _, n in trend], [d.strftime("%d") for d, _ in trend])
            ], spacing=14)),
            ft.Container(col={"xs": 12, "lg": 5}, content=ft.Column([
                eyebrow("Weekday pattern"), self._bars(list(data.weekdays), list(WEEKDAY_SHORT)),
                ft.Text(f"{WEEKDAY_NAMES[highest]} carries the most work. {WEEKDAY_NAMES[lowest]} carries the least.",
                        size=13, color=MUTED),
            ], spacing=14)),
        ], spacing=34, run_spacing=34)

    def _bars(self, values: list[int], labels: list[str]) -> ft.Container:
        maximum = max(values, default=0)
        bars = []
        for value, label in zip(values, labels):
            height = 2 if value == 0 else max(12, round(112 * value / max(1, maximum)))
            color = "#80f4ece1" if value == maximum and maximum else "#42f4ece1" if value else "#1Ff4ece1"
            bars.append(ft.Container(expand=True, content=ft.Column([
                ft.Text(str(value), size=11, color=TEXT_DIM if value == maximum else MUTED_2, text_align=ft.TextAlign.CENTER),
                ft.Container(height=height, bgcolor=color),
                ft.Text(label, size=11, color=TEXT_DIM if value == maximum else FAINT, text_align=ft.TextAlign.CENTER),
            ], alignment=ft.MainAxisAlignment.END, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, spacing=5)))
        return ft.Container(height=160, content=ft.Row(bars, spacing=5, vertical_alignment=ft.CrossAxisAlignment.END))

    def _rankings(self, data: StatsSnapshot) -> ft.Control:
        return ft.Column([eyebrow_row("What is working"), ft.ResponsiveRow([
            ft.Container(col={"xs": 12, "md": 4}, content=self._ranking("Most consistent tasks", data.tasks)),
            ft.Container(col={"xs": 12, "md": 4}, content=self._ranking("Character progress", data.characters)),
            ft.Container(col={"xs": 12, "md": 4}, content=self._ranking("Most explored worlds", data.worlds)),
        ], spacing=30, run_spacing=30)], spacing=20)

    def _ranking(self, title: str, items: tuple[RankedItem, ...]) -> ft.Control:
        maximum = items[0].count if items else 1
        rows: list[ft.Control] = [ft.Text(title, size=21, color=TEXT, font_family=SERIF)]
        for index, item in enumerate(items[:5], 1):
            rows.extend([ft.Row([ft.Text(f"{index}.", width=20, color=FAINT, size=12),
                                ft.Text(item.name, expand=True, color=TEXT_DIM, size=13),
                                ft.Text(str(item.count), color=TEXT, size=13)]),
                         ft.Stack([ft.Container(height=2, bgcolor="#1Af4ece1"),
                                   ft.Container(height=2, width=160 * item.count / max(1, maximum), bgcolor="#80f4ece1")])])
        return ft.Column(rows, spacing=9)
