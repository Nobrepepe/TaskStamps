"""Read-only analytics derived from the completion history."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from task_stamps.data.repositories.completions import CompletionRepository
from task_stamps.data.repositories.tasks import TaskRepository
from task_stamps.domain.enums import TaskStatus
from task_stamps.utilities.clock import Clock


@dataclass(frozen=True)
class RankedItem:
    name: str
    count: int


@dataclass(frozen=True)
class StatsSnapshot:
    start: date
    end: date
    total: int
    active_days: int
    possible_days: int
    current_run: int
    best_day: tuple[date, int] | None
    points: int
    daily: tuple[tuple[date, int], ...]
    weekdays: tuple[int, ...]
    tasks: tuple[RankedItem, ...]
    characters: tuple[RankedItem, ...]
    worlds: tuple[RankedItem, ...]
    active_task_count: int


class StatsService:
    def __init__(
        self, clock: Clock, completions: CompletionRepository, tasks: TaskRepository
    ) -> None:
        self.clock = clock
        self.completions = completions
        self.tasks = tasks

    def snapshot(self, days: int = 30) -> StatsSnapshot:
        if days < 1:
            raise ValueError("days must be positive")
        end = self.clock.today()
        start = end - timedelta(days=days - 1)
        completions = self.completions.list_between(start, end)

        daily_counts = Counter(item.completion_date for item in completions)
        daily = tuple(
            (start + timedelta(days=offset), daily_counts[start + timedelta(days=offset)])
            for offset in range(days)
        )
        weekdays = tuple(
            sum(count for day, count in daily if day.weekday() == weekday)
            for weekday in range(7)
        )
        active_days = sum(1 for count in daily_counts.values() if count)
        current_run = 0
        cursor = end
        while cursor >= start and daily_counts[cursor] > 0:
            current_run += 1
            cursor -= timedelta(days=1)
        best_day = (
            max(daily, key=lambda item: (item[1], item[0]))
            if completions
            else None
        )

        def ranked(values: Counter[str]) -> tuple[RankedItem, ...]:
            return tuple(
                RankedItem(name, count)
                for name, count in sorted(
                    values.items(), key=lambda item: (-item[1], item[0].casefold())
                )
            )

        return StatsSnapshot(
            start=start,
            end=end,
            total=len(completions),
            active_days=active_days,
            possible_days=days,
            current_run=current_run,
            best_day=best_day,
            points=sum(item.reward_points for item in completions),
            daily=daily,
            weekdays=weekdays,
            tasks=ranked(Counter(item.task_name_snapshot for item in completions)),
            characters=ranked(
                Counter(item.character_name_snapshot for item in completions)
            ),
            worlds=ranked(Counter(item.world_name_snapshot for item in completions)),
            active_task_count=len(self.tasks.list(status=TaskStatus.ACTIVE)),
        )
