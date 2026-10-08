<p align="center">
  <img src="https://raw.githubusercontent.com/albert-canfield/smart_heating/main/docs/images/hero.jpg" alt="Smart Heating: turn your heating into a smart, multizone system, with window and humidity advice on your phone" width="100%">
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=albert-canfield&repository=smart_heating&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open in HACS"></a>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <a href="https://github.com/albert-canfield/smart_heating/releases"><img src="https://img.shields.io/github/v/release/albert-canfield/smart_heating" alt="Release"></a>
  <a href="https://github.com/albert-canfield/smart_heating/actions/workflows/validate.yml"><img src="https://github.com/albert-canfield/smart_heating/actions/workflows/validate.yml/badge.svg" alt="Validate"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.2%2B-18BCF2" alt="Home Assistant 2026.2+">
</p>

# Smart Heating

**Turn your home's heating into a smart, multizone system that learns.**

Tired of a heating system that heats empty rooms, fires the boiler for half a degree and has no idea it will be mild tomorrow? Smart Heating builds a profile of your home: how fast each room loses heat, how quickly it warms up, how much the sun, people and cooking add, and how heat rises between floors. It reads the weather forecast, follows how you actually use each room, and heats only where and when it makes sense.

Comfort where you are, savings everywhere else. And it is fully transparent: you see the gas and electricity used, what it cost, an insulation grade for every room, and the reason behind every decision.

It works with what you already have: a gas boiler with a tank, a combi, electric heaters or a mix of both, on one floor or several.

## Why Smart Heating

| | |
|---|---|
| 🏠 **Multizone from what you own** | Smart TRVs, a boiler relay or thermostat, smart plugs or smart heaters become one coordinated system, room by room. |
| 🧠 **Learns your home** | Measures each room's heat loss, warm-up speed and free heat from normal life, then predicts temperatures hours ahead. |
| 🌦️ **Plans with the forecast** | Skips heating on mild days and knows how cold tonight will be. |
| 🚶 **Follows your habits** | Presence sensors, lights, media and schedules decide which rooms deserve comfort. Empty rooms are kept at a sensible baseline. |
| 🔥 **Burns less** | Waits when a room is already warming, lets heat rise from the floor below, batches small demands and gives hot water priority. |
| 💧 **Tackles damp** | Tells whoever is home when a short airing will dry the house, judged on dew point so rainy days count, and never while the house is heating. On hot days it says when to open up and when to keep the heat out. |
| 🪜 **One floor or many** | Uses the stack effect in multi-floor homes so upper rooms often heat themselves. |
| ⚡ **Gas, combi, electric or hybrid** | Rooms with only electric heat never fire the boiler. One room with a heater? It uses the heater instead of firing the whole boiler. |
| 📊 **Fully transparent** | The heating's own kWh and cost today (gas and electric, separated from hot water and the rest of the house), an A to G insulation grade per room, floor and house, and a log of every decision. |
| 🛡️ **Safe by design** | Frost protection is always on, and the boiler is protected from short cycling. It never fights your other controls. |
| 🧩 **Set up in minutes** | A short wizard asks what heats your home. Your Home Assistant areas become rooms with their sensors filled in. |

## See it in action

<p align="center"><img src="https://raw.githubusercontent.com/albert-canfield/smart_heating/main/docs/images/trio.jpg" alt="The card while learning, while heating with hot water at night, and when off" width="100%"></p>

One card for the whole house: temperature, status at a glance, floor averages, mode buttons and a house target. The background shifts from blue to orange with the house temperature.

<table>
  <tr>
    <td width="50%"><img src="https://raw.githubusercontent.com/albert-canfield/smart_heating/main/docs/images/rooms.jpg" alt="Expanded card with room details, heater power, energy and insulation"></td>
    <td width="50%"><img src="https://raw.githubusercontent.com/albert-canfield/smart_heating/main/docs/images/cal.jpg" alt="Calibration panel with progress bars and a one-tap heat test"></td>
  </tr>
  <tr>
    <td><b>Every room, explained.</b> Why it is heating or waiting, its own target, predictions for the next hours, energy used and its insulation grade.</td>
    <td><b>Learning you can follow.</b> See what it is learning and how long is left, and speed it up with a gentle one-tap heat test.</td>
  </tr>
