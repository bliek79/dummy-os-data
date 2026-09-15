"""Binary sensors for Dummy OS Energy."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DummyOSHomeDataCoordinator
from .ems_alpha76_surface import build_alpha76_binary_sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Expose observer-only binary state from the exact alpha76 runtime."""
    coordinator: DummyOSHomeDataCoordinator = entry.runtime_data
    async_add_entities(build_alpha76_binary_sensors(coordinator))
