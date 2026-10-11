"""Home Assistant version differences (needs the homeassistant package)."""
import sys
from pathlib import Path

import attr

sys.path.insert(0, str(Path(__file__).parents[1]))

from homeassistant.helpers import device_registry as dr  # noqa: E402

from custom_components.smart_heating.areas import _device_words  # noqa: E402


class _Child:
    """Like HA 2026.10's ChildDeviceEntry: a name; reading model or maker warns, and raises from 2027.9."""

    name = "Valve 2"

    def __getattr__(self, attr_name):
        raise AttributeError(attr_name)


def test_device_words():
    assert _device_words(None) == []
    owner = {"config_entry_id": "x"} if "config_entry_id" in attr.fields_dict(dr.DeviceEntry) else {}  # 2026.8+
    full = dr.DeviceEntry(name="Hall TRV", model="KE100", manufacturer="TP-Link", **owner)
    assert _device_words(full) == ["Hall TRV", "KE100", "TP-Link"]
    assert _device_words(_Child()) == ["Valve 2"], "child devices: name only, model and maker never read"
    if hasattr(dr, "ChildDeviceEntry"):  # HA 2026.10+
        child = dr.ChildDeviceEntry(config_entry_id="x", parent_device_id="p", name="Valve 3")
        assert _device_words(child) == ["Valve 3"]
