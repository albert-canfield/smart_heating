"""Binary sensors: boiler demand and room occupancy."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import HouseEntity, RoomEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([BoilerDemand(c), Calibrated(c)])
    for room_id in c.rooms:
        async_add_entities([RoomOccupied(c, room_id)], config_subentry_id=room_id)


class BoilerDemand(HouseEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "boiler_demand")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.boiler_on if self.coordinator.data else None


class RoomOccupied(RoomEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator, room_id: str) -> None:
        super().__init__(coordinator, room_id, "occupied")

    @property
    def is_on(self) -> bool:
        return self.coordinator.rooms[self.room_id].occupied


class Calibrated(HouseEntity, BinarySensorEntity):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "calibrated")

    @property
    def is_on(self) -> bool:
        return self.coordinator.calibrated

    @property
    def extra_state_attributes(self):
        return {"kind": "calibrated", "progress": round(self.coordinator.calibration_progress * 100)}
