"""Voice 2: is it worth burning gas now? Produces the plan."""
from __future__ import annotations

from .models import (
    HouseSnapshot,
    Level,
    Mode,
    Plan,
    Priority,
    RoomConfig,
    RoomDecision,
    RoomSnapshot,
    Settings,
    Verdict,
)
from .need import evaluate_need


def make_plan(
    rooms: list[tuple[RoomConfig, RoomSnapshot]],
    house: HouseSnapshot,
    s: Settings,
    boiler_control: bool = True,
) -> Plan:
    """Build the plan.

    boiler_control=False is valve-only: the boiler is driven by something else
    (its own thermostat, or a TRV system that fires it on demand). Boiler timing
    and hot water priority don't apply, and valves map directly to demand.
    """
    decisions: dict[str, RoomDecision] = {}
    valid = [cfg for cfg, snap in rooms if snap.temp is not None]

    # Voice 1 for every room.
    needs = {cfg.room_id: evaluate_need(cfg, snap, house, s) for cfg, snap in rooms}

    if rooms and not valid:
        for cfg, _ in rooms:
            decisions[cfg.room_id] = RoomDecision(
                cfg.room_id, needs[cfg.room_id], Verdict.FAULT, "no valid sensors"
            )
        return Plan(False, decisions, "fault", "all room sensors unavailable")

    # Voice 2, per room.
    approved: list[tuple[RoomConfig, RoomSnapshot]] = []
    season_off = (
        house.outdoor_mean is not None and house.outdoor_mean >= s.season_gate
    )
    for cfg, snap in rooms:
        need = needs[cfg.room_id]
        if snap.temp is None:
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.FAULT, need.reason)
            continue
        if not need.calling:
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.IDLE, need.reason)
            continue
        if need.level is Level.SAFETY:
            approved.append((cfg, snap))
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.APPROVED, "safety")
            continue
        if season_off:
            decisions[cfg.room_id] = RoomDecision(
                cfg.room_id, need, Verdict.VETOED,
                f"outdoor mean {house.outdoor_mean:.1f} >= {s.season_gate:.0f}",
            )
            continue
        heating_this_room = bool((house.boiler_on and snap.valve_open and cfg.radiator) or snap.heater_on)
        if not heating_this_room and _coasting(snap, need.deficit, s):
            decisions[cfg.room_id] = RoomDecision(
                cfg.room_id, need, Verdict.DEFERRED, f"coasting {snap.trend:+.2f}/h"
            )
            continue
        approved.append((cfg, snap))
        decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.APPROVED, need.reason)

    # Stack: upper rooms with a small deficit wait while a lower floor heats.
    lower_active = [c.floor for c, _ in approved]
    if lower_active:
        lowest = min(lower_active)
        keep = []
        for cfg, snap in approved:
            need = needs[cfg.room_id]
            if (
                cfg.floor > lowest
                and need.level is not Level.SAFETY
                and need.deficit < s.stack_small_deficit
                and snap.deferred_min < s.stack_max_wait_min
            ):
                decisions[cfg.room_id] = RoomDecision(
                    cfg.room_id, need, Verdict.DEFERRED, "heat rising from below"
                )
            else:
                keep.append((cfg, snap))
        approved = keep

    # Electric heaters: rooms without a boiler radiator heat on their own heater.
    heater_ids = {c.room_id for c, _ in approved if c.heater and not c.radiator}
    approved = [(c, sn) for c, sn in approved if c.room_id not in heater_ids]
    # Hybrid: don't fire the whole boiler for one room that has its own heater.
    if (
        boiler_control and len(approved) == 1 and approved[0][0].heater and not house.boiler_on
        and needs[approved[0][0].room_id].level is not Level.SAFETY
    ):
        rid = approved[0][0].room_id
        heater_ids.add(rid)
        decisions[rid] = RoomDecision(rid, needs[rid], Verdict.APPROVED, "electric heater, instead of firing the boiler for one room")
        approved = []

    # Batching: don't fire for a single small low-priority deficit.
    if approved and not house.boiler_on and all(
        c.priority is Priority.C and needs[c.room_id].deficit < s.batch_min_deficit
        and needs[c.room_id].level is not Level.SAFETY
        for c, _ in approved
    ):
        for cfg, _ in approved:
            decisions[cfg.room_id] = RoomDecision(
                cfg.room_id, needs[cfg.room_id], Verdict.DEFERRED, "batching small demand"
            )
        approved = []

    any_safety = any(needs[c.room_id].level is Level.SAFETY for c, _ in approved)
    want_on = bool(approved)
    status, reason = ("heating", f"{len(approved)} room(s) approved") if want_on else ("idle", "no approved demand")

    if not boiler_control:
        plan = _valve_only(rooms, approved, decisions, house, want_on, status, reason, s)
        return _heaters(rooms, plan, heater_ids, house)

    # Hot water priority (never blocks safety).
    if want_on and s.hw_priority and house.hw_calling and not any_safety:
        if house.hw_calling_min < s.hw_max_pause_min:
            want_on, status, reason = False, "paused", "hot water priority"

    # Boiler min off / min run.
    if want_on and not house.boiler_on and house.boiler_state_min < s.min_off_min and not any_safety:
        want_on, status, reason = False, "waiting", "boiler min off time"
    hold = False
    if not want_on and house.boiler_on and house.boiler_state_min < s.min_run_min and status not in ("paused",):
        want_on, status, reason, hold = True, "heating", "boiler min run time", True

    if house.mode is Mode.OFF and not any_safety:
        want_on, status, reason, hold = False, "off", "mode off", False

    # Valves (lazy): only move when the boiler will run, never during a min-run hold.
    if want_on and not hold:
        open_ids = {c.room_id for c, _ in approved}
        # Piggyback: below target but not yet calling, and eligible for comfort/baseline.
        for cfg, snap in rooms:
            d = decisions[cfg.room_id]
            if (
                cfg.room_id not in open_ids
                and d.verdict is Verdict.IDLE
                and _tops_up(snap, d.need.target, s)
                and house.mode is not Mode.OFF
            ):
                open_ids.add(cfg.room_id)
                decisions[cfg.room_id] = RoomDecision(
                    cfg.room_id, d.need, Verdict.PIGGYBACK, "topping up while boiler runs"
                )
        for cfg, snap in rooms:
            if not cfg.has_trv:
                continue
            d = decisions[cfg.room_id]
            should_open = cfg.room_id in open_ids
            if snap.valve_open is None or snap.valve_open != should_open:
                d.open_valve = should_open

    return _heaters(rooms, Plan(want_on, decisions, status, reason), heater_ids, house)


