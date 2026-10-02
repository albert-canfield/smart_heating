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
  deferred: "Coasting",
  vetoed: "Not needed",
  idle: "Idle",
  fault: "No sensor",
};

const FLOOR_NAME = { 0: "Ground", 1: "1st", 2: "2nd", 3: "3rd" };

const MODE_LABEL = { off: "Off", one_cycle: "One cycle", continuous: "Continuous" };

const MODE_TIP = {
  off: "Frost protection only",
  one_cycle: "Heats the rooms that need it once, then switches itself off",
  continuous: "Keeps every room at its target, firing the boiler only when it's worth it",
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
  else if (d.demand && d.hasBoiler) add("flame", "wait", d.monitor ? "Would call the boiler" : "Boiler called, not burning yet");
  if (d.calling > 0 && !d.monitor) add("radiator", "heat", `Heating ${d.calling === 1 ? "1 room" : `${d.calling} rooms`}`);
  if (d.heaterCount > 0 && !d.monitor) add("bolt", "heat", `${d.heaterCount} electric heater room${d.heaterCount === 1 ? "" : "s"} on`);
  if (d.hotWater === true) add("water", "water", "Hot water heating");
  if (d.away) add("away", "away", "Away: frost protection only");
  if (d.night) add("moon", "night", "Night settings");
  if (d.monitor) add("eye", "watch", d.calibrated ? "Watching only: not controlling yet" : "Calibrating: watching only");
  return out.length ? `<span class="inds">${out.join("")}</span>` : "";
}

const LOGO = '<svg viewBox="0 0 256 256" aria-hidden="true"><rect width="256" height="256" rx="58" fill="#101826"/><path d="M128 50L206 112V118H50V112Z" fill="#FF6B3D"/><path d="M50 126H206V160H50Z" fill="#FFB547"/><path d="M50 168H206V206H50Z" fill="#3D8BFF"/></svg>';
const CHEV = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9.5l6 6 6-6"/></svg>';
const SPIN = '<svg class="spin" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" class="trk"/><path d="M12 3a9 9 0 0 1 9 9" class="arc"/></svg>';

const ICON_BOLT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z"/></svg>';
const ICON_CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
const ICON_FLAME = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.2 1.2-3.6 2.4-4.6.2 1.6 1 2.6 2.1 3C11 8.8 11.4 5.6 12 3z"/></svg>';

const MODE_ICON = {
  off: '<path d="M12 3v8"/><path d="M6.6 6.6a7.5 7.5 0 1 0 10.8 0"/>',
  one_cycle: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v4h-4"/><path d="M11 10.5l1.5-1v6"/>',
  continuous: '<path d="M8 8.5a3.5 3.5 0 1 0 0 7c2.6 0 5.4-7 8-7a3.5 3.5 0 1 1 0 7c-2.6 0-5.4-7-8-7z"/>',
};

function modeBar(current) {
  return `<div class="modebar" role="radiogroup" aria-label="Heating mode">
    ${Object.entries(MODE_LABEL).map(([k, v]) => `
      <button class="m-${k}" role="radio" aria-checked="${current === k}" data-mode="${k}" title="${MODE_TIP[k]}">
        <svg viewBox="0 0 24 24" aria-hidden="true">${MODE_ICON[k]}</svg><span>${v}</span>
      </button>`).join("")}
  </div>`;
}

const STATUS_SENTENCE = {
  heating: (n) => `Heating ${n === 1 ? "1 room" : `${n} rooms`}`,
  idle: () => "Not heating, nothing needs it",
  paused: () => "Paused for hot water",
  waiting: () => "Waiting for boiler rest time",
  off: () => "Heating is off",
  away: () => "Away: alarm armed, frost protection only",
  fault: () => "Room sensors unavailable",
  disabled: () => "Controller disabled",
  testing: () => "Heat test running",
  starting: () => "Starting up",
};

class SmartHeatingCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._open = null;
    this._showLog = false;
    this._expanded = false;
    this._calOpen = false;
    this._tip = null;
    this._pending = {};
    this._timers = {};
    this._confirmSkip = false;
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
          else if (s.attributes.kind === "gas_cost_today") house.cost = s;
          else if (s.attributes.kind === "electric_today") house.elec = s;
          else if (s.attributes.kind === "electric_cost_today") house.elecCost = s;
          else if (s.attributes.kind === "decision_log") house.log = s;
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
        thermo: a.temperature_entity ? (hass.states[a.temperature_entity]?.attributes.friendly_name || a.temperature_entity) : null,
        thermoSource: a.temperature_source,
        deficit: a.deficit,
        tau: num(tau?.state),
        gain: tau?.attributes.free_heat_gain,
        calibration: tau?.attributes.calibration,
        warmup: num(warm?.state),
        grade: ret?.attributes.grade,
        rating: ret?.attributes.rating,
        retScore: num(ret?.state),
        pred2: num(pred?.state),
        pred8: pred?.attributes.predicted_8h,
        hoursToBase: pred?.attributes.hours_to_baseline,
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
      calling: new Set([...(house.status?.attributes.open_rooms || []), ...(house.status?.attributes.heater_rooms || [])]).size,
      monitor: house.monitor?.state === "on",
      mode: house.mode?.state,
      modeEntity: house.mode?.entity_id,
      houseTemp: num(house.temp?.state),
      calibrated: house.cal ? house.cal.attributes.calibrated === true : true,
      calPct: num(house.cal?.state),
      calPhase: house.cal?.attributes.learning_now,
      cal: house.cal?.attributes || {},
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
      elecProjected: house.elec?.attributes.projected_today_kwh,
      elecMeasured: house.elec?.attributes.measured === true,
      log: (house.log?.attributes.entries || []).slice(0, 15),
      houseGrade: house.retention?.attributes.grade,
      houseScore: num(house.retention?.state),
      outdoor: num(house.outdoor?.attributes.now) ?? num(house.outdoor?.state),
      floorNames: Object.fromEntries(rooms.filter((r) => r.floorName).map((r) => [r.floor, r.floorName])),
      floorTemps: Object.fromEntries(Object.entries(house.floors || {}).map(([f, s]) => [f, num(s.state)])),
    };
  }

  /* ---------- actions ---------- */

  _setMode(mode) {
    if (!this._data.modeEntity) return;
    this._hass.callService("select", "select_option", { entity_id: this._data.modeEntity, option: mode });
  }

  _call(domain, service, data) {
    this._hass.callService(domain, service, data).catch((err) => {
      this._error = err?.message || String(err);
      this._render();
    });
  }

  _step(entity, current, delta) {
    if (!entity) return;
    const base = this._pending[entity] ?? current ?? 19;
    const v = Math.min(25, Math.max(10, Math.round((base + delta) * 2) / 2));
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
    this._hass.callService("select", "select_option", { entity_id: entity, option });
    this._open = null;
    this._render();
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
          <button data-step="-0.5" data-entity="${entity}" data-value="${value ?? ""}" aria-label="Lower">−</button>
          <output aria-live="polite">${v == null ? "–" : Number(v).toFixed(1)}<small>°</small></output>
          <button data-step="0.5" data-entity="${entity}" data-value="${value ?? ""}" aria-label="Raise">+</button>
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
    if (!d.calibrated) return `<button class="badge cal" data-cal aria-expanded="${this._calOpen}" title="${esc(d.calPhase ? `Now: ${d.calPhase}` : "Learning how your house holds heat")}">${SPIN}Calibrating ${d.calPct ?? 0}%<span class="chev2 ${this._calOpen ? "up" : ""}">${CHEV}</span></button>`;
    return "";
  }

  _ready(d) {
    if (!d.monitor || d.heatTest != null || !d.calibrated) return "";
    const text = d.calAvailable ? "Calibration done. Ready to take over." : "Watching only.";
    return `<div class="ready"><span>${d.calAvailable ? ICON_CHECK : ""}${text}</span>
      <button class="primary" data-start>Start control</button></div>`;
  }

  _calPanel(d) {
    if (!(this._calOpen || d.heatTest != null) || (d.calibrated && d.heatTest == null)) return "";
    const c = d.cal;
    const bar = (have, need) => {
      const pct = need ? Math.min(100, Math.round((have / need) * 100)) : 0;
      return `<span class="bar" aria-hidden="true"><i style="width:${pct}%"></i></span>`;
    };
    const row = (key, label, have, need, unit, tip) => `
      <div class="need-row ${have >= need ? "done" : ""}">
        <span>${esc(label)}${this._info(key)}</span>
        ${bar(have, need)}
        <span class="val">${have >= need ? ICON_CHECK : `${fmtN(have)} of ${fmtN(need)}${unit}`}</span>
      </div>${this._tipBox(key, tip)}`;
    const eta = c.eta_hours ? (c.eta_hours > 36 ? `about ${Math.round(c.eta_hours / 24 * 2) / 2} days left` : `about ${c.eta_hours} h left`) : "almost done";
    const test = d.heatTest != null
      ? `<div class="speed"><p>${SPIN}<b>Heat test running</b>, ${fmtMin(d.heatTest)} left. Rooms that need data are heating gently; each stops at 1° warmer, never above 21.5°.</p>
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
              <span>Gentle: only rooms that still need data, each warmed by about 1° (never above 21.5°), usually under 2 h. Then the house cools. If anything else switches the heating, the test stops.</span></li>
            <li><span>Leave the heating off overnight. Each night gives up to 10 h of cooling data.</span></li>
          </ol>
        </div>`
      : `<div class="speed"><p><b>Speed it up</b>: leave the heating off overnight. Each night gives up to 10 h of cooling data.</p></div>`;
    if (d.heatTest != null && !this._calOpen) return `<div class="calpanel">${test}</div>`;
    return `
      <div class="calpanel">
        <p class="lead">Learning how your house holds heat: ${c.rooms_done ?? 0} of ${c.rooms_needed ?? "?"} rooms ready, ${eta}.</p>
        ${row("cool", "Cooling data", c.cooling_hours ?? 0, c.cooling_hours_needed ?? 24, " h",
          "Counted while the boiler has been off for at least 1 hour. Nights with the heating off fill this fastest.")}
        ${row("range", "Temperature range", c.variety_c ?? 0, c.variety_needed_c ?? 2, "°",
          "The gap between inside and outside needs to vary by 2°. A warm-up followed by a cool-down does it.")}
        ${row("heat", "Heating data", c.heating_hours ?? 0, c.heating_hours_needed ?? 2, " h",
          "Counted while the boiler runs with the room's radiator open. The heat test fills this in one go.")}
        <p class="now">Now: ${esc(d.calPhase || "starting")}</p>
        <p class="muted">Until then Smart Heating only watches and logs. Keep your heating as it is; you'll get a notification when it's ready.</p>
        ${test}
        <button class="link" data-skip>${this._confirmSkip ? "Tap again to start now with default settings" : "Start now without calibration"}</button>
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
    let statusText = (STATUS_SENTENCE[d.status] || (() => d.status || ""))(d.calling);
    if (d.monitor && d.heatTest == null && d.status === "heating") statusText = `Would heat ${d.calling === 1 ? "1 room" : `${d.calling} rooms`}`;
    if (this._config.layout !== "full") {
      this._renderCompact(d, floors, statusText);
      return;
    }

    this.shadowRoot.innerHTML = `${STYLE}
      <ha-card>
        <header>
          <div class="title">
            <h2>${this._titleHtml() || esc(this._config.title || "Smart Heating")}</h2>
            <p class="status s-${d.status}">${statusDot(d)}${esc(statusText)}${indicators(d)}${this._badge(d)}</p>
          </div>
        </header>
        ${this._calPanel(d)}
        ${this._ready(d)}
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
        <div class="compact">
          ${floors.map((f) => this._compactFloor(f, d.rooms.filter((r) => r.floor === f))).join("")}
        </div>`}

        <footer class="${this._config.layout === "full" ? "" : "slim"}">
          <dl>
            ${d.houseTemp != null ? `<div><dt>House</dt><dd>${d.houseTemp.toFixed(1)}°</dd></div>` : ""}
            ${d.outdoor != null ? `<div><dt>Outdoor today</dt><dd>${d.outdoor.toFixed(1)}°</dd></div>` : ""}
            ${d.gas != null ? `<div ${moreInfo(d.gasEntity)}><dt>Gas today${d.gasMeasured ? "" : " (est.)"}</dt><dd>${d.gas.toFixed(1)} kWh</dd></div>` : ""}
            ${d.cost != null ? `<div ${moreInfo(d.costEntity)}><dt>Gas cost today</dt><dd>£${d.cost.toFixed(2)}</dd></div>` : ""}
            ${d.elec != null ? `<div ${moreInfo(d.elecEntity)}><dt>Electric today${d.elecMeasured ? "" : " (est.)"}</dt><dd>${d.elec.toFixed(1)} kWh</dd></div>` : ""}
            ${d.elecCost != null ? `<div ${moreInfo(d.elecCostEntity)}><dt>Electric cost today</dt><dd>£${d.elecCost.toFixed(2)}</dd></div>` : ""}
          </dl>
          <p>${esc(d.reason || "")}</p>
          <button class="logbtn" data-log aria-expanded="${this._showLog}">${this._showLog ? "Hide log" : "Show log"}</button>
        </footer>
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
    const badge = this._badge(d);
    const up = [...floors].sort((a, b) => a - b);
    const floorPills = up.length < 2 ? "" : up.map((f) => {
      const rooms = d.rooms.filter((r) => r.floor === f);
      const heating = rooms.some((r) => r.verdict === "approved" || r.verdict === "piggyback");
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
        ${this._calPanel(d)}
        ${this._ready(d)}
        ${this._error ? `<p class="err" role="alert">${esc(this._error)}</p>` : ""}
        <div class="row2">
          ${floorPills}
          ${d.outdoor != null ? `<span class="fp out">Out <b>${d.outdoor.toFixed(1)}°</b></span>` : ""}
        </div>
        ${modeBar(d.mode)}
        ${this._houseStepper(d)}
        ${ex ? `
        <div class="more">
          <div class="compact">
            ${floors.map((f) => this._compactFloor(f, d.rooms.filter((r) => r.floor === f))).join("")}
          </div>
          <footer class="slim">
            <dl>
              ${d.gas != null ? `<div ${moreInfo(d.gasEntity)}><dt>Gas${d.gasMeasured ? "" : " est."}</dt><dd>${d.gas.toFixed(1)} kWh</dd></div>` : ""}
              ${d.cost != null ? `<div ${moreInfo(d.costEntity)}><dt>Gas cost</dt><dd>£${d.cost.toFixed(2)}</dd></div>` : ""}
              ${d.elec != null ? `<div ${moreInfo(d.elecEntity, d.elecProjected != null ? `About ${Number(d.elecProjected).toFixed(1)} kWh by midnight at this rate` : "")}><dt>Electric${d.elecMeasured ? "" : " est."}</dt><dd>${d.elec.toFixed(1)} kWh</dd></div>` : ""}
              ${d.elecCost != null ? `<div ${moreInfo(d.elecCostEntity)}><dt>Electric cost</dt><dd>£${d.elecCost.toFixed(2)}</dd></div>` : ""}
              ${d.houseGrade ? `<div><dt>Insulation</dt><dd><span class="grade g-${d.houseGrade}">${d.houseGrade}</span> ${d.houseScore}</dd></div>` : ""}
            </dl>
            <button class="logbtn" data-log aria-expanded="${this._showLog}">${this._showLog ? "Hide log" : "Log"}</button>
          </footer>
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
    root.querySelector("[data-cal]")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._calOpen = !this._calOpen;
      this._confirmSkip = false;
      this._render();
    });
    root.querySelectorAll("[data-test]").forEach((b) => b.addEventListener("click", () => {
      this._error = null;
      const t = b.dataset.test;
      this._call("smart_heating", "heat_test", t === "stop" ? { start: false } : { start: true, ignore_automations: t === "force" });
    }));
    root.querySelector("[data-start]")?.addEventListener("click", () => {
      this._error = null;
      this._call("smart_heating", "start_control", {});
    });
    root.querySelector("[data-skip]")?.addEventListener("click", () => {
      if (!this._confirmSkip) { this._confirmSkip = true; this._render(); return; }
      this._confirmSkip = false;
      this._calOpen = false;
      this._error = null;
      this._call("smart_heating", "start_control", { skip_calibration: true });
    });
    root.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => this._setMode(b.dataset.mode)));
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
    return r.override === "off" ? "off" : r.verdict;
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
        ${open ? `<div class="cdetail">${this._actions(open, true)}</div>` : ""}
      </div>`;
  }

  _chip(r) {
    const state = this._state(r);
    const label = r.override === "off" ? "off by you" : (STATE_LABEL[r.verdict] || r.verdict).toLowerCase();
    return `
      <button class="chip v-${state} ${r.hasTrv || r.hasHeater ? "" : "dumb"}" data-room="${esc(r.name)}"
        aria-expanded="${this._open === r.name}" aria-label="${esc(r.name)}, ${r.temp == null ? "no reading" : r.temp.toFixed(1) + " degrees"}, ${esc(label)}"
        title="${esc(r.name)}: ${esc(r.reason)}">
        ${r.occupied ? `<span class="dot" aria-hidden="true"></span>` : ""}
        ${r.heaterOn ? `<span class="bolt" aria-label="heater on">${ICON_BOLT}</span>` : ""}
        <span class="cname">${esc(r.name)}</span>
        <span class="ctemp">${r.temp == null ? "–" : r.temp.toFixed(1)}</span>
      </button>`;
  }

  _room(r) {
    const state = r.override === "off" ? "off" : r.verdict;
    const label = r.override === "off" ? "Off by you"
      : r.override === "heat" && r.verdict !== "approved" ? "Heat requested"
      : STATE_LABEL[r.verdict] || r.verdict;
    const trend = r.trend == null ? "" : r.trend > 0.15 ? " ↑" : r.trend < -0.15 ? " ↓" : "";
    return `
      <button class="room v-${state} ${r.hasTrv || r.hasHeater ? "" : "dumb"}" data-room="${esc(r.name)}"
        aria-expanded="${this._open === r.name}"
        title="${esc(r.reason)}">
        <span class="name">${esc(r.name)}${r.occupied ? `<span class="dot" aria-label="occupied"></span>` : ""}</span>
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

  _details(r) {
    const f = (v, unit = "°", dp = 1) => (v == null || isNaN(v) ? "–" : `${Number(v).toFixed(dp)}${unit}`);
    const rows = [
      ["Thermometer", r.thermo ? `${r.thermo}${r.thermoSource === "TRV" ? " (TRV)" : ""}` : "none"],
      ...(r.hasHeater ? [
        ["Heater", r.heaterOn ? `on${r.powerW ? `, ${Math.round(r.powerW)} W` : ""}` : "off"],
        ["Energy today", r.kwh == null ? "–" : `${r.kwh.toFixed(2)} kWh${r.roomCost != null ? `, £${Number(r.roomCost).toFixed(2)}` : ""}`],
      ] : []),
      ["Need", r.level],
      ["Target", f(r.target)],
      ["Short by", r.deficit != null && r.deficit > 0 ? f(r.deficit) : "–"],
      ["Trend", r.trend == null ? "–" : `${r.trend > 0 ? "+" : ""}${Number(r.trend).toFixed(2)}°/h`],
      ...(r.pred2 != null ? [
        ["In 2 h", f(r.pred2)],
        ["In 8 h", f(r.pred8)],
        ["Reaches baseline", r.hoursToBase == null ? "not soon" : `in ${Number(r.hoursToBase).toFixed(1)} h`],
      ] : []),
      ...(r.grade ? [["Insulation", `${r.grade} ${r.rating} (${Math.round(r.tau)} h)`]] : []),
      ...(r.gain != null && r.tau != null ? [["Free heat", f(r.gain)]] : []),
      ...(r.warmup != null ? [["Warm-up", `${Number(r.warmup).toFixed(1)}°/h`]] : []),
      ...(!r.grade || r.warmup == null ? [["Learning", `${r.calibration ?? 0}%`]] : []),
    ];
    return `<dl class="details">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>`;
  }

  _roomStepper(r) {
    if (!r.setpointEntity) return "";
    const d = this._data;
    const key = `room-${r.name}`;
    const vs = r.vsHouse == null || Math.abs(r.vsHouse) < 0.05 ? "same as house" : `${r.vsHouse > 0 ? "+" : ""}${Number(r.vsHouse).toFixed(1)}° vs house`;
    const tip = `${r.name} heats to this while in use (presence, lights, schedule or Heat now). Empty, it stays at ${fmt(d.baseDay)}. `
      + (r.hasHeater ? "Its electric heater switches on its own, so it can differ from other rooms."
        : r.hasTrv ? "Its TRV opens and closes on its own, so it can differ from other rooms."
        : "No TRV here: it can ask for heat, but its radiator can't be shut, so it also warms with the rest of the house.");
    return this._stepper(r.setpointEntity, r.setpoint, "Target when in use", key, tip, vs);
  }

  _actions(r, compact = false) {
    if (!r.overrideEntity) return compact ? `<div class="actions"><p><b>${esc(r.name)}</b>: ${esc(r.reason)}</p>${this._roomStepper(r)}${this._details(r)}</div>` : "";
    const opt = (key, text) => `
      <button data-ov="${key}" data-entity="${r.overrideEntity}" aria-pressed="${r.override === key}">${text}</button>`;
    const until = r.overrideUntil ? new Date(r.overrideUntil).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : null;
    return `
      <div class="actions" role="group" aria-label="${esc(r.name)} override">
        <p>${compact ? `<b>${esc(r.name)}</b> ${esc(STATE_LABEL[r.verdict] || r.verdict).toLowerCase()}: ` : ""}${esc(r.reason)}${until ? `. Override until ${until}` : ""}</p>
        ${this._roomStepper(r)}
        ${this._details(r)}
        <div class="buttons">${opt("heat", "Heat now")}${opt("off", "Turn off")}${opt("auto", "Back to auto")}</div>
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

function fmt(v) {
  return v == null ? "–" : `${Number(v).toFixed(1)}°`;
}

function fmtN(v) {
  const n = Number(v);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
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
  .roof { display: block; width: 100%; height: 18px; overflow: visible; }
  .roof polyline { fill: none; stroke: var(--primary-text-color); stroke-width: 1.2; vector-effect: non-scaling-stroke; opacity: .55; }
  .floor { display: grid; grid-template-columns: 52px 1fr; border-left: 1.5px solid var(--sh-line); border-right: 1.5px solid var(--sh-line); border-top: 1px solid var(--sh-line); }
  .floor-name { padding: 10px 0 0 8px; font-size: .75rem; color: var(--sh-muted); display: flex; flex-direction: column; gap: 2px; }
  .floor-name span { font-size: .8125rem; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .ground-line { height: 0; border-top: 2.5px solid var(--primary-text-color); opacity: .55; margin: 0 -6px; }

  .rooms { display: grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap: 6px; padding: 8px 8px 8px 0; }
  .room { all: unset; box-sizing: border-box; cursor: pointer; display: flex; flex-direction: column; gap: 2px;
          padding: 8px 10px 8px 12px; border-radius: 6px; border-left: 3px solid transparent;
          background: color-mix(in srgb, var(--primary-text-color) 4%, transparent); min-height: 72px; }
  .room .name { font-size: .8125rem; color: var(--primary-text-color); display: flex; align-items: center; gap: 6px; }
  .room .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--primary-color); }
  .room .temp { font-size: 1.375rem; font-weight: 500; font-variant-numeric: tabular-nums; color: var(--primary-text-color); line-height: 1.15; }
  .room .temp small { font-size: .75rem; font-weight: 400; color: var(--sh-muted); }
  .room .meta { font-size: .75rem; color: var(--sh-muted); display: flex; flex-wrap: wrap; column-gap: 6px; }
  .room .target { opacity: .8; margin-left: auto; white-space: nowrap; }

  .room.v-approved { border-left-color: var(--sh-heat); background: var(--sh-heat-soft); }
  .room.v-approved .meta { color: var(--sh-heat); }
  .room.v-piggyback { border-left-color: var(--sh-top); }
  .room.v-deferred { border-left-color: var(--sh-coast); }
  .room.v-off { border-left-color: var(--sh-off); opacity: .7; }
  .room.v-fault { border-left-color: var(--sh-fault); }
  .room.v-fault .meta { color: var(--sh-fault); }
  .room.dumb { background: transparent; border: 1px dashed var(--sh-line); border-left-width: 3px; }
  .room[aria-expanded="true"] { box-shadow: inset 0 0 0 1px var(--primary-text-color); }

  .actions { grid-column: 1 / -1; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--sh-line); }
  .actions p { margin: 0 0 8px; font-size: .8125rem; color: var(--sh-muted); }
  .actions .buttons { display: flex; flex-wrap: wrap; gap: 6px; }
  .details { margin: 0 0 10px; display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px 12px; }
  .details dt { font-size: .6875rem; color: var(--sh-muted); }
  .details dd { margin: 0; font-size: .875rem; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  .logbtn { all: unset; cursor: pointer; font-size: .75rem; color: var(--primary-color); padding: 2px 0; }
  .logbtn:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .log { list-style: none; margin: 8px 0 0; padding: 8px 0 0; border-top: 1px solid var(--sh-line); max-height: 260px; overflow-y: auto; }
  .log li { display: grid; grid-template-columns: max-content 1fr; gap: 8px; padding: 4px 0; font-size: .8125rem; color: var(--primary-text-color); }
  .log time { color: var(--sh-muted); font-variant-numeric: tabular-nums; }
  .log b { font-weight: 500; }
  .log .muted { color: var(--sh-muted); font-size: .8125rem; margin: 0; }
  .actions .buttons button { all: unset; cursor: pointer; padding: 6px 12px; border-radius: 14px; border: 1px solid var(--sh-line); font-size: .8125rem; color: var(--primary-text-color); }
  .actions .buttons button[aria-pressed="true"] { border-color: var(--primary-text-color); }

  footer { margin-top: 12px; display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; }
  footer dl { margin: 0; display: flex; flex-wrap: wrap; gap: 8px 20px; }
  footer dt { font-size: .75rem; color: var(--sh-muted); }
  footer dd { margin: 0; font-size: 1rem; font-weight: 500; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  footer [data-more] { cursor: pointer; border-radius: 6px; }
  footer [data-more]:hover dd, footer [data-more]:focus-visible dd { color: var(--primary-color); }
  footer [data-more]:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  footer p { margin: 0; font-size: .75rem; color: var(--sh-muted); }
  .empty { padding: 8px 0; color: var(--sh-muted); }


  /* compact layout */
  .compact { display: flex; flex-direction: column; gap: 2px; }
  .cfloor { display: grid; grid-template-columns: 46px 1fr; column-gap: 8px; padding: 6px 0; border-top: 1px solid var(--sh-line); }
  .cfloor:first-child { border-top: 0; }
  .clabel { font-size: .75rem; color: var(--sh-muted); display: flex; flex-direction: column; padding-top: 5px; line-height: 1.25; }
  .clabel span { color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; min-width: 0; }
  .chip { all: unset; box-sizing: border-box; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
          height: 30px; padding: 0 9px; border-radius: 15px; max-width: 100%;
          background: color-mix(in srgb, var(--primary-text-color) 5%, transparent); border: 1px solid transparent; }
  .chip .cname { font-size: .8125rem; color: var(--sh-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 112px; }
  .chip .ctemp { font-size: .875rem; font-weight: 500; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  .chip .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--primary-color); flex: none; }
  .chip.v-approved { background: var(--sh-heat-soft); border-color: var(--sh-heat); }
  .chip.v-approved .ctemp, .chip.v-approved .cname { color: var(--sh-heat); }
  .chip.v-piggyback { border-color: var(--sh-top); }
  .chip.v-deferred { border-color: var(--sh-coast); border-style: dotted; }
  .chip.v-off { opacity: .55; }
  .chip.v-fault .ctemp { color: var(--sh-fault); }
  .chip.dumb { background: transparent; border: 1px dashed var(--sh-line); }
  .chip.dumb.v-approved, .chip.dumb.v-piggyback { border-style: dashed; }
  .chip[aria-expanded="true"] { outline: 1.5px solid var(--primary-text-color); outline-offset: 1px; }
  .chip:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .cdetail { grid-column: 1 / -1; margin-top: 6px; }
  footer.slim { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--sh-line); align-items: center; }
  footer.slim dl { gap: 4px 16px; }
  footer.slim dt { display: inline; margin-right: 4px; }
  footer.slim dd { display: inline; font-size: .875rem; }
  footer.slim p { display: none; }
  footer.slim { flex-wrap: nowrap; }
  footer.slim .logbtn { margin-left: auto; white-space: nowrap; }
  .cdetail .actions { padding: 8px 10px; }
  .cdetail .actions p { margin-bottom: 6px; }
  .cdetail .details { grid-template-columns: repeat(auto-fill, minmax(84px, 1fr)); gap: 4px 10px; margin-bottom: 8px; }
  .cdetail .details dd { font-size: .8125rem; }
  .cdetail .actions .buttons button { padding: 4px 10px; font-size: .75rem; }


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
  .more { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--sh-line); }
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
  .modebar .m-continuous[aria-checked="true"] { background: #e0622f; }
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
