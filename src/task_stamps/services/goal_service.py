"""Goals: create, edit, log progress, extend, finish, remove and undo.

A goal walks from a baseline to a target along ten sections, carried by one
character whose ranked goal images follow the section the value sits in.
Slipping past the baseline hands the goal to a new character and moves the
baseline there; reaching the target drops a chest onto the goal's reward and
waits for the path to be extended (new character, new target) or finished.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from task_stamps.data.database import Database
from task_stamps.data.repositories.characters import CharacterRepository
from task_stamps.data.repositories.chests import ChestRepository
from task_stamps.data.repositories.goals import GoalRepository
from task_stamps.data.repositories.worlds import WorldRepository
from task_stamps.domain import goal_track
from task_stamps.domain.enums import (
    GOAL_REVIEW_DAYS,
    GoalEntryOutcome,
    GoalLegEndReason,
    GoalStatus,
    PoolType,
)
from task_stamps.domain.exceptions import (
    NoGoalCharacterError,
    UndoNotAllowedError,
    ValidationError,
)
from task_stamps.domain.models import Character, Goal, GoalEntry, GoalLeg, ViceChest
from task_stamps.services.chest_service import ChestService
from task_stamps.utilities.clock import Clock
from task_stamps.utilities.logging_setup import get_logger
from task_stamps.utilities.rng import RandomProvider

logger = get_logger("goals")


@dataclass(frozen=True)
class GoalView:
    """Everything the Goals screen needs for one goal (read model)."""

    goal: Goal
    leg: GoalLeg | None
    character: Character | None
    goal_images: dict[int, str]  # rank -> image version id
    section: int
    fraction: float  # 0..1, clamped for drawing the track
    reward_name: str | None
    next_review_on: date | None  # None unless the goal is active
    review_due: bool

    @property
    def image_version_id(self) -> str | None:
        return self.goal_images.get(self.section)


@dataclass(frozen=True)
class ProgressResult:
    entry: GoalEntry
    section_before: int
    section_after: int
    reached: bool
    rebased: bool
    chest: ViceChest | None
    previous_character_id: str | None
    character_id: str | None


class GoalService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        rng: RandomProvider,
        goals: GoalRepository,
        characters: CharacterRepository,
        worlds: WorldRepository,
        chests: ChestRepository,
        chest_service: ChestService,
    ) -> None:
        self.db = db
        self.clock = clock
        self.rng = rng
        self.goals = goals
        self.characters = characters
        self.worlds = worlds
        self.chests = chests
        self.chest_service = chest_service

    # -- reading -----------------------------------------------------------

    def views(self) -> list[GoalView]:
        return [self._view(goal) for goal in self.goals.list()]

    def view(self, goal_id: str) -> GoalView:
        return self._view(self.goals.get(goal_id))

    def reviews_due_count(self) -> int:
        return sum(1 for view in self.views() if view.review_due)

    def history(self, goal_id: str) -> tuple[list[GoalLeg], list[GoalEntry]]:
        return self.goals.legs_for_goal(goal_id), self.goals.entries_for_goal(goal_id)

    def _view(self, goal: Goal) -> GoalView:
        leg = self.goals.active_leg(goal.id)
        if leg is None:
            # Finished and removed goals keep showing whoever carried them last.
            legs = self.goals.legs_for_goal(goal.id)
            leg = legs[-1] if legs else None
        character = (
            self.characters.get(leg.character_id) if leg and leg.character_id else None
        )
        if goal.status in (GoalStatus.REACHED, GoalStatus.FINISHED):
            section, fraction = 10, 1.0
        else:
            section = goal_track.section(
                goal.baseline_value, goal.target_value, goal.current_value
            )
            fraction = max(0.0, min(1.0, goal_track.progress(
                goal.baseline_value, goal.target_value, goal.current_value
            )))
        reward_name = None
        if goal.reward_id:
            try:
                reward_name = self.chests.get_reward(goal.reward_id).name
            except KeyError:
                reward_name = None
        next_review = None
        if goal.status == GoalStatus.ACTIVE:
            next_review = goal.last_reviewed_on + timedelta(days=GOAL_REVIEW_DAYS)
        return GoalView(
            goal=goal,
            leg=leg,
            character=character,
            goal_images=self.characters.goal_images_for(character.id) if character else {},
            section=section,
            fraction=fraction,
            reward_name=reward_name,
            next_review_on=next_review,
            review_due=next_review is not None and self.clock.today() >= next_review,
        )

    # -- creating and editing ----------------------------------------------

    def create_goal(
        self,
        *,
        name: str,
        description: str = "",
        unit: str = "",
        start_value: float,
        target_value: float,
        reward_id: str | None,
        pool_type: PoolType = PoolType.ALL_WORLDS,
        world_id: str | None = None,
    ) -> GoalView:
        name = self._require_name(name)
        start_value = self._require_number(start_value, "The starting value")
        target_value = self._require_number(target_value, "The goal value")
        if start_value == target_value:
            raise ValidationError("The goal has to differ from where you start.")
        self._require_reward(reward_id)
        world_id = self._require_pool(pool_type, world_id)
        with self.db.transaction():
            goal = self.goals.create(
                name=name,
                description=description.strip(),
                unit=unit.strip(),
                baseline_value=start_value,
                target_value=target_value,
                reward_id=reward_id,  # type: ignore[arg-type]
                pool_type=pool_type,
                world_id=world_id,
                reviewed_on=self.clock.today(),
            )
            character_id = self._draw_character(goal, exclude=None)
            if character_id is None:
                raise NoGoalCharacterError(self._pool_description(goal))
            self.goals.create_leg(
                goal.id, character_id, start_value, target_value, self.clock.today()
            )
            logger.info("Goal %s created, carried by %s", goal.name, character_id)
            return self._view(goal)

    def edit_goal(
        self,
        goal_id: str,
        *,
        name: str,
        description: str,
        unit: str,
        target_value: float,
        reward_id: str | None,
        pool_type: PoolType,
        world_id: str | None,
    ) -> GoalView:
        """Edit what a goal is. The target may move only along the current
        track and not onto or behind the current value — a new direction is a
        new goal, and a met target is reached by logging progress."""
        goal = self.goals.get(goal_id)
        if goal.status not in (GoalStatus.ACTIVE, GoalStatus.REACHED):
            raise ValidationError("Finished goals can no longer be edited.")
        name = self._require_name(name)
        target_value = self._require_number(target_value, "The goal value")
        world_id = self._require_pool(pool_type, world_id)
        if reward_id != goal.reward_id or goal.status == GoalStatus.ACTIVE:
            self._require_reward(reward_id)
        target_changed = target_value != goal.target_value
        if target_changed:
            if goal.status == GoalStatus.REACHED:
                raise ValidationError(
                    "This goal is already reached. Extend the path to set a new goal."
                )
            old_direction = math.copysign(1, goal.target_value - goal.baseline_value)
            new_direction = math.copysign(1, target_value - goal.baseline_value)
            if target_value == goal.baseline_value or old_direction != new_direction:
                raise ValidationError(
                    "A goal can't change direction. Finish or remove it and set a new one."
                )
            if goal_track.is_reached(goal.baseline_value, target_value, goal.current_value):
                raise ValidationError(
                    f"You're already at {goal_track.format_value(goal.current_value)}. "
                    "Set the goal beyond that, or log the progress that reaches it."
                )
        with self.db.transaction():
            goal = self.goals.update(
                goal_id,
                name=name,
                description=description.strip(),
                unit=unit.strip(),
                target_value=target_value,
                reward_id=reward_id,
                pool_type=pool_type,
                world_id=world_id,
            )
            leg = self.goals.active_leg(goal_id)
            if target_changed and leg is not None:
                self.goals.set_leg_target(leg.id, target_value)
            return self._view(goal)

    # -- progress ----------------------------------------------------------

    def log_progress(self, goal_id: str, delta: float) -> ProgressResult:
        """Move the current value by ``delta`` (negative moves away from the
        goal). Any entry, including zero, counts as the weekly review."""
        delta = self._require_number(delta, "The change")
        today = self.clock.today()
        with self.db.transaction():
            goal = self.goals.get(goal_id)
            if goal.status == GoalStatus.REACHED:
                raise ValidationError(
                    "This goal is reached. Extend the path or finish it first."
                )
            if goal.status != GoalStatus.ACTIVE:
                raise ValidationError("This goal is no longer running.")
            leg = self._active_leg_with_character(goal)
            before = goal.current_value
            after = before + delta
            baseline, target = goal.baseline_value, goal.target_value
            section_before = goal_track.section(baseline, target, before)
            previous_character = leg.character_id
            character_id = leg.character_id
            chest = None
            fields: dict[str, object] = {"current_value": after, "last_reviewed_on": today}

            if goal_track.is_reached(baseline, target, after):
                outcome = GoalEntryOutcome.REACHED
                fields["status"] = GoalStatus.REACHED
                chest = self.chest_service.grant_for_goal(goal.reward_id, leg.id)
                section_after = 10
                logger.info("Goal %s reached", goal.name)
            elif goal_track.is_behind_baseline(baseline, target, after):
                outcome = GoalEntryOutcome.REBASED
                # End the leg first so its character is free again: if nobody
                # else can take over, the same character starts the new track.
                self.goals.end_leg(leg.id, GoalLegEndReason.REBASED, today, after)
                character_id = self._draw_character(goal, exclude=leg.character_id)
                self.goals.create_leg(goal.id, character_id, after, target, today)
                fields["baseline_value"] = after
                section_after = 1
                logger.info("Goal %s slipped past its start; rebased at %s", goal.name, after)
            else:
                outcome = GoalEntryOutcome.PROGRESS
                section_after = goal_track.section(baseline, target, after)

            entry = self.goals.add_entry(
                goal_id=goal.id,
                leg_id=leg.id,
                delta=delta,
                value_before=before,
                value_after=after,
                outcome=outcome,
                previous_reviewed_on=goal.last_reviewed_on,
                entered_on=today,
            )
            self.goals.update(goal.id, **fields)
            return ProgressResult(
                entry=entry,
                section_before=section_before,
                section_after=section_after,
                reached=outcome is GoalEntryOutcome.REACHED,
                rebased=outcome is GoalEntryOutcome.REBASED,
                chest=chest,
                previous_character_id=previous_character,
                character_id=character_id,
            )

    def undoable_entry(self, goal_id: str) -> GoalEntry | None:
        """The goal's latest entry, when it was logged today and the goal has
        not moved on since (extended, finished or removed)."""
        goal = self.goals.get(goal_id)
        entries = self.goals.entries_for_goal(goal_id, limit=1)
        if not entries or entries[0].entered_on != self.clock.today():
            return None
        entry = entries[0]
        leg = self.goals.active_leg(goal_id)
        if leg is None:
            return None
        if entry.outcome is GoalEntryOutcome.REACHED:
            return entry if goal.status == GoalStatus.REACHED and leg.id == entry.leg_id else None
        if goal.status != GoalStatus.ACTIVE:
            return None
        if entry.outcome is GoalEntryOutcome.REBASED:
            return entry if leg.id != entry.leg_id else None
        return entry if leg.id == entry.leg_id else None

    def undo_last_entry(self, goal_id: str) -> GoalEntry:
        """Take back today's latest entry: the value, the review date, and
        whatever it caused — a chest (refused once claimed) or a new leg (the
        old one returns if its character is still free)."""
        with self.db.transaction():
            entry = self.undoable_entry(goal_id)
            if entry is None:
                raise UndoNotAllowedError(
                    "Only today's latest entry can be undone, before the goal moves on."
                )
            fields: dict[str, object] = {
                "current_value": entry.value_before,
                "last_reviewed_on": entry.previous_reviewed_on,
            }
            if entry.outcome is GoalEntryOutcome.REACHED:
                self.chest_service.revoke_for_goal_leg(entry.leg_id)
                fields["status"] = GoalStatus.ACTIVE
            elif entry.outcome is GoalEntryOutcome.REBASED:
                new_leg = self.goals.active_leg(goal_id)
                assert new_leg is not None
                self.goals.delete_leg(new_leg.id)
                old_leg = self.goals.get_leg(entry.leg_id)
                if old_leg.character_id and self.goals.active_leg_for_character(
                    old_leg.character_id
                ):
                    raise UndoNotAllowedError(
                        "The character who carried this goal before has taken on "
                        "another goal, so the slip can't be undone."
                    )
                self.goals.reopen_leg(old_leg.id)
                fields["baseline_value"] = old_leg.baseline_value
            self.goals.delete_entry(entry.id)
            self.goals.update(goal_id, **fields)
            return entry

    # -- reaching the end --------------------------------------------------

    def extend(
        self, goal_id: str, target_value: float, reward_id: str | None
    ) -> GoalView:
        """Carry a reached goal further: a new character walks a fresh track
        from where you are now to the new target."""
        target_value = self._require_number(target_value, "The new goal")
        self._require_reward(reward_id)
        today = self.clock.today()
        with self.db.transaction():
            goal = self.goals.get(goal_id)
            if goal.status != GoalStatus.REACHED:
                raise ValidationError("Only a reached goal can be extended.")
            if target_value == goal.current_value:
                raise ValidationError(
                    f"You're already at {goal_track.format_value(goal.current_value)}. "
                    "Set the new goal somewhere else."
                )
            leg = self.goals.active_leg(goal_id)
            previous = None
            if leg is not None:
                previous = leg.character_id
                self.goals.end_leg(leg.id, GoalLegEndReason.REACHED, today, goal.current_value)
            goal = self.goals.update(
                goal_id,
                baseline_value=goal.current_value,
                target_value=target_value,
                reward_id=reward_id,
                status=GoalStatus.ACTIVE,
                last_reviewed_on=today,
            )
            character_id = self._draw_character(goal, exclude=previous)
            self.goals.create_leg(goal.id, character_id, goal.current_value, target_value, today)
            return self._view(goal)

    def finish(self, goal_id: str) -> GoalView:
        with self.db.transaction():
            goal = self.goals.get(goal_id)
            if goal.status != GoalStatus.REACHED:
                raise ValidationError("A goal is finished once it is reached.")
            leg = self.goals.active_leg(goal_id)
            if leg is not None:
                self.goals.end_leg(
                    leg.id, GoalLegEndReason.REACHED, self.clock.today(), goal.current_value
                )
            goal = self.goals.update(
                goal_id, status=GoalStatus.FINISHED, finished_at=self.clock.now()
            )
            return self._view(goal)

    def remove(self, goal_id: str) -> None:
        """Delete a goal outright, or hide it when it has earned a chest so
        that chest keeps its history."""
        with self.db.transaction():
            goal = self.goals.get(goal_id)
            if self.goals.has_chests(goal_id):
                leg = self.goals.active_leg(goal_id)
                if leg is not None:
                    self.goals.end_leg(
                        leg.id, GoalLegEndReason.REMOVED, self.clock.today(),
                        goal.current_value,
                    )
                self.goals.update(goal_id, status=GoalStatus.REMOVED)
            else:
                self.goals.delete(goal_id)

    # -- characters --------------------------------------------------------

    def release_character(self, character_id: str) -> None:
        """A goal character became unavailable (archived): hand its goal to
        another character on the same track, or leave it waiting for one."""
        leg = self.goals.active_leg_for_character(character_id)
        if leg is None:
            return
        goal = self.goals.get(leg.goal_id)
        replacement = self._draw_character(goal, exclude=character_id)
        self.goals.set_leg_character(leg.id, replacement)
        logger.info(
            "Goal %s lost character %s; replaced by %s", goal.name, character_id, replacement
        )

    def assign_waiting_characters(self) -> int:
        """Give a character to goals left without one. Returns how many were
        filled."""
        filled = 0
        with self.db.transaction():
            for leg in self.goals.legs_without_character():
                character_id = self._draw_character(self.goals.get(leg.goal_id), exclude=None)
                if character_id is not None:
                    self.goals.set_leg_character(leg.id, character_id)
                    filled += 1
        return filled

    def _active_leg_with_character(self, goal: Goal) -> GoalLeg:
        leg = self.goals.active_leg(goal.id)
        if leg is None:  # defensive: every running goal has a leg
            leg = self.goals.create_leg(
                goal.id, None, goal.baseline_value, goal.target_value, self.clock.today()
            )
        if leg.character_id is None:
            character_id = self._draw_character(goal, exclude=None)
            if character_id is not None:
                self.goals.set_leg_character(leg.id, character_id)
                leg = self.goals.get_leg(leg.id)
        return leg

    def _draw_character(self, goal: Goal, exclude: str | None) -> str | None:
        pool = self.characters.goal_eligible_character_ids(goal.pool_type, goal.world_id)
        if exclude is not None:
            pool = [cid for cid in pool if cid != exclude] or pool
        return self.rng.choice(pool) if pool else None

    def _pool_description(self, goal: Goal) -> str:
        if goal.pool_type == PoolType.SPECIFIC_WORLD and goal.world_id:
            world = self.worlds.find(goal.world_id)
            return f"the world '{world.name}'" if world else "the selected world"
        return "any world"

    # -- validation --------------------------------------------------------

    @staticmethod
    def _require_name(name: str) -> str:
        name = name.strip()
        if not name:
            raise ValidationError("A goal needs a name.")
        return name

    @staticmethod
    def _require_number(value: float, label: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{label} has to be a number.") from None
        if not math.isfinite(number):
            raise ValidationError(f"{label} has to be a number.")
        return number

    def _require_reward(self, reward_id: str | None) -> None:
        if not reward_id:
            raise ValidationError(
                "Pick the reward waiting at the end. Add one on the Vice Chests screen "
                "if the list is empty."
            )
        try:
            reward = self.chests.get_reward(reward_id)
        except KeyError:
            raise ValidationError("That reward no longer exists.") from None
        if reward.is_archived:
            raise ValidationError("That reward has been removed. Pick another one.")

    def _require_pool(self, pool_type: PoolType, world_id: str | None) -> str | None:
        if pool_type == PoolType.ALL_WORLDS:
            return None
        if not world_id or self.worlds.find(world_id) is None:
            raise ValidationError("Pick the world the goal's characters come from.")
        return world_id
