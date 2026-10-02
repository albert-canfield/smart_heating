"""Config flow: house setup, tuning options, and rooms as subentries."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector as sel
from types import MappingProxyType

from homeassistant.config_entries import ConfigSubentry, ConfigSubentryData

from . import areas as area_tools

from .const import (
    CONF_BOILER,
    CONF_BOILER_ON,
    CONF_COMFORT,
    CONF_FLOOR,
    CONF_HUMIDITY,
    CONF_HW_CALLING,
    CONF_LIGHTS,
    CONF_MEDIA,
    CONF_NAME,
    CONF_NIGHT_SCHEDULE,
    CONF_OUTDOOR_MEAN,
    CONF_OUTDOOR_TEMP,
    CONF_WEATHER,
    CONF_GAS_METER,
    CONF_AREA,
    CONF_ALARM,
    CONF_HW_PRIORITY,
    CONF_HW_SYSTEM,
    CONF_THERMOSTAT_STYLE,
    CONF_HEATING_TYPE,
    CONF_HEATERS,
    CONF_HEATER_W,
    CONF_HEATER_ECO_W,
    CONF_RADIATOR,
    HEATING_TYPES,
    HW_COMBI,
    HW_SYSTEMS,
    HW_TANK,
    HW_S_PLAN,
    HW_Y_PLAN,
    TYPE_COMBI,
    TYPE_ELECTRIC,
    TYPE_HYBRID,
    TYPE_TANK,
    OPT_ELEC_PRICE,
    DEFAULT_ELEC_PRICE,
    STYLE_RELAY,
    STYLE_SETPOINT,
    DEFAULT_BOILER_KW,
    DEFAULT_GAS_PRICE,
    DEFAULT_STANDING,
    OPT_BOILER_KW,
    OPT_GAS_PRICE,
    OPT_NOTIFY,
    OPT_SKIP_CAL,
    OPT_NIGHT_START,
    OPT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_NIGHT_END,
    OPT_STANDING,
    CONF_PRESENCE,
    CONF_PRIORITY,
    CONF_SCHEDULE,
    CONF_TEMP,
    CONF_TRVS,
    DEFAULT_OVERRIDE_HOURS,
    DOMAIN,
    OPT_OVERRIDE_HOURS,
    SUBENTRY_ROOM,
)
from .core import Settings


def _ent(domain: str | list[str], multiple: bool = False, device_class: str | None = None):
    cfg: dict[str, Any] = {"domain": domain, "multiple": multiple}
    if device_class:
        cfg["device_class"] = device_class
    return sel.EntitySelector(sel.EntitySelectorConfig(**cfg))


def _num(lo: float, hi: float, step: float, unit: str | None = None):
    return sel.NumberSelector(
        sel.NumberSelectorConfig(min=lo, max=hi, step=step, unit_of_measurement=unit, mode=sel.NumberSelectorMode.BOX)
    )


def _opt(key: str, data: dict[str, Any]) -> vol.Optional:
    return vol.Optional(key, description={"suggested_value": data.get(key)})





def _select(key: str, options: list[str], default: str, list_mode: bool = False):
    return {
        vol.Required(key, default=default): sel.SelectSelector(
            sel.SelectSelectorConfig(
                options=options, translation_key=key,
                mode=sel.SelectSelectorMode.LIST if list_mode else sel.SelectSelectorMode.DROPDOWN,
            )
        )
    }


def _house_suggestions(hass) -> dict[str, Any]:
    """Pre-fill obvious picks: the only weather entity, alarm panel, an outdoor sensor, a heating switch."""
    def only(domain: str, hint: str | None = None) -> str | None:
        ids = [s.entity_id for s in hass.states.async_all(domain)]
        if hint:
            hinted = [i for i in ids if hint in i]
            if hinted:
                return hinted[0]
        return ids[0] if len(ids) == 1 else None

    out = {
        CONF_WEATHER: only("weather", "home"),
        CONF_ALARM: [a] if (a := only("alarm_control_panel")) else (["zone.home"] if hass.states.get("zone.home") else None),
        CONF_BOILER: only("switch", "heating"),
    }
    outdoor = [s.entity_id for s in hass.states.async_all("sensor")
               if "outdoor" in s.entity_id and s.attributes.get("device_class") == "temperature"
               and not any(x in s.entity_id for x in ("mean", "avg", "average", "min", "max"))]
    out[CONF_OUTDOOR_TEMP] = outdoor[0] if outdoor else None
    return {k: v for k, v in out.items() if v}


def _legacy_type(data: dict[str, Any]) -> str:
    if data.get(CONF_HEATING_TYPE):
        return data[CONF_HEATING_TYPE]
    return TYPE_COMBI if data.get(CONF_HW_SYSTEM) == HW_COMBI else TYPE_TANK


class _HouseSteps:
    """Step-by-step house questions, shared by setup and reconfigure.

    type -> boiler (gas types) -> thermostat (only if the boiler control is a thermostat)
    -> hot_water (tank or hybrid) -> outside -> extras -> rooms (setup only)
    """

    _data: dict[str, Any]
    _reconfigure: bool = False

    @property
    def _type(self) -> str:
        return self._data.get(CONF_HEATING_TYPE, TYPE_TANK)

    def _keep(self, user_input: dict[str, Any], keys: list[str]) -> None:
        for k in keys:
            if k in user_input and user_input[k] not in (None, "", []):
                self._data[k] = user_input[k]
            else:
                self._data.pop(k, None)

    async def async_step_type(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data[CONF_HEATING_TYPE] = user_input[CONF_HEATING_TYPE]
            if self._type == TYPE_ELECTRIC:
                for k in (CONF_BOILER, CONF_BOILER_ON, CONF_THERMOSTAT_STYLE, CONF_HW_CALLING, CONF_HW_PRIORITY, CONF_HW_SYSTEM, CONF_GAS_METER):
                    self._data.pop(k, None)
                return await self.async_step_outside()
            return await self.async_step_boiler()
        return self.async_show_form(
            step_id="type",
            data_schema=vol.Schema(_select(CONF_HEATING_TYPE, HEATING_TYPES, self._data.get(CONF_HEATING_TYPE, TYPE_TANK), list_mode=True)),
        )

    async def async_step_boiler(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._keep(user_input, [CONF_BOILER, CONF_BOILER_ON])
            if str(self._data.get(CONF_BOILER, "")).startswith("climate."):
                return await self.async_step_thermostat()
            self._data.pop(CONF_THERMOSTAT_STYLE, None)
            return await self._after_boiler()
        d = self._data
        return self.async_show_form(
            step_id="boiler",
            data_schema=vol.Schema({
                _opt(CONF_BOILER, d): _ent(["switch", "input_boolean", "climate"]),
                _opt(CONF_BOILER_ON, d): _ent("binary_sensor"),
            }),
        )

    async def async_step_thermostat(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data[CONF_THERMOSTAT_STYLE] = user_input[CONF_THERMOSTAT_STYLE]
            return await self._after_boiler()
        return self.async_show_form(
            step_id="thermostat",
            data_schema=vol.Schema(_select(CONF_THERMOSTAT_STYLE, [STYLE_SETPOINT, STYLE_RELAY],
                                           self._data.get(CONF_THERMOSTAT_STYLE, STYLE_SETPOINT), list_mode=True)),
        )

    async def _after_boiler(self):
        if self._type in (TYPE_TANK, TYPE_HYBRID):
            return await self.async_step_hot_water()
        self._data.pop(CONF_HW_PRIORITY, None)
        self._data.pop(CONF_HW_SYSTEM, None)
        return await self.async_step_outside()

    async def async_step_hot_water(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._keep(user_input, [CONF_HW_CALLING])
            self._data[CONF_HW_PRIORITY] = bool(user_input.get(CONF_HW_PRIORITY, True))
            if self._type == TYPE_HYBRID:
                self._data[CONF_HW_SYSTEM] = user_input.get(CONF_HW_SYSTEM, HW_TANK)
            return await self.async_step_outside()
        d = self._data
        fields: dict = {}
        if self._type == TYPE_HYBRID:
            hw = d.get(CONF_HW_SYSTEM, HW_TANK)
            fields.update(_select(CONF_HW_SYSTEM, HW_SYSTEMS, HW_TANK if hw in (HW_S_PLAN, HW_Y_PLAN) else hw, list_mode=True))
        fields[_opt(CONF_HW_CALLING, d)] = _ent(["binary_sensor", "switch", "input_boolean"])
        fields[vol.Optional(CONF_HW_PRIORITY, default=d.get(CONF_HW_PRIORITY, True))] = sel.BooleanSelector()
        return self.async_show_form(step_id="hot_water", data_schema=vol.Schema(fields))

    async def async_step_outside(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._keep(user_input, [CONF_WEATHER, CONF_OUTDOOR_TEMP])
            return await self.async_step_extras()
        d = self._data
        return self.async_show_form(
            step_id="outside",
            data_schema=vol.Schema({
                _opt(CONF_WEATHER, d): _ent("weather"),
                _opt(CONF_OUTDOOR_TEMP, d): _ent("sensor", device_class="temperature"),
            }),
        )

    async def async_step_extras(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._keep(user_input, [CONF_ALARM, CONF_NIGHT_SCHEDULE, CONF_GAS_METER])
            return await self._finish_house()
        d = self._data
        fields = {
            _opt(CONF_ALARM, d): _ent(
                ["alarm_control_panel", "person", "zone", "group", "input_boolean", "binary_sensor", "switch", "device_tracker"],
                multiple=True,
            ),
            _opt(CONF_NIGHT_SCHEDULE, d): _ent(["schedule", "input_boolean", "binary_sensor"]),
        }
        if self._type != TYPE_ELECTRIC:
            fields[_opt(CONF_GAS_METER, d)] = _ent("sensor")
        return self.async_show_form(step_id="extras", data_schema=vol.Schema(fields))


class SmartHeatingConfigFlow(_HouseSteps, ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        self._data = _house_suggestions(self.hass)
        return await self.async_step_type()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        self._reconfigure = True
        self._data = dict(entry.data)
        self._data[CONF_HEATING_TYPE] = _legacy_type(self._data)
        if isinstance(self._data.get(CONF_ALARM), str):
            self._data[CONF_ALARM] = [self._data[CONF_ALARM]]
        return await self.async_step_type()

    async def _finish_house(self) -> ConfigFlowResult:
        if self._reconfigure:
            return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data=self._data)
        return await self.async_step_rooms()

    async def async_step_rooms(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            subs = []
            for area_id in user_input.get("areas", []):
                name = area_tools.area_name(self.hass, area_id) or area_id
                data = _room_data_from_area(self.hass, area_id, self._type)
                if not (data.get(CONF_TEMP) or data.get(CONF_TRVS) or data.get(CONF_HEATERS)):
                    continue
                subs.append(ConfigSubentryData(data=data, subentry_type=SUBENTRY_ROOM, title=name, unique_id=area_id))
            return self.async_create_entry(title="Smart Heating", data=self._data, subentries=subs)
        candidates = area_tools.candidate_areas(self.hass, set(), self._type)
        return self.async_show_form(
            step_id="rooms",
            data_schema=vol.Schema({
                vol.Optional("areas", default=candidates): sel.AreaSelector(sel.AreaSelectorConfig(multiple=True)),
            }),
            description_placeholders={"count": str(len(candidates))},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return SmartHeatingOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_ROOM: RoomSubentryFlow}


class SmartHeatingOptionsFlow(OptionsFlow):
    """Configure: short, separate pages instead of one long form."""

    @property
    def _type(self) -> str:
        return _legacy_type(dict(self.config_entry.data))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["temperatures", "prices", "import_areas", "advanced"])

    def _save(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **user_input})

    def _v(self, key: str, default: Any) -> Any:
        return self.config_entry.options.get(key, default)

    async def async_step_temperatures(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        d = Settings()
        schema = vol.Schema({
            vol.Required("baseline_day", default=self._v("baseline_day", d.baseline_day)): _num(10, 22, 0.5, "°C"),
            vol.Required("baseline_night", default=self._v("baseline_night", d.baseline_night)): _num(8, 20, 0.5, "°C"),
            vol.Required(OPT_NIGHT_START, default=self._v(OPT_NIGHT_START, DEFAULT_NIGHT_START)): sel.TimeSelector(),
            vol.Required(OPT_NIGHT_END, default=self._v(OPT_NIGHT_END, DEFAULT_NIGHT_END)): sel.TimeSelector(),
            vol.Required("safety", default=self._v("safety", d.safety)): _num(5, 15, 0.5, "°C"),
            vol.Required("season_gate", default=self._v("season_gate", d.season_gate)): _num(5, 20, 0.5, "°C"),
            vol.Required(OPT_OVERRIDE_HOURS, default=self._v(OPT_OVERRIDE_HOURS, DEFAULT_OVERRIDE_HOURS)): _num(0.5, 12, 0.5, "h"),
        })
        return self.async_show_form(step_id="temperatures", data_schema=schema)

    async def async_step_prices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        fields: dict = {}
        if self._type != TYPE_ELECTRIC:
            fields[vol.Required(OPT_GAS_PRICE, default=self._v(OPT_GAS_PRICE, DEFAULT_GAS_PRICE))] = _num(0, 1, 0.001, "£/kWh")
            fields[vol.Required(OPT_STANDING, default=self._v(OPT_STANDING, DEFAULT_STANDING))] = _num(0, 2, 0.01, "£/day")
            fields[vol.Required(OPT_BOILER_KW, default=self._v(OPT_BOILER_KW, DEFAULT_BOILER_KW))] = _num(1, 60, 0.5, "kW")
        if self._type in (TYPE_ELECTRIC, TYPE_HYBRID) or getattr(getattr(self.config_entry, "runtime_data", None), "has_heaters", False):
            fields[vol.Required(OPT_ELEC_PRICE, default=self._v(OPT_ELEC_PRICE, DEFAULT_ELEC_PRICE))] = _num(0, 2, 0.001, "£/kWh")
        return self.async_show_form(step_id="prices", data_schema=vol.Schema(fields))

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        d = Settings()
        v = self._v
        fields: dict = {
            vol.Required("hysteresis", default=v("hysteresis", d.hysteresis)): _num(0.2, 2, 0.1, "°C"),
            vol.Required("coast_rate", default=v("coast_rate", d.coast_rate)): _num(0.1, 3, 0.1, "°C/h"),
            vol.Required("coast_horizon_min", default=v("coast_horizon_min", d.coast_horizon_min)): _num(0, 240, 5, "min"),
            vol.Required("stack_max_wait_min", default=v("stack_max_wait_min", d.stack_max_wait_min)): _num(0, 120, 5, "min"),
        }
        if self._type != TYPE_ELECTRIC:
            fields[vol.Required("min_run_min", default=v("min_run_min", d.min_run_min))] = _num(0, 60, 1, "min")
            fields[vol.Required("min_off_min", default=v("min_off_min", d.min_off_min))] = _num(0, 60, 1, "min")
            fields[vol.Required("trv_open_offset", default=v("trv_open_offset", d.trv_open_offset))] = _num(1, 6, 1, "°C")
            fields[vol.Required("trv_closed", default=v("trv_closed", d.trv_closed))] = _num(5, 16, 1, "°C")
        if self._type in (TYPE_TANK, TYPE_HYBRID):
            fields[vol.Required("hw_max_pause_min", default=v("hw_max_pause_min", d.hw_max_pause_min))] = _num(0, 120, 5, "min")
        fields[vol.Optional(OPT_NOTIFY, description={"suggested_value": v(OPT_NOTIFY, None)})] = sel.TextSelector()
        fields[vol.Required(OPT_SKIP_CAL, default=v(OPT_SKIP_CAL, False))] = sel.BooleanSelector()
        return self.async_show_form(step_id="advanced", data_schema=vol.Schema(fields))

    async def async_step_import_areas(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        existing = {s.data.get(CONF_AREA) for s in entry.subentries.values() if s.data.get(CONF_AREA)}
        if user_input is not None:
            added = 0
            by_area = {s.data.get(CONF_AREA): s for s in entry.subentries.values() if s.data.get(CONF_AREA)}
            for area_id in user_input.get("areas", []):
                if area_id in existing:
                    if user_input.get("refresh_sensors"):
                        sub = by_area[area_id]
                        found = area_tools.discover(self.hass, area_id, self._type)
                        data = dict(sub.data)
                        for key in (CONF_TEMP, CONF_HUMIDITY):
                            if found.get(key):
                                data[key] = found[key]
                            else:
                                data.pop(key, None)
                        self.hass.config_entries.async_update_subentry(entry, sub, data=data)
                        added += 1
                    continue
                name = area_tools.area_name(self.hass, area_id) or area_id
                data = _room_data_from_area(self.hass, area_id, self._type)
                if not (data.get(CONF_TEMP) or data.get(CONF_TRVS) or data.get(CONF_HEATERS)):
                    continue
                self.hass.config_entries.async_add_subentry(
                    entry,
                    ConfigSubentry(data=MappingProxyType(data), subentry_type=SUBENTRY_ROOM, title=name, unique_id=area_id),
                )
                added += 1
            if added:
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_create_entry(data=dict(entry.options))
        candidates = area_tools.candidate_areas(self.hass, existing, self._type)
        schema = vol.Schema(
            {
                vol.Optional("areas", default=candidates or sorted(existing)): sel.AreaSelector(sel.AreaSelectorConfig(multiple=True)),
                vol.Optional("refresh_sensors", default=False): sel.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="import_areas", data_schema=schema,
            description_placeholders={"count": str(len(candidates))},
        )


def _room_data_from_area(hass, area_id: str, heating_type: str | None = None) -> dict[str, Any]:
    name = area_tools.area_name(hass, area_id) or ""
    priority, comfort = area_tools.defaults_for(name)
    found = area_tools.discover(hass, area_id, heating_type)
    data: dict[str, Any] = {CONF_AREA: area_id, CONF_PRIORITY: priority, CONF_COMFORT: comfort}
    data.update({k: v for k, v in found.items() if v})
    return data


def _detected_text(hass, area_id: str | None) -> str:
    if not area_id:
        return "none"
    area = area_tools.ar.async_get(hass).async_get_area(area_id)
    if area and area.temperature_entity_id:
        return f"{area.temperature_entity_id} (set in the area's settings)"
    ranked = area_tools.rank_room_sensors(hass, area_id, "temperature")
    if not ranked:
        return "none found"
    return "; ".join(f"{eid} ({why})" for _, eid, why in ranked[:3])


def _room_schema(data: dict[str, Any], need_floor: bool = False, heating_type: str = TYPE_TANK) -> vol.Schema:
    fields: dict = {}
    if need_floor:
        fields[vol.Required(CONF_FLOOR, default=str(data.get(CONF_FLOOR, "0")))] = sel.SelectSelector(
            sel.SelectSelectorConfig(options=["0", "1", "2", "3"], translation_key="floor")
        )
    heat: dict = {}
    if heating_type != TYPE_ELECTRIC:
        heat[_opt(CONF_TRVS, data)] = _ent("climate", multiple=True)
    if heating_type == TYPE_HYBRID:
        heat[vol.Optional(CONF_RADIATOR, default=data.get(CONF_RADIATOR, True))] = sel.BooleanSelector()
    if heating_type in (TYPE_ELECTRIC, TYPE_HYBRID) or data.get(CONF_HEATERS):
        heat[_opt(CONF_HEATERS, data)] = _ent(["switch", "climate", "input_boolean"], multiple=True)
        heat[_opt(CONF_HEATER_W, data)] = _num(100, 5000, 50, "W")
        heat[_opt(CONF_HEATER_ECO_W, data)] = _num(50, 5000, 50, "W")
    return vol.Schema(
        {
            **fields,
            vol.Required(CONF_PRIORITY, default=data.get(CONF_PRIORITY, "a")): sel.SelectSelector(
                sel.SelectSelectorConfig(options=["a", "b", "c"], translation_key="priority")
            ),
            vol.Required(CONF_COMFORT, default=data.get(CONF_COMFORT, 19.0)): _num(12, 25, 0.5, "°C"),
            _opt(CONF_TEMP, data): _ent("sensor", device_class="temperature"),
            **heat,
            _opt(CONF_HUMIDITY, data): _ent("sensor", device_class="humidity"),
            _opt(CONF_PRESENCE, data): _ent("binary_sensor", multiple=True),
            _opt(CONF_LIGHTS, data): _ent(["light", "switch"], multiple=True),
            _opt(CONF_MEDIA, data): _ent("media_player", multiple=True),
            _opt(CONF_SCHEDULE, data): _ent(["schedule", "input_boolean"]),
        }
    )


def _room_errors(user_input: dict[str, Any]) -> dict[str, str]:
    climate_heater = any(str(h).startswith("climate.") for h in user_input.get(CONF_HEATERS, []))
    if not user_input.get(CONF_TEMP) and not user_input.get(CONF_TRVS) and not climate_heater:
        return {"base": "no_temperature"}
    return {}


class RoomSubentryFlow(ConfigSubentryFlow):
    """A room is a Home Assistant area: pick the area, confirm the suggested entities."""

    _area_id: str | None = None

    @property
    def _type(self) -> str:
        return _legacy_type(dict(self._get_entry().data))

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            area_id = user_input[CONF_AREA]
            used = {s.data.get(CONF_AREA) for s in self._get_entry().subentries.values()}
            if area_id in used:
                errors["base"] = "already_added"
            else:
                self._area_id = area_id
                return await self.async_step_details()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_AREA): sel.AreaSelector()}),
            errors=errors,
        )

    async def async_step_details(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        area_id = self._area_id
        name = area_tools.area_name(self.hass, area_id) or "Room"
        level, floor_name = area_tools.area_floor(self.hass, area_id)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _room_errors(user_input)
            if not errors:
                data = {CONF_AREA: area_id, **user_input}
                if CONF_FLOOR in data:
                    data[CONF_FLOOR] = int(data[CONF_FLOOR])
                return self.async_create_entry(title=name, data=data, unique_id=area_id)
        suggested = user_input or _room_data_from_area(self.hass, area_id, self._type)
        return self.async_show_form(
            step_id="details",
            data_schema=_room_schema(suggested, need_floor=level is None, heating_type=self._type),
            errors=errors,
            description_placeholders={"area": name, "floor": floor_name or "no floor set", "detected": _detected_text(self.hass, area_id)},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        sub = self._get_reconfigure_subentry()
        area_id = sub.data.get(CONF_AREA)
        level, floor_name = area_tools.area_floor(self.hass, area_id)
        name = area_tools.area_name(self.hass, area_id) or sub.title
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _room_errors(user_input)
            if not errors:
                data = {**({CONF_AREA: area_id} if area_id else {CONF_NAME: sub.data.get(CONF_NAME, sub.title)}), **user_input}
                if CONF_FLOOR in data:
                    data[CONF_FLOOR] = int(data[CONF_FLOOR])
                return self.async_update_and_abort(self._get_entry(), sub, title=name, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_room_schema(user_input or dict(sub.data), need_floor=level is None, heating_type=self._type),
            errors=errors,
            description_placeholders={"area": name, "floor": floor_name or "no floor set", "detected": _detected_text(self.hass, area_id)},
        )
