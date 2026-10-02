# Changelog

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