</table>

<p align="center"><img src="https://raw.githubusercontent.com/albert-canfield/smart_heating/main/docs/images/wizard.jpg" alt="Setup starts with one question: what heats your home?" width="70%"></p>
<p align="center"><i>Setup starts with one question. The next steps only ask what your home needs. (Illustration of the setup flow.)</i></p>

## How it decides

<p align="center"><img src="https://raw.githubusercontent.com/albert-canfield/smart_heating/main/docs/images/how.jpg" alt="Senses, need, efficiency, acts" width="100%"></p>

Two voices must agree before the boiler fires. **Need** asks whether a room is below its frost floor, its baseline or, while in use, its comfort target. **Efficiency** asks whether burning now is worth it: is it mild outside, is the room already warming, is heat rising from below, is the demand too small, is hot water heating first? Valves and heaters move only when there is a reason.

## Quick start

1. Install from HACS with the button above, then restart Home Assistant.
2. Settings, Devices & services, Add integration, **Smart Heating**. Answer the short wizard and tick the rooms to heat.
3. Add the card to a dashboard: `type: custom:smart-heating-card`.

Smart Heating heats from day one with sensible defaults and learns your home in the background (first figures in a day or two, steady insulation grades in about 4 days to 3 weeks). Prefer to look first? Pick **Watch first** at the end of setup and tap **Start heating** on the card when you're happy.

---

# Documentation

Version 0.13.0. How it starts:

1. **Heating from day one** (or **Watching** if you picked *Watch first*: it decides and logs, never touches the boiler or TRVs, until you tap **Start heating** and confirm).
2. **Learning in the background**: each room's heat-loss time constant, free-heat gain and warm-up rate, from normal life. Heating decisions don't wait for it.
3. **Learned**: predictions, insulation grades and warm-up appear room by room as each is learned, and a notification arrives when most rooms are done.

### Learning in short

| Question | Answer |
|---|---|
| What does it need? | Per room: about 24 h of **cooling data** (boiler off for at least 1 h), a 2° **range** in the inside/outside gap, and about 2 h of **heating data** (boiler on, radiator open). Then a **steady result**: the fit is redone leaving out one group of days at a time and must move less than ±25%, which needs cooling data from at least 4 days. Cooling samples from an hour before a sudden rise in temperature or moisture (shower, cooking, sun; moisture by dew point, since relative humidity rises by itself as a room cools) to 2 h after it are left out, and old data fades with a 30-day half-life. A room that never gets that steady (heat from neighbours that changes day to day) counts as learned after 240 hours of cooling data (2 to 4 weeks) and keeps showing its range. Done when 80% of rooms are learned. Until then grades show as a range (for example D-E). Until the range builds up, a typical free-heat value keeps first estimates sensible. |
| How long? | First figures in a day or two; steady results in about 4 days to 3 weeks (bathrooms and sunny rooms take longest, because their data is the noisiest). Tap the **Learning** badge on the card for progress, what it's collecting now and roughly how long is left. |
| Does heating wait for it? | No. The heating logic (targets, presence, night, hysteresis, coasting, stack effect, hot water priority, boiler protection) works from the start. |
| How do I speed it up? | Tap **Run heat test** in the Learning panel. It is gentle: only rooms that still need heating data are opened, each stops about 1° warmer than it started and never above 21.5°. A room without a smart valve can only be stopped with the boiler, so the test ends when one reaches 21.5°. Usually under 2 h, then the house cools. Leave the heating off overnight: each night gives up to 10 h of cooling data. |
| A room learned something wrong? | Configure, **Relearn Rooms**: pick the rooms and confirm. For example after a valve was shut during the heat test, or after new windows. |

