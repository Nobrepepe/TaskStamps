"""Random, exclusive character-to-task assignment."""

from __future__ import annotations

from task_stamps.data.database import Database
from task_stamps.data.repositories.assignments import AssignmentRepository
from task_stamps.data.repositories.characters import CharacterRepository
from task_stamps.data.repositories.worlds import WorldRepository
from task_stamps.domain.enums import AssignmentEndReason, PoolType
from task_stamps.domain.exceptions import NoEligibleCharacterError
from task_stamps.domain.models import CharacterAssignment, HabitTask
from task_stamps.utilities.clock import Clock
from task_stamps.utilities.logging_setup import get_logger
from task_stamps.utilities.rng import RandomProvider

logger = get_logger("assignment")


class AssignmentService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        rng: RandomProvider,
        characters: CharacterRepository,
        assignments: AssignmentRepository,
        worlds: WorldRepository,
    ) -> None:
        self.db = db
        self.clock = clock
        self.rng = rng
        self.characters = characters
        self.assignments = assignments
        self.worlds = worlds

    def pool_description(self, task: HabitTask) -> str:
        if task.pool_type == PoolType.SPECIFIC_WORLD and task.world_id:
            world = self.worlds.find(task.world_id)
            return f"the world '{world.name}'" if world else "the selected world"
        return "all worlds"

    def eligible_character_ids(
        self, task: HabitTask, exclude_character_id: str | None = None
    ) -> list[str]:
        """Eligible pool for one draw.

        Excludes characters reserved by another task's stamp-15 completion
        today (their undo window is still open). The previous character of
        this task is excluded only when an alternative exists.
        """
        pool = self.characters.eligible_character_ids(task.pool_type, task.world_id)
        reserved = set(
            self.characters.reserved_character_ids(
                self.clock.today(), exclude_task_id=task.id
            )
        )
        pool = [cid for cid in pool if cid not in reserved]
        if exclude_character_id is not None:
            without_previous = [cid for cid in pool if cid != exclude_character_id]
            if without_previous:
                return without_previous
        return pool

    def assign_character(
        self, task: HabitTask, exclude_character_id: str | None = None
    ) -> CharacterAssignment:
        """Randomly assign an eligible character and persist it immediately.

        The result is never rerolled on startup or refresh — it only changes
        through completion, drop, archive, or explicit end reasons.
        """
        with self.db.transaction():
            pool = self.eligible_character_ids(task, exclude_character_id)
            if not pool:
                raise NoEligibleCharacterError(self.pool_description(task))
            character_id = self.rng.choice(pool)
            assignment = self.assignments.create(
                task_id=task.id,
                character_id=character_id,
                started_on=self.clock.today(),
            )
            logger.info(
                "Assigned character %s to task %s", character_id, task.name
            )
            return assignment

    def end_assignment(
        self,
        assignment_id: str,
        reason: AssignmentEndReason,
    ) -> None:
        self.assignments.end(assignment_id, reason, ended_on=self.clock.today())

    def release_character_of_task(
        self, task_id: str, reason: AssignmentEndReason
    ) -> None:
        assignment = self.assignments.active_for_task(task_id)
        if assignment is not None:
            self.end_assignment(assignment.id, reason)
