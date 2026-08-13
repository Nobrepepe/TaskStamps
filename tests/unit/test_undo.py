"""The undo system, including the stamp-15 special case."""

from __future__ import annotations

import pytest

from task_stamps.domain.enums import STAMPS_PER_CHARACTER
from task_stamps.domain.exceptions import UndoNotAllowedError
from tests.helpers import EVERY_DAY, complete_n_times, make_character, make_task, make_world


@pytest.fixture
def world(container):
    return make_world(container)


def test_undo_restores_prior_streak(container, clock, world, source_files):
    make_character(container, world.id, "Alpha", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    complete_n_times(container, clock, task.id, 4)

    assignment = container.assignments.active_for_task(task.id)
    assert assignment.current_streak == 4
    last = container.completions.list_for_task(task.id)[0]
    container.completion_service.undo_completion(last.id)

    assignment = container.assignments.active_for_task(task.id)
    assert assignment.current_streak == 3
    assert container.completions.get(last.id).is_reversed
    assert container.placements.get_for_completion(last.id) is None
    # Same character stays assigned.
    assert assignment.character_id == container.completions.get(last.id).character_id


def test_undo_makes_task_available_again_today(container, clock, world, source_files):
    make_character(container, world.id, "Alpha", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    result = container.completion_service.complete_task(task.id)
    assert not container.completion_service.available_tasks_today()

    container.completion_service.undo_completion(result.completion.id)
    available = container.completion_service.available_tasks_today()
    assert [item.task.id for item in available] == [task.id]

    redo = container.completion_service.complete_task(task.id)
    assert redo.completion.streak_number == 1


def test_undo_stamp_15_restores_prior_assignment_at_14(
    container, clock, world, source_files
):
    make_character(container, world.id, "Alpha", source_files)
    make_character(container, world.id, "Beta", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    original = container.assignments.active_for_task(task.id)

    final = complete_n_times(container, clock, task.id, STAMPS_PER_CHARACTER)[-1]
    assert final.new_assignment is not None

    container.completion_service.undo_completion(final.completion.id)

    restored = container.assignments.active_for_task(task.id)
    assert restored.id == original.id
    assert restored.character_id == original.character_id
    assert restored.is_active
    assert restored.current_streak == 14
    # The replacement assignment is gone entirely.
    with pytest.raises(KeyError):
        container.assignments.get(final.new_assignment.id)
    # And the previous character's reservation is active again.
    holder = container.assignments.active_for_character(original.character_id)
    assert holder.id == original.id


def test_undo_stamp_15_restores_task_from_draft(container, clock, world, source_files):
    solo = make_character(container, world.id, "Solo", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    complete_n_times(container, clock, task.id, STAMPS_PER_CHARACTER - 1)
    clock.advance_days(1)
    container.characters.set_archived(solo.id, True)
    final = container.completion_service.complete_task(task.id)
    assert container.tasks.get(task.id).status.value == "draft"

    container.completion_service.undo_completion(final.completion.id)
    assert container.tasks.get(task.id).status.value == "active"
    assert container.assignments.active_for_task(task.id).current_streak == 14


def test_undo_rejected_after_the_day_ends(container, clock, world, source_files):
    make_character(container, world.id, "Alpha", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    result = container.completion_service.complete_task(task.id)
    clock.advance_days(1)
    with pytest.raises(UndoNotAllowedError):
        container.completion_service.undo_completion(result.completion.id)


def test_undo_never_leaves_orphaned_active_assignments(
    container, clock, world, source_files
):
    make_character(container, world.id, "Alpha", source_files)
    make_character(container, world.id, "Beta", source_files)
    task = make_task(container, weekdays=EVERY_DAY)

    # Regular undo, redo, then a full rollover and a stamp-15 undo.
    first = container.completion_service.complete_task(task.id)
    container.completion_service.undo_completion(first.completion.id)
    complete_n_times(container, clock, task.id, STAMPS_PER_CHARACTER)
    last = container.completions.list_for_task(task.id)[0]
    container.completion_service.undo_completion(last.id)

    rows = container.db.query_all(
        "SELECT task_id, COUNT(*) AS n FROM character_assignments "
        "WHERE is_active = 1 GROUP BY task_id HAVING n > 1"
    )
    assert rows == []
    rows = container.db.query_all(
        "SELECT character_id, COUNT(*) AS n FROM character_assignments "
        "WHERE is_active = 1 GROUP BY character_id HAVING n > 1"
    )
    assert rows == []
    active = container.assignments.active_for_task(task.id)
    assert active is not None and active.current_streak == 14
