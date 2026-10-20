"""Dashboard card loading.

The integration serves the card itself (/smart_heating/smart-heating-card.js) and keeps one
dashboard resource pointing at it, updated to the new version after each update, so every
dashboard loads it. The same URL is also added as an extra module, so the browser fetches it
once, as early as possible. Nothing is written to the user's www folder.

Releases 0.14.1 to 0.15.3 served the card from /local/smart_heating/ (a copy in www): their
resource is found by its file name and pointed back here; the old copy is the user's to delete.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

NAME = "smart-heating-card.js"
SOURCE = Path(__file__).parent / "frontend" / NAME
OWN_URL = f"/{DOMAIN}/{NAME}"
_DONE = f"{DOMAIN}_card"
_PATH = f"{DOMAIN}_card_path"
_URL = f"{DOMAIN}_card_url"


def _resources(hass: HomeAssistant) -> Any:
    """The dashboard resources collection, or None when resources are kept in YAML."""
    res = getattr(hass.data.get("lovelace"), "resources", None)
    return res if hasattr(res, "async_create_item") else None


async def _ours(res: Any) -> list[dict]:
    if not getattr(res, "loaded", True):
        await res.async_load()
        res.loaded = True
    return [r for r in res.async_items() if str(r.get("url", "")).split("?")[0].endswith(f"/{NAME}")]


async def sync_resource(res: Any, url: str) -> None:
    """Keep exactly one dashboard resource for the card, at url."""
    first, *extra = await _ours(res) or [None]
    if first is None:
        await res.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Added the Smart Heating card to dashboard resources: %s", url)
    elif first.get("url") != url or first.get("type") != "module":
        await res.async_update_item(first["id"], {"res_type": "module", "url": url})
    for r in extra:
        await res.async_delete_item(r["id"])


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and load it on every dashboard."""
    if hass.data.get(_DONE):
        return
    hass.data[_DONE] = True
    try:
        if not hass.data.get(_PATH):
            await hass.http.async_register_static_paths([StaticPathConfig(OWN_URL, str(SOURCE), True)])
            hass.data[_PATH] = True
    except Exception as err:  # noqa: BLE001
        hass.data[_DONE] = False  # try again on the next set-up
        _LOGGER.warning("Could not serve the Smart Heating card: %s", err)
        return
    url = f"{OWN_URL}?v={VERSION}"
    try:
        if (res := _resources(hass)) is not None:
            await sync_resource(res, url)
        else:
            _LOGGER.info("Dashboard resources are in YAML: add %s (type module) to load the card on every dashboard", url)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not add the Smart Heating card to dashboard resources: %s", err)
    try:
        add_extra_js_url(hass, url)
        hass.data[_URL] = url
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not load the Smart Heating card on every page: %s", err)


async def async_remove_card(hass: HomeAssistant) -> None:
    """Undo async_register_card when the last Smart Heating entry is deleted. Never raises."""
    hass.data[_DONE] = False
    try:
        if url := hass.data.pop(_URL, None):
            remove_extra_js_url(hass, url)
        if (res := _resources(hass)) is not None:
            for r in await _ours(res):
                await res.async_delete_item(r["id"])
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not remove the Smart Heating card: %s", err)
