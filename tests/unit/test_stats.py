from __future__ import annotations

from tests.helpers import EVERY_DAY, complete_n_times, make_character, make_task, make_world


def test_stats_aggregate_history_by_day_task_and_character(
    container, clock, source_files
):
    world = make_world(container, "Forest")
    character = make_character(container, world.id, "Moss", source_files)
    task = make_task(container, "Read", EVERY_DAY)

    results = complete_n_times(container, clock, task.id, 3)
    snapshot = container.stats_service.snapshot(7)

    assert snapshot.total == 3
    assert snapshot.active_days == 3
    assert snapshot.weekdays[:3] == (1, 1, 1)
    assert snapshot.tasks[0].name == "Read"
    assert snapshot.characters[0].name == character.name
    assert snapshot.worlds[0].name == world.name
    assert snapshot.current_run == 3
    assert snapshot.best_day is not None
    assert snapshot.best_day[1] == 1
    assert snapshot.points == sum(result.reward_points for result in results)


def test_stats_ignore_reversed_completions(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    result = complete_n_times(container, clock, task.id, 1)[0]

    container.completion_service.undo_completion(result.completion.id)
    snapshot = container.stats_service.snapshot(30)

    assert snapshot.total == 0
    assert snapshot.tasks == ()
