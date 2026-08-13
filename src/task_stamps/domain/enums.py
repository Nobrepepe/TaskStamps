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