def _heaters(rooms, plan: Plan, heater_ids: set[str], house: HouseSnapshot) -> Plan:
    """Switch electric heaters: on for rooms assigned to them, off for every other heater room."""
    on_any = False
    for cfg, _ in rooms:
        if not cfg.heater:
            continue
        d = plan.rooms[cfg.room_id]
        on = cfg.room_id in heater_ids and (house.mode is not Mode.OFF or d.need.level is Level.SAFETY)
        d.heater_on = on
        on_any = on_any or on
    if on_any and plan.status in ("idle", "off"):
        n = len(plan.heater_rooms)
        plan.status, plan.reason = "heating", f"{n} electric heater room(s)"
    return plan


def _valve_only(rooms, approved, decisions, house: HouseSnapshot, want_on: bool, status: str, reason: str, s: Settings) -> Plan:
    any_safety = any(decisions[c.room_id].need.level is Level.SAFETY for c, _ in approved)
    if house.mode is Mode.OFF and not any_safety:
        approved, want_on, status, reason = [], False, "off", "mode off"
    open_ids = {c.room_id for c, _ in approved}
    if house.boiler_on and house.mode is not Mode.OFF:
        # Known to be firing anyway: let near-target rooms top up.
        for cfg, snap in rooms:
            d = decisions[cfg.room_id]
            if cfg.room_id not in open_ids and d.verdict is Verdict.IDLE and _tops_up(snap, d.need.target, s):
                open_ids.add(cfg.room_id)
                decisions[cfg.room_id] = RoomDecision(cfg.room_id, d.need, Verdict.PIGGYBACK, "topping up while boiler runs")
    for cfg, snap in rooms:
        if not cfg.has_trv:
            continue
        should_open = cfg.room_id in open_ids
        if snap.valve_open is None or snap.valve_open != should_open:
            decisions[cfg.room_id].open_valve = should_open
    return Plan(want_on, decisions, status, reason)


def _tops_up(snap: RoomSnapshot, target: float | None, s: Settings) -> bool:
    """Top up while the boiler runs anyway. Starts half the hysteresis below target and, once the
    valve is open, carries on to target + overshoot, so a room sitting at its target doesn't open
    and close its valve every minute."""
    if snap.temp is None or target is None:
        return False
    if snap.valve_open:
        return snap.temp < target + s.overshoot
    return snap.temp < target - s.hysteresis / 2


def _coasting(snap: RoomSnapshot, deficit: float, s: Settings) -> bool:
    if snap.trend is None or snap.trend < s.coast_rate:
        return False
    minutes = max(deficit, 0) / snap.trend * 60
    return minutes <= s.coast_horizon_min
