"""User setpoints: one house target that shifts every room, plus per-room fine-tuning.

The house target starts at a reference (the typical comfort of the main rooms).
Moving it by +1 raises every room's comfort and the day/night baselines by 1.
A room's own setpoint is stored relative to the house, so it keeps its
difference when the house target moves. Safety (frost) never moves.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from statistics import median

from .models import Priority, RoomConfig, Settings


def _r(v: float) -> float:
    return round(v * 2) / 2


@dataclass
class Setpoints:
    reference: float = 19.0
    house: float = 19.0
    # room_id -> {"base": comfort before the house offset, "cfg": configured comfort when set}
    rooms: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def initial(cls, cfgs: list[RoomConfig]) -> "Setpoints":
        main = [c.comfort for c in cfgs if c.priority is Priority.A] or [c.comfort for c in cfgs]
        ref = _r(median(main)) if main else 19.0
        return cls(reference=ref, house=ref)

    @property
    def offset(self) -> float:
        return round(self.house - self.reference, 2)

    def base(self, cfg: RoomConfig) -> float:
        own = self.rooms.get(cfg.room_id)
        # A changed comfort in the room's Reconfigure form wins over an old card setting.
        if own and own.get("cfg") == cfg.comfort:
            return float(own["base"])
        return cfg.comfort

    def comfort(self, cfg: RoomConfig) -> float:
        return round(self.base(cfg) + self.offset, 2)

    def is_custom(self, cfg: RoomConfig) -> bool:
        return abs(self.base(cfg) - cfg.comfort) > 1e-6

    def set_room(self, cfg: RoomConfig, value: float) -> None:
        self.rooms[cfg.room_id] = {"base": round(value - self.offset, 2), "cfg": cfg.comfort}

    def reset_room(self, cfg: RoomConfig) -> None:
        self.rooms.pop(cfg.room_id, None)

    def room_cfg(self, cfg: RoomConfig) -> RoomConfig:
        return replace(cfg, comfort=self.comfort(cfg))

    def settings(self, s: Settings) -> Settings:
        off = self.offset
        if not off:
            return s
        return replace(
            s,
            baseline_day=max(s.safety, s.baseline_day + off),
            baseline_night=max(s.safety, s.baseline_night + off),
        )

    def to_dict(self) -> dict:
        return {"reference": self.reference, "house": self.house, "rooms": self.rooms}

    @classmethod
    def from_dict(cls, d: dict) -> "Setpoints":
        return cls(float(d["reference"]), float(d["house"]), dict(d.get("rooms", {})))
