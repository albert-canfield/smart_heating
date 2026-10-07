# Changelog

## 0.12.0
- Window and humidity advice. A small chip on the card says **Open windows 10 min** or **Close windows**, with the reason a tap away, and `sensor.smart_heating_window_advice` (`open` / `close` / `none`, with the reason, rooms, burst length, outdoor humidity and dew point) is there for automations. Each room's humidity and dew point are in the diagnostics.
  - Drying: when a room is above 65% humidity and the air outside is clearly drier, judged on dew point, so cold rainy days still count (light rain: open on the sheltered side; downpours, storms, hail and gales: no).
  - Without wasting heat: a short wide-open burst (5 min below 0°, 10 up to 10°, 15 up to 15°, 25 when mild, half in strong wind), then a **Close windows** reminder (straight away if a storm starts or everyone leaves; kept across restarts). Never while the house is heating (boiler or electric heaters), at night or while away, and at most every 2 hours.
  - Hot days (outside the heating season): open when a room reaches 24° and it is 2° cooler outside; close when it warms up outside or the rooms have cooled; keep shut with blinds down when it is hotter outside than in.
  - Outdoor humidity from a new optional sensor in the Outside step, or the weather entity.
- Notifications for the whole household (Configure, Notifications): pick one or more people and alerts go to the Home Assistant app on their phones. Window advice only goes to people at home at the time; learning finished and boiler problems go to everyone. Other notify services (a wall tablet, a Telegram chat) get every alert. Window alerts: never at night, at most 8 a day, each replacing the last on the phone; a close goes to the phones that got the open, home or not. An existing notify service carries over into Other notify services, and window alerts start once you save the Notifications page. Alerts can never get in the way of a boiler command.
- Learning is honest about what it knows:
  - A room counts as learned only when its result is steady: the fit is redone leaving out one group of days at a time and must move less than ±25%, with cooling data from at least 4 days. Until then the grade shows as a range, for example D-E (32-48 h), settling, and the Learning panel has a **Steady result** row. New attributes: `tau_low`, `tau_high`, `grade_range`, `settled`, `uncertainty_pct`.
  - Cooling samples from an hour before a sudden rise in temperature or moisture (shower, cooking, sun) to 2 h after it are left out. They made rooms look leakier than they are, bathrooms most. Moisture is judged by dew point, because relative humidity rises by itself as a room cools.
  - A room that never gets that steady (heat from neighbours that changes day to day) counts as learned after 240 hours of cooling data (2 to 4 weeks) and keeps showing its range.
  - Old data fades with a 30-day half-life, so draught-proofing or new windows show up.
  - After updating, rooms show Learning again until they have 4 days of new data; what was learned so far is kept and fades out.
- Diagnostics: each room's uncertainty, samples per day group and samples skipped; window advice and the readings behind it; which phones alerts reach.
- **Breaking**: the Continuous mode is now **Auto** (`select.smart_heating_mode` option `auto` instead of `continuous`), which says what it does: heat each room when it needs it. Automations that set or check `continuous` need `auto`. The saved mode carries over.
- README: new cover and refreshed screenshots, rendered from the real card with `docs/render.py`.

## 0.11.0
- Energy is shared out instead of all or nothing: the meter is the truth for the total, boiler time (heating, hot water, both) and heater time (per mode) decide the share, and the rates are learned from your own days (rolling 28 days, starting from 70% of the boiler's input and the heaters' rated power, with a cold-weather term for heating).
- Gas: Heating gas today and its cost (the existing sensors, now heating only), plus Hot water gas today, and with a smart meter Other gas today and House gas today. Heating + hot water + other = the meter.
- Electricity: each heater's real draw is learned (a 2000 W heater in a half mode becomes 1 kW), quickly from a live house power sensor when you have one; Heating electricity today and its cost, plus Other and House electricity with a smart meter. Electricity costs follow a unit rate sensor too.
- Setup asks the energy questions that match your heating: gas for boilers, electricity for electric heaters, both for hybrid. Without a smart meter, the simple estimates stay: boiler time at 70% of its input, heater time at its rated power.
- Each day after midnight the meter total is shared out and logged; learned rates and the recent error are on the heating sensors and in diagnostics.
- Card: the bottom shows only the heating's kWh and cost, with a flame for gas and a bolt for electricity (both for hybrid). The (i) next to it opens the breakdown: heating rows count, each item is a bullet, hot water and the hob are greyed and not counted, with subtotals per fuel, plus the total heating cost for hybrid. Any row opens its history.
- Card: in the compact layout the expanded rooms sit inside the house outline (roof, walls and ground), as in the full layout. Roof, walls and ground share one line width and colour, the roof sits straight on the walls, and the lines between floors are thin and a little lighter.
- Card: an open room's panel has a light highlight so it stands out.

