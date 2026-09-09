"""Weekday scheduling and missed-day evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from task_stamps.data.database import Database
from task_stamps.data.repositories.assignments import AssignmentRepository
from task_stamps.data.repositories.completions import CompletionRepository
from task_stamps.data.repositories.state import (
    KEY_LAST_EVALUATION_DATE,
    KEY_LAST_KNOWN_DATE,
    AppStateRepository,
)
from task_stamps.data.repositories.tasks import TaskRepository
from task_stamps.data.repositories.misses import MissRepository
from task_stamps.domain.enums import AssignmentEndReason, TaskStatus
from task_stamps.domain.exceptions import NoEligibleCharacterError
from task_stamps.domain.models import HabitTask, PausePeriod
from task_stamps.utilities.clock import Clock
from task_stamps.utilities.dates import date_range, mask_matches
from task_stamps.utilities.logging_setup import get_logger

logger = get_logger("schedule")


@dataclass
class DropEvent:
    task_id: str
    task_name: str
    old_character_id: str
    dropped_due_date: date
    new_character_id: str | None  # None when no replacement was available
    auto_paused: bool = False


def _is_paused_on(pauses: list[PausePeriod], day: date) -> bool:
    """A date counts as paused from the pause start (inclusive) up to the
    resume date (exclusive) — the resume day is schedulable again."""
    for pause in pauses:
        if pause.started_on <= day and (pause.ended_on is None or day < pause.ended_on):
            return True
    return False


class ScheduleService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        tasks: TaskRepository,
        assignments: AssignmentRepository,
        completions: CompletionRepository,
        state: AppStateRepository,
        misses: MissRepository,
    ) -> None:
        self.db = db
        self.clock = clock
        self.tasks = tasks
        self.assignments = assignments
        self.completions = completions
        self.state = state
        self.misses = misses
        # Set lazily by the container to avoid a hard construction cycle
        # with AssignmentService.
        self.assignment_service = None  # type: ignore[assignment]

    # -- pure schedule questions --------------------------------------

    def is_scheduled_on(self, task: HabitTask, day: date) -> bool:
        return mask_matches(task.weekday_mask, day)

    def next_scheduled_date(self, task: HabitTask, from_date: date) -> date | None:
        if task.weekday_mask == 0:
            return None
        for offset in range(0, 8):
            candidate = from_date + timedelta(days=offset)
            if mask_matches(task.weekday_mask, candidate):
                return candidate
        return None

    def missed_dates(
        self,
        task: HabitTask,
        boundary_inclusive: date,
        today: date,
        pauses: list[PausePeriod],
    ) -> list[date]:
        """Scheduled, unpaused dates in [boundary, today) — today itself is
        never considered missed while it is still in progress."""
        return [
            day
            for day in date_range(boundary_inclusive, today)
            if self.is_scheduled_on(task, day) and not _is_paused_on(pauses, day)
        ]

    # -- evaluation ----------------------------------------------------

    def evaluate_missed_days(self) -> list[DropEvent]:
        """Detect scheduled days missed since the last evaluation and drop
        the affected assignments (once each, with one replacement draw).

        Runs at startup, on focus after a date change, and before every
        completion. Paused and archived tasks are never evaluated.
        """
        today = self.clock.today()
        last_evaluation = self.state.get_date(KEY_LAST_EVALUATION_DATE)
        events: list[DropEvent] = []
        with self.db.transaction():
            for task in self.tasks.list(status=TaskStatus.ACTIVE):
                event = self._evaluate_task(task, today, last_evaluation)
                if event is not None:
                    events.append(event)
            self.state.set_date(KEY_LAST_EVALUATION_DATE, today)
            self.state.set_date(KEY_LAST_KNOWN_DATE, today)
        return events

    def _evaluate_task(
        self, task: HabitTask, today: date, last_evaluation: date | None
    ) -> DropEvent | None:
        assignment = self.assignments.active_for_task(task.id)
        if assignment is None:
            return None
        boundary = assignment.started_on
        last_completion = self.completions.last_completion_date(assignment.id)
        if last_completion is not None:
            boundary = max(boundary, last_completion + timedelta(days=1))
        if last_evaluation is not None:
            # Dates before the previous evaluation day were already checked;
            # that day itself was "today" back then, so it is included now.
            boundary = max(boundary, last_evaluation)
        pauses = self.tasks.pauses_for(task.id)
        missed = self.missed_dates(task, boundary, today, pauses)
        if not missed:
            return None

        # Every scheduled failure is recorded. Once the third consecutive
        # miss is reached, pausing makes later dates in this batch irrelevant.
        consecutive = self.misses.consecutive_misses(task.id)
        for missed_date in missed:
            self.misses.record(task.id, missed_date)
            consecutive += 1
            if consecutive >= 3:
                break

        # Exactly one drop and one replacement, no matter how many
        # scheduled dates went by while the app was closed.
        first_missed = missed[0]
        self.assignments.end(
            assignment.id,
            AssignmentEndReason.DROPPED,
            ended_on=today,
            dropped_due_date=first_missed,
        )
        logger.info(
            "Task %s dropped: missed scheduled date %s", task.name, first_missed
        )
        new_character_id: str | None = None
        assert self.assignment_service is not None
        try:
            replacement = self.assignment_service.assign_character(
                task, exclude_character_id=assignment.character_id
            )
            new_character_id = replacement.character_id
        except NoEligibleCharacterError:
            self.tasks.set_status(task.id, TaskStatus.DRAFT)
            logger.warning(
                "Task %s left without a character after drop; moved to draft", task.name
            )
        auto_paused = consecutive >= 3 and new_character_id is not None
        if auto_paused:
            self.tasks.open_pause(task.id, today)
            self.tasks.set_status(task.id, TaskStatus.PAUSED)
            logger.info("Task %s automatically paused after three misses", task.name)
        return DropEvent(
            task_id=task.id,
            task_name=task.name,
            old_character_id=assignment.character_id,
            dropped_due_date=first_missed,
            new_character_id=new_character_id,
            auto_paused=auto_paused,
        )

    # -- date-change detection ------------------------------------------

    def date_changed_since_last_check(self) -> bool:
        last_known = self.state.get_date(KEY_LAST_KNOWN_DATE)
        return last_known is None or last_known != self.clock.today()
