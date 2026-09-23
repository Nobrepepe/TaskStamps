from __future__ import annotations

import sqlite3

import pytest

from task_stamps.data.database import Database
from task_stamps.data.migrations.m0001_initial import SQL as M1
from task_stamps.data.migrations.m0002_rewards import SQL as M2
from task_stamps.data.migrations.m0003_task_penalties import SQL as M3
from task_stamps.data.migrations.m0004_worldhub import SQL as M4
from task_stamps.data.migrations.m0005_dark_board import SQL as M5
from task_stamps.data.migrations.m0006_daily_boss import SQL as M6
from task_stamps.data.migrations.m0007_vice_chests import SQL as M7
from task_stamps.domain import goal_track
from task_stamps.domain.enums import (
    GoalLegEndReason,
    GoalStatus,
    PoolType,
    TaskWeight,
)
from task_stamps.domain.exceptions import (
    CharacterEditError,
    NoGoalCharacterError,
    UndoNotAllowedError,
    ValidationError,
)
from tests.helpers import (
    EVERY_DAY,
    add_goal_images,
    make_character,
    make_goal_character,
    make_task,
    make_world,
)


def _reward(container, name="Pizza night"):
    return container.chest_service.save_reward(None, TaskWeight.MAJOR, 15, name, "")


def _goal(container, reward, start=0.0, target=100.0, name="Read pages", **extra):
    return container.goal_service.create_goal(
        name=name, start_value=start, target_value=target, reward_id=reward.id, **extra
    )


def _unclaimed(container, reward_id):
    return container.chests.unclaimed_counts().get(reward_id, 0)


@pytest.fixture
def world(container):
    return make_world(container)


@pytest.fixture
def cast(container, world, source_files):
    """Three characters with full goal art."""
    return [
        make_goal_character(container, world.id, name, source_files)
        for name in ("Ada", "Bo", "Cy")
    ]


# -- the track ------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 1), (9.99, 1), (10, 2), (55, 6), (90, 10), (99.9, 10), (100, 10), (-5, 1)],
)
def test_sections_upward(value, expected):
    assert goal_track.section(0, 100, value) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [(90, 1), (89, 2), (85, 6), (81, 10), (80, 10)]
)
def test_sections_downward(value, expected):
    assert goal_track.section(90, 80, value) == expected


def test_track_edges_tolerate_float_noise():
    assert goal_track.section(0, 1, 0.1 + 0.2) == 4  # 0.30000000000000004
    assert goal_track.is_reached(0, 0.3, 0.1 + 0.2)
    assert not goal_track.is_behind_baseline(0.3, 1, 0.1 + 0.2)
    assert goal_track.is_behind_baseline(90, 80, 90.5)
    assert goal_track.format_value(82.50) == "82.5"
    assert goal_track.format_value(3.0) == "3"


# -- creating -------------------------------------------------------------


def test_create_draws_a_goal_character(container, cast):
    view = _goal(container, _reward(container))
    assert view.character.id in {c.id for c in cast}
    assert view.section == 1
    assert view.image_version_id == container.characters.goal_image(view.character.id, 1)
    assert view.goal.status == GoalStatus.ACTIVE
    assert not view.review_due


def test_create_refuses_without_a_character_with_all_ten_images(
    container, world, source_files
):
    partial = make_character(container, world.id, "Half", source_files, stamp_count=0)
    add_goal_images(container, partial.id, source_files, count=9)
    with pytest.raises(NoGoalCharacterError):
        _goal(container, _reward(container))
    assert container.goals.list() == []  # the transaction rolled back


def test_create_validates_reward_and_values(container, cast):
    reward = _reward(container)
    with pytest.raises(ValidationError):
        container.goal_service.create_goal(
            name="x", start_value=5, target_value=5, reward_id=reward.id
        )
    with pytest.raises(ValidationError):
        container.goal_service.create_goal(
            name="x", start_value=0, target_value=5, reward_id=None
        )
    with pytest.raises(ValidationError):
        container.goal_service.create_goal(
            name="x", start_value=0, target_value=float("nan"), reward_id=reward.id
        )


def test_goals_never_share_a_character_but_tasks_may(container, world, source_files):
    reward = _reward(container)
    solo = make_character(container, world.id, "Solo", source_files)
    add_goal_images(container, solo.id, source_files)
    make_task(container, weekdays=EVERY_DAY)  # Solo now holds a task too
    first = _goal(container, reward)
    assert first.character.id == solo.id
    with pytest.raises(NoGoalCharacterError):
        _goal(container, reward, name="Second")