## 0.10.3
- Card: rooms in use show a small person icon (with an "In use" tooltip) instead of a blue dot, which was easy to confuse with the blue status dot for hot water priority.

## 0.10.2
- Season gate is a bar, not a wall: on mild days a room in use heats when it is clearly cold (1.5° below target and not warming by itself, adjustable as Mild-day margin), empty rooms wait, and what you ask for always heats. Default gate 15.5° (the usual UK figure), with a 0.5° margin so it doesn't flip.
- One Cycle heats the rooms in use and any Heat now rooms, even on mild days. With nothing to heat it waits 3 minutes and the card says why, with a countdown, Heat all rooms below target, and Off now.
- Heat now heats from any shortfall, skips coasting and batching, works while away, and while Off starts One Cycle, which ends when the room reaches its target.
- Off cancels everything: One Cycle, Heat now in every room, a running heat test, and the boiler at once.
- A room in use whose comfort equals the baseline is now treated as in use, not empty.
- A new setup no longer restores Watch or Mode states left by an earlier setup with the same entity ids.

## 0.10.1
- No outdoor sensor needed: without one, the weather entity's current temperature is used.
- A failed or empty forecast fetch is retried after 5 minutes instead of 30 (for example while the weather entity is still starting), and no longer clears the forecast already held.
- `sensor.smart_heating_outdoor_day_mean` shows forecast mean and minimum for 12 h and 24 h and the observed 12 h mean as attributes, so template helpers for these can go.
- Deleting the integration also deletes its stored data (learned models, energy, log), so a new setup starts clean.

## 0.10.0
- Heats from day one and learns in the background. The heating logic never used the learned model, so waiting for calibration only delayed it. Setup ends with Start heating now or Watch first; Start control without calibration and Skip calibration are gone.
- Start heating on the card asks to confirm (Start heating or Cancel, cancels itself after 10 s) and lists other automations that switch the heating.
- Configure, Relearn Rooms (and service `smart_heating.relearn`): clears what chosen rooms have learned, after a confirmation.
- Setup checks in Repairs: hot water sensor that is the boiler's own signal (now ignored, and refused by the wizard), automations that switch the heating, boiler running sensor that doesn't respond.
- Heat test: a room without a smart valve can only be stopped with the boiler, so the test ends when one reaches 21.5°.
- Piggyback top-ups start half the hysteresis below target and run to target + overshoot: no more valve open/close every minute for a room sitting at its target.
- Learning: a typical free-heat value anchors the first estimates and fades as real data varies, so one night gives sensible insulation figures instead of 5 h or 300 h.
- Log: a changing trend in a reason no longer adds a line, room faults in the first minutes after a restart are not logged, and the log is kept across restarts.

## 0.9.8
- Gas setup asks for a smart meter integration (for example Octopus Energy or Glow): a consumption sensor (kWh or m³, a total that restarts at midnight is fine) and an optional unit rate sensor. Without one, gas is estimated from boiler running time and the boiler's input (for example 15 kW).
- Costs are unit costs only: the standing charge is gone from the calculations and from Configure. With a rate sensor, each kWh is costed at the rate when it was used.
- Tap gas or electricity figures on the card to open their history. Daily cost sensors now reset cleanly in long-term statistics.

## 0.9.7
- Gentler heat test: only rooms that still need heating data, each stops about 1° warmer than it started and never above 21.5° (was 23°). Rooms that already have their data stay closed; the test isn't offered when no room needs it.
- New README with screenshots.

## 0.9.6
- Spinner in front of "Heat test running".
- During a heat test the log and boiler demand show what the test does.
- "Starting up" instead of a false fault for 2 minutes after a restart.

## 0.9.5
- Boiler protection on every command: 2 minute minimum between switches, backs off when something else switches the boiler, flicker lockout (more than 6 switches in 30 minutes), heat test stops if interrupted.
- Heat test lists other automations that use the boiler control.

## 0.9.0 to 0.9.4
- Step-by-step setup wizard starting with "What heats your home?".
- Electric heaters (smart plugs or smart heaters) and hybrid homes, with energy and cost tracking.
- Thermostat setpoint style; hot water tank, combi or none.
- Card: status indicators, pulsing status dot, title and icon, visual editor.

## 0.8.0
- Calibration panel with progress, time left and tips; one-tap heat test; Start control when ready.
- House target and per-room targets with steppers.

## 0.7.x
- Rooms from Home Assistant areas and floors; insulation index; decision log; diagnostics; compact card.
