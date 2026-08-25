"""Dummy OS Data integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import DummyOSHomeDataCoordinator


type DummyOSDataConfigEntry = ConfigEntry[DummyOSHomeDataCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> bool:
    """Set up Dummy OS Data from a config entry."""
    coordinator = DummyOSHomeDataCoordinator(hass, entry)
    await coordinator.async_setup()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
