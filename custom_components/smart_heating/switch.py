"""Switches: controller enabled (kill switch) and monitor-only."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import HouseEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([EnabledSwitch(c), MonitorOnlySwitch(c)])


class _RestoredSwitch(HouseEntity, SwitchEntity, RestoreEntity):
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in (STATE_ON, STATE_OFF):
            await self._set(last.state == STATE_ON, restoring=True)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
        self.async_write_ha_state()

    async def _set(self, value: bool, restoring: bool = False) -> None:
        raise NotImplementedError


class EnabledSwitch(_RestoredSwitch):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "enabled")

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def _set(self, value: bool, restoring: bool = False) -> None:
        await self.coordinator.async_set_enabled(value)


class MonitorOnlySwitch(_RestoredSwitch):
    """On = decide and log only, never touch the boiler or TRVs."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "monitor_only")

    @property
    def is_on(self) -> bool:
        return self.coordinator.monitor_only

    async def _set(self, value: bool, restoring: bool = False) -> None:
        await self.coordinator.async_set_monitor_only(value, restoring)
