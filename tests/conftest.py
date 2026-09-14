"""Pytest bootstrap for pure Dummy OS Energy logic tests without Home Assistant."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]
CUSTOM_COMPONENTS = ROOT / "custom_components"
DUMMY_OS_DATA = CUSTOM_COMPONENTS / "dummy_os_data"

if "custom_components" not in sys.modules:
    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(CUSTOM_COMPONENTS)]
    sys.modules["custom_components"] = custom_components
if "custom_components.dummy_os_data" not in sys.modules:
    dummy_os_data = types.ModuleType("custom_components.dummy_os_data")
    dummy_os_data.__path__ = [str(DUMMY_OS_DATA)]
    sys.modules["custom_components.dummy_os_data"] = dummy_os_data

if "homeassistant" not in sys.modules:
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

# Minimal datetime compatibility for pure alpha76 calculations.
util = sys.modules.setdefault("homeassistant.util", types.ModuleType("homeassistant.util"))
util.__path__ = []
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
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    dt.parse_datetime = parse_datetime
    sys.modules["homeassistant.util.dt"] = dt
    util.dt = dt

# Small structural stubs needed to import the original scheduler/store/safety
# and execution modules. They intentionally implement no Home Assistant policy.
core = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
class HomeAssistant: pass
class State: pass
def callback(func): return func
core.HomeAssistant = HomeAssistant
core.State = State
core.callback = callback

exceptions = sys.modules.setdefault("homeassistant.exceptions", types.ModuleType("homeassistant.exceptions"))
class HomeAssistantError(Exception): pass
exceptions.HomeAssistantError = HomeAssistantError

helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
helpers.__path__ = []
storage = sys.modules.setdefault("homeassistant.helpers.storage", types.ModuleType("homeassistant.helpers.storage"))
class Store:
    def __class_getitem__(cls, item): return cls
    def __init__(self, *args, **kwargs): self.data = None
    async def async_load(self): return self.data
    async def async_save(self, data): self.data = data
storage.Store = Store


def _install_event_stub() -> None:
    """Keep the HA event import surface stable throughout pytest collection.

    Some legacy regression modules rebuild parts of the Home Assistant stub
    namespace while pytest imports the complete suite.  The alpha76 execution
    module imports ``async_call_later`` at module import time, so restore that
    minimal symbol before every test module is collected.  This changes only
    the pure-test harness; production integration code is untouched.
    """
    parent = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    parent.__path__ = getattr(parent, "__path__", [])
    event_module = sys.modules.get("homeassistant.helpers.event")
    if event_module is None:
        event_module = types.ModuleType("homeassistant.helpers.event")
        sys.modules["homeassistant.helpers.event"] = event_module

    def async_call_later(*args, **kwargs):
        return lambda: None

    event_module.async_call_later = async_call_later
    parent.event = event_module


_install_event_stub()


def pytest_collect_file(file_path, parent):
    """Reassert the event stub before pytest imports each test module."""
    _install_event_stub()


config_entries = sys.modules.setdefault("homeassistant.config_entries", types.ModuleType("homeassistant.config_entries"))
class ConfigEntry: pass
config_entries.ConfigEntry = ConfigEntry

update_coord = sys.modules.setdefault("homeassistant.helpers.update_coordinator", types.ModuleType("homeassistant.helpers.update_coordinator"))
class DataUpdateCoordinator:
    def __class_getitem__(cls, item): return cls
    def __init__(self, *args, **kwargs): self.data = {}
class CoordinatorEntity:
    def __class_getitem__(cls, item): return cls
update_coord.DataUpdateCoordinator = DataUpdateCoordinator
update_coord.CoordinatorEntity = CoordinatorEntity

# aiohttp helpers imported by the original coordinator are never used by parity
# unit tests, but the import surface must remain intact.
aiohttp_client = sys.modules.setdefault("homeassistant.helpers.aiohttp_client", types.ModuleType("homeassistant.helpers.aiohttp_client"))
def async_get_clientsession(*args, **kwargs): return None
aiohttp_client.async_get_clientsession = async_get_clientsession
