import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "smart_heating"))

from core import (  # noqa: E402
    HouseSnapshot,
    Level,
    Mode,
    Override,
    Priority,
    RoomConfig,
    RoomSnapshot,
    Settings,
    Signal,
    Trend,
    Verdict,
    evaluate_need,
    is_occupied,
    make_plan,
)

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)
S = Settings()
LIVING = RoomConfig("living", "Living", 1, Priority.A, 19.0)
KITCHEN = RoomConfig("kitchen", "Kitchen", 1, Priority.A, 19.0)
PLAY = RoomConfig("play", "Play", 0, Priority.B, 18.0)
BED = RoomConfig("bed", "Bedroom", 2, Priority.A, 18.5)
HALL = RoomConfig("hall", "Hall", 0, Priority.C, 17.0, has_trv=False)


def house(**kw):
    base = dict(now=NOW, mode=Mode.AUTO, outdoor_mean=6.0)
    base.update(kw)
    return HouseSnapshot(**base)


# ---------- Voice 1 ----------

def test_empty_room_holds_baseline_only():
    n = evaluate_need(LIVING, RoomSnapshot(temp=17.5), house(), S)
    assert not n.calling and n.target == 17.0


def test_empty_room_below_baseline_calls():
    n = evaluate_need(LIVING, RoomSnapshot(temp=16.4), house(), S)
    assert n.calling and n.level is Level.BASELINE


def test_occupied_room_gets_comfort():
    n = evaluate_need(LIVING, RoomSnapshot(temp=18.0, occupied=True), house(), S)
    assert n.calling and n.level is Level.COMFORT and n.target == 19.0


def test_office_at_18_8_no_heat():
    office = RoomConfig("office", "Office", 0, Priority.B, 18.0)
    n = evaluate_need(office, RoomSnapshot(temp=18.8, occupied=True), house(), S)
    assert not n.calling


def test_night_dark_bedroom_no_comfort():
    n = evaluate_need(BED, RoomSnapshot(temp=16.0, scheduled=True), house(night=True), S)
    assert not n.calling  # 16.0 > 15 night baseline - hysteresis


def test_night_lights_on_bedroom_comfort():
    n = evaluate_need(BED, RoomSnapshot(temp=17.0, lights_on=True), house(night=True), S)
    assert n.calling and n.level is Level.COMFORT


def test_hysteresis_keeps_calling_until_overshoot():
    snap = RoomSnapshot(temp=18.9, occupied=True, prev_calling=True)
    assert evaluate_need(LIVING, snap, house(), S).calling
    snap.temp = 19.1
    assert not evaluate_need(LIVING, snap, house(), S).calling


def test_mode_off_still_protects_frost():
    n = evaluate_need(LIVING, RoomSnapshot(temp=11.0), house(mode=Mode.OFF), S)
    assert n.calling and n.level is Level.SAFETY


def test_override_off_blocks_comfort():
    n = evaluate_need(LIVING, RoomSnapshot(temp=16.0, occupied=True, override=Override.OFF), house(), S)
    assert not n.calling


# ---------- Voice 2 / plan ----------

def test_occupied_cold_room_fires_boiler_and_opens_valve():
    p = make_plan([(LIVING, RoomSnapshot(temp=18.0, occupied=True, valve_open=False))], house(), S)
    assert p.boiler_on and p.open_rooms == ["living"]


def test_warm_season_vetoes_comfort():
    p = make_plan([(LIVING, RoomSnapshot(temp=18.0, occupied=True))], house(outdoor_mean=17.0), S)
    assert not p.boiler_on and p.rooms["living"].verdict is Verdict.VETOED


def test_season_gate_has_a_margin():
    from core import season_is_off
    assert season_is_off(None, 15.5, 15.5) and not season_is_off(False, 15.4, 15.5)
    assert season_is_off(True, 15.2, 15.5)  # once mild, stays mild just under the gate
    assert not season_is_off(True, 14.9, 15.5) and not season_is_off(True, None, 15.5)


def _mild(cfg, snap, **kw):
    return make_plan([(cfg, snap)], house(**{"outdoor_mean": 17.0, **kw}), S).rooms[cfg.room_id]


def test_mild_day_auto_heats_only_a_cold_room_in_use():
    assert _mild(LIVING, RoomSnapshot(temp=18.0, occupied=True)).verdict is Verdict.VETOED  # 1 below: not cold enough
    d = _mild(LIVING, RoomSnapshot(temp=17.4, occupied=True))  # 1.6 below and not warming
    assert d.verdict is Verdict.APPROVED and "cold room" in d.reason
    assert _mild(LIVING, RoomSnapshot(temp=17.4, occupied=True, trend=0.5)).verdict is Verdict.VETOED  # warming by itself
    d = _mild(LIVING, RoomSnapshot(temp=15.0))  # empty: baseline only
    assert d.verdict is Verdict.VETOED and d.reason.endswith("empty room")


def test_mild_day_what_you_ask_for_heats():
    d = _mild(LIVING, RoomSnapshot(temp=18.8, override=Override.HEAT))  # Heat now: from any shortfall
    assert d.verdict is Verdict.APPROVED and d.need.level is Level.MANUAL
    assert _mild(LIVING, RoomSnapshot(temp=18.4, occupied=True), mode=Mode.ONE_CYCLE).verdict is Verdict.APPROVED
    assert _mild(LIVING, RoomSnapshot(temp=15.0), mode=Mode.ONE_CYCLE).verdict is Verdict.VETOED  # empty room waits
    d = _mild(LIVING, RoomSnapshot(temp=16.9), mode=Mode.ONE_CYCLE, one_cycle_all=True)  # every room, any shortfall
    assert d.verdict is Verdict.APPROVED


