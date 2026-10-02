"""Smoke test: rooms from HA areas/floors inside a real HomeAssistant core."""
import asyncio, sys, tempfile, importlib.abc, importlib.machinery
from pathlib import Path
from unittest.mock import MagicMock


class _Stub(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path, target=None):
        if name.split(".")[0] in ("hass_nabucasa", "home_assistant_bluetooth", "habluetooth"):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
    def create_module(self, spec):
        m = MagicMock(); m.__path__ = []; m.__name__ = spec.name; m.__spec__ = spec; return m
    def exec_module(self, m): pass


sys.meta_path.insert(0, _Stub())
sys.path.insert(0, str(Path(__file__).parents[1]))

from ha_env import load_registries, pin_clock  # noqa: E402

pin_clock()

from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.config_entries import ConfigEntry, ConfigSubentryData  # noqa: E402
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, floor_registry as fr  # noqa: E402

from custom_components.smart_heating import areas as A  # noqa: E402
from custom_components.smart_heating.config_flow import _room_data_from_area  # noqa: E402
from custom_components.smart_heating.coordinator import HeatingCoordinator  # noqa: E402


async def main():
    hass = HomeAssistant(tempfile.mkdtemp())
    await hass.config.async_set_time_zone("Europe/London")
    await load_registries(hass)
    await hass.async_start()
    floors, areas, devs, ents = fr.async_get(hass), ar.async_get(hass), dr.async_get(hass), er.async_get(hass)
    f2 = floors.async_create("2nd Floor")   # no levels set, like a typical setup
    f1 = floors.async_create("1st Floor")
    g = floors.async_create("Ground Floor")
    office = areas.async_create("Office", floor_id=g.floor_id)
    living = areas.async_create("Living Room", floor_id=f1.floor_id)
    hall = areas.async_create("Hallway (1st floor)", floor_id=f1.floor_id)
    bed = areas.async_create("Master Bedroom", floor_id=f2.floor_id)
    garden = areas.async_create("Back Garden", floor_id=g.floor_id)

    entry_for_devices = MagicMock(); entry_for_devices.entry_id = "x"
    def entity(domain, uid, area=None, device=None, dc=None, name=None):
        e = ents.async_get_or_create(domain, "test", uid, device_id=device, original_device_class=dc, original_name=name)
        if area:
            ents.async_update_entity(e.entity_id, area_id=area)
        return e.entity_id

    # Office: thermometer device + TRV device (TRV also exposes a temperature sensor that must be ignored)
    th = devs.async_get_or_create(config_entry_id=None, identifiers={("t", "th_office")}, name="TH office") if False else None
    t_office = entity("sensor", "th_office_t", office.id, dc="temperature")
    h_office = entity("sensor", "th_office_h", office.id, dc="humidity")
    trv = entity("climate", "office_trv", office.id)
    entity("sensor", "office_trv_battery_temp", office.id, dc="temperature", name="TRV internal temperature")
    # Living: temperature via area setting, presence, light
    t_living = entity("sensor", "living_t", living.id, dc="temperature")
    hass.states.async_set(t_living, "19.2", {"device_class": "temperature", "unit_of_measurement": "°C"})
    areas.async_update(living.id, temperature_entity_id=t_living)
    p_living = entity("binary_sensor", "living_presence", living.id, dc="occupancy")
    l_living = entity("light", "living_ceiling", living.id)
    entity("sensor", "hall_t", hall.id, dc="temperature")
    # Bedroom: Shelly relay internal temperature (45°C, not diagnostic), Shelly diagnostic temp, an ESP board temp, and the real TH sensor
    from homeassistant.helpers.device_registry import DeviceInfo
    from homeassistant.config_entries import ConfigEntry as _CE
    fake = _CE(version=1, minor_version=1, domain="test", title="t", data={}, options={}, source="user", unique_id=None, discovery_keys={}, subentries_data=[])
    # Device registry only needs the entry to look registered.
    from unittest.mock import MagicMock as _MM
    hass.config_entries = _MM(); hass.config_entries.async_get_entry = lambda eid: fake if eid == fake.entry_id else None
    shelly = devs.async_get_or_create(config_entry_id=fake.entry_id, identifiers={("t", "shelly_bed")}, name="Shelly bedroom lights", model="Shelly Plus 2PM", manufacturer="Shelly")
    th = devs.async_get_or_create(config_entry_id=fake.entry_id, identifiers={("t", "th_bed")}, name="TH Master Bedroom", model="LYWSD03MMC", manufacturer="Xiaomi")
    devs.async_update_device(shelly.id, area_id=bed.id); devs.async_update_device(th.id, area_id=bed.id)
    relay_t = entity("sensor", "aa_shelly_bed_temp", device=shelly.id, dc="temperature")
    hass.states.async_set(relay_t, "45.4")
    from homeassistant.const import EntityCategory
    diag = ents.async_get_or_create("sensor", "test", "aa_shelly_bed_device_temp", device_id=shelly.id, original_device_class="temperature", entity_category=EntityCategory.DIAGNOSTIC)
    hass.states.async_set(diag.entity_id, "44.0")
    bed_t = entity("sensor", "th_master_bedroom_temperature", device=th.id, dc="temperature")
    entity("sensor", "th_master_bedroom_humidity", device=th.id, dc="humidity")
    hass.states.async_set(bed_t, "19.6")
    entity("light", "bed_light", bed.id)
    entity("binary_sensor", "garden_pir", garden.id, dc="motion")
    entity("sensor", "garden_t", garden.id, dc="temperature")

    print("office discover:", A.discover(hass, office.id))
    assert A.discover(hass, office.id)["temperature_sensor"] == t_office
    assert A.discover(hass, office.id)["trvs"] == [trv]
    d_living = A.discover(hass, living.id)
    assert d_living["temperature_sensor"] == t_living and d_living["presence"] == [p_living] and d_living["lights"] == [l_living]
    cands = A.candidate_areas(hass, set())
    print("candidates:", [areas.async_get_area(a).name for a in cands])
    assert garden.id not in cands and office.id in cands
    print("defaults:", {n: A.defaults_for(n) for n in ("Office", "Hallway (1st floor)", "Master Bedroom", "Kids Bathroom", "Living Room")})
    print("bedroom ranking:", A.rank_room_sensors(hass, bed.id, "temperature"))
    assert A.discover(hass, bed.id)["temperature_sensor"] == bed_t
    print("floor of bed:", A.area_floor(hass, bed.id))
    assert A.area_floor(hass, bed.id) == (2, "2nd Floor") and A.area_floor(hass, office.id) == (0, "Ground Floor")

    subs = [ConfigSubentryData(subentry_id=a.id, subentry_type="room", title=a.name, data=_room_data_from_area(hass, a.id), unique_id=a.id)
            for a in (office, living, hall, bed)]
    hass.states.async_set("person.albert", "home"); hass.states.async_set("person.partner", "not_home")
    entry = ConfigEntry(version=1, minor_version=1, domain="smart_heating", title="Smart Heating",
                        data={"alarm_panel": ["person.albert", "person.partner"]},
                        options={}, source="user", unique_id="smart_heating", discovery_keys={}, subentries_data=subs)
    for st, val in ((t_office, "18.1"), (t_living, "19.2")):
        hass.states.async_set(st, val)
    c = HeatingCoordinator(hass, entry)
    c.async_config_entry_first_refresh = c.async_refresh
    await c.async_start()
    print("rooms:", [(r.cfg.name, r.cfg.floor, r.floor_name, r.cfg.priority.value, r.cfg.comfort, r.trvs) for r in c.rooms.values()])
    print("floor names:", c.floor_names, "| house temp:", c.house_temp, c.floor_temps)
    office_room = c.rooms[office.id]
    assert office_room.cfg.floor == 0 and office_room.trvs == [trv] and office_room.cfg.priority.value == "b"
    assert c.rooms[hall.id].cfg.priority.value == "c" and c.rooms[bed.id].cfg.comfort == 18.5
    assert not c.away
    hass.states.async_set("person.albert", "not_home")
    await c.async_refresh()
    print("everyone out ->", c.data.status, "|", c.data.reason)
    assert c.away and c.data.status == "away"
    # Retention index with a learned model.
    from custom_components.smart_heating.core.learn import RoomModel
    import math
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    m = RoomModel.new(); tin = 20.0; t = dt_util.utcnow()
    for i in range(72 * 12):
        h = i / 12; tout = 2 + 8 * (h % 24) / 24
        from custom_components.smart_heating.core.learn import Phase
        m.observe(t + timedelta(minutes=5 * i), round(tin, 2), tout, Phase.FREE)
        tin += -(tin - tout - 5.5) / 84 / 12
    c.rooms[office.id].model = m
    from custom_components.smart_heating.sensor import RetentionSensor, RoomRetention
    rr = RoomRetention(c, office.id); hs = RetentionSensor(c, "house_heat_retention", lambda c: c.house_tau, scope="house")
    print("office retention:", rr.native_value, rr.extra_state_attributes)
    print("house retention:", hs.native_value, hs.extra_state_attributes["grade"], hs.extra_state_attributes["weakest_rooms"])
    assert rr.extra_state_attributes["grade"] == "B"
    await c.async_stop(); await hass.async_stop()
    print("AREAS OK")


asyncio.run(main())
