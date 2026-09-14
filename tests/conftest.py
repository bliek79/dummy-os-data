"""Pytest bootstrap for pure Dummy OS Energy logic tests without Home Assistant."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]
CUSTOM_COMPONENTS = ROOT / "custom_components"
DUMMY_OS_DATA = CUSTOM_COMPONENTS / "dummy_os_data"

# Pure logic modules are imported without executing the HA integration package.
if "custom_components" not in sys.modules:
    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(CUSTOM_COMPONENTS)]
    sys.modules["custom_components"] = custom_components

if "custom_components.dummy_os_data" not in sys.modules:
    dummy_os_data = types.ModuleType("custom_components.dummy_os_data")
    dummy_os_data.__path__ = [str(DUMMY_OS_DATA)]
    sys.modules["custom_components.dummy_os_data"] = dummy_os_data

# The vendored alpha76 decision modules depend only on homeassistant.util.dt.
# CI deliberately does not install Home Assistant, so provide the minimal,
# behavior-compatible UTC helpers needed by those pure calculations.
if "homeassistant" not in sys.modules:
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

if "homeassistant.util" not in sys.modules:
    util = types.ModuleType("homeassistant.util")
    util.__path__ = []
    sys.modules["homeassistant.util"] = util
else:
    util = sys.modules["homeassistant.util"]

if "homeassistant.util.dt" not in sys.modules:
    dt = types.ModuleType("homeassistant.util.dt")
    dt.UTC = timezone.utc
    dt.DEFAULT_TIME_ZONE = timezone.utc
    dt.utcnow = lambda: datetime.now(timezone.utc)
    dt.now = lambda: datetime.now(timezone.utc)
    dt.as_local = lambda value: value

    def parse_datetime(value):
        if value in (None, ""):
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return parsed

    dt.parse_datetime = parse_datetime
    sys.modules["homeassistant.util.dt"] = dt
    util.dt = dt
