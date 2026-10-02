"""Room temperature trend (degC/h) from recent samples."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta


class Trend:
    def __init__(self, window_min: float = 30.0, min_span_min: float = 10.0) -> None:
        self._window = timedelta(minutes=window_min)
        self._min_span = timedelta(minutes=min_span_min)
        self._samples: deque[tuple[datetime, float]] = deque()

    def add(self, when: datetime, temp: float) -> None:
        if self._samples and self._samples[-1][0] == when:
            return
        self._samples.append((when, temp))
        while self._samples and when - self._samples[0][0] > self._window:
            self._samples.popleft()

    def rate(self) -> float | None:
        """Least-squares slope in degC per hour."""
        if len(self._samples) < 3:
            return None
        t0 = self._samples[0][0]
        if self._samples[-1][0] - t0 < self._min_span:
            return None
        xs = [(t - t0).total_seconds() / 3600 for t, _ in self._samples]
        ys = [v for _, v in self._samples]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        den = sum((x - mx) ** 2 for x in xs)
        if den == 0:
            return None
        return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den, 3)
