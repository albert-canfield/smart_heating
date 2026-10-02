"""Diagnostics download: full controller state for debugging."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    c = entry.runtime_data
    plan = c.data
    rooms = {}
    for rid, room in c.rooms.items():
        d = plan.rooms.get(rid) if plan else None
        m = room.model
        rooms[room.cfg.name] = {
            "config": {
                "floor": room.cfg.floor,
                "priority": room.cfg.priority.value,
                "comfort": room.cfg.comfort,
                "temperature_sensor": room.temp_entity,
                "trvs": room.trvs,
                "presence": room.presence,
                "lights": room.lights,
                "media": room.media,
                "schedule": room.schedule,
            },
            "live": {
                "temperature": c.room_temp(room),
                "trend": room.trend.rate(),
                "occupied": room.occupied,
                "override": room.override.value,
                "prev_calling": room.prev_calling,
            },
            "decision": {
                "level": d.need.level.value,
                "target": d.need.target,
                "deficit": d.need.deficit,
                "calling": d.need.calling,
                "verdict": d.verdict.value,
                "reason": d.reason,
                "valve_command": d.open_valve,
            } if d else None,
            "model": {
                "tau_h": m.tau,
                "free_gain": m.gain,
                "warmup_c_per_h": m.warmup,
                "progress": m.progress,
                "complete": m.complete,
                "samples_free": m.free.n,
                "samples_heating": m.heat_n,
                "x_spread": round(m.free.spread, 2),
            },
        }
    return {
        "capabilities": c.capabilities,
        "setpoints": c.setpoints.to_dict(),
        "heat_test": c.heat_test,
        "calibration": c.calibration_info,
        "mode": c.mode.value,
        "enabled": c.enabled,
        "monitor_only": c.monitor_only,
        "calibrated": c.calibrated,
        "calibration_progress": c.calibration_progress,
        "settings": asdict(c.settings),
        "house_config": dict(entry.data),
        "plan": {
            "status": plan.status,
            "reason": plan.reason,
            "boiler_on": plan.boiler_on,
            "open_rooms": plan.open_rooms,
            "close_rooms": plan.close_rooms,
        } if plan else None,
        "climate": {
            "house_temp": c.house_temp,
            "floor_temps": c.floor_temps,
            "outdoor_mean": c.outdoor_mean,
            "forecast_min_24h": c.forecast_min_24h,
            "forecast_points": len(c.outdoor.forecast),
        },
        "gas": {
            "source": c.gas_source,
            "kwh_today": c.gas_kwh,
            "measured": c.gas_measured,
            "price_per_kwh": c.gas_price_now,
            "price_from": c.gas_price_from,
            "cost_today": c.gas_cost,
            "kwh_per_degree_day": c.kwh_per_dd,
            "energy_day": c.energy.to_dict(),
        },
        "rooms": rooms,
        "log": list(c.log),
    }
