"""Dummy OS Data integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import DummyOSHomeDataCoordinator

_LOGGER = logging.getLogger(__name__)


type DummyOSDataConfigEntry = ConfigEntry[DummyOSHomeDataCoordinator]

_ENTITY_ID_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("sensor", "do_home_actual_quarter", "sensor.do_home_actual_quarter"),
    ("sensor", "do_home_history_status", "sensor.do_home_history_status"),
    ("sensor", "do_home_history_days", "sensor.do_home_history_days"),
    ("sensor", "do_home_forecast_model", "sensor.do_home_forecast_model"),
    ("sensor", "do_home_forecast", "sensor.do_home_forecast"),
    ("sensor", "do_home_forecast_timeline", "sensor.do_home_forecast_timeline"),
    ("sensor", "do_home_forecast_next_quarter", "sensor.do_home_forecast_next_quarter"),
    ("sensor", "do_home_forecast_coverage", "sensor.do_home_forecast_coverage"),
    ("sensor", "do_home_forecast_confidence", "sensor.do_home_forecast_confidence"),
    ("sensor", "do_home_forecast_model_health", "sensor.do_home_forecast_model_health"),
    ("sensor", "do_home_forecast_accuracy", "sensor.do_home_forecast_accuracy"),
    ("sensor", "do_home_forecast_mae", "sensor.do_home_forecast_mae"),
    ("sensor", "do_home_forecast_bias", "sensor.do_home_forecast_bias"),
    ("sensor", "do_home_forecast_evaluation_samples", "sensor.do_home_forecast_evaluation_samples"),
    ("sensor", "do_weather_temperature", "sensor.do_weather_temperature"),
    ("sensor", "do_weather_apparent_temperature", "sensor.do_weather_apparent_temperature"),
    ("sensor", "do_weather_relative_humidity", "sensor.do_weather_relative_humidity"),
    ("sensor", "do_weather_precipitation", "sensor.do_weather_precipitation"),
    ("sensor", "do_weather_cloud_cover", "sensor.do_weather_cloud_cover"),
    ("sensor", "do_weather_wind_speed", "sensor.do_weather_wind_speed"),
    ("sensor", "do_weather_wind_direction", "sensor.do_weather_wind_direction"),
    ("sensor", "do_weather_wind_gusts", "sensor.do_weather_wind_gusts"),
    ("sensor", "do_weather_weather_code", "sensor.do_weather_weather_code"),
    ("sensor", "do_weather_forecast_timeline", "sensor.do_weather_forecast_timeline"),
    ("sensor", "do_weather_source_status", "sensor.do_weather_source_status"),
    ("sensor", "do_weather_source_freshness", "sensor.do_weather_source_freshness"),
    ("sensor", "do_weather_last_update", "sensor.do_weather_last_update"),
    ("sensor", "do_weather_model", "sensor.do_weather_model"),
    ("select", "do_home_profile", "select.do_home_profile"),
)


def _apply_entity_name_policy() -> None:
    """Apply HA-native entity naming without duplicated Dummy OS prefixes.

    The integration remains named "Dummy OS Data", while its single device is
    presented as "Dummy OS". Entity names are relative to that device and use
    ``has_entity_name=True`` as required by current Home Assistant naming
    conventions. Entity IDs and unique IDs are deliberately unaffected.
    """
    from . import select as select_platform
    from . import sensor as sensor_platform
    from .select import DummyOSHomeProfileSelect
    from .sensor import DummyOSBaseSensor, DummyOSWeatherBaseSensor, DummyOSWeatherCurrentSensor

    # Device name used by DeviceInfo in the platform modules. The integration
    # itself remains "Dummy OS Data" through manifest.json.
    sensor_platform.NAME = "Dummy OS"
    select_platform.NAME = "Dummy OS"

    def _make_relative(entity_class: type) -> None:
        name = getattr(entity_class, "_attr_name", None)
        if isinstance(name, str) and name.startswith("Dummy OS "):
            entity_class._attr_name = name.removeprefix("Dummy OS ")
        entity_class._attr_has_entity_name = True

    for entity_class in DummyOSBaseSensor.__subclasses__():
        _make_relative(entity_class)
    for entity_class in DummyOSWeatherBaseSensor.__subclasses__():
        _make_relative(entity_class)
    _make_relative(DummyOSHomeProfileSelect)

    # Weather current sensors receive their name per instance in __init__, so
    # normalize that generated name there as well. Guard against double wrapping
    # when a config entry is reloaded.
    if not getattr(DummyOSWeatherCurrentSensor, "_dummy_os_name_policy_wrapped", False):
        original_init = DummyOSWeatherCurrentSensor.__init__

        def _weather_current_init(self, *args, **kwargs) -> None:
            original_init(self, *args, **kwargs)
            if isinstance(self._attr_name, str) and self._attr_name.startswith("Dummy OS "):
                self._attr_name = self._attr_name.removeprefix("Dummy OS ")
            self._attr_has_entity_name = True

        DummyOSWeatherCurrentSensor.__init__ = _weather_current_init
        DummyOSWeatherCurrentSensor._dummy_os_name_policy_wrapped = True


async def async_setup_entry(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> bool:
    """Set up Dummy OS Data from a config entry."""
    _apply_entity_name_policy()

    coordinator = DummyOSHomeDataCoordinator(hass, entry)
    await coordinator.async_setup()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_migrate_generated_entity_ids(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_migrate_generated_entity_ids(hass: HomeAssistant) -> None:
    """Migrate only known automatically generated Dummy OS Data entity IDs."""
    registry = er.async_get(hass)

    for platform, unique_id, target_entity_id in _ENTITY_ID_MIGRATIONS:
        current_entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
        if current_entity_id is None or current_entity_id == target_entity_id:
            continue

        known_generated_prefix = f"{platform}.dummy_os_data_dummy_os_"
        if not current_entity_id.startswith(known_generated_prefix):
            continue

        if registry.async_get(target_entity_id) is not None:
            _LOGGER.warning(
                "Cannot migrate %s to %s because the target entity ID already exists",
                current_entity_id,
                target_entity_id,
            )
            continue

        registry.async_update_entity(current_entity_id, new_entity_id=target_entity_id)
        _LOGGER.info("Migrated entity ID %s to %s", current_entity_id, target_entity_id)


async def _async_update_listener(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
