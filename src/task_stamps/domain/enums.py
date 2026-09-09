"""Domain enumerations."""

from __future__ import annotations

from enum import StrEnum

STAMPS_PER_CHARACTER = 15


class TaskStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class TaskWeight(StrEnum):
    TRIVIAL = "trivial"
    MINOR = "minor"
    MEDIUM = "medium"
    MAJOR = "major"


class ChestSource(StrEnum):
    STREAK = "streak"
    BOSS = "boss"


#: Streak milestones inside a character run that hand out a chest.
CHEST_TIERS = (5, 10, 15)

#: Weights that earn chests; Trivial tasks award stamps only.
CHEST_WEIGHTS = (TaskWeight.MINOR, TaskWeight.MEDIUM, TaskWeight.MAJOR)


class CharacterStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"


class PoolType(StrEnum):
    ALL_WORLDS = "all"
    SPECIFIC_WORLD = "world"


class AssignmentEndReason(StrEnum):
    COMPLETED = "completed"
    DROPPED = "dropped"
    ARCHIVED = "archived"
    REVERSED = "reversed"
    CHARACTER_UNAVAILABLE = "character_unavailable"
    POOL_CHANGED = "pool_changed"


class AssetType(StrEnum):
    WORLD_COVER = "world_cover"
    PORTRAIT = "portrait"
    BOSS_IMAGE = "boss_image"
    STAMP_IMAGE = "stamp_image"
    SOUND = "sound"


WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
