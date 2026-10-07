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

Samples 15 min apart are not independent (a sunny afternoon moves a dozen of them
the same way), so a textbook standard error would claim far more certainty than
the data holds. Instead the days are dealt into DAY_GROUPS groups and the fit is
redone leaving out one group at a time: how far tau moves is how settled it is.

Free heat that comes and goes (a shower, cooking, sun) leaves the room cooling
faster afterwards than its walls alone would, which pulls tau down. Samples from
an hour before such an event to HOLD after it are left out. Moisture is judged by
dew point: relative humidity rises by itself as a room cools. Old data fades with a
FADE_HALF_LIFE_H half-life so draught-proofing or a new window shows up.

Some rooms never settle (free heat from neighbours that changes day to day); after
STEADY_CAP cooling samples (counted without fading) they count as learned anyway, with their range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .ventilation import dew_point


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
DAY_GROUPS = 5  # days are dealt into this many groups for the leave-one-out check
DAYS_NEEDED = 4  # groups with data before the check means anything
DAY_MIN = 12  # samples (3 h) for a group to count
SETTLED = 0.25  # relative standard error of 1/tau at which the result counts as settled
STEADY_CAP = 960  # cooling samples since the day groups began (240 h): as settled as this room gets
ERR_CAP = 9.99  # reported when the groups disagree on whether the room cools at all
RISE_C = 0.25  # degC above the last hour's low with the heating off: free heat arriving
DEW_JUMP = 2.0  # degC of dew point above the last hour's low: moisture added (shower, cooking, drying)
LOOKBACK = timedelta(hours=1)
HOLD = timedelta(hours=2)
FADE_HALF_LIFE_H = 30 * 24.0


@dataclass
class Fit:
    n: float = 0
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

    def scale(self, f: float) -> None:
        """Fade: older samples count for less. The range seen is kept."""
        self.n *= f
        self.sx *= f
        self.sy *= f
        self.sxx *= f
        self.sxy *= f

    def __add__(self, o: "Fit") -> "Fit":
        return Fit(self.n + o.n, self.sx + o.sx, self.sy + o.sy, self.sxx + o.sxx, self.sxy + o.sxy,
                   min(self.xmin, o.xmin), max(self.xmax, o.xmax))

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

    def to_dict(self) -> dict:
        return {"n": self.n, "sx": self.sx, "sy": self.sy, "sxx": self.sxx, "sxy": self.sxy,
                "xmin": None if math.isinf(self.xmin) else self.xmin,
                "xmax": None if math.isinf(self.xmax) else self.xmax}

    @classmethod
    def from_dict(cls, d: dict) -> "Fit":
        f = dict(d)
        f["xmin"] = math.inf if f.get("xmin") is None else f["xmin"]
        f["xmax"] = -math.inf if f.get("xmax") is None else f["xmax"]
        return cls(**f)


def _day(now: datetime) -> int:
    """Days run noon to noon, so a night stays in one group."""
    return (now - timedelta(hours=12)).toordinal()


