"""Sensors: house status and per-room need/decision."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from homeassistant.const import EntityCategory

from .core import Level, Verdict, insulation
from .entity import HouseEntity, RoomEntity

STATUSES = ["heating", "idle", "paused", "waiting", "off", "away", "fault", "disabled", "testing", "starting"]


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    house = [
        HouseStatus(c),
        ClimateSensor(c, "house_temperature", lambda c: c.house_temp, "house_temperature"),
        ClimateSensor(c, "outdoor_day_mean", lambda c: c.outdoor_mean, "outdoor_day_mean"),
        ClimateSensor(c, "forecast_min_24h", lambda c: c.forecast_min_24h, "forecast_min_24h"),
    ]
    house += [
        Metric(c, "calibration", lambda c: round(c.calibration_progress * 100), PERCENTAGE, kind="calibration",
               attrs=lambda c: {"calibrated": c.calibrated, "available": c.learnable, "learning_now": c.learning_phase,
                                "watching_only": c.monitor_only, "heat_test_min_left": c.heat_test_left_min,
                                "can_heat_test": c.boiler_control or c.has_trvs or c.has_heaters,
                                "competing_automations": c.competing_automations,
                                **c.calibration_info,
                                "rooms": {r.cfg.name: round(r.model.progress * 100) for r in c.rooms.values()}}),
        Metric(c, "house_heat_loss_tau", lambda c: c.house_tau, UnitOfTime.HOURS, kind="house_tau"),
    ]
    kwh = dict(device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING)
    money = dict(device_class=SensorDeviceClass.MONETARY, state_class=SensorStateClass.TOTAL, daily=True)

    def gas_rates(c):
        r = c.gas_rates
        return {"heating_kw": r.rates.get("heating"), "hot_water_kw": r.rates.get("hot_water"),
                "colder_per_10c_kw": r.rates.get("cold"), "other_kwh_per_day": r.base,
                "meter_days": r.days, "meter_error": r.error, "learned": r.days >= 3}

    gas = [
        Metric(c, "gas_today", lambda c: c.gas_kwh, UnitOfEnergy.KILO_WATT_HOUR, kind="gas_today", **kwh,
               attrs=lambda c: {"source": c.gas_source, "measured": c.gas_measured,
                                "heating_hours": round(c.energy.use_hours(15.5)["heating"], 2),
                                "boiler_hours": round(c.energy.runtime_min / 60, 2), "boiler_starts": c.energy.burns,
                                **gas_rates(c), "yesterday": c.gas_yesterday}),
        Metric(c, "gas_cost_today", lambda c: c.gas_cost, "GBP", kind="gas_cost_today", **money,
               attrs=lambda c: {"price_per_kwh": round(c.gas_price_now, 4), "price_from": c.gas_price_from,
                                "yesterday": round(c.gas_yesterday["heating_kwh"] * c.gas_price_now, 2) if c.gas_yesterday else None}),
        Metric(c, "hot_water_gas_today", lambda c: c.gas_hw_kwh, UnitOfEnergy.KILO_WATT_HOUR, kind="hot_water_gas_today", **kwh,
               attrs=lambda c: {"hot_water_hours": round(c.energy.use_hours(15.5)["hot_water"], 2),
                                "cost": round(c.gas_hw_kwh * c.gas_price_now, 2)}),
        Metric(c, "boiler_runtime_today", lambda c: round(c.energy.runtime_min), UnitOfTime.MINUTES, kind="runtime_today"),
        Metric(c, "boiler_burns_today", lambda c: c.energy.burns, None, kind="burns_today"),
        Metric(c, "gas_per_degree_day", lambda c: c.kwh_per_dd, "kWh/°Cd", kind="kwh_per_degree_day",
               attrs=lambda c: {"degree_days_today": c.energy.degree_days(c.settings.season_gate), "base": c.settings.season_gate}),
    ]
    if c.gas_source == "smart_meter":
        gas += [
            Metric(c, "other_gas_today", lambda c: c.gas_other_kwh, UnitOfEnergy.KILO_WATT_HOUR, kind="other_gas_today", **kwh,
                   attrs=lambda c: {"cost": round((c.gas_other_kwh or 0) * c.gas_price_now, 2)}),
            Metric(c, "house_gas_today", lambda c: c.gas_house_kwh, UnitOfEnergy.KILO_WATT_HOUR, kind="house_gas_today", **kwh),
        ]
    if c.has_gas:
        house += gas
    if c.has_electric:
        house += [
            Metric(c, "electric_today", lambda c: round(c.elec_kwh, 3), UnitOfEnergy.KILO_WATT_HOUR, kind="electric_today", **kwh,
                   attrs=lambda c: {"measured": c.electric_measured, "source": c.elec_source, "projected_today_kwh": c.elec_projected_kwh,
                                    "heater_hours": round(sum(c.elec_hours.values()), 2),
                                    "power_now_w": round(sum(c.heater_power_w(r) for r in c.rooms.values() if r.heaters)),
                                    "heater_kw": c.elec_rates.rates, "learned_from_live_power": c.step_kw,
                                    "meter_days": c.elec_rates.days, "meter_error": c.elec_rates.error,
                                    "yesterday": c.elec_yesterday}),
            Metric(c, "electric_cost_today", lambda c: c.elec_cost, "GBP", kind="electric_cost_today", **money,
                   attrs=lambda c: {"price_per_kwh": round(c.elec_price_now, 4),
                                    "projected_today": round((c.elec_projected_kwh or 0) * c.elec_price_now, 2) if c.elec_projected_kwh else None}),
        ]
        if c.elec_source == "smart_meter":
            house += [
                Metric(c, "other_electricity_today", lambda c: c.elec_other_kwh, UnitOfEnergy.KILO_WATT_HOUR, kind="other_electricity_today", **kwh),
                Metric(c, "house_electricity_today", lambda c: c.elec_house_kwh, UnitOfEnergy.KILO_WATT_HOUR, kind="house_electricity_today", **kwh),
            ]
    house.append(DecisionLog(c))
    house.append(WindowAdviceSensor(c))
    house.append(RetentionSensor(c, "house_heat_retention", lambda c: c.house_tau, scope="house"))
    if len(c.floors) > 1:
        house += [
            ClimateSensor(c, f"floor_{f}_temperature", (lambda c, f=f: c.floor_temps.get(f)), "floor_temperature", floor=f)
            for f in c.floors
        ]
        house += [
            RetentionSensor(c, f"floor_{f}_heat_retention", (lambda c, f=f: c.floor_tau(f)), scope="floor", floor=f)
            for f in c.floors
        ]
    async_add_entities(house)
    for room_id in c.rooms:
        async_add_entities(
            [
                RoomNeed(c, room_id),
                RoomDecisionSensor(c, room_id),
                RoomModelSensor(c, room_id, "heat_loss_tau", lambda r, c: r.model.tau, UnitOfTime.HOURS),
                RoomModelSensor(c, room_id, "warm_up_rate", lambda r, c: r.model.warmup, "°C/h"),
                RoomPredicted(c, room_id),
                RoomRetention(c, room_id),
            ] + ([RoomEnergy(c, room_id)] if c.rooms[room_id].heaters else []),
            config_subentry_id=room_id,
        )


class WindowAdviceSensor(HouseEntity, SensorEntity):
    """Open the windows to dry or cool the house, or close them."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["open", "close", "none"]

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "window_advice")

    @property
    def native_value(self) -> str:
        return self.coordinator.windows.advice.action

    @property
    def icon(self) -> str:
        return {"open": "mdi:window-open-variant", "close": "mdi:window-closed-variant"}.get(
            self.native_value, "mdi:window-closed")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        a = self.coordinator.windows.advice
        return {
            "kind": "window_advice",
            "advice": a.kind or None,
            "reason": a.reason or None,
            "rooms": a.rooms,
            "minutes": a.minutes,
            "since": a.since.isoformat() if a.since else None,
            "until": a.until.isoformat() if a.until else None,
            **{k: v for k, v in self.coordinator.window_info.items() if k not in ("humidity", "dew_points")},
        }


