"""Voice 1: does this room need heat?"""
from __future__ import annotations

from .models import (
    HouseSnapshot,
    Level,
    Mode,
    NeedResult,
    Override,
    RoomConfig,
    RoomSnapshot,
    Settings,
)


def evaluate_need(
    cfg: RoomConfig, snap: RoomSnapshot, house: HouseSnapshot, s: Settings
) -> NeedResult:
    if snap.temp is None:
        return NeedResult(Level.NONE, None, False, 0.0, "sensor unavailable")

    # Candidate targets, each tagged with its level.
    candidates: list[tuple[float, Level, str]] = [(s.safety, Level.SAFETY, "frost/damp floor")]

    if house.mode is not Mode.OFF and snap.override is not Override.OFF:
        base = s.baseline_night if house.night else s.baseline_day
        candidates.append((base, Level.BASELINE, "night baseline" if house.night else "baseline"))

        eligible, why = _eligible(snap, house)
        if eligible:
            candidates.append((cfg.comfort, Level.COMFORT, why))

    target, level, why = max(candidates, key=lambda c: c[0])
    deficit = round(target - snap.temp, 2)

    # Hysteresis: start below target - h, stop at target + overshoot.
    if snap.prev_calling:
        calling = snap.temp < target + s.overshoot
    else:
        calling = snap.temp <= target - s.hysteresis

    if not calling:
        return NeedResult(Level.NONE, target, False, deficit, f"at target ({why})")
    if snap.temp < s.safety:
        # Below the frost/damp floor: always safety, whatever the target.
        return NeedResult(Level.SAFETY, target, True, deficit, "below safety floor")
    return NeedResult(level, target, True, deficit, why)


def _eligible(snap: RoomSnapshot, house: HouseSnapshot) -> tuple[bool, str]:
    if snap.override is Override.HEAT:
        return True, "manual heat"
    if house.night:
        # Night: comfort only where lights are on (going to bed, reading).
        if snap.lights_on:
            return True, "night, lights on"
        return False, ""
    if snap.occupied:
        return True, "occupied"
    if snap.scheduled:
        return True, "scheduled"
    return False, ""
