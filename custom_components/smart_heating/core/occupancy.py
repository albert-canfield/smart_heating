"""Room occupancy from presence, media and light signals."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Signal:
    is_on: bool
    last_changed: datetime


def _held_on(sig: Signal, now: datetime, minutes: float) -> bool:
    return sig.is_on and now - sig.last_changed >= timedelta(minutes=minutes)


def _recently_off(sig: Signal, now: datetime, minutes: float) -> bool:
    return (not sig.is_on) and now - sig.last_changed < timedelta(minutes=minutes)


def is_occupied(
    now: datetime,
    presence: list[Signal],
    media: list[Signal],
    lights: list[Signal],
    was_occupied: bool,
    join_min: float = 5.0,
    leave_min: float = 20.0,
    light_max_min: float = 30.0,
) -> bool:
    """Debounced occupancy.

    Join: presence or media held on for join_min, or a light switched on
    within light_max_min (a light alone never keeps a room occupied longer).
    Stay: any presence/media on, or switched off less than leave_min ago.
    """
    strong = presence + media
    if was_occupied:
        if any(s.is_on for s in strong):
            return True
        if any(_recently_off(s, now, leave_min) for s in strong):
            return True
        return any(
            s.is_on and now - s.last_changed < timedelta(minutes=light_max_min)
            for s in lights
        )
    if any(_held_on(s, now, join_min) for s in strong):
        return True
    return any(
        s.is_on and now - s.last_changed < timedelta(minutes=light_max_min)
        for s in lights
    )
