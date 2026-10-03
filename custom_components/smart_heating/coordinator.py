"""Coordinator: gathers state, runs the decision core, applies the plan."""
from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.components import persistent_notification
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

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
    CONF_GAS_RATE,
    CONF_ENERGY_SOURCE,
    SOURCE_METER,
    SOURCE_ESTIMATE,
    CONF_START_MODE,
    START_WATCH,
    STARTUP_GRACE_MIN,
    BOILER_SILENT_MIN,
    ONE_CYCLE_WAIT_MIN,
    SEASON_GATE_BAND,
    CONF_AREA,
    CONF_ALARM,
    CONF_HW_PRIORITY,
    CONF_HW_SYSTEM,
    CONF_THERMOSTAT_STYLE,
    HW_COMBI,
    HW_NONE,
    HW_TANK,
    HW_S_PLAN,
    HW_Y_PLAN,
    CONF_HEATING_TYPE,
    TYPE_TANK,
    TYPE_COMBI,
    TYPE_ELECTRIC,
    CONF_HEATERS,
    CONF_HEATER_W,
    CONF_HEATER_ECO_W,
    CONF_RADIATOR,
    DEFAULT_HEATER_W,
    OPT_ELEC_PRICE,
    DEFAULT_ELEC_PRICE,
    STYLE_SETPOINT,
    EVENT_DECISION,
    LOG_SIZE,
    CALIBRATED_SHARE,
    DEFAULT_BOILER_KW,
    DEFAULT_GAS_PRICE,
    FORECAST_REFRESH_MIN,
    FORECAST_RETRY_MIN,
    OPT_BOILER_KW,
    OPT_GAS_PRICE,
    OPT_NOTIFY,
    OPT_NIGHT_START,
    OPT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_NIGHT_END,
    SAVE_DELAY_S,
    STORE_VERSION,
    CONF_PRESENCE,
    CONF_PRIORITY,
    CONF_SCHEDULE,
    CONF_TEMP,
    CONF_TRVS,
    DEFAULT_OVERRIDE_HOURS,
    DOMAIN,
    OPT_KEYS,
    OPT_OVERRIDE_HOURS,
    SUBENTRY_ROOM,
    TRV_STAGGER_S,
    UPDATE_INTERVAL_S,
    HEAT_TEST_CAP,
    HEAT_TEST_MIN,
    HEAT_TEST_RISE,
    BOILER_GUARD_S,
    BOILER_FLAP_WINDOW_MIN,
    BOILER_FLAP_MAX,
    BOILER_LOCK_MIN,
    EXTERNAL_HOLD_MIN,
)
from . import areas as area_tools
from .core import (
    EnergyDay,
    season_is_off,
    HouseSnapshot,
    RoomModel,
    Phase,
    Setpoints,
    calibration_summary,
    insulation,
    is_away,
    overall_progress,
    Mode,
    OutdoorModel,
    Override,
    Plan,
    Priority,
    RoomConfig,
    RoomSnapshot,
    Settings,
    Signal,
    Trend,
    house_means,
    is_occupied,
    make_plan,
)
from .core.learn import HEAT_NEEDED

_LOGGER = logging.getLogger(__name__)
_NUMBERS = re.compile(r"[-+]?\d+(?:\.\d+)?")
_BAD = (None, STATE_UNAVAILABLE, STATE_UNKNOWN, "")
_ON_STATES = (STATE_ON, "playing", "home", "heat")


@dataclass
class Room:
    room_id: str
    cfg: RoomConfig
    temp_entity: str | None
    humidity_entity: str | None
    trvs: list[str]
    presence: list[str]
    media: list[str]
    lights: list[str]
    schedule: str | None
    area_id: str | None = None
    floor_name: str | None = None
    trend: Trend = field(default_factory=Trend)
    occupied: bool = False
    prev_calling: bool = False
    deferred_since: datetime | None = None
    override: Override = Override.AUTO
    override_until: datetime | None = None
    model: RoomModel = field(default_factory=RoomModel.new)
    heaters: list[str] = field(default_factory=list)
    heater_w: float = DEFAULT_HEATER_W
    heater_w_set: bool = False
    heater_eco_w: float | None = None
    power_sensors: dict[str, str] = field(default_factory=dict)  # heater -> its power sensor (W)
    heat_state: bool | None = None
    heat_since: datetime | None = None
    kwh_today: float = 0.0
    heater_min_today: float = 0.0

    @property
    def entities(self) -> list[str]:
        ids = [self.temp_entity, *self.trvs, *self.heaters, *self.power_sensors.values(), *self.presence, *self.media, *self.lights]
        return [e for e in ids + [self.humidity_entity, self.schedule] if e]