Only real radiator heat counts: burns for hot water only (cylinder with the heating valve shut, or a combi running a tap) are treated as cooling time. Progress is saved, so restarts don't lose it.

### Modes, Heat now and mild days

| | What it does |
|---|---|
| **Off** | Stops everything: One Cycle, Heat now in every room, a running heat test, and the boiler at once. Frost protection stays on. |
| **One Cycle** | Heats the rooms in use (and any you pick with Heat now) to their targets once, then switches to Off. If nothing needs heat, the card shows why with a 3-minute countdown and offers **Heat all rooms below target** (empty rooms too, from any shortfall). |
| **Auto** | Heats each room when it needs it, firing the boiler only when it's worth it. This is the everyday mode. |
| **Heat now** (a room) | Heats that room from any shortfall. While Off it starts One Cycle, which ends when the room reaches its target. Works on mild days and while away. |

**Season gate** (outdoor day mean, last 12 h plus next 12 h; 15.5°C by default, the usual UK figure): below it is heating season and every room is heated normally. On milder days automatic heating needs strong evidence, while what you ask for always heats:

| Request | Heating season | Mild day, Auto | Mild day, One Cycle |
|---|---|---|---|
| Frost floor | heat | heat | heat |
| Heat now | heat | heat | heat |
| Room in use | heat (from 0.5° below) | only if cold: 1.5° below and not warming by itself | heat (from 0.5° below) |
| Empty room | heat | wait | wait |

Once mild, it stays mild until the mean drops 0.5° below the gate, so it doesn't flip back and forth. The log says which rule allowed or blocked each room.

### How energy is shared out

The meter is the truth for the total; run time decides how it is shared; the rates are learned from your own days.

- **Gas**: each minute the boiler burns is sorted by what asked for it: heating, hot water, or both. Each day, *meter = a x hot water hours + b x heating hours + k x heating hours x (degrees below 15.5° outside) / 10 + c*, fitted over the last 28 days. **a** and **b** are your boiler's real kWh per hour, **k** how much harder it works on cold days, **c** the hob. They start at 70% of the boiler's input (and 0.5 kWh/day for the hob) and need 3 meter days before they move; a day far off the rest (a meter glitch) is left out.
- **Electricity**: each heater's on time is counted per mode (full or eco), and its real draw is learned the same way (a "2000 W" heater in a half mode becomes 1 kW), starting from the power set in its room. With a live house power sensor, the jump when a heater switches on or off teaches its draw within minutes. A heater with its own power sensor is simply measured.
- **Live**: today's hours x the learned rates, updated as they run. **Daily**: after midnight the meter's total is shared out and logged, for example *Gas 2026-10-05: meter 31.8 kWh, heating 21.4, hot water 9.8, other 0.6 (model +4%)*. The learned rates, how many meter days they rest on and the recent error are attributes of the heating sensors and in the diagnostics.

### Setting temperatures

On the card, when the mode is One cycle or Auto:
- **House target** (− 19.0 +) moves every room together, plus the day and night baselines. The frost floor never moves.
- Tap a room for its own **Target when in use**. It keeps its difference from the house when the house target moves. Rooms without a TRV still ask for heat, but their radiator can't be shut.

Both are also entities (`number.smart_heating_house_target`, `number.<room>_target`) for automations. A new comfort set in a room's Reconfigure form replaces the card setting.

### Windows and humidity

A small chip next to the status says **Open 10min** or **Close**; tap it for the reason. The same advice is `sensor.smart_heating_window_advice` and, if you choose, a phone alert.

- **Drying**: when a room is above 65% humidity and the air outside is clearly drier. This is judged on dew point, not relative humidity: cold Scottish rain air at 95% holds far less water than a warm room at 70%, so light rain does not stop it (open on the sheltered side). Downpours, storms, hail and gales do.
- **Without wasting heat**: a short burst, wide open, then closed. The walls and furniture keep their heat and the heating only rewarms the air. The burst is 5 min below 0°, 10 min up to 10°, 15 min up to 15°, 25 min when mild, and half that in strong wind. It is never advised while the house is heating (boiler or electric heaters), at night or while away, and at most every 2 hours. A **Close windows** reminder follows when the time is up, or straight away if a storm starts or everyone leaves. Advice in progress survives a restart.
- **Hot days** (outside the heating season): open when a room is 24° or more and it is at least 2° cooler outside; close when it gets warmer outside or the rooms have cooled; keep closed with blinds down when it is hotter outside than in.

