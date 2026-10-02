"""Base entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HeatingCoordinator


class HouseEntity(CoordinatorEntity[HeatingCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HeatingCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)}, name="Smart Heating", manufacturer="Smart Heating"
        )


class RoomEntity(CoordinatorEntity[HeatingCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HeatingCoordinator, room_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.room_id = room_id
        room = coordinator.rooms[room_id]
        self._attr_unique_id = f"{room_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, room_id)},
            name=room.cfg.name,
            manufacturer="Smart Heating",
            model="Room",
            via_device=(DOMAIN, coordinator.entry.entry_id),
            suggested_area=room.cfg.name if room.area_id else None,
        )

    @property
    def decision(self):
        plan = self.coordinator.data
        return plan.rooms.get(self.room_id) if plan else None
