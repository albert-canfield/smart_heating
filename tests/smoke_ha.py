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
from custom_components.smart_heating.core import Mode  # noqa: E402
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
              "outdoor_temperature": "sensor.outdoor_temperature", "gas_meter": "sensor.gas",
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
    p = c.data
    print("monitor-only plan:", p.status, "|", p.reason, "| boiler", p.boiler_on, "| open", p.open_rooms)
    print("house", c.house_temp, "floors", c.floor_temps, "outdoor mean", c.outdoor_mean, "fmin", c.forecast_min_24h)
    assert p.boiler_on and "living" in p.open_rooms and calls == [], calls

    # Control is locked until calibrated.
    try:
        await c.async_set_monitor_only(False)
        raise SystemExit("expected calibration lock")
    except Exception as err:  # noqa: BLE001
        print("lock ok:", str(err)[:60], "...")

    # Skip calibration and let it act.
    c.skip_calibration = True
    await c.async_set_monitor_only(False)
    await c.async_refresh()
    for _ in range(40):
        await asyncio.sleep(0.25)
        if any(cl[0] == "switch" for cl in calls):
            break
    print("service calls:", calls)
    assert ("climate", "set_temperature", {"entity_id": "climate.living_trv", "temperature": 22}) in calls
    assert ("switch", "turn_on", {"entity_id": "switch.heating"}) in calls

    # Gas accounting from the meter.
    hass.states.async_set("sensor.gas", "1001.5", {"unit_of_measurement": "m³"})
    await c.async_refresh()
    print("gas today kWh", c.gas_kwh, "measured", c.gas_measured, "cost", c.gas_cost)
    assert c.gas_measured and abs(c.gas_kwh - 16.8) < 0.01

    # Alarm armed away: heating off (safety only), mode preserved.
    hass.states.async_set("alarm_control_panel.alarmo", "armed_away")
    await c.async_refresh()
    print("armed away ->", c.data.status, c.data.boiler_on, "| mode kept:", c.mode.value)
    assert c.data.status == "away" and not c.data.boiler_on and c.mode is Mode.CONTINUOUS
    hass.states.async_set("sensor.living_t", "11.0")
    await c.async_refresh()
    print("armed away + frost ->", c.data.status, c.data.boiler_on)
    assert c.data.boiler_on
    hass.states.async_set("sensor.living_t", "18.0")
    hass.states.async_set("alarm_control_panel.alarmo", "disarmed")
    await c.async_refresh()
    print("disarmed ->", c.data.status, "| log:", [e["message"] for e in list(c.log)[:3]])
    assert c.data.status != "away"

    # One Cycle ends itself when nothing needs heat.
    hass.states.async_set("sensor.living_t", "19.5")
    c.mode = Mode.ONE_CYCLE
    c.skip_calibration = False
    c.monitor_only = True
    await c.async_refresh()
    print("one cycle ->", c.mode.value, "|", c.data.reason)
    assert c.mode is Mode.OFF

    # Setpoints: house target shifts every room and the baseline; rooms keep their difference.
    assert c.setpoints.house == 19.0, c.setpoints.house
    await c.async_set_house_target(20)
    assert c.room_comfort(c.rooms["living"]) == 20.0 and c.room_comfort(c.rooms["hall"]) == 18.0
    assert c.effective_settings.baseline_day == 18.0
    await c.async_set_room_target("living", 21)
    await c.async_set_house_target(19)
    assert c.room_comfort(c.rooms["living"]) == 20.0, c.room_comfort(c.rooms["living"])
    c.mode = Mode.CONTINUOUS
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
    c.mode, c.monitor_only = Mode.CONTINUOUS, True
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

    # Start control before calibration needs explicit skip.
    c.skip_calibration = False
    try:
        await c.async_start_control()
        raise SystemExit("expected lock")
    except Exception as err:  # noqa: BLE001
        assert "Calibration" in str(err)
    await c.async_start_control(skip_calibration=True)
    assert not c.monitor_only and c.calibrated and c.force_start

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
    print("calibration attrs:", {k: v for k, v in cal.extra_state_attributes.items() if k != "rooms"})

    await c.async_stop()
    await hass.async_stop()
    print("SMOKE OK")


asyncio.run(main())