class HouseStatus(HouseEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.status if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self.coordinator.data
        c = self.coordinator
        if not p:
            return {}
        return {
            "reason": p.reason,
            "boiler_demand": p.boiler_on,
            "mode": c.mode.value,
            "one_cycle_wait": c.one_cycle_wait,
            "one_cycle_all": c.one_cycle_all,
            "season_off": c._season_off,
            "away": c.away,
            "profile": c.profile,
            "monitor_only": c.monitor_only,
            "calibrated": c.calibrated,
            "house_target": c.setpoints.house,
            "enabled": c.enabled,
            "open_rooms": [c.rooms[r].cfg.name for r in p.open_rooms],
            "close_rooms": [c.rooms[r].cfg.name for r in p.close_rooms],
            "heater_rooms": [c.rooms[r].cfg.name for r in p.heater_rooms],
            "boiler_firing": c.boiler_firing,
            "hot_water": c.hot_water_on,
            "night": c.night_now,
            "has_boiler": c.boiler_control or c.has_boiler_state,
            "calling_rooms": [
                c.rooms[r].cfg.name for r, d in p.rooms.items() if d.need.calling
            ],
        }


class RoomNeed(RoomEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [l.value for l in Level]

    def __init__(self, coordinator, room_id: str) -> None:
        super().__init__(coordinator, room_id, "need")

    @property
    def native_value(self) -> str | None:
        d = self.decision
        return d.need.level.value if d else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.decision
        room = self.coordinator.rooms[self.room_id]
        if not d:
            return {}
        return {
            "floor": room.cfg.floor,
            "floor_name": room.floor_name,
            "area_id": room.area_id,
            "priority": room.cfg.priority.value,
            "comfort": self.coordinator.room_comfort(room),
            "comfort_configured": room.cfg.comfort,
            "temperature": self.coordinator.room_temp(room),
            "temperature_entity": room.temp_entity or (room.trvs[0] if room.trvs else None),
            "temperature_source": "room sensor" if room.temp_entity else ("TRV" if room.trvs else None),
            "target": d.need.target,
            "deficit": d.need.deficit,
            "calling": d.need.calling,
            "trend": room.trend.rate(),
            "occupied": room.occupied,
            "override": room.override.value,
            "override_until": room.override_until.isoformat() if room.override_until else None,
            "has_trv": room.cfg.has_trv,
            "has_heater": bool(room.heaters),
            "heater_on": d.heater_on,
            "radiator": room.cfg.radiator,
            "reason": d.need.reason,
        }


class RoomDecisionSensor(RoomEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [v.value for v in Verdict]

    def __init__(self, coordinator, room_id: str) -> None:
        super().__init__(coordinator, room_id, "decision")

    @property
    def native_value(self) -> str | None:
        d = self.decision
        return d.verdict.value if d else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.decision
        if not d:
            return {}
        return {"reason": d.reason, "valve_command": d.open_valve}


FLOOR_NAMES = {0: "Ground floor", 1: "1st floor", 2: "2nd floor", 3: "3rd floor"}


class ClimateSensor(HouseEntity, SensorEntity):
    """House average, per-floor average, outdoor day mean, forecast minimum."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, key: str, getter, kind: str, floor: int | None = None) -> None:
        super().__init__(coordinator, key)
        self._getter = getter
        self._kind = kind
        self._floor = floor
        if floor is not None:
            self._attr_translation_key = None
            label = coordinator.floor_names.get(floor) or FLOOR_NAMES.get(floor, f"Floor {floor}")
            self._attr_name = f"{label} temperature"

    @property
    def native_value(self) -> float | None:
        return self._getter(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"kind": self._kind}
        if self._floor is not None:
            attrs["floor"] = self._floor
            attrs["floor_name"] = self.coordinator.floor_names.get(self._floor)
        if self._kind == "outdoor_day_mean":
            o, now = self.coordinator.outdoor, dt_util.utcnow()

            def r(v):
                return round(v, 1) if v is not None else None

            attrs["now"] = o.now_temp(now)
            attrs["observed_mean_12h"] = r(o.observed_mean())
            attrs["forecast_mean_12h"] = r(o.forecast_mean(now, 12))
            attrs["forecast_mean_24h"] = r(o.forecast_mean(now, 24))
            attrs["forecast_min_12h"] = o.forecast_min(now, 12)
            attrs["forecast_min_24h"] = o.forecast_min(now, 24)
            attrs["forecast_points"] = len(o.forecast)
        if self._kind == "house_temperature":
            attrs["rooms"] = {
                r.cfg.name: self.coordinator.room_temp(r) for r in self.coordinator.rooms.values()
            }
        return attrs


class Metric(HouseEntity, SensorEntity):
    """Generic house metric read from the coordinator."""

    def __init__(self, coordinator, key, getter, unit, kind, device_class=None, state_class=SensorStateClass.MEASUREMENT, attrs=None, daily=False) -> None:
        super().__init__(coordinator, key)
        self._getter, self._kind, self._attrs, self._daily = getter, kind, attrs, daily
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class if unit is not None or kind == "burns_today" else None

    @property
    def native_value(self):
        return self._getter(self.coordinator)

    @property
    def last_reset(self):
        """Daily totals restart at local midnight, so long-term statistics don't count the drop."""
        return dt_util.start_of_local_day() if self._daily else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        out = {"kind": self._kind}
        if self._attrs:
            out.update(self._attrs(self.coordinator))
        return out


class RoomModelSensor(RoomEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, room_id, key, getter, unit) -> None:
        super().__init__(coordinator, room_id, key)
        self._getter = getter
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        return self._getter(self.coordinator.rooms[self.room_id], self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        m = self.coordinator.rooms[self.room_id].model
        out = {"kind": self._attr_translation_key, "calibration": round(m.progress * 100), "free_heat_gain": m.gain, **m.status}
        if self._attr_translation_key == "heat_loss_tau":
            lo, hi = m.tau_range or (None, None)
            out.update(tau_low=lo, tau_high=hi, settled=m.settled)
        return out


class RoomPredicted(RoomEntity, SensorEntity):
    """Room temperature in 2 h with heating off, and hours until it hits the baseline."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, room_id) -> None:
        super().__init__(coordinator, room_id, "predicted_2h")

    def _inputs(self):
        c = self.coordinator
        room = c.rooms[self.room_id]
        tin = c.room_temp(room)
        tout = c.outdoor.forecast_mean(dt_util.utcnow(), 2) or c.outdoor.now_temp(dt_util.utcnow())
        return room, tin, tout

    @property
    def native_value(self) -> float | None:
        room, tin, tout = self._inputs()
        if tin is None or tout is None:
            return None
        return room.model.predict(tin, tout, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        room, tin, tout = self._inputs()
        c = self.coordinator
        if tin is None or tout is None:
            return {}
        base = c.effective_settings.baseline_day
        return {
            "kind": "predicted_2h",
            "outdoor_used": round(tout, 1),
            "hours_to_baseline": room.model.hours_to(tin, tout, base),
            "baseline": base,
            "predicted_8h": room.model.predict(tin, tout, 8),
        }


class DecisionLog(HouseEntity, SensorEntity):
    """Latest decision as state; recent entries as an attribute (not recorded to the database)."""

    _unrecorded_attributes = frozenset({"entries"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "decision_log")

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.log:
            return None
        e = self.coordinator.log[0]
        text = f"{e['room']}: {e['message']}" if e.get("room") else e["message"]
        return text[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"kind": "decision_log", "entries": list(self.coordinator.log)[:50]}


def _retention_attrs(tau, calibration=None) -> dict[str, Any]:
    d = insulation.describe(tau)
    d["kind"] = "heat_retention"
    if calibration is not None:
        d["calibration"] = calibration
    return d


class RetentionSensor(HouseEntity, SensorEntity):
    """House or floor heat retention index (0-100) with A-G grade."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-thermometer-outline"

    def __init__(self, coordinator, key, getter, scope: str, floor: int | None = None) -> None:
        super().__init__(coordinator, key)
        self._getter, self._scope, self._floor = getter, scope, floor
        if floor is not None:
            self._attr_translation_key = None
            label = coordinator.floor_names.get(floor) or FLOOR_NAMES.get(floor, f"Floor {floor}")
            self._attr_name = f"{label} heat retention"

    @property
    def native_value(self):
        return insulation.score(self._getter(self.coordinator))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = _retention_attrs(self._getter(self.coordinator))
        d["scope"] = self._scope
        if self._floor is not None:
            d["floor"] = self._floor
        if self._scope == "house":
            d["weakest_rooms"] = self.coordinator.weakest_rooms()
            d["note"] = "Comparative: upper floors gain heat from below, so they rate better than their fabric alone."
        return d


class RoomRetention(RoomEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-thermometer-outline"

    def __init__(self, coordinator, room_id) -> None:
        super().__init__(coordinator, room_id, "heat_retention")

    @property
    def native_value(self):
        return insulation.score(self.coordinator.rooms[self.room_id].model.tau)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        m = self.coordinator.rooms[self.room_id].model
        d = _retention_attrs(m.tau, round(m.progress * 100))
        lo, hi = m.tau_range or (None, None)
        d.update(tau_low=lo, tau_high=hi, grade_range=insulation.grade_range(lo, hi), settled=m.settled)
        return d


class RoomEnergy(RoomEntity, SensorEntity):
    """Electric heater energy today for one room."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, room_id) -> None:
        super().__init__(coordinator, room_id, "energy_today")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.rooms[self.room_id].kwh_today, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        r = c.rooms[self.room_id]
        return {
            "kind": "room_energy",
            "power_now_w": c.heater_power_w(r),
            "heater_on_min_today": round(r.heater_min_today),
            "rated_w": r.heater_w,
            "eco_w": r.heater_eco_w,
            "measured": len(r.power_sensors) == len(r.heaters),
            "power_sensors": list(r.power_sensors.values()),
            "cost_today": round(r.kwh_today * c.elec_price_now, 2),
        }
