"""Read-only streak and progress summaries for the interface."""

from __future__ import annotations

from dataclasses import dataclass

from task_stamps.data.repositories.assignments import AssignmentRepository
from task_stamps.data.repositories.completions import CompletionRepository
from task_stamps.domain.enums import STAMPS_PER_CHARACTER
from task_stamps.domain.models import CharacterAssignment


@dataclass
class ProgressSummary:
    assignment: CharacterAssignment | None
    current_streak: int
    next_stamp_number: int | None
    used_stamp_numbers: set[int]


class StreakService:
    def __init__(
        self, assignments: AssignmentRepository, completions: CompletionRepository
    ) -> None:
        self.assignments = assignments
        self.completions = completions

    def _summary_for_assignment(
        self, assignment: CharacterAssignment | None
    ) -> ProgressSummary:
        if assignment is None:
            return ProgressSummary(None, 0, None, set())
        used = {
            completion.streak_number
            for completion in self.completions.list_for_assignment(assignment.id)
        }
        next_number = (
            assignment.current_streak + 1
            if assignment.is_active and assignment.current_streak < STAMPS_PER_CHARACTER
            else None
        )
        return ProgressSummary(
            assignment=assignment,
            current_streak=assignment.current_streak,
            next_stamp_number=next_number,
            used_stamp_numbers=used,
        )

    def task_progress(self, task_id: str) -> ProgressSummary:
        return self._summary_for_assignment(self.assignments.active_for_task(task_id))

    def character_progress(self, character_id: str) -> ProgressSummary:
        """Active assignment when present, otherwise the most recent one."""
        assignment = self.assignments.active_for_character(character_id)
        if assignment is None:
            history = self.assignments.history_for_character(character_id, limit=1)
            assignment = history[0] if history else None
        return self._summary_for_assignment(assignment)
