"""Atomic task completion, the stamp-15 rollover, and same-day undo."""

from __future__ import annotations

from dataclasses import dataclass

from task_stamps.data.database import Database
from task_stamps.data.repositories.assignments import AssignmentRepository
from task_stamps.data.repositories.characters import CharacterRepository
from task_stamps.data.repositories.completions import CompletionRepository
from task_stamps.data.repositories.placements import PlacementRepository
from task_stamps.data.repositories.tasks import TaskRepository
from task_stamps.data.repositories.worlds import WorldRepository
from task_stamps.domain.enums import (
    STAMPS_PER_CHARACTER,
    AssignmentEndReason,
    TaskStatus,
)
from task_stamps.domain.exceptions import (
    AlreadyCompletedTodayError,
    NoActiveAssignmentError,
    NoEligibleCharacterError,
    NotScheduledTodayError,
    StampUnavailableError,
    TaskNotActiveError,
    TaskPausedError,
    UndoNotAllowedError,
    ValidationError,
)
from task_stamps.domain.models import (
    CharacterAssignment,
    HabitTask,
    StampPlacement,
    TaskCompletion,
    ViceChest,
)
from task_stamps.services.assignment_service import AssignmentService
from task_stamps.services.board_service import BoardService
from task_stamps.services.boss_service import BossService
from task_stamps.services.chest_service import ChestService
from task_stamps.services.schedule_service import ScheduleService
from task_stamps.utilities.clock import Clock
from task_stamps.utilities.logging_setup import get_logger

logger = get_logger("completion")


@dataclass
class AvailableTask:
    """A task the user can complete right now, for the Add Stamp panel."""

    task: HabitTask
    assignment: CharacterAssignment
    character_name: str
    portrait_version_id: str | None
    current_streak: int
    next_stamp_number: int


@dataclass
class CompletionResult:
    completion: TaskCompletion
    placement: StampPlacement
    sound_version_id: str | None
    assignment_completed: bool  # stamp 15 finished the run
    new_assignment: CharacterAssignment | None
    task_deactivated: bool  # no replacement character existed
    chest: ViceChest | None  # streak 5/10/15 earned a chest
    boss_chest_granted: bool  # this completion defeated today's Boss


