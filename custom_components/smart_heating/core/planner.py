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
    riders: list[RoomConfig] = []  # rooms that may not start the boiler: they heat when another room calls
    season_off = house.season_off if house.season_off is not None else season_is_off(None, house.outdoor_mean, s.season_gate)
    for cfg, snap in rooms:
        need = needs[cfg.room_id]
        if snap.temp is None:
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.FAULT, need.reason)
            continue
        if snap.opening and need.level is not Level.SAFETY:
            # Open to outside: pause the room (its valve closes, its heater goes off). Frost still heats.
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.DEFERRED, f"{snap.opening} open: heating paused")
            continue
        if not need.calling:
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.IDLE, need.reason)
            continue
        if snap.recovering_min > 0 and need.level not in (Level.SAFETY, Level.MANUAL):
            # Just closed: the drop came from the opening, the rest of the house usually brings it back.
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.DEFERRED,
                                                  f"recovering after the door or window closed, {snap.recovering_min:.0f} min left")
            continue
        if need.level is Level.SAFETY:
            approved.append((cfg, snap))
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.APPROVED, "safety")
            continue
        why = need.reason
        if season_off:
            allowed, why = _mild_day(snap, need, house, s)
            if not allowed:
                decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.VETOED, why)
                continue
        valve = snap.valve_open if cfg.has_trv else True  # a radiator without a TRV is always open
        heating_this_room = bool((house.boiler_on and valve and cfg.radiator) or snap.heater_on)
        if need.level is not Level.MANUAL and not heating_this_room and _coasting(snap, need.deficit, s):
            decisions[cfg.room_id] = RoomDecision(
                cfg.room_id, need, Verdict.DEFERRED, f"coasting {snap.trend:+.2f}/h"
            )
            continue
        if cfg.radiator and not cfg.calls_boiler and need.level is not Level.MANUAL:
            riders.append(cfg)
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.DEFERRED, "heats when another room calls the boiler")
            continue
        approved.append((cfg, snap))
        decisions[cfg.room_id] = RoomDecision(cfg.room_id, need, Verdict.APPROVED, why)

    # Stack: upper rooms with a small deficit wait while a lower floor heats.
    lower_active = [c.floor for c, _ in approved]
    if lower_active:
        lowest = min(lower_active)
        keep = []
        for cfg, snap in approved:
            need = needs[cfg.room_id]
            if (
                cfg.floor > lowest
                and need.level not in (Level.SAFETY, Level.MANUAL)
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

    # Batching: don't fire for a single small low-priority deficit (unless you asked for heat).
    asked = house.mode is Mode.ONE_CYCLE or house.one_cycle_all
    if approved and not house.boiler_on and not asked and all(
        c.priority is Priority.C and needs[c.room_id].deficit < s.batch_min_deficit
        and needs[c.room_id].level not in (Level.SAFETY, Level.MANUAL)
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
    if house.away and not want_on:
        status, reason = "off", "away"

    if not boiler_control:
        plan = _valve_only(rooms, approved, decisions, house, want_on, status, reason, s, riders)
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
    elif house.away and not approved:  # nothing you asked for: away stops the boiler at once, like Off
        want_on, status, reason, hold = False, "off", "away", False

    # Valves (lazy): only move when the boiler will run, never during a min-run hold.
    if want_on and not hold:
        open_ids = {c.room_id for c, _ in approved}
        for cfg in riders:  # the boiler runs for others: these rooms take their share
            open_ids.add(cfg.room_id)
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, decisions[cfg.room_id].need, Verdict.PIGGYBACK, "heating while another room calls")
        # Piggyback: below target but not yet calling, and eligible for comfort/baseline.
        for cfg, snap in rooms:
            d = decisions[cfg.room_id]
            if (
                cfg.room_id not in open_ids
                and cfg.radiator  # topping up rides on the boiler: rooms without a radiator can't
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


def _valve_only(rooms, approved, decisions, house: HouseSnapshot, want_on: bool, status: str, reason: str, s: Settings,
                riders: list[RoomConfig] = ()) -> Plan:
    any_safety = any(decisions[c.room_id].need.level is Level.SAFETY for c, _ in approved)
    if house.mode is Mode.OFF and not any_safety:
        approved, want_on, status, reason = [], False, "off", "mode off"
    open_ids = {c.room_id for c, _ in approved}
    if approved:
        for cfg in riders:
            open_ids.add(cfg.room_id)
            decisions[cfg.room_id] = RoomDecision(cfg.room_id, decisions[cfg.room_id].need, Verdict.PIGGYBACK, "heating while another room calls")
    if house.boiler_on and house.mode is not Mode.OFF:
        # Known to be firing anyway: let near-target rooms top up.
        for cfg, snap in rooms:
            d = decisions[cfg.room_id]
            if cfg.room_id not in open_ids and cfg.radiator and d.verdict is Verdict.IDLE and _tops_up(snap, d.need.target, s):
                open_ids.add(cfg.room_id)
                decisions[cfg.room_id] = RoomDecision(cfg.room_id, d.need, Verdict.PIGGYBACK, "topping up while boiler runs")
    for cfg, snap in rooms:
        if not cfg.has_trv:
            continue
        should_open = cfg.room_id in open_ids
        if snap.valve_open is None or snap.valve_open != should_open:
            decisions[cfg.room_id].open_valve = should_open
    return Plan(want_on, decisions, status, reason)


def season_is_off(prev: bool | None, mean: float | None, gate: float, band: float = 0.5) -> bool:
    """Mild day: the outdoor day mean is at or above the gate. Once mild, it stays mild until the
    mean drops `band` below the gate, so it doesn't flip while the mean hovers at the gate."""
    if mean is None:
        return False
    return mean >= gate - band if prev else mean >= gate


def _mild_day(snap: RoomSnapshot, need, house: HouseSnapshot, s: Settings) -> tuple[bool, str]:
    """On a mild day automatic heating needs strong evidence; what you ask for always passes."""
    gate = f"mild day (outdoor {house.outdoor_mean:.1f}° ≥ {s.season_gate:g}°)"
    if need.level is Level.MANUAL:
        return True, "manual heat"
    if house.one_cycle_all:
        return True, "One Cycle, every room below target"
    if need.level is not Level.COMFORT:
        return False, f"{gate}, empty room"
    if house.mode is Mode.ONE_CYCLE:
        return True, f"One Cycle ({need.reason})"
    if need.deficit >= s.mild_margin and (snap.trend is None or snap.trend < s.coast_rate):
        return True, f"cold room on a mild day ({need.reason})"
    return False, f"{gate}, not cold enough"


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
