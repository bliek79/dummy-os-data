"""Dummy OS Forecast integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, NAME, PLATFORMS
from .coordinator import DummyOSHomeDataCoordinator
from .degree_days import DummyOSDegreeDaysCoordinator
from .entity_migrations import (
    OBSOLETE_HOME_INPUT_ENTITY_ALIASES,
    is_known_generated_entity_id,
)
from .prices import DummyOSPricesCoordinator
from .solar import DummyOSSolarCoordinator

_LOGGER = logging.getLogger(__name__)


type DummyOSDataConfigEntry = ConfigEntry[DummyOSHomeDataCoordinator]

# Alpha.12 changes the public identity namespace while keeping the technical
# integration domain stable. Existing registry rows are migrated in-place so
# Home Assistant does not create duplicate entities with the new unique IDs.
_IDENTITY_MIGRATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("sensor", "do_data_grid_net_power", "do_source_grid_net_power", "sensor.do_source_grid_net_power"),
    ("sensor", "do_data_grid_import_power", "do_source_grid_import_power", "sensor.do_source_grid_import_power"),
    ("sensor", "do_data_grid_export_power", "do_source_grid_export_power", "sensor.do_source_grid_export_power"),
    ("sensor", "do_data_solar_power", "do_source_solar_power", "sensor.do_source_solar_power"),
    ("sensor", "do_data_battery_charge_power", "do_source_battery_charge_power", "sensor.do_source_battery_charge_power"),
    ("sensor", "do_data_battery_discharge_power", "do_source_battery_discharge_power", "sensor.do_source_battery_discharge_power"),
    ("sensor", "do_data_home_power", "do_source_home_power", "sensor.do_source_home_power"),
    ("sensor", "do_home_actual_quarter", "do_energy_actual_quarter", "sensor.do_energy_actual_quarter"),
    ("sensor", "do_home_history_status", "do_energy_history_status", "sensor.do_energy_history_status"),
    ("sensor", "do_home_history_days", "do_energy_history_days", "sensor.do_energy_history_days"),
    ("sensor", "do_home_forecast_model", "do_energy_forecast_model", "sensor.do_energy_forecast_model"),
    ("sensor", "do_home_forecast", "do_energy_forecast", "sensor.do_energy_forecast"),
    ("sensor", "do_home_forecast_timeline", "do_energy_forecast_timeline", "sensor.do_energy_forecast_timeline"),
    ("sensor", "do_home_forecast_next_quarter", "do_energy_forecast_next_quarter", "sensor.do_energy_forecast_next_quarter"),
    ("sensor", "do_home_forecast_coverage", "do_energy_forecast_coverage", "sensor.do_energy_forecast_coverage"),
    ("sensor", "do_home_forecast_confidence", "do_energy_forecast_confidence", "sensor.do_energy_forecast_confidence"),
    ("sensor", "do_home_forecast_model_health", "do_energy_forecast_model_health", "sensor.do_energy_forecast_model_health"),
    ("sensor", "do_home_forecast_accuracy", "do_energy_forecast_accuracy", "sensor.do_energy_forecast_accuracy"),
    ("sensor", "do_home_forecast_mae", "do_energy_forecast_mae", "sensor.do_energy_forecast_mae"),
    ("sensor", "do_home_forecast_bias", "do_energy_forecast_bias", "sensor.do_energy_forecast_bias"),
    ("sensor", "do_home_forecast_evaluation_samples", "do_energy_forecast_evaluation_samples", "sensor.do_energy_forecast_evaluation_samples"),
    ("select", "do_home_profile", "do_energy_profile", "select.do_energy_profile"),
)

# Stable namespaces still keep deterministic canonical entity IDs for older
# automatically generated aliases from previous alphas.
_ENTITY_ID_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
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
    ("sensor", "do_solar_evaluation_last_completed_quarter", "sensor.do_solar_evaluation_last_completed_quarter"),
    ("sensor", "do_solar_model", "sensor.do_solar_model"),
)


def _is_obsolete_home_input_state(state: State | None) -> bool:
    """Return whether a state has the exact temporary alpha.11.4 signature."""
    if state is None:
        return False
    attrs = state.attributes
    return (
        attrs.get("canonical_sign") == "positive_consumption_negative_export"
        and isinstance(attrs.get("source_entity"), str)
        and "source_available" in attrs
    )


async def async_setup_entry(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> bool:
    """Set up Dummy OS Forecast from a config entry."""
    _async_remove_obsolete_home_input_entities(hass)
    _async_migrate_alpha12_identities(hass)
    _async_migrate_generated_entity_ids(hass)

    if entry.title in {"Dummy OS", "Dummy OS Data"} and entry.title != NAME:
        hass.config_entries.async_update_entry(entry, title=NAME)

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
    _async_remove_obsolete_home_input_entities(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_remove_obsolete_home_input_entities(hass: HomeAssistant) -> None:
    """Remove known automatic alpha.11.4 entities and their stale HA states."""
    registry = er.async_get(hass)

    for unique_id, aliases in OBSOLETE_HOME_INPUT_ENTITY_ALIASES.items():
        registered_entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)

        if registered_entity_id is not None:
            if is_known_generated_entity_id("sensor", unique_id, registered_entity_id):
                registry.async_remove(registered_entity_id)
                hass.states.async_remove(registered_entity_id)
                _LOGGER.info(
                    "Removed obsolete Home input entity and state %s",
                    registered_entity_id,
                )
            else:
                _LOGGER.warning(
                    "Preserving user-renamed obsolete Home input entity %s",
                    registered_entity_id,
                )

        for alias_entity_id in aliases:
            if alias_entity_id == registered_entity_id:
                continue
            if registry.async_get(alias_entity_id) is not None:
                continue
            state = hass.states.get(alias_entity_id)
            if not _is_obsolete_home_input_state(state):
                continue
            hass.states.async_remove(alias_entity_id)
            _LOGGER.info("Removed stale obsolete Home input state %s", alias_entity_id)


def _async_migrate_alpha12_identities(hass: HomeAssistant) -> None:
    """Rename known registry identities from Data/Home to Source/Energy."""
    registry = er.async_get(hass)

    for platform, old_unique_id, new_unique_id, target_entity_id in _IDENTITY_MIGRATIONS:
        current_entity_id = registry.async_get_entity_id(platform, DOMAIN, old_unique_id)
        if current_entity_id is None:
            continue

        automatically_named = current_entity_id == f"{platform}.{old_unique_id}"
        if not automatically_named and not is_known_generated_entity_id(
            platform, old_unique_id, current_entity_id
        ):
            _LOGGER.warning(
                "Preserving user-renamed entity %s while alpha.12 changes unique ID %s",
                current_entity_id,
                old_unique_id,
            )
            continue

        existing_target = registry.async_get(target_entity_id)
        if existing_target is not None and target_entity_id != current_entity_id:
            _LOGGER.warning(
                "Cannot migrate %s to %s because the target entity ID already exists",
                current_entity_id,
                target_entity_id,
            )
            continue

        registry.async_update_entity(
            current_entity_id,
            new_entity_id=target_entity_id,
            new_unique_id=new_unique_id,
        )
        if current_entity_id != target_entity_id:
            hass.states.async_remove(current_entity_id)
        _LOGGER.info(
            "Migrated Dummy OS Forecast identity %s/%s to %s/%s",
            current_entity_id,
            old_unique_id,
            target_entity_id,
            new_unique_id,
        )


def _async_migrate_generated_entity_ids(hass: HomeAssistant) -> None:
    """Migrate known automatically generated stable-namespace entity IDs."""
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
