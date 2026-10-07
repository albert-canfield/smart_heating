"""Smoke test: run the coordinator inside a real HomeAssistant core with fake entities.

Not part of the pytest suite (needs the full homeassistant package).
Run: python3 tests/smoke_ha.py
"""
import asyncio
import sys
import tempfile
import importlib.abc
import importlib.machinery
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock


class _Stub(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    roots = ("hass_nabucasa", "home_assistant_bluetooth", "habluetooth")

    def find_spec(self, name, path, target=None):
        if name.split(".")[0] in self.roots:
            return importlib.machinery.ModuleSpec(name, self, is_package=True)

    def create_module(self, spec):
        m = MagicMock(); m.__path__ = []; m.__name__ = spec.name; m.__spec__ = spec
        return m

    def exec_module(self, m):
        pass


sys.meta_path.insert(0, _Stub())
sys.path.insert(0, str(Path(__file__).parents[1]))

from ha_env import load_registries, pin_clock  # noqa: E402

pin_clock()

from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse  # noqa: E402
from homeassistant.config_entries import ConfigEntry, ConfigSubentryData  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402

from custom_components.smart_heating.coordinator import HeatingCoordinator  # noqa: E402
from custom_components.smart_heating.core import Mode, Override  # noqa: E402
from custom_components.smart_heating.core.learn import HEAT_NEEDED  # noqa: E402
from homeassistant.exceptions import HomeAssistantError  # noqa: E402
import custom_components.smart_heating.coordinator as _coord  # noqa: E402

_coord.TRV_STAGGER_S = 0


async def main() -> None:
    hass = HomeAssistant(tempfile.mkdtemp())
    await hass.config.async_set_time_zone("Europe/London")
    await load_registries(hass)
    await hass.async_start()

    calls = []

    async def record(call):
        calls.append((call.domain, call.service, dict(call.data)))
        if call.domain == "switch":
            hass.states.async_set(call.data["entity_id"], "on" if call.service == "turn_on" else "off")
        if call.domain == "climate":
            hass.states.async_set(call.data["entity_id"], "heat", {"temperature": call.data["temperature"]})

    async def forecast(call) -> ServiceResponse:
        now = dt_util.utcnow()
        return {call.data["entity_id"][0] if isinstance(call.data["entity_id"], list) else call.data["entity_id"]: {
            "forecast": [{"datetime": (now + timedelta(hours=h)).isoformat(), "temperature": 6 + h % 5} for h in range(24)]
        }}

    hass.services.async_register("switch", "turn_on", record)
    hass.services.async_register("switch", "turn_off", record)
    hass.services.async_register("climate", "set_temperature", record)
    hass.services.async_register("weather", "get_forecasts", forecast, supports_response=SupportsResponse.ONLY)

    hass.states.async_set("switch.heating", "off")
    hass.states.async_set("alarm_control_panel.alarmo", "disarmed")
    hass.states.async_set("weather.home", "cloudy")
    hass.states.async_set("sensor.outdoor_temperature", "7.0", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.gas", "1000.0", {"unit_of_measurement": "m³"})
    hass.states.async_set("sensor.living_t", "18.0")
    hass.states.async_set("sensor.bed_t", "19.5")
    hass.states.async_set("sensor.hall_t", "18.2")
    hass.states.async_set("binary_sensor.living_presence", "on")
    hass.states.async_set("climate.living_trv", "heat", {"temperature": 5})
    hass.states.async_set("climate.bed_trv", "heat", {"temperature": 5})

    def sub(sid, data):
        return ConfigSubentryData(subentry_id=sid, subentry_type="room", title=data["name"], data=data, unique_id=None)

    entry = ConfigEntry(
        version=1, minor_version=1, domain="smart_heating", title="Smart Heating",
        data={"boiler_switch": "switch.heating", "weather": "weather.home",
              "outdoor_temperature": "sensor.outdoor_temperature", "gas_meter": "sensor.gas", "gas_rate": "sensor.gas_rate",
              "alarm_panel": "alarm_control_panel.alarmo"},
        options={}, source="user", unique_id="smart_heating", discovery_keys={},
        subentries_data=[
            sub("living", {"name": "Living room", "floor": 1, "priority": "a", "comfort": 19.0,
                           "temperature_sensor": "sensor.living_t", "trvs": ["climate.living_trv"],
                           "presence": ["binary_sensor.living_presence"]}),
            sub("bed", {"name": "Bedroom", "floor": 2, "priority": "a", "comfort": 18.5,
                        "temperature_sensor": "sensor.bed_t", "trvs": ["climate.bed_trv"]}),
            sub("hall", {"name": "Hall", "floor": 0, "priority": "c", "comfort": 17.0,
                         "temperature_sensor": "sensor.hall_t"}),
        ],
    )

    c = HeatingCoordinator(hass, entry)
    c.async_config_entry_first_refresh = c.async_refresh  # no config entry manager here
    # Presence must be held for 5 min to count: backdate it.
    hass.states.async_set("binary_sensor.living_presence", "on", force_update=True)
    object.__setattr__(hass.states.get("binary_sensor.living_presence"), "last_changed", dt_util.utcnow() - timedelta(minutes=10))
    object.__setattr__(hass.states.get("switch.heating"), "last_changed", dt_util.utcnow() - timedelta(minutes=90))
    await c.async_start()
    await hass.async_block_till_done()
    assert c.fresh, "first start of a new setup"
    p = c.data
    print("monitor-only plan:", p.status, "|", p.reason, "| boiler", p.boiler_on, "| open", p.open_rooms)
    print("house", c.house_temp, "floors", c.floor_temps, "outdoor mean", c.outdoor_mean, "fmin", c.forecast_min_24h)
    assert p.boiler_on and "living" in p.open_rooms and calls == [], calls

    # No calibration lock: heating starts while learning carries on in the background.
    assert not c.calibrated
    await c.async_set_monitor_only(False)
    await c.async_refresh()
    for _ in range(40):
        await asyncio.sleep(0.25)
        if any(cl[0] == "switch" for cl in calls):
            break
    print("service calls:", calls)
    assert ("climate", "set_temperature", {"entity_id": "climate.living_trv", "temperature": 22}) in calls
    assert ("switch", "turn_on", {"entity_id": "switch.heating"}) in calls

    # Gas: the meter is the truth for the total; burning time shares it between heating, hot water and other.
    c.energy.heat_only_min = 60.0  # an hour of heating so far today
    hass.states.async_set("sensor.gas", "1001.5", {"unit_of_measurement": "m³"})  # 16.8 kWh on the meter
    await c.async_refresh()
    print("gas split (heating, hot water, other, house):", (c.gas_kwh, c.gas_hw_kwh, c.gas_other_kwh, c.gas_house_kwh), "| £", c.gas_cost)
    assert c.gas_measured and abs(c.gas_house_kwh - 16.8) < 0.01
    assert abs(c.gas_kwh - 10.5) < 0.3, c.gas_kwh  # 1 h at the starting rate: 70% of 15 kW
    assert abs(c.gas_kwh + c.gas_hw_kwh + c.gas_other_kwh - c.gas_house_kwh) < 0.05
    assert abs(c.gas_cost - c.gas_kwh * 0.06) < 0.02 and c.gas_price_from == "fixed", "heating gas only, at the unit price"
    # A unit rate sensor (here in pence) prices each new kWh at the rate when it was used.
    hass.states.async_set("sensor.gas_rate", "10.0", {"unit_of_measurement": "p/kWh"})
    cost0, kwh0 = c.gas_cost, c.gas_kwh
    c.energy.heat_only_min += 30.0
    await c.async_refresh()
    print("gas with rate sensor:", c.gas_kwh, "kWh | £", c.gas_cost, "|", c.gas_price_from, c.gas_price_now)
    assert c.gas_price_from == "rate sensor" and abs(c.gas_cost - (cost0 + (c.gas_kwh - kwh0) * 0.10)) < 0.02
    # Day change: yesterday's meter total is shared out by the model and recorded.
    c.energy.day = (dt_util.as_local(dt_util.utcnow()).date() - timedelta(days=1)).isoformat()
    await c.async_refresh()
    y = c.gas_yesterday
    print("gas yesterday:", y)
    assert c.gas_days and c.gas_days[-1].day == y["day"] and abs(y["meter_kwh"] - 16.8) < 0.05
    assert abs(y["heating_kwh"] + y["hot_water_kwh"] + y["other_kwh"] - y["meter_kwh"]) < 0.05
    # Ten meter days with a boiler really burning 12 kWh/h for heating and 9 for hot water: the rates follow.
    import random
    from custom_components.smart_heating.core.consumption import DayRecord
    rng = random.Random(3)
    c.gas_days = []
    for i in range(10):
        heat, hw = rng.uniform(2, 6), rng.uniform(0.5, 1.5)
        c.gas_days.append(DayRecord(f"2025-12-{i + 1:02d}", 12.0 * heat + 9.0 * hw + 0.6, {"heating": heat, "hot_water": hw, "cold": 0.0}))
    c._refit_gas()
    print("learned gas rates:", c.gas_rates.rates, "base", c.gas_rates.base, "days", c.gas_rates.days, "error", c.gas_rates.error)
    assert abs(c.gas_rates.rates["heating"] - 12) < 0.8 and c.gas_rates.days == 10
    # No smart meter: the same split from the starting rates (70% of the boiler's input), as an estimate.
    c.house_cfg["energy_source"] = "estimate"
    c.gas_days = []  # a home that never had a meter (one that had keeps the rates it learned)
    c._refit_gas()
    c.energy.heat_only_min, c.energy.hw_only_min, c.energy.both_min, c.energy.other_min = 120.0, 30.0, 0.0, 0.0
    await c.async_refresh()
    print("no meter (heating, hot water, other, house, measured):", c.gas_kwh, c.gas_hw_kwh, c.gas_other_kwh, c.gas_house_kwh, c.gas_measured)
    assert not c.gas_measured and c.gas_house_kwh is None
    assert abs(c.gas_kwh - 21.0) < 0.3 and abs(c.gas_hw_kwh - 5.25) < 0.3 and c.gas_other_kwh is not None
    c.house_cfg["energy_source"] = "smart_meter"

    # Alarm armed away: heating off (safety only), mode preserved.
    hass.states.async_set("alarm_control_panel.alarmo", "armed_away")
    await c.async_refresh()
    print("armed away ->", c.data.status, c.data.boiler_on, "| mode kept:", c.mode.value)
    assert c.data.status == "away" and not c.data.boiler_on and c.mode is Mode.AUTO
    hass.states.async_set("sensor.living_t", "11.0")
    await c.async_refresh()
    print("armed away + frost ->", c.data.status, c.data.boiler_on)
    assert c.data.boiler_on
    hass.states.async_set("sensor.living_t", "18.0")
    hass.states.async_set("alarm_control_panel.alarmo", "disarmed")
    await c.async_refresh()
    print("disarmed ->", c.data.status, "| log:", [e["message"] for e in list(c.log)[:3]])
    assert c.data.status != "away"

    # One Cycle with nothing to heat waits 3 minutes, saying why, then Off.
    hass.states.async_set("sensor.living_t", "19.5")
    c.monitor_only = True
    await c.async_set_mode(Mode.ONE_CYCLE)
    print("one cycle wait ->", c.mode.value, "|", c.data.reason, "|", c.one_cycle_wait)
    assert c.mode is Mode.ONE_CYCLE and c.one_cycle_wait and c.one_cycle_wait["reasons"]
    c._one_cycle_since -= timedelta(minutes=4)
    await c.async_refresh()
    print("one cycle ->", c.mode.value, "|", c.data.reason)
    assert c.mode is Mode.OFF and c.one_cycle_wait is None and "One Cycle ended: nothing needed heat" in c.data.reason

    # Heat now while Off starts One Cycle; when the room reaches its target, back to Off.
    hass.states.async_set("sensor.living_t", "18.8")
    await c.async_set_override("living", Override.HEAT)
    assert c.mode is Mode.ONE_CYCLE and c.data.rooms["living"].verdict.value == "approved", c.data.rooms["living"]
    hass.states.async_set("sensor.living_t", "19.5")
    await c.async_refresh()
    assert c.mode is Mode.OFF and c.rooms["living"].override is Override.AUTO, (c.mode, c.rooms["living"].override)
    print("heat now from off -> one cycle -> off ok")

    # Last night replayed: mild day (12.3° against a gate of 10°). Auto waits for a room in use that is
    # 0.9° short; One Cycle heats it; an empty room waits either way.
    from dataclasses import replace
    gate_before = c.settings
    c.settings = replace(c.settings, season_gate=10.0)
    c.house_cfg["outdoor_mean"] = "sensor.mean"
    hass.states.async_set("sensor.mean", "12.3")
    hass.states.async_set("sensor.living_t", "18.1")
    hass.states.async_set("sensor.hall_t", "16.0")
    c.mode = Mode.AUTO
    await c.async_refresh()
    v = {r: (d.verdict.value, d.reason) for r, d in c.data.rooms.items()}
    print("mild day, auto:", v)
    assert v["living"][0] == "vetoed" and v["living"][1].endswith("not cold enough")
    assert v["hall"][0] == "vetoed" and v["hall"][1].endswith("empty room")
    await c.async_set_mode(Mode.ONE_CYCLE)
    v = {r: (d.verdict.value, d.reason) for r, d in c.data.rooms.items()}
    print("mild day, one cycle:", v)
    assert v["living"][0] == "approved" and v["hall"][0] == "vetoed"
    await c.async_set_mode(Mode.OFF)
    c.settings = gate_before
    c.house_cfg.pop("outdoor_mean")
    hass.states.async_set("sensor.living_t", "19.5")
    hass.states.async_set("sensor.hall_t", "18.2")

    # Setpoints: house target shifts every room and the baseline; rooms keep their difference.
    assert c.setpoints.house == 19.0, c.setpoints.house
    await c.async_set_house_target(20)
    assert c.room_comfort(c.rooms["living"]) == 20.0 and c.room_comfort(c.rooms["hall"]) == 18.0
    assert c.effective_settings.baseline_day == 18.0
    await c.async_set_room_target("living", 21)
    await c.async_set_house_target(19)
    assert c.room_comfort(c.rooms["living"]) == 20.0, c.room_comfort(c.rooms["living"])
    c.mode = Mode.AUTO
    await c.async_refresh()
    assert c.data.rooms["living"].need.target == 20.0, c.data.rooms["living"].need.target
    print("setpoints ok: living", c.room_comfort(c.rooms["living"]), "hall", c.room_comfort(c.rooms["hall"]))

    # Heat test: opens only rooms that still need heating data, boiler on, closes a room at
    # 1° above its start or 21.5°, ends when every room is closed and restores the TRVs.
    async def tick():
        await c.async_refresh()
        await asyncio.sleep(0.3)
        await hass.async_block_till_done()

    def boiler_rested():
        object.__setattr__(hass.states.get("switch.heating"), "last_changed", dt_util.utcnow() - timedelta(minutes=30))
        c._boiler_cmd_at = dt_util.utcnow() - timedelta(minutes=30)
        c._boiler_cmds = []

    trv_closed = c.settings.trv_closed
    hass.states.async_set("switch.heating", "off")
    boiler_rested()
    hass.states.async_set("climate.bed_trv", "heat", {"temperature": 16, "max_temp": 30})
    hass.states.async_set("sensor.bed_t", "20.8")
    c.rooms["living"].model.heat_n = HEAT_NEEDED  # living already has its heating data
    c.mode, c.monitor_only = Mode.AUTO, True
    calls.clear()
    await c.async_heat_test(True)
    await hass.async_block_till_done()
    assert ("climate", "set_temperature", {"entity_id": "climate.bed_trv", "temperature": 30.0}) in calls, calls
    assert not any(cl[2].get("entity_id") == "climate.living_trv" for cl in calls), calls
    assert "living" in c.heat_test["closed"] and c.heat_test["start_temps"]["bed"] == 20.8
    assert ("switch", "turn_on", {"entity_id": "switch.heating"}) in calls
    assert c.data.status == "testing", c.data.status
    hass.states.async_set("sensor.bed_t", "21.4")  # stop is min(21.5, 20.8 + 1)
    await tick()
    assert c.heat_test is not None and "bed" not in c.heat_test["closed"]
    hass.states.async_set("sensor.bed_t", "21.5")
    await tick()
    assert ("climate", "set_temperature", {"entity_id": "climate.bed_trv", "temperature": trv_closed}) in calls, calls
    assert c.heat_test is None, "every room closed: the test ends by itself"
    assert ("climate", "set_temperature", {"entity_id": "climate.bed_trv", "temperature": 16.0}) in calls, calls
    assert hass.states.get("switch.heating").state == "off", "test end must switch off even inside the guard time"
    print("heat test cap ok:", [e["message"] for e in list(c.log)[:3]])

    # A room stops 1° above where it started.
    c.rooms["living"].model.heat_n = 0
    hass.states.async_set("sensor.bed_t", "19.5")
    hass.states.async_set("sensor.living_t", "19.0")
    boiler_rested()
    await c.async_heat_test(True)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.living_t", "20.0")
    await tick()
    assert "living" in c.heat_test["closed"] and "bed" not in c.heat_test["closed"], c.heat_test["closed"]
    await c.async_heat_test(False)
    await hass.async_block_till_done()
    assert c.heat_test is None

    # Not offered when every room already has its heating data.
    for r in c.rooms.values():
        r.model.heat_n = HEAT_NEEDED
    calls.clear()
    try:
        await c.async_heat_test(True)
        raise SystemExit("expected: heat test not needed")
    except HomeAssistantError as err:
        assert "isn't needed" in str(err)
    assert c.heat_test is None and not calls, calls
    for r in c.rooms.values():
        r.model.heat_n = 0

    # A radiator without a smart valve can only be stopped with the boiler: the test ends at 21.5°.
    hass.states.async_set("sensor.living_t", "19.0")
    hass.states.async_set("sensor.bed_t", "19.5")
    boiler_rested()
    await c.async_heat_test(True)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.hall_t", "21.6")
    await tick()
    recent = [e["message"] for e in list(c.log)[:5]]
    print("unvalved room ->", next((m for m in recent if "Hall reached" in m), recent)[:100])
    assert c.heat_test is None and any("Hall reached 21.6" in m for m in recent), recent
    hass.states.async_set("sensor.hall_t", "21.3")
    boiler_rested()
    try:
        await c.async_heat_test(True)
        raise SystemExit("expected: unvalved room too warm to start")
    except HomeAssistantError as err:
        assert "Hall" in str(err)
    hass.states.async_set("sensor.hall_t", "18.2")

    # Off cancels everything at once: the heat test, Heat now, and the boiler, even inside the guard time.
    hass.states.async_set("sensor.living_t", "19.0")
    hass.states.async_set("sensor.bed_t", "19.5")
    boiler_rested()
    await c.async_heat_test(True)
    await hass.async_block_till_done()
    assert hass.states.get("switch.heating").state == "on"
    c.rooms["bed"].override = Override.HEAT
    calls.clear()
    await c.async_set_mode(Mode.OFF)
    await hass.async_block_till_done()
    print("off cancels ->", [e["message"][:60] for e in list(c.log)[:3]])
    assert c.heat_test is None and c.rooms["bed"].override is Override.AUTO
    assert hass.states.get("switch.heating").state == "off" and ("switch", "turn_off", {"entity_id": "switch.heating"}) in calls
    c.mode = Mode.AUTO

    # Something else switches the boiler off during a heat test: back off and stop the test, never fight.
    hass.states.async_set("sensor.bed_t", "19.5")
    object.__setattr__(hass.states.get("switch.heating"), "last_changed", dt_util.utcnow() - timedelta(minutes=30))
    c._boiler_cmd_at = dt_util.utcnow() - timedelta(minutes=30)
    c.external_hold_until = c.boiler_locked_until = None
    calls.clear()
    await c.async_heat_test(True)
    await hass.async_block_till_done()
    assert hass.states.get("switch.heating").state == "on"
    c._boiler_cmd_at -= timedelta(seconds=30)
    hass.states.async_set("switch.heating", "off")  # e.g. an old automation
    for _ in range(5):
        await c.async_refresh()
        await asyncio.sleep(0.1); await hass.async_block_till_done()
    ons = [cl for cl in calls if cl[1] == "turn_on"]
    print("external off during test -> test running:", c.heat_test is not None, "| turn_on calls:", len(ons), "| log:", c.log[0]["message"][:70])
    assert c.heat_test is None and len(ons) == 1 and hass.states.get("switch.heating").state == "off"

    # Guard: a command inside 2 min of the last change is refused; too many switches lock control.
    c.external_hold_until = None
    calls.clear()
    await c._boiler(True)
    assert not calls, "guard must refuse switching right after a change"
    c._boiler_cmds = [dt_util.utcnow() - timedelta(minutes=m) for m in range(6)]
    c._boiler_cmd_at = dt_util.utcnow() - timedelta(minutes=5)
    object.__setattr__(hass.states.get("switch.heating"), "last_changed", dt_util.utcnow() - timedelta(minutes=5))
    await c._boiler(True)
    assert not calls and c.boiler_locked_until is not None
    print("guard and flicker lockout ok:", c.log[0]["message"][:80])
    c.boiler_locked_until = None
    info = c.calibration_info
    print("heat test ok | calibration info:", {k: info[k] for k in ("rooms_needed", "cooling_hours_left", "eta_hours")})

    # Start heating before learning finishes: no lock, no skip needed.
    await c.async_set_monitor_only(True)
    await c.async_start_control()
    assert not c.monitor_only and not c.calibrated

    # Relearn clears a room's learned data.
    c.rooms["bed"].model.heat_n = 5
    await c.async_relearn(["bed"])
    assert c.rooms["bed"].model.heat_n == 0 and c.rooms["bed"].model.free.n == 0
    assert any(e["message"].startswith("Relearning") and e["room"] == "Bedroom" for e in list(c.log)[:5])

    # Repairs: a hot water signal that is the boiler's own sensor is ignored and flagged.
    from homeassistant.helpers import issue_registry as ir
    c.house_cfg["hw_calling"] = "switch.heating"
    c._check_setup()
    assert c.hw_entity is None and ir.async_get(hass).async_get_issue("smart_heating", "hw_same_as_boiler")
    c.house_cfg.pop("hw_calling")
    c._check_setup()
    assert ir.async_get(hass).async_get_issue("smart_heating", "hw_same_as_boiler") is None

    # Repairs: heating called but the boiler running sensor stays off for 20 min.
    c.house_cfg["boiler_on_sensor"] = "binary_sensor.burner"
    hass.states.async_set("binary_sensor.burner", "off")
    hass.states.async_set("switch.heating", "on")
    t0 = dt_util.utcnow()
    c._check_boiler_response(t0)
    c._check_boiler_response(t0 + timedelta(minutes=19))
    assert ir.async_get(hass).async_get_issue("smart_heating", "boiler_sensor_silent") is None
    c._check_boiler_response(t0 + timedelta(minutes=21))
    assert ir.async_get(hass).async_get_issue("smart_heating", "boiler_sensor_silent")
    hass.states.async_set("binary_sensor.burner", "on")
    c._check_boiler_response(t0 + timedelta(minutes=22))
    assert ir.async_get(hass).async_get_issue("smart_heating", "boiler_sensor_silent") is None
    c.house_cfg.pop("boiler_on_sensor")

    # Log: a changing trend in a reason is not news.
    assert _coord._NUMBERS.sub("#", "coasting +0.31/h") == _coord._NUMBERS.sub("#", "coasting +0.46/h")
    print("start, relearn, repairs, log key ok")

    # No outdoor sensor: the weather entity's own temperature is used.
    c.house_cfg.pop("outdoor_temperature")
    hass.states.async_set("weather.home", "cloudy", {"temperature": 7.5})
    c.outdoor._hist.clear()  # one reading per 5 min is kept; start clean
    await c.async_refresh()
    assert c.outdoor.now_temp(dt_util.utcnow()) == 7.5
    # A failed forecast fetch is retried within minutes and keeps the forecast already held.
    pts = len(c.outdoor.forecast)
    hass.services.async_remove("weather", "get_forecasts")  # e.g. the weather integration still starting
    c._forecast_at = None
    await c.async_refresh()
    assert pts and len(c.outdoor.forecast) == pts
    assert timedelta(minutes=24) < dt_util.utcnow() - c._forecast_at < timedelta(minutes=26), c._forecast_at
    hass.services.async_register("weather", "get_forecasts", forecast, supports_response=SupportsResponse.ONLY)
    c.house_cfg["outdoor_temperature"] = "sensor.outdoor_temperature"
    print("outdoor fallback and forecast retry ok")

    # Every platform's entities build and report without errors.
    import importlib
    from types import SimpleNamespace
    fake_entry = SimpleNamespace(runtime_data=c)
    ents = []
    for plat in ("sensor", "binary_sensor", "select", "switch", "number"):
        mod = importlib.import_module(f"custom_components.smart_heating.{plat}")
        await mod.async_setup_entry(hass, fake_entry, lambda e, **kw: ents.extend(e))
    for e in ents:
        e.hass = hass
        for attr in ("native_value", "is_on", "current_option", "extra_state_attributes"):
            if hasattr(type(e), attr):
                getattr(e, attr)
    nums = [e for e in ents if type(e).__name__ in ("HouseTarget", "RoomTarget")]
    print("entities:", len(ents), "| numbers:", [(type(n).__name__, n.native_value) for n in nums])
    cal = next(e for e in ents if getattr(e, "_kind", None) == "calibration")
    od = next(e for e in ents if getattr(e, "_kind", None) == "outdoor_day_mean").extra_state_attributes
    assert {"observed_mean_12h", "forecast_mean_12h", "forecast_mean_24h", "forecast_min_12h", "forecast_min_24h"} <= set(od), od
    print("outdoor day mean attrs:", {k: v for k, v in od.items() if k != "kind"})
    print("calibration attrs:", {k: v for k, v in cal.extra_state_attributes.items() if k != "rooms"})

    # Window advice: damp bedroom, rain outside but far drier air. Only the person at home is told.
    from homeassistant.config_entries import ConfigEntry as _CE
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    app = _CE(version=1, minor_version=1, domain="mobile_app", title="app", data={}, options={}, source="user",
              unique_id=None, discovery_keys={}, subentries_data=[])
    from unittest.mock import MagicMock
    saved_entries, hass.config_entries = hass.config_entries, MagicMock()  # the device registry only checks the entry exists
    hass.config_entries.async_get_entry = lambda eid: app if eid == app.entry_id else None
    pushes = []
    for who in ("albert", "wife"):
        dev = dr.async_get(hass).async_get_or_create(config_entry_id=app.entry_id, identifiers={("mobile_app", who)},
                                                     name=f"{who.title()} Phone")
        er.async_get(hass).async_get_or_create("device_tracker", "mobile_app", who, device_id=dev.id,
                                               suggested_object_id=f"{who}_phone")

        async def push(call, who=who):
            pushes.append((who, dict(call.data)))
        hass.services.async_register("notify", f"mobile_app_{who}_phone", push)
    hass.config_entries = saved_entries
    hass.states.async_set("person.albert", "not_home", {"device_trackers": ["device_tracker.albert_phone"]})
    hass.states.async_set("person.wife", "home", {"device_trackers": ["device_tracker.wife_phone"]})
    c.notify_people = ["person.albert", "person.wife"]
    assert c.phones() == ["notify.mobile_app_albert_phone", "notify.mobile_app_wife_phone"], c.phones()
    c.mode = Mode.OFF  # boiler stays off: a burst is never advised while it heats
    c.rooms["bed"].humidity_entity = "sensor.bed_rh"
    hass.states.async_set("sensor.bed_rh", "80")
    hass.states.async_set("weather.home", "rainy", {"humidity": 95, "temperature": 7.0, "wind_speed": 5, "wind_speed_unit": "m/s"})
    hass.states.async_set("switch.heating", "off")
    await c.async_refresh()
    await hass.async_block_till_done()
    from custom_components.smart_heating.sensor import WindowAdviceSensor
    wa = WindowAdviceSensor(c).extra_state_attributes
    print("window advice:", WindowAdviceSensor(c).native_value, "|", wa["reason"], "| pushed to:", [w for w, _ in pushes])
    assert WindowAdviceSensor(c).native_value == "open" and wa["advice"] == "dry" and wa["rooms"] == ["Bedroom"], wa
    assert [w for w, _ in pushes] == ["wife"] and pushes[0][1]["data"] == {"tag": "smart_heating_windows"}, pushes
    # She goes out before the burst ends: the close still goes to her phone, not to whoever is home now.
    hass.states.async_set("person.wife", "not_home", {"device_trackers": ["device_tracker.wife_phone"]})
    hass.states.async_set("person.albert", "home", {"device_trackers": ["device_tracker.albert_phone"]})
    c.windows.advice.until = dt_util.utcnow() - timedelta(seconds=1)
    await c.async_refresh()
    await hass.async_block_till_done()
    print("burst over ->", c.windows.advice.action, c.windows.advice.kind, "| pushed to:", [w for w, _ in pushes])
    assert c.windows.advice.kind == "done" and [w for w, _ in pushes] == ["wife", "wife"] and not c._window_open_to
    c.mode = Mode.AUTO

    # The log survives a restart.
    await c.async_stop()
    c2 = HeatingCoordinator(hass, entry)
    await c2._load()
    assert any(e["message"].startswith("Relearning") for e in c2.log), "log kept across restarts"
    assert not c2.fresh, "a restart is not a new setup"
    assert c2.windows.advice.kind == "done" and c2.windows.next_dry is not None, "window advice kept across restarts"
    # Deleting the integration deletes its stored data.
    import os
    from custom_components.smart_heating import async_remove_entry
    stored = hass.config.path(".storage", f"smart_heating.{entry.entry_id}")
    assert os.path.exists(stored)
    await async_remove_entry(hass, entry)
    assert not os.path.exists(stored), "store removed with the entry"
    await hass.async_stop()
    print("SMOKE OK")


asyncio.run(main())
