import pytest

from task_stamps.domain.enums import TaskStatus, TaskWeight
from task_stamps.domain.exceptions import UndoNotAllowedError, ValidationError
from task_stamps.services.reward_service import reward_for
from tests.helpers import EVERY_DAY, make_character, make_task, make_world


def _penalties(container, task_id):
    return container.db.query_all(
        "SELECT * FROM task_penalties WHERE task_id = ? ORDER BY penalty_date",
        (task_id,),
    )


@pytest.mark.parametrize(
    ("weight", "expected"),
    [
        (TaskWeight.TRIVIAL, (0, 0, 0, 0)),
        (TaskWeight.MINOR, (1, 2, 3, 5)),
        (TaskWeight.MEDIUM, (2, 3, 4, 6)),
        (TaskWeight.MAJOR, (3, 5, 6, 8)),
    ],
)
def test_reward_schedule(weight, expected):
    assert tuple(reward_for(weight, streak) for streak in (1, 5, 10, 15)) == expected


def test_completion_earns_points_and_undo_removes_them(
    container, source_files
):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.task_service.update_task(task.id, weight=TaskWeight.MAJOR)

    result = container.completion_service.complete_task(task.id)

    assert result.reward_points == 3
    assert result.completion.reward_points == 3
    assert container.vice_service.balance == 3

    container.completion_service.undo_completion(result.completion.id)
    assert container.vice_service.balance == 0


def test_claim_spends_points_and_inventory_atomically(container, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.task_service.update_task(task.id, weight=TaskWeight.MINOR)
    container.completion_service.complete_task(task.id)
    vice = container.vice_service.save_offering(None, "Cake", "A slice", 1, 2)

    claim = container.vice_service.claim(vice.id)

    assert claim.offering_name_snapshot == "Cake"
    assert claim.price_paid == 1
    assert container.vice_service.balance == 0
    assert container.vices.get(vice.id).quantity == 1
    with pytest.raises(ValidationError, match="enough points"):
        container.vice_service.claim(vice.id)
    assert container.vices.get(vice.id).quantity == 1
    container.vice_service.remove_offering(vice.id)
    assert container.vice_service.balance == 0


def test_out_of_stock_vice_cannot_be_claimed(container):
    vice = container.vice_service.save_offering(None, "Nap", "", 0, 0)
    with pytest.raises(ValidationError, match="out of stock"):
        container.vice_service.claim(vice.id)


def test_completion_cannot_be_undone_after_its_points_are_spent(
    container, source_files
):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    result = container.completion_service.complete_task(task.id)
    vice = container.vice_service.save_offering(None, "Treat", "", 2, 1)
    container.vice_service.claim(vice.id)

    with pytest.raises(UndoNotAllowedError, match="already been spent"):
        container.completion_service.undo_completion(result.completion.id)


def test_missed_task_deducts_next_streak_reward_without_negative_balance(
    container, clock, source_files
):
    world = make_world(container)
    make_character(container, world.id, "First", source_files)
    make_character(container, world.id, "Second", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.task_service.update_task(task.id, weight=TaskWeight.MAJOR)
    # Reach streak four: the next completion would earn the five-streak bonus (5).
    for _ in range(4):
        container.completion_service.complete_task(task.id)
        clock.advance_days(1)
    assert container.vice_service.balance == 12

    clock.advance_days(1)  # leave the current scheduled day uncompleted
    events = container.schedule_service.evaluate_missed_days()

    assert events[0].points_deducted == 5
    assert container.vice_service.balance == 7
    assert _penalties(container, task.id)[0]["points_assessed"] == 5


def test_missed_penalty_takes_only_available_balance(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "First", source_files)
    make_character(container, world.id, "Second", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.task_service.update_task(task.id, weight=TaskWeight.MAJOR)
    container.completion_service.complete_task(task.id)  # Earn 3.
    vice = container.vice_service.save_offering(None, "Small treat", "", 2, 1)
    container.vice_service.claim(vice.id)  # Leave only 1 available.
    clock.advance_days(2)

    event = container.schedule_service.evaluate_missed_days()[0]

    assert event.points_deducted == 1
    assert _penalties(container, task.id)[0]["points_assessed"] == 3
    assert container.vice_service.balance == 0


def test_three_consecutive_misses_auto_pause_and_stop_future_charges(
    container, clock, source_files
):
    world = make_world(container)
    make_character(container, world.id, "First", source_files)
    make_character(container, world.id, "Second", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.completion_service.complete_task(task.id)
    clock.advance_days(4)  # Tuesday, Wednesday, and Thursday were missed.

    events = container.schedule_service.evaluate_missed_days()

    assert events[0].auto_paused
    assert container.tasks.get(task.id).status == TaskStatus.PAUSED
    assert len(_penalties(container, task.id)) == 3
    balance = container.vice_service.balance
    clock.advance_days(10)
    assert container.schedule_service.evaluate_missed_days() == []
    assert container.vice_service.balance == balance


def test_completion_resets_consecutive_miss_count(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "First", source_files)
    make_character(container, world.id, "Second", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.completion_service.complete_task(task.id)
    clock.advance_days(2)  # Tuesday missed; complete Wednesday.
    container.completion_service.complete_task(task.id)
    clock.advance_days(3)  # Thursday and Friday missed; Saturday is in progress.

    container.schedule_service.evaluate_missed_days()

    assert container.tasks.get(task.id).status == TaskStatus.ACTIVE
    assert container.vices.consecutive_misses(task.id) == 2


def test_pausing_scheduled_task_charges_available_points_but_keeps_run(
    container, clock, source_files
):
    world = make_world(container)
    character = make_character(container, world.id, "Hero", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.completion_service.complete_task(task.id)
    clock.advance_days(1)
    assignment = container.assignments.active_for_task(task.id)

    deducted = container.task_service.pause(task.id)

    assert deducted == 2
    assert container.vice_service.balance == 0
    preserved = container.assignments.active_for_task(task.id)
    assert preserved.id == assignment.id
    assert preserved.character_id == character.id
    assert preserved.current_streak == 1


def test_scheduled_pause_with_insufficient_or_zero_points_still_succeeds(
    container, source_files
):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    task = make_task(container, weekdays=EVERY_DAY)

    assert container.task_service.pause(task.id) == 0
    assert container.tasks.get(task.id).status == TaskStatus.PAUSED
    assert container.vice_service.balance == 0
