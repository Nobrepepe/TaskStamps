"""The stamp-15 rollover: completion, release, replacement draw."""

from __future__ import annotations

import pytest

from task_stamps.domain.enums import STAMPS_PER_CHARACTER, AssignmentEndReason
from tests.helpers import EVERY_DAY, complete_n_times, make_character, make_task, make_world


@pytest.fixture
def world(container):
    return make_world(container)


def test_stamp_15_recorded_before_reassignment(container, clock, world, source_files):
    make_character(container, world.id, "Alpha", source_files)
    make_character(container, world.id, "Beta", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    original = container.assignments.active_for_task(task.id)

    results = complete_n_times(container, clock, task.id, STAMPS_PER_CHARACTER)
    final = results[-1]

    assert final.completion.streak_number == 15
    assert final.assignment_completed
    completions = container.completions.list_for_assignment(original.id)
    assert [c.streak_number for c in completions] == list(range(1, 16))
    finished = container.assignments.get(original.id)
    assert finished.end_reason == AssignmentEndReason.COMPLETED
    assert not finished.is_active


def test_stamp_15_releases_old_character(container, clock, world, source_files):
    make_character(container, world.id, "Alpha", source_files)
    make_character(container, world.id, "Beta", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    original = container.assignments.active_for_task(task.id)

    complete_n_times(container, clock, task.id, STAMPS_PER_CHARACTER)

    assert container.assignments.active_for_character(original.character_id) is None


def test_new_character_assigned_after_stamp_15(container, clock, world, source_files):
    make_character(container, world.id, "Alpha", source_files)
    make_character(container, world.id, "Beta", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    original = container.assignments.active_for_task(task.id)

    final = complete_n_times(container, clock, task.id, STAMPS_PER_CHARACTER)[-1]

    assert final.new_assignment is not None
    assert final.new_assignment.is_active
    assert final.new_assignment.current_streak == 0
    replacement = container.assignments.active_for_task(task.id)
    assert replacement.id == final.new_assignment.id
    assert replacement.character_id != original.character_id


def test_previous_character_excluded_when_alternatives_exist(
    container, clock, world, source_files
):
    make_character(container, world.id, "Alpha", source_files)
    make_character(container, world.id, "Beta", source_files)
    make_character(container, world.id, "Gamma", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    original = container.assignments.active_for_task(task.id)

    # Rollover path
    final = complete_n_times(container, clock, task.id, STAMPS_PER_CHARACTER)[-1]
    assert final.new_assignment.character_id != original.character_id

    # Drop path: miss a day, replacement must avoid the dropped character.
    dropped = container.assignments.active_for_task(task.id)
    clock.advance_days(2)
    events = container.schedule_service.evaluate_missed_days()
    assert len(events) == 1
    replacement = container.assignments.active_for_task(task.id)
    assert replacement.character_id != dropped.character_id


def test_previous_character_allowed_when_only_candidate(
    container, clock, world, source_files
):
    make_character(container, world.id, "Solo", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    original = container.assignments.active_for_task(task.id)

    final = complete_n_times(container, clock, task.id, STAMPS_PER_CHARACTER)[-1]

    assert final.new_assignment is not None
    assert final.new_assignment.character_id == original.character_id
    assert final.new_assignment.id != original.id


def test_rollover_without_replacement_moves_task_to_draft(
    container, clock, world, source_files
):
    """Stamp 15 with zero eligible replacements parks the task as a draft
    instead of leaving a broken active task behind."""
    solo = make_character(container, world.id, "Solo", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    complete_n_times(container, clock, task.id, STAMPS_PER_CHARACTER - 1)
    clock.advance_days(1)
    # Simulate the only character becoming unavailable mid-run.
    container.characters.set_archived(solo.id, True)
    final = container.completion_service.complete_task(task.id)

    assert final.completion.streak_number == 15  # history preserved first
    assert final.assignment_completed
    assert final.new_assignment is None
    assert final.task_deactivated
    assert container.tasks.get(task.id).status.value == "draft"
    assert container.assignments.active_for_task(task.id) is None
