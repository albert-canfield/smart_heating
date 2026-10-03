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
    base = dict(now=NOW, mode=Mode.CONTINUOUS, outdoor_mean=6.0)
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
    p = make_plan([(LIVING, RoomSnapshot(temp=18.0, occupied=True))], house(outdoor_mean=15.0), S)
    assert not p.boiler_on and p.rooms["living"].verdict is Verdict.VETOED


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
    assert m.progress >= 0.69  # free side done, no heating yet
    assert not m.complete
    for i in range(10 * 3 + 1):
        m.observe(NOW + timedelta(days=3, minutes=5 * i), 18.0 + 0.1 * i, 6.0, Phase.HEAT)
    assert m.warmup and abs(m.warmup - 1.2) < 0.05
    assert m.complete and overall_progress([m]) == 1.0


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
    for m in models[:4]:
        for i in range(96):
            m.free.add(1.0 + i * 0.03, -0.05 - i * 0.0015)
        m.heat_n, m.heat_sum = 8, 8.0
    info = calibration_summary(models, 0.8)
    assert info["rooms_done"] == 4 and info["cooling_hours_left"] == 0 and info["eta_hours"] == 0


# ---------- electric heaters and hybrid ----------

def _house(mode=None, boiler_on=False):
    return HouseSnapshot(now=datetime(2026, 1, 10, 12, tzinfo=timezone.utc), mode=mode or Mode.CONTINUOUS,
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
