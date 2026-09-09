"""Builders shared by the test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from task_stamps.container import AppContainer
from task_stamps.domain.enums import STAMPS_PER_CHARACTER, PoolType, TaskWeight
from task_stamps.domain.models import Character, HabitTask, World
from task_stamps.services.completion_service import CompletionResult
from task_stamps.utilities.clock import FixedClock
from task_stamps.utilities.dates import weekdays_to_mask
from task_stamps.utilities.placeholder_art import (
    render_beep_wav,
    render_portrait_png,
    render_stamp_png,
)

EVERY_DAY = (0, 1, 2, 3, 4, 5, 6)
MON_WED_FRI = (0, 2, 4)


def make_world(container: AppContainer, name: str = "Testland") -> World:
    return container.library_service.create_world(name)


def make_character(
    container: AppContainer,
    world_id: str,
    name: str,
    source_dir: Path,
    stamp_count: int = STAMPS_PER_CHARACTER,
    with_sound: bool = False,
) -> Character:
    """Create a character with a portrait and ``stamp_count`` stamp images
    (15 makes it ready, anything less leaves it a draft)."""
    library = container.library_service
    character = library.create_character(world_id, name)
    portrait = source_dir / f"{character.id}_portrait.png"
    render_portrait_png(portrait, (150, 150, 160), width=30, height=40)
    library.import_portrait(character.id, portrait)
    if with_sound:
        sound = source_dir / f"{character.id}_sound.wav"
        render_beep_wav(sound, duration=0.05)
        library.import_default_sound(character.id, sound)
    for sequence in range(1, stamp_count + 1):
        stamp_file = source_dir / f"{character.id}_stamp_{sequence}.png"
        render_stamp_png(stamp_file, sequence, (160, 170, 150), width=32, height=24)
        library.import_stamp_image(character.id, sequence, stamp_file)
    return container.characters.get(character.id)


def make_task(
    container: AppContainer,
    name: str = "Habit",
    weekdays: Iterable[int] = MON_WED_FRI,
    pool_type: PoolType = PoolType.ALL_WORLDS,
    world_id: str | None = None,
    activate: bool = True,
    weight: TaskWeight = TaskWeight.MEDIUM,
) -> HabitTask:
    task = container.task_service.create_draft(
        name, "", weekdays_to_mask(weekdays), pool_type, world_id, weight
    )
    if activate:
        container.task_service.activate(task.id)
    return container.tasks.get(task.id)


def complete_n_times(
    container: AppContainer, clock: FixedClock, task_id: str, count: int
) -> list[CompletionResult]:
    """Complete a task ``count`` times, advancing the clock day by day so no
    scheduled day is ever skipped."""
    results: list[CompletionResult] = []
    for _ in range(count):
        task = container.tasks.get(task_id)
        while (
            not container.schedule_service.is_scheduled_on(task, clock.today())
            or container.completions.exists_for_date(task_id, clock.today())
        ):
            clock.advance_days(1)
        results.append(container.completion_service.complete_task(task_id))
    return results
