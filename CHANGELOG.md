# Changelog

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
