"""Domain models mapped 1:1 to database rows (plus one view model)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from task_stamps.domain.enums import (
    AssignmentEndReason,
    AssetType,
    CharacterStatus,
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
    reward_points: int
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
class ViceOffering:
    id: str
    name: str
    description: str
    price: int
    quantity: int
    created_at: datetime
    updated_at: datetime


@dataclass
class ViceClaim:
    id: str
    offering_id: str | None
    offering_name_snapshot: str
    price_paid: int
    claimed_at: datetime


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
