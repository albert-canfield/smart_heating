"""Outdoor day mean: past observations blended with the forecast ahead."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta


class OutdoorModel:
    """Keeps up to 12 h of observed outdoor temps and the latest hourly forecast.

    day_mean = mean(observed last 12 h) blended 50/50 with mean(forecast next 12 h).
    Falls back to whichever side exists.
    """

    def __init__(self, history_h: float = 12.0) -> None:
        self._hist: deque[tuple[datetime, float]] = deque()
        self._history = timedelta(hours=history_h)
        self.forecast: list[tuple[datetime, float]] = []

    def observe(self, when: datetime, temp: float) -> None:
        if self._hist and when - self._hist[-1][0] < timedelta(minutes=5):
            return
        self._hist.append((when, temp))
        while self._hist and when - self._hist[0][0] > self._history:
            self._hist.popleft()

    def set_forecast(self, points: list[tuple[datetime, float]]) -> None:
        self.forecast = sorted(points)

    def _ahead(self, now: datetime, hours: float) -> list[float]:
        end = now + timedelta(hours=hours)
        return [t for when, t in self.forecast if now - timedelta(hours=1) <= when <= end]

    def now_temp(self, now: datetime) -> float | None:
        """Latest observation (if fresh) or nearest forecast hour."""
        if self._hist and now - self._hist[-1][0] < timedelta(minutes=30):
            return self._hist[-1][1]
        near = [(abs((w - now).total_seconds()), t) for w, t in self.forecast]
        near = [x for x in near if x[0] <= 5400]
        return min(near)[1] if near else None

    def observed_mean(self) -> float | None:
        if len(self._hist) < 2:
            return None
        return sum(t for _, t in self._hist) / len(self._hist)

    def forecast_mean(self, now: datetime, hours: float = 12.0) -> float | None:
        vals = self._ahead(now, hours)
        return sum(vals) / len(vals) if vals else None

    def forecast_min(self, now: datetime, hours: float = 24.0) -> float | None:
        vals = self._ahead(now, hours)
        return min(vals) if vals else None

    def day_mean(self, now: datetime) -> float | None:
        past, ahead = self.observed_mean(), self.forecast_mean(now, 12.0)
        if past is not None and ahead is not None:
            return round((past + ahead) / 2, 1)
        if ahead is not None:
            return round(self.forecast_mean(now, 24.0), 1)
        return round(past, 1) if past is not None else None


def house_means(temps: list[tuple]) -> tuple[float | None, dict[int, float]]:
    """Mean of the valid room temps, and per floor. An item is (floor, temp) or (floor, temp, counts):
    a room with counts False (nothing heats it, e.g. a garage) is left out of the house mean
    but still shown on its floor."""
    valid = [(t[0], t[1], t[2] if len(t) > 2 else True) for t in temps if t[1] is not None]
    if not valid:
        return None, {}
    floors: dict[int, list[float]] = {}
    for f, t, _ in valid:
        floors.setdefault(f, []).append(t)
    house = [t for _, t, counts in valid if counts] or [t for _, t, _ in valid]
    return (
        round(sum(house) / len(house), 2),
        {f: round(sum(v) / len(v), 2) for f, v in sorted(floors.items())},
    )
