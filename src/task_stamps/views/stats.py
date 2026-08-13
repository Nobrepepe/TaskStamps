"""Completion history and progress insights."""

from __future__ import annotations

import flet as ft

from task_stamps.components.common import BORDER_COLOR, MUTED_TEXT, card, section_title
from task_stamps.domain.enums import WEEKDAY_SHORT
from task_stamps.services.stats_service import RankedItem, StatsSnapshot
from task_stamps.views.base import View

ACCENT = "#7C8B74"
PALE_ACCENT = "#DDE3D9"


class StatsView(View):
    def build(self) -> ft.Control:
        self.days = 30
        self.range_picker = ft.Dropdown(
            value="30",
            width=150,
            text_size=13,
            options=[
                ft.dropdown.Option("14", "Last 14 days"),
                ft.dropdown.Option("30", "Last 30 days"),
                ft.dropdown.Option("90", "Last 90 days"),
                ft.dropdown.Option("365", "Last year"),
            ],
            on_change=self._change_range,
        )
        header = ft.Container(
            padding=ft.padding.only(left=24, right=24, top=18, bottom=10),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("Stats", size=20, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "See what is sticking and where your momentum grows.",
                                size=13,
                                color=MUTED_TEXT,
                            ),
                        ],
                        spacing=2,
                    ),
                    ft.Container(expand=True),
                    self.range_picker,
                ]
            ),
        )
        self.content = ft.Column(
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        return ft.Column(
            [
                header,
                ft.Container(
                    self.content,
                    expand=True,
                    padding=ft.padding.only(left=24, right=24, bottom=24),
                ),
            ],
            expand=True,
            spacing=0,
        )

    def _change_range(self, event: ft.ControlEvent) -> None:
        self.days = int(event.control.value)
        self.refresh()

    def refresh(self) -> None:
        snapshot = self.app.container.stats_service.snapshot(self.days)
        if snapshot.total == 0:
            self.content.controls = [self._empty_state(snapshot)]
        else:
            self.content.controls = [
                self._summary(snapshot),
                self._charts(snapshot),
                self._rankings(snapshot),
            ]
        self.page.update()

    def _empty_state(self, snapshot: StatsSnapshot) -> ft.Control:
        return card(
            ft.Container(
                padding=36,
                alignment=ft.alignment.center,
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.INSIGHTS_OUTLINED, size=44, color=ACCENT),
                        ft.Text(
                            "Your patterns will appear here",
                            size=18,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            "Complete tasks and place stamps to reveal weekday "
                            "patterns, consistency, and your strongest habits.",
                            color=MUTED_TEXT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            f"{snapshot.active_task_count} active task"
                            f"{'' if snapshot.active_task_count == 1 else 's'} right now",
                            size=12,
                            color=ACCENT,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10,
                ),
            )
        )

    def _summary(self, data: StatsSnapshot) -> ft.Control:
        rate = round(data.active_days / data.possible_days * 100)
        best = (
            f"{data.best_day[0].strftime('%b %d')} · {data.best_day[1]}"
            if data.best_day
            else "—"
        )
        items = [
            ("Stamps placed", str(data.total), ft.Icons.APPROVAL_OUTLINED),
            ("Active days", f"{data.active_days} · {rate}%", ft.Icons.EVENT_AVAILABLE),
            ("Current daily run", f"{data.current_run} days", ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED),
            ("Best day", best, ft.Icons.EMOJI_EVENTS_OUTLINED),
            ("Points earned", str(data.points), ft.Icons.STARS_OUTLINED),
        ]
        return ft.ResponsiveRow(
            [
                ft.Container(
                    col={"xs": 12, "sm": 6, "md": 2.4},
                    content=card(
                        ft.Column(
                            [
                                ft.Icon(icon, color=ACCENT, size=20),
                                ft.Text(value, size=21, weight=ft.FontWeight.W_600),
                                ft.Text(label, size=11, color=MUTED_TEXT),
                            ],
                            spacing=3,
                        )
                    ),
                )
                for label, value, icon in items
            ],
            spacing=10,
            run_spacing=10,
        )

    def _charts(self, data: StatsSnapshot) -> ft.Control:
        trend = data.daily[-min(14, len(data.daily)) :]
        return ft.ResponsiveRow(
            [
                ft.Container(
                    col={"xs": 12, "lg": 7},
                    content=self._chart_card(
                        "Recent activity",
                        "Tasks completed each day",
                        self._bars(
                            [count for _, count in trend],
                            [day.strftime("%d") for day, _ in trend],
                            [day.strftime("%a, %b %d") for day, _ in trend],
                        ),
                    ),
                ),
                ft.Container(
                    col={"xs": 12, "lg": 5},
                    content=self._chart_card(
                        "Weekday pattern",
                        "Total tasks completed by day of week",
                        self._bars(
                            list(data.weekdays),
                            list(WEEKDAY_SHORT),
                            [
                                f"{name}: {count} task{'s' if count != 1 else ''}"
                                for name, count in zip(WEEKDAY_SHORT, data.weekdays)
                            ],
                        ),
                    ),
                ),
            ],
            spacing=12,
            run_spacing=12,
        )

    def _chart_card(self, title: str, subtitle: str, graph: ft.Control) -> ft.Control:
        return card(
            ft.Column(
                [
                    ft.Text(title, size=15, weight=ft.FontWeight.W_600),
                    ft.Text(subtitle, size=11, color=MUTED_TEXT),
                    ft.Container(height=8),
                    graph,
                ],
                spacing=2,
            ),
            padding=16,
        )

    def _bars(
        self, values: list[int], labels: list[str], tooltips: list[str]
    ) -> ft.Control:
        maximum = max(values, default=0) or 1
        bars: list[ft.Control] = []
        for value, label, tooltip in zip(values, labels, tooltips):
            height = 8 if value == 0 else max(16, round(112 * value / maximum))
            bars.append(
                ft.Container(
                    expand=True,
                    content=ft.Column(
                        [
                            ft.Text(
                                str(value),
                                size=10,
                                color=MUTED_TEXT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Container(
                                height=height,
                                bgcolor=ACCENT if value else PALE_ACCENT,
                                border_radius=ft.border_radius.only(
                                    top_left=5, top_right=5
                                ),
                                tooltip=tooltip,
                            ),
                            ft.Text(
                                label,
                                size=9,
                                color=MUTED_TEXT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        spacing=4,
                    ),
                )
            )
        return ft.Container(
            height=154,
            content=ft.Row(
                bars,
                spacing=5,
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
        )

    def _rankings(self, data: StatsSnapshot) -> ft.Control:
        return ft.Column(
            [
                section_title("WHAT IS WORKING"),
                ft.ResponsiveRow(
                    [
                        ft.Container(
                            col={"xs": 12, "md": 4},
                            content=self._ranking_card(
                                "Most consistent tasks",
                                "Completions",
                                data.tasks,
                                ft.Icons.CHECK_CIRCLE_OUTLINE,
                            ),
                        ),
                        ft.Container(
                            col={"xs": 12, "md": 4},
                            content=self._ranking_card(
                                "Character progress",
                                "Stamps collected",
                                data.characters,
                                ft.Icons.PERSON_OUTLINE,
                            ),
                        ),
                        ft.Container(
                            col={"xs": 12, "md": 4},
                            content=self._ranking_card(
                                "Most explored worlds",
                                "Stamps collected",
                                data.worlds,
                                ft.Icons.PUBLIC_OUTLINED,
                            ),
                        ),
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
            ],
            spacing=8,
        )

    def _ranking_card(
        self,
        title: str,
        unit: str,
        items: tuple[RankedItem, ...],
        icon: str,
    ) -> ft.Control:
        maximum = items[0].count if items else 1
        rows: list[ft.Control] = []
        for index, item in enumerate(items[:5], start=1):
            rows.append(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(f"{index}.", width=18, color=MUTED_TEXT, size=11),
                                ft.Text(item.name, expand=True, size=12),
                                ft.Text(str(item.count), size=12, weight=ft.FontWeight.W_600),
                            ],
                            spacing=5,
                        ),
                        ft.ProgressBar(
                            value=item.count / maximum,
                            color=ACCENT,
                            bgcolor=PALE_ACCENT,
                            height=4,
                        ),
                    ],
                    spacing=4,
                )
            )
        return card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, size=19, color=ACCENT),
                            ft.Column(
                                [
                                    ft.Text(title, size=14, weight=ft.FontWeight.W_600),
                                    ft.Text(unit, size=10, color=MUTED_TEXT),
                                ],
                                spacing=0,
                                expand=True,
                            ),
                        ]
                    ),
                    ft.Divider(height=10, color=BORDER_COLOR),
                    *rows,
                ],
                spacing=10,
            ),
            padding=16,
        )
