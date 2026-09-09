from __future__ import annotations

import pytest

from task_stamps.domain.enums import CHEST_TIERS, CHEST_WEIGHTS, TaskStatus, TaskWeight
from task_stamps.domain.exceptions import UndoNotAllowedError, ValidationError
from task_stamps.services.chest_service import slot_weight, weighted_pick
from task_stamps.utilities.placeholder_art import render_portrait_png, render_stamp_png
from task_stamps.utilities.rng import SeededRandomProvider
from tests.helpers import (
    EVERY_DAY,
    complete_n_times,
    make_character,
    make_task,
    make_world,
)


def _reward(container, weight, tier, name):
    return container.chest_service.save_reward(None, weight, tier, name, "")


def _fill_every_slot(container):
    """One reward in each of the nine slots, named '<weight>-<tier>'."""
    return {
        (weight, tier): _reward(container, weight, tier, f"{weight.value}-{tier}")
        for weight in CHEST_WEIGHTS
        for tier in CHEST_TIERS
    }


def _boss_media(container, character_id, source_dir):
    image = source_dir / f"{character_id}_boss.png"
    render_portrait_png(image, (90, 40, 40), width=64, height=36)
    container.library_service.import_boss_image(character_id, image)


def _unclaimed(container, reward_id):
    return container.chests.unclaimed_counts().get(reward_id, 0)


# -- the reward slots ----------------------------------------------------


def test_the_nine_slots_are_weight_by_tier(container):
    slots = container.chest_service.slots()
    assert len(slots) == 9
    assert {(slot.weight, slot.tier) for slot in slots} == {
        (weight, tier) for weight in CHEST_WEIGHTS for tier in CHEST_TIERS
    }
    assert all(slot.rewards == () for slot in slots)


def test_a_reward_needs_a_name_and_a_real_slot(container):
    service = container.chest_service
    with pytest.raises(ValidationError):
        service.save_reward(None, TaskWeight.MINOR, 5, "   ", "")
    with pytest.raises(ValidationError):
        service.save_reward(None, TaskWeight.TRIVIAL, 5, "Nope", "")
    with pytest.raises(ValidationError):
        service.save_reward(None, TaskWeight.MINOR, 7, "Nope", "")


def test_removing_a_reward_with_chests_keeps_it_out_of_future_draws(
    container, clock, source_files
):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    reward = _reward(container, TaskWeight.MEDIUM, 5, "Coffee")
    task = make_task(container, weekdays=EVERY_DAY, weight=TaskWeight.MEDIUM)
    complete_n_times(container, clock, task.id, 5)
    assert _unclaimed(container, reward.id) == 1

    container.chest_service.remove_reward(reward.id)

    # Archived, not deleted: the earned chest survives and still counts.
    assert container.chests.get_reward(reward.id).is_archived
    assert _unclaimed(container, reward.id) == 1
    assert container.chests.rewards_in_slot(TaskWeight.MEDIUM, 5) == []


def test_removing_an_untouched_reward_deletes_it(container):
    reward = _reward(container, TaskWeight.MAJOR, 15, "Day trip")
    container.chest_service.remove_reward(reward.id)
    with pytest.raises(KeyError):
        container.chests.get_reward(reward.id)


# -- earning streak chests -----------------------------------------------


