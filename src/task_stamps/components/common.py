"""Small reusable interface pieces. Deliberately neutral and quiet so the
imported character artwork stays the visual focus."""

from __future__ import annotations

from typing import Callable

import flet as ft

from task_stamps.domain.enums import STAMPS_PER_CHARACTER

PORTRAIT_RATIO = 3 / 4  # width : height (portrait, taller than wide)
STAMP_RATIO = 4 / 3  # width : height (landscape, wider than tall)

BORDER_COLOR = "#E2E0DB"
MUTED_TEXT = "#8A8880"
CARD_BG = "#FFFFFF"


def framed_image(
    src: str | None,
    width: float | None,
    ratio: float,
    *,
    icon: str = ft.Icons.IMAGE_OUTLINED,
    radius: int = 8,
) -> ft.Container:
    """Aspect-ratio image container. With an explicit width it is fixed size
    and never stretches; with width=None it instead expands to fill
    whatever space its parent gives it (e.g. inside a grid cell)."""
    content: ft.Control
    if width is None:
        content = (
            ft.Image(src=src, expand=True, fit=ft.ImageFit.CONTAIN)
            if src
            else ft.Icon(icon, size=40, color=MUTED_TEXT)
        )
        return ft.Container(
            content=content,
            expand=True,
            alignment=ft.alignment.center,
            bgcolor="#F5F4F0",
            border=ft.border.all(1, BORDER_COLOR),
            border_radius=radius,
        )
    height = width / ratio
    if src:
        content = ft.Image(
            src=src, width=width, height=height, fit=ft.ImageFit.CONTAIN
        )
    else:
        content = ft.Icon(icon, size=min(width, height) * 0.4, color=MUTED_TEXT)
    return ft.Container(
        content=content,
        width=width,
        height=height,
        alignment=ft.alignment.center,
        bgcolor="#F5F4F0",
        border=ft.border.all(1, BORDER_COLOR),
        border_radius=radius,
    )


def portrait_image(src: str | None, width: float | None = 96) -> ft.Container:
    return framed_image(src, width, PORTRAIT_RATIO, icon=ft.Icons.PERSON_OUTLINED)


def stamp_image(src: str | None, width: float = 96) -> ft.Container:
    return framed_image(src, width, STAMP_RATIO)


def progress_dots(
    used: set[int], next_number: int | None, size: float = 14
) -> ft.Row:
    """Fifteen-step progress: used stamps filled, next highlighted, rest faint."""
    dots: list[ft.Control] = []
    for number in range(1, STAMPS_PER_CHARACTER + 1):
        if number in used:
            color, border = "#7C8B74", None
        elif number == next_number:
            color, border = "#FFFFFF", ft.border.all(2, "#7C8B74")
        else:
            color, border = "#EDECE7", ft.border.all(1, BORDER_COLOR)
        dots.append(
            ft.Container(
                width=size,
                height=size,
                bgcolor=color,
                border=border,
                border_radius=size / 2,
                tooltip=f"Stamp {number}",
            )
        )
    return ft.Row(dots, spacing=4, wrap=True)


def status_chip(text: str, color: str = "#8A8880") -> ft.Container:
    return ft.Container(
        content=ft.Text(text, size=11, color="#FFFFFF", weight=ft.FontWeight.W_500),
        bgcolor=color,
        padding=ft.padding.symmetric(horizontal=8, vertical=2),
        border_radius=10,
    )


STATUS_COLORS = {
    "draft": "#A8A6A0",
    "active": "#7C8B74",
    "paused": "#C2A36B",
    "archived": "#8A8880",
    "ready": "#7C8B74",
}


def card(content: ft.Control, padding: int = 14, on_click=None) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=CARD_BG,
        border=ft.border.all(1, BORDER_COLOR),
        border_radius=10,
        padding=padding,
        on_click=on_click,
        ink=on_click is not None,
    )


def section_title(text: str) -> ft.Text:
    return ft.Text(text, size=13, weight=ft.FontWeight.W_600, color=MUTED_TEXT)


def confirm_dialog(
    page: ft.Page,
    title: str,
    message: str,
    on_confirm: Callable[[], None],
    confirm_label: str = "Confirm",
) -> None:
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Text(message),
    )

    def close(_=None) -> None:
        page.close(dialog)

    def confirm(_=None) -> None:
        page.close(dialog)
        on_confirm()

    dialog.actions = [
        ft.TextButton("Cancel", on_click=close),
        ft.FilledButton(confirm_label, on_click=confirm),
    ]
    page.open(dialog)
