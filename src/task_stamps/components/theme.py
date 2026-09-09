"""Dark-archive visual tokens and structural primitives."""

from __future__ import annotations

import flet as ft

BG = "#12100f"
BG_2 = "#1a1512"
BG_HOVER = "#221b16"
BG_HOVER_ALPHA = "#8C221b16"
BOARD_FLOOR = "#171310"

TEXT = "#f4ece1"
TEXT_DIM = "#b8aca1"
MUTED = "#a2958a"
MUTED_2 = "#8e8278"
FAINT = "#6f645c"

LINE = "#24f4ece1"
LINE_INPUT = "#2Ef4ece1"
ACCENT = "#e9a94f"
ACCENT_2 = "#b48ade"
GOOD = "#6fc9a0"
BAD = "#c9705f"
GLOW_TEAL = "#452DBEC4"

SERIF = "Instrument Serif"
SANS = "Figtree"
SANS_MEDIUM = "Figtree Medium"


def eyebrow(label: str, color: str = MUTED_2) -> ft.Text:
    return ft.Text(
        spans=[
            ft.TextSpan(
                label.upper(),
                style=ft.TextStyle(
                    font_family=SANS_MEDIUM,
                    size=11,
                    color=color,
                    letter_spacing=1.5,
                ),
            )
        ]
    )


def hairline(fade_at: float = 0.9) -> ft.Container:
    return ft.Container(
        height=1,
        gradient=ft.LinearGradient(
            begin=ft.alignment.center_left,
            end=ft.alignment.center_right,
            colors=[LINE, LINE, "#00f4ece1"],
            stops=[0.0, fade_at, 1.0],
        ),
    )


def eyebrow_row(label: str, trailing: ft.Control | None = None) -> ft.Row:
    controls: list[ft.Control] = [eyebrow(label), ft.Container(content=hairline(), expand=True)]
    if trailing is not None:
        controls.append(trailing)
    return ft.Row(controls, spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def text_action(
    label: str,
    on_click,
    *,
    color: str = TEXT,
    size: float = 13.5,
) -> ft.Container:
    return ft.Container(
        content=ft.Text(label, size=size, color=color, font_family=SANS_MEDIUM),
        padding=ft.padding.only(bottom=3),
        border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.35, color))),
        on_click=on_click,
        ink=True,
    )


def dialog_title(text: str) -> ft.Text:
    return ft.Text(text, size=24, color=TEXT, font_family=SERIF)


def dialog_action(label: str, on_click, *, destructive: bool = False) -> ft.TextButton:
    return ft.TextButton(
        label,
        on_click=on_click,
        style=ft.ButtonStyle(color=BAD if destructive else TEXT),
    )


def style_dialog(dialog: ft.AlertDialog) -> ft.AlertDialog:
    dialog.bgcolor = BG_2
    dialog.surface_tint_color = BG_2
    dialog.shadow_color = "#80000000"
    if isinstance(dialog.title, ft.Text):
        dialog.title.font_family = SERIF
        dialog.title.size = dialog.title.size or 24
        dialog.title.color = TEXT
    return dialog
