"""Heat retention (insulation) index from learned time constants.

tau (hours) is how long a room takes to lose ~63% of its temperature lead over
outside with the heating off. Longer = better retention. It reflects fabric,
glazing and draughts, but also heat shared with neighbouring rooms (upper floors
benefit from rising heat), so it is a comparative indicator, not an EPC.
"""
from __future__ import annotations

import math

# (minimum tau in hours, grade)
GRADES = [(120, "A"), (80, "B"), (55, "C"), (40, "D"), (28, "E"), (18, "F"), (0, "G")]
GRADE_TEXT = {
    "A": "excellent",
    "B": "very good",
    "C": "good",
    "D": "average",
    "E": "below average",
    "F": "poor",
    "G": "very poor",
}
TAU_LOW, TAU_HIGH = 10.0, 200.0


def score(tau: float | None) -> int | None:
    """0-100, logarithmic between 10 h (0) and 200 h (100)."""
    if tau is None or tau <= 0:
        return None
    s = 100 * math.log(tau / TAU_LOW) / math.log(TAU_HIGH / TAU_LOW)
    return int(round(min(100, max(0, s))))


def grade(tau: float | None) -> str | None:
    if tau is None:
        return None
    for floor, g in GRADES:
        if tau >= floor:
            return g
    return "G"


def loss_per_hour(tau: float | None, delta: float = 10.0) -> float | None:
    """Initial temperature drop per hour when it is `delta` degrees colder outside."""
    if tau is None or tau <= 0:
        return None
    return round(delta / tau, 2)


def combine(taus: list[float]) -> float | None:
    """Group value: median, robust to one odd room."""
    vals = sorted(t for t in taus if t)
    if not vals:
        return None
    mid = len(vals) // 2
    return round(vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2, 1)


def describe(tau: float | None) -> dict:
    g = grade(tau)
    return {
        "score": score(tau),
        "grade": g,
        "rating": GRADE_TEXT.get(g) if g else None,
        "time_constant_h": tau,
        "loss_per_hour_at_10c": loss_per_hour(tau),
    }
