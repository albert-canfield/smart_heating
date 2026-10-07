"""Window advice: when opening windows dries or cools the house, and when to close them.

Drying works on dew point, not relative humidity. Cold air holds little water, so cold
outside air, even in light rain, is usually far drier than indoor air once warmed. A short
wide-open burst swaps the room's air while walls and furniture keep their heat, so the
heating only rewarms the air; longer airing cools the fabric and wastes heat. The burst is
shorter the colder and windier it is (air swaps faster), and is never advised while the
house is heating, so no heat goes straight out of the window.

Cooling: outside the heating season, open when it is cooler outside than in a hot room,
and keep closed when it is hotter outside.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

HUMID = 65.0  # %RH: a room worth drying
DRY_MARGIN = 3.0  # degC: outside dew point at least this far below the room's
HOT = 24.0  # degC: room too warm (outside the heating season)
COOL_MARGIN = 2.0  # degC: outside this much cooler than the room before opening
WARM = 22.0  # degC: on a hot day, worth keeping the heat out from here
WIND_SHORT = 30.0  # km/h: wind swaps the air faster, halve the burst
WIND_MAX = 60.0  # km/h: gale, never advise opening
STORMY = {"pouring", "lightning", "lightning-rainy", "hail", "exceptional"}
COOLDOWN = timedelta(hours=2)  # between drying bursts: humidity takes a while to build back
REMIND = timedelta(minutes=15)  # how long a "close" reminder stays up


def dew_point(t: float | None, rh: float | None) -> float | None:
    """Magnus formula, degC."""
    if t is None or rh is None or rh <= 0:
        return None
    a, b = 17.62, 243.12
    g = math.log(min(rh, 100.0) / 100) + a * t / (b + t)
    return round(b * g / (a - g), 1)


def burst_minutes(tout: float, wind_kmh: float | None = None) -> int:
    """Wide-open airing that swaps the air without chilling the walls."""
    m = 5 if tout < 0 else 10 if tout < 10 else 15 if tout < 15 else 25
    if wind_kmh is not None and wind_kmh >= WIND_SHORT:
        m = max(5, m // 2)
    return m


@dataclass
class RoomAir:
    name: str
    temp: float | None
    rh: float | None = None

    @property
    def dew_point(self) -> float | None:
        return dew_point(self.temp, self.rh)


@dataclass
class Outside:
    temp: float | None
    dew_point: float | None = None
    condition: str | None = None  # HA weather condition
    wind_kmh: float | None = None

    @property
    def stormy(self) -> bool:
        return (self.condition or "") in STORMY or (self.wind_kmh or 0.0) >= WIND_MAX


@dataclass
class Advice:
    action: str = "none"  # open | close | none
    kind: str = ""  # open: dry, cool. close: done, storm, warmer, cooled, away, hot
    reason: str = ""
    rooms: list[str] = field(default_factory=list)
    minutes: int | None = None  # length of a drying burst
    since: datetime | None = None
    until: datetime | None = None  # end of a burst or of a close reminder


def _names(rooms: list[RoomAir]) -> str:
    names = [r.name for r in rooms]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


class WindowAdvisor:
    def __init__(self) -> None:
        self.advice = Advice()
        self.next_dry: datetime | None = None

    def step(self, now: datetime, rooms: list[RoomAir], out: Outside, *, heating_season: bool,
             heating_now: bool = False, night: bool = False, away: bool = False) -> Advice:
        a = self.advice
        if away:
            if a.action == "open":
                return self._set(now, Advice("close", "away", "Close the windows: everyone is out.", a.rooms,
                                             until=now + REMIND))
            if a.action == "close" and a.until and now < a.until:
                return a
            return self._set(now, Advice())
        if a.action == "open":
            if out.stormy:
                what = out.condition.replace("-", " ") if (out.condition or "") in STORMY else "strong wind"
                return self._set(now, Advice("close", "storm", f"Close the windows: {what}.", a.rooms, until=now + REMIND))
            if a.kind == "dry":
                if now < a.until:
                    return a
                return self._set(now, Advice("close", "done", "Close the windows: the damp air is out. Longer only cools the walls.",
                                             a.rooms, until=now + REMIND))
            if out.temp is None:
                return a
            cool = self._cool(rooms, out, heating_season, keep=True)
            if cool:
                return self._set(now, cool)
            warmest = max((r.temp for r in rooms if r.temp is not None), default=out.temp)
            if out.temp > warmest - 1:
                text = f"Close the windows: it is now {out.temp:.0f}° outside, warmer than inside."
                return self._set(now, Advice("close", "warmer", text, a.rooms, until=now + REMIND))
            return self._set(now, Advice("close", "cooled", "Close the windows: the rooms have cooled down.", a.rooms,
                                         until=now + REMIND))
        if a.action == "close" and a.until and now < a.until:
            return a
        if out.temp is None:
            return self._set(now, Advice())
        return self._set(now, self._hot(rooms, out, heating_season, keep=a.kind == "hot")
                         or self._cool(rooms, out, heating_season)
                         or self._dry(now, rooms, out, heating_season, heating_now, night)
                         or Advice())

    def to_dict(self) -> dict:
        a = self.advice
        iso = lambda t: t.isoformat() if t else None  # noqa: E731
        return {"action": a.action, "kind": a.kind, "reason": a.reason, "rooms": a.rooms, "minutes": a.minutes,
                "since": iso(a.since), "until": iso(a.until), "next_dry": iso(self.next_dry)}

    @classmethod
    def from_dict(cls, d: dict) -> "WindowAdvisor":
        w = cls()
        when = lambda k: datetime.fromisoformat(d[k]) if d.get(k) else None  # noqa: E731
        w.advice = Advice(d.get("action", "none"), d.get("kind", ""), d.get("reason", ""), list(d.get("rooms") or []),
                          d.get("minutes"), when("since"), when("until"))
        w.next_dry = when("next_dry")
        return w

    def _set(self, now: datetime, new: Advice) -> Advice:
        old = self.advice
        new.since = old.since if (new.action, new.kind) == (old.action, old.kind) else now
        self.advice = new
        return new

    def _hot(self, rooms, out, heating_season, keep=False) -> Advice | None:
        """Hotter outside than in on a warm day: keep the heat out."""
        temps = [r.temp for r in rooms if r.temp is not None]
        if heating_season or not temps:
            return None
        warmest = max(temps)
        if warmest < WARM - (1 if keep else 0) or out.temp < warmest + (-0.5 if keep else 1):
            return None
        return Advice("close", "hot", f"Keep the windows shut and blinds down: {out.temp:.0f}° outside, "
                      f"{warmest:.0f}° inside.")

    def _cool(self, rooms, out, heating_season, keep=False) -> Advice | None:
        """A hot room and cooler air outside that is not damper."""
        if heating_season or out.stormy:
            return None
        hot = [r for r in rooms if r.temp is not None and r.temp >= HOT - (1.5 if keep else 0)
               and out.temp <= r.temp - (1 if keep else COOL_MARGIN)
               and (out.dew_point is None or r.dew_point is None or out.dew_point < r.dew_point + 2)]
        if not hot:
            return None
        top = max(hot, key=lambda r: r.temp)
        return Advice("open", "cool", f"Open the windows in {_names(hot)}: {out.temp:.0f}° outside, "
                      f"{top.name} is {top.temp:.1f}°.", [r.name for r in hot])

    def _dry(self, now, rooms, out, heating_season, heating_now, night) -> Advice | None:
        """A damp room and much drier air outside: a short burst, never while the house heats."""
        if night or out.stormy or out.dew_point is None or (heating_season and heating_now):
            return None
        if self.next_dry and now < self.next_dry:
            return None
        damp = [r for r in rooms if r.rh is not None and r.rh >= HUMID and r.dew_point is not None
                and r.dew_point - out.dew_point >= DRY_MARGIN]
        if not damp:
            return None
        worst = max(damp, key=lambda r: r.rh)
        mins = burst_minutes(out.temp, out.wind_kmh)
        text = (f"Open the windows wide for {mins} min in {_names(damp)}: {worst.name} is at {worst.rh:.0f}% "
                f"and the air outside is much drier (dew point {out.dew_point:.0f}° vs {worst.dew_point:.0f}°).")
        if out.condition == "rainy":
            text += " Fine in light rain: open on the sheltered side."
        until = now + timedelta(minutes=mins)
        self.next_dry = until + COOLDOWN
        return Advice("open", "dry", text, [r.name for r in damp], minutes=mins, until=until)
