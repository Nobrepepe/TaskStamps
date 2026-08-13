"""Point rewards for weighted task completions."""

from task_stamps.domain.enums import TaskWeight

_BASE = {
    TaskWeight.TRIVIAL: 0,
    TaskWeight.MINOR: 1,
    TaskWeight.MEDIUM: 2,
    TaskWeight.MAJOR: 3,
}

_THRESHOLDS = {
    5: {
        TaskWeight.TRIVIAL: 0,
        TaskWeight.MINOR: 2,
        TaskWeight.MEDIUM: 3,
        TaskWeight.MAJOR: 5,
    },
    10: {
        TaskWeight.TRIVIAL: 0,
        TaskWeight.MINOR: 3,
        TaskWeight.MEDIUM: 4,
        TaskWeight.MAJOR: 6,
    },
    15: {
        TaskWeight.TRIVIAL: 0,
        TaskWeight.MINOR: 5,
        TaskWeight.MEDIUM: 6,
        TaskWeight.MAJOR: 8,
    },
}


def reward_for(weight: TaskWeight, streak_number: int) -> int:
    """Return the reward for this completion, including threshold bonuses."""
    return _THRESHOLDS.get(streak_number, _BASE)[weight]
