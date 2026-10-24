# Changelog

## 0.15.5
- A room is in use 1 minute after its presence sensor (or a media player) switches on, instead of after 5 minutes of continuous presence. That was slow, and with motion sensors, which drop back to off after a minute or so without movement, a room could take much longer or never count. Smart Heating also checks again right at that minute instead of waiting for its next regular update. A walk-through still doesn't count.
- Responsive again: presence, lights, media, doors and windows, schedules, the boiler and hot water, heaters and away act at once, as before 0.15.3. Only measurements (temperatures, humidity, power, TRV readings, weather), which report every few seconds, still refresh Smart Heating at most every 30 seconds, which keeps the database light.
- The house target moves only the in-use targets of the rooms. The day and night baselines for empty rooms stay where you set them (Configure, Temperatures and Night); before, they moved with the house target. The house target can't go below the day baseline.
- **Motion sensors** (device class motion) mark a room in use after two triggers within 10 minutes, or 5 minutes on, so a walk-through doesn't count. Presence sensors (occupancy, mmWave) keep the 1 minute rule.
- **Night**: rooms stay at the night baseline. Only the room's schedule or Heat now brings comfort heat at night; presence, media and lights no longer do (people sleep in the room with a sensor or a night light on).
- **TRVs always stay in heat mode**: closed is the frost setpoint (5° by default), so the TRV still guards against freezing; a TRV found in mode off is switched back to heat. New option **Open TRVs fully** (Configure, Advanced): an open TRV goes to its max (30° on most, like the Kasa KE100) instead of target + offset, so its own sensor by the hot radiator can't close it early. With it on there is no room cap if Home Assistant stops while the boiler runs.
- The kill switch, Watching only and a mode change now stop TRV, heater and boiler commands already on their way (a plan moving many TRVs takes seconds). Turning Smart Heating off also stops a heat test.
- A room whose thermometer is unavailable keeps its TRV as it is (it was closed). With every thermometer down, electric heaters go off.
- A room with no radiator and no heater (watched only) never calls the boiler.
- A hybrid room whose heater is held off by a precaution heats on gas instead of waiting.
- On a mild day a cold room already heating carries on until it is warm, instead of stopping halfway. Coasting only delays starting the boiler: a room joins a run already going.
- The boiler switch, its running sensor and the hot water sensor are no longer taken as a room's TRV or heater when rooms are made from areas.
- Boiler flicker lockout: logged and notified once, not on every cycle while it lasts. The "boiler on for" time works with setpoint thermostats too.
- Heat now and Off on a room survive a restart until they expire. Learned data is saved every 10 minutes, not only on a clean stop, so a power cut loses little.
- After a heat test, TRVs go back to their mode and setpoint from before (a TRV that was off stays off).
- Door and window sensors now refresh the room at once.
- A daily gas or electricity total that resets after midnight is no longer taken as a revised reading (it lost the day's first part). A restart across midnight closes the electricity day instead of losing it.
- Import areas reloads Smart Heating once, not once per room. A failed setup no longer leaves listeners running.
- Lighter database: the status sensor's live room lists and reason, each room's decision reason and the prediction details are no longer recorded in history.
- The Notifications form shows the window alerts default the integration actually uses.
- Card: no lost steps when tapping + or - quickly; the header and room names wrap on phones instead of scrolling sideways; long floor and room names stay inside the card; a config change applies at once; keyboard focus stays put while the card updates, and the expand arrow is a real button; `hide_title` works in the full layout too; less work per Home Assistant update; no "heating by hour" fetch while the card is collapsed.

## 0.15.4
- The card is served from the integration again (`/smart_heating/smart-heating-card.js`) and no longer copied into your `www` folder, as asked in the HACS review. The dashboard resource is moved back automatically. If you ran 0.14.1 to 0.15.3, you can delete the `www/smart_heating/` folder they left behind.
- Floor names (and a few other values from Home Assistant: room names in the info buttons, entity ids, the currency) are escaped in the card, so a name with `<` or `"` can't break the card or add markup.

## 0.15.3
- **Sensor alerts on the card**: when a room's thermometer (or its TRVs, when it has none) is unavailable, or hasn't reported for 3 hours, a small alert icon shows in front of the room and at the top right of the card. Hover for what's wrong; tap the top one for the list. Heating does nothing different. Also in `sensor_issue` on each room's need sensor and `sensor_issues` on the status sensor, for automations.
- Removed the "heat rising from below" wait. Upper rooms a little under target no longer wait up to 40 min while a lower floor heats: how much heat rises depends on which rooms heat below, so a fixed rule was usually wrong, and the held room often needed its own boiler run later. Now it joins the run already going. The Upper floor max wait setting (Advanced) is gone.
- After a restart or reload, no TRV or boiler command goes out until the mode, Enabled and Watching only are restored. Before, the first decision ran as Auto, so with Off or Watching only set it could move the TRVs once.
- A boiler command that fails (the switch drops off the network mid-command) no longer breaks that update. It counts as not sent: it isn't counted towards boiler protection, isn't taken for something else switching the boiler (no 15 min back-off), is noted once in the log and is sent again on the next cycle.
- Much lighter on the Home Assistant database. Each room's need sensor no longer records its live values (temperature, trend, deficit, reason and a few more) in history: they changed on almost every refresh and stored a new attribute row each time, about 5 MB a day per room. The house temperature sensor no longer records every room's reading. The card still shows all of them live; settings-like values (target, its source, in use, override) stay in history.
- The room trend is rounded to 0.1°/h (the card shows one decimal), so it no longer changes on every refresh.
- Sensor changes refresh Smart Heating at once, then at most every 30 seconds instead of every 10. Taps on the card (mode, Heat now) still act at once.
- README and docs brought in line with the code: the heating gas and electricity sensors' entity ids on new installs (`sensor.smart_heating_heating_gas_today`, `..._heating_gas_cost_today`, `..._heating_electricity_today`), up to 8 h of cooling data a night, the full room settings table, which alerts go to whom, Repairs checks, status and room attributes for automations, and no more mentions of heat rising between floors.

## 0.15.2
- When a room is in use, in order: a presence sensor decides; with no presence sensor the lights do; with neither, **Heat now** on the card (or a schedule). Media players playing count like presence.
- Lights (rooms with no presence sensor): the room is in use for as long as a light is on, and for 30 minutes after it goes off (switching one on and straight off counts too). Before, a light only counted for its first 30 minutes and the room emptied as soon as it went off.
- Rooms with a presence sensor ignore their lights: a light left on in an empty room no longer starts its comfort heating.

## 0.15.1
- New room setting **This room has no window or door to outside**, just above the door and window sensors. Tick it for a room like an inner bathroom: it is left out of window advice (no "open the windows" or "close" for it, no alert, no window icon on its chip), and its door and window sensors are ignored and cleared when you save, so it never pauses for one. Its humidity still shows in diagnostics.

## 0.15.0
- **Heating by hour**: the breakdown behind the (i) opens with a small chart of today's heating energy per hour, one line per fuel the house has (gas, electricity), so you can see when in the day the heating used it. It reads Home Assistant's own statistics of the gas and electricity sensors, so it covers the whole day, also after a restart. Hover an hour for its kWh; a dashed line marks now.
- **Window advice on the rooms**: the rooms the window advice is about get a tiny window icon in front of their name, open (blue) or closed (amber), with the advice on hover. The chip at the top is unchanged.
- README: an animated cover with a short tour of the card (rooms, a room panel, heating by hour, window advice).

## 0.14.3
- Fixes the real cause of the card's "Custom element doesn't exist: smart-heating-card". Home Assistant's app loads a polyfill that replaces the browser's custom element registry with its own, which only knows elements defined through it. The card's script loads at the same time as the app; when it ran first (often on a reload, with everything cached), the card was defined in the browser's registry and Home Assistant never found it, so even rebuilding it (0.14.2) failed. The card now notices the swap and registers itself with Home Assistant's registry too, and Home Assistant swaps the real card in.
- The self-repair from 0.14.2 waits until Home Assistant can find the card, and also runs when an older copy of the card (a cached page) loaded first.

## 0.14.2
- Fixes the card still showing "Custom element doesn't exist: smart-heating-card" now and then, mostly after a reload. The dashboard and the card's script load at the same time; when the dashboard builds the card first, Home Assistant swaps the real card in once the script has run, but not when the card sits inside some custom cards (stacks, expanders, swipe cards). The card now finds such leftovers and rebuilds them itself, including ones shown later (a folded section opening). The browser console says when it did, and inside which card.

## 0.14.1
- The card loads more reliably. It could show "Configuration error" on a page opened while Home Assistant was still starting: Home Assistant serves dashboards before custom integrations have started, and a page only picks up an integration's card script when it loads, so such a page never got the card. The card is now copied to `www/smart_heating/` (served from the start) and kept as a dashboard resource that every dashboard loads, updated automatically after each update. Still one HACS install.
- The card is sent gzipped (24 KB instead of 95 KB) to browsers that accept it.
- The browser console shows a **Smart Heating 0.14.1** badge when the card loads, and a warning if an older copy is already running.
- While Home Assistant starts, the card says "Smart Heating is starting" instead of asking to add rooms.
- Deleting Smart Heating also removes its dashboard resource and the copy in `www`.
- Room devices link to the house device by device id on Home Assistant 2026.8 and later (`via_device_id`), which ends the "deprecated `via_device` parameter" warnings; the old link stops working in 2027.8. Older versions keep the old link.
- Reconfigure (house and rooms) shows "Saved." / "Room saved." again on Home Assistant 2026.10 and later, and reloads Smart Heating once instead of twice. Home Assistant 2026.12 would have rejected the second reload. If set-up had failed, saving still reloads it to try again.
- Room sensor discovery skips the model and maker of Home Assistant 2026.10's new child devices (reading them warns now and fails from 2027.9).
- The card no longer says "Door open: heating paused" during the first minute, before the room is actually paused.
- No more "Forecast fetch failed" warning while Home Assistant starts and the weather entity isn't there yet (it retries within minutes, as before).

## 0.14.0
- Doors and windows to outside: a new room setting for their contact sensors (window sensors in the area are filled in; outside doors are added by hand). While one is open for more than a minute the room pauses: its TRV closes or its heater goes off, and it does not ask for heat; frost protection still can. After it closes the room waits up to 20 minutes for heat from the rest of the house before it may start the boiler, only when the drop was the opening's doing, and it stops waiting once it is back where it was or if it is still falling 10 minutes after closing.
- A small door or window icon on the room while one is open or the room is recovering, with a tooltip; the room panel says "Door open: heating paused" or "Front door closed: recovering, 12 min left".
- A phone alert to whoever is home when one stays open 30 minutes while the heating is needed.
- The drop while open, and the hour after, is left out of learning. Each room's recovery times are kept in diagnostics (`recoveries_min`) to learn a per-room wait later.
- Window advice: no "close the windows" reminder when the advised rooms' window sensors all read shut.
- README: screenshots and the How it decides diagram show doors and windows.

## 0.13.0
- New room panel. Tap a room: its temperature and state on top, and a scale with the frost, night, empty and in-use temperatures, the one that applies now lit up. Then **Target when in use** with **Auto / Heat now / Off** under it (the panel stays open after a tap). **Room profile** folds out a one-line summary of why the room has its target, a **Prediction without heating** (in 2 h, in 8 h, and when it would reach the baseline), and small tiles for insulation, warm-up and free heat, plus the heater and its energy, or an always-open radiator, where there is one.
- The card shows what really happens, from device states: a room counts as heating only while the boiler heats its radiator (TRV open, or no TRV, like a bypass radiator) or its electric heater is on. Fixes "Heating 0 rooms" while rooms heated (valves already open were not counted), orange rooms while the boiler was paused for hot water, waiting, held by boiler protection, disabled or watching only, and the heat test showing its rooms as idle. Rooms that want heat but get none yet show as **Wants heat**.
- Boiler protection is visible: "Boiler protection until 12:15" instead of "Heating 3 rooms" while it holds the boiler back.
- New `sensor.smart_heating_heating_hours_today`: how long the heating was on today (boiler heating rooms, or any electric heater; hot water left out).
- The bottom of the card reads **Today 🕐 1.2 h 🔥 3.8 kWh £0.35 (i)**: the clock opens the heating hours, the kWh its sensor, the (i) the breakdown. Hours and cost appear once there are some.
- Window chip shortened to **Open 10min** / **Close** so it fits on a phone; the tooltip keeps the full reason.
- Status attributes for automations: `heating_rooms`, `radiator_rooms` and `heater_rooms` now come from device states; new `wanted_rooms`, `boiler_called` and `boiler_hold_until`. Each room's need sensor has `heating_now`, `heater_on` (the device) and `heater_wanted` (our command).
- Smaller fixes: electric heater hours are wall-clock time (they read 0 with power sensors, and two heaters counted twice); gas heating hours match the footer; the electricity breakdown shows "Everything else"; away shows its real reason; "Coasting" is now "Waiting"; the idle line says how many rooms are waiting; the in-use icon follows the room's comfort state; "Reaches baseline" uses the night baseline at night; the house grade is faded while settling; mode and override errors show on the card; C and D grades are readable.
- Numbers on the card come from the integration instead of being typed in: heat test limits, cooling hours per night (from the night times), calibration thresholds, the stepper's range and step, and the currency (from Home Assistant).
- No topping up for rooms without a radiator (they showed "Topping up" in hybrid homes).
- Radiators without a TRV (a bypass radiator, for example) count as heating whenever the boiler runs, so a rise while it heats is no longer mistaken for the room warming on its own.
- Electric heater safety: a heater is kept off, with a phone alert and a Repairs entry, when the room's reading hasn't been reported for 60 minutes, or the heater has been on for 30 minutes without the reading moving; it rests 15 minutes after 2 hours on, waits for live readings after a restart, and never heats above target + 1° or 24°. These only ever switch a heater off, never on. Radiators and the boiler are not affected.
- Repairs flags a heater room that has had no temperature for 30 minutes.
- Each room has a state, worked out from what it has and whether a reading arrives: controlled, follows the boiler (radiator without a TRV), watched only (nothing to heat it) or not working (no reading). The card shows **No temperature**, **Watched only** and **Heater stopped** with the reason; `room_state` and `heater_stopped` are on each room's need sensor. A watched-only room is left out of the house average but still counts on its floor.
- New room setting **Can switch the boiler on** (on by default). Off for an always-open radiator: the room warms whenever another room calls, but never starts or keeps the boiler running by itself. Frost protection and Heat now still can. The room's profile shows "Boiler: Never starts it".

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
