"""Selects: house mode and per-room override."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .core import Mode, Override
from .entity import HouseEntity, RoomEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([ModeSelect(c)])
    for room_id in c.rooms:
        async_add_entities([OverrideSelect(c, room_id)], config_subentry_id=room_id)


class ModeSelect(HouseEntity, SelectEntity, RestoreEntity):
    _attr_options = [m.value for m in Mode]

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "mode")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        # A new setup ignores what an earlier one with the same entity id left behind.
        if last and last.state in self._attr_options and not self.coordinator.fresh:
            await self.coordinator.async_set_mode(Mode(last.state), restoring=True)

    @property
    def current_option(self) -> str:
        return self.coordinator.mode.value

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_mode(Mode(option))
        self.async_write_ha_state()


class OverrideSelect(RoomEntity, SelectEntity):
    _attr_options = [o.value for o in Override]

    def __init__(self, coordinator, room_id: str) -> None:
        super().__init__(coordinator, room_id, "override")

    @property
    def current_option(self) -> str:
        return self.coordinator.rooms[self.room_id].override.value

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_override(self.room_id, Override(option))
        self.async_write_ha_state()
