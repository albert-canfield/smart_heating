"""Share a meter's daily total between uses, with rates learned from your own days.

Each day:  meter total = known + sum(rate[use] x hours[use]) + base

`rate` is kWh per hour of use (gas heating, gas hot water, an electric heater in a mode),
`base` is the rest per day (gas hob, the rest of the house), `known` is anything measured
directly (a heater with its own power sensor). Rates start from typical values (boiler input
x 70%, a heater's rated watts) and move towards what the meter shows over a rolling window,
through a ridge regression that pulls each rate towards its starting value. Few or odd days
therefore can't produce silly rates; many days let the meter decide.
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

WINDOW_DAYS = 28
MIN_DAYS = 3  # fewer meter days than this: keep the starting values


def meter_step(start: float | None, last: float | None, carry: float, value: float) -> tuple[float, float, float]:
    """Advance a meter reading. Handles totals that restart (e.g. at midnight) and small revisions.

    Returns (start, last, carry); used so far = carry + last - start.
    """
    if start is None or last is None:
        return value, value, carry
    if value >= last:
        return start, value, carry
    if value < last / 2:  # restarted: keep what was counted, count again from here
        return value, value, carry + last - start
    return start, last, carry  # a small drop is a revised reading: ignore it


@dataclass
class Cost:
    """Cost of a growing kWh figure, each new kWh at the unit price when it was used."""

    cost: float = 0.0
    priced_kwh: float = 0.0

    def add(self, kwh: float, price: float) -> float:
        if kwh > self.priced_kwh:
            self.cost += (kwh - self.priced_kwh) * price
        self.priced_kwh = kwh
        return round(self.cost, 2)


@dataclass
class DayRecord:
    day: str
    total: float | None  # meter kWh that day; None when there is no meter
    hours: dict[str, float] = field(default_factory=dict)
    known: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DayRecord":
        return cls(day=str(d["day"]), total=d.get("total"), hours=dict(d.get("hours") or {}), known=float(d.get("known", 0.0)))


@dataclass
class Rates:
    rates: dict[str, float]  # use -> kWh per hour
    base: float  # kWh per day
    days: int = 0  # days with a meter total behind the fit
    error: float | None = None  # mean absolute error over those days, as a share of the meter

    def kwh(self, use: str, hours: float) -> float:
        return self.rates.get(use, 0.0) * hours

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Rates":
        return cls(rates={k: float(v) for k, v in (d.get("rates") or {}).items()}, base=float(d.get("base", 0.0)),
                   days=int(d.get("days", 0)), error=d.get("error"))


def _solve(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting (small systems only)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit(
    records: list[DayRecord],
    prior: dict[str, float],
    base_prior: float,
    bounds: dict[str, tuple[float, float]] | None = None,
    strength: float = 2.0,
    base_strength: float = 1.0,
) -> Rates:
    """Rates for each use in `prior` and a daily base, from days that have a meter total.

    `strength` is how many days' worth of evidence each starting value counts as (2: one odd day
    moves a rate a third of the way); `base_strength` holds the base (high for a small steady gas
    hob, low for the rest of a house's electricity); `bounds` keep rates physical (a boiler can't
    burn more than its input). With a week or more, days far off the rest (a meter glitch) are
    left out and the fit is done again.
    """
    days = [r for r in records[-WINDOW_DAYS:] if r.total is not None and r.total >= 0]
    if len(days) < MIN_DAYS:
        return Rates(dict(prior), base_prior, days=len(days))
    first = _fit(days, prior, base_prior, bounds, strength, base_strength)
    if len(days) >= 7:
        resid = [abs(predict(first, r) - r.total) for r in days]
        mad = statistics.median(resid)
        keep = [r for r, e in zip(days, resid) if e <= max(5 * mad, 0.15 * r.total, 2.0)]
        if len(keep) < len(days):
            out = _fit(keep, prior, base_prior, bounds, strength, base_strength)
            out.days = len(days)
            out.error = _error(out, days)
            return out
    return first


def _error(rates: Rates, days: list[DayRecord]) -> float | None:
    total = sum(r.total for r in days)
    return round(sum(abs(predict(rates, r) - r.total) for r in days) / total, 3) if total > 0 else None


def _fit(days, prior, base_prior, bounds, strength, base_strength) -> Rates:
    uses = list(prior)
    k = len(uses) + 1
    ata = [[0.0] * k for _ in range(k)]
    aty = [0.0] * k
    for r in days:
        x = [r.hours.get(u, 0.0) for u in uses] + [1.0]
        y = r.total - r.known
        for i in range(k):
            aty[i] += x[i] * y
            for j in range(k):
                ata[i][j] += x[i] * x[j]
    theta0 = [prior[u] for u in uses] + [base_prior]
    n = len(days)
    for i, u in enumerate(uses):
        # Pull towards the starting value, sized like the data's own evidence for this rate: how much
        # its hours vary from day to day (a use that runs the same every day says little about its rate).
        hs = [r.hours.get(u, 0.0) for r in days]
        spread = statistics.pvariance(hs) if n > 1 else 0.0
        lam = strength * max(spread, statistics.fmean(h * h for h in hs) / n, 0.05)
        ata[i][i] += lam
        aty[i] += lam * theta0[i]
    ata[k - 1][k - 1] += base_strength
    aty[k - 1] += base_strength * base_prior
    theta = _solve(ata, aty) or theta0
    rates = {}
    for i, u in enumerate(uses):
        lo, hi = (bounds or {}).get(u, (0.0, float("inf")))
        rates[u] = round(min(hi, max(lo, theta[i])), 3)
    base = round(max(0.0, theta[-1]), 3)
    out = Rates(rates, base, days=len(days))
    out.error = _error(out, days)
    return out


def predict(rates: Rates, record: DayRecord) -> float:
    return record.known + sum(rates.kwh(u, h) for u, h in record.hours.items()) + rates.base


def learn_step(current: float | None, jump_w: float | None, rated_kw: float, alpha: float = 0.3) -> float | None:
    """A heater's real draw (kW) from the jump in house power when it alone switched.

    Jumps far from its rating (another appliance switching at the same moment) are ignored;
    accepted ones move the learned value a step at a time.
    """
    if jump_w is None or rated_kw <= 0:
        return current
    kw = jump_w / 1000
    if not 0.3 * rated_kw <= kw <= 1.6 * rated_kw:
        return current
    return round(kw if current is None else current + alpha * (kw - current), 3)
