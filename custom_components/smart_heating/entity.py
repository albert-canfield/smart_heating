"""Base entities."""
from __future__ import annotations

import inspect
from typing import Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HeatingCoordinator

HOUSE_DEVICE = {"name": "Smart Heating", "manufacturer": "Smart Heating"}
# HA 2026.8+ links devices by registry id (via_device is removed in 2027.8); 2026.2 only has via_device.
_VIA_ID = "via_device_id" in inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters


def _via_house(coordinator: HeatingCoordinator) -> dict[str, Any]:
    """Link a room's device to the house device."""
    entry_id = coordinator.entry.entry_id
    if _VIA_ID:
        try:
            house = dr.async_get(coordinator.hass).async_get_or_create(
                config_entry_id=entry_id, identifiers={(DOMAIN, entry_id)}, **HOUSE_DEVICE
            )
            return {"via_device_id": house.id}
        except Exception:  # noqa: BLE001
            pass  # entry not registered (tests): the old form still works until 2027.8
    return {"via_device": (DOMAIN, entry_id)}


class HouseEntity(CoordinatorEntity[HeatingCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HeatingCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)}, **HOUSE_DEVICE)


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
            **_via_house(coordinator),
            suggested_area=room.cfg.name if room.area_id else None,
        )

    @property
    def decision(self):
        plan = self.coordinator.data
        return plan.rooms.get(self.room_id) if plan else None
