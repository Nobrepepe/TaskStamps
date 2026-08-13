"""Board placement: persistence, bounds, resize independence."""

from __future__ import annotations

from task_stamps.container import build_container
from task_stamps.services.board_service import BoardService, stamp_extents
from task_stamps.utilities.clock import FixedClock
from task_stamps.utilities.rng import SeededRandomProvider
from tests.helpers import EVERY_DAY, complete_n_times, make_character, make_task, make_world


def test_historical_placement_is_not_regenerated(
    container, data_dir, clock, source_files
):
    world = make_world(container)
    make_character(container, world.id, "Alpha", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    result = container.completion_service.complete_task(task.id)
    saved = result.placement
    board_date = saved.board_date

    def snapshot(placement):
        return (
            placement.x_normalized,
            placement.y_normalized,
            placement.rotation_degrees,
            placement.scale,
            placement.z_index,
            placement.image_asset_version_id,
        )

    first_load = container.board_service.load_board(board_date)
    second_load = container.board_service.load_board(board_date)
    assert snapshot(first_load[0].placement) == snapshot(saved)
    assert snapshot(second_load[0].placement) == snapshot(saved)

    container.close()
    reopened = build_container(
        data_dir=data_dir, clock=clock, rng=SeededRandomProvider(777)
    )
    try:
        after_restart = reopened.board_service.load_board(board_date)
        assert snapshot(after_restart[0].placement) == snapshot(saved)
    finally:
        reopened.close()


def test_random_placement_stays_inside_board_bounds(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Alpha", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    complete_n_times(container, clock, task.id, 14)  # a crowded fortnight

    rows = container.db.query_all("SELECT * FROM stamp_placements")
    assert len(rows) == 14
    for row in rows:
        half_w, half_h = stamp_extents(row["scale"], row["rotation_degrees"])
        assert row["x_normalized"] - half_w >= 0
        assert row["x_normalized"] + half_w <= 1
        assert row["y_normalized"] - half_h >= 0
        assert row["y_normalized"] + half_h <= 1


def test_generated_geometry_bounds_hold_under_pressure():
    """Direct fuzz of the generator with an accumulating crowded board."""
    from task_stamps.domain.models import StampPlacement
    from datetime import date, datetime

    rng = SeededRandomProvider(7)

    class _FakeRepo:  # generator only needs list context via BoardService API
        pass

    service = BoardService(placements=None, rng=rng)  # type: ignore[arg-type]
    existing: list[StampPlacement] = []
    for index in range(120):
        geometry = service.generate_geometry(existing)
        half_w, half_h = stamp_extents(geometry.scale, geometry.rotation_degrees)
        assert 0 <= geometry.x - half_w and geometry.x + half_w <= 1
        assert 0 <= geometry.y - half_h and geometry.y + half_h <= 1
        existing.append(
            StampPlacement(
                id=str(index),
                completion_id=str(index),
                board_date=date(2026, 1, 5),
                x_normalized=geometry.x,
                y_normalized=geometry.y,
                rotation_degrees=geometry.rotation_degrees,
                scale=geometry.scale,
                z_index=index + 1,
                image_asset_version_id="v",
                sound_asset_version_id=None,
                created_at=datetime(2026, 1, 5, 9, 0),
            )
        )


def test_placement_coordinates_survive_board_resizing(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Alpha", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    result = container.completion_service.complete_task(task.id)
    placement = result.placement

    small = BoardService.project(placement, 800, 450)
    large = BoardService.project(placement, 1600, 900)
    # Doubling the board doubles every pixel measure: pure projection of the
    # stored normalized coordinates, nothing recalculated.
    assert abs(large.left - 2 * small.left) < 1e-6
    assert abs(large.top - 2 * small.top) < 1e-6
    assert abs(large.width - 2 * small.width) < 1e-6
    assert abs(large.height - 2 * small.height) < 1e-6

    # The stored values themselves are unchanged by projections.
    reloaded = container.placements.get_for_completion(result.completion.id)
    assert reloaded.x_normalized == placement.x_normalized
    assert reloaded.y_normalized == placement.y_normalized
