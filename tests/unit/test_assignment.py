"""Assignment eligibility, exclusivity, pools, and persistence."""

from __future__ import annotations

import sqlite3

import pytest

from task_stamps.container import build_container
from task_stamps.domain.enums import CharacterStatus, PoolType, TaskStatus
from task_stamps.domain.exceptions import (
    NoEligibleCharacterError,
    PoolChangeConflictError,
)
from task_stamps.utilities.rng import SeededRandomProvider
from tests.helpers import make_character, make_task, make_world


def test_two_tasks_cannot_hold_same_character(container, source_files):
    world = make_world(container)
    make_character(container, world.id, "Solo", source_files)
    make_task(container, name="First")
    second = make_task(container, name="Second", activate=False)
    with pytest.raises(NoEligibleCharacterError):
        container.task_service.activate(second.id)

    # The database index also enforces exclusivity directly.
    first_assignment = container.assignments.list_active()[0]
    with pytest.raises(sqlite3.IntegrityError):
        container.assignments.create(
            second.id, first_assignment.character_id, container.clock.today()
        )


def test_draft_character_cannot_be_assigned(container, source_files):
    world = make_world(container)
    make_character(container, world.id, "Unfinished", source_files, stamp_count=10)
    task = make_task(container, activate=False)
    with pytest.raises(NoEligibleCharacterError):
        container.task_service.activate(task.id)


def test_character_missing_stamp_cannot_be_assigned_even_if_marked_ready(
    container, source_files
):
    world = make_world(container)
    character = make_character(container, world.id, "Gappy", source_files, stamp_count=14)
    container.characters.set_status(character.id, CharacterStatus.READY)  # stale flag
    task = make_task(container, activate=False)
    with pytest.raises(NoEligibleCharacterError):
        container.task_service.activate(task.id)


def test_world_pool_never_selects_other_world(container, source_files):
    world_a = make_world(container, "A")
    world_b = make_world(container, "B")
    make_character(container, world_b.id, "Outsider", source_files)
    for index in range(3):
        make_character(container, world_a.id, f"Local{index}", source_files)
    for index in range(5):
        task = make_task(
            container,
            name=f"Task{index}",
            pool_type=PoolType.SPECIFIC_WORLD,
            world_id=world_a.id,
            activate=index < 3,  # only 3 characters exist in world A
        )
        if index < 3:
            assignment = container.assignments.active_for_task(task.id)
            character = container.characters.get(assignment.character_id)
            assert character.world_id == world_a.id


def test_all_world_pool_can_select_any_eligible_character(container, source_files):
    world_a = make_world(container, "A")
    world_b = make_world(container, "B")
    char_a = make_character(container, world_a.id, "FromA", source_files)
    char_b = make_character(container, world_b.id, "FromB", source_files)
    task = make_task(container, pool_type=PoolType.ALL_WORLDS, activate=False)
    eligible = container.assignment_service.eligible_character_ids(
        container.tasks.get(task.id)
    )
    assert set(eligible) == {char_a.id, char_b.id}


def test_no_character_leaves_task_in_draft(container):
    make_world(container)  # empty world, no characters at all
    task = make_task(container, activate=False)
    with pytest.raises(NoEligibleCharacterError) as excinfo:
        container.task_service.activate(task.id)
    assert "all worlds" in excinfo.value.user_message
    assert container.tasks.get(task.id).status == TaskStatus.DRAFT
    assert container.assignments.active_for_task(task.id) is None


def test_pool_change_cannot_silently_invalidate_assignment(container, source_files):
    world_a = make_world(container, "A")
    world_b = make_world(container, "B")
    make_character(container, world_a.id, "OnlyA", source_files)
    make_character(container, world_b.id, "OnlyB", source_files)
    task = make_task(container, pool_type=PoolType.SPECIFIC_WORLD, world_id=world_a.id)
    assignment = container.assignments.active_for_task(task.id)

    with pytest.raises(PoolChangeConflictError):
        container.task_service.update_task(
            task.id, pool_type=PoolType.SPECIFIC_WORLD, world_id=world_b.id
        )
    unchanged = container.assignments.active_for_task(task.id)
    assert unchanged.id == assignment.id
    assert container.tasks.get(task.id).world_id == world_a.id


def test_restart_does_not_reroll_assignments(container, data_dir, clock, source_files):
    world = make_world(container)
    for index in range(4):
        make_character(container, world.id, f"C{index}", source_files)
    task = make_task(container)
    original = container.assignments.active_for_task(task.id)
    container.close()

    # Fresh container over the same data directory with a different RNG.
    reopened = build_container(
        data_dir=data_dir, clock=clock, rng=SeededRandomProvider(999)
    )
    try:
        persisted = reopened.assignments.active_for_task(task.id)
        assert persisted.id == original.id
        assert persisted.character_id == original.character_id
    finally:
        reopened.close()
