"""Clock abstraction so services can be tested with controlled dates.

Always uses the computer's local timezone; nothing is hard-coded.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def today(self) -> date: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now().astimezone()

    def today(self) -> date:
        return date.today()


class FixedClock:
    """Test clock with a settable local date."""

    def __init__(self, today: date, at: time = time(9, 0)) -> None:
        self._today = today
        self._time = at

    def now(self) -> datetime:
        return datetime.combine(self._today, self._time).astimezone()

    def today(self) -> date:
        return self._today

    def set_today(self, value: date) -> None:
        self._today = value

    def advance_days(self, days: int) -> None:
        self._today = self._today + timedelta(days=days)
