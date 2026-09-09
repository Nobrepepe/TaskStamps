"""Shared daily-board renderer used by Today and the calendar history view.

Renders saved placements exactly as stored — placements are never mutated
or regenerated here.
"""

from __future__ import annotations

import math
from typing import Callable

import flet as ft

from task_stamps.components.theme import BOARD_FLOOR, LINE_INPUT, MUTED
from task_stamps.domain.models import BoardStamp
from task_stamps.services.board_service import BoardService


def stamp_control(
    stamp: BoardStamp,
    board_w: float,
    board_h: float,
    on_click: Callable[[BoardStamp], None] | None,
) -> ft.Container:
    rect = BoardService.project(stamp.placement, board_w, board_h)
    image = ft.Image(
        src="/" + stamp.image_relative_path,
        width=rect.width,
        height=rect.height,
        fit=ft.ImageFit.CONTAIN,
    )
    return ft.Container(
        content=image,
        left=rect.left,
        top=rect.top,
        width=rect.width,
        height=rect.height,
        rotate=ft.Rotate(math.radians(stamp.placement.rotation_degrees)),
        on_click=(lambda _, s=stamp: on_click(s)) if on_click else None,
        tooltip=f"{stamp.character_name_snapshot} — stamp {stamp.streak_number}",
    )


def build_board(
    stamps: list[BoardStamp],
    board_w: float,
    board_h: float,
    background_color: str,
    on_stamp_click: Callable[[BoardStamp], None] | None = None,
    on_board_click: Callable[[], None] | None = None,
    empty_hint: str | None = None,
) -> ft.Container:
    horizontal = ft.LinearGradient(
        begin=ft.alignment.center_left,
        end=ft.alignment.center_right,
        colors=["#00f4ece1", LINE_INPUT, LINE_INPUT, "#00f4ece1"],
        stops=[0, 0.13, 0.87, 1],
    )
    vertical = ft.LinearGradient(
        begin=ft.alignment.top_center,
        end=ft.alignment.bottom_center,
        colors=["#00f4ece1", LINE_INPUT, LINE_INPUT, "#00f4ece1"],
        stops=[0, 0.13, 0.87, 1],
    )
    children: list[ft.Control] = [
        ft.Container(left=0, top=0, width=board_w, height=1, gradient=horizontal),
        ft.Container(left=0, bottom=0, width=board_w, height=1, gradient=horizontal),
        ft.Container(left=0, top=0, width=1, height=board_h, gradient=vertical),
        ft.Container(right=0, top=0, width=1, height=board_h, gradient=vertical),
    ]
    if not stamps and empty_hint:
        children.append(
            ft.Container(
                content=ft.Text(empty_hint, color=MUTED, size=14),
                alignment=ft.alignment.center,
                left=0,
                top=0,
                width=board_w,
                height=board_h,
            )
        )
    for stamp in stamps:  # already ordered by z-index
        children.append(stamp_control(stamp, board_w, board_h, on_stamp_click))
    return ft.Container(
        content=ft.Stack(children, width=board_w, height=board_h),
        width=board_w,
        height=board_h,
        bgcolor=background_color or BOARD_FLOOR,
        shadow=ft.BoxShadow(
            blur_radius=26, color="#8C000000", blur_style=ft.ShadowBlurStyle.INNER
        ),
        on_click=(lambda _: on_board_click()) if on_board_click else None,
    )