@dataclass
class RoomModel:
    free: Fit  # everything, used for tau and gain
    days: list[Fit] = field(default_factory=lambda: [Fit() for _ in range(DAY_GROUPS)])  # the same, by day
    heat_n: int = 0
    heat_sum: float = 0.0
    faded: str | None = None  # iso: when the sums were last faded
    skipped: int = 0  # free-running samples left out around disturbances
    counted: int = 0  # cooling samples in the day groups, not faded (for STEADY_CAP)
    # Open segment and disturbance watch (not persisted).
    seg_phase: str | None = None
    seg_start: str | None = None  # iso
    seg_tin: float | None = None
    seg_tout_sum: float = 0.0
    seg_tout_n: int = 0
    recent: list = field(default_factory=list)  # (time, tin, dew point) over the last hour with the heating off
    pending: list = field(default_factory=list)  # (end, day, x, y): samples held back for LOOKBACK
    hold_until: datetime | None = None

    @classmethod
    def new(cls) -> "RoomModel":
        return cls(free=Fit())

    # ---------- learning ----------

    def observe(self, now: datetime, tin: float | None, tout: float | None, phase: Phase,
                rh: float | None = None, day: int | None = None) -> bool:
        """Feed one tick. Returns True when a sample was taken. Cooling samples are held back
        an hour in case a disturbance turns up; `day` groups them (default: UTC noon to noon)."""
        if phase is not Phase.FREE:
            self._flush()  # a rise with the heating on is the heating, not a disturbance
            self.recent.clear()
        if tin is None or (phase is Phase.FREE and tout is None) or phase is Phase.OTHER:
            self._reset()
            return False
        if phase is Phase.FREE:
            self._watch(now, tin, rh)
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
            if self.hold_until and start < self.hold_until:
                self.skipped += 1
            else:
                self.pending.append((now, _day(now) if day is None else day, x, rate))
            self._release(now)
        else:
            self.heat_n += 1
            self.heat_sum += rate
        self._open(now, tin, phase)
        if tout is not None:
            self.seg_tout_sum, self.seg_tout_n = tout, 1
        return True

    def _watch(self, now: datetime, tin: float, rh: float | None) -> None:
        """Spot free heat arriving: the room warming with the heating off, or humidity jumping."""
        self.recent = [r for r in self.recent if now - r[0] <= LOOKBACK]
        td = dew_point(tin, rh)
        self.recent.append((now, tin, td))
        tds = [r[2] for r in self.recent if r[2] is not None]
        if tin - min(r[1] for r in self.recent) >= RISE_C or (td is not None and td - min(tds) >= DEW_JUMP):
            self.skipped += len(self.pending)
            self.pending.clear()
            self.hold_until = now + HOLD
            self.recent = [(now, tin, td)]  # measure any further rise from here: the hold runs from the last one

    def _release(self, now: datetime) -> None:
        while self.pending and now - self.pending[0][0] >= LOOKBACK:
            self._commit(*self.pending.pop(0))

    def _flush(self) -> None:
        while self.pending:
            self._commit(*self.pending.pop(0))

    def _commit(self, end: datetime, day: int, x: float, y: float) -> None:
        last = datetime.fromisoformat(self.faded) if self.faded else None
        if last is None or end > last:
            if last is not None:
                f = 0.5 ** ((end - last).total_seconds() / 3600 / FADE_HALF_LIFE_H)
                for fit in (self.free, *self.days):
                    fit.scale(f)
            self.faded = end.isoformat()
        self.free.add(x, y)
        self.days[day % DAY_GROUPS].add(x, y)
        self.counted += 1

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
    def _used_days(self) -> list[Fit]:
        return [f for f in self.days if f.n >= DAY_MIN - 0.5]  # a little slack: fading nibbles at fresh samples

    @property
    def tau_error(self) -> float | None:
        """Relative standard error of the cooling rate, by leaving out one group of days at a time
        (delete-a-group jackknife, no prior). None until DAYS_NEEDED groups have data."""
        used = self._used_days
        if len(used) < DAYS_NEEDED:
            return None
        slopes = []
        for i in range(len(used)):
            line = sum(used[:i] + used[i + 1:], Fit()).line()
            if not line:
                return ERR_CAP
            slopes.append(line[0])
        g = len(slopes)
        mean = sum(slopes) / g
        if mean >= 0:
            return ERR_CAP
        se = math.sqrt((g - 1) / g * sum((s - mean) ** 2 for s in slopes))
        return round(min(ERR_CAP, se / -mean), 3)

    @property
    def tau_range(self) -> tuple[float, float] | None:
        """tau at one standard error either side."""
        k, err = self.k, self.tau_error
        if k is None or err is None:
            return None
        lo = max(TAU_RANGE[0], 1 / (k * (1 + err)))
        hi = TAU_RANGE[1] if err >= 1 else min(TAU_RANGE[1], 1 / (k * (1 - err)))
        return round(lo, 1), round(hi, 1)

    @property
    def settled(self) -> bool:
        err = self.tau_error
        return err is not None and err <= SETTLED

    @property
    def steady_enough(self) -> bool:
        """Settled, or so much data that more will not settle it (the range stays shown)."""
        return self.settled or (self.tau_error is not None and self.counted >= STEADY_CAP)

    @property
    def _steadiness(self) -> float:
        err = self.tau_error
        steady = 0.0 if err is None else 1.0 if self.steady_enough else SETTLED / err
        return 0.5 * min(1.0, len(self._used_days) / DAYS_NEEDED) + 0.5 * steady

    @property
    def progress(self) -> float:
        # Samples count most; variety and steadiness top it up. Completion needs all (see `complete`).
        free = (0.5 * min(1.0, self.free.n / FREE_NEEDED) + 0.2 * min(1.0, self.free.spread / FREE_SPREAD_NEEDED)
                + 0.3 * self._steadiness)
        heat = min(1.0, self.heat_n / HEAT_NEEDED)
        return round(0.7 * free + 0.3 * heat, 3)

    @property
    def complete(self) -> bool:
        return (
            self.free.n >= FREE_NEEDED
            and self.free.spread >= FREE_SPREAD_NEEDED
            and self.heat_n >= HEAT_NEEDED
            and self.steady_enough
            and self.k is not None
        )

    @property
    def status(self) -> dict:
        """What is still missing, for the UI."""
        err = self.tau_error
        return {
            "cooling_hours": round(self.free.n * SAMPLE_MIN / 60, 1),
            "cooling_hours_needed": FREE_NEEDED * SAMPLE_MIN / 60,
            "variety_c": round(self.free.spread, 2) if self.free.n else 0.0,
            "variety_needed_c": FREE_SPREAD_NEEDED,
            "heating_hours": round(self.heat_n * SAMPLE_MIN / 60, 1),
            "heating_hours_needed": HEAT_NEEDED * SAMPLE_MIN / 60,
            "cooling_days": len(self._used_days),
            "cooling_days_needed": DAYS_NEEDED,
            "uncertainty_pct": None if err is None else math.ceil(err * 100 - 1e-9),
            "uncertainty_needed_pct": round(SETTLED * 100),
        }

    def settle_hours(self, free_share: float = 0.75) -> float:
        """Rough wall-clock hours until the result is settled."""
        err, days = self.tau_error, len(self._used_days)
        if err is None:
            return 24.0 * (DAYS_NEEDED - days)
        if self.steady_enough:
            return 0.0
        seen = sum(f.n for f in self._used_days)
        more = min(seen * ((err / SETTLED) ** 2 - 1), STEADY_CAP - self.counted)  # error falls with sqrt(data)
        return max(0.0, more) * SAMPLE_MIN / 60 / free_share

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
        return {
            "free": self.free.to_dict(),
            "days": [f.to_dict() for f in self.days],
            "heat_n": self.heat_n,
            "heat_sum": self.heat_sum,
            "faded": self.faded,
            "skipped": self.skipped,
            "counted": self.counted,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RoomModel":
        days = [Fit.from_dict(f) for f in d.get("days", [])][:DAY_GROUPS]
        m = cls(free=Fit.from_dict(d.get("free", {})), days=days + [Fit() for _ in range(DAY_GROUPS - len(days))])
        m.heat_n = d.get("heat_n", 0)
        m.heat_sum = d.get("heat_sum", 0.0)
        m.faded = d.get("faded")
        m.skipped = d.get("skipped", 0)
        m.counted = d.get("counted", 0)
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

    ranked = sorted(models, key=lambda m: (not m.complete, -m.progress, sum(left(m))))[:need]
    lefts = [left(m) for m in ranked]
    cooling = max(x[0] for x in lefts)
    variety = max(x[1] for x in lefts)
    heating = max(x[2] for x in lefts)
    worst = min(ranked, key=lambda m: m.progress)
    st = worst.status
    errs = [0.0 if m.steady_enough else m.tau_error for m in ranked]
    eta = math.ceil(cooling / free_share + heating) if (cooling or heating) else 0
    eta = max(eta, math.ceil(max(m.settle_hours(free_share) for m in ranked)))
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
        "cooling_days": min(m.status["cooling_days"] for m in ranked),
        "cooling_days_needed": DAYS_NEEDED,
        "uncertainty_pct": None if None in errs else math.ceil(max(errs) * 100 - 1e-9),
        "uncertainty_needed_pct": round(SETTLED * 100),
        "eta_hours": eta,
    }


def house_tau(models: list[RoomModel]) -> float | None:
    taus = sorted(m.tau for m in models if m.tau)
    return taus[len(taus) // 2] if taus else None


__all__ = [
    "Phase", "RoomModel", "classify", "overall_progress", "house_tau", "calibration_summary",
    "SAMPLE_MIN", "FREE_NEEDED", "HEAT_NEEDED", "timedelta",
]
