"""Numbers: house target and per-room target (comfort when in use)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SETPOINT_MAX, SETPOINT_MIN, SETPOINT_STEP
from .entity import HouseEntity, RoomEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([HouseTarget(c)])
    for room_id in c.rooms:
        async_add_entities([RoomTarget(c, room_id)], config_subentry_id=room_id)


class _Target(NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = SETPOINT_MIN
    _attr_native_max_value = SETPOINT_MAX
    _attr_native_step = SETPOINT_STEP
    _attr_mode = NumberMode.BOX


class HouseTarget(HouseEntity, _Target):
    """Shifts every room's comfort and the baselines together."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "house_target")

    @property
    def native_value(self) -> float:
        return self.coordinator.setpoints.house

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        s = c.effective_settings
        return {
            "kind": "house_target",
            "offset": c.setpoints.offset,
            "baseline_day": s.baseline_day,
            "baseline_night": s.baseline_night,
            "safety": s.safety,
        }

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_house_target(value)
        self.async_write_ha_state()


class RoomTarget(RoomEntity, _Target):
    """The room's target while in use. Keeps its difference when the house target moves."""

    def __init__(self, coordinator, room_id: str) -> None:
        super().__init__(coordinator, room_id, "target")

    @property
    def native_value(self) -> float:
        return self.coordinator.room_comfort(self.coordinator.rooms[self.room_id])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        cfg = c.rooms[self.room_id].cfg
        return {
            "kind": "room_target",
            "vs_house": round(c.room_comfort(c.rooms[self.room_id]) - c.setpoints.house, 2),
            "custom": c.setpoints.is_custom(cfg),
        }

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_room_target(self.room_id, value)
        self.async_write_ha_state()
