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



async def setup(house_data, rooms, states):
    hass = HomeAssistant(tempfile.mkdtemp())
    await hass.config.async_set_time_zone("Europe/London")
    await load_registries(hass)
    await hass.async_start()
    calls = []

    async def record(call):
        calls.append((call.domain, call.service, dict(call.data)))
        eid = call.data["entity_id"]
        if call.domain == "climate" and call.service == "set_temperature":
            st = hass.states.get(eid)
            attrs = dict(st.attributes) if st else {}
            attrs["temperature"] = call.data["temperature"]
            hass.states.async_set(eid, call.data.get("hvac_mode", st.state if st else "heat"), attrs)
        if call.domain == "climate" and call.service == "set_hvac_mode":
            st = hass.states.get(eid)
            hass.states.async_set(eid, call.data["hvac_mode"], dict(st.attributes))

    for svc in ("set_temperature", "set_hvac_mode"):
        hass.services.async_register("climate", svc, record)
    for eid, (state, attrs) in states.items():
        hass.states.async_set(eid, state, attrs)
    entry = ConfigEntry(
        version=1, minor_version=1, domain="smart_heating", title="Smart Heating", data=house_data,
        options={}, source="user", unique_id="smart_heating", discovery_keys={},
        subentries_data=[ConfigSubentryData(subentry_id=sid, subentry_type="room", title=d["name"], data=d, unique_id=None) for sid, d in rooms],
    )
    c = HeatingCoordinator(hass, entry)
    c.async_config_entry_first_refresh = c.async_refresh
    return hass, c, calls


async def wait_calls(calls, pred):
    for _ in range(60):
        await asyncio.sleep(0.25)
        if pred():
            return