class HeatingCoordinator(DataUpdateCoordinator[Plan]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_S),
            config_entry=entry,
        )
        self.entry = entry
        self.house_cfg: dict[str, Any] = dict(entry.data)
        opts = dict(entry.options)
        self.settings = replace(Settings(), **{k: float(opts[k]) for k in OPT_KEYS if k in opts})
        self.heating_type = self.house_cfg.get(CONF_HEATING_TYPE) or (
            TYPE_COMBI if self.house_cfg.get(CONF_HW_SYSTEM) == HW_COMBI else TYPE_TANK
        )
        if self.heating_type == TYPE_ELECTRIC:
            self.hw_system = HW_NONE
        elif self.heating_type == TYPE_COMBI:
            self.hw_system = HW_COMBI
        elif self.heating_type == TYPE_TANK:
            self.hw_system = HW_TANK
        else:
            hw = self.house_cfg.get(CONF_HW_SYSTEM, HW_TANK)
            self.hw_system = HW_TANK if hw in (HW_S_PLAN, HW_Y_PLAN) else hw
        self.thermostat_style = self.house_cfg.get(CONF_THERMOSTAT_STYLE)
        # Cylinder systems: we may pause heating so the cylinder recovers. A combi does it by itself.
        self.settings = replace(
            self.settings,
            hw_priority=self.hw_system not in (HW_COMBI, HW_NONE) and bool(self.house_cfg.get(CONF_HW_PRIORITY, True)),
        )
        self.override_hours = float(opts.get(OPT_OVERRIDE_HOURS, DEFAULT_OVERRIDE_HOURS))

        # Runtime state (restored by the select/switch entities).
        self.mode: Mode = Mode.CONTINUOUS
        self.enabled = True
        self.monitor_only = self.house_cfg.get(CONF_START_MODE, START_WATCH) == START_WATCH  # then restored by its switch

        self.rooms: dict[str, Room] = {}
        for sub_id, sub in entry.subentries.items():
            if sub.subentry_type != SUBENTRY_ROOM:
                continue
            d = sub.data
            area_id = d.get(CONF_AREA)
            level, floor_name = area_tools.area_floor(hass, area_id)
            name = area_tools.area_name(hass, area_id) or d.get(CONF_NAME) or sub.title
            floor = level if level is not None else int(d.get(CONF_FLOOR, 0))
            temp_entity = d.get(CONF_TEMP)
            if not temp_entity and area_id:
                temp_entity = area_tools.discover(hass, area_id).get("temperature_sensor")
            cfg = RoomConfig(
                room_id=sub_id,
                name=name,
                floor=floor,
                priority=Priority(d.get(CONF_PRIORITY, "a")),
                comfort=float(d.get(CONF_COMFORT, 19.0)),
                has_trv=bool(d.get(CONF_TRVS)),
                radiator=self.heating_type != TYPE_ELECTRIC and bool(d.get(CONF_RADIATOR, True)),
                heater=bool(d.get(CONF_HEATERS)),
            )
            self.rooms[sub_id] = Room(
                room_id=sub_id,
                cfg=cfg,
                temp_entity=temp_entity,
                humidity_entity=d.get(CONF_HUMIDITY),
                trvs=list(d.get(CONF_TRVS, [])),
                presence=list(d.get(CONF_PRESENCE, [])),
                media=list(d.get(CONF_MEDIA, [])),
                lights=list(d.get(CONF_LIGHTS, [])),
                schedule=d.get(CONF_SCHEDULE),
                area_id=area_id,
                floor_name=floor_name,
                heaters=list(d.get(CONF_HEATERS, [])),
                heater_w=float(d.get(CONF_HEATER_W) or DEFAULT_HEATER_W),
                heater_w_set=bool(d.get(CONF_HEATER_W)),
                heater_eco_w=float(d[CONF_HEATER_ECO_W]) if d.get(CONF_HEATER_ECO_W) else None,
                power_sensors=area_tools.power_sensors(hass, list(d.get(CONF_HEATERS, []))),
            )
        self.floor_names: dict[int, str] = {
            **area_tools.floor_names(hass),
            **{r.cfg.floor: r.floor_name for r in self.rooms.values() if r.floor_name},
        }

        self._unsub = None
        self._apply_lock = asyncio.Lock()
        self._applied_boiler: bool | None = None

        # Climate picture.
        self.outdoor = OutdoorModel()
        self._forecast_at: datetime | None = None
        self.outdoor_mean: float | None = None
        self.forecast_min_24h: float | None = None
        self.house_temp: float | None = None
        self.floor_temps: dict[int, float] = {}

        # Calibration, learning and gas.
        self._store: Store = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.energy = EnergyDay()
        self.cal_notified = False
        self.night_start = _parse_time(opts.get(OPT_NIGHT_START, DEFAULT_NIGHT_START))
        self.night_end = _parse_time(opts.get(OPT_NIGHT_END, DEFAULT_NIGHT_END))
        self.notify_service: str = str(opts.get(OPT_NOTIFY, "") or "")
        self.gas_price = float(opts.get(OPT_GAS_PRICE, DEFAULT_GAS_PRICE))  # fixed, or fallback for the rate sensor
        self.gas_price_now = self.gas_price
        self.gas_price_from = "fixed"
        self.boiler_kw = float(opts.get(OPT_BOILER_KW, DEFAULT_BOILER_KW))
        self.elec_price = float(opts.get(OPT_ELEC_PRICE, DEFAULT_ELEC_PRICE))
        self.elec_kwh = 0.0
        self.elec_day: str | None = None
        self._elec_tick: datetime | None = None
        self.gas_kwh: float | None = None
        self.gas_measured = False
        self.gas_cost: float | None = None
        self.kwh_per_dd: float | None = None

        # Decision log.
        self.log: deque[dict[str, Any]] = deque(maxlen=LOG_SIZE)
        self._last_verdict: dict[str, str] = {}
        self._last_boiler: bool | None = None
        self._last_status: str | None = None
        self.away = False
        self.away_reason = ""
        self.learning_phase = "starting"
        self.setpoints = Setpoints.initial([r.cfg for r in self.rooms.values()])
        self.welcomed = False
        self.fresh = False  # first start of this setup: nothing to restore
        self._silent_since: datetime | None = None
        # One Cycle: when it started, whether it has heated, every room or only rooms in use.
        self._one_cycle_since: datetime | None = None
        self._one_cycle_heated = False
        self._one_cycle_timer = None  # ends the wait on time, not at the next minute's refresh
        self.one_cycle_all = False
        self.one_cycle_wait: dict[str, Any] | None = None
        self._season_off: bool | None = None
        self._setup_checked: datetime | None = None
        self.heat_test: dict[str, Any] | None = None
        # Boiler protection state.
        self._boiler_cmd_state: bool | None = None
        self._boiler_cmd_at: datetime | None = None
        self._boiler_cmds: list[datetime] = []
        self.boiler_locked_until: datetime | None = None
        self.external_hold_until: datetime | None = None
        self._started_at: datetime | None = None
        self._delivering: bool | None = None
        self._delivering_since: datetime | None = None

    def _log(self, message: str, room: str | None = None, **values: Any) -> None:
        entry = {"time": dt_util.utcnow().isoformat(), "room": room, "message": message, **values}
        self.log.appendleft(entry)
        self.hass.bus.async_fire(EVENT_DECISION, {"room": room, "message": message})
        _LOGGER.debug("%s%s", f"{room}: " if room else "", message)

    def _log_changes(self, plan: Plan) -> None:
        for rid, d in plan.rooms.items():
            room = self.rooms[rid]
            idle = d.verdict.value == "idle"
            key = "idle" if idle else f"{d.verdict.value}:{_NUMBERS.sub('#', d.reason)}"  # trend changes aren't news
            prev = self._last_verdict.get(rid)
            if prev == key:
                continue
            if d.verdict.value == "fault" and self.starting:
                continue  # sensors still coming up after a restart; logged if it lasts
            self._last_verdict[rid] = key
            if idle and prev is None:
                continue
            temp = self.room_temp(room)
            if idle:
                parts = [f"satisfied at {temp:.1f}°" if temp is not None else "satisfied"]
            else:
                parts = [d.verdict.value, f"({d.reason})"]
                if temp is not None and d.need.target is not None:
                    parts.append(f"{temp:.1f}° to {d.need.target:.1f}°")
            if d.open_valve is not None:
                parts.append("valve opening" if d.open_valve else "valve closing")
            self._log(" ".join(parts), room=room.cfg.name, verdict=d.verdict.value,
                      temp=temp, target=d.need.target, trend=room.trend.rate())
        if plan.boiler_on != self._last_boiler and self._last_boiler is not None:
            self._log(f"Boiler {'on' if plan.boiler_on else 'off'}: {plan.reason}", boiler=plan.boiler_on)
        elif plan.status != self._last_status and self._last_status is not None:
            self._log(f"Status {plan.status}: {plan.reason}")
        self._last_boiler, self._last_status = plan.boiler_on, plan.status

    # ---------- calibration ----------

    @property
    def calibration_progress(self) -> float:
        return overall_progress([r.model for r in self.rooms.values()])

    # ---------- capabilities ----------

    @property
    def boiler_entity(self) -> str | None:
        return self.house_cfg.get(CONF_BOILER) or None

    @property
    def boiler_control(self) -> bool:
        return self.boiler_entity is not None

    @property
    def has_trvs(self) -> bool:
        return any(r.trvs for r in self.rooms.values())

    @property
    def has_boiler_state(self) -> bool:
        return bool(self.house_cfg.get(CONF_BOILER_ON) or self.boiler_entity)

    @property
    def has_outdoor(self) -> bool:
        return bool(self.house_cfg.get(CONF_OUTDOOR_TEMP) or self.house_cfg.get(CONF_WEATHER))

    @property
    def has_heaters(self) -> bool:
        return any(r.heaters for r in self.rooms.values())

    @property
    def has_gas(self) -> bool:
        return self.heating_type != TYPE_ELECTRIC

    @property
    def learnable(self) -> bool:
        """Calibration needs outdoor temperature and to know when each room gets heat."""
        return self.has_outdoor and (self.has_boiler_state or self.has_heaters)

    @property
    def profile(self) -> str:
        if self.has_heaters and not self.boiler_control and not self.has_trvs:
            return "electric"
        if self.has_heaters and (self.boiler_control or self.has_trvs):
            return "hybrid"
        if self.boiler_control and self.has_trvs:
            return "full_zoning"
        if self.boiler_control:
            return "single_zone"
        if self.has_trvs:
            return "valve_only"
        return "monitor"

    @property
    def capabilities(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "heating_type": self.heating_type,
            "heaters": self.has_heaters,
            "boiler_control": self.boiler_control,
            "boiler_state": self.has_boiler_state,
            "trvs": self.has_trvs,
            "outdoor": self.has_outdoor,
            "presence": any(r.presence or r.media or r.lights for r in self.rooms.values()),
            "hot_water": bool(self.hw_entity),
            "hot_water_system": self.hw_system,
            "hot_water_priority": self.settings.hw_priority,
            "thermostat_style": self.thermostat_style if self._is_thermostat else None,
            "gas_meter": bool(self.house_cfg.get(CONF_GAS_METER)),
            "away_detection": bool(self.away_entities),
            "calibration": "available" if self.learnable else "unavailable (needs outdoor source and boiler state)",
        }

    @property
    def calibrated(self) -> bool:
        """Enough rooms have learned their model. Display and notification only: control never waits for it."""
        if not self.learnable:
            return True
        if not self.rooms:
            return False
        done = sum(1 for r in self.rooms.values() if r.model.complete)
        return done / len(self.rooms) >= CALIBRATED_SHARE

    @property
    def calibration_info(self) -> dict[str, Any]:
        if not self.learnable:
            return {}
        return calibration_summary([r.model for r in self.rooms.values()], CALIBRATED_SHARE)

    @property
    def house_tau(self) -> float | None:
        return insulation.combine([r.model.tau for r in self.rooms.values() if r.model.tau])

    def floor_tau(self, floor: int) -> float | None:
        return insulation.combine([r.model.tau for r in self.rooms.values() if r.cfg.floor == floor and r.model.tau])

    def weakest_rooms(self, n: int = 3) -> list[dict]:
        rated = sorted((r for r in self.rooms.values() if r.model.tau), key=lambda r: r.model.tau)
        return [{"room": r.cfg.name, "grade": insulation.grade(r.model.tau), "time_constant_h": r.model.tau} for r in rated[:n]]

    def _store_data(self) -> dict[str, Any]:
        return {
            "rooms": {rid: r.model.to_dict() for rid, r in self.rooms.items()},
            "energy": self.energy.to_dict(),
            "cal_notified": self.cal_notified,
            "setpoints": self.setpoints.to_dict(),
            "welcomed": self.welcomed,
            "log": list(self.log),
            "heat_test": self.heat_test,
            "electric": {
                "day": self.elec_day, "kwh": self.elec_kwh,
                "rooms": {rid: [r.kwh_today, r.heater_min_today] for rid, r in self.rooms.items() if r.heaters},
            },
        }

    async def _load(self) -> None:
        data = await self._store.async_load() or {}
        self.fresh = not data
        for rid, d in data.get("rooms", {}).items():
            if rid in self.rooms:
                try:
                    self.rooms[rid].model = RoomModel.from_dict(d)
                except (TypeError, ValueError) as err:
                    _LOGGER.warning("Discarding stored model for %s: %s", rid, err)
        if "energy" in data:
            self.energy = EnergyDay.from_dict(data["energy"])
        self.cal_notified = bool(data.get("cal_notified", False))
        self.welcomed = bool(data.get("welcomed", False))
        for entry in data.get("log") or []:  # newest first, older than anything logged since start
            if isinstance(entry, dict):
                self.log.append(entry)
        self.heat_test = data.get("heat_test") or None
        el = data.get("electric") or {}
        if el.get("day") == dt_util.as_local(dt_util.utcnow()).date().isoformat():
            self.elec_day, self.elec_kwh = el["day"], float(el.get("kwh", 0))
            for rid, (kwh, mins) in (el.get("rooms") or {}).items():
                if rid in self.rooms:
                    self.rooms[rid].kwh_today, self.rooms[rid].heater_min_today = float(kwh), float(mins)
        if data.get("setpoints"):
            try:
                self.setpoints = Setpoints.from_dict(data["setpoints"])
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.warning("Discarding stored setpoints: %s", err)

    @property
    def starting(self) -> bool:
        """The first minutes after a start, while sensors are still coming up."""
        return bool(self._started_at and dt_util.utcnow() - self._started_at < timedelta(minutes=STARTUP_GRACE_MIN))

    async def _notify_calibrated(self) -> None:
        tau = self.house_tau
        msg = (
            "Smart Heating has learned how your rooms lose and gain heat"
            + (f" (house heat-loss time constant about {tau:.0f} h)" if tau else "")
            + ": predictions and insulation grades are ready."
            + (" It is still watching only: tap **Start heating** on the card when you are ready." if self.monitor_only else "")
        )
        persistent_notification.async_create(
            self.hass, msg, title="Smart Heating has learned your house", notification_id=f"{DOMAIN}_calibrated"
        )
        if self.notify_service and "." in self.notify_service:
            domain, service = self.notify_service.split(".", 1)
            try:
                await self.hass.services.async_call(
                    domain, service, {"title": "Smart Heating has learned your house", "message": msg.replace("**", "")}
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Notify via %s failed: %s", self.notify_service, err)

    @property
    def boiler_firing(self) -> bool | None:
        """Is the boiler burning right now (running sensor if set, else the control state)? None if unknown."""
        if not self.has_boiler_state:
            return None
        return self._firing(dt_util.utcnow())[0]

    @property
    def hw_entity(self) -> str | None:
        """The hot water call signal. Ignored when it is the boiler's own sensor or switch: that says the
        boiler is running, not that the tank is asking for heat."""
        hw = self.house_cfg.get(CONF_HW_CALLING)
        if hw and hw in (self.house_cfg.get(CONF_BOILER_ON), self.house_cfg.get(CONF_BOILER)):
            return None
        return hw or None

    @property
    def hot_water_on(self) -> bool | None:
        entity = self.hw_entity
        return self._is_on(entity) if entity else None

    @property
    def night_now(self) -> bool:
        return self._is_night(dt_util.utcnow())

    @property
    def floors(self) -> list[int]:
        return sorted({r.cfg.floor for r in self.rooms.values()})

    # ---------- lifecycle ----------

    async def async_start(self) -> None:
        tracked: set[str] = set()
        for room in self.rooms.values():
            tracked.update(room.entities)
        for key in (CONF_BOILER, CONF_BOILER_ON, CONF_HW_CALLING, CONF_OUTDOOR_MEAN, CONF_OUTDOOR_TEMP, CONF_NIGHT_SCHEDULE):
            if self.house_cfg.get(key):
                tracked.add(self.house_cfg[key])
        tracked.update(self.away_entities)
        if self.house_cfg.get(CONF_GAS_METER):
            tracked.add(self.house_cfg[CONF_GAS_METER])
        from homeassistant.helpers import area_registry as ar, floor_registry as fr

        @callback
        def _registry_changed(event) -> None:
            ids = {r.area_id for r in self.rooms.values()}
            if event.data.get("area_id") in ids or event.event_type == fr.EVENT_FLOOR_REGISTRY_UPDATED:
                self.hass.config_entries.async_schedule_reload(self.entry.entry_id)

        self._unsub_registry = [
            self.hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, _registry_changed),
            self.hass.bus.async_listen(fr.EVENT_FLOOR_REGISTRY_UPDATED, _registry_changed),
        ]
        await self._load()
        if self.fresh:  # saved at once, so only the very first start counts as fresh
            await self._store.async_save(self._store_data())
        self._started_at = dt_util.utcnow()
        self._log(f"Started: {self.profile.replace('_', ' ')} profile, {len(self.rooms)} room(s)"
                  + ("" if self.learnable else ", calibration unavailable"))
        if not self.welcomed:
            self.welcomed = True
            learning = (
                "It learns how each room holds heat in the background (usually 1 to 3 days). Predictions and "
                "insulation grades appear room by room as they are learned. Tap the **Learning** badge on the card "
                "to see progress or run the gentle **Heat test** to speed it up."
            )
            if self.monitor_only:
                title = "Smart Heating is watching"
                msg = ("It decides and logs what it would do, without touching the boiler or TRVs. When you are happy, "
                       "tap **Start heating** on the card.\n\n" + learning)
            else:
                title = "Smart Heating is heating your home"
                msg = "It runs on sensible defaults from today.\n\n" + learning
            persistent_notification.async_create(self.hass, msg, title=title, notification_id=f"{DOMAIN}_welcome")
        self._check_setup()
        self._unsub = async_track_state_change_event(self.hass, list(tracked), self._on_change)
        await self.async_config_entry_first_refresh()

    async def async_stop(self) -> None:
        self._reset_one_cycle()
        if self._unsub:
            self._unsub()
            self._unsub = None
        for unsub in getattr(self, "_unsub_registry", []):
            unsub()
        await self._store.async_save(self._store_data())

    @callback
    def _on_change(self, event: Event[EventStateChangedData]) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    # ---------- user controls ----------

    async def async_set_mode(self, mode: Mode, all_rooms: bool = False, restoring: bool = False) -> None:
        """Off always cancels: One Cycle, Heat now in every room, a heat test, and the boiler at once."""
        now = dt_util.utcnow()
        if restoring:
            self.mode = mode
            if mode is Mode.ONE_CYCLE:
                self._one_cycle_since, self._one_cycle_heated = now, False
            return
        if mode is Mode.OFF:
            await self._cancel_to_off("Off")
            await self.async_request_refresh()
            return
        if mode is Mode.ONE_CYCLE:
            if self.mode is Mode.ONE_CYCLE:
                if all_rooms and not self.one_cycle_all:
                    self._log("One Cycle: heating every room below its target")
            else:
                self._log("Mode set to one_cycle" + (", every room below its target" if all_rooms else ""))
                self._one_cycle_since, self._one_cycle_heated = now, False
            self.one_cycle_all = self.one_cycle_all or all_rooms
        else:
            if mode is not self.mode:
                self._log(f"Mode set to {mode.value}")
            self._reset_one_cycle()
        self.mode = mode
        await self.async_refresh()  # at once, so the card shows what One Cycle will do

    def _reset_one_cycle(self) -> None:
        self._one_cycle_since, self._one_cycle_heated = None, False
        self.one_cycle_all, self.one_cycle_wait = False, None
        if self._one_cycle_timer:
            self._one_cycle_timer()
            self._one_cycle_timer = None

    @callback
    def _one_cycle_due(self, _now: datetime) -> None:
        self._one_cycle_timer = None
        self.hass.async_create_task(self.async_request_refresh())

    async def _cancel_to_off(self, why: str) -> None:
        """Back to Off: Heat now ends in every room, One Cycle and any heat test stop, the boiler goes off."""
        manual = [r for r in self.rooms.values() if r.override is Override.HEAT]
        for r in manual:
            r.override, r.override_until = Override.AUTO, None
        self._reset_one_cycle()
        was = self.mode
        self.mode = Mode.OFF
        self._log(f"{why}: heating off" + (f", Heat now ended in {', '.join(r.cfg.name for r in manual)}" if manual else "")
                  if was is not Mode.OFF or manual else "Mode set to off")
        if self.heat_test:
            await self._finish_heat_test("stopped: heating set to Off")
        if self.boiler_control and self.enabled and not self.monitor_only:
            await self._boiler(False, force=True)  # off is always allowed, even inside the guard time

    async def async_set_enabled(self, value: bool) -> None:
        self.enabled = value
        if not value and self.boiler_control:
            await self._boiler(False, force=True)
        await self.async_request_refresh()

    async def async_set_monitor_only(self, value: bool, restoring: bool = False) -> None:
        if value != self.monitor_only and not restoring:
            self._log("Watching only: decisions are logged, the boiler and TRVs are left alone" if value
                      else "Heating: Smart Heating now controls the boiler and TRVs")
        self.monitor_only = value
        self._check_setup()
        await self.async_request_refresh()

    # ---------- setpoints ----------

    @property
    def effective_settings(self) -> Settings:
        return self.setpoints.settings(self.settings)

    def room_comfort(self, room: Room) -> float:
        return self.setpoints.comfort(room.cfg)

    async def async_set_house_target(self, value: float) -> None:
        value = round(float(value) * 2) / 2
        if value != self.setpoints.house:
            self._log(f"House target set to {value:.1f}° (rooms shift {value - self.setpoints.house:+.1f}°)")
        self.setpoints.house = value
        await self._store.async_save(self._store_data())
        await self.async_request_refresh()

    async def async_set_room_target(self, room_id: str, value: float) -> None:
        room = self.rooms[room_id]
        value = round(float(value) * 2) / 2
        self.setpoints.set_room(room.cfg, value)
        self._log(f"Target set to {value:.1f}°", room=room.cfg.name)
        await self._store.async_save(self._store_data())
        await self.async_request_refresh()

    # ---------- going live ----------

    async def async_start_control(self, skip_calibration: bool = False) -> None:
        """Leave watch mode. Learning carries on in the background (skip_calibration is no longer needed)."""
        await self.async_set_monitor_only(False)
        await self._store.async_save(self._store_data())

    async def async_relearn(self, room_ids: list[str]) -> None:
        """Forget what these rooms have learned; they learn again from now."""
        for rid in room_ids:
            room = self.rooms.get(rid)
            if room is None:
                continue
            room.model = RoomModel.new()
            room.heat_state = room.heat_since = None
            self._log("Relearning: learned data cleared", room=room.cfg.name)
        if not self.calibrated:
            self.cal_notified = False
        await self._store.async_save(self._store_data())
        await self.async_request_refresh()

    # ---------- setup checks (Repairs) ----------

    def _issue(self, issue_id: str, active: bool, placeholders: dict[str, str] | None = None) -> None:
        if active:
            ir.async_create_issue(
                self.hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                translation_key=issue_id, translation_placeholders=placeholders or {},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    @callback
    def _check_setup(self) -> None:
        """Settings that would make control misbehave, shown in Settings > Repairs."""
        self._setup_checked = dt_util.utcnow()
        hw = self.house_cfg.get(CONF_HW_CALLING)
        self._issue("hw_same_as_boiler", bool(hw) and self.hw_entity is None, {"entity": str(hw)})
        others = self.competing_automations if self.boiler_control and not self.monitor_only else []
        self._issue("competing_automations", bool(others), {"automations": ", ".join(others)})

    def _check_boiler_response(self, now: datetime) -> None:
        """The boiler running sensor should follow a heating call; warn when it stays off."""
        if not (self.boiler_control and self.house_cfg.get(CONF_BOILER_ON)) or self.monitor_only or self.heat_test:
            self._silent_since = None
            return
        firing, _ = self._firing(now)
        if firing:
            self._silent_since = None
            self._issue("boiler_sensor_silent", False)
        elif self._commanded_on(self._state(self.boiler_entity)):
            self._silent_since = self._silent_since or now
            if now - self._silent_since >= timedelta(minutes=BOILER_SILENT_MIN):
                self._issue("boiler_sensor_silent", True, {
                    "sensor": self.house_cfg[CONF_BOILER_ON], "minutes": str(BOILER_SILENT_MIN)})
        else:
            self._silent_since = None

    @property
    def competing_automations(self) -> list[str]:
        """Enabled automations that also use the boiler control: they may switch it while we do."""
        if not self.boiler_entity:
            return []
        try:
            from homeassistant.components.automation import automations_with_entity
            ids = automations_with_entity(self.hass, self.boiler_entity)
        except Exception:  # noqa: BLE001
            return []
        out = []
        for eid in ids:
            st = self.hass.states.get(eid)
            if st is not None and st.state == "on":
                out.append(st.attributes.get("friendly_name") or eid)
        return out

    async def async_heat_test(self, start: bool = True, ignore_automations: bool = False) -> None:
        """Calibration heat test: rooms that still need heating data warm gently, boiler on. Then the house cools."""
        now = dt_util.utcnow()
        if not start:
            if self.heat_test:
                await self._finish_heat_test("stopped")
            return
        if self.heat_test:
            return
        if not self.enabled:
            raise HomeAssistantError("The controller is disabled.")
        if not (self.boiler_control or self.has_trvs or self.has_heaters):
            raise HomeAssistantError("The heat test needs boiler control, TRVs or heaters.")
        others = self.competing_automations
        if others and not ignore_automations:
            raise HomeAssistantError(
                f"These automations also use {self.boiler_entity}: {', '.join(others)}. "
                "Turn them off first, so they don't switch the boiler during the test."
            )
        prev = {}
        for room in self.rooms.values():
            for trv in room.trvs:
                st = self._state(trv)
                if st is not None:
                    prev[trv] = st.attributes.get("temperature")
        prev_heaters = {}
        for room in self.rooms.values():
            for h in room.heaters:
                st = self._state(h)
                if st is not None:
                    prev_heaters[h] = [st.state, st.attributes.get("temperature")]
        # Gentle: only rooms that still need heating data, and none already near the cap.
        start_temps = {r.room_id: self.room_temp(r) for r in self.rooms.values()}
        controlled = [r for r in self.rooms.values() if r.trvs or r.heaters]
        closed = [
            r.room_id for r in controlled
            if r.model.heat_n >= HEAT_NEEDED
            or (start_temps[r.room_id] is not None and start_temps[r.room_id] >= HEAT_TEST_CAP - 0.3)
        ]
        to_open = [r for r in controlled if r.room_id not in closed]
        if controlled and not to_open:
            if all(r.model.heat_n >= HEAT_NEEDED for r in controlled):
                self._log("Heat test not needed: every room already has its heating data")
                raise HomeAssistantError("No room needs heating data any more, so the heat test isn't needed.")
            raise HomeAssistantError(
                f"The rooms that still need heating data are already near {HEAT_TEST_CAP:g}°. "
                "Run the heat test when the house is cooler."
            )
        if self.boiler_control:
            warm = [r.cfg.name for r in self._unvalved_rooms()
                    if start_temps[r.room_id] is not None and start_temps[r.room_id] >= HEAT_TEST_CAP - 0.3]
            if warm:
                raise HomeAssistantError(
                    f"{', '.join(warm)} {'is' if len(warm) == 1 else 'are'} already near {HEAT_TEST_CAP:g}° and "
                    "can't be closed (no smart valve). Run the heat test when the house is cooler."
                )
        boiler = self._state(self.boiler_entity)
        self.heat_test = {
            "until": (now + timedelta(minutes=HEAT_TEST_MIN)).isoformat(),
            "prev_trv": prev,
            "prev_heaters": prev_heaters,
            "boiler_was_on": self._commanded_on(boiler),
            "start_temps": start_temps,
            "closed": closed,
        }
        await self._store.async_save(self._store_data())
        if controlled:
            self._log(
                f"Heat test started for {len(to_open)} room(s): up to {HEAT_TEST_RISE:g}° warmer, "
                f"never above {HEAT_TEST_CAP:g}°"
            )
        else:
            self._log(f"Heat test started: boiler on for up to {HEAT_TEST_MIN // 60} h {HEAT_TEST_MIN % 60} min")
        for room in to_open:
            for trv in room.trvs:
                await self._set_trv(trv, None, open_max=True)
            for h in room.heaters:
                await self._set_heater(h, True, 25.0, room)
        await self._boiler(True, 25.0)
        await self.async_refresh()

    def _unvalved_rooms(self) -> list[Room]:
        """Radiators without a smart valve: during the heat test only stopping the boiler stops them."""
        return [r for r in self.rooms.values() if r.cfg.radiator and not r.trvs]

    @property
    def heat_test_left_min(self) -> int | None:
        if not self.heat_test:
            return None
        until = dt_util.parse_datetime(self.heat_test["until"])
        return max(0, round((until - dt_util.utcnow()).total_seconds() / 60)) if until else 0

    async def _run_heat_test(self, plan: Plan) -> None:
        """Keep the test going: close rooms that are done, end on time."""
        test = self.heat_test
        if not test:
            return
        left = self.heat_test_left_min or 0
        starts = test.setdefault("start_temps", {})
        live = [r for r in self.rooms.values() if (r.trvs or r.heaters) and r.room_id not in test["closed"]]
        for room in live:
            t = self.room_temp(room)
            if starts.get(room.room_id) is None and t is not None:
                starts[room.room_id] = t  # no reading at the start (or a test from before 0.9.7)
            start = starts.get(room.room_id)
            stop = min(HEAT_TEST_CAP, start + HEAT_TEST_RISE) if start is not None else HEAT_TEST_CAP
            has_data = room.model.heat_n >= HEAT_NEEDED
            if not has_data and (t is None or t < stop):
                continue
            test["closed"].append(room.room_id)
            self._log(
                "Heat test: has its heating data, radiator closed" if has_data
                else f"Heat test: reached {t:.1f}°, radiator closed",
                room=room.cfg.name,
            )
            for trv in room.trvs:
                await self._set_trv(trv, self.settings.trv_closed)
            for h in room.heaters:
                await self._set_heater(h, False, 0, room)
        if self.heat_test is not test:
            return
        if self.boiler_control:
            hot = next(((r, t) for r in self._unvalved_rooms() if (t := self.room_temp(r)) is not None and t >= HEAT_TEST_CAP), None)
            if hot:
                await self._finish_heat_test(f"stopped: {hot[0].cfg.name} reached {hot[1]:.1f}° and has no smart valve to close")
                return
        controlled = [r for r in self.rooms.values() if r.trvs or r.heaters]
        all_closed = bool(controlled) and all(r.room_id in test["closed"] for r in controlled)
        if left <= 0 or all_closed:
            await self._finish_heat_test("finished" if left <= 0 else "done for every room")
            return
        if self.settings.hw_priority and self._is_on(self.hw_entity):
            return  # tank heating first; the test carries on after
        await self._boiler(True, 25.0)

    async def _finish_heat_test(self, why: str) -> None:
        test, self.heat_test = self.heat_test, None
        if not test:
            return
        self._log(f"Heat test {why}: radiators back to their settings, the house now cools for calibration")
        for trv, temp in (test.get("prev_trv") or {}).items():
            if temp is not None:
                await self._set_trv(trv, float(temp))
        by_heater = {h: r for r in self.rooms.values() for h in r.heaters}
        for h, (state, temp) in (test.get("prev_heaters") or {}).items():
            room = by_heater.get(h)
            if room is None:
                continue
            on = state not in ("off",) if h.startswith("climate.") else state == STATE_ON
            await self._set_heater(h, on, float(temp) if temp else self.room_comfort(room), room)
        if self.monitor_only or not self.enabled:
            was_on = bool(test.get("boiler_was_on"))
            await self._boiler(was_on, force=not was_on)  # never leave the boiler on after a test
        await self._store.async_save(self._store_data())
        self.hass.async_create_task(self.async_request_refresh())

    def _heater_entity_on(self, entity_id: str) -> bool:
        st = self._state(entity_id)
        if st is None:
            return False
        if st.domain == "climate":
            action = st.attributes.get("hvac_action")
            return action == "heating" if action is not None else st.state not in ("off", "idle")
        return st.state == STATE_ON

    def _heater_on(self, room: Room) -> bool | None:
        """Is any heater in the room switched to heat (commanded, not necessarily drawing)?"""
        states = [self._state(h) for h in room.heaters]
        if not any(states):
            return None
        return any(
            (st.state not in ("off",) if st.domain == "climate" else st.state == STATE_ON)
            for st in states if st is not None
        )

    async def _set_heater(self, entity_id: str, on: bool, target: float, room: Room) -> None:
        st = self._state(entity_id)
        if st is None:
            return
        domain = st.domain
        try:
            if domain == "climate":
                if on:
                    want = round(target * 2) / 2
                    cur = st.attributes.get("temperature")
                    if st.state != "off" and cur is not None and abs(float(cur) - want) < 0.25:
                        return
                    data: dict[str, Any] = {"entity_id": entity_id, "temperature": want}
                    if st.state == "off" and "heat" in (st.attributes.get("hvac_modes") or ["heat"]):
                        data["hvac_mode"] = "heat"
                    await self.hass.services.async_call("climate", "set_temperature", data, blocking=True)
                elif st.state != "off":
                    if "off" in (st.attributes.get("hvac_modes") or ["off"]):
                        await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "off"}, blocking=True)
                    else:
                        await self.hass.services.async_call("climate", "set_temperature", {"entity_id": entity_id, "temperature": float(st.attributes.get("min_temp") or 5)}, blocking=True)
                return
            if (st.state == STATE_ON) == on:
                return
            await self.hass.services.async_call(
                domain if domain in ("switch", "input_boolean", "light") else "homeassistant",
                "turn_on" if on else "turn_off", {"entity_id": entity_id}, blocking=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Heater %s command failed: %s", entity_id, err)
            self._log(f"Heater {entity_id} command failed: {err}", room=room.cfg.name)

    async def _set_trv(self, trv: str, temp: float | None, open_max: bool = False) -> None:
        st = self._state(trv)
        if st is None:
            return
        data: dict[str, Any] = {"entity_id": trv}
        if open_max:
            temp = min(30.0, float(st.attributes.get("max_temp") or 30))
            if st.state == "off" and "heat" in (st.attributes.get("hvac_modes") or []):
                data["hvac_mode"] = "heat"
        data["temperature"] = temp
        try:
            await self.hass.services.async_call("climate", "set_temperature", data, blocking=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("TRV %s set %s failed: %s", trv, temp, err)
        await asyncio.sleep(TRV_STAGGER_S)

    async def async_set_override(self, room_id: str, value: Override) -> None:
        room = self.rooms[room_id]
        self._log(f"Override {value.value}" + (f" for {self.override_hours:g} h" if value is not Override.AUTO else ""), room=room.cfg.name)
        room.override = value
        room.override_until = (
            None if value is Override.AUTO
            else dt_util.utcnow() + timedelta(hours=self.override_hours)
        )
        if value is Override.HEAT and self.mode is Mode.OFF:
            self._log("Heat now while Off: One Cycle started", room=room.cfg.name)
            await self.async_set_mode(Mode.ONE_CYCLE)
            return
        await self.async_request_refresh()

    # ---------- update ----------

    async def _async_update_data(self) -> Plan:
        now = dt_util.utcnow()
        self._check_external_boiler(now)
        await self._update_climate(now)
        self._update_away()
        house = self._house_snapshot(now)

        pairs: list[tuple[RoomConfig, RoomSnapshot]] = []
        for room in self.rooms.values():
            pairs.append((self.setpoints.room_cfg(room.cfg), self._room_snapshot(room, now)))

        self.house_temp, self.floor_temps = house_means(
            [(cfg.floor, snap.temp) for cfg, snap in pairs]
        )

        plan = make_plan(pairs, house, self.effective_settings, boiler_control=self.boiler_control)

        self._learn(now, house, pairs)
        self._account(now, house, plan)
        if self.learnable and self.calibrated and not self.cal_notified:
            self.cal_notified = True
            self._log("Learning complete: predictions and insulation grades are ready")
            self.hass.async_create_task(self._notify_calibrated())
        self._check_boiler_response(now)
        if self._setup_checked is None or now - self._setup_checked >= timedelta(minutes=10):
            self._check_setup()
        self._store.async_delay_save(self._store_data, SAVE_DELAY_S)

        # One Cycle ends itself once nothing calls or every caller is coasting.
        if self.away and plan.status == "off":
            plan.status, plan.reason = "away", self.away_reason or "away"
        if self.mode is Mode.ONE_CYCLE:
            self._one_cycle_step(now, plan)

        # Remember state for hysteresis and stack wait.
        for room in self.rooms.values():
            d = plan.rooms.get(room.room_id)
            if d is None:
                continue
            room.prev_calling = d.need.calling
            if d.verdict.value == "deferred":
                room.deferred_since = room.deferred_since or now
            else:
                room.deferred_since = None

        if not self.enabled:
            plan.status, plan.reason = "disabled", "controller disabled"
        if self.heat_test and self.enabled:
            plan.status = "testing"
            plan.reason = f"heat test, {self.heat_test_left_min} min left"
            if self.boiler_control:
                # Show what the test is doing, not what normal control would do.
                plan.boiler_on = self._commanded_on(self._state(self.boiler_entity))
        elif plan.status == "fault" and self.starting:
            plan.status, plan.reason = "starting", "waiting for sensors after start-up"
        if self.boiler_locked_until and now < self.boiler_locked_until:
            plan.reason = f"boiler protection: switching paused until {dt_util.as_local(self.boiler_locked_until):%H:%M}; {plan.reason}"
        elif self.external_hold_until and now < self.external_hold_until:
            plan.reason = f"boiler switched by something else, backing off until {dt_util.as_local(self.external_hold_until):%H:%M}; {plan.reason}"
        self._log_changes(plan)
        if self.heat_test and self.enabled:
            if not self._apply_lock.locked():
                self.hass.async_create_background_task(self._locked(self._run_heat_test(plan)), f"{DOMAIN}_heat_test")
        elif self.enabled and self.monitor_only:
            plan.reason = f"watching only: {plan.reason}"
        elif self.enabled:
            if self._apply_lock.locked():
                _LOGGER.debug("Previous apply still running, skipping")
            else:
                self.hass.async_create_background_task(self._apply(plan), f"{DOMAIN}_apply")
        return plan

    def _learn(self, now: datetime, house: HouseSnapshot, pairs) -> None:
        if not self.learnable:
            return
        tout = self.outdoor.now_temp(now)
        gas_on, gas_min = self._radiators_heating(now) if self.has_boiler_state else (False, 1e9)
        heaters_on = any(snap.heater_on for _, snap in pairs)
        if tout is None:
            self.learning_phase = "waiting for outdoor temperature"
        elif gas_on or heaters_on:
            self.learning_phase = "collecting heating data"
        elif gas_min < 60:
            self.learning_phase = f"radiators cooling down ({60 - int(gas_min)} min until cooling data)"
        else:
            self.learning_phase = "collecting cooling data"
        for cfg, snap in pairs:
            room = self.rooms[cfg.room_id]
            radiator_open = snap.valve_open if room.trvs else None
            gas_heat = cfg.radiator and gas_on and radiator_open is not False
            heating = bool(gas_heat or snap.heater_on)
            if room.heat_state is None:
                room.heat_state = heating
                room.heat_since = now - timedelta(minutes=min(gas_min if cfg.radiator else 1e6, 1e6))
            elif heating != room.heat_state:
                room.heat_state, room.heat_since = heating, now
            mins = _minutes(now, room.heat_since)
            if heating:
                phase = Phase.HEAT if mins >= 10 else Phase.OTHER
            elif cfg.radiator and gas_on:
                phase = Phase.OTHER  # boiler on, this radiator shut: pipes still warm the room a bit
            else:
                quiet = min(mins, gas_min) if cfg.radiator else mins
                phase = Phase.FREE if quiet >= 60 else Phase.OTHER
            room.model.observe(now, snap.temp, tout, phase)

    def heater_power_w(self, room: Room) -> float:
        """Present electric draw of a room's heaters in W: measured if a power sensor exists, else rated."""
        total = 0.0
        for h in room.heaters:
            sensor = room.power_sensors.get(h)
            measured = self._float(sensor) if sensor else None
            if measured is not None:
                st = self._state(sensor)
                unit = str(st.attributes.get("unit_of_measurement", "W")).lower() if st else "w"
                total += measured * (1000 if unit == "kw" else 1)
                continue
            if not self._heater_entity_on(h):
                continue
            st = self._state(h)
            eco = bool(st and "eco" in str(st.attributes.get("preset_mode") or "").lower())
            total += room.heater_eco_w if eco and room.heater_eco_w else room.heater_w
        return round(total, 1)

    @property
    def electric_measured(self) -> bool:
        return all(len(r.power_sensors) == len(r.heaters) for r in self.rooms.values() if r.heaters)

    @property
    def elec_cost(self) -> float:
        return round(self.elec_kwh * self.elec_price, 2)

    @property
    def elec_projected_kwh(self) -> float | None:
        local = dt_util.as_local(dt_util.utcnow())
        hours = local.hour + local.minute / 60
        return round(self.elec_kwh * 24 / hours, 2) if hours >= 1 else None

    def _account_electric(self, now: datetime) -> None:
        if not self.has_heaters:
            return
        day = dt_util.as_local(now).date().isoformat()
        if self.elec_day != day:
            self.elec_day, self.elec_kwh = day, 0.0
            for r in self.rooms.values():
                r.kwh_today = r.heater_min_today = 0.0
        last, self._elec_tick = self._elec_tick, now
        if last is None:
            return
        hours = min((now - last).total_seconds() / 3600, 0.25)  # ignore gaps (restarts)
        for r in self.rooms.values():
            if not r.heaters:
                continue
            w = self.heater_power_w(r)
            kwh = w * hours / 1000
            r.kwh_today = round(r.kwh_today + kwh, 4)
            if w > 0:
                r.heater_min_today += hours * 60
            self.elec_kwh = round(self.elec_kwh + kwh, 4)

    @property
    def gas_source(self) -> str:
        """smart_meter: kWh from a meter integration; estimate: boiler running time x input."""
        src = self.house_cfg.get(CONF_ENERGY_SOURCE)
        if src in (SOURCE_METER, SOURCE_ESTIMATE):
            return src
        return SOURCE_METER if self.house_cfg.get(CONF_GAS_METER) else SOURCE_ESTIMATE

    def _gas_unit_price(self) -> tuple[float, str]:
        """(£/kWh, where from): the rate sensor when it reads, else the fixed price."""
        rate = self._float(self.house_cfg.get(CONF_GAS_RATE)) if self.gas_source == SOURCE_METER else None
        if rate is not None:
            unit = str((self._state(self.house_cfg.get(CONF_GAS_RATE)).attributes.get("unit_of_measurement") or "")).lower()
            if unit.startswith("p/") or "pence" in unit:
                rate /= 100
            if 0 <= rate < 5:
                return rate, "rate sensor"
        return self.gas_price, "fixed"

    def _account(self, now: datetime, house: HouseSnapshot, plan: Plan) -> None:
        self._account_electric(now)
        meter_entity = self.house_cfg.get(CONF_GAS_METER) if self.gas_source == SOURCE_METER else None
        meter = self._float(meter_entity)
        st = self._state(meter_entity)
        unit_m3 = bool(st and str(st.attributes.get("unit_of_measurement", "")).lower() in ("m³", "m3", "ft³"))
        firing, _ = self._firing(now)
        self.energy = self.energy.tick(
            now,
            dt_util.as_local(now).date(),
            firing,
            house.hw_calling,
            plan.boiler_on,
            meter,
            self.outdoor.now_temp(now),
        )
        self.gas_kwh, self.gas_measured = self.energy.gas_kwh(unit_m3, self.boiler_kw)
        self.gas_price_now, self.gas_price_from = self._gas_unit_price()
        self.gas_cost = self.energy.price(self.gas_kwh, self.gas_price_now)
        self.kwh_per_dd = self.energy.kwh_per_degree_day(self.gas_kwh, self.settings.season_gate)

    def _weather_temp(self, weather: str | None) -> float | None:
        """The weather entity's current temperature (used when there is no outdoor sensor)."""
        st = self._state(weather)
        try:
            return float(st.attributes["temperature"]) if st is not None else None
        except (KeyError, TypeError, ValueError):
            return None

    async def _update_climate(self, now: datetime) -> None:
        weather = self.house_cfg.get(CONF_WEATHER)
        temp = self._float(self.house_cfg.get(CONF_OUTDOOR_TEMP))
        if temp is None:
            temp = self._weather_temp(weather)
        if temp is not None:
            self.outdoor.observe(now, temp)

        due = self._forecast_at is None or now - self._forecast_at >= timedelta(minutes=FORECAST_REFRESH_MIN)
        if weather and due:
            self._forecast_at = now
            points = []
            try:
                resp = await self.hass.services.async_call(
                    "weather", "get_forecasts",
                    {"entity_id": weather, "type": "hourly"},
                    blocking=True, return_response=True,
                )
                for item in (resp or {}).get(weather, {}).get("forecast", []):
                    when = dt_util.parse_datetime(str(item.get("datetime")))
                    t = item.get("temperature")
                    if when is not None and t is not None:
                        points.append((dt_util.as_utc(when), float(t)))
                if points:  # an empty answer keeps the forecast we have
                    self.outdoor.set_forecast(points)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Forecast fetch from %s failed: %s", weather, err)
            if not points:  # try again soon rather than in half an hour
                self._forecast_at = now - timedelta(minutes=FORECAST_REFRESH_MIN - FORECAST_RETRY_MIN)

        # An explicit mean sensor wins; otherwise the internal blend.
        explicit = self._float(self.house_cfg.get(CONF_OUTDOOR_MEAN))
        self.outdoor_mean = explicit if explicit is not None else self.outdoor.day_mean(now)
        self.forecast_min_24h = self.outdoor.forecast_min(now, 24)

    @property
    def away_entities(self) -> list[str]:
        value = self.house_cfg.get(CONF_ALARM) or []
        return [value] if isinstance(value, str) else list(value)

    def _update_away(self) -> None:
        pairs = []
        for eid in self.away_entities:
            st = self.hass.states.get(eid)
            if st is not None:
                pairs.append((eid.split(".", 1)[0], st.state))
        away, why = is_away(pairs)
        if away != self.away:
            self._log(f"Away ({why}): heating off, safety floor only" if away
                      else f"Home again: back to {self.mode.value}")
        self.away, self.away_reason = away, why

    def _one_cycle_step(self, now: datetime, plan: Plan) -> None:
        """One Cycle heats what needs it, then Off. With nothing to heat it waits a few minutes, saying why."""
        if any(d.verdict.value == "approved" for d in plan.rooms.values()):
            self._one_cycle_heated, self.one_cycle_wait = True, None
            return
        if self._one_cycle_heated:
            self._end_one_cycle("rooms reached their targets", plan)
            return
        since = self._one_cycle_since = self._one_cycle_since or now
        until = since + timedelta(minutes=ONE_CYCLE_WAIT_MIN)
        reasons = self._why_nothing(plan)
        if now >= until:
            self._end_one_cycle("nothing needed heat" + (f" ({reasons[0]})" if reasons else ""), plan)
            return
        if self._one_cycle_timer is None:
            self._one_cycle_timer = async_call_later(self.hass, (until - now).total_seconds() + 1, self._one_cycle_due)
        if self.one_cycle_wait is None:
            self._log("One Cycle: nothing needs heat yet" + (f" ({reasons[0]})" if reasons else "")
                      + f". Off in {ONE_CYCLE_WAIT_MIN} min unless something changes")
        self.one_cycle_wait = {"until": until.isoformat(), "reasons": reasons, "all_rooms": self.one_cycle_all}
        plan.reason = "One Cycle: nothing needs heat yet"

    def _end_one_cycle(self, why: str, plan: Plan) -> None:
        manual = [r for r in self.rooms.values() if r.override is Override.HEAT]
        for r in manual:
            r.override, r.override_until = Override.AUTO, None
        self._reset_one_cycle()
        self.mode = Mode.OFF
        self._log(f"One Cycle ended: {why}. Mode set to off")
        plan.reason = f"One Cycle ended: {why}"

    def _why_nothing(self, plan: Plan) -> list[str]:
        """Plain reasons, most useful first, for the card and the log."""
        out: list[str] = []
        s = self.effective_settings

        def names(ids: list[str]) -> str:
            shown = [self.rooms[r].cfg.name for r in ids[:4]]
            return ", ".join(shown) + (f" and {len(ids) - 4} more" if len(ids) > 4 else "")

        if self._season_off and self.outdoor_mean is not None:
            out.append(f"Mild day: outdoor {self.outdoor_mean:.1f}°, season gate {s.season_gate:g}°. "
                       "Only rooms in use, or ones you pick, are heated.")
        if self.away:
            out.append("Away: only rooms you pick with Heat now are heated.")
        near = []
        for rid, d in plan.rooms.items():
            room, t = self.rooms[rid], self.room_temp(self.rooms[rid])
            if d.verdict.value == "idle" and room.occupied and t is not None and d.need.target is not None and d.need.target > s.safety:
                near.append(f"{room.cfg.name} {t:.1f}° (heats at {d.need.target - s.hysteresis:.1f}° or below)")
        if near:
            out.append("In use and warm enough: " + ", ".join(near[:3]))
        empty = [rid for rid, d in plan.rooms.items() if d.verdict.value == "vetoed" and d.reason.endswith("empty room")]
        if empty:
            out.append(f"Empty rooms wait on mild days: {names(empty)}")
        coasting = [rid for rid, d in plan.rooms.items() if d.verdict.value == "deferred"]
        if coasting:
            out.append(f"Warming by itself or waiting: {names(coasting)}")
        return out or ["Every room is at its target."]

    @property
    def effective_mode(self) -> Mode:
        return Mode.OFF if self.away else self.mode

    def _house_snapshot(self, now: datetime) -> HouseSnapshot:
        hw = self._state(self.hw_entity)
        # Control timing follows what we command; without control, follow what fires.
        if self.boiler_control:
            boiler = self._state(self.boiler_entity)
            boiler_on = self._commanded_on(boiler)
        else:
            boiler = self._state(self.house_cfg.get(CONF_BOILER_ON))
            boiler_on = self._boiler_is_on(boiler)
        self._season_off = season_is_off(self._season_off, self.outdoor_mean, self.effective_settings.season_gate, SEASON_GATE_BAND)
        return HouseSnapshot(
            now=now,
            mode=self.mode,
            away=self.away,
            season_off=self._season_off,
            one_cycle_all=self.mode is Mode.ONE_CYCLE and self.one_cycle_all,
            night=self._is_night(now),
            outdoor_mean=self.outdoor_mean,
            hw_calling=bool(hw and hw.state in _ON_STATES),
            hw_calling_min=_minutes(now, hw.last_changed) if hw and hw.state in _ON_STATES else 0.0,
            boiler_on=boiler_on,
            boiler_state_min=_minutes(now, boiler.last_changed) if boiler else 1e9,
        )

    def _room_snapshot(self, room: Room, now: datetime) -> RoomSnapshot:
        if room.override_until and now >= room.override_until:
            room.override, room.override_until = Override.AUTO, None

        temp = self.room_temp(room)
        if temp is not None:
            room.trend.add(now, temp)

        room.occupied = is_occupied(
            now,
            self._signals(room.presence),
            self._signals(room.media),
            self._signals(room.lights),
            room.occupied,
        )
        return RoomSnapshot(
            temp=temp,
            trend=room.trend.rate(),
            occupied=room.occupied,
            scheduled=self._is_on(room.schedule),
            lights_on=any(self._is_on(e) for e in room.lights),
            override=room.override,
            valve_open=self._valve_open(room),
            heater_on=self._heater_on(room) if room.heaters else None,
            prev_calling=room.prev_calling,
            deferred_min=_minutes(now, room.deferred_since) if room.deferred_since else 0.0,
        )

    # ---------- actuation ----------

    async def _locked(self, coro) -> None:
        async with self._apply_lock:
            await coro

    async def _apply(self, plan: Plan) -> None:
        async with self._apply_lock:
            # Open valves before firing; leave valves alone when stopping.
            for room_id, decision in plan.rooms.items():
                if decision.open_valve is None:
                    continue
                room = self.rooms[room_id]
                target = decision.need.target or self.room_comfort(room)
                setpoint = (
                    _clamp(round(target + self.settings.trv_open_offset))
                    if decision.open_valve
                    else _clamp(round(self.settings.trv_closed))
                )
                for trv in room.trvs:
                    st = self.hass.states.get(trv)
                    if st is None or st.state in _BAD:
                        continue
                    current = st.attributes.get("temperature")
                    if current is not None and float(current) == setpoint:
                        continue
                    try:
                        await self.hass.services.async_call(
                            "climate", "set_temperature",
                            {"entity_id": trv, "temperature": setpoint},
                            blocking=True,
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning("TRV %s set %s failed: %s", trv, setpoint, err)
                        self._log(f"TRV {trv} command failed: {err}", room=room.cfg.name)
                    await asyncio.sleep(TRV_STAGGER_S)
            for room_id, decision in plan.rooms.items():
                if decision.heater_on is None:
                    continue
                room = self.rooms[room_id]
                target = decision.need.target or self.room_comfort(room)
                for h in room.heaters:
                    await self._set_heater(h, decision.heater_on, target, room)
            if self.boiler_control:
                targets = [
                    d.need.target for d in plan.rooms.values()
                    if d.verdict.value in ("approved", "piggyback") and d.need.target is not None
                ]
                await self._boiler(plan.boiler_on, max(targets) if targets else None)

    async def _boiler(self, on: bool, target: float | None = None, force: bool = False) -> None:
        """Every boiler command goes through here: protects the boiler from short cycling.

        - never switches within BOILER_GUARD_S of the last change (ours or anyone's)
        - never switches back on while something else has taken over (external hold)
        - too many switches in a short window locks boiler control and notifies
        Turning off for the kill switch (force) is always allowed.
        """
        entity = self.boiler_entity
        if not entity:
            return
        st = self._state(entity)
        if st is None:
            return
        now = dt_util.utcnow()
        is_on = self._commanded_on(st)
        if is_on == on:
            if on and self._setpoint_style and not self._boiler_blocked(now, on):
                await self._boiler_raw(on, target)  # adjust the setpoint only
            return
        if not force and self._boiler_blocked(now, on, st):
            return
        self._boiler_cmds = [t for t in self._boiler_cmds if now - t < timedelta(minutes=BOILER_FLAP_WINDOW_MIN)]
        if not force and len(self._boiler_cmds) >= BOILER_FLAP_MAX:
            self.boiler_locked_until = now + timedelta(minutes=BOILER_LOCK_MIN)
            self._log(f"Boiler protection: {len(self._boiler_cmds)} switches in {BOILER_FLAP_WINDOW_MIN} min, "
                      f"boiler control locked for {BOILER_LOCK_MIN} min")
            self._notify_problem(
                "Boiler protection",
                f"Smart Heating switched the boiler {len(self._boiler_cmds)} times in {BOILER_FLAP_WINDOW_MIN} minutes, "
                f"so it has stopped switching it for {BOILER_LOCK_MIN} minutes. Something else may be switching "
                f"{entity} too (an automation, schedule or hot water priority). Check the log on the card.",
            )
            if not on:
                pass  # off is the safe direction: still allowed below
            else:
                return
        self._boiler_cmds.append(now)
        self._boiler_cmd_state, self._boiler_cmd_at = on, now
        await self._boiler_raw(on, target)

    def _boiler_blocked(self, now: datetime, on: bool, st: State | None = None) -> bool:
        if on and self.boiler_locked_until and now < self.boiler_locked_until:
            return True
        if on and self.external_hold_until and now < self.external_hold_until:
            return True
        last = self._boiler_cmd_at
        if st is not None and (last is None or st.last_changed > last):
            last = st.last_changed
        return last is not None and (now - last).total_seconds() < BOILER_GUARD_S

    def _notify_problem(self, title: str, message: str) -> None:
        persistent_notification.async_create(self.hass, message, title=title, notification_id=f"{DOMAIN}_problem")
        if self.notify_service and "." in self.notify_service:
            domain, service = self.notify_service.split(".", 1)
            self.hass.async_create_task(self.hass.services.async_call(domain, service, {"title": title, "message": message}))

    def _check_external_boiler(self, now: datetime) -> None:
        """Did something else switch the boiler since our last command? Then back off, never fight."""
        if not self.boiler_control or self._boiler_cmd_state is None or self._boiler_cmd_at is None:
            return
        if self.monitor_only and not self.heat_test:
            self._boiler_cmd_state = None  # watching only: others own the boiler
            return
        st = self._state(self.boiler_entity)
        if st is None:
            return
        actual = self._commanded_on(st)
        if actual == self._boiler_cmd_state:
            return
        if (now - self._boiler_cmd_at).total_seconds() < 5:
            return  # our own command still settling
        self._boiler_cmd_state = actual
        hw = self.settings.hw_priority and self._is_on(self.hw_entity)
        self.external_hold_until = now + timedelta(minutes=EXTERNAL_HOLD_MIN)
        who = "hot water priority" if hw else "something else"
        self._log(f"Boiler switched {'on' if actual else 'off'} by {who}: Smart Heating backs off for {EXTERNAL_HOLD_MIN} min")
        if self.heat_test and not actual and not hw:
            self.hass.async_create_task(self._locked(self._finish_heat_test("stopped: the heating was switched off by something else")))
            self._notify_problem(
                "Heat test stopped",
                f"{self.boiler_entity} was switched off by something else during the heat test (an automation, schedule "
                "or thermostat?). Smart Heating stopped the test instead of fighting it. Pause that automation and run "
                "the test again from the card.",
            )

    async def _boiler_raw(self, on: bool, target: float | None = None) -> None:
        entity = self.boiler_entity
        if not entity:
            return
        st = self.hass.states.get(entity)
        if st is None or st.state in _BAD:
            return
        domain = entity.split(".", 1)[0]
        if domain == "climate" and self._setpoint_style:
            # The thermostat regulates: give it the target, or the frost floor when off.
            want = target if on and target else (25.0 if on else self.effective_settings.safety)
            if on:
                # Make sure it fires even if the thermostat's own room is already warm (other zones calling).
                try:
                    own = float(st.attributes.get("current_temperature"))
                    want = max(want, own + 1.0)
                except (TypeError, ValueError):
                    pass
                want = min(want, 25.0)
            want = round(want * 2) / 2
            try:
                current = float(st.attributes.get("temperature") or 0)
            except (TypeError, ValueError):
                current = 0.0
            if st.state != "off" and abs(current - want) < 0.25:
                return
            await self.hass.services.async_call(
                "climate", "set_temperature", {"entity_id": entity, "temperature": want, "hvac_mode": "heat"}, blocking=True
            )
            return
        if domain == "climate":
            # A smart thermostat acting as the boiler control: heat at 25, or off.
            try:
                setpoint = float(st.attributes.get("temperature") or 0)
            except (TypeError, ValueError):
                setpoint = 0.0
            is_on = st.state != "off" and setpoint >= 25
            if is_on == on:
                return
            if on:
                await self.hass.services.async_call(
                    "climate", "set_temperature",
                    {"entity_id": entity, "temperature": 25, "hvac_mode": "heat"}, blocking=True,
                )
            else:
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode", {"entity_id": entity, "hvac_mode": "off"}, blocking=True
                )
            return
        if (st.state == STATE_ON) == on:
            return
        await self.hass.services.async_call(
            domain if domain in ("switch", "input_boolean") else "homeassistant",
            "turn_on" if on else "turn_off", {"entity_id": entity}, blocking=True,
        )

    def _is_night(self, now: datetime) -> bool:
        """Night schedule entity if configured, otherwise the night start/end times."""
        entity = self.house_cfg.get(CONF_NIGHT_SCHEDULE)
        if entity and self._state(entity) is not None:
            return self._is_on(entity)
        t = dt_util.as_local(now).time()
        start, end = self.night_start, self.night_end
        if start <= end:
            return start <= t < end
        return t >= start or t < end

    def _commanded_on(self, st: State | None) -> bool:
        """Is the boiler control currently set to call for heat?"""
        if st is None:
            return False
        if st.domain == "climate":
            try:
                temp = float(st.attributes.get("temperature") or 0)
            except (TypeError, ValueError):
                return False
            if self._setpoint_style:
                return st.state != "off" and temp > self.effective_settings.safety + 0.25
            return st.state != "off" and temp >= 25
        return st.state == STATE_ON

    @property
    def _is_thermostat(self) -> bool:
        return bool(self.boiler_entity and self.boiler_entity.startswith("climate."))

    @property
    def _setpoint_style(self) -> bool:
        return self._is_thermostat and self.thermostat_style == STYLE_SETPOINT

    def _heating_demand(self) -> bool:
        """Is the heating circuit asking for heat (zone valve / thermostat calling)?"""
        if not self.boiler_control:
            return True  # unknown: assume anything that fires heats the radiators
        st = self._state(self.boiler_entity)
        if self._setpoint_style:
            return self._boiler_is_on(st)
        return self._commanded_on(st)

    def _radiators_heating(self, now: datetime) -> tuple[bool, float]:
        """Are the radiators actually getting heat, and for how long in that state.

        Burns for hot water only don't count: an S/Y-plan cylinder with the heating valve shut,
        or a combi running a tap, leaves the radiators cooling.
        """
        firing, firing_min = self._firing(now)
        hw = self._is_on(self.hw_entity)
        delivering = firing and self._heating_demand() and not (self.hw_system == HW_COMBI and hw)
        if self._delivering is None:
            self._delivering, self._delivering_since = delivering, now - timedelta(minutes=min(firing_min, 1e6))
        elif delivering != self._delivering:
            self._delivering, self._delivering_since = delivering, now
        return delivering, _minutes(now, self._delivering_since)

    def _firing(self, now: datetime) -> tuple[bool, float]:
        """Is the boiler actually running (for gas and learning), and for how long in that state."""
        st = self._state(self.house_cfg.get(CONF_BOILER_ON)) or self._state(self.boiler_entity)
        if st is None:
            return False, 1e9
        return self._boiler_is_on(st), _minutes(now, st.last_changed)

    def _boiler_is_on(self, st: State | None) -> bool:
        if st is None:
            return False
        if st.domain == "climate":
            action = st.attributes.get("hvac_action")
            return action == "heating" if action is not None else st.state == "heat"
        return st.state == STATE_ON

    def room_temp(self, room: Room) -> float | None:
        """Room thermometer, or the mean of its TRVs' own readings as a fallback."""
        if room.temp_entity:
            v = self._float(room.temp_entity)
            # A room can't be below -10 or above 40: that's a wrong sensor (device internal temperature).
            return v if v is not None and -10.0 <= v <= 40.0 else None
        vals = []
        for trv in [*room.trvs, *(h for h in room.heaters if h.startswith("climate."))]:
            st = self._state(trv)
            t = st.attributes.get("current_temperature") if st else None
            if t is not None:
                try:
                    vals.append(float(t))
                except (TypeError, ValueError):
                    pass
        return round(sum(vals) / len(vals), 2) if vals else None

    # ---------- helpers ----------

    def _state(self, entity_id: str | None) -> State | None:
        if not entity_id:
            return None
        st = self.hass.states.get(entity_id)
        if st is None or st.state in _BAD:
            return None
        return st

    def _float(self, entity_id: str | None) -> float | None:
        st = self._state(entity_id)
        if st is None:
            return None
        try:
            return float(st.state)
        except ValueError:
            return None

    def _is_on(self, entity_id: str | None) -> bool:
        st = self._state(entity_id)
        return bool(st and st.state in _ON_STATES)

    def _signals(self, entity_ids: list[str]) -> list[Signal]:
        out = []
        for e in entity_ids:
            st = self._state(e)
            if st is not None:
                out.append(Signal(st.state in _ON_STATES, st.last_changed))
        return out

    def _valve_open(self, room: Room) -> bool | None:
        states = []
        for trv in room.trvs:
            st = self._state(trv)
            t = st.attributes.get("temperature") if st else None
            if t is None:
                return None
            states.append(float(t) > self.settings.trv_closed + 0.5)
        if not states or len(set(states)) > 1:
            return None
        return states[0]


def _parse_time(value: str):
    from datetime import time as _t

    try:
        parts = [int(x) for x in str(value).split(":")[:2]]
        return _t(parts[0], parts[1] if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        return _t(22, 0)


def _minutes(now: datetime, then: datetime | None) -> float:
    if then is None:
        return 1e9
    return (now - then).total_seconds() / 60


def _clamp(v: float) -> int:
    return int(min(30, max(5, v)))
