"""Away detection from whatever the house has."""
from __future__ import annotations

ALARM_AWAY = {"armed_away", "armed_vacation"}
TRUE_STATES = {"on", "true", "away"}


def is_away(states: list[tuple[str, str]]) -> tuple[bool, str]:
    """Decide away from (domain, state) pairs.

    - alarm_control_panel: armed away or vacation -> away (any panel is enough)
    - input_boolean / switch / binary_sensor: on -> away (any is enough)
    - person / device_tracker: away only if every one is not home
    - zone (zone.home): away if nobody is in it ("0")
    - group of people: "not_home" -> away
    Returns (away, reason).
    """
    people: list[bool] = []
    for domain, state in states:
        if state in ("unknown", "unavailable", "", None):
            continue
        if domain == "alarm_control_panel":
            if state in ALARM_AWAY:
                return True, f"alarm {state.replace('_', ' ')}"
        elif domain in ("input_boolean", "switch", "binary_sensor"):
            if state.lower() in TRUE_STATES:
                return True, "away switch on"
        elif domain in ("person", "device_tracker"):
            people.append(state != "home")
        elif domain == "zone":
            try:
                people.append(int(float(state)) == 0)
            except ValueError:
                pass
        elif domain == "group":
            if state in ("home", "not_home"):
                people.append(state == "not_home")
    if people and all(people):
        return True, "everyone away"
    return False, ""
