"""Date and weekday-mask helpers. Weekday index 0 = Monday ... 6 = Sunday."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Iterator

from task_stamps.domain.enums import WEEKDAY_SHORT


def weekdays_to_mask(weekdays: Iterable[int]) -> int:
    mask = 0
    for day in weekdays:
        if not 0 <= day <= 6:
            raise ValueError(f"weekday out of range: {day}")
        mask |= 1 << day
    return mask


def mask_to_weekdays(mask: int) -> list[int]:
    return [day for day in range(7) if mask & (1 << day)]


def mask_matches(mask: int, value: date) -> bool:
    return bool(mask & (1 << value.weekday()))


def mask_label(mask: int) -> str:
    days = mask_to_weekdays(mask)
    if not days:
        return "No days"
    if len(days) == 7:
        return "Every day"
    return ", ".join(WEEKDAY_SHORT[day] for day in days)


def date_range(start: date, end_exclusive: date) -> Iterator[date]:
    current = start
    while current < end_exclusive:
        yield current
        current += timedelta(days=1)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
