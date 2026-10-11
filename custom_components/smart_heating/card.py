"""Dashboard card loading.

HA serves dashboards from the first seconds of start-up, but custom integrations set up
minutes later, and the frontend only reads extra scripts when a page loads. A page opened
in between never got the card ("Configuration error" until a full reload). So the card is
copied to config/www (served by HA from the start, as /local) with a .gz next to it, and
kept as a dashboard resource, which every dashboard loads from storage. The same URL is
also added as an extra module, so the browser fetches it once, as early as possible.
"""
from __future__ import annotations

import gzip
import logging
import os
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

NAME = "smart-heating-card.js"
SOURCE = Path(__file__).parent / "frontend" / NAME
OWN_URL = f"/{DOMAIN}/{NAME}"  # served by the integration once it is set up
LOCAL_URL = f"/local/{DOMAIN}/{NAME}"  # served by HA from config/www from the start
_DONE = f"{DOMAIN}_card"
_PATH = f"{DOMAIN}_card_path"
_URL = f"{DOMAIN}_card_url"


def _write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def copy_to_www(www: Path) -> None:
    """Copy the card and a gzip of it (HA sends that to browsers that accept it), when changed."""
    data = SOURCE.read_bytes()
    folder = www / DOMAIN
    folder.mkdir(parents=True, exist_ok=True)
    js, gz = folder / NAME, folder / f"{NAME}.gz"
    try:
        if js.read_bytes() == data and gzip.decompress(gz.read_bytes()) == data:
            return
    except (OSError, EOFError, gzip.BadGzipFile):
        pass
    _write(gz, gzip.compress(data, mtime=0))  # the .gz first: it is what browsers get
    _write(js, data)


def remove_from_www(www: Path) -> None:
    folder = www / DOMAIN
    for f in (folder / NAME, folder / f"{NAME}.gz"):
        f.unlink(missing_ok=True)
    try:
        folder.rmdir()
    except OSError:
        pass  # missing, or holds something else


def local_served(hass: HomeAssistant) -> bool:
    """HA serves config/www at /local only if the folder existed when it started."""
    return any(getattr(r, "canonical", None) == "/local" for r in hass.http.app.router.resources())


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
    """Load the card on every dashboard, also on pages opened while HA is still starting."""
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
        await hass.async_add_executor_job(copy_to_www, Path(hass.config.path("www")))
        if local_served(hass):
            url = f"{LOCAL_URL}?v={VERSION}"
        else:
            _LOGGER.info("The www folder is new: the Smart Heating card loads from %s until Home Assistant restarts", OWN_URL)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not copy the Smart Heating card to www, it loads from %s: %s", OWN_URL, err)
    try:
        if (res := _resources(hass)) is not None:
            await sync_resource(res, url)
        else:
            _LOGGER.info("Dashboard resources are in YAML: add %s (type module) so the card also loads while Home Assistant starts", url)
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
        await hass.async_add_executor_job(remove_from_www, Path(hass.config.path("www")))
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not remove the Smart Heating card: %s", err)
