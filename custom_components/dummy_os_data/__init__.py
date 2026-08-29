"""Dummy OS Data integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import DummyOSHomeDataCoordinator
from .degree_days import DummyOSDegreeDaysCoordinator
from .entity_migrations import is_known_generated_entity_id
from .prices import DummyOSPricesCoordinator
from .solar import DummyOSSolarCoordinator

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
    ("sensor", "do_prices_status", "sensor.do_prices_status"),
    ("sensor", "do_prices_market_current", "sensor.do_prices_market_current"),
    ("sensor", "do_prices_import_current", "sensor.do_prices_import_current"),
    ("sensor", "do_prices_export_current", "sensor.do_prices_export_current"),
    ("sensor", "do_prices_timeline", "sensor.do_prices_timeline"),
    ("sensor", "do_prices_tariff_profile", "sensor.do_prices_tariff_profile"),
    ("sensor", "do_prices_gas_market", "sensor.do_prices_gas_market"),
    ("sensor", "do_prices_gas_all_in", "sensor.do_prices_gas_all_in"),
    ("sensor", "do_solar_status", "sensor.do_solar_status"),
    ("sensor", "do_solar_forecast_timeline", "sensor.do_solar_forecast_timeline"),
    ("sensor", "do_solar_forecast_today_north", "sensor.do_solar_forecast_today_north"),
    ("sensor", "do_solar_forecast_today_south", "sensor.do_solar_forecast_today_south"),
    ("sensor", "do_solar_forecast_today_total", "sensor.do_solar_forecast_today_total"),
    ("sensor", "do_solar_forecast_tomorrow_north", "sensor.do_solar_forecast_tomorrow_north"),
    ("sensor", "do_solar_forecast_tomorrow_south", "sensor.do_solar_forecast_tomorrow_south"),
    ("sensor", "do_solar_forecast_tomorrow_total", "sensor.do_solar_forecast_tomorrow_total"),
    ("sensor", "do_solar_forecast_next_quarter", "sensor.do_solar_forecast_next_quarter"),
    ("sensor", "do_solar_actual_power_north", "sensor.do_solar_actual_power_north"),
    ("sensor", "do_solar_actual_power_south", "sensor.do_solar_actual_power_south"),
    ("sensor", "do_solar_actual_power_total", "sensor.do_solar_actual_power_total"),
    ("sensor", "do_solar_model", "sensor.do_solar_model"),
    ("select", "do_home_profile", "select.do_home_profile"),
)


async def async_setup_entry(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> bool:
    """Set up Dummy OS Data from a config entry."""
    coordinator = DummyOSHomeDataCoordinator(hass, entry)
    await coordinator.async_setup()

    coordinator.degree_days = DummyOSDegreeDaysCoordinator(hass, coordinator.weather)
    await coordinator.degree_days.async_setup()

    coordinator.prices = DummyOSPricesCoordinator(hass, entry)
    await coordinator.prices.async_setup()

    coordinator.solar = DummyOSSolarCoordinator(hass, entry)
    await coordinator.solar.async_setup()

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

        if not is_known_generated_entity_id(platform, unique_id, current_entity_id):
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
        solar = getattr(entry.runtime_data, "solar", None)
        if solar is not None:
            await solar.async_shutdown()
        prices = getattr(entry.runtime_data, "prices", None)
        if prices is not None:
            await prices.async_shutdown()
        degree_days = getattr(entry.runtime_data, "degree_days", None)
        if degree_days is not None:
            await degree_days.async_shutdown()
        await entry.runtime_data.async_shutdown()
    return unload_ok
