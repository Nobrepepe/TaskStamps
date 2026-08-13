"""Task and library lifecycle: archive, readiness, world safety."""

from __future__ import annotations

import pytest

from task_stamps.domain.enums import AssignmentEndReason, CharacterStatus, TaskStatus
from task_stamps.domain.exceptions import CharacterEditError, WorldArchiveError
from tests.helpers import EVERY_DAY, make_character, make_task, make_world


def test_archiving_task_releases_character(container, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Freed", source_files)
    task = make_task(container)
    container.task_service.archive(task.id)

    assert container.tasks.get(task.id).status == TaskStatus.ARCHIVED
    assert container.assignments.active_for_character(character.id) is None
    history = container.assignments.history_for_task(task.id)
    assert history[0].end_reason == AssignmentEndReason.ARCHIVED


def test_archiving_preserves_completion_history(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Historian", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.completion_service.complete_task(task.id)
    container.task_service.archive(task.id)

    completions = container.completions.list_for_task(task.id)
    assert len(completions) == 1
    assert container.board_service.stamp_count(clock.today()) == 1


def test_readiness_recomputed_on_edits(container, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Almost", source_files, stamp_count=14)
    assert character.status == CharacterStatus.DRAFT
    from task_stamps.utilities.placeholder_art import render_stamp_png

    final_stamp = source_files / "final.png"
    render_stamp_png(final_stamp, 15, (100, 120, 140), width=32, height=24)
    container.library_service.import_stamp_image(character.id, 15, final_stamp)
    assert container.characters.get(character.id).status == CharacterStatus.READY


def test_clearing_stamp_blocked_while_assigned(container, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Busy", source_files)
    make_task(container)
    with pytest.raises(CharacterEditError):
        container.library_service.clear_stamp_image(character.id, 3)
    # Still ready, assignment untouched.
    assert container.characters.get(character.id).status == CharacterStatus.READY
    assert container.assignments.active_for_character(character.id) is not None


def test_world_archive_requires_confirmation_and_reassigns(container, source_files):
    world_a = make_world(container, "A")
    world_b = make_world(container, "B")
    make_character(container, world_a.id, "Leaving", source_files)
    fallback = make_character(container, world_b.id, "Fallback", source_files)
    from task_stamps.domain.enums import PoolType

    task = make_task(
        container, pool_type=PoolType.SPECIFIC_WORLD, world_id=world_a.id
    )
    # Widen the pool afterwards so the replacement draw can reach world B.
    container.task_service.update_task(task.id, pool_type=PoolType.ALL_WORLDS)

    with pytest.raises(WorldArchiveError):
        container.library_service.archive_world(world_a.id)

    container.library_service.archive_world(world_a.id, confirmed=True)
    replacement = container.assignments.active_for_task(task.id)
    assert replacement is not None
    assert replacement.character_id == fallback.id


def test_archiving_character_with_no_replacement_leaves_task_draft(
    container, source_files
):
    world = make_world(container)
    character = make_character(container, world.id, "OnlyOne", source_files)
    task = make_task(container)
    container.library_service.archive_character(character.id, confirmed=True)

    assert container.tasks.get(task.id).status == TaskStatus.DRAFT
    assert container.assignments.active_for_task(task.id) is None
    ended = container.assignments.history_for_task(task.id)[0]
    assert ended.end_reason == AssignmentEndReason.CHARACTER_UNAVAILABLE
