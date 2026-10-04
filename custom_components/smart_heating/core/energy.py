"""Daily gas and boiler accounting. Unit costs only: standing charges are not heating costs."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime

from .consumption import meter_step

M3_TO_KWH = 11.2  # UK typical: volume correction 1.02264 x CV ~39.5 MJ/m3 / 3.6


@dataclass
class EnergyDay:
    day: str = ""
    meter_start: float | None = None
    meter_last: float | None = None
    meter_carry: float = 0.0  # counted before the meter reset today (a daily total at midnight)
    runtime_min: float = 0.0
    heat_runtime_min: float = 0.0
    hw_runtime_min: float = 0.0
    # Burning time by what asked for it (both: heating and hot water together; other: neither known).
    heat_only_min: float = 0.0
    hw_only_min: float = 0.0
    both_min: float = 0.0
    other_min: float = 0.0
    burns: int = 0
    was_on: bool = False
    outdoor_sum: float = 0.0
    outdoor_n: int = 0
    last_tick: str | None = None
    cost: float = 0.0
    priced_kwh: float = 0.0

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
                if heating_demand and hw_calling:
                    self.both_min += dt_min
                elif heating_demand:
                    self.heat_only_min += dt_min
                elif hw_calling:
                    self.hw_only_min += dt_min
                else:
                    self.other_min += dt_min
        if boiler_on and not self.was_on:
            self.burns += 1
        self.was_on = boiler_on
        if meter is not None:
            self.meter_start, self.meter_last, self.meter_carry = meter_step(
                self.meter_start, self.meter_last, self.meter_carry, meter)
        if outdoor is not None:
            self.outdoor_sum += outdoor
            self.outdoor_n += 1
        self.last_tick = now.isoformat()
        return self

    # ---------- results ----------

    def gas_kwh(self, meter_unit_m3: bool, boiler_input_kw: float) -> tuple[float, bool]:
        """(kWh today, measured?) Falls back to runtime x input when no meter."""
        if self.meter_start is not None and self.meter_last is not None:
            used = self.meter_carry + self.meter_last - self.meter_start
            return round(used * M3_TO_KWH if meter_unit_m3 else used, 2), True
        return round(self.runtime_min / 60 * boiler_input_kw, 2), False

    def price(self, kwh: float, price_per_kwh: float) -> float:
        """Cost today: each new kWh at the unit price when it was used (rates can change)."""
        if kwh > self.priced_kwh:
            self.cost += (kwh - self.priced_kwh) * price_per_kwh
        self.priced_kwh = kwh
        return round(self.cost, 2)

    def use_hours(self, cold_base: float) -> dict[str, float]:
        """Hours for the gas fit: heating, hot water (burning with no heating call counts as hot water,
        e.g. a combi running a tap) and heating hours weighted by how cold the day was (per 10 degC)."""
        heat = (self.heat_only_min + self.both_min / 2) / 60
        hw = (self.hw_only_min + self.other_min + self.both_min / 2) / 60
        mean = self.outdoor_mean()
        cold = max(0.0, cold_base - mean) / 10 if mean is not None else 0.0
        return {"heating": round(heat, 3), "hot_water": round(hw, 3), "cold": round(heat * cold, 3)}

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
