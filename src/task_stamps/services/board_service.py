"""Daily board loading and normalized stamp placement.

The board is a fixed 16:9 canvas addressed with normalized 0..1 coordinates,
so a saved layout reproduces identically at any window size. Placements are
generated once, saved, and never regenerated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from task_stamps.data.repositories.placements import PlacementRepository
from task_stamps.domain.models import BoardStamp, StampPlacement
from task_stamps.utilities.rng import RandomProvider

BOARD_ASPECT: float = 16 / 9
STAMP_ASPECT: float = 4 / 3  # landscape artwork, width : height
STAMP_BASE_WIDTH: float = 0.16  # fraction of board width at scale 1.0
SCALE_MIN, SCALE_MAX = 0.85, 1.15
ROTATION_MAX_DEGREES: float = 10.0
EDGE_MARGIN: float = 0.01
CANDIDATE_COUNT: int = 14


@dataclass(frozen=True)
class PlacementGeometry:
    x: float
    y: float
    rotation_degrees: float
    scale: float


@dataclass(frozen=True)
class PixelRect:
    left: float
    top: float
    width: float
    height: float


def stamp_extents(scale: float, rotation_degrees: float) -> tuple[float, float]:
    """Half-width and half-height of the rotated stamp's bounding box.

    Returned in normalized board units (x relative to board width, y relative
    to board height). The physical stamp is ``width x width/STAMP_ASPECT``.
    """
    width = STAMP_BASE_WIDTH * scale  # normalized x units
    physical_height_x = width / STAMP_ASPECT  # physical height, in x units
    height = physical_height_x * BOARD_ASPECT  # same height, in y units
    theta = math.radians(abs(rotation_degrees))
    bounding_w = width * math.cos(theta) + physical_height_x * math.sin(theta)
    bounding_h = height * math.cos(theta) + width * BOARD_ASPECT * math.sin(theta)
    return bounding_w / 2, bounding_h / 2


class BoardService:
    def __init__(self, placements: PlacementRepository, rng: RandomProvider) -> None:
        self.placements = placements
        self.rng = rng

    # -- reading (never mutates) ---------------------------------------

    def load_board(self, board_date: date) -> list[BoardStamp]:
        return self.placements.board_for_date(board_date)

    def stamp_count(self, board_date: date) -> int:
        return self.placements.count_for_date(board_date)

    # -- placement generation -------------------------------------------

    def generate_geometry(self, existing: list[StampPlacement]) -> PlacementGeometry:
        """Try several candidate positions and keep the least overlapping
        one; overlap is allowed once the board gets crowded."""
        scale = self.rng.uniform(SCALE_MIN, SCALE_MAX)
        rotation = self.rng.uniform(-ROTATION_MAX_DEGREES, ROTATION_MAX_DEGREES)
        half_w, half_h = stamp_extents(scale, rotation)
        x_low, x_high = half_w + EDGE_MARGIN, 1 - half_w - EDGE_MARGIN
        y_low, y_high = half_h + EDGE_MARGIN, 1 - half_h - EDGE_MARGIN

        best: tuple[float, float, float] | None = None
        for _ in range(CANDIDATE_COUNT):
            x = self.rng.uniform(x_low, x_high)
            y = self.rng.uniform(y_low, y_high)
            overlap = self._overlap_score(x, y, half_w, half_h, existing)
            if best is None or overlap < best[0]:
                best = (overlap, x, y)
            if overlap == 0.0:
                break
        assert best is not None
        return PlacementGeometry(x=best[1], y=best[2], rotation_degrees=rotation, scale=scale)

    @staticmethod
    def _overlap_score(
        x: float,
        y: float,
        half_w: float,
        half_h: float,
        existing: list[StampPlacement],
    ) -> float:
        total = 0.0
        for other in existing:
            other_hw, other_hh = stamp_extents(other.scale, other.rotation_degrees)
            dx = min(x + half_w, other.x_normalized + other_hw) - max(
                x - half_w, other.x_normalized - other_hw
            )
            dy = min(y + half_h, other.y_normalized + other_hh) - max(
                y - half_h, other.y_normalized - other_hh
            )
            if dx > 0 and dy > 0:
                total += dx * dy
        return total

    def create_placement(
        self,
        *,
        completion_id: str,
        board_date: date,
        image_asset_version_id: str,
        sound_asset_version_id: str | None,
    ) -> StampPlacement:
        existing = self.placements.list_for_date(board_date)
        geometry = self.generate_geometry(existing)
        return self.placements.create(
            completion_id=completion_id,
            board_date=board_date,
            x_normalized=geometry.x,
            y_normalized=geometry.y,
            rotation_degrees=geometry.rotation_degrees,
            scale=geometry.scale,
            z_index=len(existing) + 1,
            image_asset_version_id=image_asset_version_id,
            sound_asset_version_id=sound_asset_version_id,
        )

    # -- projection to pixels --------------------------------------------

    @staticmethod
    def board_size_for(available_w: float, available_h: float) -> tuple[float, float]:
        """Largest 16:9 rectangle fitting the available area."""
        width = min(available_w, available_h * BOARD_ASPECT)
        return width, width / BOARD_ASPECT

    @staticmethod
    def project(placement: StampPlacement, board_w: float, board_h: float) -> PixelRect:
        width = STAMP_BASE_WIDTH * placement.scale * board_w
        height = width / STAMP_ASPECT
        return PixelRect(
            left=placement.x_normalized * board_w - width / 2,
            top=placement.y_normalized * board_h - height / 2,
            width=width,
            height=height,
        )
