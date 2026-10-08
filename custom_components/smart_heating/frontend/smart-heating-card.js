/*
 * Smart Heating card
 * A section view of the house: roof, floors stacked as built, rooms as cells.
 * Zero config: discovers the smart_heating integration's entities.
 *
 *   type: custom:smart-heating-card
 *   title: Heating        # optional
 *   layout: compact       # compact (default) or full
 *   icon: mdi:radiator    # optional; default is the Smart Heating logo
 *   hide_title: false     # optional
 */

const STATE_LABEL = {
  approved: "Heating",
  piggyback: "Topping up",
  wants: "Wants heat",
  watched: "Watched only",  // nothing heats it: shown, learned from, never heated  // approved, but no heat flowing yet (hot water first, boiler rest, protection, watching)
  deferred: "Waiting",  // warming on its own, heat rising from below, or a small demand batched
  vetoed: "Not needed",
  idle: "Idle",
  fault: "No sensor",
};

const SHORT_RATING = { "below average": "below avg" };  // fits a tile; the tooltip keeps the full word

const FLOOR_NAME = { 0: "Ground", 1: "1st", 2: "2nd", 3: "3rd" };

const MODE_LABEL = { off: "Off", one_cycle: "One cycle", auto: "Auto" };

const MODE_TIP = {
  off: "Stops everything: One Cycle, Heat now and the boiler. Frost protection stays on",
  one_cycle: "Heats the rooms in use, or ones you pick, once, then switches itself off",
  auto: "Heats each room when it needs it, firing the boiler only when it's worth it",
};

const ICON_INFO = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 7.5v.5"/></svg>';
const IND = {
  flame: '<path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.2 1.2-3.6 2.4-4.6.2 1.6 1 2.6 2.1 3C11 8.8 11.4 5.6 12 3z"/>',
  radiator: '<rect x="4" y="6" width="16" height="11" rx="2"/><path d="M8 6v11M12 6v11M16 6v11M6 17v2M18 17v2"/>',
  water: '<path d="M12 3.5c3 3.8 5.5 6.9 5.5 10a5.5 5.5 0 0 1-11 0c0-3.1 2.5-6.2 5.5-10z"/>',
  moon: '<path d="M19 14.5A7.5 7.5 0 0 1 9.5 5a7.5 7.5 0 1 0 9.5 9.5z"/>',
  away: '<path d="M4 11l8-6 8 6v8a1 1 0 0 1-1 1h-4v-5h-6v5H5a1 1 0 0 1-1-1z"/><path d="M3 21L21 3"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  bolt: '<path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z"/>',
};

function statusDot(d) {
  const key = d.monitor && d.heatTest == null && ["heating", "paused", "waiting"].includes(d.status) ? "would" : (d.status || "idle");
  return `<i class="sdot d-${key}" aria-hidden="true"></i>`;
}

function indicators(d) {
  const out = [];
  const add = (key, cls, label) => out.push(`<span class="ind ${cls}" title="${esc(label)}" aria-label="${esc(label)}" role="img"><svg viewBox="0 0 24 24">${IND[key]}</svg></span>`);
  if (d.firing === true) add("flame", "burn", "Boiler burning");
  else if (d.monitor && d.demand && d.hasBoiler) add("flame", "wait", "Would call the boiler");
  else if (d.called) add("flame", "wait", "Boiler called, not burning yet");
  else if (d.demand && d.holdUntil) add("flame", "wait", `Boiler wanted, protection holds it until ${hhmm(d.holdUntil)}`);
  if (d.radiatorCount > 0) add("radiator", "heat", `Radiators heating in ${rooms_(d.radiatorCount)}`);
  if (d.heaterCount > 0) add("bolt", "heat", `${d.heaterCount} electric heater room${d.heaterCount === 1 ? "" : "s"} on`);
  if (d.hotWater === true) add("water", "water", "Hot water heating");
  if (d.away) add("away", "away", `Away${d.awayReason ? ` (${d.awayReason})` : ""}: frost protection only`);
  if (d.night) add("moon", "night", "Night settings");
  if (d.monitor) add("eye", "watch", "Watching only: not controlling yet");
  return out.length ? `<span class="inds">${out.join("")}</span>` : "";
}

const LOGO = '<svg viewBox="0 0 256 256" aria-hidden="true"><rect width="256" height="256" rx="58" fill="#101826"/><path d="M128 50L206 112V118H50V112Z" fill="#FF6B3D"/><path d="M50 126H206V160H50Z" fill="#FFB547"/><path d="M50 168H206V206H50Z" fill="#3D8BFF"/></svg>';
const CHEV = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9.5l6 6 6-6"/></svg>';
const SPIN = '<svg class="spin" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" class="trk"/><path d="M12 3a9 9 0 0 1 9 9" class="arc"/></svg>';

const ICON_PERSON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7" r="3.6"/><path d="M4.8 20.5c0-4 3.2-7 7.2-7s7.2 3 7.2 7z"/></svg>';
const ICON_BOLT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z"/></svg>';
const ICON_WINDOW = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3.5" width="14" height="17" rx="1.5"/><path d="M12 3.5v17M5 12h14"/></svg>';
const ICON_CLOCK = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>';
const ICON_CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
const ICON_FLAME = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.2 1.2-3.6 2.4-4.6.2 1.6 1 2.6 2.1 3C11 8.8 11.4 5.6 12 3z"/></svg>';

const MODE_ICON = {
  off: '<path d="M12 3v8"/><path d="M6.6 6.6a7.5 7.5 0 1 0 10.8 0"/>',
  one_cycle: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v4h-4"/><path d="M11 10.5l1.5-1v6"/>',
  auto: '<path d="M8 8.5a3.5 3.5 0 1 0 0 7c2.6 0 5.4-7 8-7a3.5 3.5 0 1 1 0 7c-2.6 0-5.4-7-8-7z"/>',
};

function modeBar(current) {
  return `<div class="modebar" role="radiogroup" aria-label="Heating mode">
    ${Object.entries(MODE_LABEL).map(([k, v]) => `
      <button class="m-${k}" role="radio" aria-checked="${current === k}" data-mode="${k}" title="${MODE_TIP[k]}">
        <svg viewBox="0 0 24 24" aria-hidden="true">${MODE_ICON[k]}</svg><span>${v}</span>
      </button>`).join("")}
  </div>`;
}

const rooms_ = (n) => (n === 1 ? "1 room" : `${n} rooms`);
const STATUS_SENTENCE = {
  heating: (n, d) => n ? `Heating ${rooms_(n)}`
    : d.called && !d.firing ? "Boiler starting"
    : d.holdUntil ? `Boiler protection until ${hhmm(d.holdUntil)}`
    : /min run/.test(d.reason || "") ? "Boiler finishing its minimum run" : "Heating",
  idle: (n, d) => (d.waitingRooms ? `Not heating, ${rooms_(d.waitingRooms)} waiting` : "Not heating, nothing needs it"),
  paused: () => "Paused for hot water",
  waiting: () => "Waiting for boiler rest time",
  off: () => "Heating is off",
  away: (n, d) => `Away${d.awayReason ? ` (${d.awayReason})` : ""}: frost protection only`,
  fault: () => "Room sensors unavailable",
  disabled: () => "Controller disabled",
  testing: () => "Heat test running",
  starting: () => "Starting up",
};

class SmartHeatingCard extends HTMLElement {
  disconnectedCallback() {
    clearInterval(this._ocTimer);
    clearTimeout(this._confirmTimer);
  }

