"""Per-room thermal learning and prediction.

Model (first order, lumped):
    dTin/dt = -k * (Tin - Tout - G)        heating off
where k = 1/tau (per hour) and G is the free-heat lift (people, sun, cooking,
heat from other rooms). A straight-line fit of y = dTin/dt against
x = Tin - Tout over free-running intervals gives slope -k and intercept k*G.

Warm-up rate is the mean rise (degC/h) over intervals with the boiler running
and the room's radiator open.

Over a night or two, Tin - Tout barely varies, so the slope alone is poorly
determined. A prior anchors the line at a typical free-heat lift (the room stops
cooling PRIOR_GAIN above outside) and fades out as real variety builds up.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum


class Phase(str, Enum):
    FREE = "free"  # boiler off long enough that radiators are cold
    HEAT = "heat"  # boiler running, this room's radiator open
    OTHER = "other"  # transition or mixed, ignored


SAMPLE_MIN = 15.0
FREE_NEEDED = 96  # 24 h of free-running samples
FREE_SPREAD_NEEDED = 2.0  # degC range of (Tin - Tout) seen
HEAT_NEEDED = 8  # 2 h of heating samples
TAU_RANGE = (5.0, 400.0)  # plausible hours
PRIOR_GAIN = 1.5  # degC: typical free-heat lift (people, sun, neighbouring rooms)
PRIOR_WEIGHT = 8.0  # samples' worth while the data barely varies
PRIOR_FADE = 6.0  # degC of (Tin - Tout) variety at which the prior has faded out


@dataclass
class Fit:
    n: int = 0
    sx: float = 0.0
    sy: float = 0.0
    sxx: float = 0.0
    sxy: float = 0.0
    xmin: float = math.inf
    xmax: float = -math.inf

    def add(self, x: float, y: float) -> None:
        self.n += 1
        self.sx += x
        self.sy += y
        self.sxx += x * x
        self.sxy += x * y
        self.xmin = min(self.xmin, x)
        self.xmax = max(self.xmax, x)

    def line(self, prior: tuple[float, float] | None = None) -> tuple[float, float] | None:
        """Least-squares slope and intercept; `prior` = (x, weight) adds that many points at (x, 0)."""
        if self.n < 3:
            return None
        x0, w = prior if prior else (0.0, 0.0)
        n, sx, sxx = self.n + w, self.sx + w * x0, self.sxx + w * x0 * x0
        den = n * sxx - sx**2
        if den <= 1e-9:
            return None
        slope = (n * self.sxy - sx * self.sy) / den
        return slope, (self.sy - slope * sx) / n

    @property
    def spread(self) -> float:
        return self.xmax - self.xmin if self.n else 0.0


@dataclass
class RoomModel:
    free: Fit
    heat_n: int = 0
    heat_sum: float = 0.0
    # Open segment (not persisted meaningfully across restarts).
    seg_phase: str | None = None
    seg_start: str | None = None  # iso
    seg_tin: float | None = None
    seg_tout_sum: float = 0.0
    seg_tout_n: int = 0

    @classmethod
    def new(cls) -> "RoomModel":
        return cls(free=Fit())

    # ---------- learning ----------

    def observe(self, now: datetime, tin: float | None, tout: float | None, phase: Phase) -> bool:
        """Feed one tick. Returns True when a sample was recorded."""
        if tin is None or (phase is Phase.FREE and tout is None) or phase is Phase.OTHER:
            self._reset()
            return False
        if self.seg_phase != phase.value or self.seg_start is None:
            self._open(now, tin, phase)
            if tout is not None:
                self.seg_tout_sum, self.seg_tout_n = tout, 1
            return False
        if tout is not None:
            self.seg_tout_sum += tout
            self.seg_tout_n += 1
        start = datetime.fromisoformat(self.seg_start)
        hours = (now - start).total_seconds() / 3600
        if hours * 60 < SAMPLE_MIN:
            return False
        rate = (tin - self.seg_tin) / hours
        if phase is Phase.FREE:
            tout_mean = self.seg_tout_sum / max(self.seg_tout_n, 1)
            x = (tin + self.seg_tin) / 2 - tout_mean
            self.free.add(x, rate)
        else:
            self.heat_n += 1
            self.heat_sum += rate
        self._open(now, tin, phase)
        if tout is not None:
            self.seg_tout_sum, self.seg_tout_n = tout, 1
        return True

    def _open(self, now: datetime, tin: float, phase: Phase) -> None:
        self.seg_phase, self.seg_start, self.seg_tin = phase.value, now.isoformat(), tin
        self.seg_tout_sum, self.seg_tout_n = 0.0, 0

    def _reset(self) -> None:
        self.seg_phase = self.seg_start = self.seg_tin = None
        self.seg_tout_sum, self.seg_tout_n = 0.0, 0

    # ---------- results ----------

    @property
    def _prior(self) -> tuple[float, float]:
        return PRIOR_GAIN, PRIOR_WEIGHT * max(0.0, 1.0 - self.free.spread / PRIOR_FADE)

    @property
    def k(self) -> float | None:
        line = self.free.line(self._prior)
        if not line or line[0] >= 0:
            return None
        k = -line[0]
        tau = 1 / k
        return k if TAU_RANGE[0] <= tau <= TAU_RANGE[1] else None

    @property
    def tau(self) -> float | None:
        return round(1 / self.k, 1) if self.k else None

    @property
    def gain(self) -> float | None:
        line, k = self.free.line(self._prior), self.k
        return round(line[1] / k, 2) if line and k else None

    @property
    def warmup(self) -> float | None:
        return round(self.heat_sum / self.heat_n, 2) if self.heat_n >= 3 else None

    @property
    def progress(self) -> float:
        # Samples count most; variety tops it up. Completion still needs both (see `complete`).
        free = 0.75 * min(1.0, self.free.n / FREE_NEEDED) + 0.25 * min(1.0, self.free.spread / FREE_SPREAD_NEEDED)
        heat = min(1.0, self.heat_n / HEAT_NEEDED)
        return round(0.7 * free + 0.3 * heat, 3)

    @property
    def complete(self) -> bool:
        return (
            self.free.n >= FREE_NEEDED
            and self.free.spread >= FREE_SPREAD_NEEDED
            and self.heat_n >= HEAT_NEEDED
            and self.k is not None
        )

    @property
    def status(self) -> dict:
        """What is still missing, for the UI."""
        return {
            "cooling_hours": round(self.free.n * SAMPLE_MIN / 60, 1),
            "cooling_hours_needed": FREE_NEEDED * SAMPLE_MIN / 60,
            "variety_c": round(self.free.spread, 2) if self.free.n else 0.0,
            "variety_needed_c": FREE_SPREAD_NEEDED,
            "heating_hours": round(self.heat_n * SAMPLE_MIN / 60, 1),
            "heating_hours_needed": HEAT_NEEDED * SAMPLE_MIN / 60,
        }

    def predict(self, tin: float, tout: float, hours: float) -> float | None:
        """Temperature after `hours` with heating off."""
        k, g = self.k, self.gain
        if k is None or g is None:
            return None
        eq = tout + g
        return round(eq + (tin - eq) * math.exp(-k * hours), 2)

    def hours_to(self, tin: float, tout: float, floor: float, horizon: float = 72.0) -> float | None:
        """Hours until the room drifts down to `floor` with heating off."""
        k, g = self.k, self.gain
        if k is None or g is None:
            return None
        eq = tout + g
        if tin <= floor:
            return 0.0
        if eq >= floor:
            return None  # never reaches it
        h = -math.log((floor - eq) / (tin - eq)) / k
        return round(h, 1) if h <= horizon else None

    # ---------- persistence ----------

    def to_dict(self) -> dict:
        d = asdict(self)
        for key in ("xmin", "xmax"):
            if math.isinf(d["free"][key]):
                d["free"][key] = None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RoomModel":
        f = dict(d.get("free", {}))
        f["xmin"] = math.inf if f.get("xmin") is None else f["xmin"]
        f["xmax"] = -math.inf if f.get("xmax") is None else f["xmax"]
        m = cls(free=Fit(**f))
        m.heat_n = d.get("heat_n", 0)
        m.heat_sum = d.get("heat_sum", 0.0)
        return m


def classify(boiler_on: bool, boiler_state_min: float, radiator_open: bool | None,
             free_after_min: float = 60.0, heat_after_min: float = 10.0) -> Phase:
    """Which kind of interval this tick belongs to, for one room."""
    if not boiler_on and boiler_state_min >= free_after_min:
        return Phase.FREE
    if boiler_on and boiler_state_min >= heat_after_min and radiator_open is not False:
        return Phase.HEAT
    return Phase.OTHER


def overall_progress(models: list[RoomModel]) -> float:
    return round(sum(m.progress for m in models) / len(models), 3) if models else 0.0


def calibration_summary(models: list[RoomModel], share: float, free_share: float = 0.75) -> dict:
    """What the house still needs before learning is complete.

    Looks at the rooms closest to done (as many as `share` requires) and reports
    the worst of them, so the numbers shrink to zero exactly when calibration ends.
    `free_share` is the assumed fraction of wall-clock time the boiler is off long
    enough to give cooling data, used for a rough time estimate.
    """
    if not models:
        return {}
    need = max(1, math.ceil(share * len(models) - 1e-9))

    def left(m: RoomModel) -> tuple[float, float, float]:
        st = m.status
        return (
            max(0.0, st["cooling_hours_needed"] - st["cooling_hours"]),
            max(0.0, st["variety_needed_c"] - st["variety_c"]),
            max(0.0, st["heating_hours_needed"] - st["heating_hours"]),
        )

    ranked = sorted(models, key=lambda m: (not m.complete, sum(left(m))))[:need]
    lefts = [left(m) for m in ranked]
    cooling = max(x[0] for x in lefts)
    variety = max(x[1] for x in lefts)
    heating = max(x[2] for x in lefts)
    worst = min(ranked, key=lambda m: m.progress)
    st = worst.status
    eta = math.ceil(cooling / free_share + heating) if (cooling or heating) else 0
    return {
        "rooms_done": sum(1 for m in models if m.complete),
        "rooms_needed": need,
        "rooms_total": len(models),
        "cooling_hours_left": round(cooling, 1),
        "variety_left_c": round(variety, 2),
        "heating_hours_left": round(heating, 2),
        "cooling_hours": round(st["cooling_hours_needed"] - cooling, 1),
        "cooling_hours_needed": st["cooling_hours_needed"],
        "variety_c": round(st["variety_needed_c"] - variety, 2),
        "variety_needed_c": st["variety_needed_c"],
        "heating_hours": round(st["heating_hours_needed"] - heating, 2),
        "heating_hours_needed": st["heating_hours_needed"],
        "eta_hours": eta,
    }


def house_tau(models: list[RoomModel]) -> float | None:
    taus = sorted(m.tau for m in models if m.tau)
    return taus[len(taus) // 2] if taus else None


__all__ = [
    "Phase", "RoomModel", "classify", "overall_progress", "house_tau", "calibration_summary",
    "SAMPLE_MIN", "FREE_NEEDED", "HEAT_NEEDED", "timedelta",
]
