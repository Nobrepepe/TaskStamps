"""Streak and Boss chests: the reward slots, grants, claims and revocations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from task_stamps.data.database import Database
from task_stamps.data.repositories.chests import ChestRepository
from task_stamps.domain.enums import CHEST_TIERS, CHEST_WEIGHTS, TaskWeight
from task_stamps.domain.exceptions import ValidationError
from task_stamps.domain.models import ViceChest, ViceReward
from task_stamps.utilities.clock import Clock
from task_stamps.utilities.logging_setup import get_logger
from task_stamps.utilities.rng import RandomProvider

logger = get_logger("chests")

#: Boss-chest rarity. The nine slot weights are weight_factor * tier_factor,
#: which sum to exactly 100 — so with every slot filled they read as percents:
#: Minor 36/18/6, Medium 18/9/3, Major 6/3/1 across streaks 5/10/15.
_WEIGHT_FACTOR = {TaskWeight.MINOR: 6, TaskWeight.MEDIUM: 3, TaskWeight.MAJOR: 1}
_TIER_FACTOR = {5: 6, 10: 3, 15: 1}


def slot_weight(weight: TaskWeight, tier: int) -> int:
    """Relative Boss-chest odds of one slot."""
    return _WEIGHT_FACTOR[weight] * _TIER_FACTOR[tier]


def weighted_pick(
    items: list[tuple[TaskWeight, int]], rng: RandomProvider
) -> tuple[TaskWeight, int]:
    """Pick one slot in proportion to its weight.

    Uses only `uniform`, so it stays inside the existing RandomProvider
    protocol and reproduces exactly under a seeded provider.
    """
    weights = [slot_weight(weight, tier) for weight, tier in items]
    draw = rng.uniform(0, float(sum(weights)))
    cumulative = 0.0
    for item, weight in zip(items, weights):
        cumulative += weight
        if draw < cumulative:
            return item
    return items[-1]


@dataclass(frozen=True)
class SlotView:
    """One of the nine (weight, tier) slots, with its rewards and chest counts."""

    weight: TaskWeight
    tier: int
    rewards: tuple[ViceReward, ...]
    chest_counts: tuple[int, ...]

    @property
    def unclaimed(self) -> int:
        return sum(self.chest_counts)


class ChestService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        rng: RandomProvider,
        chests: ChestRepository,
    ) -> None:
        self.db = db
        self.clock = clock
        self.rng = rng
        self.chests = chests

    # -- the editor --------------------------------------------------------

    def slots(self) -> list[SlotView]:
        counts = self.chests.unclaimed_counts()
        rewards = self.chests.list_rewards()
        views: list[SlotView] = []
        for weight in CHEST_WEIGHTS:
            for tier in CHEST_TIERS:
                in_slot = tuple(
                    reward
                    for reward in rewards
                    if reward.task_weight is weight and reward.tier == tier
                )
                views.append(
                    SlotView(
                        weight=weight,
                        tier=tier,
                        rewards=in_slot,
                        chest_counts=tuple(counts.get(r.id, 0) for r in in_slot),
                    )
                )
        return views

    def save_reward(
        self,
        reward_id: str | None,
        weight: TaskWeight,
        tier: int,
        name: str,
        description: str,
    ) -> ViceReward:
        name = name.strip()
        if not name:
            raise ValidationError("A reward needs a name.")
        if weight not in CHEST_WEIGHTS:
            raise ValidationError("Only Minor, Medium and Major tasks earn chests.")
        if tier not in CHEST_TIERS:
            raise ValidationError("Chests are earned at streaks 5, 10 and 15.")
        description = description.strip()
        if reward_id is None:
            return self.chests.create_reward(weight, tier, name, description)
        return self.chests.update_reward(reward_id, name, description, weight, tier)

    def remove_reward(self, reward_id: str) -> None:
        """Archive a reward that has chest history so past chests keep their
        name; delete it outright when nothing references it."""
        with self.db.transaction():
            if self.chests.has_chests(reward_id):
                self.chests.archive_reward(reward_id)
            else:
                self.chests.delete_reward(reward_id)

    def claim(self, reward_id: str) -> ViceChest:
        with self.db.transaction():
            chest = self.chests.claim_oldest(reward_id)
            if chest is None:
                raise ValidationError("There is no chest waiting for this reward.")
            return chest

    # -- unclaimed inventory ----------------------------------------------

    def unclaimed_total(self) -> int:
        return self.chests.unclaimed_total()

    def sealed_boss_count(self) -> int:
        return self.chests.sealed_boss_count()

    # -- grants (called inside the caller's transaction) -------------------

    def grant_for_completion(
        self, weight: TaskWeight, streak_number: int, completion_id: str
    ) -> ViceChest | None:
        """Grant the streak chest for this completion, if one is due.

        Returns None for Trivial tasks, for streaks that are not a milestone,
        and when the slot has no rewards defined yet.
        """
        if weight not in CHEST_WEIGHTS or streak_number not in CHEST_TIERS:
            return None
        rewards = self.chests.rewards_in_slot(weight, streak_number)
        if not rewards:
            return None
        reward = self.rng.choice(rewards)
        chest = self.chests.grant_streak_chest(reward, completion_id)
        logger.info(
            "Streak %s on a %s task earned a chest for %s",
            streak_number,
            weight.value,
            reward.name,
        )
        return chest

    def grant_boss_chest_if_defeated(
        self, day: date, defeated: bool
    ) -> ViceChest | None:
        """Grant the day's sealed Boss chest. Idempotent: the second call for
        a day returns None, so the insert itself is the 'newly defeated' event."""
        if not defeated:
            return None
        chest = self.chests.grant_boss_chest(day)
        if chest is not None:
            logger.info("Boss defeated on %s; sealed chest granted", day)
        return chest

    # -- revocations (undo) ------------------------------------------------

    def revoke_for_completion(self, completion_id: str) -> str | None:
        """Take back the chest a completion granted. Returns the reward name if
        one was revoked, or None if the completion never earned a chest."""
        chest = self.chests.chest_for_completion(completion_id)
        if chest is None:
            return None
        if chest.is_claimed:
            raise ValidationError(
                f"The chest this completion earned ({chest.reward_name_snapshot}) "
                "has already been claimed, so it cannot be undone."
            )
        self.chests.delete_chest(chest.id)
        return chest.reward_name_snapshot

    def revoke_boss_chest(self, day: date) -> bool:
        """Take back the day's Boss chest once the Boss is no longer defeated."""
        chest = self.chests.boss_chest_for(day)
        if chest is None:
            return False
        if not chest.is_sealed:
            raise ValidationError(
                "Today's Boss chest has already been opened, so this completion "
                "cannot be undone."
            )
        self.chests.delete_chest(chest.id)
        return True

    # -- opening a Boss chest ---------------------------------------------

    def open_boss_chest(self) -> ViceChest:
        """Unseal one Boss chest: roll a slot by difficulty, then a reward
        inside it, and claim that reward on the spot."""
        with self.db.transaction():
            chest = self.chests.oldest_sealed_boss_chest()
            if chest is None:
                raise ValidationError("You have no Boss chests to open.")
            filled = [
                (weight, tier)
                for weight in CHEST_WEIGHTS
                for tier in CHEST_TIERS
                if self.chests.rewards_in_slot(weight, tier)
            ]
            if not filled:
                raise ValidationError(
                    "Add at least one reward before opening a Boss chest."
                )
            weight, tier = weighted_pick(filled, self.rng)
            reward = self.rng.choice(self.chests.rewards_in_slot(weight, tier))
            opened = self.chests.open_boss_chest(chest.id, reward)
            logger.info("Boss chest opened: %s", reward.name)
            return opened