  setConfig(config) {
    this._config = config || {};
    this._open = null;
    this._showLog = false;
    this._expanded = false;
    this._calOpen = false;
    this._winOpen = false;
    this._aboutOpen = new Set();  // rooms whose "Room profile" is unfolded
    this._tip = null;
    this._energyOpen = false;
    this._pending = {};
    this._timers = {};
    this._confirmStart = false;
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "icon", selector: { icon: {} } },
        { name: "hide_title", selector: { boolean: {} } },
        { name: "layout", selector: { select: { mode: "dropdown", options: [
          { value: "compact", label: "Compact" }, { value: "full", label: "Full" }] } } },
      ],
      computeLabel: (f) => ({ title: "Title", icon: "Icon", hide_title: "Hide title and icon", layout: "Layout" }[f.name]),
      computeHelper: (f) => ({ title: "Default: Smart Heating", icon: "Empty: the Smart Heating logo" }[f.name]),
    };
  }

  static getStubConfig() {
    return {};
  }

  _titleHtml() {
    if (this._config.hide_title) return "";
    const icon = this._config.icon
      ? `<ha-icon icon="${esc(this._config.icon)}"></ha-icon>`
      : `<span class="logo">${LOGO}</span>`;
    return `<span class="ttl">${icon}<span>${esc(this._config.title || "Smart Heating")}</span></span>`;
  }

  getCardSize() {
    return this._config?.layout === "full" ? 9 : 2;
  }

  set hass(hass) {
    this._hass = hass;
    const model = this._model();
    const sig = JSON.stringify(model);
    if (sig === this._sig) return;
    this._sig = sig;
    this._data = model;
    this._render();
  }

  /* ---------- discovery ---------- */

  _model() {
    const hass = this._hass;
    const regs = hass.entities || {};
    const byDevice = {};
    for (const [id, reg] of Object.entries(regs)) {
      if (reg.platform !== "smart_heating") continue;
      const st = hass.states[id];
      if (!st) continue;
      (byDevice[reg.device_id] = byDevice[reg.device_id] || []).push(st);
    }

    const house = {};
    const rooms = [];
    for (const states of Object.values(byDevice)) {
      const need = states.find((s) => s.entity_id.startsWith("sensor.") && "deficit" in s.attributes);
      if (!need) {
        for (const s of states) {
          if (s.entity_id.startsWith("sensor.") && "boiler_demand" in s.attributes) house.status = s;
          else if (s.attributes.kind === "house_temperature") house.temp = s;
          else if (s.attributes.kind === "outdoor_day_mean") house.outdoor = s;
          else if (s.attributes.kind === "calibration") house.cal = s;
          else if (s.attributes.kind === "gas_today") house.gas = s;
          else if (s.attributes.kind === "heating_hours_today") house.hours = s;
          else if (s.attributes.kind === "gas_cost_today") house.cost = s;
          else if (s.attributes.kind === "electric_today") house.elec = s;
          else if (s.attributes.kind === "electric_cost_today") house.elecCost = s;
          else if (s.attributes.kind === "hot_water_gas_today") house.hwGas = s;
          else if (s.attributes.kind === "other_gas_today") house.otherGas = s;
          else if (s.attributes.kind === "other_electricity_today") house.otherElec = s;
          else if (s.attributes.kind === "decision_log") house.log = s;
          else if (s.attributes.kind === "window_advice") house.windows = s;
          else if (s.attributes.kind === "heat_retention" && s.attributes.scope === "house") house.retention = s;
          else if (s.attributes.kind === "floor_temperature") (house.floors = house.floors || {})[s.attributes.floor] = s;
          else if (s.entity_id.startsWith("select.") && s.attributes.options?.includes("one_cycle")) house.mode = s;
          else if (s.entity_id.startsWith("switch.") && s.entity_id.includes("monitor")) house.monitor = s;
          else if (s.attributes.kind === "house_target") house.target = s;
        }
        continue;
      }
      const decision = states.find((s) => s.entity_id.startsWith("sensor.") && "valve_command" in s.attributes);
      const override = states.find((s) => s.entity_id.startsWith("select."));
      const setp = states.find((s) => s.attributes.kind === "room_target");
      const energy = states.find((s) => s.attributes.kind === "room_energy");
      const byKind = (k) => states.find((s) => s.attributes.kind === k);
      const tau = byKind("heat_loss_tau"), warm = byKind("warm_up_rate"), pred = byKind("predicted_2h");
      const ret = states.find((s) => s.attributes.kind === "heat_retention" && !s.attributes.scope);
      const a = need.attributes;
      rooms.push({
        name: (hass.devices?.[regs[need.entity_id]?.device_id]?.name) || need.entity_id,
        floor: a.floor ?? 0,
        floorName: a.floor_name,
        priority: a.priority,
        temp: a.temperature != null && !isNaN(parseFloat(a.temperature)) ? parseFloat(a.temperature) : null,
        target: a.target,
        comfort: a.comfort,
        trend: a.trend,
        occupied: a.occupied,
        hasTrv: a.has_trv,
        hasHeater: a.has_heater === true,
        heaterOn: a.heater_on === true,
        heatingNow: a.heating_now === true,
        radiator: a.radiator !== false,
        callsBoiler: a.calls_boiler !== false,
        roomState: a.room_state,  // controlled, follows_boiler, watched, not_working
        heaterStopped: a.heater_stopped || null,
        targetSource: a.target_source,  // which target applies: safety (frost), baseline, comfort (in use), manual
        inUse: a.target_source === "comfort",
        kwh: num(energy?.state),
        powerW: energy?.attributes.power_now_w,
        roomCost: energy?.attributes.cost_today,
        override: override?.state || "auto",
        overrideEntity: override?.entity_id,
        setpoint: num(setp?.state),
        setpointEntity: setp?.entity_id,
        vsHouse: setp?.attributes.vs_house,
        overrideUntil: a.override_until,
        verdict: decision?.state || "idle",
        level: need.state,
        deficit: a.deficit,
        tau: num(tau?.state),
        gain: tau?.attributes.free_heat_gain,
        calibration: tau?.attributes.calibration,
        warmup: num(warm?.state),
        grade: ret?.attributes.grade,
        gradeRange: ret?.attributes.grade_range,
        settled: ret?.attributes.settled,
        tauLow: ret?.attributes.tau_low,
        tauHigh: ret?.attributes.tau_high,
        rating: ret?.attributes.rating,
        retScore: num(ret?.state),
        pred2: num(pred?.state),
        pred8: pred?.attributes.predicted_8h,
        hoursToBase: pred?.attributes.hours_to_baseline,
        predBase: pred?.attributes.baseline,
        reason: decision?.attributes.reason || a.reason || "",
      });
    }
    rooms.sort((x, y) => (y.floor - x.floor) || x.name.localeCompare(y.name));

    return {
      rooms,
      status: house.status?.state,
      reason: house.status?.attributes.reason,
      firing: house.status?.attributes.boiler_firing,
      demand: house.status?.attributes.boiler_demand === true,
      hasBoiler: house.status?.attributes.has_boiler === true,
      hotWater: house.status?.attributes.hot_water,
      night: house.status?.attributes.night === true,
      away: house.status?.attributes.away === true,
      heaterCount: (house.status?.attributes.heater_rooms || []).length,
      radiatorCount: (house.status?.attributes.radiator_rooms || []).length,
      calling: (house.status?.attributes.heating_rooms || []).length,
      wanted: (house.status?.attributes.wanted_rooms || []).length,
      waitingRooms: rooms.filter((r) => r.verdict === "deferred").length,
      called: house.status?.attributes.boiler_called === true,
      awayReason: house.status?.attributes.away_reason || null,
      holdUntil: house.status?.attributes.boiler_hold_until || null,
      currency: hass.config?.currency || "GBP",
      monitor: house.status ? house.status.attributes.monitor_only === true : house.monitor?.state === "on",
      mode: house.mode?.state,
      oneCycleWait: house.status?.attributes.one_cycle_wait || null,
      modeEntity: house.mode?.entity_id,
      houseTemp: num(house.temp?.state),
      calibrated: house.cal ? house.cal.attributes.calibrated === true : true,
      calPct: num(house.cal?.state),
      calPhase: house.cal?.attributes.learning_now,
      cal: house.cal?.attributes || {},
      win: house.windows && house.windows.state !== "none" && house.windows.state !== "unavailable"
        ? { action: house.windows.state, reason: house.windows.attributes.reason, minutes: house.windows.attributes.minutes,
            advice: house.windows.attributes.advice } : null,
      calAvailable: house.cal ? house.cal.attributes.available !== false : false,
      heatTest: house.cal?.attributes.heat_test_min_left ?? null,
      target: num(house.target?.state),
      targetEntity: house.target?.entity_id,
      baseDay: house.target?.attributes.baseline_day,
      baseNight: house.target?.attributes.baseline_night,
      safety: house.target?.attributes.safety,
      gas: num(house.gas?.state),
      gasEntity: house.gas?.entity_id,
      gasMeasured: house.gas?.attributes.measured === true,
      cost: num(house.cost?.state),
      costEntity: house.cost?.entity_id,
      elec: num(house.elec?.state),
      elecEntity: house.elec?.entity_id,
      elecCost: num(house.elecCost?.state),
      elecCostEntity: house.elecCost?.entity_id,
      hwGas: num(house.hwGas?.state),
      hwGasEntity: house.hwGas?.entity_id,
      hwGasCost: house.hwGas?.attributes.cost,
      hwHours: house.hwGas?.attributes.hot_water_hours,
      otherGas: num(house.otherGas?.state),
      otherGasEntity: house.otherGas?.entity_id,
      otherGasCost: house.otherGas?.attributes.cost,
      gasHours: house.gas?.attributes.heating_hours,
      heatHours: num(house.hours?.state),
      heatHoursEntity: house.hours?.entity_id,
      elecHours: house.elec?.attributes.heater_hours,
      otherElec: num(house.otherElec?.state),
      otherElecEntity: house.otherElec?.entity_id,
      elecProjected: house.elec?.attributes.projected_today_kwh,
      elecMeasured: house.elec?.attributes.measured === true,
      elecEst: house.elec ? house.elec.attributes.source !== "smart_meter" && house.elec.attributes.measured !== true : false,
      log: (house.log?.attributes.entries || []).slice(0, 15),
      houseGrade: house.retention?.attributes.grade,
      houseSettled: house.retention?.attributes.settled !== false,
      houseScore: num(house.retention?.state),
      outdoor: num(house.outdoor?.attributes.now),
      floorNames: Object.fromEntries(rooms.filter((r) => r.floorName).map((r) => [r.floor, r.floorName])),
      floorTemps: Object.fromEntries(Object.entries(house.floors || {}).map(([f, s]) => [f, num(s.state)])),
    };
  }

  /* ---------- actions ---------- */

  _setMode(mode) {
    if (!this._data.modeEntity) return;
    this._call("select", "select_option", { entity_id: this._data.modeEntity, option: mode });
  }

  _call(domain, service, data) {
    this._hass.callService(domain, service, data).catch((err) => {
      this._error = err?.message || String(err);
      this._render();
      clearTimeout(this._errTimer);
      this._errTimer = setTimeout(() => { this._error = null; this._render(); }, 10000);
    });
  }

  _step(entity, current, delta) {
    if (!entity) return;
    const a = this._hass.states[entity]?.attributes || {};
    const lo = a.min ?? 10, hi = a.max ?? 25, step = a.step ?? 0.5;
    const base = this._pending[entity] ?? current;
    if (base == null) return;  // no value yet: don't send a made-up one
    const v = Number(Math.min(hi, Math.max(lo, Math.round((base + Math.sign(delta) * step) / step) * step)).toFixed(2));
    this._pending[entity] = v;
    clearTimeout(this._timers[entity]);
    this._timers[entity] = setTimeout(() => {
      this._call("number", "set_value", { entity_id: entity, value: v });
      setTimeout(() => { delete this._pending[entity]; this._sig = null; this.hass = this._hass; }, 1500);
    }, 700);
    this._render();
  }

  _shown(entity, value) {
    return this._pending[entity] ?? value;
  }

  _setOverride(entity, option) {
    this._call("select", "select_option", { entity_id: entity, option });
  }


  /* ---------- helpers: tips, steppers, calibration ---------- */

  _info(key, label = "More info") {
    return `<button class="info ${this._tip === key ? "on" : ""}" data-tip="${key}" aria-label="${esc(label)}" aria-expanded="${this._tip === key}">${ICON_INFO}</button>`;
  }

  _tipBox(key, text) {
    return this._tip === key ? `<p class="tip" role="note">${esc(text)}</p>` : "";
  }

  _stepper(entity, value, label, key, tip, sub = "") {
    const v = this._shown(entity, value);
    const pending = entity in this._pending;
    return `
      <div class="stepper-row">
        <span class="sp-label">${esc(label)}${this._info(key)}${sub ? `<small>${esc(sub)}</small>` : ""}</span>
        <span class="stepper ${pending ? "pending" : ""}" role="group" aria-label="${esc(label)}">
          <button data-step="-1" data-entity="${entity}" data-value="${value ?? ""}" aria-label="Lower">−</button>
          <output aria-live="polite">${v == null ? "–" : Number(v).toFixed(1)}<small>°</small></output>
          <button data-step="1" data-entity="${entity}" data-value="${value ?? ""}" aria-label="Raise">+</button>
        </span>
      </div>
      ${this._tipBox(key, tip)}`;
  }

  _houseStepper(d) {
    if (!d.targetEntity || d.mode === "off") return "";
    const comfortVals = d.rooms.map((r) => r.setpoint).filter((x) => x != null);
    const lo = comfortVals.length ? Math.min(...comfortVals) : null;
    const hi = comfortVals.length ? Math.max(...comfortVals) : null;
    const range = lo == null ? "" : lo === hi ? `${lo.toFixed(1)}°` : `${lo.toFixed(1)} to ${hi.toFixed(1)}°`;
    const tip = `Moves every room together. Rooms in use heat to their own target (now ${range}). `
      + `Empty rooms stay at ${fmt(d.baseDay)} by day and ${fmt(d.baseNight)} at night. Fine-tune a room by tapping it.`;
    return this._stepper(d.targetEntity, d.target, "House target", "house", tip);
  }

  _badge(d) {
    if (d.heatTest != null) return `<button class="badge test" data-cal>${ICON_FLAME}Heat test ${fmtMin(d.heatTest)}</button>`;
    if (!d.calibrated) return `<button class="badge cal" data-cal aria-expanded="${this._calOpen}" title="${esc(d.calPhase ? `Now: ${d.calPhase}` : "Learning how your house holds heat")}">Learning ${d.calPct ?? 0}%<span class="chev2 ${this._calOpen ? "up" : ""}">${CHEV}</span></button>`;
    return "";
  }

  _winBadge(d) {
    if (!d.win) return "";
    const open = d.win.action === "open";
    const label = open ? `Open${d.win.advice === "dry" && d.win.minutes ? ` ${d.win.minutes}min` : ""}` : "Close";  // short: fits a phone
    return `<button class="badge win ${open ? "open" : "close"}" data-win aria-expanded="${this._winOpen}" aria-label="${open ? "Open windows" : "Close windows"}" title="${esc(d.win.reason || "")}">${ICON_WINDOW}${label}</button>`;
  }

  _winBox(d) {
    if (!d.win || !this._winOpen || !d.win.reason) return "";
    return `<div class="winbox" role="status">${esc(d.win.reason)}</div>`;
  }

  _ready(d) {
    if (!d.monitor || d.heatTest != null) return "";
    if (this._confirmStart) {
      const others = d.cal.competing_automations || [];
      return `<div class="ready confirm" role="alertdialog" aria-label="Start heating">
        <span>Start heating now? Smart Heating will switch the boiler and TRVs.${others.length
          ? ` Turn these automations off first, they also switch the heating: <b>${esc(others.join(", "))}</b>.` : ""}</span>
        <span class="actions"><button class="primary" data-confirm="start">Start heating</button><button data-confirm="cancel">Cancel</button></span>
      </div>`;
    }
    const learned = d.calibrated && d.calAvailable;
    return `<div class="ready"><span>${learned ? ICON_CHECK : ""}${learned ? "Learning done. Watching only." : "Watching only: decisions are logged, nothing is switched."}</span>
      <button class="primary" data-start>Start heating</button></div>`;
  }

  _oneCycleBox(d) {
    const w = d.oneCycleWait;
    if (!w || d.mode !== "one_cycle") return "";
    return `<div class="ocbox" role="status">
      <p><b>One Cycle: nothing needs heat yet</b></p>
      <ul>${(w.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      <p class="muted">Switches to Off in <b data-countdown="${esc(w.until)}">${fmtLeft(w.until)}</b> unless something changes. Heat now on a room starts it straight away.</p>
      <div class="actions">${w.all_rooms ? "" : `<button class="primary" data-oc="all">${ICON_FLAME}Heat all rooms below target</button>`}
        <button data-oc="off">Off now</button></div>
    </div>`;
  }

  _calPanel(d) {
    if (!(this._calOpen || d.heatTest != null) || (d.calibrated && d.heatTest == null)) return "";
    const c = d.cal;
    const bar = (have, need) => {
      const pct = need ? Math.min(100, Math.round((have / need) * 100)) : 0;
      return `<span class="bar" aria-hidden="true"><i style="width:${pct}%"></i></span>`;
    };
    const row = (key, label, have, need, unit, tip, text) => `
      <div class="need-row ${have >= need ? "done" : ""}">
        <span>${esc(label)}${this._info(key)}</span>
        ${bar(have, need)}
        <span class="val">${have >= need ? ICON_CHECK : text || `${fmtN(have)} of ${fmtN(need)}${unit}`}</span>
      </div>${this._tipBox(key, tip)}`;
    const errNeed = c.uncertainty_needed_pct ?? 25;
    const steady = c.uncertainty_pct == null
      ? row("steady", "Steady result", c.cooling_days ?? 0, c.cooling_days_needed, " days",
          `Tested by refitting with one group of days left out at a time: the answer must barely move. Needs cooling data from ${c.cooling_days_needed} different days first.`)
      : row("steady", "Steady result", Math.min(errNeed, (errNeed * errNeed) / Math.max(c.uncertainty_pct, 1)), errNeed, "",
          `Tested by refitting with one group of days left out at a time: the answer must barely move. Needs ±${errNeed}% or better. Times with a shower, cooking or sun are left out, so this can take a week or two.`,
          `${c.uncertainty_pct > 100 ? "over ±100%" : `±${c.uncertainty_pct}%`} (needs ±${errNeed}%)`);
    const eta = c.eta_hours ? (c.eta_hours > 36 ? `about ${Math.round(c.eta_hours / 24 * 2) / 2} days left` : `about ${c.eta_hours} h left`) : "almost done";
    const rise = c.heat_test_rise ?? 1, cap = c.heat_test_cap ?? 21.5, maxMin = c.heat_test_max_min ?? 135;
    const night = c.night_cooling_hours != null ? `Each night gives up to ${fmtN(c.night_cooling_hours)} h of cooling data.` : "";
    const test = d.heatTest != null
      ? `<div class="speed"><p>${SPIN}<b>Heat test running</b>, ${fmtMin(d.heatTest)} left. Rooms that need data are heating gently; each stops at ${fmtN(rise)}° warmer, never above ${fmtN(cap)}°.</p>
         <button data-test="stop">Stop test</button></div>`
      : c.can_heat_test && c.heating_hours_left > 0 ? `
        <div class="speed">
          <p><b>Speed it up</b></p>
          <ol>
            <li>${(c.competing_automations || []).length ? `
              <p class="warn">Turn off these automations first, they also switch the heating: <b>${esc(c.competing_automations.join(", "))}</b>.</p>
              <button data-test="start">${ICON_FLAME}Run heat test</button>
              <button class="link" data-test="force">Run anyway</button>` : `
              <button class="primary" data-test="start">${ICON_FLAME}Run heat test</button>`}
              <span>Gentle: only rooms that still need data, each warmed by about ${fmtN(rise)}° (never above ${fmtN(cap)}°), at most ${fmtDur(maxMin)}. Then the house cools. If anything else switches the heating, the test stops.</span></li>
            <li><span>Leave the heating off overnight. ${night}</span></li>
          </ol>
        </div>`
      : `<div class="speed"><p><b>Speed it up</b>: leave the heating off overnight. ${night}</p></div>`;
    if (d.heatTest != null && !this._calOpen) return `<div class="calpanel">${test}</div>`;
    if (c.cooling_hours_needed == null) return `<div class="calpanel">${test}</div>`;  // nothing to learn from: no rows to show
    return `
      <div class="calpanel">
        <p class="lead">Learning how your house holds heat: ${c.rooms_done} of ${c.rooms_needed} rooms ready, ${eta}.</p>
        ${row("cool", "Cooling data", c.cooling_hours, c.cooling_hours_needed, " h",
          `Counted while the radiators have been off for at least ${fmtDur(c.cooling_after_min ?? 60)}. Nights with the heating off fill this fastest.`)}
        ${row("range", "Temperature range", c.variety_c, c.variety_needed_c, "°",
          `The gap between inside and outside needs to vary by ${fmtN(c.variety_needed_c)}°. A warm-up followed by a cool-down does it.`)}
        ${row("heat", "Heating data", c.heating_hours, c.heating_hours_needed, " h",
          "Counted while the boiler runs with the room's radiator open. The heat test fills this in one go.")}
        ${steady}
        <p class="now">Now: ${esc(d.calPhase || "starting")}</p>
        <p class="muted">${d.monitor ? "Watching only until you tap Start heating. Learning carries on either way."
          : "Heating runs as usual. Predictions and insulation grades appear room by room as they are learned."}</p>
        ${test}
      </div>`;
  }

  /* ---------- render ---------- */

  _render() {
    const d = this._data;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });

    if (!d.rooms.length) {
      this.shadowRoot.innerHTML = `${STYLE}<ha-card><div class="empty">
        Add rooms in Settings, Devices &amp; services, Smart Heating, then <b>Add room</b>.
      </div></ha-card>`;
      return;
    }

    const floors = [...new Set(d.rooms.map((r) => r.floor))].sort((a, b) => b - a);
    let statusText = (STATUS_SENTENCE[d.status] || (() => d.status || ""))(d.calling, d);
    if (d.monitor && d.heatTest == null && d.status === "heating") {
      statusText = d.wanted ? `Would heat ${rooms_(d.wanted)}` : "Would finish the boiler's minimum run";
    }
    if (this._config.layout !== "full") {
      this._renderCompact(d, floors, statusText);
      return;
    }

    this.shadowRoot.innerHTML = `${STYLE}
      <ha-card>
        <header>
          <div class="title">
            <h2>${this._titleHtml() || esc(this._config.title || "Smart Heating")}</h2>
            <p class="status s-${d.status}">${statusDot(d)}${esc(statusText)}${indicators(d)}${this._badge(d)}${this._winBadge(d)}</p>
          </div>
        </header>
        ${this._winBox(d)}
        ${this._calPanel(d)}
        ${this._ready(d)}
        ${this._oneCycleBox(d)}
        ${this._error ? `<p class="err" role="alert">${esc(this._error)}</p>` : ""}
        ${modeBar(d.mode)}
        ${this._houseStepper(d)}

        ${this._config.layout === "full" ? `
        <div class="section">
          <svg class="roof" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
            <polyline points="0,10 50,1 100,10" />
          </svg>
          ${floors.map((f) => this._floor(f, d.rooms.filter((r) => r.floor === f))).join("")}
          <div class="ground-line" aria-hidden="true"></div>
        </div>` : `
        ${compactHouse(floors.map((f) => this._compactFloor(f, d.rooms.filter((r) => r.floor === f))).join(""))}`}

        <footer class="${this._config.layout === "full" ? "" : "slim"}">
          <dl>
            ${d.houseTemp != null ? `<div><dt>House</dt><dd>${d.houseTemp.toFixed(1)}°</dd></div>` : ""}
            ${d.outdoor != null ? `<div><dt>Outside now</dt><dd>${d.outdoor.toFixed(1)}°</dd></div>` : ""}
            ${energySummary(d, this._energyOpen)}
          </dl>
          <p>${esc(d.reason || "")}</p>
          <button class="logbtn" data-log aria-expanded="${this._showLog}">${this._showLog ? "Hide log" : "Show log"}</button>
        </footer>
        ${this._energyOpen ? energyBreakdown(d) : ""}
        ${this._showLog ? this._logPanel(d.log) : ""}
      </ha-card>`;

    this._bind();
  }

  _floor(floor, rooms) {
    const open = rooms.find((r) => r.name === this._open);
    return `
      <div class="floor">
        <div class="floor-name">${this._floorLabel(floor)}${this._data.floorTemps[floor] != null ? `<span>${this._data.floorTemps[floor].toFixed(1)}°</span>` : ""}</div>
        <div class="rooms">
          ${rooms.map((r) => this._room(r)).join("")}
          ${open ? this._actions(open) : ""}
        </div>
      </div>`;
  }

  _renderCompact(d, floors, statusText) {
    const hue = tempHue(d.houseTemp);
    const badge = this._badge(d) + this._winBadge(d);
    const up = [...floors].sort((a, b) => a - b);
    const floorPills = up.length < 2 ? "" : up.map((f) => {
      const rooms = d.rooms.filter((r) => r.floor === f);
      const heating = rooms.some((r) => r.heatingNow);
      const t = d.floorTemps[f];
      return `<span class="fp ${heating ? "on" : ""}">${heating ? `<i aria-label="heating"></i>` : ""}${this._floorLabel(f)}${t != null ? ` <b>${t.toFixed(1)}°</b>` : ""}</span>`;
    }).join("");
    const ex = this._expanded;
    this.shadowRoot.innerHTML = `${STYLE}
      <ha-card class="mini" style="--h:${hue}">
        <div class="tint" aria-hidden="true"></div>
        <div class="summary" data-expand role="button" tabindex="0" aria-expanded="${ex}" aria-label="${ex ? "Collapse" : "Expand"} heating details">
          <div class="hdr">
            ${this._titleHtml()}
            <span class="st s-${d.status}">${statusDot(d)}<span class="stt">${esc(statusText)}</span></span>
            <span class="chev ${ex ? "up" : ""}" aria-hidden="true">${CHEV}</span>
          </div>
          <div class="row1">
            <span class="big">${d.houseTemp != null ? d.houseTemp.toFixed(1) : "–"}<small>°</small></span>
            ${badge || indicators(d) ? `<span class="sub">${indicators(d)}${badge}</span>` : ""}
          </div>
        </div>
        ${this._winBox(d)}
        ${this._calPanel(d)}
        ${this._ready(d)}
        ${this._oneCycleBox(d)}
        ${this._error ? `<p class="err" role="alert">${esc(this._error)}</p>` : ""}
        <div class="row2">
          ${floorPills}
          ${d.outdoor != null ? `<span class="fp out">Out <b>${d.outdoor.toFixed(1)}°</b></span>` : ""}
        </div>
        ${modeBar(d.mode)}
        ${this._houseStepper(d)}
        ${ex ? `
        <div class="more">
          ${compactHouse(floors.map((f) => this._compactFloor(f, d.rooms.filter((r) => r.floor === f))).join(""))}
          <footer class="slim">
            <dl>
              ${energySummary(d, this._energyOpen)}
              ${d.houseGrade ? `<div ${d.houseSettled ? "" : 'class="unsettled" title="Still settling: it firms up as rooms are learned"'}><dt>Insulation</dt><dd><span class="grade g-${d.houseGrade}">${d.houseGrade}</span> ${d.houseScore}</dd></div>` : ""}
            </dl>
            <button class="logbtn" data-log aria-expanded="${this._showLog}">${this._showLog ? "Hide log" : "Log"}</button>
          </footer>
          ${this._energyOpen ? energyBreakdown(d) : ""}
          ${this._showLog ? this._logPanel(d.log) : ""}
        </div>` : ""}
      </ha-card>`;
    this._bind();
  }

  _bind() {
    const root = this.shadowRoot;
    const toggle = (e) => {
      if (e.target.closest("button")) return;
      this._expanded = !this._expanded;
      if (!this._expanded) { this._open = null; this._showLog = false; }
      this._render();
    };
    const sum = root.querySelector("[data-expand]");
    sum?.addEventListener("click", toggle);
    sum?.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(e); } });
    root.querySelectorAll("[data-tip]").forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      this._tip = this._tip === b.dataset.tip ? null : b.dataset.tip;
      this._render();
    }));
    root.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      this._step(b.dataset.entity, b.dataset.value === "" ? null : parseFloat(b.dataset.value), parseFloat(b.dataset.step));
    }));
    root.querySelectorAll("[data-about]").forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      const name = b.dataset.about;
      if (!this._aboutOpen.delete(name)) this._aboutOpen.add(name);
      this._render();
    }));
    root.querySelector("[data-win]")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._winOpen = !this._winOpen;
      this._render();
    });
    root.querySelector("[data-cal]")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._calOpen = !this._calOpen;
      this._render();
    });
    root.querySelectorAll("[data-test]").forEach((b) => b.addEventListener("click", () => {
      this._error = null;
      const t = b.dataset.test;
      this._call("smart_heating", "heat_test", t === "stop" ? { start: false } : { start: true, ignore_automations: t === "force" });
    }));
    root.querySelector("[data-start]")?.addEventListener("click", () => {
      this._confirmStart = true;  // ask first; cancels itself after 10 s
      clearTimeout(this._confirmTimer);
      this._confirmTimer = setTimeout(() => { this._confirmStart = false; this._render(); }, 10000);
      this._render();
    });
    root.querySelectorAll("[data-confirm]").forEach((b) => b.addEventListener("click", () => {
      clearTimeout(this._confirmTimer);
      this._confirmStart = false;
      this._error = null;
      if (b.dataset.confirm === "start") this._call("smart_heating", "start_control", {});
      this._render();
    }));
    root.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => this._setMode(b.dataset.mode)));
    root.querySelectorAll("[data-energy]").forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      this._energyOpen = !this._energyOpen;
      this._render();
    }));
    root.querySelectorAll("[data-oc]").forEach((b) => b.addEventListener("click", () => {
      this._error = null;
      if (b.dataset.oc === "all") this._call("smart_heating", "one_cycle", { all_rooms: true });
      else this._setMode("off");
    }));
    clearInterval(this._ocTimer);
    const cd = root.querySelector("[data-countdown]");
    if (cd) this._ocTimer = setInterval(() => { cd.textContent = fmtLeft(cd.dataset.countdown); }, 1000);
    root.querySelectorAll("[data-more]").forEach((el) => {
      const open = (e) => {
        e.stopPropagation();
        this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: el.dataset.more }, bubbles: true, composed: true }));
      };
      el.addEventListener("click", open);
      el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(e); } });
    });
    root.querySelectorAll("[data-room]").forEach((b) => b.addEventListener("click", () => {
      this._open = this._open === b.dataset.room ? null : b.dataset.room;
      this._render();
    }));
    root.querySelector("[data-log]")?.addEventListener("click", () => {
      this._showLog = !this._showLog;
      this._render();
    });
    root.querySelectorAll("[data-ov]").forEach((b) => b.addEventListener("click", () => this._setOverride(b.dataset.entity, b.dataset.ov)));
  }

  _floorLabel(f) {
    const n = this._data.floorNames?.[f];
    if (!n) return FLOOR_NAME[f] ?? f;
    return n.replace(/\s*floor$/i, "") || n;
  }

  _state(r) {
    if (r.roomState === "watched") return "watched";
    if (r.override === "off") return "off";
    if (r.heatingNow) return r.verdict === "piggyback" ? "piggyback" : "approved";  // incl. an always-open radiator
    return r.verdict === "approved" || r.verdict === "piggyback" ? "wants" : r.verdict;
  }

  _compactFloor(floor, rooms) {
    const open = rooms.find((r) => r.name === this._open);
    const avg = this._data.floorTemps[floor];
    return `
      <div class="cfloor">
        <div class="clabel">${this._floorLabel(floor)}${avg != null ? `<span>${avg.toFixed(1)}°</span>` : ""}</div>
        <div class="chips">
          ${rooms.map((r) => this._chip(r)).join("")}
        </div>
        ${open ? `<div class="cdetail">${this._actions(open)}</div>` : ""}
      </div>`;
  }

  _chip(r) {
    const state = this._state(r);
    const label = r.override === "off" ? "off by you" : (STATE_LABEL[state] || state).toLowerCase();
    return `
      <button class="chip v-${state} ${r.hasTrv || r.hasHeater ? "" : "dumb"}" data-room="${esc(r.name)}"
        aria-expanded="${this._open === r.name}" aria-label="${esc(r.name)}, ${r.temp == null ? "no reading" : r.temp.toFixed(1) + " degrees"}, ${esc(label)}"
        title="${esc(r.name)}: ${esc(r.reason)}">
        ${r.inUse ? `<span class="inuse" title="In use" role="img" aria-label="In use">${ICON_PERSON}</span>` : ""}
        ${r.heaterOn ? `<span class="bolt" aria-label="heater on">${ICON_BOLT}</span>` : ""}
        <span class="cname">${esc(r.name)}</span>
        <span class="ctemp">${r.temp == null ? "–" : r.temp.toFixed(1)}</span>
      </button>`;
  }

  _room(r) {
    const state = this._state(r);
    const label = r.override === "off" ? "Off by you"
      : r.override === "heat" && state !== "approved" ? "Heat requested"
      : STATE_LABEL[state] || state;
    const trend = r.trend == null ? "" : r.trend > 0.15 ? " ↑" : r.trend < -0.15 ? " ↓" : "";
    return `
      <button class="room v-${state} ${r.hasTrv || r.hasHeater ? "" : "dumb"}" data-room="${esc(r.name)}"
        aria-expanded="${this._open === r.name}"
        title="${esc(r.reason)}">
        <span class="name">${esc(r.name)}${r.inUse ? `<span class="inuse" title="In use" role="img" aria-label="In use">${ICON_PERSON}</span>` : ""}</span>
        <span class="temp">${r.temp == null ? "–" : `${r.temp.toFixed(1)}°`}<small>${trend}</small></span>
        <span class="meta">${esc(label)}${r.target != null ? `<span class="target">to ${Number(r.target).toFixed(1)}°</span>` : ""}</span>
      </button>`;
  }

  _logPanel(entries) {
    if (!entries.length) return `<div class="log"><p class="muted">No decisions logged yet.</p></div>`;
    const t = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return `<ol class="log">${entries.map((e) => `
      <li><time>${t(e.time)}</time><span>${e.room ? `<b>${esc(e.room)}</b> ` : ""}${esc(e.message)}</span></li>`).join("")}</ol>`;
  }

  _roomStepper(r) {
    if (!r.setpointEntity) return "";
    const d = this._data;
    const key = `room-${r.name}`;
    const vs = r.vsHouse == null || Math.abs(r.vsHouse) < 0.05 ? "same as house" : `${r.vsHouse > 0 ? "+" : ""}${Number(r.vsHouse).toFixed(1)}° vs house`;
    const tip = `${r.name} heats to this while in use (presence, lights, schedule or Heat now). Empty, it stays at ${fmt(d.baseDay)} by day and ${fmt(d.baseNight)} at night. `
      + (r.hasHeater ? "Its electric heater switches on its own, so it can differ from other rooms."
        : r.hasTrv ? "Its TRV opens and closes on its own, so it can differ from other rooms."
        : "No TRV here: it can ask for heat, but its radiator can't be shut, so it also warms with the rest of the house.");
    return this._stepper(r.setpointEntity, r.setpoint, "Target when in use", key, tip, vs);
  }

  /* ---------- room panel: state and scale on top, target and override, the rest folded away ---------- */

  _panelState(r) {
    if (r.roomState === "not_working") return ["No temperature", "off"];
    if (r.roomState === "watched") return ["Watched only", "idle"];
    if (r.override === "off") return ["Off by you", "off"];
    if (r.heaterStopped && !r.heatingNow) return ["Heater stopped", "wait"];
    const st = this._state(r);
    if (st === "approved" || st === "piggyback") return [STATE_LABEL[st], "heat"];
    if (r.override === "heat") return ["Heat requested", "wait"];
    if (st === "wants" || st === "deferred") return [STATE_LABEL[st], "wait"];
    if (st === "fault") return [STATE_LABEL.fault, "off"];
    if (r.temp != null && r.target != null && r.temp >= r.target) return ["Warm enough", "ok"];
    return [STATE_LABEL[st] || "Idle", "idle"];
  }

  // Why the room has the target it has: which temperature applies now, and what the others are.
  _why(r) {
    const d = this._data, use = fmt(r.setpoint ?? r.comfort);
    const until = r.overrideUntil ? ` until ${hhmm(r.overrideUntil)}` : "";
    if (r.override === "off") return { key: "frost", tag: "Turned off", text: `It only keeps above ${fmt(d.safety)} (frost protection).` };
    if (r.targetSource === "manual") return { key: "use", tag: "Heat now", text: `You asked for heat: it holds ${use}${until}.` };
    if (r.targetSource === "safety") {
      const tag = d.mode === "off" ? "Heating off" : d.away ? "Away" : "Frost protection";
      return { key: "frost", tag, text: `Only frost protection applies: it keeps above ${fmt(d.safety)}.` };
    }
    if (r.targetSource == null) return { key: "", tag: "No temperature", text: "It has no temperature reading, so it is left alone." };
    if (r.inUse) return { key: "use", tag: "In use", text: `Empty: ${fmt(d.baseDay)} by day, ${fmt(d.baseNight)} at night.` };
    return { key: d.night ? "night" : "day", tag: d.night ? "Empty, night" : "Empty", text: `In use: ${use}.` };
  }

  _gap(r) {
    if (r.temp == null || r.target == null) return "";
    const g = r.target - r.temp;
    if (g > 0.05) {
      const rate = r.heatingNow ? r.warmup || (r.trend > 0.05 ? r.trend : null) : r.trend > 0.05 ? r.trend : null;  // only when it is warming
      const m = rate ? Math.max(5, Math.round((g / rate) * 12) * 5) : null;
      return `${g.toFixed(1)}° to go${m ? `, ~${fmtDur(m)}` : ""}`;
    }
    return g < -0.05 ? `${(-g).toFixed(1)}° above` : "at target";
  }

  // Frost, night, empty and in-use temperatures on one line; the one that applies now is lit.
  _scale(r, why) {
    const d = this._data;
    const marks = [["frost", "Frost", d.safety], ["night", "Night", d.baseNight], ["day", "Empty", d.baseDay], ["use", "In use", r.setpoint ?? r.comfort]]
      .sort((a, b) => (b[0] === why.key) - (a[0] === why.key))  // equal temperatures: the one that applies stays
      .filter((m, i, all) => m[2] != null && all.findIndex((n) => n[2] === m[2]) === i);
    if (marks.length < 2) return "";
    const vals = [...marks.map((m) => m[2]), r.temp].filter((v) => v != null);
    const lo = Math.min(...vals) - 0.8, hi = Math.max(...vals) + 0.8;
    const x = (v) => (16 + ((v - lo) / (hi - lo)) * 268).toFixed(1);
    const deg = (v) => `${Number(v).toFixed(Number(v) % 1 ? 1 : 0)}°`;
    const ticks = marks.map(([k, label, v]) => `<g class="${k === why.key ? "on" : ""}"><line x1="${x(v)}" x2="${x(v)}" y1="26" y2="38"/>
      <text x="${x(v)}" y="51" text-anchor="middle">${label}</text><text class="v" x="${x(v)}" y="62" text-anchor="middle">${deg(v)}</text></g>`).join("");
    const now = r.temp == null ? "" : `<g class="now"><circle cx="${x(r.temp)}" cy="32" r="5"/><text x="${x(r.temp)}" y="16" text-anchor="middle">${r.temp.toFixed(1)}°</text></g>`;
    return `<svg class="rp-scale" viewBox="0 0 300 66" role="img" aria-label="${esc(r.name)} against its frost, night, empty and in-use temperatures">
      <line class="track" x1="10" x2="290" y1="32" y2="32"/>${ticks}${now}</svg>`;
  }

  _about(r, why) {
    const f = (v, unit = "°") => (v == null || isNaN(v) ? "–" : `${Number(v).toFixed(1)}${unit}`);
    const tile = (k, v, span = 1, tip = "") =>
      `<div class="rp-tile${span > 1 ? ` s${span}` : ""}"${tip ? ` title="${esc(tip)}"` : ""}><span>${k}</span><b>${v}</b></div>`;
    const lose = (h) => `With the heating off it loses about two thirds of its warmth over outside in ${h} h.`;
    const settling = r.settled === false && (r.calibration ?? 0) < 100;
    const ins = !r.grade ? null : settling
      ? { g: r.gradeRange || r.grade, t: "settling",
          tip: `${lose(r.gradeRange ? `${Math.round(r.tauLow)} to ${Math.round(r.tauHigh)}` : Math.round(r.tau))} Still settling.` }
      : { g: r.settled === false && r.gradeRange ? r.gradeRange : r.grade, t: SHORT_RATING[r.rating] || r.rating || "", tip: `${r.rating}. ${lose(Math.round(r.tau))}` };
    const base = f(r.predBase ?? this._data.baseDay);
    const forecast = r.pred2 == null ? "" : `<div class="rp-fc"><span>Prediction without heating</span>
      <p><b>${f(r.pred2)}</b> in 2 h · <b>${f(r.pred8)}</b> in 8 h · ${r.hoursToBase == null ? `stays above <b>${base}</b>` : r.hoursToBase === 0 ? `already at <b>${base}</b>` : `down to <b>${base}</b> in ${f(r.hoursToBase, " h")}`}</p></div>`;
    const tiles = [
      ins ? tile("Insulation", `<i class="grade g-${esc(String(ins.g).charAt(0))}">${esc(ins.g)}</i>${esc(ins.t)}`, 1, ins.tip) : "",
      r.warmup != null ? tile("Warm-up", f(r.warmup, "°/h"), 1, "How fast it warms while its radiator or heater is on.") : "",
      r.gain != null && r.tau != null ? tile("Free heat", `${r.gain >= 0 ? "+" : ""}${f(r.gain)}`, 1,
        "How much warmer than outside it settles with no heating at all: people, sun, cooking and the rooms around it.") : "",
      (!r.grade || r.warmup == null) && r.roomState !== "watched" && r.roomState !== "not_working" ? tile("Learning", `${r.calibration ?? 0}%`) : "",
      r.radiator && !r.hasTrv ? tile("Radiator", "No TRV, always open", 2) : "",
      r.radiator && !r.callsBoiler ? tile("Boiler", "Never starts it", 1, "This room heats when another room calls. Frost protection and Heat now can still start the boiler.") : "",
      r.hasHeater ? tile("Heater", r.heaterOn ? `on${r.powerW ? `, ${Math.round(r.powerW)} W` : ""}` : r.heaterStopped ? "kept off" : "off", 1,
        r.heaterStopped ? `Kept off: ${r.heaterStopped}` : "") : "",
      r.hasHeater && r.kwh != null ? tile("Today", `${r.kwh.toFixed(2)} kWh${r.roomCost != null ? ` · ${money(r.roomCost, this._data.currency)}` : ""}`, 2) : "",
    ].join("");
    const [tag, text] = r.roomState === "not_working" ? ["No temperature", "check its thermometer (battery, range)"]
      : r.roomState === "watched" ? ["Watched only", "nothing here can heat it"]
      : r.heaterStopped && !r.heatingNow ? ["Heater kept off", r.heaterStopped]
      : [why.tag, `target ${f(r.target)}, ${this._gap(r)}`];
    return `<div class="rp-fc sum" title="${esc(`${tag}: ${text}. ${why.text}`)}"><span>Summary</span><p><b>${esc(tag)}:</b> ${esc(text)}</p></div>
      ${forecast}<div class="rp-tiles">${tiles}</div>`;
  }

  _actions(r) {
    const [label, cls] = this._panelState(r);
    const why = this._why(r);
    const arrow = r.trend > 0.15 ? "↑" : r.trend < -0.15 ? "↓" : "";
    const until = r.overrideUntil ? hhmm(r.overrideUntil) : null;
    const opt = (key, text) => `<button data-ov="${key}" data-entity="${r.overrideEntity}" aria-pressed="${r.override === key}">${text}</button>`;
    const open = this._aboutOpen.has(r.name);
    const ins = r.grade ? (r.settled === false && r.gradeRange ? r.gradeRange : r.grade) : null;
    const settling = r.settled === false && (r.calibration ?? 0) < 100;
    const summary = [ins ? `${ins} insulation${settling ? " (settling)" : ""}` : null, r.warmup != null ? `warms ${Number(r.warmup).toFixed(1)}°/h` : null,
      r.hasHeater ? `heater ${r.heaterOn ? "on" : "off"}` : null].filter(Boolean).join(" · ");
    return `
      <div class="rp" role="group" aria-label="${esc(r.name)}">
        <div class="rp-head">
          <div><span class="rp-name">${esc(r.name)}</span><b class="rp-temp">${r.temp == null ? "–" : `${r.temp.toFixed(1)}°`}</b>
            <span class="rp-trend">${arrow} ${r.trend == null ? "" : `${r.trend > 0 ? "+" : ""}${Number(r.trend).toFixed(1)}°/h`}</span></div>
          <span class="pill ${cls}" title="${esc(r.heaterStopped ? `Heater kept off: ${r.heaterStopped}` : r.reason)}">${esc(label)}${until ? ` until ${until}` : ""}</span>
        </div>
        ${r.temp == null || r.roomState === "watched" ? "" : this._scale(r, why)}
        ${r.roomState === "watched" ? "" : this._roomStepper(r)}
        ${r.overrideEntity && r.roomState !== "watched" ? `<div class="rp-seg" role="group" aria-label="${esc(r.name)} override">${opt("auto", "Auto")}${opt("heat", "Heat now")}${opt("off", "Off")}</div>` : ""}
        <button class="rp-toggle" data-about="${esc(r.name)}" aria-expanded="${open}">
          <span class="chev2 ${open ? "up" : ""}">${CHEV}</span>Room profile<small>${esc(summary)}</small></button>
        ${open ? `<div class="rp-more">${this._about(r, why)}</div>` : ""}
      </div>`;
  }
}

