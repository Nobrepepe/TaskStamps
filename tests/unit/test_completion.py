"""Completion basics: stamp numbering, per-day rules, scheduling guards."""

from __future__ import annotations

import pytest

from task_stamps.domain.exceptions import (
    AlreadyCompletedTodayError,
    NotScheduledTodayError,
    TaskPausedError,
)
from tests.helpers import MON_WED_FRI, make_character, make_task, make_world


@pytest.fixture
def world_and_character(container, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Hero", source_files)
    return world, character


def test_first_completion_uses_stamp_one(container, clock, world_and_character):
    task = make_task(container, weekdays=MON_WED_FRI)
    result = container.completion_service.complete_task(task.id)
    assert result.completion.streak_number == 1
    stamp = container.characters.get_stamp(result.completion.stamp_id)
    assert stamp.sequence_number == 1
    assert result.placement is not None
    assert result.placement.board_date == clock.today()


def test_each_scheduled_completion_advances_by_one(container, clock, world_and_character):
    task = make_task(container, weekdays=MON_WED_FRI)
    container.completion_service.complete_task(task.id)  # Monday -> 1
    clock.advance_days(2)  # Wednesday
    result = container.completion_service.complete_task(task.id)
    assert result.completion.streak_number == 2
    assignment = container.assignments.active_for_task(task.id)
    assert assignment.current_streak == 2


def test_cannot_complete_twice_same_date(container, world_and_character):
    task = make_task(container)
    container.completion_service.complete_task(task.id)
    with pytest.raises(AlreadyCompletedTodayError):
        container.completion_service.complete_task(task.id)


def test_cannot_complete_on_unscheduled_day(container, clock, world_and_character):
    task = make_task(container, weekdays=MON_WED_FRI)
    clock.advance_days(1)  # Tuesday
    with pytest.raises(NotScheduledTodayError):
        container.completion_service.complete_task(task.id)


def test_unscheduled_days_do_not_reset_streak(container, clock, world_and_character):
    task = make_task(container, weekdays=MON_WED_FRI)
    container.completion_service.complete_task(task.id)  # Monday
    clock.advance_days(1)  # Tuesday: nothing scheduled
    container.schedule_service.evaluate_missed_days()
    assignment = container.assignments.active_for_task(task.id)
    assert assignment.current_streak == 1
    clock.advance_days(1)  # Wednesday
    result = container.completion_service.complete_task(task.id)
    assert result.completion.streak_number == 2


def test_cannot_complete_while_paused(container, world_and_character):
    task = make_task(container)
    container.task_service.pause(task.id)
    with pytest.raises(TaskPausedError):
        container.completion_service.complete_task(task.id)


def test_completion_failure_rolls_back_everything(container, clock, world_and_character):
    """A failed completion leaves no partial rows behind."""
    task = make_task(container, weekdays=MON_WED_FRI)
    clock.advance_days(1)  # Tuesday — not scheduled
    with pytest.raises(NotScheduledTodayError):
        container.completion_service.complete_task(task.id)
    assert container.board_service.stamp_count(clock.today()) == 0
    assert not container.completions.list_for_task(task.id)
    assert container.assignments.active_for_task(task.id).current_streak == 0
