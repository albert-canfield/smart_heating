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
    light_off_min: float = 30.0,
) -> bool:
    """Debounced occupancy.

    Presence sensors decide; without one the lights do; without either, the card's Heat now (and the schedule).
    Presence or media: in use once held on for join_min, until leave_min after it goes off.
    Lights, only in a room with no presence sensor: in use while one is on, and for light_off_min after it goes
    off (on and straight off counts too). That only once the room was in use: after a restart every light looks
    freshly switched.
    """
    strong = presence + media
    if was_occupied and (any(s.is_on for s in strong) or any(_recently_off(s, now, leave_min) for s in strong)):
        return True
    if any(_held_on(s, now, join_min) for s in strong):
        return True
    if presence:
        return False  # a presence sensor decides on its own: lights don't count
    return any(s.is_on or (was_occupied and _recently_off(s, now, light_off_min)) for s in lights)