async def main() -> None:
    # 1) Valve only: no boiler control, no room thermometer (TRV reading), no outdoor source.
    hass, c, calls = await setup(
        {},
        [("living", {"name": "Living room", "floor": 1, "comfort": 19.0, "trvs": ["climate.living_trv"],
                     "presence": ["binary_sensor.p"]}),
         ("bed", {"name": "Bedroom", "floor": 2, "comfort": 18.5, "trvs": ["climate.bed_trv"]})],
        {"climate.living_trv": ("heat", {"temperature": 5, "current_temperature": 17.8}),
         "climate.bed_trv": ("heat", {"temperature": 22, "current_temperature": 20.4}),
         "binary_sensor.p": ("on", {})},
    )
    object.__setattr__(hass.states.get("binary_sensor.p"), "last_changed", dt_util.utcnow() - timedelta(minutes=10))
    await c.async_start()
    print("valve-only caps:", c.capabilities["profile"], "| calibrated (unavailable => unlocked):", c.calibrated)
    assert c.profile == "valve_only" and c.calibrated and not c.learnable
    print("room temp from TRV:", c.room_temp(c.rooms["living"]), "| plan:", c.data.status, c.data.open_rooms, c.data.close_rooms)
    assert c.room_temp(c.rooms["living"]) == 17.8
    await c.async_set_monitor_only(False)
    await c.async_refresh()
    await wait_calls(calls, lambda: len(calls) >= 2)
    print("calls:", calls)
    assert ("climate", "set_temperature", {"entity_id": "climate.living_trv", "temperature": 22}) in calls
    assert ("climate", "set_temperature", {"entity_id": "climate.bed_trv", "temperature": 5}) in calls
    assert not any(cl[0] in ("switch", "homeassistant") for cl in calls)
    await c.async_stop(); await hass.async_stop()

    # 2) Smart thermostat as the boiler control, single zone (no TRVs).
    hass, c, calls = await setup(
        {"boiler_switch": "climate.nest", "weather": "weather.x"},
        [("living", {"name": "Living room", "floor": 1, "comfort": 19.0, "temperature_sensor": "sensor.t", "presence": ["binary_sensor.p"]})],
        {"climate.nest": ("off", {"temperature": 15, "hvac_action": "idle"}),
         "sensor.t": ("17.5", {}), "binary_sensor.p": ("on", {}), "weather.x": ("cloudy", {})},
    )
    object.__setattr__(hass.states.get("binary_sensor.p"), "last_changed", dt_util.utcnow() - timedelta(minutes=10))
    object.__setattr__(hass.states.get("climate.nest"), "last_changed", dt_util.utcnow() - timedelta(minutes=90))
    hass.services.async_register("weather", "get_forecasts", lambda call: {"weather.x": {"forecast": []}},
                                 supports_response=SupportsResponse.ONLY)
    c.skip_calibration = True
    await c.async_start()
    print("thermostat caps:", c.profile, "| boiler state:", c.has_boiler_state)
    assert c.profile == "single_zone"
    await c.async_set_monitor_only(False)
    await c.async_refresh()
    await wait_calls(calls, lambda: calls)
    print("calls:", calls)
    assert ("climate", "set_temperature", {"entity_id": "climate.nest", "temperature": 25, "hvac_mode": "heat"}) in calls
    hass.states.async_set("sensor.t", "19.5")
    object.__setattr__(hass.states.get("climate.nest"), "last_changed", dt_util.utcnow() - timedelta(minutes=30))
    c._boiler_cmd_at = dt_util.utcnow() - timedelta(minutes=30)
    await c.async_refresh()
    await wait_calls(calls, lambda: any(cl[1] == "set_hvac_mode" for cl in calls))
    print("calls after warm:", calls[-1])
    assert calls[-1] == ("climate", "set_hvac_mode", {"entity_id": "climate.nest", "hvac_mode": "off"})
    await c.async_stop(); await hass.async_stop()

    # 3) Thermostat in setpoint style: it gets the room target, and the frost floor when off.
    hass, c, calls = await setup(
        {"boiler_switch": "climate.nest", "thermostat_style": "setpoint", "weather": "weather.x"},
        [("living", {"name": "Living room", "floor": 1, "comfort": 19.0, "temperature_sensor": "sensor.t", "presence": ["binary_sensor.p"]})],
        {"climate.nest": ("heat", {"temperature": 12, "hvac_action": "idle"}),
         "sensor.t": ("17.5", {}), "binary_sensor.p": ("on", {}), "weather.x": ("cloudy", {})},
    )
    object.__setattr__(hass.states.get("binary_sensor.p"), "last_changed", dt_util.utcnow() - timedelta(minutes=10))
    object.__setattr__(hass.states.get("climate.nest"), "last_changed", dt_util.utcnow() - timedelta(minutes=90))
    hass.services.async_register("weather", "get_forecasts", lambda call: {"weather.x": {"forecast": []}},
                                 supports_response=SupportsResponse.ONLY)
    c.skip_calibration = True
    await c.async_start()
    await c.async_set_monitor_only(False)
    await c.async_refresh()
    await wait_calls(calls, lambda: calls)
    print("setpoint style calls:", calls)
    assert ("climate", "set_temperature", {"entity_id": "climate.nest", "temperature": 19.0, "hvac_mode": "heat"}) in calls
    hass.states.async_set("sensor.t", "19.5")
    object.__setattr__(hass.states.get("climate.nest"), "last_changed", dt_util.utcnow() - timedelta(minutes=30))
    c._boiler_cmd_at = dt_util.utcnow() - timedelta(minutes=30)
    await c.async_refresh()
    await wait_calls(calls, lambda: calls[-1][2]["temperature"] == 12.0)
    assert calls[-1] == ("climate", "set_temperature", {"entity_id": "climate.nest", "temperature": 12.0, "hvac_mode": "heat"}), calls[-1]
    await c.async_stop(); await hass.async_stop()

    # 4) Hot water systems: S-plan cylinder-only burns are not radiator heat; combi has no pause.
    room = [("living", {"name": "Living room", "floor": 1, "comfort": 19.0, "temperature_sensor": "sensor.t"})]
    base = {"sensor.t": ("18.0", {}), "switch.ch": ("off", {}), "binary_sensor.fire": ("on", {}),
            "binary_sensor.hw": ("on", {}), "sensor.out": ("6.0", {})}
    hass, c, calls = await setup({"boiler_switch": "switch.ch", "boiler_on_sensor": "binary_sensor.fire",
                                  "hw_calling": "binary_sensor.hw", "outdoor_temperature": "sensor.out"}, room, base)
    await c.async_start()
    heating, _ = c._radiators_heating(dt_util.utcnow())
    print("s-plan: firing for cylinder only -> radiators heating:", heating, "| hw priority:", c.settings.hw_priority)
    assert heating is False and c.settings.hw_priority
    await c.async_stop(); await hass.async_stop()
    base["switch.ch"] = ("on", {})
    hass, c, calls = await setup({"boiler_switch": "switch.ch", "boiler_on_sensor": "binary_sensor.fire",
                                  "hw_calling": "binary_sensor.hw", "outdoor_temperature": "sensor.out",
                                  "hot_water_system": "combi"}, room, base)
    await c.async_start()
    heating, _ = c._radiators_heating(dt_util.utcnow())
    print("combi: tap running -> radiators heating:", heating, "| hw priority:", c.settings.hw_priority)
    assert heating is False and not c.settings.hw_priority
    await c.async_stop(); await hass.async_stop()
    print("PROFILES OK")


asyncio.run(main())