Humidity comes from each room's humidity sensor; outside, from an optional outdoor humidity sensor or the weather entity.

## Works with what you have

Setup asks **"What heats your home?"** first and then only what that setup needs:

| Heating | Typical kit | What Smart Heating does |
|---|---|---|
| **Boiler with a hot water tank** (also known as S-plan or Y-plan) | relay or thermostat, TRVs, tank sensor | Rooms vote, boiler fires for approved rooms, TRVs open and close as valves. Optional hot water first |
| **Combi boiler** (no tank) | thermostat or relay, TRVs | Same, without the hot water pause: the boiler already serves taps first |
| **Electric heaters only** | smart plugs on plain heaters, or smart heaters (`climate`) | Each room switches its own heaters; no boiler timing. Energy and cost tracked per room |
| **Boiler plus some electric heaters** | both | Electric-only rooms never fire the boiler. A room with a radiator and a heater uses the heater when it's the only room calling, instead of firing the whole boiler |

Combinations that work:
- **Thermostat + smart TRVs** (combi or tank): full room-by-room control. In *Setpoint* style the thermostat is nudged above its own reading when a TRV room calls, so it fires even if its own room is warm.
- **Thermostat + plain TRVs**: single zone, the thermostat gets the target, or the frost floor when off.
- **Relay only** (e.g. a Shelly on the boiler): single zone, on/off.
- **TRVs only**: valves are controlled, the boiler stays on its own thermostat.

Thermostat style: **Setpoint** (recommended: it gets the target and regulates, so it stays sensible if Home Assistant stops) or **On / off** (heat at 25° or off).

Electric heaters: a smart plug is switched on/off; a smart heater gets the room target and hvac off when not needed. Enter the heater's power (e.g. 2000 W) and optional eco power (e.g. 1000 W, used when a smart heater reports an eco preset). If the plug or heater has its own power sensor it is found automatically and measured power is used instead. Sensors: electricity today (kWh, with a projection to midnight), cost today, and per-room energy today.

**Electric heater safety.** A heater only runs with a live temperature behind it. A room with a heater needs a thermometer, a TRV or a smart heater that reports temperature (the room form refuses it otherwise), and the heater is kept off, with a phone alert and a Repairs entry, when:
- the room's reading hasn't been reported for 60 minutes (a thermometer with a dead battery often keeps its last value instead of going unavailable),
- the heater has been on for 30 minutes and the reading hasn't moved at all (a stuck sensor, or a heater that isn't heating),
- it has run for 2 hours without a break: it then rests for 15 minutes,
- Home Assistant has only just started and readings may not be live yet.
It also never heats a room above its target + 1°, nor above 24°. These only ever switch a heater off, never on, and it resumes by itself once readings are live and moving. Radiators and the boiler are not affected.

Other fallbacks:
- **No room thermometer**: the TRVs' or smart heaters' own reading is used (less accurate near the radiator).
- **No outdoor sensor**: the weather entity's current temperature is used, blended with its hourly forecast.
- **No weather entity either**: season gate and learning are skipped, predictions stay empty.
- **No presence, lights or media**: rooms use their comfort schedule and manual "Heat now".
- **No smart meter**: gas is estimated from boiler running time (boiler running sensor, or the heating switch or thermostat) at 70% of the boiler's gas input, and electricity from each heater's on time at its rated (or eco) power, flagged as estimates.
- **No away source**: away mode is never triggered; use the mode buttons.
- **No night schedule**: 22:00 to 07:00, changeable in Configure.
- **No areas or floors in HA**: rooms can still be added; floor is then picked in the room form.

## Install

