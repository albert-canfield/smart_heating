"""Plain data models for the decision core. No Home Assistant imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Mode(str, Enum):
    OFF = "off"
    ONE_CYCLE = "one_cycle"
    CONTINUOUS = "continuous"


class Level(str, Enum):
    """Voice 1 need level, highest first."""

    SAFETY = "safety"
    COMFORT = "comfort"
    BASELINE = "baseline"
    NONE = "none"


class Verdict(str, Enum):
    """Voice 2 outcome for a room."""

    APPROVED = "approved"
    PIGGYBACK = "piggyback"
    DEFERRED = "deferred"
    VETOED = "vetoed"
    IDLE = "idle"
    FAULT = "fault"


class Priority(str, Enum):
    A = "a"  # living, kitchen, bedrooms, bathrooms
    B = "b"  # office, play room
    C = "c"  # transit, service


class Override(str, Enum):
    AUTO = "auto"
    HEAT = "heat"  # heat now, expires
    OFF = "off"  # off until expiry


@dataclass(frozen=True)
class Settings:
    baseline_day: float = 17.0
    baseline_night: float = 15.0
    safety: float = 12.0
    season_gate: float = 14.0
    hysteresis: float = 0.5
    overshoot: float = 0.1
    min_run_min: float = 10.0
    min_off_min: float = 10.0
    coast_rate: float = 0.3  # degC/h considered "rising on its own"
    coast_horizon_min: float = 90.0
    stack_max_wait_min: float = 40.0
    stack_small_deficit: float = 1.0
    batch_min_deficit: float = 1.0  # must exceed hysteresis to have any effect
    hw_priority: bool = True
    hw_max_pause_min: float = 45.0
    trv_open_offset: float = 3.0
    trv_closed: float = 5.0


@dataclass(frozen=True)
class RoomConfig:
    room_id: str
    name: str
    floor: int  # 0 = ground, higher = upstairs
    priority: Priority = Priority.A
    comfort: float = 19.0
    has_trv: bool = True
    radiator: bool = True  # has a radiator on the boiler circuit
    heater: bool = False  # has electric heater(s) Smart Heating can switch


@dataclass
class RoomSnapshot:
    temp: float | None
    trend: float | None = None  # degC/h, None if unknown
    occupied: bool = False
    scheduled: bool = False
    lights_on: bool = False
    override: Override = Override.AUTO
    valve_open: bool | None = None
    heater_on: bool | None = None
    prev_calling: bool = False
    deferred_min: float = 0.0  # how long this room has been deferred


@dataclass
class HouseSnapshot:
    now: datetime
    mode: Mode
    night: bool = False
    outdoor_mean: float | None = None
    hw_calling: bool = False
    hw_calling_min: float = 0.0  # minutes hot water has been calling
    boiler_on: bool = False
    boiler_state_min: float = 1e9  # minutes since boiler last changed state


@dataclass
class NeedResult:
    level: Level
    target: float | None
    calling: bool
    deficit: float  # target - temp (positive = too cold)
    reason: str


@dataclass
class RoomDecision:
    room_id: str
    need: NeedResult
    verdict: Verdict
    reason: str
    open_valve: bool | None = None  # None = leave as is
    heater_on: bool | None = None  # None = no heater


@dataclass
class Plan:
    boiler_on: bool
    rooms: dict[str, RoomDecision] = field(default_factory=dict)
    status: str = "idle"
    reason: str = ""

    @property
    def open_rooms(self) -> list[str]:
        return [r for r, d in self.rooms.items() if d.open_valve is True]

    @property
    def heater_rooms(self) -> list[str]:
        return [r for r, d in self.rooms.items() if d.heater_on is True]

    @property
    def close_rooms(self) -> list[str]:
        return [r for r, d in self.rooms.items() if d.open_valve is False]
