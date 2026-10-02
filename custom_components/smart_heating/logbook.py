"""Describe Smart Heating decisions in the Home Assistant Logbook."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_DECISION


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    @callback
    def describe(event: Event) -> dict[str, str]:
        room = event.data.get("room")
        return {
            LOGBOOK_ENTRY_NAME: f"Smart Heating: {room}" if room else "Smart Heating",
            LOGBOOK_ENTRY_MESSAGE: event.data.get("message", ""),
        }

    async_describe_event(DOMAIN, EVENT_DECISION, describe)