def test_world_pool_is_respected(container, cast, source_files):
    other = make_world(container, "Elsewhere")
    stranger = make_goal_character(container, other.id, "Stranger", source_files)
    view = _goal(
        container, _reward(container), pool_type=PoolType.SPECIFIC_WORLD, world_id=other.id
    )
    assert view.character.id == stranger.id


# -- logging progress -----------------------------------------------------


def test_progress_moves_sections_and_restarts_the_review(container, clock, cast):
    view = _goal(container, _reward(container))
    clock.advance_days(7)
    assert container.goal_service.view(view.goal.id).review_due
    assert container.goal_service.reviews_due_count() == 1

    result = container.goal_service.log_progress(view.goal.id, 35)
    assert (result.section_before, result.section_after) == (1, 4)
    assert not (result.reached or result.rebased)
    after = container.goal_service.view(view.goal.id)
    assert after.goal.current_value == 35
    assert after.goal.last_reviewed_on == clock.today()
    assert not after.review_due

    clock.advance_days(7)
    container.goal_service.log_progress(view.goal.id, 0)  # a check-in counts
    assert not container.goal_service.view(view.goal.id).review_due


def test_negative_entry_inside_the_track_keeps_the_character(container, cast):
    view = _goal(container, _reward(container))
    container.goal_service.log_progress(view.goal.id, 55)
    result = container.goal_service.log_progress(view.goal.id, -30)
    assert result.section_after == 3
    assert not result.rebased
    assert result.character_id == view.character.id


def test_slipping_past_the_start_rebases_with_a_new_character(container, cast):
    view = _goal(container, _reward(container), start=10, target=50)
    result = container.goal_service.log_progress(view.goal.id, -4)
    assert result.rebased
    assert result.character_id != view.character.id
    after = container.goal_service.view(view.goal.id)
    assert after.goal.baseline_value == 6
    assert after.goal.target_value == 50
    assert after.section == 1
    old, new = container.goals.legs_for_goal(view.goal.id)
    assert old.end_reason == GoalLegEndReason.REBASED and old.end_value == 6
    assert new.is_active and new.baseline_value == 6


def test_downward_goal_rebases_when_the_value_rises(container, cast):
    view = _goal(container, _reward(container), start=90, target=80)
    assert container.goal_service.log_progress(view.goal.id, -5).section_after == 6
    result = container.goal_service.log_progress(view.goal.id, +7)  # 92
    assert result.rebased
    assert container.goal_service.view(view.goal.id).goal.baseline_value == 92


def test_a_lone_goal_character_takes_over_its_own_rebase(container, world, source_files):
    solo = make_goal_character(container, world.id, "Solo", source_files)
    view = _goal(container, _reward(container))
    result = container.goal_service.log_progress(view.goal.id, -1)
    assert result.rebased and result.character_id == solo.id


def test_reaching_drops_one_chest_on_the_chosen_reward(container, cast):
    reward = _reward(container)
    decoy = _reward(container, "Decoy")
    view = _goal(container, reward, start=0, target=10)
    result = container.goal_service.log_progress(view.goal.id, 12)  # overshoot
    assert result.reached and result.chest is not None
    assert result.chest.reward_id == reward.id
    assert _unclaimed(container, reward.id) == 1
    assert _unclaimed(container, decoy.id) == 0
    after = container.goal_service.view(view.goal.id)
    assert after.goal.status == GoalStatus.REACHED
    assert after.section == 10 and not after.review_due
    with pytest.raises(ValidationError):
        container.goal_service.log_progress(view.goal.id, 1)


def test_extend_hands_a_fresh_track_to_a_new_character(container, cast):
    reward = _reward(container)
    next_reward = _reward(container, "Concert")
    view = _goal(container, reward, start=0, target=10)
    container.goal_service.log_progress(view.goal.id, 12)
    extended = container.goal_service.extend(view.goal.id, 30, next_reward.id)
    assert extended.goal.status == GoalStatus.ACTIVE
    assert (extended.goal.baseline_value, extended.goal.target_value) == (12, 30)
    assert extended.goal.reward_id == next_reward.id
    assert extended.character.id != view.character.id
    assert extended.section == 1
    first, second = container.goals.legs_for_goal(view.goal.id)
    assert first.end_reason == GoalLegEndReason.REACHED
    assert second.ordinal == 2 and second.is_active

    container.goal_service.log_progress(view.goal.id, 18)
    assert _unclaimed(container, next_reward.id) == 1