def test_chests_land_only_on_streaks_5_10_and_15(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    make_character(container, world.id, "Spare", source_files)
    rewards = _fill_every_slot(container)
    task = make_task(container, weekdays=EVERY_DAY, weight=TaskWeight.MEDIUM)

    results = complete_n_times(container, clock, task.id, 15)

    earned = [index + 1 for index, result in enumerate(results) if result.chest]
    assert earned == [5, 10, 15]
    for tier in CHEST_TIERS:
        assert _unclaimed(container, rewards[(TaskWeight.MEDIUM, tier)].id) == 1
    # Nothing leaked into the other weights' slots.
    assert _unclaimed(container, rewards[(TaskWeight.MINOR, 5)].id) == 0
    assert _unclaimed(container, rewards[(TaskWeight.MAJOR, 5)].id) == 0


def test_trivial_tasks_earn_stamps_only(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    _fill_every_slot(container)
    task = make_task(container, weekdays=EVERY_DAY, weight=TaskWeight.TRIVIAL)

    results = complete_n_times(container, clock, task.id, 5)

    assert all(result.chest is None for result in results)
    assert container.chest_service.unclaimed_total() == 0


def test_an_empty_slot_grants_nothing(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    task = make_task(container, weekdays=EVERY_DAY, weight=TaskWeight.MINOR)

    results = complete_n_times(container, clock, task.id, 5)

    assert results[4].chest is None
    assert container.chest_service.unclaimed_total() == 0


def test_the_draw_stays_inside_the_slot(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    inside = {
        _reward(container, TaskWeight.MINOR, 5, name).id
        for name in ("Coffee", "Snack", "A short walk")
    }
    outside = _reward(container, TaskWeight.MINOR, 10, "Episode")
    task = make_task(container, weekdays=EVERY_DAY, weight=TaskWeight.MINOR)

    result = complete_n_times(container, clock, task.id, 5)[4]

    assert result.chest is not None
    assert result.chest.reward_id in inside
    assert _unclaimed(container, outside.id) == 0


# -- claiming ------------------------------------------------------------


def test_claiming_spends_one_chest(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    reward = _reward(container, TaskWeight.MINOR, 5, "Coffee")
    task = make_task(container, weekdays=EVERY_DAY, weight=TaskWeight.MINOR)
    complete_n_times(container, clock, task.id, 5)

    chest = container.chest_service.claim(reward.id)

    assert chest.is_claimed
    assert chest.reward_name_snapshot == "Coffee"
    assert _unclaimed(container, reward.id) == 0
    with pytest.raises(ValidationError):
        container.chest_service.claim(reward.id)


# -- undo ----------------------------------------------------------------


def test_undo_takes_back_an_unclaimed_chest(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    reward = _reward(container, TaskWeight.MINOR, 5, "Coffee")
    task = make_task(container, weekdays=EVERY_DAY, weight=TaskWeight.MINOR)
    result = complete_n_times(container, clock, task.id, 5)[4]
    assert _unclaimed(container, reward.id) == 1

    container.completion_service.undo_completion(result.completion.id)

    assert _unclaimed(container, reward.id) == 0
    assert container.chest_service.unclaimed_total() == 0


def test_undo_is_refused_once_the_chest_is_claimed(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    reward = _reward(container, TaskWeight.MINOR, 5, "Coffee")
    task = make_task(container, weekdays=EVERY_DAY, weight=TaskWeight.MINOR)
    result = complete_n_times(container, clock, task.id, 5)[4]
    container.chest_service.claim(reward.id)

    with pytest.raises(UndoNotAllowedError, match="already been claimed"):
        container.completion_service.undo_completion(result.completion.id)

    # The refusal rolled everything back: the stamp is still on the board.
    assert not container.completions.get(result.completion.id).is_reversed
    assert container.assignments.active_for_task(task.id).current_streak == 5


# -- the Boss chest ------------------------------------------------------


def test_defeating_the_boss_seals_exactly_one_chest_per_day(
    container, clock, source_files
):
    world = make_world(container)
    character = make_character(container, world.id, "Boss", source_files)
    _boss_media(container, character.id, source_files)
    make_character(container, world.id, "Spare", source_files)
    first = make_task(container, "First", EVERY_DAY)
    second = make_task(container, "Second", EVERY_DAY)

    opening = container.completion_service.complete_task(first.id)
    assert not opening.boss_chest_granted  # one of two tasks done

    closing = container.completion_service.complete_task(second.id)
    assert closing.boss_chest_granted
    assert container.chest_service.sealed_boss_count() == 1

    # A second evaluation of the same day mints nothing further.
    assert (
        container.chest_service.grant_boss_chest_if_defeated(clock.today(), True) is None
    )
    assert container.chest_service.sealed_boss_count() == 1


def test_undo_returns_the_sealed_boss_chest(container, clock, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Boss", source_files)
    _boss_media(container, character.id, source_files)
    make_character(container, world.id, "Spare", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    result = container.completion_service.complete_task(task.id)
    assert container.chest_service.sealed_boss_count() == 1

    container.completion_service.undo_completion(result.completion.id)

    assert container.chest_service.sealed_boss_count() == 0


def test_undo_is_refused_once_the_boss_chest_is_opened(container, clock, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Boss", source_files)
    _boss_media(container, character.id, source_files)
    make_character(container, world.id, "Spare", source_files)
    _reward(container, TaskWeight.MINOR, 5, "Coffee")
    task = make_task(container, weekdays=EVERY_DAY)
    result = container.completion_service.complete_task(task.id)
    container.chest_service.open_boss_chest()

    with pytest.raises(UndoNotAllowedError, match="already been opened"):
        container.completion_service.undo_completion(result.completion.id)


def test_opening_a_boss_chest_rolls_a_reward_and_claims_it(
    container, clock, source_files
):
    world = make_world(container)
    character = make_character(container, world.id, "Boss", source_files)
    _boss_media(container, character.id, source_files)
    make_character(container, world.id, "Spare", source_files)
    rewards = _fill_every_slot(container)
    task = make_task(container, weekdays=EVERY_DAY)
    container.completion_service.complete_task(task.id)

    opened = container.chest_service.open_boss_chest()

    assert opened.reward_id in {reward.id for reward in rewards.values()}
    assert opened.is_claimed
    assert not opened.is_sealed
    assert container.chest_service.sealed_boss_count() == 0
    with pytest.raises(ValidationError, match="no Boss chests"):
        container.chest_service.open_boss_chest()


def test_a_boss_chest_cannot_be_opened_with_no_rewards_defined(
    container, clock, source_files
):
    world = make_world(container)
    character = make_character(container, world.id, "Boss", source_files)
    _boss_media(container, character.id, source_files)
    make_character(container, world.id, "Spare", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.completion_service.complete_task(task.id)

    with pytest.raises(ValidationError, match="at least one reward"):
        container.chest_service.open_boss_chest()

    # Refusing to open leaves the chest sealed and waiting.
    assert container.chest_service.sealed_boss_count() == 1


# -- Boss chest odds -----------------------------------------------------


def test_slot_weights_read_as_percentages():
    grid = {
        (weight, tier): slot_weight(weight, tier)
        for weight in CHEST_WEIGHTS
        for tier in CHEST_TIERS
    }
    assert sum(grid.values()) == 100
    assert grid[(TaskWeight.MINOR, 5)] == 36
    assert grid[(TaskWeight.MAJOR, 15)] == 1
    # Rarity falls off along both axes.
    assert grid[(TaskWeight.MINOR, 5)] > grid[(TaskWeight.MEDIUM, 5)] > grid[
        (TaskWeight.MAJOR, 5)
    ]
    assert grid[(TaskWeight.MAJOR, 5)] > grid[(TaskWeight.MAJOR, 10)] > grid[
        (TaskWeight.MAJOR, 15)
    ]


def test_weighted_pick_follows_the_odds():
    rng = SeededRandomProvider(42)
    slots = [(weight, tier) for weight in CHEST_WEIGHTS for tier in CHEST_TIERS]
    counts = {slot: 0 for slot in slots}
    draws = 20_000
    for _ in range(draws):
        counts[weighted_pick(slots, rng)] += 1

    for slot in slots:
        share = counts[slot] / draws * 100
        assert abs(share - slot_weight(*slot)) < 1.5


def test_emptying_slots_renormalises_rather_than_skewing():
    rng = SeededRandomProvider(7)
    slots = [(TaskWeight.MINOR, 5), (TaskWeight.MAJOR, 15)]  # weights 36 and 1
    counts = {slot: 0 for slot in slots}
    draws = 20_000
    for _ in range(draws):
        counts[weighted_pick(slots, rng)] += 1

    expected = 36 / 37 * 100
    assert abs(counts[(TaskWeight.MINOR, 5)] / draws * 100 - expected) < 1.5
    assert counts[(TaskWeight.MAJOR, 15)] > 0


# -- misses: the point charge is gone, the auto-pause is not --------------


def _misses(container, task_id):
    return container.db.query_all(
        "SELECT * FROM task_misses WHERE task_id = ? ORDER BY miss_date", (task_id,)
    )


def test_three_consecutive_misses_still_auto_pause_the_task(
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
    assert len(_misses(container, task.id)) == 3
    clock.advance_days(10)
    assert container.schedule_service.evaluate_missed_days() == []
    assert len(_misses(container, task.id)) == 3


def test_completion_resets_the_consecutive_miss_count(container, clock, source_files):
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
    assert container.misses.consecutive_misses(task.id) == 2


def test_pausing_on_a_scheduled_day_costs_nothing(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.completion_service.complete_task(task.id)
    clock.advance_days(1)

    container.task_service.pause(task.id)

    assert container.tasks.get(task.id).status == TaskStatus.PAUSED
    # Pausing is not a miss: nothing is recorded, the streak is kept, and it
    # never counts toward the three-miss auto-pause.
    assert _misses(container, task.id) == []
    assert container.assignments.active_for_task(task.id).current_streak == 1
    assert container.misses.consecutive_misses(task.id) == 0


def test_paused_days_never_become_misses(container, clock, source_files):
    world = make_world(container)
    make_character(container, world.id, "Hero", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.completion_service.complete_task(task.id)
    clock.advance_days(1)
    container.task_service.pause(task.id)

    clock.advance_days(5)
    assert container.schedule_service.evaluate_missed_days() == []
    container.task_service.resume(task.id)

    assert _misses(container, task.id) == []
    assert container.assignments.active_for_task(task.id).current_streak == 1
