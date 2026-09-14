"""Dummy OS Forecast integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, NAME, PLATFORMS
from .coordinator import DummyOSHomeDataCoordinator
from .degree_days import DummyOSDegreeDaysCoordinator
from .ems_alpha76_runtime import async_setup_ems_alpha76_runtime, get_ems_alpha76_runtime
from .entity_migrations import (
    OBSOLETE_HOME_INPUT_ENTITY_ALIASES,
    is_known_generated_entity_id,
)
from .prices import DummyOSPricesCoordinator
from .solar import DummyOSSolarCoordinator

_LOGGER = logging.getLogger(__name__)


type DummyOSDataConfigEntry = ConfigEntry[DummyOSHomeDataCoordinator]

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
    ("sensor", "dummy_os_data_energy_peak_learning", "do_energy_peak_learning", "sensor.do_energy_peak_learning"),
    ("select", "do_home_profile", "do_energy_profile", "select.do_energy_profile"),
)

_DEGREE_DAYS_RUNTIME_STATE_ALIASES: tuple[str, ...] = (
    "sensor.do_degree_days_status", "sensor.do_degree_days_history_days",
    "sensor.do_degree_days_temperature_daily", "sensor.do_degree_days_daily",
    "sensor.do_weighted_degree_days_daily", "sensor.do_degree_days_reference_daily",
    "sensor.do_weighted_degree_days_reference_daily", "sensor.do_degree_days_difference",
    "sensor.do_weighted_degree_days_difference", "sensor.do_heat_degree_days_last_day",
    "sensor.dummy_os_forecast_do_degree_days_status",
    "sensor.dummy_os_forecast_do_degree_days_history_days",
    "sensor.dummy_os_forecast_do_degree_days_temperature_daily",
    "sensor.dummy_os_forecast_do_degree_days_daily",
    "sensor.dummy_os_forecast_do_degree_days_weighted_daily",
    "sensor.dummy_os_forecast_do_degree_days_reference_daily",
    "sensor.dummy_os_forecast_do_degree_days_weighted_reference_daily",
    "sensor.dummy_os_forecast_do_degree_days_difference",
    "sensor.dummy_os_forecast_do_degree_days_weighted_difference",
    "sensor.dummy_os_forecast_do_degree_days_last_day",
)

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
    ("sensor", "do_solar_evaluation_horizon_1h", "sensor.do_solar_evaluation_horizon_1h"),
    ("sensor", "do_solar_evaluation_horizon_6h", "sensor.do_solar_evaluation_horizon_6h"),
    ("sensor", "do_solar_evaluation_horizon_24h", "sensor.do_solar_evaluation_horizon_24h"),
    ("sensor", "do_solar_evaluation_horizon_48h", "sensor.do_solar_evaluation_horizon_48h"),
    ("sensor", "do_solar_evaluation_horizon_72h", "sensor.do_solar_evaluation_horizon_72h"),
    ("sensor", "do_solar_model", "sensor.do_solar_model"),
    ("sensor", "do_energy_forecast_quality_by_daypart", "sensor.do_energy_forecast_quality_by_daypart"),
    ("sensor", "do_energy_forecast_quality_by_day_type", "sensor.do_energy_forecast_quality_by_day_type"),
    ("sensor", "do_energy_forecast_quality_by_day_type_and_daypart", "sensor.do_energy_forecast_quality_by_day_type_and_daypart"),
    ("sensor", "do_energy_forecast_quality_by_hour", "sensor.do_energy_forecast_quality_by_hour"),
    ("sensor", "do_energy_peak_learning", "sensor.do_energy_peak_learning"),
    ("sensor", "do_energy_time_windows", "sensor.do_energy_time_windows"),
    ("sensor", "do_energy_recency_weighting", "sensor.do_energy_recency_weighting"),
    ("sensor", "do_energy_fallback_hierarchy", "sensor.do_energy_fallback_hierarchy"),
    ("sensor", "do_energy_meaningful_confidence", "sensor.do_energy_meaningful_confidence"),
    ("sensor", "do_energy_forecast_quality_by_horizon", "sensor.do_energy_forecast_quality_by_horizon"),
    ("sensor", "do_energy_forecast_planner_hours", "sensor.do_energy_forecast_planner_hours"),
    ("sensor", "do_energy_forecast_planner_contract", "sensor.do_energy_forecast_planner_contract"),
    ("sensor", "do_plan_input_72h", "sensor.do_plan_input_72h"),
    ("sensor", "do_degree_days_status", "sensor.do_degree_days_status"),
    ("sensor", "do_degree_days_history_days", "sensor.do_degree_days_history_days"),
    ("sensor", "do_degree_days_temperature_daily", "sensor.do_degree_days_temperature_daily"),
    ("sensor", "do_degree_days_daily", "sensor.do_degree_days_daily"),
    ("sensor", "do_degree_days_weighted_daily", "sensor.do_degree_days_weighted_daily"),
    ("sensor", "do_degree_days_reference_daily", "sensor.do_degree_days_reference_daily"),
    ("sensor", "do_degree_days_weighted_reference_daily", "sensor.do_degree_days_weighted_reference_daily"),
    ("sensor", "do_degree_days_difference", "sensor.do_degree_days_difference"),
    ("sensor", "do_degree_days_weighted_difference", "sensor.do_degree_days_weighted_difference"),
    ("sensor", "do_degree_days_last_day", "sensor.do_degree_days_last_day"),
)


async def _async_noop() -> None:
    pass


async def _async_setup_cloud_sources(coordinator: DummyOSHomeDataCoordinator, weather_setup) -> None:
    results = await asyncio.gather(
        weather_setup(), coordinator.prices.async_setup(), coordinator.solar.async_setup(),
        return_exceptions=True,
    )
    for source_name, result in zip(("weather", "prices", "solar"), results, strict=True):
        if isinstance(result, BaseException):
            _LOGGER.warning("Dummy OS Data %s startup failed in background: %s", source_name, result)
    try:
        await coordinator.degree_days.async_setup()
    except Exception as err:
        _LOGGER.warning("Dummy OS Data degree-days startup failed in background: %s", err)
    coordinator._notify()


def _is_obsolete_home_input_state(state: State | None) -> bool:
    if state is None:
        return False
    attrs = state.attributes
    return (
        attrs.get("canonical_sign") == "positive_consumption_negative_export"
        and isinstance(attrs.get("source_entity"), str)
        and "source_available" in attrs
    )


async def async_setup_entry(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> bool:
    _async_remove_obsolete_home_input_entities(hass)
    _async_migrate_alpha12_identities(hass)
    _async_remove_degree_days_runtime_states(hass)
    _async_migrate_generated_entity_ids(hass)

    if entry.title in {"Dummy OS", "Dummy OS Data"} and entry.title != NAME:
        hass.config_entries.async_update_entry(entry, title=NAME)

    coordinator = DummyOSHomeDataCoordinator(hass, entry)
    weather_setup = coordinator.weather.async_setup
    coordinator.weather.async_setup = _async_noop
    try:
        await coordinator.async_setup()
    finally:
        coordinator.weather.async_setup = weather_setup

    coordinator.degree_days = DummyOSDegreeDaysCoordinator(hass, coordinator.weather)
    coordinator.prices = DummyOSPricesCoordinator(hass, entry)
    coordinator.solar = DummyOSSolarCoordinator(hass, entry)
    entry.runtime_data = coordinator

    # Build the copied alpha76 EMS behind the new forecast layer before platform
    # setup. It is shadow-only: original planning/gating is active, but no
    # automatic execution listener or old physical services are registered.
    ems_runtime = await async_setup_ems_alpha76_runtime(hass, entry, coordinator)
    entry.async_on_unload(lambda: hass.async_create_task(ems_runtime.async_shutdown_shadow()))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    source_setup_task = hass.async_create_task(_async_setup_cloud_sources(coordinator, weather_setup))
    coordinator._source_setup_task = source_setup_task
    entry.async_on_unload(source_setup_task.cancel)

    _async_remove_degree_days_runtime_states(hass)
    _async_migrate_generated_entity_ids(hass)
    _async_remove_obsolete_home_input_entities(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_remove_obsolete_home_input_entities(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    for unique_id, aliases in OBSOLETE_HOME_INPUT_ENTITY_ALIASES.items():
        registered_entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if registered_entity_id is not None:
            if is_known_generated_entity_id("sensor", unique_id, registered_entity_id):
                registry.async_remove(registered_entity_id)
                hass.states.async_remove(registered_entity_id)
                _LOGGER.info("Removed obsolete Home input entity and state %s", registered_entity_id)
            else:
                _LOGGER.warning("Preserving user-renamed obsolete Home input entity %s", registered_entity_id)
        for alias_entity_id in aliases:
            if alias_entity_id == registered_entity_id or registry.async_get(alias_entity_id) is not None:
                continue
            state = hass.states.get(alias_entity_id)
            if not _is_obsolete_home_input_state(state):
                continue
            hass.states.async_remove(alias_entity_id)
            _LOGGER.info("Removed stale obsolete Home input state %s", alias_entity_id)


def _async_remove_degree_days_runtime_states(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    for entity_id in _DEGREE_DAYS_RUNTIME_STATE_ALIASES:
        if registry.async_get(entity_id) is not None or hass.states.get(entity_id) is None:
            continue
        hass.states.async_remove(entity_id)
        _LOGGER.info("Removed legacy Degree Days runtime state %s", entity_id)


def _async_migrate_alpha12_identities(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    for platform, old_unique_id, new_unique_id, target_entity_id in _IDENTITY_MIGRATIONS:
        old_entity_id = registry.async_get_entity_id(platform, DOMAIN, old_unique_id)
        new_entity_id = registry.async_get_entity_id(platform, DOMAIN, new_unique_id)
        if old_entity_id is None:
            continue
        if new_entity_id is not None and new_entity_id != old_entity_id:
            continue
        changes: dict[str, str] = {}
        if new_entity_id is None:
            changes["new_unique_id"] = new_unique_id
        if old_entity_id != target_entity_id and registry.async_get(target_entity_id) is None:
            changes["new_entity_id"] = target_entity_id
        if changes:
            registry.async_update_entity(old_entity_id, **changes)


def _async_migrate_generated_entity_ids(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    for platform, unique_id, target_entity_id in _ENTITY_ID_MIGRATIONS:
        current_entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
        if current_entity_id is None or current_entity_id == target_entity_id:
            continue
        if registry.async_get(target_entity_id) is not None:
            continue
        registry.async_update_entity(current_entity_id, new_entity_id=target_entity_id)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DummyOSDataConfigEntry) -> bool:
    coordinator = entry.runtime_data
    runtime = get_ems_alpha76_runtime(coordinator)
    if runtime is not None:
        await runtime.async_shutdown_shadow()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN)
        if isinstance(domain_data, dict):
            domain_data.pop(entry.entry_id, None)
    return unload_ok