**HACS (recommended):** use the button above, or HACS, then ⋮, then Custom repositories, add `https://github.com/albert-canfield/smart_heating` as type *Integration*, install **Smart Heating** and restart Home Assistant.

**Manual:** copy `custom_components/smart_heating` into `/config/custom_components/` and restart.

Brand icon and logo ship in `brand/` (shown by Home Assistant 2026.3 and later).

The dashboard card ships inside the integration: it is served and loaded on every dashboard automatically, with no resource to add and no file in `www`. After an update, a normal browser refresh picks up the new card.

## Set up

Settings, Devices & services, Add integration, Smart Heating. A short wizard:

1. **What heats your home?**
2. **Your boiler**: the relay, switch or thermostat for heating, and optionally a boiler running sensor (skipped for electric).
3. **Your thermostat**: Setpoint or On / off (only if the boiler control is a thermostat).
4. **Hot water**: tank heating sensor and *Hot water first* (tank and hybrid only).
5. **Outside temperature**: your weather entity (enough on its own) and optionally a real outdoor thermometer and humidity sensor.
6. **Optional extras**: away detection, night schedule.
7. **Energy** (asked to match your heating type: gas for boilers, electricity for electric heaters, both for hybrid): with a smart meter integration (for example Octopus Energy or Glow), pick the consumption sensor (a running total in kWh, or m³ for gas; a total that restarts at midnight is fine) and optionally a unit rate sensor in £/kWh, and for electricity a live house power sensor (for example the Home Mini "current demand"). Without a smart meter, enter the boiler's gas input (for example 15 kW) or rely on the heaters' rated power, plus your unit price.
8. **Rooms**: areas with a thermometer, TRV or heater are pre-ticked and become rooms in one go. Pick **Start heating now** or **Watch first**.

Everything can be changed later: **Reconfigure** repeats the wizard; **Configure** has short pages for *Temperatures & Night*, *Energy Prices*, *Notifications*, *Import Rooms From Areas*, *Relearn Rooms* and *Advanced*.

**Setup checks** (Settings, Repairs): a hot water sensor that is really the boiler's own switch or running sensor (it is then ignored for hot water priority and the gas split; the wizard no longer accepts it), other automations that switch the heating while Smart Heating heats, and a boiler running sensor that doesn't turn on within 20 minutes of a heating call.

**Night period**: while the night schedule is on, the baseline drops to the night value (15°C) and comfort heat only goes to rooms with lights on or a manual "Heat now". Bedroom evening pre-heat comes from each room's own comfort schedule.

**Frost protection** is the safety floor (12°C default, adjustable down to 5°C). It is always on while Smart Heating is in control: in Off, on mild days and while away it still fires the boiler if any room drops below it. There is deliberately no switch to disable it. In Watch mode Smart Heating switches nothing at all, so frost protection then relies on your existing heating.

**Rooms come from your Home Assistant areas.** A room is an area: its name and floor come from Settings → Areas & floors and stay in sync when you rename or move things. Floor order uses each floor's level, or the floor name ("Ground Floor", "1st Floor") when no level is set.

- **Import rooms from areas** (Configure → Import rooms from areas): pre-selects every area with a temperature sensor or TRV (outdoor areas like gardens are skipped) and creates them all in one go. Tick *Re-detect thermometer* to refresh the sensors of rooms already added.
- **Add room**: pick one area; its entities are pre-filled.

For each area it picks up: the area's own temperature and humidity sensors (Settings → Areas → area → Temperature / Humidity sensor; recommended), otherwise the best candidate in the area. Candidates exclude diagnostic entities (device internal temperatures), TRV internal sensors, relays, plugs and appliances, and any reading outside 5–35°C; combined temperature + humidity devices and thermometer-like names are preferred. At runtime a room reading outside −10 to 40°C is ignored. Room details on the card show which thermometer is used; `climate` entities as TRVs; occupancy, presence and motion sensors; lights; media players. Priority and comfort are guessed from the name (hall/landing/utility C at 17°C; office/play room B at 18°C; bedrooms A at 18.5°C; others A at 19°C). Review any room with Reconfigure.

