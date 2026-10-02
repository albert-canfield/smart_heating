"""Shared set-up for the smoke tests (needs the homeassistant package)."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util

# Midday on a winter weekday, so day/night rules don't depend on when the tests run.
PINNED = datetime(2026, 1, 14, 12, 0, tzinfo=ZoneInfo("Europe/London"))


def pin_clock() -> None:
    """Move HA's clocks to PINNED, still ticking.

    HA stamps states with time.time() and the integration reads dt_util.utcnow(),
    so both are shifted by the same offset. Call before importing other HA modules:
    some of them do `from homeassistant.util.dt import utcnow`.
    """
    offset = PINNED.timestamp() - time.time()
    real_time = time.time
    time.time = lambda: real_time() + offset
    dt_util.utcnow = lambda: dt_util.utc_from_timestamp(time.time())
    dt_util.now = lambda time_zone=None: dt_util.utcnow().astimezone(time_zone or dt_util.get_default_time_zone())


async def load_registries(hass) -> None:
    """Floor, area, device and entity registries. HA 2026.9+ needs async_setup first where it exists."""
    from homeassistant.helpers import (
        area_registry,
        device_registry,
        entity_registry,
        floor_registry,
    )

    for m in (floor_registry, area_registry, device_registry, entity_registry):
        if hasattr(m, "async_setup"):
            m.async_setup(hass)
        await m.async_load(hass)
