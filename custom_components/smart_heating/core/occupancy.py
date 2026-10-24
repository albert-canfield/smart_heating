"""Room occupancy from presence, media and light signals."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Signal:
    is_on: bool
    last_changed: datetime
    motion: bool = False  # a motion (PIR) sensor: one trigger stays on 1 to 3 min, so one alone is a walk-through
    triggers: int = 0  # motion only: its switch-ons in the last MOTION_WINDOW_MIN


JOIN_MIN = 1.0  # a presence sensor (or media playing) on this long marks the room in use: filters a walk-through
MOTION_TRIGGERS = 2  # a motion sensor marks the room in use after this many triggers within MOTION_WINDOW_MIN
MOTION_WINDOW_MIN = 10.0
MOTION_HOLD_MIN = 5.0  # or after this long on without a break (someone moving about)


def _held_on(sig: Signal, now: datetime, minutes: float) -> bool:
    return sig.is_on and now - sig.last_changed >= timedelta(minutes=minutes)


def _joins(sig: Signal, now: datetime, join_min: float) -> bool:
    if sig.motion:
        return sig.triggers >= MOTION_TRIGGERS or _held_on(sig, now, MOTION_HOLD_MIN)
    return _held_on(sig, now, join_min)


def join_at(sig: Signal) -> datetime | None:
    """When an on signal would mark the room in use with no further change (for a timely re-check)."""
    if not sig.is_on:
        return None
    return sig.last_changed + timedelta(minutes=MOTION_HOLD_MIN if sig.motion else JOIN_MIN)


def _recently_off(sig: Signal, now: datetime, minutes: float) -> bool:
    return (not sig.is_on) and now - sig.last_changed < timedelta(minutes=minutes)


def is_occupied(
    now: datetime,
    presence: list[Signal],
    media: list[Signal],
    lights: list[Signal],
    was_occupied: bool,
    join_min: float = JOIN_MIN,
    leave_min: float = 20.0,
    light_off_min: float = 30.0,
) -> bool:
    """Debounced occupancy.

    Presence sensors decide; without one the lights do; without either, the card's Heat now (and the schedule).
    Presence or media: in use once held on for join_min, until leave_min after it goes off. A motion sensor
    (device class motion) needs MOTION_TRIGGERS switch-ons within MOTION_WINDOW_MIN, or MOTION_HOLD_MIN on,
    since a single trigger keeps it on for 1 to 3 min: a walk-through.
    Lights, only in a room with no presence sensor: in use while one is on, and for light_off_min after it goes
    off (on and straight off counts too). That only once the room was in use: after a restart every light looks
    freshly switched.
    """
    strong = presence + media
    if was_occupied and (any(s.is_on for s in strong) or any(_recently_off(s, now, leave_min) for s in strong)):
        return True
    if any(_joins(s, now, join_min) for s in strong):
        return True
    if presence:
        return False  # a presence sensor decides on its own: lights don't count
    return any(s.is_on or (was_occupied and _recently_off(s, now, light_off_min)) for s in lights)