def test_tie_is_named_after_the_room_in_use():
    study = RoomConfig("study", "Study", 0, Priority.B, 17.0)  # comfort equals the day baseline
    assert evaluate_need(study, RoomSnapshot(temp=16.0, occupied=True), house(), S).level is Level.COMFORT


def test_away_stops_automatic_heating_but_not_heat_now():
    p = make_plan([(LIVING, RoomSnapshot(temp=17.0, occupied=True))], house(away=True), S)
    assert not p.boiler_on and p.status == "off" and p.reason == "away"
    p = make_plan([(LIVING, RoomSnapshot(temp=17.0, override=Override.HEAT))], house(away=True), S)
    assert p.boiler_on and p.rooms["living"].need.level is Level.MANUAL


def test_heat_now_skips_coasting_and_batching_one_cycle_skips_batching():
    util = RoomConfig("util", "Utility", 0, Priority.C, 17.0)
    d = make_plan([(util, RoomSnapshot(temp=16.7, trend=1.0, override=Override.HEAT))], house(), S).rooms["util"]
    assert d.verdict is Verdict.APPROVED
    assert not make_plan([(util, RoomSnapshot(temp=16.3))], house(), S).boiler_on  # batched normally
    assert make_plan([(util, RoomSnapshot(temp=16.3))], house(mode=Mode.ONE_CYCLE), S).boiler_on


def test_season_never_vetoes_safety():
    p = make_plan([(LIVING, RoomSnapshot(temp=11.0))], house(outdoor_mean=15.0), S)
    assert p.boiler_on


def test_coasting_room_deferred():
    snap = RoomSnapshot(temp=18.3, occupied=True, trend=0.8, valve_open=False)
    p = make_plan([(LIVING, snap)], house(), S)
    assert not p.boiler_on and p.rooms["living"].verdict is Verdict.DEFERRED


def test_stack_defers_upper_small_deficit():
    rooms = [
        (PLAY, RoomSnapshot(temp=16.0, occupied=True, valve_open=False)),
        (BED, RoomSnapshot(temp=18.0, scheduled=True, valve_open=False)),
    ]
    p = make_plan(rooms, house(), S)
    assert p.boiler_on
    assert p.rooms["bed"].verdict is Verdict.DEFERRED
    assert "play" in p.open_rooms


def test_stack_releases_after_max_wait():
    rooms = [
        (PLAY, RoomSnapshot(temp=16.0, occupied=True)),
        (BED, RoomSnapshot(temp=18.0, scheduled=True, deferred_min=45)),
    ]
    p = make_plan(rooms, house(), S)
    assert p.rooms["bed"].verdict is Verdict.APPROVED


def test_hot_water_priority_pauses_heating():
    p = make_plan([(LIVING, RoomSnapshot(temp=18.0, occupied=True))], house(hw_calling=True, hw_calling_min=10), S)
    assert not p.boiler_on and p.status == "paused"


def test_hot_water_pause_has_limit():
    p = make_plan([(LIVING, RoomSnapshot(temp=18.0, occupied=True))], house(hw_calling=True, hw_calling_min=60), S)
    assert p.boiler_on


def test_min_off_time_respected():
    p = make_plan([(LIVING, RoomSnapshot(temp=18.0, occupied=True))], house(boiler_on=False, boiler_state_min=3), S)
    assert not p.boiler_on and p.status == "waiting"


def test_min_run_holds_boiler_without_moving_valves():
    p = make_plan([(LIVING, RoomSnapshot(temp=19.5, valve_open=True))], house(boiler_on=True, boiler_state_min=4), S)
    assert p.boiler_on and p.open_rooms == [] and p.close_rooms == []


def test_lazy_valves_when_boiler_off():
    p = make_plan([(LIVING, RoomSnapshot(temp=19.5, valve_open=True))], house(boiler_on=False), S)
    assert not p.boiler_on and p.close_rooms == []


def test_satisfied_room_closed_while_boiler_runs():
    rooms = [
        (LIVING, RoomSnapshot(temp=18.0, occupied=True, valve_open=True)),
        (KITCHEN, RoomSnapshot(temp=20.0, occupied=True, valve_open=True)),
    ]
    p = make_plan(rooms, house(boiler_on=True), S)
    assert p.close_rooms == ["kitchen"]


def test_piggyback_room_near_target():
    rooms = [
        (LIVING, RoomSnapshot(temp=18.0, occupied=True, valve_open=False)),
        (KITCHEN, RoomSnapshot(temp=18.7, occupied=True, valve_open=False)),
    ]
    p = make_plan(rooms, house(), S)
    assert p.rooms["kitchen"].verdict is Verdict.PIGGYBACK
    assert set(p.open_rooms) == {"living", "kitchen"}


def test_piggyback_margin_stops_valve_flapping():
    living = (LIVING, RoomSnapshot(temp=18.0, occupied=True, valve_open=False))

    def kitchen(temp, valve_open):
        p = make_plan([living, (KITCHEN, RoomSnapshot(temp=temp, occupied=True, valve_open=valve_open))], house(), S)
        return p.rooms["kitchen"].verdict

    assert kitchen(18.8, False) is Verdict.IDLE  # 0.2 below target: not worth opening
    assert kitchen(18.95, True) is Verdict.PIGGYBACK  # already open: carry on to target + overshoot
    assert kitchen(19.1, True) is Verdict.IDLE


