"""Daily gas and boiler accounting."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime

M3_TO_KWH = 11.2  # UK typical: volume correction 1.02264 x CV ~39.5 MJ/m3 / 3.6


@dataclass
class EnergyDay:
    day: str = ""
    meter_start: float | None = None
    meter_last: float | None = None
    runtime_min: float = 0.0
    heat_runtime_min: float = 0.0
    hw_runtime_min: float = 0.0
    burns: int = 0
    was_on: bool = False
    outdoor_sum: float = 0.0
    outdoor_n: int = 0
    last_tick: str | None = None

    # ---------- feeding ----------

    def tick(
        self,
        now: datetime,
        today: date,
        boiler_on: bool,
        hw_calling: bool,
        heating_demand: bool,
        meter: float | None,
        outdoor: float | None,
    ) -> "EnergyDay":
        """Advance; returns a fresh EnergyDay when the local day rolls over."""
        if self.day != today.isoformat():
            fresh = EnergyDay(day=today.isoformat(), meter_start=meter, meter_last=meter, was_on=boiler_on)
            fresh.last_tick = now.isoformat()
            return fresh
        if self.last_tick:
            dt_min = (now - datetime.fromisoformat(self.last_tick)).total_seconds() / 60
            if 0 < dt_min < 30 and self.was_on:
                self.runtime_min += dt_min
                if hw_calling:
                    self.hw_runtime_min += dt_min
                if heating_demand:
                    self.heat_runtime_min += dt_min
        if boiler_on and not self.was_on:
            self.burns += 1
        self.was_on = boiler_on
        if meter is not None:
            if self.meter_start is None or meter < (self.meter_last or meter):
                self.meter_start = meter  # first reading or meter reset
            self.meter_last = meter
        if outdoor is not None:
            self.outdoor_sum += outdoor
            self.outdoor_n += 1
        self.last_tick = now.isoformat()
        return self

    # ---------- results ----------

    def gas_kwh(self, meter_unit_m3: bool, boiler_input_kw: float) -> tuple[float, bool]:
        """(kWh today, measured?) Falls back to runtime x input when no meter."""
        if self.meter_start is not None and self.meter_last is not None:
            used = self.meter_last - self.meter_start
            return round(used * M3_TO_KWH if meter_unit_m3 else used, 2), True
        return round(self.runtime_min / 60 * boiler_input_kw, 2), False

    def cost(self, kwh: float, price_per_kwh: float, standing: float) -> float:
        return round(kwh * price_per_kwh + standing, 2)

    def outdoor_mean(self) -> float | None:
        return round(self.outdoor_sum / self.outdoor_n, 1) if self.outdoor_n else None

    def degree_days(self, base: float) -> float | None:
        m = self.outdoor_mean()
        return round(max(base - m, 0.0), 2) if m is not None else None

    def kwh_per_degree_day(self, kwh: float, base: float) -> float | None:
        dd = self.degree_days(base)
        return round(kwh / dd, 2) if dd and dd >= 0.5 else None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EnergyDay":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
