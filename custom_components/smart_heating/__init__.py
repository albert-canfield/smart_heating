"""Smart Heating: two-voice room heating controller."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS, SERVICE_HEAT_TEST, SERVICE_RELEARN, SERVICE_START_CONTROL, VERSION
from .coordinator import HeatingCoordinator

_LOGGER = logging.getLogger(__name__)
CARD_URL = f"/{DOMAIN}/smart-heating-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "smart-heating-card.js"

type SmartHeatingConfigEntry = ConfigEntry[HeatingCoordinator]


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the dashboard card from the integration and load it on every dashboard."""
    if hass.data.get(f"{DOMAIN}_card"):
        return
    hass.data[f"{DOMAIN}_card"] = True
    try:
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_FILE), True)])
        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not register the Smart Heating card automatically: %s", err)


def _coordinators(hass: HomeAssistant) -> list[HeatingCoordinator]:
    return [
        e.runtime_data for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if isinstance(getattr(e, "runtime_data", None), HeatingCoordinator)
    ]


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_HEAT_TEST):
        return

    async def heat_test(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_heat_test(call.data.get("start", True), call.data.get("ignore_automations", False))

    async def start_control(call: ServiceCall) -> None:
        for c in _coordinators(hass):
            await c.async_start_control()

    async def relearn(call: ServiceCall) -> None:
        wanted = {n.strip().lower() for n in call.data["rooms"]}
        for c in _coordinators(hass):
            ids = [rid for rid, r in c.rooms.items() if r.cfg.name.lower() in wanted]
            if len(ids) < len(wanted):
                known = ", ".join(sorted(r.cfg.name for r in c.rooms.values()))
                raise HomeAssistantError(f"Unknown room name. Rooms: {known}")
            await c.async_relearn(ids)

    hass.services.async_register(DOMAIN, SERVICE_HEAT_TEST, heat_test, vol.Schema({vol.Optional("start", default=True): cv.boolean, vol.Optional("ignore_automations", default=False): cv.boolean}))
    # skip_calibration is accepted for old automations; control no longer waits for calibration.
    hass.services.async_register(DOMAIN, SERVICE_START_CONTROL, start_control, vol.Schema({vol.Optional("skip_calibration"): cv.boolean}))
    hass.services.async_register(DOMAIN, SERVICE_RELEARN, relearn, vol.Schema({vol.Required("rooms"): vol.All(cv.ensure_list, [cv.string])}))


async def async_setup_entry(hass: HomeAssistant, entry: SmartHeatingConfigEntry) -> bool:
    await _async_register_card(hass)
    _async_register_services(hass)
    coordinator = HeatingCoordinator(hass, entry)
    await coordinator.async_start()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartHeatingConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok


async def _async_reload(hass: HomeAssistant, entry: SmartHeatingConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
