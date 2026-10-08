"""Home Assistant areas and floors as the source of rooms."""
from __future__ import annotations

import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr

PRESENCE_CLASSES = {"occupancy", "presence", "motion"}
_NOT_ROOM_TEMP = re.compile(r"battery|cpu|chip|processor|internal|esp|wifi|board|device|core|soc|probe|cylinder|coil|boiler", re.I)

_OUTSIDE = re.compile(r"garden|outside|outdoor|patio|yard|drive|balcony|terrace|shed|street", re.I)
_ORDINAL = re.compile(r"(-?\d+)")


def _level_from_name(name: str) -> int | None:
    n = name.lower()
    if "basement" in n or "cellar" in n:
        return -1
    if "ground" in n:
        return 0
    if "first" in n:
        return 1
    if "second" in n:
        return 2
    if "third" in n or "attic" in n or "loft" in n:
        return 3
    m = _ORDINAL.search(n)
    return int(m.group(1)) if m else None


_PRIORITY_C = re.compile(r"hall|landing|corridor|utility|cupboard|entrance|stair|porch|garage|loft|store", re.I)
_PRIORITY_B = re.compile(r"office|study|play|guest|spare|gym|dining", re.I)


def area_floor(hass: HomeAssistant, area_id: str | None) -> tuple[int | None, str | None]:
    """(level, floor name) for an area, or (None, None)."""
    if not area_id:
        return None, None
    area = ar.async_get(hass).async_get_area(area_id)
    if area is None or not area.floor_id:
        return None, None
    floors = fr.async_get(hass)
    floor = floors.async_get_floor(area.floor_id)
    if floor is None:
        return None, None
    if floor.level is not None:
        return floor.level, floor.name
    # No level set: infer from the name ("Ground Floor", "1st Floor"), else registry position.
    guess = _level_from_name(floor.name)
    if guess is not None:
        return guess, floor.name
    ordered = list(floors.async_list_floors())
    return ordered.index(floor), floor.name


def area_name(hass: HomeAssistant, area_id: str | None) -> str | None:
    if not area_id:
        return None
    area = ar.async_get(hass).async_get_area(area_id)
    return area.name if area else None


def floor_names(hass: HomeAssistant) -> dict[int, str]:
    floors = fr.async_get(hass)
    out: dict[int, str] = {}
    for i, f in enumerate(floors.async_list_floors()):
        level = f.level if f.level is not None else _level_from_name(f.name)
        out[level if level is not None else i] = f.name
    return out


def _area_entities(hass: HomeAssistant, area_id: str) -> list[er.RegistryEntry]:
    ents = er.async_get(hass)
    devs = dr.async_get(hass)
    found = {e.entity_id: e for e in er.async_entries_for_area(ents, area_id)}
    for dev in dr.async_entries_for_area(devs, area_id):
        for e in er.async_entries_for_device(ents, dev.id):
            if e.area_id in (None, area_id):  # entity not moved to another area
                found.setdefault(e.entity_id, e)
    return [e for e in found.values() if not e.disabled_by and not e.hidden_by]


def _dclass(e: er.RegistryEntry) -> str | None:
    return e.device_class or e.original_device_class


_JUNK_DEVICE = re.compile(
    r"relay|switch|plug|outlet|dimmer|bulb|lamp|1pm|2pm|\bmini\b|\btv\b|router|nas|printer|server|computer|camera|"
    r"doorbell|inverter|\bhub\b|bridge|gateway|\bups\b|esp32|esp8266|panel|display|speaker|boiler|cylinder",
    re.I,
)
_ROOM_HINT = re.compile(r"(^|[._ ])th[._ ]|thermo|ambient|room|climate|atc|lywsd|sht|snzb|temperature and humidity", re.I)
PLAUSIBLE = (5.0, 35.0)


def _value(hass: HomeAssistant, entity_id: str) -> float | None:
    st = hass.states.get(entity_id)
    try:
        return float(st.state) if st else None
    except (TypeError, ValueError):
        return None


def rank_room_sensors(hass: HomeAssistant, area_id: str, device_class: str) -> list[tuple[int, str, str]]:
    """Candidate room sensors, best first, as (score, entity_id, why).

    Rejects diagnostic/config entities (device internal temperatures), TRV-internal
    sensors, relays/plugs/appliances, and readings outside a plausible room range.
    Prefers combined temperature+humidity devices and room-thermometer names.
    """
    devs = dr.async_get(hass)
    entities = _area_entities(hass, area_id)
    trv_devices = {e.device_id for e in entities if e.domain == "climate" and e.device_id}
    humid_devices = {e.device_id for e in entities if e.domain == "sensor" and _dclass(e) == "humidity" and e.device_id}
    temp_devices = {e.device_id for e in entities if e.domain == "sensor" and _dclass(e) == "temperature" and e.device_id}
    out = []
    for e in entities:
        if e.domain != "sensor" or _dclass(e) != device_class or e.entity_category is not None:
            continue
        if e.device_id in trv_devices:
            continue
        dev = devs.async_get(e.device_id) if e.device_id else None
        text = " ".join(filter(None, [e.entity_id, e.original_name, dev and dev.name, dev and dev.model, dev and dev.manufacturer]))
        if _NOT_ROOM_TEMP.search(e.entity_id + " " + (e.original_name or "")) or _JUNK_DEVICE.search(text):
            continue
        score, why = 0, []
        if device_class == "temperature":
            v = _value(hass, e.entity_id)
            if v is not None and not PLAUSIBLE[0] <= v <= PLAUSIBLE[1]:
                continue
            if v is not None:
                score += 1
            if e.device_id in humid_devices:
                score += 3; why.append("temperature + humidity device")
        elif e.device_id in temp_devices:
            score += 3; why.append("temperature + humidity device")
        if _ROOM_HINT.search(text):
            score += 2; why.append("thermometer name")
        out.append((score, e.entity_id, ", ".join(why) or "only candidate"))
    return sorted(out, key=lambda x: (-x[0], x[1]))


