"""Missed-day evaluation: drops, single reassignment, pauses."""

from __future__ import annotations

from datetime import date

import pytest

from task_stamps.domain.enums import AssignmentEndReason
from tests.helpers import MON_WED_FRI, make_character, make_task, make_world


@pytest.fixture
def two_characters(container, source_files):
    world = make_world(container)
    return (
        make_character(container, world.id, "Alpha", source_files),
        make_character(container, world.id, "Beta", source_files),
    )


def test_missing_one_scheduled_day_drops_assignment(container, clock, two_characters):
    task = make_task(container, weekdays=MON_WED_FRI)
    original = container.assignments.active_for_task(task.id)
    container.completion_service.complete_task(task.id)  # Monday
    clock.advance_days(3)  # Thursday: Wednesday was missed
    events = container.schedule_service.evaluate_missed_days()

    assert len(events) == 1
    assert events[0].dropped_due_date == date(2026, 1, 7)  # the missed Wednesday
    dropped = container.assignments.get(original.id)
    assert not dropped.is_active
    assert dropped.end_reason == AssignmentEndReason.DROPPED
    replacement = container.assignments.active_for_task(task.id)
    assert replacement is not None
    assert replacement.id != original.id
    assert replacement.current_streak == 0


def test_multiple_missed_dates_cause_single_drop(container, clock, two_characters):
    task = make_task(container, weekdays=MON_WED_FRI)
    container.completion_service.complete_task(task.id)  # Monday
    clock.advance_days(14)  # two full weeks closed: many missed dates
    events = container.schedule_service.evaluate_missed_days()

    assert len(events) == 1
    history = container.assignments.history_for_task(task.id)
    assert len(history) == 2  # original + exactly one replacement
    assert sum(1 for a in history if a.end_reason == AssignmentEndReason.DROPPED) == 1


def test_current_day_is_never_missed_while_in_progress(container, clock, two_characters):
    task = make_task(container, weekdays=MON_WED_FRI)
    # Monday, scheduled, not completed yet — evaluating today must not drop.
    events = container.schedule_service.evaluate_missed_days()
    assert events == []
    assert container.assignments.active_for_task(task.id) is not None


def test_paused_scheduled_dates_do_not_count_as_missed(container, clock, two_characters):
    task = make_task(container, weekdays=MON_WED_FRI)
    original = container.assignments.active_for_task(task.id)
    container.completion_service.complete_task(task.id)  # Monday, streak 1
    container.task_service.pause(task.id)
    clock.advance_days(7)  # skips Wed + Fri while paused
    container.task_service.resume(task.id)
    events = container.schedule_service.evaluate_missed_days()

    assert events == []
    assignment = container.assignments.active_for_task(task.id)
    assert assignment.id == original.id


def test_resume_preserves_streak_and_character(container, clock, two_characters):
    task = make_task(container, weekdays=MON_WED_FRI)
    original = container.assignments.active_for_task(task.id)
    container.completion_service.complete_task(task.id)
    container.task_service.pause(task.id)
    clock.advance_days(9)
    container.task_service.resume(task.id)

    assignment = container.assignments.active_for_task(task.id)
    assert assignment.id == original.id
    assert assignment.character_id == original.character_id
    assert assignment.current_streak == 1


def test_evaluation_before_completion_drops_stale_streak(container, clock, two_characters):
    """complete_task itself runs the evaluation first."""
    task = make_task(container, weekdays=MON_WED_FRI)
    original = container.assignments.active_for_task(task.id)
    container.completion_service.complete_task(task.id)  # Monday
    clock.advance_days(4)  # Friday; Wednesday missed, no explicit evaluation ran
    result = container.completion_service.complete_task(task.id)

    # The completion went to the *replacement* assignment at streak 1.
    assert result.completion.streak_number == 1
    assert result.completion.assignment_id != original.id


def test_archived_tasks_are_not_evaluated(container, clock, two_characters):
    task = make_task(container, weekdays=MON_WED_FRI)
    container.task_service.archive(task.id)
    clock.advance_days(10)
    events = container.schedule_service.evaluate_missed_days()
    assert events == []
