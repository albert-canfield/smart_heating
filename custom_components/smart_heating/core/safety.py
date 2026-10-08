"""Electric heater precautions. They only ever keep a heater off, never switch one on.

A heater runs only with a live temperature reading behind it: a thermometer that stops
reporting often keeps its last value instead of going unavailable, and a heater driven by a
frozen low reading would never stop. So a heater stays off when:
  - the room's reading hasn't been reported for STALE (dead battery, out of range),
  - it has been on for STUCK and the reading hasn't moved at all (stuck sensor, or the
    heater isn't heating),
  - the room is at its ceiling: target + OVER_TARGET, and never above CEILING,
  - it has run MAX_RUN without a break: then it rests for REST,
  - Home Assistant has only just started (readings may not be live yet).
Radiators are not affected: a stale reading there wastes gas, while switching a radiator room
off could leave it without frost protection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

STALE = timedelta(minutes=60)
STUCK = timedelta(minutes=30)
MAX_RUN = timedelta(hours=2)
REST = timedelta(minutes=15)
CEILING = 24.0
OVER_TARGET = 1.0
MOVED = 0.05  # degC: any change in the reading counts as movement


@dataclass
class HeaterWatch:
    """Per room: how long its heater has been on, and what the reading was then."""

    on_since: datetime | None = None
    temp_at_on: float | None = None
    rest_until: datetime | None = None
    stuck_at: float | None = None  # reading when it was found stuck: cleared once the reading moves

    def update(self, now: datetime, heater_on: bool, temp: float | None) -> None:
        if heater_on and self.on_since is None:
            self.on_since, self.temp_at_on = now, temp
        elif not heater_on:
            self.on_since = self.temp_at_on = None
        if self.stuck_at is not None and temp is not None and abs(temp - self.stuck_at) >= MOVED:
            self.stuck_at = None


@dataclass(frozen=True)
class Block:
    kind: str  # starting, no_reading, stale, stuck, rest, ceiling
    reason: str

    @property
    def shown(self) -> bool:
        """Worth showing on the card: not the everyday ceiling or the start-up wait."""
        return self.kind not in ("ceiling", "starting")

    @property
    def alert(self) -> bool:
        """Worth a phone alert: the heater was stopped because something looks wrong."""
        return self.kind in ("no_reading", "stale", "stuck", "rest")


def heater_block(now: datetime, w: HeaterWatch, temp: float | None, reported_at: datetime | None,
                 target: float | None, heater_on: bool, starting: bool = False) -> Block | None:
    """Why this room's heater must stay off now; None when it may run."""
    if starting:
        return Block("starting", "starting up: waiting for live readings")
    if temp is None:
        return Block("no_reading", "no temperature reading")
    if reported_at is None or now - reported_at > STALE:
        return Block("stale", f"no temperature reading for {int(STALE.total_seconds() // 60)} min")
    if w.stuck_at is not None:
        return Block("stuck", f"the temperature did not move in {int(STUCK.total_seconds() // 60)} min with the heater on")
    if heater_on and w.on_since and now - w.on_since >= STUCK and w.temp_at_on is not None \
            and abs(temp - w.temp_at_on) < MOVED:
        w.stuck_at = temp
        return Block("stuck", f"the temperature did not move in {int(STUCK.total_seconds() // 60)} min with the heater on")
    if w.rest_until and now < w.rest_until:
        return Block("rest", f"resting after {int(MAX_RUN.total_seconds() // 3600)} h on")
    if heater_on and w.on_since and now - w.on_since >= MAX_RUN:
        w.rest_until = now + REST
        return Block("rest", f"resting after {int(MAX_RUN.total_seconds() // 3600)} h on")
    cap = min(CEILING, (target if target is not None else CEILING) + OVER_TARGET)
    if temp >= cap:
        return Block("ceiling", f"at its {cap:.1f}° ceiling")
    return None