// House temperature to hue: blue (cold) through teal, green, yellow to orange (warm).
const HUE_STOPS = [[15, 215], [16.5, 195], [18, 165], [19.5, 75], [21, 38], [23, 18]];
function tempHue(t) {
  if (t == null) return 210;
  if (t <= HUE_STOPS[0][0]) return HUE_STOPS[0][1];
  for (let i = 1; i < HUE_STOPS.length; i++) {
    const [t1, h1] = HUE_STOPS[i];
    const [t0, h0] = HUE_STOPS[i - 1];
    if (t <= t1) return Math.round(h0 + (h1 - h0) * ((t - t0) / (t1 - t0)));
  }
  return HUE_STOPS[HUE_STOPS.length - 1][1];
}

function money(v, currency) {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "GBP" }).format(v);
  } catch (e) {
    return `${Number(v).toFixed(2)} ${currency || ""}`.trim();
  }
}

function hhmm(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmt(v) {
  return v == null ? "–" : `${Number(v).toFixed(1)}°`;
}

function fmtN(v) {
  const n = Number(v);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

// Minutes for a sentence: "1 h", "2 h 15", "45 min".
function fmtDur(m) {
  return m >= 60 && m % 60 === 0 ? `${m / 60} h` : fmtMin(m);
}

function fmtMin(m) {
  if (m == null) return "";
  return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`;
}

function num(v) {
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Rooms by floor inside a house outline: roof, walls and ground, all one line.
function compactHouse(inner) {
  return `<div class="chouse">
    <svg class="roof" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true"><polyline points="0,10 50,1 100,10" /></svg>
    <div class="compact">${inner}</div>
    <div class="ground-line" aria-hidden="true"></div>
  </div>`;
}

// Energy in the footer: only what the heating used, with an (i) that opens where all the energy went.
const EIC_GAS = `<span class="eic flame">${ICON_FLAME}</span>`, EIC_ELEC = `<span class="eic">${ICON_BOLT}</span>`;
const EIC_CLOCK = `<span class="eic">${ICON_CLOCK}</span>`;

// Today 🕐 1.2 h 🔥 3.8 kWh £0.35 (i). Hours and cost only once there are some.
function energySummary(d, open) {
  const hasGas = d.gas != null, hasElec = d.elec != null;
  if (!hasGas && !hasElec) return "";
  const kwh = (v) => `${v > 0 ? v.toFixed(1) : "0"} kWh`;
  const proj = d.elecProjected != null ? `. About ${Number(d.elecProjected).toFixed(1)} kWh by midnight at this rate` : "";
  const info = `<button class="ibtn" data-energy aria-expanded="${open}" aria-label="Where the energy went" title="Where the energy went">${ICON_INFO}</button>`;
  const fig = (entity, icon, title, value) => `<span class="efuel">${icon}<span ${moreInfo(entity, title)}>${value}</span></span>`;
  const cost = hasGas && hasElec ? (d.cost || 0) + (d.elecCost || 0) : hasGas ? d.cost : d.elecCost;
  return `<div class="efig"><dt>Today</dt><dd>`
    + (d.heatHours > 0 ? fig(d.heatHoursEntity, EIC_CLOCK, "Heating hours today", `${d.heatHours.toFixed(1)} h`) : "")
    + (hasGas ? fig(d.gasEntity, EIC_GAS, `Heating gas today${d.gasMeasured ? "" : " (estimated)"}`, kwh(d.gas)) : "")
    + (hasElec ? fig(d.elecEntity, EIC_ELEC, `Heating electricity today${d.elecEst ? " (estimated)" : ""}${proj}`, kwh(d.elec)) : "")
    + (cost > 0 ? `<span class="ecost" title="Heating cost today">${money(cost, d.currency)}</span>` : "")
    + `${info}</dd></div>`;
}

// The breakdown behind the (i): heating rows count; hot water, hob and other are shown greyed and don't.
function energyBreakdown(d) {
  const hrs = (v) => (v == null ? "" : ` <small>${Number(v).toFixed(1)} h</small>`);
  const kwh = (v) => (v == null ? "–" : `${Number(v).toFixed(1)} kWh`);
  const gbp = (v) => (v == null ? "–" : money(v, d.currency));
  const row = (label, hours, k, c, entity, muted = false) =>
    `<li class="${muted ? "muted" : ""}" ${moreInfo(entity)}><span>${label}${hrs(hours)}</span><span class="n">${kwh(k)}</span><span class="n">${gbp(c)}</span></li>`;
  const sub = (label, k, c) => `<li class="esub"><span>${label}</span><span class="n">${kwh(k)}</span><span class="n">${gbp(c)}</span></li>`;
  const parts = [];
  if (d.gas != null) {
    parts.push(`<p class="ehead">${EIC_GAS}Gas${d.gasMeasured ? "" : " (estimated)"}</p><ul>`
      + row("Heating", d.gasHours, d.gas, d.cost, d.gasEntity)
      + (d.hwGas != null ? row("Hot water", d.hwHours, d.hwGas, d.hwGasCost, d.hwGasEntity, true) : "")
      + (d.otherGas != null ? row("Hob and other", null, d.otherGas, d.otherGasCost, d.otherGasEntity, true) : "")
      + sub("Gas for heating", d.gas, d.cost) + "</ul>");
  }
  if (d.elec != null) {
    parts.push(`<p class="ehead">${EIC_ELEC}Electricity${d.elecEst ? " (estimated)" : ""}</p><ul>`
      + row("Heaters", d.elecHours, d.elec, d.elecCost, d.elecEntity)
      + (d.otherElec != null ? row("Everything else", null, d.otherElec, null, d.otherElecEntity, true) : "")
      + sub("Electricity for heating", d.elec, d.elecCost) + "</ul>");
  }
  // One fuel: its subtotal is already the heating cost. Hybrid: add them up.
  const total = d.gas != null && d.elec != null
    ? `<p class="etotal"><span>Heating cost today</span><b>${money((d.cost || 0) + (d.elecCost || 0), d.currency)}</b></p>` : "";
  return `<div class="ebreak" role="region" aria-label="Where the energy went">${parts.join("")}${total}</div>`;
}

// Time left until an ISO moment, as m:ss.
function fmtLeft(until) {
  const s = Math.max(0, Math.round((new Date(until).getTime() - Date.now()) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// Attributes that make a footer figure open its sensor's more-info dialog (history graph).
function moreInfo(entityId, title = "") {
  if (!entityId) return title ? `title="${esc(title)}"` : "";
  return `data-more="${esc(entityId)}" role="button" tabindex="0" title="${esc(title ? `${title}. Show history` : "Show history")}"`;
}

const STYLE = `<style>
  :host {
    --sh-heat: #e07a2f;
    --sh-heat-soft: rgba(224, 122, 47, 0.12);
    --sh-top: #f0a868;
    --sh-coast: #b9925a;
    --sh-off: var(--disabled-text-color, #9e9e9e);
    --sh-fault: var(--error-color, #db4437);
    --sh-line: var(--divider-color, rgba(127,127,127,.25));
    --sh-muted: var(--secondary-text-color);
    --sh-house: color-mix(in srgb, var(--primary-text-color) 45%, transparent);  /* roof, walls and floor of the house */
    --sh-house-w: 1.5px;
    --sh-floor: color-mix(in srgb, var(--primary-text-color) 32%, transparent);  /* lines between floors */
  }
  ha-card { padding: 16px 16px 12px; }
  header { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; justify-content: space-between; margin-bottom: 14px; }
  h2 { margin: 0; font-size: 1.25rem; font-weight: 500; line-height: 1.2; color: var(--primary-text-color); }
  .status { margin: 4px 0 0; font-size: .875rem; color: var(--sh-muted); display: flex; gap: 8px; align-items: center; }
  .status.s-heating { color: var(--sh-heat); }
  .status.s-fault { color: var(--sh-fault); }
  .monitor { font-size: .75rem; padding: 1px 8px; border-radius: 10px; border: 1px solid var(--sh-line); color: var(--sh-muted); }

  .modes { display: inline-flex; border: 1px solid var(--sh-line); border-radius: 18px; padding: 2px; }
  .modes button { all: unset; cursor: pointer; padding: 6px 12px; border-radius: 16px; font-size: .8125rem; color: var(--sh-muted); }
  .modes button[aria-checked="true"] { background: var(--primary-text-color); color: var(--card-background-color, #fff); }
  .modes button:focus-visible, .room:focus-visible, .actions button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

  .section { position: relative; }
  .roof { display: block; width: calc(100% - var(--sh-house-w)); margin: 0 auto; height: 18px; overflow: visible; }
  .roof polyline { fill: none; stroke: var(--sh-house); stroke-width: 1.5; vector-effect: non-scaling-stroke; stroke-linejoin: round; }
  .floor { display: grid; grid-template-columns: 52px 1fr; border-left: var(--sh-house-w) solid var(--sh-house); border-right: var(--sh-house-w) solid var(--sh-house); border-top: 1px solid var(--sh-floor); }
  .section .floor:first-of-type { border-top: 0; }
  .floor-name { padding: 10px 0 0 8px; font-size: .75rem; color: var(--sh-muted); display: flex; flex-direction: column; gap: 2px; }
  .floor-name span { font-size: .8125rem; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .ground-line { height: 0; border-top: var(--sh-house-w) solid var(--sh-house); }
  .chouse .roof { height: 14px; }
  .chouse .compact { border: 0 solid var(--sh-house); border-width: 0 var(--sh-house-w); padding: 2px 8px; }

  .rooms { display: grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap: 6px; padding: 8px 8px 8px 0; }
  .room { all: unset; box-sizing: border-box; cursor: pointer; display: flex; flex-direction: column; gap: 2px;
          padding: 8px 10px 8px 12px; border-radius: 6px; border-left: 3px solid transparent;
          background: color-mix(in srgb, var(--primary-text-color) 4%, transparent); min-height: 72px; }
  .room .name { font-size: .8125rem; color: var(--primary-text-color); display: flex; align-items: center; gap: 6px; }
  .inuse { display: inline-flex; flex: none; width: 11px; height: 11px; color: var(--secondary-text-color); }
  .inuse svg { width: 100%; height: 100%; fill: currentColor; }
  .room .name .inuse { margin-left: 5px; vertical-align: -1px; }
  .room .temp { font-size: 1.375rem; font-weight: 500; font-variant-numeric: tabular-nums; color: var(--primary-text-color); line-height: 1.15; }
  .room .temp small { font-size: .75rem; font-weight: 400; color: var(--sh-muted); }
  .room .meta { font-size: .75rem; color: var(--sh-muted); display: flex; flex-wrap: wrap; column-gap: 6px; }
  .room .target { opacity: .8; margin-left: auto; white-space: nowrap; }

  .room.v-approved { border-left-color: var(--sh-heat); background: var(--sh-heat-soft); }
  .room.v-approved .meta { color: var(--sh-heat); }
  .room.v-piggyback { border-left-color: var(--sh-top); }
  .room.v-deferred { border-left-color: var(--sh-coast); }
  .room.v-wants { border-left-color: var(--sh-heat); border-left-style: dotted; }
  .room.v-off { border-left-color: var(--sh-off); opacity: .7; }
  .room.v-fault { border-left-color: var(--sh-fault); }
  .room.v-fault .meta { color: var(--sh-fault); }
  .room.dumb { background: transparent; border: 1px dashed var(--sh-line); border-left-width: 3px; }
  .room[aria-expanded="true"] { box-shadow: inset 0 0 0 1px var(--primary-text-color); }

  .actions { grid-column: 1 / -1; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--sh-line); background: rgba(255, 255, 255, .1); }  /* the open room stands out */
  .actions p { margin: 0 0 8px; font-size: .8125rem; color: var(--sh-muted); }
  .logbtn { all: unset; cursor: pointer; font-size: .75rem; color: var(--primary-color); padding: 2px 0; }
  .logbtn:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .log { list-style: none; margin: 8px 0 0; padding: 8px 0 0; border-top: 1px solid var(--sh-line); max-height: 260px; overflow-y: auto; }
  .log li { display: grid; grid-template-columns: max-content 1fr; gap: 8px; padding: 4px 0; font-size: .8125rem; color: var(--primary-text-color); }
  .log time { color: var(--sh-muted); font-variant-numeric: tabular-nums; }
  .log b { font-weight: 500; }
  .log .muted { color: var(--sh-muted); font-size: .8125rem; margin: 0; }

  footer { margin-top: 12px; display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; }
  footer dl { margin: 0; display: flex; flex-wrap: wrap; gap: 8px 20px; }
  footer dt { font-size: .75rem; color: var(--sh-muted); }
  footer dd { margin: 0; font-size: 1rem; font-weight: 500; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  footer [data-more] { cursor: pointer; border-radius: 6px; }
  .ibtn { all: unset; cursor: pointer; display: inline-flex; width: 16px; height: 16px; margin-left: 6px; vertical-align: -2px; border-radius: 50%; color: var(--sh-muted); }
  .ibtn svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
  .ibtn:hover, .ibtn[aria-expanded="true"] { color: var(--primary-color); }
  .ibtn:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .ebreak { margin-top: 10px; padding: 10px 12px; border-radius: 10px; font-size: .8125rem; color: var(--primary-text-color);
            background: color-mix(in srgb, var(--primary-text-color) 5%, transparent); }
  .ebreak ul { list-style: none; margin: 0 0 10px; padding: 0; display: grid; gap: 1px; }
  .ebreak ul:last-child { margin-bottom: 2px; }
  .ebreak li { display: grid; grid-template-columns: 1fr auto auto; gap: 14px; padding: 3px 0; font-variant-numeric: tabular-nums; }
  .ebreak li:not(.esub) > span:first-child::before { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%;
                                                     margin: 0 8px 1px 2px; background: var(--sh-heat); vertical-align: middle; }
  .ebreak li.muted > span:first-child::before { background: var(--sh-muted); opacity: .6; }
  .ebreak li[data-more] { cursor: pointer; border-radius: 4px; }
  .ebreak li[data-more]:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .ebreak .n { text-align: right; min-width: 60px; }
  .ebreak li.muted { color: var(--sh-muted); }
  .ebreak li small { color: var(--sh-muted); font-size: .75rem; }
  .ebreak li.esub { border-top: 1px solid var(--divider-color); margin-top: 3px; padding-top: 5px; font-weight: 500; }
  .ebreak .etotal b { font-size: .8125rem; }
  .ebreak .ehead { margin: 2px 0 3px; font-size: .6875rem; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--sh-muted); }
  .ebreak .etotal { display: flex; justify-content: space-between; align-items: baseline; margin: 4px 0 6px; padding-top: 7px; border-top: 1px solid var(--divider-color); font-size: .875rem; }
  footer [data-more]:hover dd, footer [data-more]:focus-visible dd { color: var(--primary-color); }
  footer [data-more]:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  footer p { margin: 0; font-size: .75rem; color: var(--sh-muted); }
  .empty { padding: 8px 0; color: var(--sh-muted); }


  /* compact layout */
  .compact { display: flex; flex-direction: column; gap: 2px; }
  .cfloor { display: grid; grid-template-columns: 46px 1fr; column-gap: 8px; padding: 6px 0; border-top: 1px solid var(--sh-floor); }
  .cfloor:first-child { border-top: 0; }
  .clabel { font-size: .75rem; color: var(--sh-muted); display: flex; flex-direction: column; padding-top: 5px; line-height: 1.25; }
  .clabel span { color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; min-width: 0; }
  .chip { all: unset; box-sizing: border-box; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
          height: 30px; padding: 0 9px; border-radius: 15px; max-width: 100%;
          background: color-mix(in srgb, var(--primary-text-color) 5%, transparent); border: 1px solid transparent; }
  .chip .cname { font-size: .8125rem; color: var(--sh-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 112px; }
  .chip .ctemp { font-size: .875rem; font-weight: 500; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  .chip.v-approved { background: var(--sh-heat-soft); border-color: var(--sh-heat); }
  .chip.v-approved .ctemp, .chip.v-approved .cname { color: var(--sh-heat); }
  .chip.v-piggyback { border-color: var(--sh-top); }
  .chip.v-deferred { border-color: var(--sh-coast); border-style: dotted; }
  .chip.v-wants { border-color: var(--sh-heat); border-style: dotted; }
  .chip.v-watched, .room.v-watched { opacity: .6; }
  .chip.v-wants .cname { color: var(--sh-heat); }
  .chip.v-off { opacity: .55; }
  .chip.v-fault .ctemp { color: var(--sh-fault); }
  .chip.dumb { background: transparent; border: 1px dashed var(--sh-line); }
  .chip.dumb.v-approved, .chip.dumb.v-piggyback { border-style: dashed; }
  .chip[aria-expanded="true"] { outline: 1.5px solid var(--primary-text-color); outline-offset: 1px; }
  .chip:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .cdetail { grid-column: 1 / -1; margin-top: 6px; }
  footer.slim { margin-top: 8px; padding-top: 8px; align-items: center; }
  footer.slim dl { gap: 4px 16px; }
  footer.slim dt { display: inline; margin-right: 4px; }
  footer.slim dd { display: inline; font-size: .875rem; }
  footer.slim .efig dd { font-size: .8125rem; }
  .efuel { white-space: nowrap; }
  .efuel + .efuel { margin-left: 6px; }
  .eic { --s: 15px; display: inline-flex; width: var(--s); height: var(--s); margin-right: 2px; vertical-align: calc(.36em - var(--s) / 2); color: var(--sh-muted); }
  .eic.flame { vertical-align: calc(.36em - var(--s) * .5625); }  /* the flame sits high in its box */
  .eic svg { width: 100%; height: 100%; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .efig .ibtn { vertical-align: calc(.36em - 8px); }
  .ehead .eic { --s: 13px; margin-right: 5px; }
  .efig dt { display: inline; margin-right: 5px; }
  .ecost { font-size: .85em; margin-left: 5px; }
  .unsettled .grade { opacity: .55; }

  /* room panel */
  .rp { grid-column: 1 / -1; display: grid; gap: 10px; padding: 10px 12px 12px; border-radius: 10px; border: 1px solid var(--sh-line);
        background: color-mix(in srgb, var(--primary-text-color) 6%, transparent); }
  .rp-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
  .rp-name { display: block; font-size: .8125rem; color: var(--sh-muted); }
  .rp-temp { font-size: 2rem; font-weight: 400; line-height: 1.05; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  .rp-trend { margin-left: 6px; font-size: .75rem; color: var(--sh-muted); }
  .pill { flex: none; display: inline-flex; align-items: center; padding: 2px 9px; border-radius: 999px; font-size: .75rem; font-weight: 600; white-space: nowrap; }
  .pill.heat { background: var(--sh-heat); color: #fff; }
  .pill.ok { background: color-mix(in srgb, var(--success-color, #43a047) 24%, transparent); color: var(--primary-text-color); }
  .pill.wait { background: color-mix(in srgb, var(--warning-color, #f5a524) 24%, transparent); color: var(--primary-text-color); }
  .pill.off, .pill.idle { background: color-mix(in srgb, var(--primary-text-color) 10%, transparent); color: var(--sh-muted); }
  .rp-scale { width: 100%; max-width: 380px; justify-self: center; height: auto; overflow: visible; }
  .rp-scale .track { stroke: var(--sh-line); stroke-width: 4; stroke-linecap: round; }
  .rp-scale line { stroke: var(--sh-muted); stroke-width: 1.5; }
  .rp-scale text { fill: var(--sh-muted); font-size: 9.5px; font-family: inherit; }
  .rp-scale text.v { font-size: 9px; }
  .rp-scale .on line { stroke: var(--sh-top); stroke-width: 2.5; }
  .rp-scale .on text { fill: var(--sh-top); font-weight: 700; }
  .rp-scale .now circle { fill: var(--primary-text-color); stroke: var(--card-background-color, #000); stroke-width: 2; }
  .rp-scale .now text { fill: var(--primary-text-color); font-size: 11px; font-weight: 600; }
  .rp .stepper-row { margin: 0; }
  .rp .stepper button { width: 32px; height: 28px; line-height: 28px; font-size: 1.1rem; padding: 0; border: 0; border-radius: 8px; }
  .rp .stepper output { font-size: 1rem; min-width: 52px; }
  .rp-seg { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3px; padding: 3px; border-radius: 10px;
            background: color-mix(in srgb, var(--primary-text-color) 9%, transparent); }
  .rp-seg button { all: unset; cursor: pointer; text-align: center; padding: 7px 0; border-radius: 8px; font-size: .8125rem; color: var(--primary-text-color); }
  .rp-seg button[aria-pressed="true"] { background: color-mix(in srgb, var(--primary-text-color) 16%, transparent); font-weight: 600; }
  .rp-seg button:focus-visible, .rp-toggle:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
  .rp-toggle { all: unset; cursor: pointer; display: flex; align-items: baseline; gap: 6px; padding-top: 8px; border-top: 1px solid var(--sh-line);
               font-size: .8125rem; color: var(--primary-text-color); }
  .rp-toggle small { color: var(--sh-muted); font-size: .75rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rp-toggle .chev2 { align-self: center; transform: rotate(-90deg); }
  .rp-toggle .chev2.up { transform: none; }
  .rp-more { display: grid; gap: 6px; margin-top: -4px; }
  .rp-fc { display: grid; gap: 1px; padding: 4px 8px; border-radius: 8px;
           background: color-mix(in srgb, var(--primary-text-color) 7%, transparent); font-size: .75rem; color: var(--sh-muted); }
  .rp-fc > span { font-size: .625rem; }
  .rp-fc.sum p { color: var(--primary-text-color); font-size: .6875rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rp-fc p { margin: 0; line-height: 1.45; text-align: center; }
  .rp-fc b { font-weight: 500; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .rp-tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); grid-auto-flow: row dense; gap: 5px; }
  .rp-tile { display: grid; align-content: start; gap: 1px; min-width: 0; padding: 4px 8px; border-radius: 8px;
             background: color-mix(in srgb, var(--primary-text-color) 7%, transparent); }
  .rp-tile.s2 { grid-column: span 2; }
  .rp-tile > span { font-size: .625rem; color: var(--sh-muted); }
  .rp-tile > b { text-align: center; font-size: .78rem; font-weight: 500; color: var(--primary-text-color); font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rp-tile .grade { font-style: normal; margin-right: 4px; font-size: .6875rem; line-height: 15px; min-width: 15px; padding: 0 4px; }
  footer.slim p { display: none; }
  footer.slim { flex-wrap: nowrap; }
  footer.slim .logbtn { margin-left: auto; white-space: nowrap; }


  /* mini layout */
  ha-card { display: block; }
  ha-card.mini { position: relative; overflow: hidden; padding: 12px 14px; isolation: isolate;
                 background: var(--ha-card-background, var(--card-background-color, #fff)); border-radius: var(--ha-card-border-radius, 12px); }
  .tint { position: absolute; inset: 0; pointer-events: none; border-radius: inherit; z-index: 0;
          background: linear-gradient(115deg, hsl(var(--h) 85% 55% / .30) 0%, hsl(var(--h) 85% 55% / .10) 55%, hsl(var(--h) 85% 55% / 0) 100%);
          transition: background .6s; }
  ha-card.mini > :not(.tint) { position: relative; z-index: 1; }
  .summary { all: unset; box-sizing: border-box; cursor: pointer; width: 100%; display: flex; flex-direction: column; gap: 4px; }
  .hdr { display: flex; align-items: center; gap: 8px; min-height: 22px; }
  .ttl { display: inline-flex; align-items: center; gap: 6px; min-width: 0; flex: 0 1 auto; font-size: .8125rem; font-weight: 500;
         color: var(--sh-muted); white-space: nowrap; overflow: hidden; }
  .ttl > span:last-child { overflow: hidden; text-overflow: ellipsis; }
  .ttl .logo { display: inline-flex; flex: none; }
  .ttl .logo svg { width: 18px; height: 18px; }
  .ttl ha-icon { --mdc-icon-size: 18px; color: var(--sh-heat); flex: none; }
  .hdr .st { margin-left: auto; justify-content: flex-end; }
  .row1 { display: flex; align-items: center; gap: 12px; }
  .row1 .sub { margin-top: 2px; }
  h2 .ttl { font-size: 1.1rem; color: var(--primary-text-color); }
  h2 .ttl .logo svg { width: 22px; height: 22px; }
  .summary:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 4px; border-radius: 8px; }
  .big { font-size: 2.25rem; font-weight: 400; line-height: 1; letter-spacing: -.02em; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  .big small { font-size: 1.1rem; vertical-align: top; margin-left: 1px; color: var(--sh-muted); }
  .mid { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
  .st { font-size: .8125rem; font-weight: 500; color: var(--primary-text-color); display: flex; align-items: center; gap: 7px; min-width: 0; padding-left: 2px; }
  .stt { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .st.s-heating { color: var(--sh-heat); }
  .st.s-fault { color: var(--sh-fault); }
  .sub { font-size: .75rem; color: var(--sh-muted); display: flex; gap: 6px; align-items: center; white-space: nowrap; }
  .sub em { font-style: normal; padding: 0 6px; border-radius: 8px; border: 1px solid var(--sh-line); flex: none; }
  .sub .phase { overflow: hidden; text-overflow: ellipsis; }
  .chev { color: var(--sh-muted); display: inline-flex; padding: 2px; }
  .chev svg { width: 20px; height: 20px; }
  .chev svg, .chev2 svg { fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; transition: transform .2s; }
  .chev.up svg, .chev2.up svg { transform: rotate(180deg); }
  .row2 { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; }
  .fp { display: inline-flex; align-items: center; gap: 4px; height: 24px; padding: 0 9px; border-radius: 12px; font-size: .75rem; color: var(--sh-muted);
        background: color-mix(in srgb, var(--card-background-color, #fff) 55%, transparent); }
  .fp b { font-weight: 500; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .fp.on { color: var(--sh-heat); }
  .fp.on b { color: var(--sh-heat); }
  .fp i { width: 6px; height: 6px; border-radius: 50%; background: var(--sh-heat); }
  .fp.out { margin-left: auto; }
  .modes.small { margin-bottom: 6px; }
  .modes.small button { padding: 4px 10px; font-size: .75rem; }
  .mini .chip { height: 26px; padding: 0 8px; background: color-mix(in srgb, var(--card-background-color, #fff) 55%, transparent); }
  .mini .chip .cname { font-size: .75rem; max-width: 96px; }
  .mini .chip .ctemp { font-size: .8125rem; }
  .mini .chip.v-approved { background: var(--sh-heat-soft); }
  .mini .chip.dumb { background: transparent; }
  .mini .cfloor { padding: 4px 0; grid-template-columns: 40px 1fr; }
  .mini footer.slim { margin-top: 4px; padding-top: 6px; }


  .grade { display: inline-block; min-width: 18px; padding: 0 5px; border-radius: 4px; text-align: center; color: #fff; font-weight: 600; font-size: .75rem; line-height: 18px; }
  .g-A { background: #2e8b57; } .g-B { background: #4caf50; } .g-C { background: #8bc34a; } .g-D { background: #e0b020; }
  .g-E { background: #f08c2a; } .g-F { background: #e5612f; } .g-G { background: #d23a2f; }
  .g-C, .g-D { color: #1c2024; }  /* white is unreadable on the light green and yellow */

  /* mode bar */
  .modebar { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 10px; }
  .modebar button { all: unset; box-sizing: border-box; cursor: pointer; height: 40px; border-radius: 10px;
                    display: flex; align-items: center; justify-content: center; gap: 6px; padding: 0 6px; white-space: nowrap;
                    font-size: .8125rem; font-weight: 500; color: var(--primary-text-color);
                    border: 1.5px solid color-mix(in srgb, var(--primary-text-color) 22%, transparent);
                    background: color-mix(in srgb, var(--card-background-color, #fff) 70%, transparent);
                    transition: background .15s, border-color .15s, color .15s; }
  .modebar svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; flex: none; }
  .modebar button:hover { border-color: color-mix(in srgb, var(--primary-text-color) 45%, transparent); }
  .modebar button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .modebar button[aria-checked="true"] { color: #fff; border-color: transparent; box-shadow: 0 1px 3px rgba(0,0,0,.25); }
  .modebar .m-off[aria-checked="true"] { background: #5f6b7a; }
  .modebar .m-one_cycle[aria-checked="true"] { background: #d18a1f; }
  .modebar .m-auto[aria-checked="true"] { background: #e0622f; }
  @media (max-width: 360px) { .modebar span { font-size: .75rem; } .modebar svg { display: none; } }

  @media (max-width: 420px) {
    .floor { grid-template-columns: 1fr; }
    .floor-name { padding: 8px 0 0 8px; flex-direction: row; gap: 8px; }
    .rooms { padding-left: 8px; grid-template-columns: repeat(2, 1fr); }
  }

  /* tips */
  .info { all: unset; cursor: pointer; display: inline-flex; width: 16px; height: 16px; margin-left: 4px; vertical-align: -3px;
          color: var(--sh-muted); opacity: .7; border-radius: 50%; }
  .info svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; }
  .info:hover, .info.on { opacity: 1; color: var(--primary-color); }
  .info:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
  .tip { margin: 4px 0 6px; padding: 8px 10px; border-radius: 8px; font-size: .75rem; line-height: 1.4; color: var(--primary-text-color);
         background: color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color, #fff)); }

  /* stepper */
  .stepper-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 10px; }
  .sp-label { font-size: .8125rem; color: var(--primary-text-color); display: flex; align-items: center; flex-wrap: wrap; column-gap: 2px; }
  .sp-label small { flex-basis: 100%; font-size: .6875rem; color: var(--sh-muted); }
  .stepper { display: inline-flex; align-items: center; border-radius: 12px; padding: 3px;
             border: 1.5px solid color-mix(in srgb, var(--primary-text-color) 18%, transparent);
             background: color-mix(in srgb, var(--card-background-color, #fff) 75%, transparent); }
  .stepper button { all: unset; cursor: pointer; width: 36px; height: 32px; border-radius: 9px; text-align: center;
                    font-size: 1.25rem; line-height: 32px; color: var(--primary-text-color); }
  .stepper button:hover { background: color-mix(in srgb, var(--primary-text-color) 8%, transparent); }
  .stepper button:active { background: color-mix(in srgb, var(--primary-text-color) 15%, transparent); }
  .stepper button:focus-visible { outline: 2px solid var(--primary-color); }
  .stepper output { min-width: 58px; text-align: center; font-size: 1.125rem; font-weight: 500; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  .stepper output small { font-size: .75rem; color: var(--sh-muted); }
  .stepper.pending output { color: var(--sh-heat); }
  .actions .stepper-row { margin: 0 0 8px; }
  .actions .stepper button { width: 32px; height: 28px; line-height: 28px; font-size: 1.1rem; padding: 0; border: 0; border-radius: 8px; }
  .actions .stepper output { font-size: 1rem; min-width: 52px; }

  /* badge, panel, ready */
  .badge { all: unset; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; flex: none; font-size: .75rem;
           padding: 1px 8px; border-radius: 10px; border: 1px solid var(--sh-line); color: var(--primary-text-color);
           background: color-mix(in srgb, var(--card-background-color, #fff) 60%, transparent); }
  .badge:hover { border-color: var(--primary-color); }
  .badge:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
  .badge.test svg { width: 13px; height: 13px; fill: currentColor; }
  .badge.test { color: #fff; background: var(--sh-heat); border-color: transparent; }
  .chev2 { display: inline-flex; color: var(--sh-muted); }
  .chev2 svg { width: 12px; height: 12px; }
  .badge .spin { width: 12px; height: 12px; fill: none; stroke-width: 3; animation: sh-spin 1.1s linear infinite; }
  .badge .spin .trk { stroke: color-mix(in srgb, var(--primary-color) 22%, transparent); }
  .badge .spin .arc { stroke: var(--primary-color); stroke-linecap: round; }
  @keyframes sh-spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .badge .spin { animation-duration: 4s; } }
  .status .badge { margin-left: 4px; }
  .badge.win { font-size: .6875rem; padding: 1px 7px; gap: 3px; white-space: nowrap; }
  .badge.win svg { width: 12px; height: 12px; fill: none; stroke: currentColor; stroke-width: 1.8; }
  .badge.win.open { color: var(--primary-color); border-color: color-mix(in srgb, var(--primary-color) 45%, transparent); }
  .badge.win.close { color: var(--warning-color, #b26a00); border-color: color-mix(in srgb, var(--warning-color, #b26a00) 45%, transparent); }
  .winbox { margin-top: 10px; padding: 8px 12px; border-radius: 10px; font-size: .8125rem; color: var(--primary-text-color);
            background: color-mix(in srgb, var(--card-background-color, #fff) 80%, transparent); border: 1px solid var(--sh-line); }
  .calpanel { margin-top: 10px; padding: 10px 12px; border-radius: 10px; font-size: .8125rem;
              background: color-mix(in srgb, var(--card-background-color, #fff) 80%, transparent); border: 1px solid var(--sh-line); }
  .calpanel p { margin: 0 0 8px; }
  .calpanel .lead { color: var(--primary-text-color); }
  .calpanel .now { color: var(--primary-text-color); margin-top: 8px; }
  .calpanel .muted { color: var(--sh-muted); font-size: .75rem; }
  .need-row { display: grid; grid-template-columns: minmax(0, 10.5em) 1fr auto; align-items: center; gap: 10px; padding: 3px 0; }
  .need-row > span:first-child { display: flex; align-items: center; color: var(--primary-text-color); white-space: nowrap; }
  .need-row .val { font-variant-numeric: tabular-nums; color: var(--sh-muted); font-size: .75rem; text-align: right; min-width: 64px; }
  .need-row .val svg, .ready svg { width: 16px; height: 16px; fill: none; stroke: #2e8b57; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; vertical-align: -3px; }
  .bar { height: 6px; border-radius: 3px; background: color-mix(in srgb, var(--primary-text-color) 10%, transparent); overflow: hidden; }
  .bar i { display: block; height: 100%; border-radius: 3px; background: var(--primary-color); }
  .need-row.done .bar i { background: #2e8b57; }
  .calpanel > .speed:first-child { margin: 0; padding: 0; border: 0; }
  .speed { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--sh-line); }
  .speed ol { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; }
  .speed li span { display: block; color: var(--sh-muted); font-size: .75rem; margin-top: 3px; }
  .calpanel button:not(.info), .ready button { all: unset; white-space: nowrap; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px;
              border-radius: 14px; border: 1px solid var(--sh-line); font-size: .8125rem; color: var(--primary-text-color); }
  .calpanel button:not(.info) svg { width: 14px; height: 14px; fill: currentColor; }
  .calpanel button.primary, .ready button.primary { background: var(--sh-heat); color: #fff; border-color: transparent; font-weight: 500; }
  .calpanel button.link { white-space: normal; border: 0; padding: 8px 0 0; color: var(--primary-color); font-size: .75rem; }
  .calpanel button:focus-visible, .ready button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .ready { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 10px; padding: 8px 10px 8px 12px;
           border-radius: 10px; font-size: .8125rem; color: var(--primary-text-color);
           background: color-mix(in srgb, #2e8b57 14%, var(--card-background-color, #fff)); }
  .ready span { display: flex; align-items: center; gap: 6px; }
  .ocbox { margin-top: 10px; padding: 10px 12px; border-radius: 10px; font-size: .8125rem; color: var(--primary-text-color);
           background: color-mix(in srgb, #3d8bff 12%, var(--card-background-color, #fff)); }
  .ocbox p { margin: 0 0 6px; }
  .ocbox ul { margin: 0 0 8px; padding-left: 18px; }
  .ocbox li { margin: 2px 0; }
  .ocbox .muted { color: var(--sh-muted); }
  .ocbox .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .ocbox button { all: unset; white-space: nowrap; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px;
                  border-radius: 999px; border: 1px solid var(--divider-color, rgba(0,0,0,.15)); font-size: .8125rem; }
  .ocbox button.primary { background: var(--sh-heat); color: #fff; border-color: transparent; font-weight: 500; }
  .ocbox button svg { width: 16px; height: 16px; fill: currentColor; }
  .ocbox button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .ready.confirm { flex-wrap: wrap; background: color-mix(in srgb, #e0a020 18%, var(--card-background-color, #fff)); }
  .ready.confirm > span:first-child { display: block; flex: 1 1 220px; }
  .ready .actions { gap: 8px; }
  .err { margin: 8px 0 0; font-size: .75rem; color: var(--sh-fault); }
  .summary { -webkit-tap-highlight-color: transparent; }

  .chip .bolt, .room .bolt { display: inline-flex; color: var(--sh-heat); }
  .chip .bolt svg { width: 12px; height: 12px; fill: currentColor; }

  .inds { display: inline-flex; gap: 4px; flex: none; }
  .ind { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%;
         color: var(--sh-muted); background: color-mix(in srgb, var(--card-background-color, #fff) 60%, transparent); }
  .ind svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .ind.burn { color: #fff; background: #e0622f; }
  .ind.burn svg { fill: currentColor; stroke: none; animation: sh-flicker 1.6s ease-in-out infinite; transform-origin: 50% 90%; }
  .ind.wait { color: #e0622f; }
  .ind.heat { color: var(--sh-heat); }
  .ind.heat svg path[d^="M13 2"] { fill: currentColor; stroke: none; }
  .ind.water { color: #2f8fe0; }
  .ind.water svg { fill: currentColor; stroke: none; }
  .ind.away { color: #8a6fd1; }
  .ind.night { color: #6f7fd1; }
  .ind.night svg { fill: currentColor; stroke: none; }
  .status .inds { margin-left: 4px; }
  @keyframes sh-flicker { 0%, 100% { transform: scale(1); } 50% { transform: scale(.86) translateY(1px); } }
  @media (prefers-reduced-motion: reduce) { .ind.burn svg { animation: none; } }

  .sdot { --c: #3aa864; position: relative; flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--c); }
  .sdot::after { content: ""; position: absolute; inset: 0; border-radius: 50%; background: var(--c); opacity: 0; }
  .sdot.d-heating, .sdot.d-testing { --c: #e0622f; }
  .sdot.d-would { --c: #d18a1f; }
  .sdot.d-paused { --c: #2f8fe0; }
  .sdot.d-waiting { --c: #9aa3ad; }
  .sdot.d-idle { --c: #3aa864; }
  .sdot.d-off, .sdot.d-disabled { --c: #8a929b; }
  .sdot.d-away { --c: #8a6fd1; }
  .sdot.d-fault { --c: #db4437; }
  .sdot.d-heating::after, .sdot.d-testing::after, .sdot.d-fault::after { animation: sh-pulse 1.6s ease-out infinite; }
  .sdot.d-would::after, .sdot.d-paused::after, .sdot.d-waiting::after { animation: sh-pulse 2.6s ease-out infinite; }
  .sdot.d-testing::after { animation-duration: 1s; }
  @keyframes sh-pulse { 0% { transform: scale(1); opacity: .55; } 100% { transform: scale(3); opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .sdot::after { animation: none !important; } }
  .status { align-items: center; }

  .calpanel .warn { margin: 0 0 6px; padding: 6px 8px; border-radius: 8px; font-size: .75rem; color: var(--primary-text-color);
                    background: color-mix(in srgb, #e0a020 18%, var(--card-background-color, #fff)); }
  .calpanel button.link[data-test] { padding: 0 0 0 10px; }

  .calpanel .spin { width: 13px; height: 13px; fill: none; stroke-width: 3; vertical-align: -2px; margin-right: 6px; animation: sh-spin 1.1s linear infinite; }
  .calpanel .spin .trk { stroke: color-mix(in srgb, var(--sh-heat) 25%, transparent); }
  .calpanel .spin .arc { stroke: var(--sh-heat); stroke-linecap: round; }
  .sdot.d-starting { --c: #9aa3ad; }
  .sdot.d-starting::after { animation: sh-pulse 1.6s ease-out infinite; }
</style>`;

if (!customElements.get("smart-heating-card")) {
  customElements.define("smart-heating-card", SmartHeatingCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "smart-heating-card")) window.customCards.push({
  type: "smart-heating-card",
  name: "Smart Heating",
  description: "Smart Heating: house temperature, mode, rooms and decisions.",
  preview: true,
});
