"""Reusable dark-archive interface controls."""

from __future__ import annotations

from typing import Callable

import flet as ft

from task_stamps.components.theme import (
    BAD,
    BG,
    FAINT,
    GLOW_TEAL,
    MUTED_2,
    SANS,
    TEXT,
    dialog_action,
    eyebrow,
    style_dialog,
)
from task_stamps.domain.enums import STAMPS_PER_CHARACTER

PORTRAIT_RATIO = 3 / 4
STAMP_RATIO = 4 / 3
BOSS_RATIO = 16 / 9


def bleeding_image(
    src: str | None,
    width: float | None,
    ratio: float,
    *,
    glow: bool = True,
    radius_stops: tuple[float, float] = (0.48, 1.0),
) -> ft.Control:
    height = width / ratio if width is not None else None
    if src:
        art: ft.Control = ft.Image(
            src=src,
            width=width,
            height=height,
            expand=width is None,
            fit=ft.ImageFit.CONTAIN,
        )
    else:
        art = ft.Container(
            width=width,
            height=height,
            expand=width is None,
            image=ft.DecorationImage(
                src="/ui/hatch.png",
                repeat=ft.ImageRepeat.REPEAT,
            ),
            alignment=ft.alignment.center,
            content=ft.Text(
                "NO ART",
                size=11,
                color=FAINT,
                font_family=SANS,
                style=ft.TextStyle(letter_spacing=1.6),
            ),
        )
    masked = ft.ShaderMask(
        content=art,
        width=width,
        height=height,
        expand=width is None,
        shader=ft.RadialGradient(
            center=ft.alignment.Alignment(0, -0.1),
            radius=1.0,
            colors=["#FF000000", "#00000000"],
            stops=list(radius_stops),
        ),
        blend_mode=ft.BlendMode.DST_IN,
    )
    layers: list[ft.Control] = []
    if glow:
        layers.append(
            ft.Container(
                width=width,
                height=height,
                expand=width is None,
                gradient=ft.RadialGradient(
                    center=ft.alignment.Alignment(0, -0.1),
                    radius=0.6,
                    colors=[GLOW_TEAL, "#0012100f"],
                ),
            )
        )
    layers.append(masked)
    return ft.Stack(layers, width=width, height=height, expand=width is None)


def portrait_image(src: str | None, width: float | None = 96) -> ft.Control:
    return bleeding_image(src, width, PORTRAIT_RATIO)


def stamp_image(src: str | None, width: float = 96) -> ft.Control:
    return bleeding_image(src, width, STAMP_RATIO, glow=False)


def progress_run(used: set[int], next_number: int | None) -> ft.Row:
    controls: list[ft.Control] = []
    for number in range(1, STAMPS_PER_CHARACTER + 1):
        color = TEXT if number in used else "#6Bf4ece1" if number == next_number else "#24f4ece1"
        controls.append(ft.Container(width=7, height=2, bgcolor=color))
    return ft.Row(controls, spacing=3)


def section_title(text: str) -> ft.Text:
    return eyebrow(text)


def confirm_dialog(
    page: ft.Page,
    title: str,
    message: str,
    on_confirm: Callable[[], None],
    confirm_label: str = "Confirm",
) -> None:
    dialog = style_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message, color=MUTED_2, font_family=SANS),
        )
    )
    app = getattr(page, "data", None)

    def close(_=None) -> None:
        app.close_dialog(dialog) if app and hasattr(app, "close_dialog") else page.close(dialog)

    def confirm(_=None) -> None:
        app.close_dialog(dialog) if app and hasattr(app, "close_dialog") else page.close(dialog)
        on_confirm()

    destructive = confirm_label.lower().startswith(("archive", "remove", "reset"))
    dialog.actions = [
        dialog_action("Cancel", close),
        dialog_action(confirm_label, confirm, destructive=destructive),
    ]
    app.open_dialog(dialog) if app and hasattr(app, "open_dialog") else page.open(dialog)
