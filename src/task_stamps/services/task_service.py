"""Habit task lifecycle: draft, activation, pause/resume, archive."""

from __future__ import annotations

from task_stamps.data.database import Database
from task_stamps.data.repositories.assignments import AssignmentRepository
from task_stamps.data.repositories.tasks import TaskRepository
from task_stamps.domain.enums import (
    AssignmentEndReason,
    PoolType,
    TaskStatus,
    TaskWeight,
)
from task_stamps.domain.exceptions import (
    PoolChangeConflictError,
    ValidationError,
)
from task_stamps.domain.models import CharacterAssignment, HabitTask
from task_stamps.services.assignment_service import AssignmentService
from task_stamps.services.schedule_service import ScheduleService
from task_stamps.utilities.clock import Clock
from task_stamps.utilities.logging_setup import get_logger

logger = get_logger("tasks")


class TaskService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        tasks: TaskRepository,
        assignments: AssignmentRepository,
        assignment_service: AssignmentService,
        schedule: ScheduleService,
    ) -> None:
        self.db = db
        self.clock = clock
        self.tasks = tasks
        self.assignments = assignments
        self.assignment_service = assignment_service
        self.schedule = schedule

    def create_draft(
        self,
        name: str,
        description: str,
        weekday_mask: int,
        pool_type: PoolType,
        world_id: str | None,
        weight: TaskWeight = TaskWeight.MEDIUM,
    ) -> HabitTask:
        if not name.strip():
            raise ValidationError("A task needs a name.")
        if pool_type == PoolType.SPECIFIC_WORLD and not world_id:
            raise ValidationError("Pick a world for a world-limited pool.")
        return self.tasks.create(
            name.strip(),
            description.strip(),
            weekday_mask,
            pool_type,
            world_id if pool_type == PoolType.SPECIFIC_WORLD else None,
            weight,
        )

    def update_task(
        self,
        task_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        weekday_mask: int | None = None,
        pool_type: PoolType | None = None,
        world_id: str | None = ...,  # type: ignore[assignment]
        weight: TaskWeight | None = None,
    ) -> HabitTask:
        """Edit a task. A pool change that would exclude the currently
        assigned character is rejected instead of silently breaking it."""
        with self.db.transaction():
            task = self.tasks.get(task_id)
            new_pool = pool_type if pool_type is not None else task.pool_type
            new_world = task.world_id if world_id is ... else world_id
            if new_pool == PoolType.ALL_WORLDS:
                new_world = None
            elif not new_world:
                raise ValidationError("Pick a world for a world-limited pool.")
            assignment = self.assignments.active_for_task(task_id)
            if assignment is not None and new_pool == PoolType.SPECIFIC_WORLD:
                character_world = self.db.query_one(
                    "SELECT world_id FROM characters WHERE id = ?",
                    (assignment.character_id,),
                )
                if character_world and character_world["world_id"] != new_world:
                    raise PoolChangeConflictError()
            return self.tasks.update(
                task_id,
                name=name,
                description=description,
                weekday_mask=weekday_mask,
                pool_type=new_pool,
                world_id=new_world,
                weight=weight,
            )

    def activate(self, task_id: str) -> CharacterAssignment:
        """Activate a draft (or reactivate a task that lost its character).

        Assigns one random eligible character; when none exists a
        NoEligibleCharacterError propagates and the task stays a draft.
        """
        with self.db.transaction():
            task = self.tasks.get(task_id)
            if task.status == TaskStatus.ARCHIVED:
                raise ValidationError("Archived tasks cannot be activated.")
            if task.status == TaskStatus.ACTIVE:
                raise ValidationError("This task is already active.")
            if task.weekday_mask == 0:
                raise ValidationError("Select at least one weekday before activating.")
            assignment = self.assignments.active_for_task(task_id)
            if assignment is None:
                assignment = self.assignment_service.assign_character(task)
            self.tasks.set_status(task_id, TaskStatus.ACTIVE)
            return assignment

    def pause(self, task_id: str) -> None:
        """Pause while retaining the assignment and streak. Paused dates are
        stored as ranges and never count as missed, so pausing costs nothing."""
        self.schedule.evaluate_missed_days()
        with self.db.transaction():
            task = self.tasks.get(task_id)
            if task.status != TaskStatus.ACTIVE:
                raise ValidationError("Only active tasks can be paused.")
            self.tasks.open_pause(task_id, self.clock.today())
            self.tasks.set_status(task_id, TaskStatus.PAUSED)

    def resume(self, task_id: str) -> None:
        """Resume with the same assignment and streak; the pause period is
        closed so those dates never count as missed."""
        with self.db.transaction():
            task = self.tasks.get(task_id)
            if task.status != TaskStatus.PAUSED:
                raise ValidationError("Only paused tasks can be resumed.")
            self.tasks.close_open_pause(task_id, self.clock.today())
            self.tasks.set_status(task_id, TaskStatus.ACTIVE)

    def archive(self, task_id: str) -> None:
        """Archive: releases the character, preserves all history."""
        with self.db.transaction():
            task = self.tasks.get(task_id)
            if task.status == TaskStatus.ARCHIVED:
                return
            if task.status == TaskStatus.PAUSED:
                self.tasks.close_open_pause(task_id, self.clock.today())
            assignment = self.assignments.active_for_task(task_id)
            if assignment is not None:
                self.assignments.end(
                    assignment.id,
                    AssignmentEndReason.ARCHIVED,
                    ended_on=self.clock.today(),
                )
            self.tasks.set_status(task_id, TaskStatus.ARCHIVED)
            logger.info("Archived task %s", task.name)