| Field | Notes |
|---|---|
| Priority | A living/sleeping, B occasional, C transit/service |
| Comfort temperature | target while the room is in use |
| Temperature sensor | pre-filled; optional if the room has TRVs |
| TRVs | pre-filled with the area's `climate` entities; empty = a radiator without a valve, always open while the boiler runs |
| Can switch the boiler on | on by default; off for an always-open radiator such as a bypass in the hall: it warms whenever another room calls, but never starts the boiler by itself (frost protection and Heat now still can) |
| Presence sensors, lights, media players | pre-filled from the area |
| Comfort schedule | optional, e.g. bedroom evenings |

Room devices created by Smart Heating are placed in their area, so they appear on the area's page.

**Configure** pages: *Temperatures & Night* (baseline day 17°C, night 15°C, night times, safety 12°C, season gate 15.5°C, override length), *Energy Prices* (gas unit price, boiler kW for estimates, electricity unit price), *Notifications* (see below), *Relearn Rooms* (clear what chosen rooms have learned, asked to confirm), *Advanced* (hysteresis, coasting, stack wait, mild-day margin 1.5°C, boiler min run/off, TRV setpoints, hot water pause). Pages only show what your heating type uses.

**Notifications** (Configure → Notifications): pick one or more **people**. Alerts go to the Home Assistant app on each person's phone, found from the person's device trackers. Learning finished and boiler problems go to everyone; window advice only to people at home at the time, so whoever is in gets it. **Other notify services** (a wall tablet, a Telegram chat) get every alert. **Window alerts** can be turned off here; there are never more than 8 a day and none at night, and a **Close windows** goes to the phones that got the alert to open, home or not. After an update from a version with a single notify service, window alerts start once you save this page.

## Entities