def test_finish_frees_the_character(container, world, source_files):
    solo = make_goal_character(container, world.id, "Solo", source_files)
    reward = _reward(container)
    view = _goal(container, reward, start=0, target=1)
    container.goal_service.log_progress(view.goal.id, 1)
    finished = container.goal_service.finish(view.goal.id)
    assert finished.goal.status == GoalStatus.FINISHED
    assert finished.character.id == solo.id  # still shown as who carried it
    assert _goal(container, reward, name="Next").character.id == solo.id


# -- editing and removing -------------------------------------------------


def test_edit_keeps_the_target_ahead_and_on_course(container, cast):
    reward = _reward(container)
    view = _goal(container, reward, start=0, target=100)
    container.goal_service.log_progress(view.goal.id, 40)
    kwargs = dict(
        name="Read", description="", unit="pages", reward_id=reward.id,
        pool_type=PoolType.ALL_WORLDS, world_id=None,
    )
    with pytest.raises(ValidationError):
        container.goal_service.edit_goal(view.goal.id, target_value=-10, **kwargs)
    with pytest.raises(ValidationError):
        container.goal_service.edit_goal(view.goal.id, target_value=40, **kwargs)
    edited = container.goal_service.edit_goal(view.goal.id, target_value=50, **kwargs)
    assert edited.section == 9
    assert container.goals.active_leg(view.goal.id).target_value == 50
    assert edited.goal.unit == "pages"


def test_rewards_a_goal_is_walking_toward_cannot_be_removed(container, cast):
    reward = _reward(container)
    view = _goal(container, reward, start=0, target=1)
    with pytest.raises(ValidationError):
        container.chest_service.remove_reward(reward.id)
    container.goal_service.log_progress(view.goal.id, 1)
    container.chest_service.remove_reward(reward.id)  # reached: no longer waiting


def test_remove_deletes_or_hides_depending_on_chests(container, cast):
    reward = _reward(container)
    plain = _goal(container, reward, name="Plain")
    container.goal_service.remove(plain.goal.id)
    with pytest.raises(KeyError):
        container.goals.get(plain.goal.id)

    paid = _goal(container, reward, start=0, target=1, name="Paid")
    container.goal_service.log_progress(paid.goal.id, 1)
    container.goal_service.remove(paid.goal.id)
    assert container.goals.get(paid.goal.id).status == GoalStatus.REMOVED
    assert [v.goal.name for v in container.goal_service.views()] == []
    assert _unclaimed(container, reward.id) == 1
    assert container.goals.active_leg(paid.goal.id) is None


# -- undo -----------------------------------------------------------------


def test_undo_restores_value_and_review_date(container, clock, cast):
    view = _goal(container, _reward(container))
    created_on = clock.today()
    clock.advance_days(3)
    container.goal_service.log_progress(view.goal.id, 20)
    container.goal_service.undo_last_entry(view.goal.id)
    after = container.goal_service.view(view.goal.id)
    assert after.goal.current_value == 0
    assert after.goal.last_reviewed_on == created_on
    assert container.goals.entries_for_goal(view.goal.id) == []


def test_undo_is_same_day_only(container, clock, cast):
    view = _goal(container, _reward(container))
    container.goal_service.log_progress(view.goal.id, 20)
    clock.advance_days(1)
    assert container.goal_service.undoable_entry(view.goal.id) is None
    with pytest.raises(UndoNotAllowedError):
        container.goal_service.undo_last_entry(view.goal.id)


def test_undo_of_reaching_takes_the_chest_back_unless_claimed(container, cast):
    reward = _reward(container)
    view = _goal(container, reward, start=0, target=10)
    container.goal_service.log_progress(view.goal.id, 10)
    container.goal_service.undo_last_entry(view.goal.id)
    assert _unclaimed(container, reward.id) == 0
    assert container.goals.get(view.goal.id).status == GoalStatus.ACTIVE

    container.goal_service.log_progress(view.goal.id, 10)
    container.chest_service.claim(reward.id)
    with pytest.raises(ValidationError):
        container.goal_service.undo_last_entry(view.goal.id)
    assert container.goals.get(view.goal.id).status == GoalStatus.REACHED


