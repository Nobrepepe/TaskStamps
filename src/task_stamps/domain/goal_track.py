"""Pure goal-track arithmetic, shared by the service and the views.

A track runs from a baseline to a target in either direction and is cut into
ten equal sections. Section k (1-based) covers progress [(k-1)/10, k/10) and
shows ranked goal image k; the target itself is still section 10.
"""

from __future__ import annotations

import math

from task_stamps.domain.enums import GOAL_SECTIONS

# Float entries such as 0.1 + 0.2 must still land on a section edge.
_EPSILON = 1e-9


def progress(baseline: float, target: float, value: float) -> float:
    """Fraction of the way from baseline to target: 0 at the baseline, 1 at
    the target, negative past the baseline in the wrong direction."""
    return (value - baseline) / (target - baseline)


def is_reached(baseline: float, target: float, value: float) -> bool:
    return progress(baseline, target, value) >= 1 - _EPSILON


def is_behind_baseline(baseline: float, target: float, value: float) -> bool:
    return progress(baseline, target, value) < -_EPSILON


def section(baseline: float, target: float, value: float) -> int:
    """The 1-based section (and goal image rank) the value sits in."""
    fraction = progress(baseline, target, value)
    return max(1, min(GOAL_SECTIONS, math.floor(fraction * GOAL_SECTIONS + _EPSILON) + 1))


def format_value(value: float) -> str:
    """Up to two decimals, without trailing zeros: 82.50 -> 82.5, 3.0 -> 3."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text