House device:
- `select.smart_heating_mode`: `off` / `one_cycle` / `auto` (shown as Off, One Cycle, Auto)
- service `smart_heating.one_cycle` (`all_rooms: true` heats every room below its target)
- `switch.smart_heating_controller_enabled`: kill switch (turns the boiler off)
- `switch.smart_heating_monitor_only`: on = decide and log only
- `number.smart_heating_house_target`: house target (shifts every room)
- services `smart_heating.heat_test` (start / stop), `smart_heating.start_control` (leave watch mode) and `smart_heating.relearn` (`rooms: ["Master Bedroom"]`)
- `sensor.smart_heating_status`: heating / idle / paused / waiting / off / away / fault / disabled (+ reason; from device states: `heating_rooms` (rooms really getting heat), `radiator_rooms` (a radiator while the boiler heats it: TRV open, or no TRV), `heater_rooms` (electric heaters that are on); from the plan: `wanted_rooms`, `calling_rooms`, `open_rooms` / `close_rooms` (valves being moved this minute); `boiler_called`, `boiler_hold_until` while boiler protection holds it back)
- `sensor.smart_heating_decision_log`: latest decision; last 50 entries in attributes (not stored in the database)
- `binary_sensor.smart_heating_boiler_demand`
- `sensor.smart_heating_house_temperature` (+ every room's reading)
- floor averages (only when rooms span more than one floor)
- `sensor.smart_heating_outdoor_day_mean`: observed last 12 h blended with forecast next 12 h. Attributes: `now`, `observed_mean_12h`, `forecast_mean_12h`, `forecast_mean_24h`, `forecast_min_12h`, `forecast_min_24h`, `forecast_points`
- `sensor.smart_heating_forecast_minimum_24h`
- `sensor.smart_heating_calibration` (% overall, per room in attributes), `binary_sensor.smart_heating_calibrated`
- `sensor.smart_heating_heating_hours_today`: hours today the heating was on (boiler heating rooms, or any electric heater), hot water left out
- `sensor.smart_heating_window_advice`: `open` / `close` / `none`. Attributes: `advice` (`dry`, `cool`, or for close `done`, `storm`, `warmer`, `cooled`, `away`, `hot`), `reason`, `rooms`, `minutes`, `until`, outdoor humidity and dew point, weather and wind (each room's humidity and dew point are in the diagnostics). For automations, for example a light by the door that turns blue on `open`
- `sensor.smart_heating_house_heat_loss_time_constant` (hours, median of rooms)
- `sensor.smart_heating_gas_today`: **heating** gas today (kWh), `sensor.smart_heating_gas_cost_today` its cost, `sensor.smart_heating_hot_water_gas_today`, and with a smart meter `sensor.smart_heating_other_gas_today` (hob and anything unassigned) and `sensor.smart_heating_house_gas_today` (the meter). Heating + hot water + other = the meter
- `sensor.smart_heating_electric_today`: **heating** electricity today, its cost, and with a smart meter `..._other_electricity_today` and `..._house_electricity_today`
- Costs are unit costs only: standing charges are left out because the heating can't change them. With a unit rate sensor, each kWh is costed at the rate when it was used
- All of these keep long-term statistics: tap them on the card for their history, find them in History, or add them to the Energy dashboard (gas consumption, and the cost as "an entity tracking the total costs")
- `sensor.smart_heating_boiler_runtime_today`, `sensor.smart_heating_boiler_burns_today`
- `sensor.smart_heating_gas_per_degree_day` (kWh per °C·day below the season gate: the weather-normalised efficiency figure)

Per room device: `target` (number), `need`, `decision` (with reason), `occupied`, `override` (Auto / Heat now / Off, expires after the override duration), plus the learned model:
- `heat_loss_time_constant` (h) with free-heat gain and sample counts
- `warm_up_rate` (°C/h with the radiator on)
- `predicted_in_2h` (°C with heating off, using the forecast), with `predicted_8h` and `hours_to_baseline`

## Insulation index

Once learned, every room, floor and the house get a **heat retention** score (0–100) and an EPC-style grade:

| Grade | Time constant | Meaning |
|---|---|---|
| A | 120 h or more | excellent |
| B | 80–120 h | very good |
| C | 55–80 h | good |
| D | 40–55 h | average |
| E | 28–40 h | below average |
| F | 18–28 h | poor |
| G | under 18 h | very poor |

The time constant is how long a room takes to lose about 63% of its warmth over outside with the heating off, learned in the background. Each sensor also shows `loss_per_hour_at_10c` (how fast it cools when it's 10°C colder outside), and the house sensor lists the `weakest_rooms`: good places to check windows, draughts or extractor fans.

It is comparative, not an official EPC: rooms also share heat with their neighbours, so upper floors and inner rooms rate better than their walls alone would.

Grades are only as good as the data, so each room says how sure it is. Until the result is steady, the room shows a range, for example **D-E (32-48 h), settling**, and its sensors carry `tau_low`, `tau_high`, `grade_range` and `settled`. The range is found by refitting with one group of days left out at a time, which is honest about days that differ (wind, sun, a busy kitchen) in a way a plain statistical error is not.

## Card

```yaml
type: custom:smart-heating-card
title: Smart Heating   # optional, default Smart Heating
icon: mdi:radiator     # optional, default the Smart Heating logo
hide_title: false      # optional
layout: compact        # compact (default): summary, tap to expand; full: large room tiles in a house section
```

All options are also in the card's visual editor. The title and icon share the top line with the status, so they cost no extra space.

Compact shows house temperature (always the house average), status with small indicators (flame = boiler burning, outline flame = boiler called, radiator = rooms heating, bolt = electric heaters on, drop = hot water heating, moon = night, crossed house = away, eye = watching only), floor averages (only when rooms span more than one floor) and the mode buttons (Off grey, One cycle amber, Auto orange when selected); the background tint follows the house temperature (blue when cold, through green and yellow, to orange when warm). Tap it to expand rooms (inside the house outline, by floor), the heating's energy and the log. The bottom shows only what the heating used today in kWh and pounds, with a flame for gas and a bolt for electricity (both for hybrid); the small (i) next to it opens the breakdown: heating rows with their hours count, hot water and the hob are shown greyed and aren't counted, with subtotals per fuel, plus the day's total heating cost for hybrid. A small person icon marks rooms in use (presence, media, or a light at night). When there is window advice, a small chip next to the status says **Open 10min** or **Close**; tap it for the reason. Tap a room for its panel: its temperature and state on top (a room with no reading says **No temperature**, one with nothing to heat it **Watched only**, a heater held off by a safety check **Heater stopped**, with the reason), and a scale with the frost, night, empty and in-use temperatures, the one that applies now lit up. Then its **Target when in use** with **Auto / Heat now / Off** under it. **Room profile** folds out why the room has the target it has, where it would be in 2 and 8 hours with the heating off, and small tiles for insulation, warm-up and free heat (plus the heater and its energy, or an always-open radiator, where there is one). **Show log** lists recent decisions.

## Logs and diagnostics

- **Card**: Show log (last 15 decisions) and room details.
- **Logbook**: every decision change, boiler on/off, mode, override, alarm and calibration event appears in Home Assistant's Logbook as "Smart Heating" (and in the history of the related devices).
- **Diagnostics**: integration page, three-dot menu, Download diagnostics. Full JSON of settings, every room's config, live values, decision and learned model (with its uncertainty and skipped samples), window advice with the humidity and dew points behind it, which phones alerts would reach, gas accounting and the last 200 log entries.
- **Debug logging**: `logger: logs: custom_components.smart_heating: debug`.

## Going live

1. Turn off your old heating automation, so only one thing switches the boiler (Repairs lists any that still do).
2. Add the house and all rooms. With **Start heating now** it takes over straight away; with **Watch first** it decides and logs while you compare with your current heating.
3. When watching, tap **Start heating** on the card and confirm. Learning carries on either way.

**Boiler protection** (applies to every command, including the heat test):
- The boiler is never switched again within 2 minutes of its last change, whoever made it.
- If something else switches the boiler (an automation, schedule, thermostat or hot water priority), Smart Heating backs off for 15 minutes instead of switching it back. During a heat test it stops the test and sends a notification.
- More than 6 switches in 30 minutes locks boiler switching for 30 minutes (off is still allowed) and sends a notification.
- Before a heat test, enabled automations that use the boiler control are listed; turn them off first.

Safety nets: all room sensors unavailable means boiler off; frost floor always applies, even in Off; a Shelly auto-off timer on the boiler switch is still recommended in case HA itself stops.

## Safety

Smart Heating switches real heating equipment. It protects the boiler from short cycling and always keeps a frost floor, but it is not a safety device: keep your boiler's own controls and a hardware timer or auto-off on the relay as a backstop. Use at your own risk (see the licence).

## Contributing

Issues and pull requests are welcome. Please attach diagnostics to bug reports (Settings, Devices & services, Smart Heating, three-dot menu, Download diagnostics).

## Tests

```
pip install pytest
pytest tests
```

The decision core (`core/`) has no Home Assistant imports and is fully unit tested, including the learner recovering a known time constant from simulated cooling. `tests/smoke_ha.py` and `tests/smoke_profiles.py` run the coordinator inside a real Home Assistant core with fake entities (full zoning with a switch, valve only, thermostat in on/off and setpoint style, hot water systems; `tests/smoke_electric.py` walks the setup wizard and runs an electric home with a smart plug and a smart heater; needs the `homeassistant` package). `tests/card_preview.html` renders the card with mock data in any browser.

## Roadmap

- Use the learned model in decisions: optimum start, defer when the room won't reach baseline before it's needed
- Weekly efficiency report
- Fault detection: radiator not delivering, open window by temperature drop
- Wind and heat from the floor below as terms in the learned model, once real data shows they help (sun was assessed and left out: small in a UK winter, and sunny spells are already filtered)
- Optional damp guard: keep very humid rooms a little warmer to prevent condensation

## Licence

MIT. See [LICENSE](LICENSE).
