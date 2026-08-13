"""Domain-specific exceptions.

Every exception carries a user-presentable message so the interface layer
never has to expose raw tracebacks.
"""

from __future__ import annotations


class TaskStampsError(Exception):
    """Base class for expected application errors."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class ValidationError(TaskStampsError):
    pass


class NoEligibleCharacterError(TaskStampsError):
    def __init__(self, pool_description: str) -> None:
        super().__init__(
            "No character is available: all eligible characters in "
            f"{pool_description} are already assigned or incomplete."
        )
        self.pool_description = pool_description


class TaskNotActiveError(TaskStampsError):
    def __init__(self) -> None:
        super().__init__("This task is not active, so it cannot be completed.")


class TaskPausedError(TaskStampsError):
    def __init__(self) -> None:
        super().__init__("This task is paused. Resume it before completing.")


class NotScheduledTodayError(TaskStampsError):
    def __init__(self) -> None:
        super().__init__("This task is not scheduled for today.")


class AlreadyCompletedTodayError(TaskStampsError):
    def __init__(self) -> None:
        super().__init__("This task was already completed today.")


class NoActiveAssignmentError(TaskStampsError):
    def __init__(self) -> None:
        super().__init__("This task has no assigned character.")


class StampUnavailableError(TaskStampsError):
    def __init__(self) -> None:
        super().__init__("The required stamp image is missing for the assigned character.")


class UndoNotAllowedError(TaskStampsError):
    pass


class AssetImportError(TaskStampsError):
    pass


class AssetInUseError(TaskStampsError):
    pass


class BackupError(TaskStampsError):
    pass


class PoolChangeConflictError(TaskStampsError):
    def __init__(self) -> None:
        super().__init__(
            "The new character pool does not include the currently assigned "
            "character. Archive the task or end its assignment explicitly first."
        )


class CharacterEditError(TaskStampsError):
    pass


class WorldArchiveError(TaskStampsError):
    pass


class DataAccessError(TaskStampsError):
    pass
