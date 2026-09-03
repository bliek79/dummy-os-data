"""Select entities for Dummy OS Forecast."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, NAME, PROFILE_OPTIONS, VERSION
from .coordinator import DummyOSHomeDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: DummyOSHomeDataCoordinator = entry.runtime_data
    async_add_entities([DummyOSEnergyProfileSelect(coordinator)])


class DummyOSEnergyProfileSelect(SelectEntity):
    """Select the active Energy Forecast historical profile."""

    _attr_name = "DO Energy Profile"
    _attr_unique_id = "do_energy_profile"
    _attr_suggested_object_id = "do_energy_profile"
    _attr_options = PROFILE_OPTIONS
    _attr_icon = "mdi:home-account"
    _attr_should_poll = False

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        self.coordinator = coordinator
        self._remove_listener = None

    @property
    def current_option(self) -> str:
        return self.coordinator.profile

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "main")},
            name=NAME,
            manufacturer="Dummy OS",
            model="Forecast Platform",
            sw_version=VERSION,
        )

    async def async_select_option(self, option: str) -> None:
        if option not in PROFILE_OPTIONS:
            raise ValueError(f"Unsupported profile: {option}")
        await self.coordinator.async_set_profile(option)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_listener = self.coordinator.async_add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
