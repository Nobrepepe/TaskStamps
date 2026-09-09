"""Domain models mapped 1:1 to database rows (plus one view model)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from task_stamps.domain.enums import (
    AssignmentEndReason,
    AssetType,
    CharacterStatus,
    ChestSource,
    PoolType,
    TaskStatus,
    TaskWeight,
)


@dataclass
class World:
    id: str
    name: str
    description: str
    cover_asset_version_id: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class Character:
    id: str
    world_id: str
    name: str
    description: str
    portrait_asset_version_id: str | None
    boss_image_asset_version_id: str | None
    boss_sound_asset_version_id: str | None
    default_sound_asset_version_id: str | None
    status: CharacterStatus
    is_archived: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class CharacterStamp:
    id: str
    character_id: str
    sequence_number: int
    image_asset_version_id: str | None
    sound_asset_version_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class HabitTask:
    id: str
    name: str
    description: str
    weekday_mask: int  # bit 0 = Monday ... bit 6 = Sunday
    pool_type: PoolType
    world_id: str | None
    status: TaskStatus
    weight: TaskWeight
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass
class CharacterAssignment:
    id: str
    task_id: str
    character_id: str
    current_streak: int
    started_on: date
    ended_on: date | None
    end_reason: AssignmentEndReason | None
    dropped_due_date: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class TaskCompletion:
    id: str
    task_id: str
    assignment_id: str
    character_id: str
    stamp_id: str
    completion_date: date
    completed_at: datetime
    streak_number: int
    task_name_snapshot: str
    character_name_snapshot: str
    world_name_snapshot: str
    is_reversed: bool
    reversed_at: datetime | None


@dataclass
class StampPlacement:
    id: str
    completion_id: str
    board_date: date
    x_normalized: float
    y_normalized: float
    rotation_degrees: float
    scale: float
    z_index: int
    image_asset_version_id: str
    sound_asset_version_id: str | None
    created_at: datetime


@dataclass
class PausePeriod:
    id: str
    task_id: str
    started_on: date
    ended_on: date | None


@dataclass
class Asset:
    id: str
    asset_type: AssetType
    current_version_id: str | None
    created_at: datetime


@dataclass
class AssetVersion:
    id: str
    asset_id: str
    relative_path: str
    file_name: str
    mime_type: str
    file_size: int
    checksum: str
    created_at: datetime


@dataclass
class ViceReward:
    """One user-defined reward living in a (weight, streak tier) slot."""

    id: str
    task_weight: TaskWeight
    tier: int
    name: str
    description: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class ViceChest:
    """An earned chest. Streak chests name their reward at grant time; a Boss
    chest stays sealed (no reward) until it is opened."""

    id: str
    source: ChestSource
    reward_id: str | None
    reward_name_snapshot: str | None
    completion_id: str | None
    boss_date: date | None
    granted_at: datetime
    claimed_at: datetime | None

    @property
    def is_claimed(self) -> bool:
        return self.claimed_at is not None

    @property
    def is_sealed(self) -> bool:
        return self.source is ChestSource.BOSS and self.reward_id is None


@dataclass
class BoardStamp:
    """Everything needed to render one stamp on a daily board (read model)."""

    placement: StampPlacement
    completion_id: str
    task_id: str
    completion_date: date
    completed_at: datetime
    streak_number: int
    task_name_snapshot: str
    character_name_snapshot: str
    image_relative_path: str
    sound_relative_path: str | None


@dataclass(frozen=True)
class DailyBoss:
    date: date
    character_id: str
    name: str
    world_name: str
    day_number: int
    image_relative_path: str
    sound_relative_path: str | None
    strikes_landed: int
    strikes_target: int

    @property
    def strikes_remaining(self) -> int:
        return max(0, self.strikes_target - self.strikes_landed)

    @property
    def defeated(self) -> bool:
        return self.strikes_target > 0 and self.strikes_landed >= self.strikes_target