def test_undo_of_a_rebase_brings_the_old_character_back(container, cast):
    view = _goal(container, _reward(container), start=10, target=50)
    container.goal_service.log_progress(view.goal.id, -4)
    container.goal_service.undo_last_entry(view.goal.id)
    after = container.goal_service.view(view.goal.id)
    assert after.character.id == view.character.id
    assert after.goal.baseline_value == 10 and after.goal.current_value == 10
    assert len(container.goals.legs_for_goal(view.goal.id)) == 1


def test_undo_of_a_rebase_is_refused_once_the_old_character_moved_on(
    container, world, source_files
):
    reward = _reward(container)
    ada = make_goal_character(container, world.id, "Ada", source_files)
    bo = make_goal_character(container, world.id, "Bo", source_files)
    first = _goal(container, reward, name="First")
    container.goal_service.log_progress(first.goal.id, -1)  # first -> other char
    freed = first.character.id
    second = _goal(container, reward, name="Second")
    assert second.character.id == freed
    with pytest.raises(UndoNotAllowedError):
        container.goal_service.undo_last_entry(first.goal.id)
    assert {ada.id, bo.id} == {
        container.goal_service.view(first.goal.id).character.id, second.character.id
    }


# -- the library ----------------------------------------------------------


def test_archiving_a_goal_character_hands_the_goal_on(container, cast):
    view = _goal(container, _reward(container), start=0, target=100)
    container.goal_service.log_progress(view.goal.id, 30)
    with pytest.raises(CharacterEditError):
        container.library_service.archive_character(view.character.id)
    container.library_service.archive_character(view.character.id, confirmed=True)
    after = container.goal_service.view(view.goal.id)
    assert after.character.id != view.character.id
    assert after.goal.current_value == 30 and after.section == 4


def test_goal_waits_for_a_character_and_takes_one_when_free(
    container, world, source_files
):
    solo = make_goal_character(container, world.id, "Solo", source_files)
    view = _goal(container, _reward(container))
    container.library_service.archive_character(solo.id, confirmed=True)
    assert container.goal_service.view(view.goal.id).character is None
    fresh = make_goal_character(container, world.id, "Fresh", source_files)
    assert container.goal_service.assign_waiting_characters() == 1
    assert container.goal_service.view(view.goal.id).character.id == fresh.id


def test_goal_images_cannot_be_cleared_while_carrying(container, cast):
    view = _goal(container, _reward(container))
    with pytest.raises(CharacterEditError):
        container.library_service.clear_goal_image(view.character.id, 3)
    idle = next(c for c in cast if c.id != view.character.id)
    container.library_service.clear_goal_image(idle.id, 3)
    assert 3 not in container.characters.goal_images_for(idle.id)


def test_goal_images_are_protected_from_asset_cleanup(container, cast):
    before = container.characters.goal_images_for(cast[0].id)
    container.asset_service.cleanup_unreferenced_versions()
    for version_id in before.values():
        assert container.asset_service.path_for_version_id(version_id) is not None


# -- schema ---------------------------------------------------------------


def test_goal_schema_migrates_from_v7_and_keeps_chests(tmp_path):
    path = tmp_path / "v7.sqlite3"
    connection = sqlite3.connect(path)
    for sql in (M1, M2, M3, M4, M5, M6, M7):
        connection.executescript(sql)
    connection.execute(
        "INSERT INTO vice_rewards(id, task_weight, tier, name, created_at, updated_at) "
        "VALUES ('r1', 'minor', 5, 'Tea', datetime('now'), datetime('now'))"
    )
    connection.execute(
        "INSERT INTO vice_chests(id, source, reward_id, reward_name_snapshot, boss_date, "
        "granted_at, claimed_at) VALUES ('c1', 'boss', 'r1', 'Tea', '2026-01-05', "
        "datetime('now'), NULL)"
    )
    connection.execute("PRAGMA user_version = 7")
    connection.commit()
    connection.close()

    database = Database(path)
    database.migrate()
    row = database.query_one("SELECT * FROM vice_chests WHERE id = 'c1'")
    assert row["reward_name_snapshot"] == "Tea" and row["goal_leg_id"] is None
    tables = {
        r["name"]
        for r in database.query_all("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"goals", "goal_legs", "goal_entries", "character_goal_images"} <= tables
    with pytest.raises(sqlite3.IntegrityError):  # one Boss chest per day still holds
        database.execute(
            "INSERT INTO vice_chests(id, source, reward_id, boss_date, granted_at) "
            "VALUES ('c2', 'boss', 'r1', '2026-01-05', datetime('now'))"
        )
    database.close()