class CompletionService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        tasks: TaskRepository,
        characters: CharacterRepository,
        worlds: WorldRepository,
        assignments: AssignmentRepository,
        completions: CompletionRepository,
        placements: PlacementRepository,
        schedule: ScheduleService,
        assignment_service: AssignmentService,
        board: BoardService,
        boss: BossService,
        chest_service: ChestService,
    ) -> None:
        self.db = db
        self.clock = clock
        self.tasks = tasks
        self.characters = characters
        self.worlds = worlds
        self.assignments = assignments
        self.completions = completions
        self.placements = placements
        self.schedule = schedule
        self.assignment_service = assignment_service
        self.board = board
        self.boss = boss
        self.chest_service = chest_service

    # -- queries ---------------------------------------------------------

    def available_tasks_today(self) -> list[AvailableTask]:
        today = self.clock.today()
        result: list[AvailableTask] = []
        for task in self.tasks.list(status=TaskStatus.ACTIVE):
            if not self.schedule.is_scheduled_on(task, today):
                continue
            if self.completions.exists_for_date(task.id, today):
                continue
            assignment = self.assignments.active_for_task(task.id)
            if assignment is None:
                continue
            character = self.characters.get(assignment.character_id)
            result.append(
                AvailableTask(
                    task=task,
                    assignment=assignment,
                    character_name=character.name,
                    portrait_version_id=character.portrait_asset_version_id,
                    current_streak=assignment.current_streak,
                    next_stamp_number=assignment.current_streak + 1,
                )
            )
        return result

    # -- completion -------------------------------------------------------

    def complete_task(self, task_id: str) -> CompletionResult:
        """Perform a completion as one atomic transaction.

        Eligibility is revalidated inside the transaction; any failure rolls
        everything back.
        """
        self.schedule.evaluate_missed_days()
        today = self.clock.today()
        with self.db.transaction():
            task = self.tasks.get(task_id)
            if task.status == TaskStatus.PAUSED:
                raise TaskPausedError()
            if task.status != TaskStatus.ACTIVE:
                raise TaskNotActiveError()
            if not self.schedule.is_scheduled_on(task, today):
                raise NotScheduledTodayError()
            if self.completions.exists_for_date(task.id, today):
                raise AlreadyCompletedTodayError()
            assignment = self.assignments.active_for_task(task.id)
            if assignment is None:
                raise NoActiveAssignmentError()

            new_streak = assignment.current_streak + 1
            stamp = self.characters.stamp_by_sequence(
                assignment.character_id, new_streak
            )
            if stamp is None or stamp.image_asset_version_id is None:
                raise StampUnavailableError()

            character = self.characters.get(assignment.character_id)
            world = self.worlds.get(character.world_id)
            # The assigned sound (stamp-specific, then character default) is
            # frozen here. The global sound remains a live playback setting
            # and plays before this sound.
            sound_version_id = (
                stamp.sound_asset_version_id or character.default_sound_asset_version_id
            )
            completion = self.completions.create(
                task_id=task.id,
                assignment_id=assignment.id,
                character_id=character.id,
                stamp_id=stamp.id,
                completion_date=today,
                streak_number=new_streak,
                task_name_snapshot=task.name,
                character_name_snapshot=character.name,
                world_name_snapshot=world.name,
            )
            placement = self.board.create_placement(
                completion_id=completion.id,
                board_date=today,
                image_asset_version_id=stamp.image_asset_version_id,
                sound_asset_version_id=sound_version_id,
            )
            chest = self.chest_service.grant_for_completion(
                task.weight, new_streak, completion.id
            )
            # The Boss is defeated when today's board holds every stamp the day
            # asks for; the grant is idempotent, so the insert *is* the event.
            boss = self.boss.daily_boss(today)
            boss_chest = self.chest_service.grant_boss_chest_if_defeated(
                today, boss is not None and boss.defeated
            )

            assignment_completed = new_streak >= STAMPS_PER_CHARACTER
            new_assignment: CharacterAssignment | None = None
            task_deactivated = False
            if assignment_completed:
                self.assignments.update_streak(assignment.id, new_streak)
                self.assignments.end(
                    assignment.id, AssignmentEndReason.COMPLETED, ended_on=today
                )
                try:
                    new_assignment = self.assignment_service.assign_character(
                        task, exclude_character_id=character.id
                    )
                except NoEligibleCharacterError:
                    self.tasks.set_status(task.id, TaskStatus.DRAFT)
                    task_deactivated = True
                    logger.warning(
                        "Task %s finished a character but no replacement exists; "
                        "moved to draft",
                        task.name,
                    )
            else:
                self.assignments.update_streak(assignment.id, new_streak)

            logger.info(
                "Completed task %s (stamp %s, character %s)",
                task.name,
                new_streak,
                character.name,
            )
            return CompletionResult(
                completion=completion,
                placement=placement,
                sound_version_id=sound_version_id,
                assignment_completed=assignment_completed,
                new_assignment=new_assignment,
                task_deactivated=task_deactivated,
                chest=chest,
                boss_chest_granted=boss_chest is not None,
            )

    # -- undo --------------------------------------------------------------

    def can_undo(self, completion: TaskCompletion) -> bool:
        return (
            not completion.is_reversed
            and completion.completion_date == self.clock.today()
        )

    def undo_completion(self, completion_id: str) -> None:
        """Transactionally reverse a completion made today."""
        today = self.clock.today()
        with self.db.transaction():
            completion = self.completions.get(completion_id)
            if completion.is_reversed:
                raise UndoNotAllowedError("This completion was already undone.")
            if completion.completion_date != today:
                raise UndoNotAllowedError(
                    "Only completions made today can be undone; earlier boards are read-only."
                )
            try:
                self.chest_service.revoke_for_completion(completion.id)
            except ValidationError as error:
                raise UndoNotAllowedError(error.user_message) from error
            assignment = self.assignments.get(completion.assignment_id)

            if completion.streak_number < STAMPS_PER_CHARACTER:
                if not assignment.is_active:
                    raise UndoNotAllowedError(
                        "This completion's assignment has already ended, so it "
                        "cannot be undone."
                    )
                self.placements.delete_for_completion(completion.id)
                self.completions.mark_reversed(completion.id)
                self.assignments.update_streak(
                    assignment.id, completion.streak_number - 1
                )
            else:
                self._undo_stamp_fifteen(completion, assignment)
            # Removing a stamp can un-defeat the Boss; the day's chest goes with it.
            boss = self.boss.daily_boss(today)
            if boss is None or not boss.defeated:
                try:
                    self.chest_service.revoke_boss_chest(today)
                except ValidationError as error:
                    raise UndoNotAllowedError(error.user_message) from error
            logger.info("Reversed completion %s", completion_id)

    def _undo_stamp_fifteen(
        self, completion: TaskCompletion, old_assignment: CharacterAssignment
    ) -> None:
        """Restore the pre-completion state: the replacement assignment is
        removed (it can never have completions of its own the same day) and
        the finished assignment resumes at streak 14. The old character was
        kept reserved from other tasks all day, so exclusivity holds."""
        if old_assignment.end_reason != AssignmentEndReason.COMPLETED:
            raise UndoNotAllowedError(
                "The finished assignment has changed since completion, so it "
                "cannot be undone."
            )
        replacement = self.assignments.active_for_task(completion.task_id)
        if replacement is not None and replacement.id != old_assignment.id:
            if self.completions.list_for_assignment(replacement.id):
                raise UndoNotAllowedError(
                    "The replacement character has already been used, so this "
                    "completion cannot be undone."
                )
            self.assignments.delete(replacement.id)
        holder = self.assignments.active_for_character(old_assignment.character_id)
        if holder is not None and holder.id != old_assignment.id:
            raise UndoNotAllowedError(
                "The character has since been assigned elsewhere, so this "
                "completion cannot be undone."
            )
        self.placements.delete_for_completion(completion.id)
        self.completions.mark_reversed(completion.id)
        self.assignments.reactivate(
            old_assignment.id, streak=STAMPS_PER_CHARACTER - 1
        )
        task = self.tasks.get(completion.task_id)
        if task.status == TaskStatus.DRAFT:
            # The task was deactivated because no replacement existed.
            self.tasks.set_status(task.id, TaskStatus.ACTIVE)