def test_batching_skips_tiny_low_priority_call():
    util = RoomConfig("util", "Utility", 0, Priority.C, 17.0)
    p = make_plan([(util, RoomSnapshot(temp=16.3))], house(), S)
    assert not p.boiler_on


def test_dumb_room_never_gets_valve_command():
    rooms = [(LIVING, RoomSnapshot(temp=18.0, occupied=True)), (HALL, RoomSnapshot(temp=16.0))]
    p = make_plan(rooms, house(), S)
    assert p.rooms["hall"].open_valve is None


def test_all_sensors_down_fails_safe():
    p = make_plan([(LIVING, RoomSnapshot(temp=None))], house(), S)
    assert not p.boiler_on and p.status == "fault"


def test_mode_off_stops_comfort():
    p = make_plan([(LIVING, RoomSnapshot(temp=18.0, occupied=True))], house(mode=Mode.OFF), S)
    assert not p.boiler_on


# ---------- occupancy & trend ----------

def test_presence_join_needs_hold():
    sig = [Signal(True, NOW - timedelta(minutes=2))]
    assert not is_occupied(NOW, sig, [], [], was_occupied=False)
    sig = [Signal(True, NOW - timedelta(minutes=6))]
    assert is_occupied(NOW, sig, [], [], was_occupied=False)


def test_presence_leave_delay():
    sig = [Signal(False, NOW - timedelta(minutes=10))]
    assert is_occupied(NOW, sig, [], [], was_occupied=True)
    sig = [Signal(False, NOW - timedelta(minutes=25))]
    assert not is_occupied(NOW, sig, [], [], was_occupied=True)


def test_light_alone_expires():
    lights = [Signal(True, NOW - timedelta(minutes=45))]
    assert not is_occupied(NOW, [], [], lights, was_occupied=True)


def test_trend_rate():
    t = Trend()
    for i in range(7):
        t.add(NOW + timedelta(minutes=5 * i), 18.0 + 0.1 * i)
    assert abs(t.rate() - 1.2) < 0.01


# ---------- climate ----------
from core import OutdoorModel, house_means  # noqa: E402


def test_house_and_floor_means():
    avg, floors = house_means([(0, 18.0), (0, 17.0), (1, 20.0), (2, None)])
    assert avg == 18.33 and floors == {0: 17.5, 1: 20.0}


def test_outdoor_day_mean_blends_past_and_forecast():
    m = OutdoorModel()
    for i in range(12):
        m.observe(NOW - timedelta(hours=11 - i), 6.0)
    m.set_forecast([(NOW + timedelta(hours=h), 10.0) for h in range(1, 25)])
    assert m.day_mean(NOW) == 8.0
    assert m.forecast_min(NOW) == 10.0


def test_outdoor_day_mean_forecast_only():
    m = OutdoorModel()
    m.set_forecast([(NOW + timedelta(hours=h), float(h % 4)) for h in range(1, 25)])
    assert m.day_mean(NOW) == 1.5


# ---------- learning ----------
import math  # noqa: E402

from core.learn import Phase, RoomModel, classify, overall_progress  # noqa: E402
from core.energy import EnergyDay  # noqa: E402


def _simulate(model, tau=84.0, gain=5.5, hours=48, tout_fn=lambda h: 6 + 3 * math.sin(h / 24 * 2 * math.pi)):
    tin = 20.0
    k = 1 / tau
    t = NOW
    step = 5 / 60
    h = 0.0
    while h < hours:
        tout = tout_fn(h)
        model.observe(t, round(tin, 2), tout, Phase.FREE)
        tin += -k * (tin - tout - gain) * step
        h += step
        t += timedelta(minutes=5)
    return tin


def test_learner_recovers_tau_and_gain():
    m = RoomModel.new()
    _simulate(m, hours=72, tout_fn=lambda h: 2 + 8 * (h % 24) / 24)
    assert m.tau and 70 < m.tau < 100
    assert m.gain and 4.0 < m.gain < 7.0


def test_learner_prior_gives_sane_tau_from_one_mild_night():
    # One mild night read at 0.1 degC resolution: outside falls with the room, so Tin - Tout
    # barely varies and the slope alone is noise. The free-heat prior keeps tau plausible.
    m = RoomModel.new()
    tin, k, t = 22.0, 1 / 40.0, NOW
    for i in range(10 * 12):  # 10 h, 5 min ticks
        tout = 12 - i / 36
        m.observe(t, round(tin, 1), tout, Phase.FREE)
        tin += -k * (tin - tout - 1.5) * (5 / 60)
        t += timedelta(minutes=5)
    assert m.free.spread < 2.0
    assert m.tau and 25 < m.tau < 60, m.tau
    assert m.gain is not None and -1 < m.gain < 4, m.gain


def test_learner_progress_and_completion():
    m = RoomModel.new()
    _simulate(m, hours=30, tout_fn=lambda h: 2 + 8 * (h % 24) / 24)
    assert m.free.n >= 96 and m.tau_error is None  # 24 h of data, but from 2 days only
    assert not m.settled and m.progress < 0.6
    _simulate(m, hours=120, tout_fn=lambda h: 2 + 8 * (h % 24) / 24)
    assert m.settled and m.progress >= 0.69  # free side done, no heating yet
    assert not m.complete
    for i in range(10 * 3 + 1):
        m.observe(NOW + timedelta(days=6, minutes=5 * i), 18.0 + 0.1 * i, 6.0, Phase.HEAT)
    assert m.warmup and abs(m.warmup - 1.2) < 0.05
    assert m.complete and overall_progress([m]) == 1.0


