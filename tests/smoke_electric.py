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

from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.config_entries import ConfigEntry, ConfigSubentryData  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402

from custom_components.smart_heating.coordinator import HeatingCoordinator  # noqa: E402
import voluptuous_serialize  # noqa: E402
from homeassistant.config_entries import ConfigEntries  # noqa: E402
from homeassistant.helpers import config_validation as cv  # noqa: E402
from homeassistant.helpers import device_registry as dr, entity_registry as er, area_registry as ar  # noqa: E402
import custom_components.smart_heating.coordinator as _coord  # noqa: E402
from custom_components.smart_heating.config_flow import SmartHeatingConfigFlow, RoomSubentryFlow  # noqa: E402

_coord.TRV_STAGGER_S = 0


def ser(result):
    if result.get("data_schema") is not None:
        voluptuous_serialize.convert(result["data_schema"], custom_serializer=cv.custom_serializer)
    return result


async def main() -> None:
    hass = HomeAssistant(tempfile.mkdtemp())
    await hass.config.async_set_time_zone("Europe/London")
    await load_registries(hass)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    await hass.async_start()

    calls = []

    async def record(call):
        calls.append((call.domain, call.service, dict(call.data)))
        eid = call.data["entity_id"]
        st = hass.states.get(eid)
        attrs = dict(st.attributes) if st else {}
        if call.domain == "switch":
            hass.states.async_set(eid, "on" if call.service == "turn_on" else "off", attrs)
        elif call.service == "set_temperature":
            attrs["temperature"] = call.data["temperature"]
            hass.states.async_set(eid, call.data.get("hvac_mode", st.state), attrs)
        elif call.service == "set_hvac_mode":
            hass.states.async_set(eid, call.data["hvac_mode"], attrs)

    for d, svc in (("switch", "turn_on"), ("switch", "turn_off"), ("climate", "set_temperature"), ("climate", "set_hvac_mode")):
        hass.services.async_register(d, svc, record)

    # A coffee shop: one area with a smart plug heater (measures power) and a smart climate heater.
    area = ar.async_get(hass).async_create("Cafe")
    dreg, ereg = dr.async_get(hass), er.async_get(hass)
    from homeassistant.config_entries import ConfigEntry as _CE
    other = _CE(version=1, minor_version=1, domain="demo", title="demo", data={}, options={}, source="user", unique_id=None, discovery_keys={}, subentries_data=[])
    hass.config_entries._entries[other.entry_id] = other
    plug = dreg.async_get_or_create(config_entry_id=other.entry_id, identifiers={("demo", "plug")}, name="Heater plug", model="Smart Plug")
    dreg.async_update_device(plug.id, area_id=area.id)
    ereg.async_get_or_create("switch", "demo", "plug_sw", device_id=plug.id, suggested_object_id="cafe_heater")
    ereg.async_get_or_create("sensor", "demo", "plug_w", device_id=plug.id, suggested_object_id="cafe_heater_power", original_device_class="power")
    panel = dreg.async_get_or_create(config_entry_id=other.entry_id, identifiers={("demo", "panel")}, name="Panel heater", model="Wifi panel")
    dreg.async_update_device(panel.id, area_id=area.id)
    ereg.async_get_or_create("climate", "demo", "panel", device_id=panel.id, suggested_object_id="cafe_panel")
    ereg.async_get_or_create("sensor", "demo", "cafe_t", suggested_object_id="cafe_temperature", original_device_class="temperature")
    ereg.async_update_entity("sensor.cafe_temperature", area_id=area.id)
    hass.states.async_set("switch.cafe_heater", "off")
    hass.states.async_set("sensor.cafe_heater_power", "0", {"unit_of_measurement": "W", "device_class": "power"})
    hass.states.async_set("climate.cafe_panel", "off", {"temperature": 15, "current_temperature": 17, "hvac_modes": ["off", "heat"], "preset_mode": "eco", "hvac_action": "off"})
    hass.states.async_set("sensor.cafe_temperature", "16.0", {"device_class": "temperature"})
    hass.states.async_set("weather.home", "cloudy")

    # Wizard: electric skips boiler, hot water and gas meter steps.
    flow = SmartHeatingConfigFlow()
    flow.hass, flow.handler, flow.flow_id, flow.context = hass, "smart_heating", "f1", {"source": "user"}
    r = ser(await flow.async_step_user())
    assert r["step_id"] == "type", r
    r = ser(await flow.async_step_type({"heating_type": "electric"}))
    assert r["step_id"] == "outside", r
    r = ser(await flow.async_step_outside({"weather": "weather.home"}))
    assert r["step_id"] == "extras" and "gas_meter" not in str(r["data_schema"].schema), r
    r = ser(await flow.async_step_extras({}))
    assert r["step_id"] == "rooms", r
    r = await flow.async_step_rooms({"areas": [area.id]})
    assert r["type"] == "create_entry", r
    room = r["subentries"][0]["data"]
    print("wizard (electric):", r["data"], "| room:", room)
    assert set(room["heaters"]) == {"switch.cafe_heater", "climate.cafe_panel"} and "trvs" not in room

    # Wizard: tank boiler with a thermostat asks the thermostat style and hot water.
    f2 = SmartHeatingConfigFlow()
    f2.hass, f2.handler, f2.flow_id, f2.context = hass, "smart_heating", "f2", {"source": "user"}
    hass.states.async_set("climate.nest", "heat", {"temperature": 18})
    await f2.async_step_user()
    r = ser(await f2.async_step_type({"heating_type": "boiler_tank"}))
    assert r["step_id"] == "boiler"
    r = ser(await f2.async_step_boiler({"boiler_switch": "climate.nest"}))
    assert r["step_id"] == "thermostat"
    r = ser(await f2.async_step_thermostat({"thermostat_style": "setpoint"}))
    assert r["step_id"] == "hot_water"
    r = ser(await f2.async_step_hot_water({"hot_water_priority": True}))
    assert r["step_id"] == "outside"
    r = ser(await f2.async_step_outside({"weather": "weather.home"}))
    assert r["step_id"] == "extras" and "gas_meter" not in str(r["data_schema"].schema), r
    r = ser(await f2.async_step_extras({}))
    assert r["step_id"] == "energy", r
    r = ser(await f2.async_step_energy({"energy_source": "smart_meter"}))
    assert r["step_id"] == "energy_meter", r
    r = ser(await f2.async_step_energy_meter({"gas_meter": "sensor.gas_kwh", "gas_rate": "sensor.gas_rate", "gas_price": 0.07}))
    assert r["step_id"] == "rooms", r
    r = await f2.async_step_rooms({"areas": []})
    assert r["type"] == "create_entry" and r["data"]["energy_source"] == "smart_meter" and r["data"]["gas_rate"] == "sensor.gas_rate", r
    assert r["options"] == {"gas_price": 0.07}, r["options"]
    f3 = SmartHeatingConfigFlow()
    f3.hass, f3.handler, f3.flow_id, f3.context = hass, "smart_heating", "f3", {"source": "user"}
    await f3.async_step_user()
    await f3.async_step_type({"heating_type": "combi"})
    r = ser(await f3.async_step_boiler({"boiler_switch": "switch.x"}))
    assert r["step_id"] == "outside", "combi skips hot water"
    await f3.async_step_outside({})
    r = ser(await f3.async_step_extras({}))
    assert r["step_id"] == "energy", r
    r = ser(await f3.async_step_energy({"energy_source": "estimate"}))
    assert r["step_id"] == "energy_estimate", r
    r = ser(await f3.async_step_energy_estimate({"boiler_input_kw": 15, "gas_price": 0.06}))
    assert r["step_id"] == "rooms", r
    r = await f3.async_step_rooms({"areas": []})
    assert r["data"]["energy_source"] == "estimate" and "gas_meter" not in r["data"], r["data"]
    assert r["options"] == {"boiler_input_kw": 15, "gas_price": 0.06}, r["options"]
    print("wizard (tank + thermostat + smart meter, combi + estimate): steps ok")

    # Run the electric coordinator.
    entry = ConfigEntry(
        version=1, minor_version=1, domain="smart_heating", title="Smart Heating", data=r_data if (r_data := {"heating_type": "electric", "weather": "weather.home", "outdoor_temperature": "sensor.out"}) else {},
        options={}, source="user", unique_id="smart_heating", discovery_keys={},
        subentries_data=[ConfigSubentryData(subentry_id="cafe", subentry_type="room", title="Cafe",
                                            data={**room, "heater_power_w": 2000, "heater_eco_power_w": 1000}, unique_id=area.id)],
    )
    hass.states.async_set("sensor.out", "6.0")
    c = HeatingCoordinator(hass, entry)
    c.async_config_entry_first_refresh = c.async_refresh
    c.skip_calibration = True
    await c.async_start()
    print("electric:", c.profile, "| learnable:", c.learnable, "| power sensors:", c.rooms["cafe"].power_sensors)
    assert c.profile == "electric" and c.learnable and c.rooms["cafe"].power_sensors == {"switch.cafe_heater": "sensor.cafe_heater_power"}
    await c.async_set_monitor_only(False)
    c.rooms["cafe"].override = _coord.Override.HEAT
    await c.async_refresh()
    await asyncio.sleep(0.3); await hass.async_block_till_done()
    print("calls:", calls)
    assert ("switch", "turn_on", {"entity_id": "switch.cafe_heater"}) in calls
    assert any(cl[0] == "climate" and cl[2].get("entity_id") == "climate.cafe_panel" and cl[2].get("hvac_mode") == "heat" for cl in calls)
    assert c.data.rooms["cafe"].heater_on and not c.data.boiler_on

    # Energy: measured plug 1800 W + panel in eco (1000 W rated) for 30 min.
    hass.states.async_set("sensor.cafe_heater_power", "1800", {"unit_of_measurement": "W"})
    hass.states.async_set("climate.cafe_panel", "heat", {**hass.states.get("climate.cafe_panel").attributes, "hvac_action": "heating"})
    print("power now:", c.heater_power_w(c.rooms["cafe"]))
    assert c.heater_power_w(c.rooms["cafe"]) == 2800
    c._elec_tick = dt_util.utcnow() - timedelta(minutes=10)
    c._account_electric(dt_util.utcnow())
    print("kWh after 10 min:", c.elec_kwh, "| cost:", c.elec_cost)
    assert abs(c.elec_kwh - 2800 * (10 / 60) / 1000) < 0.01

    # Warm: heaters off.
    hass.states.async_set("sensor.cafe_temperature", "19.6")
    c.rooms["cafe"].override = _coord.Override.AUTO
    calls.clear()
    await c.async_refresh()
    await asyncio.sleep(0.3); await hass.async_block_till_done()
    print("warm calls:", calls)
    assert ("switch", "turn_off", {"entity_id": "switch.cafe_heater"}) in calls
    assert ("climate", "set_hvac_mode", {"entity_id": "climate.cafe_panel", "hvac_mode": "off"}) in calls

    # Heat test switches heaters on and restores them.
    calls.clear()
    await c.async_heat_test(True)
    await hass.async_block_till_done()
    assert hass.states.get("switch.cafe_heater").state == "on"
    await c.async_heat_test(False)
    await hass.async_block_till_done()
    assert hass.states.get("switch.cafe_heater").state == "off" and hass.states.get("climate.cafe_panel").state == "off"
    print("heat test with heaters ok")

    # Room form for an electric home shows heaters, not TRVs.
    sub = RoomSubentryFlow()
    sub.hass, sub.handler, sub.flow_id, sub.context = hass, ("x", "room"), "s1", {"source": "user"}
    sub._get_entry = lambda: entry
    sub._area_id = area.id
    r = ser(await sub.async_step_details())
    keys = [str(k) for k in r["data_schema"].schema]
    assert "heaters" in keys and "trvs" not in keys, keys
    print("room form keys:", keys)

    await c.async_stop(); await hass.async_stop()
    print("ELECTRIC OK")


asyncio.run(main())