_TRV_HINT = re.compile(r"trv|thermostatic|radiator valve|valve|ke100|eurotronic|spirit|tado.*(radiator|smart radiator)|sonoff trvzb|moes", re.I)
_HEATER_HINT = re.compile(r"heater|heating panel|panel heater|convector|radiator(?! valve)|oil|infrared|storage|fan heater|towel", re.I)


def _device_text(hass: HomeAssistant, e: er.RegistryEntry) -> str:
    dev = dr.async_get(hass).async_get(e.device_id) if e.device_id else None
    return " ".join(filter(None, [e.entity_id, e.original_name, e.name, dev and dev.name, dev and dev.model, dev and dev.manufacturer]))


def power_sensors(hass: HomeAssistant, heaters: list[str]) -> dict[str, str]:
    """Each heater's power sensor (W), found on the same device: smart plugs and many heaters report it."""
    ents = er.async_get(hass)
    out: dict[str, str] = {}
    for h in heaters:
        entry = ents.async_get(h)
        if not entry or not entry.device_id:
            continue
        for e in er.async_entries_for_device(ents, entry.device_id):
            if e.domain == "sensor" and _dclass(e) == "power" and not e.disabled_by:
                out[h] = e.entity_id
                break
    return out


def discover(hass: HomeAssistant, area_id: str, heating_type: str | None = None) -> dict[str, Any]:
    """Suggested entities for a room, from what is assigned to the area.

    Electric homes: climate entities are heaters. Hybrid: climate entities that look like
    radiator valves are TRVs, the rest heaters. Switches/plugs named like heaters are heaters.
    """
    area = ar.async_get(hass).async_get_area(area_id)
    entities = _area_entities(hass, area_id)
    climate = [e for e in entities if e.domain == "climate"]
    plugs = [e for e in entities if e.domain == "switch" and _HEATER_HINT.search(_device_text(hass, e))]
    if heating_type == "electric":
        trvs, heaters = [], climate + plugs
    elif heating_type == "hybrid":
        trvs = [e for e in climate if _TRV_HINT.search(_device_text(hass, e))]
        heaters = [e for e in climate if e not in trvs] + plugs
    else:
        trvs, heaters = climate, []

    def pick(device_class: str, preferred: str | None) -> str | None:
        if preferred:  # the area's own Temperature/Humidity setting always wins
            return preferred
        ranked = rank_room_sensors(hass, area_id, device_class)
        return ranked[0][1] if ranked else None

    return {
        "temperature_sensor": pick("temperature", area.temperature_entity_id if area else None),
        "humidity_sensor": pick("humidity", area.humidity_entity_id if area else None),
        "trvs": sorted(e.entity_id for e in trvs),
        "heaters": sorted(e.entity_id for e in heaters),
        "presence": sorted(e.entity_id for e in entities if e.domain == "binary_sensor" and _dclass(e) in PRESENCE_CLASSES),
        # Windows almost always face outside; doors are often internal, so those are added by hand.
        "openings": sorted(e.entity_id for e in entities if e.domain == "binary_sensor" and _dclass(e) == "window"),
        "lights": sorted(e.entity_id for e in entities if e.domain == "light"),
        "media": sorted(e.entity_id for e in entities if e.domain == "media_player"),
    }


def defaults_for(name: str) -> tuple[str, float]:
    """(priority, comfort) guessed from the room name."""
    n = name.lower()
    if _PRIORITY_C.search(n):
        return "c", 17.0
    if _PRIORITY_B.search(n):
        return "b", 18.0
    if "bath" in n or "ensuite" in n or "en suite" in n or "shower" in n:
        return "a", 19.0
    if "bed" in n or "nursery" in n:
        return "a", 18.5
    return "a", 19.0


def candidate_areas(hass: HomeAssistant, exclude: set[str], heating_type: str | None = None) -> list[str]:
    """Areas with a temperature sensor, TRV or heater that aren't rooms yet."""
    out = []
    for area in ar.async_get(hass).async_list_areas():
        if area.id in exclude or _OUTSIDE.search(area.name):
            continue
        d = discover(hass, area.id, heating_type)
        if d["temperature_sensor"] or d["trvs"] or d["heaters"]:
            out.append(area.id)
    return out