def _days(model, gains, tau=40.0, step_min=5):
    """Free-running days; `gains` is each day's free-heat lift (neighbours heated or not)."""
    tin, k, t = 20.0, 1 / tau, NOW
    for day, gain in enumerate(gains):
        for i in range(24 * 60 // step_min):
            h = day * 24 + i * step_min / 60
            tout = 5 + 3 * math.sin(h / 24 * 2 * math.pi) + 2 * (day % 3)
            model.observe(t, round(tin, 2), tout, Phase.FREE)
            tin += -k * (tin - tout - gain) * step_min / 60
            t += timedelta(minutes=step_min)


def test_settles_only_when_days_agree():
    clean, mixed = RoomModel.new(), RoomModel.new()
    _days(clean, [3.0] * 6)
    _days(mixed, [1.0, 6.0, 2.0, 5.5, 0.5, 6.0])
    assert clean.settled and clean.tau_error < 0.05
    lo, hi = clean.tau_range
    assert lo <= clean.tau <= hi and 35 < clean.tau < 45
    assert mixed.status["cooling_days"] == 5 and mixed.tau_error > 0.25 and not mixed.settled
    lo, hi = mixed.tau_range
    assert hi - lo > 0.4 * mixed.tau
    assert not mixed.steady_enough and mixed.settle_hours() > 0


def test_a_room_that_never_settles_counts_as_learned_after_two_weeks():
    m = RoomModel.new()
    for i in range(1200):  # day groups that disagree a lot: cooling rates 1/100 to 1/16 per hour
        g = i % 5
        x = 6 + (i // 5 % 40) * 0.25
        m._commit(NOW + timedelta(minutes=15 * i), g, x, -[0.01, 0.06, 0.015, 0.05, 0.03][g] * (x - 2))
    m.heat_n, m.heat_sum = 8, 8.0
    assert not m.settled and m.steady_enough and m.complete and m.settle_hours() == 0
    assert m.tau_range[1] - m.tau_range[0] > 0.3 * m.tau  # the range stays shown


def test_disturbance_skips_samples_around_it():
    m = RoomModel.new()
    tin, t = 20.0, NOW
    for i in range(8 * 60):  # 8 h free-running, 1 min ticks, shower at 4 h
        shower = 240 <= i < 250
        tin += (0.15 if shower else -0.004)
        m.observe(t, round(tin, 2), 5.0, Phase.FREE, rh=85.0 if shower else 55.0)
        t += timedelta(minutes=1)
    # 1 h before, the shower, then 2 h of hold: about 13 of 32 samples left out.
    assert 11 <= m.skipped <= 15 and m.free.n + len(m.pending) + m.skipped >= 30


def test_steady_cap_counts_samples_not_faded_weight():
    # 20 cooling samples a day (5 h) never add up to 960 once faded; the cap counts real samples.
    m = RoomModel.new()
    for i in range(1000):
        g = i // 20 % 5
        x = 6 + (i % 40) * 0.25
        m._commit(NOW + timedelta(hours=1.2 * i), g, x, -[0.01, 0.06, 0.015, 0.05, 0.03][g] * (x - 2))
    assert sum(f.n for f in m.days) < 960 and m.counted == 1000 and not m.settled and m.steady_enough
    assert RoomModel.from_dict(m.to_dict()).counted == 1000 and RoomModel.from_dict({"free": {}}).counted == 0


def test_cooling_alone_does_not_look_like_moisture():
    # Relative humidity rises as a room cools with the same moisture in it: no hold.
    m = RoomModel.new()
    t = NOW
    for i in range(3 * 60):
        tin = 20.0 - i * 1.6 / 60
        rh = 100 * math.exp(17.62 * 13.0 / (243.12 + 13.0) - 17.62 * tin / (243.12 + tin))  # dew point stays 13.0
        m.observe(t, round(tin, 2), 5.0, Phase.FREE, rh=round(rh, 1))
        t += timedelta(minutes=1)
    assert m.skipped == 0 and m.hold_until is None


def test_humidity_jump_alone_is_a_disturbance():
    m = RoomModel.new()
    t = NOW
    for i in range(3 * 60):
        m.observe(t, round(20.0 - i * 0.003, 2), 5.0, Phase.FREE, rh=80.0 if 60 <= i < 70 else 55.0)
        t += timedelta(minutes=1)
    assert m.skipped >= 6 and m.hold_until is not None


def test_heating_flushes_held_samples():
    m = RoomModel.new()
    t = NOW
    for i in range(40):
        m.observe(t + timedelta(minutes=i), 20.0 - i * 0.01, 5.0, Phase.FREE)
    assert m.free.n == 0 and len(m.pending) == 2
    m.observe(t + timedelta(minutes=41), 19.6, 5.0, Phase.OTHER)
    assert round(m.free.n, 3) == 2 and not m.pending


def test_old_data_fades():
    m = RoomModel.new()
    m._commit(NOW, 0, 10.0, -0.3)
    m._commit(NOW + timedelta(days=30), 1, 10.0, -0.3)
    assert abs(m.free.n - 1.5) < 1e-9 and abs(m.days[0].n - 0.5) < 1e-9 and m.days[1].n == 1


def test_other_phase_resets_segment():
    m = RoomModel.new()
    m.observe(NOW, 19.0, 6.0, Phase.FREE)
    m.observe(NOW + timedelta(minutes=10), 18.9, 6.0, Phase.OTHER)
    assert not m.observe(NOW + timedelta(minutes=20), 18.8, 6.0, Phase.FREE)
    assert m.free.n == 0


def test_prediction_and_hours_to_floor():
    m = RoomModel.new()
    _simulate(m, hours=72, tout_fn=lambda h: 2 + 8 * (h % 24) / 24)
    p = m.predict(20.0, 5.0, 8)
    assert 18.0 < p < 20.0
    assert m.hours_to(20.0, 5.0, 17.0) and m.hours_to(20.0, 5.0, 17.0) > 8
    assert m.hours_to(20.0, 14.0, 17.0) is None  # free heat keeps it above 17


def test_model_roundtrip():
    m = RoomModel.new()
    _simulate(m, hours=10)
    m2 = RoomModel.from_dict(m.to_dict())
    assert m2.free.n == m.free.n and m2.tau == m.tau
    assert [f.n for f in m2.days] == [f.n for f in m.days] and m2.faded == m.faded


def test_model_loads_old_format():
    old = {"free": {"n": 100, "sx": 1000.0, "sy": -20.0, "sxx": 10400.0, "sxy": -205.0, "xmin": 7.0, "xmax": 13.0},
           "heat_n": 9, "heat_sum": 9.0, "seg_phase": "free", "seg_start": None, "seg_tin": None}
    m = RoomModel.from_dict(old)
    assert m.tau and len(m.days) == 5 and m.tau_error is None and not m.complete


def test_classify():
    assert classify(False, 90, None) is Phase.FREE
    assert classify(False, 20, None) is Phase.OTHER
    assert classify(True, 15, True) is Phase.HEAT
    assert classify(True, 15, False) is Phase.OTHER
    assert classify(True, 15, None) is Phase.HEAT  # dumb radiator: always open


# ---------- energy ----------

def test_energy_day_runtime_burns_and_meter():
    d = EnergyDay()
    today = NOW.date()
    d = d.tick(NOW, today, False, False, False, 100.0, 5.0)
    t = NOW
    for i, on in enumerate([True, True, True, False, True, True]):
        t += timedelta(minutes=10)
        d = d.tick(t, today, on, False, on, 100.0 + i, 5.0)
    assert d.burns == 2
    assert d.runtime_min == 40.0
    kwh, measured = d.gas_kwh(meter_unit_m3=True, boiler_input_kw=15)
    assert measured and kwh == round(5 * 11.2, 2)
    assert d.kwh_per_degree_day(kwh, 14.0) == round(kwh / 9.0, 2)


def test_energy_estimate_without_meter_and_rollover():
    d = EnergyDay().tick(NOW, NOW.date(), True, False, True, None, None)
    d = d.tick(NOW + timedelta(minutes=20), NOW.date(), True, False, True, None, None)
    kwh, measured = d.gas_kwh(False, 15)
    assert not measured and kwh == 5.0
    d2 = d.tick(NOW + timedelta(days=1), (NOW + timedelta(days=1)).date(), False, False, False, None, None)
    assert d2.runtime_min == 0 and d2.day != d.day


def test_energy_meter_daily_total_reset_and_revisions():
    d = EnergyDay().tick(NOW, NOW.date(), False, False, False, 40.0, None)  # a daily total, already at 40 kWh
    t = NOW
    for v in (41.0, 40.9, 42.0, 0.5, 1.5):  # use, a revised reading, use, reset to a new total, use
        t += timedelta(minutes=10)
        d = d.tick(t, NOW.date(), False, False, False, v, None)
    kwh, measured = d.gas_kwh(False, 15)
    assert measured and kwh == 3.0  # 40 -> 42, then 0.5 -> 1.5; the 40.9 revision is ignored


def test_energy_cost_at_the_rate_when_used_without_standing_charge():
    d = EnergyDay()
    assert d.price(10.0, 0.06) == 0.6
    assert d.price(15.0, 0.10) == 1.1  # the 5 new kWh at the new rate
    assert d.price(15.0, 0.50) == 1.1  # no new kWh, no new cost


# ---------- valve-only (no boiler control) ----------

def test_valve_only_opens_and_closes_directly():
    rooms = [
        (LIVING, RoomSnapshot(temp=18.0, occupied=True, valve_open=False)),
        (KITCHEN, RoomSnapshot(temp=20.0, occupied=True, valve_open=True)),
    ]
    p = make_plan(rooms, house(boiler_on=False), S, boiler_control=False)
    assert p.open_rooms == ["living"] and p.close_rooms == ["kitchen"]


def test_valve_only_ignores_boiler_timing_and_hw():
    rooms = [(LIVING, RoomSnapshot(temp=18.0, occupied=True, valve_open=False))]
    p = make_plan(rooms, house(boiler_state_min=1, hw_calling=True, hw_calling_min=5), S, boiler_control=False)
    assert p.open_rooms == ["living"] and p.status == "heating"


def test_valve_only_mode_off_closes_everything():
    rooms = [(LIVING, RoomSnapshot(temp=18.0, occupied=True, valve_open=True))]
    p = make_plan(rooms, house(mode=Mode.OFF), S, boiler_control=False)
    assert p.close_rooms == ["living"] and not p.boiler_on


def test_single_zone_no_trvs_still_fires_boiler():
    no_trv = RoomConfig("living", "Living", 1, Priority.A, 19.0, has_trv=False)
    p = make_plan([(no_trv, RoomSnapshot(temp=18.0, occupied=True))], house(), S)
    assert p.boiler_on and p.open_rooms == [] and p.close_rooms == []


# ---------- insulation & away ----------
from core import insulation, is_away  # noqa: E402


def test_insulation_grades_and_scores():
    assert insulation.grade(84) == "B" and insulation.grade(32) == "E" and insulation.grade(10) == "G"
    assert insulation.score(10) == 0 and insulation.score(200) == 100 and 60 < insulation.score(84) < 75
    assert insulation.loss_per_hour(84) == 0.12
    assert insulation.combine([32, 84, 600]) == 84
    assert insulation.describe(None)["grade"] is None
    assert insulation.grade_range(32, 48) == "D-E" and insulation.grade_range(42, 50) == "D"
    assert insulation.grade_range(None, 50) is None


def test_away_sources():
    assert is_away([("alarm_control_panel", "armed_away")])[0]
    assert not is_away([("alarm_control_panel", "armed_home")])[0]
    assert is_away([("person", "not_home"), ("person", "work")])[0]
    assert not is_away([("person", "not_home"), ("person", "home")])[0]
    assert is_away([("zone", "0")])[0] and not is_away([("zone", "2")])[0]
    assert is_away([("input_boolean", "on")])[0]
    assert not is_away([("person", "unavailable")])[0]
    assert is_away([("alarm_control_panel", "disarmed"), ("binary_sensor", "on")])[0]


# ---------- setpoints and calibration summary ----------

def test_setpoints_shift_and_keep_room_difference():
    from core import Setpoints, RoomConfig, Priority, Settings
    living = RoomConfig("l", "Living", 0, Priority.A, 19.0)
    bed = RoomConfig("b", "Bed", 1, Priority.A, 18.5)
    hall = RoomConfig("h", "Hall", 0, Priority.C, 17.0)
    sp = Setpoints.initial([living, bed, hall])
    assert sp.house == 19.0 and sp.offset == 0
    sp.house = 20.5
    assert sp.comfort(hall) == 18.5 and sp.settings(Settings()).baseline_day == 18.5
    sp.set_room(bed, 21.0)
    sp.house = 19.0
    assert sp.comfort(bed) == 19.5 and sp.is_custom(bed)
    # A new configured comfort (Reconfigure) wins over the old card setting.
    bed2 = RoomConfig("b", "Bed", 1, Priority.A, 18.0)
    assert sp.comfort(bed2) == 18.0
    assert Setpoints.from_dict(sp.to_dict()).comfort(bed) == 19.5


def test_setpoints_never_lower_baseline_below_safety():
    from core import Setpoints, Settings
    sp = Setpoints(reference=19.0, house=10.0)
    s = sp.settings(Settings())
    assert s.baseline_night == s.safety == 12.0


def test_calibration_summary_counts_down():
    from core import RoomModel, calibration_summary
    models = [RoomModel.new() for _ in range(5)]
    info = calibration_summary(models, 0.8)
    assert info["rooms_needed"] == 4 and info["cooling_hours_left"] == 24.0 and info["eta_hours"] > 24
    assert info["cooling_days"] == 0 and info["uncertainty_pct"] is None
    for m in models[:4]:
        for i in range(96):
            m.free.add(1.0 + i * 0.03, -0.05 - i * 0.0015)
        m.heat_n, m.heat_sum = 8, 8.0
    info = calibration_summary(models, 0.8)
    assert info["rooms_done"] == 0 and info["cooling_hours_left"] == 0 and info["eta_hours"] >= 96
    for m in models[:4]:
        for i in range(96):
            m.days[i % 5].add(1.0 + i * 0.03, -0.05 - i * 0.0015)
    info = calibration_summary(models, 0.8)
    assert info["rooms_done"] == 4 and info["uncertainty_pct"] == 0 and info["eta_hours"] == 0


# ---------- electric heaters and hybrid ----------

def _house(mode=None, boiler_on=False):
    return HouseSnapshot(now=datetime(2026, 1, 10, 12, tzinfo=timezone.utc), mode=mode or Mode.AUTO,
                         outdoor_mean=5.0, boiler_on=boiler_on)


def test_electric_room_uses_heater_not_boiler():
    from core import make_plan
    cfg = RoomConfig("e", "Cafe", 0, Priority.A, 19.0, has_trv=False, radiator=False, heater=True)
    plan = make_plan([(cfg, RoomSnapshot(temp=16.0, occupied=True, heater_on=False))], _house(), Settings(), boiler_control=False)
    assert plan.rooms["e"].heater_on is True and not plan.boiler_on
    warm = make_plan([(cfg, RoomSnapshot(temp=19.5, occupied=True, heater_on=True))], _house(), Settings(), boiler_control=False)
    assert warm.rooms["e"].heater_on is False


def test_electric_heater_off_in_off_mode_but_frost_still_heats():
    from core import make_plan
    cfg = RoomConfig("e", "Cafe", 0, Priority.A, 19.0, has_trv=False, radiator=False, heater=True)
    off = make_plan([(cfg, RoomSnapshot(temp=16.0, heater_on=True))], _house(Mode.OFF), Settings(), boiler_control=False)
    assert off.rooms["e"].heater_on is False
    frost = make_plan([(cfg, RoomSnapshot(temp=10.0))], _house(Mode.OFF), Settings(), boiler_control=False)
    assert frost.rooms["e"].heater_on is True


def test_hybrid_single_room_uses_heater_instead_of_boiler():
    from core import make_plan
    hyb = RoomConfig("h", "Office", 0, Priority.B, 18.0, has_trv=True, radiator=True, heater=True)
    gas = RoomConfig("g", "Living", 1, Priority.A, 19.0, has_trv=True)
    alone = make_plan([(hyb, RoomSnapshot(temp=16.0, occupied=True, valve_open=False)), (gas, RoomSnapshot(temp=19.5, valve_open=False))],
                      _house(), Settings())
    assert alone.rooms["h"].heater_on is True and not alone.boiler_on
    both = make_plan([(hyb, RoomSnapshot(temp=16.0, occupied=True, valve_open=False)), (gas, RoomSnapshot(temp=17.0, occupied=True, valve_open=False))],
                     _house(), Settings())
    assert both.boiler_on and both.rooms["h"].heater_on is False and both.rooms["h"].open_valve is True


# ---------- consumption: meter split with learned rates ----------
import random  # noqa: E402

from core.consumption import Cost, DayRecord, fit, learn_step, meter_step  # noqa: E402

GAS_PRIOR = {"heating": 10.5, "hot_water": 10.5, "cold": 0.0}
GAS_BOUNDS = {"heating": (2.25, 18.0), "hot_water": (2.25, 18.0), "cold": (0.0, 7.5)}


def _gas_days(n, seed=7, noise=0.8, hob=0.6, true=(12.0, 9.0, 2.0)):
    rng, out = random.Random(seed), []
    for i in range(n):
        heat, hw, cf = rng.uniform(1, 6), rng.uniform(0.5, 1.5), rng.uniform(0, 1.2)
        h = {"heating": heat, "hot_water": hw, "cold": heat * cf}
        out.append(DayRecord(f"d{i}", true[0] * heat + true[1] * hw + true[2] * heat * cf + hob + rng.gauss(0, noise), h))
    return out


def test_fit_learns_the_boilers_real_rates_from_daily_totals():
    r = fit(_gas_days(28), GAS_PRIOR, 0.5, GAS_BOUNDS, base_strength=30)
    assert abs(r.rates["heating"] - 12) < 0.5 and abs(r.rates["cold"] - 2) < 0.5
    assert abs(r.rates["hot_water"] - 9) < 0.8 and r.base < 1.2  # hot water runs ~1 h every day: hardest to separate
    assert r.days == 28 and r.error < 0.05


def test_fit_ignores_a_meter_glitch_day():
    days = _gas_days(14)
    days[5] = DayRecord("glitch", 180.0, days[5].hours)
    r = fit(days, GAS_PRIOR, 0.5, GAS_BOUNDS, base_strength=30)
    assert abs(r.rates["heating"] - 12) < 1.0, r.rates


def test_fit_needs_a_few_days_before_moving_away_from_the_starting_values():
    odd = [DayRecord("odd", 60.0, {"heating": 2.0, "hot_water": 1.0, "cold": 0.0})]
    assert fit(odd, GAS_PRIOR, 0.5, GAS_BOUNDS, base_strength=30).rates == GAS_PRIOR
    assert fit([], GAS_PRIOR, 0.5, GAS_BOUNDS).rates == GAS_PRIOR  # no meter: the starting values
    r = fit(_gas_days(3), GAS_PRIOR, 0.5, GAS_BOUNDS, base_strength=30)
    assert all(abs(r.rates[u] - GAS_PRIOR[u]) < 3 for u in ("heating", "hot_water")), r.rates


def test_two_heaters_always_together_share_what_the_meter_shows():
    # Two "2000 W" heaters in half mode: 2600 W with both on, 600 W of house load otherwise.
    hours = [3, 5, 4, 6, 2, 5, 4, 3, 6, 2, 4, 5, 3, 6]  # two weeks
    days = [DayRecord(f"d{i}", 2.0 * h + 14.4, {"a:full": h, "b:full": h}) for i, h in enumerate(hours)]
    r = fit(days, {"a:full": 2.0, "b:full": 2.0}, 10.0, {"a:full": (0.5, 2.6), "b:full": (0.5, 2.6)}, strength=1.0, base_strength=0.5)
    assert abs(r.rates["a:full"] - 1.0) < 0.25 and abs(r.rates["b:full"] - 1.0) < 0.25, r.rates


def test_live_power_jumps_teach_a_heaters_real_draw():
    kw = learn_step(None, 1010, rated_kw=2.0)  # 2 kW heater measured at about 1 kW (half mode)
    assert kw == 1.01
    assert learn_step(kw, 3500, rated_kw=2.0) == kw  # a kettle at the same moment: ignored
    assert learn_step(kw, 990, rated_kw=2.0) == round(1.01 + 0.3 * (0.99 - 1.01), 3)


def test_meter_restart_and_cost_at_the_rate_when_used():
    st = meter_step(None, None, 0.0, 40.0)
    for v in (41.0, 40.9, 42.0, 0.5, 1.5):
        st = meter_step(*st, v)
    start, last, carry = st
    assert carry + last - start == 3.0
    c = Cost()
    assert c.add(10.0, 0.06) == 0.6 and c.add(15.0, 0.10) == 1.1 and c.add(15.0, 0.5) == 1.1


# ---------- window advice ----------
from core.ventilation import COOLDOWN, Outside, RoomAir, WindowAdvisor, burst_minutes, dew_point  # noqa: E402


def test_dew_point_and_burst_length():
    assert dew_point(20.0, 65.0) == 13.2 and dew_point(5.0, 95.0) == 4.3
    assert burst_minutes(-2) == 5 and burst_minutes(6) == 10 and burst_minutes(12) == 15 and burst_minutes(18) == 25
    assert burst_minutes(6, wind_kmh=40) == 5


def _damp():
    return [RoomAir("Bathroom", 20.0, 80.0), RoomAir("Bedroom", 19.0, 55.0)]


def test_drying_burst_then_close_then_cooldown():
    w, rainy = WindowAdvisor(), Outside(6.0, dew_point(6.0, 95.0), "rainy", 15.0)
    a = w.step(NOW, _damp(), rainy, heating_season=True)
    assert a.action == "open" and a.kind == "dry" and a.rooms == ["Bathroom"] and a.minutes == 10
    assert "sheltered side" in a.reason  # light rain does not stop it: the air is still far drier
    assert w.step(NOW + timedelta(minutes=5), _damp(), rainy, heating_season=True).action == "open"
    a = w.step(NOW + timedelta(minutes=10), _damp(), rainy, heating_season=True)
    assert a.action == "close" and a.kind == "done"
    assert w.step(NOW + timedelta(minutes=26), _damp(), rainy, heating_season=True).action == "none"  # cooldown
    later = NOW + timedelta(minutes=10) + COOLDOWN
    assert w.step(later, _damp(), rainy, heating_season=True).action == "open"


def test_no_drying_when_it_would_not_help_or_waste_heat():
    dry_out = Outside(6.0, dew_point(6.0, 90.0), "cloudy")
    assert WindowAdvisor().step(NOW, _damp(), dry_out, heating_season=True, heating_now=True).action == "none"
    assert WindowAdvisor().step(NOW, _damp(), dry_out, heating_season=True, night=True).action == "none"
    assert WindowAdvisor().step(NOW, _damp(), Outside(6.0, 4.0, "pouring"), heating_season=True).action == "none"
    assert WindowAdvisor().step(NOW, _damp(), Outside(6.0, 4.0, "cloudy", 70.0), heating_season=True).action == "none"
    muggy = Outside(18.0, dew_point(18.0, 90.0), "cloudy")  # outside air as damp as inside
    assert WindowAdvisor().step(NOW, _damp(), muggy, heating_season=False).action == "none"
    assert WindowAdvisor().step(NOW, _damp(), dry_out, heating_season=True, away=True).action == "none"


def test_storm_closes_an_open_window():
    w = WindowAdvisor()
    w.step(NOW, _damp(), Outside(6.0, 4.0, "rainy"), heating_season=True)
    a = w.step(NOW + timedelta(minutes=3), _damp(), Outside(6.0, 4.0, "pouring"), heating_season=True)
    assert a.action == "close" and a.kind == "storm" and "pouring" in a.reason


def test_summer_cooling_and_hot_days():
    hot = [RoomAir("Loft", 26.0, 50.0), RoomAir("Kitchen", 22.0, 50.0)]
    w = WindowAdvisor()
    a = w.step(NOW, hot, Outside(19.0, 10.0, "clear-night"), heating_season=False)
    assert a.action == "open" and a.kind == "cool" and a.rooms == ["Loft"]
    assert WindowAdvisor().step(NOW, hot, Outside(19.0, 10.0), heating_season=True).action == "none"  # heating season
    cooler = [RoomAir("Loft", 23.5, 50.0), RoomAir("Kitchen", 21.0, 50.0)]
    assert w.step(NOW + timedelta(hours=1), cooler, Outside(19.0, 10.0), heating_season=False).action == "open"
    done = [RoomAir("Loft", 22.0, 50.0), RoomAir("Kitchen", 20.0, 50.0)]
    a = w.step(NOW + timedelta(hours=2), done, Outside(19.0, 10.0), heating_season=False)
    assert a.action == "close" and a.kind == "cooled"
    a = WindowAdvisor().step(NOW, hot, Outside(29.0, 15.0, "sunny"), heating_season=False)
    assert a.action == "close" and a.kind == "hot"


def test_window_advice_survives_a_restart_and_closes_when_everyone_leaves():
    w = WindowAdvisor()
    w.step(NOW, _damp(), Outside(6.0, 4.0, "cloudy"), heating_season=True)
    w2 = WindowAdvisor.from_dict(w.to_dict())
    assert w2.advice.action == "open" and w2.advice.until == w.advice.until and w2.next_dry == w.next_dry
    a = w2.step(NOW + timedelta(minutes=10), _damp(), Outside(6.0, 4.0, "cloudy"), heating_season=True)
    assert a.action == "close" and a.kind == "done"
    w3 = WindowAdvisor()
    w3.step(NOW, _damp(), Outside(6.0, 4.0, "cloudy"), heating_season=True)
    a = w3.step(NOW + timedelta(minutes=2), _damp(), Outside(6.0, 4.0, "cloudy"), heating_season=True, away=True)
    assert a.action == "close" and a.kind == "away"
    assert w3.step(NOW + timedelta(minutes=30), _damp(), Outside(6.0, 4.0), heating_season=True, away=True).action == "none"


def test_missing_outdoor_temperature_keeps_a_running_burst():
    w = WindowAdvisor()
    w.step(NOW, _damp(), Outside(6.0, 4.0, "cloudy"), heating_season=True)
    assert w.step(NOW + timedelta(minutes=3), _damp(), Outside(None), heating_season=True).action == "open"
    assert w.step(NOW + timedelta(minutes=10), _damp(), Outside(None), heating_season=True).kind == "done"
