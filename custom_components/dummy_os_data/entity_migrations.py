"""Known Home Assistant entity-ID aliases that require deterministic migration."""

from __future__ import annotations


# These are the entity IDs that Home Assistant actually generated on a clean
# 0.1.0-alpha.11.0 installation. Keep this mapping explicit: release validation
# must never infer a generated entity ID from a guessed prefix.
SOLAR_GENERATED_ENTITY_ID_ALIASES: dict[str, str] = {
    "do_solar_status": "sensor.dummy_os_solar_source_status",
    "do_solar_forecast_timeline": "sensor.dummy_os_solar_forecast_timeline",
    "do_solar_forecast_today_north": "sensor.dummy_os_solar_forecast_today_north",
    "do_solar_forecast_today_south": "sensor.dummy_os_solar_forecast_today_south",
    "do_solar_forecast_today_total": "sensor.dummy_os_solar_forecast_today_total",
    "do_solar_forecast_tomorrow_north": "sensor.dummy_os_solar_forecast_tomorrow_north",
    "do_solar_forecast_tomorrow_south": "sensor.dummy_os_solar_forecast_tomorrow_south",
    "do_solar_forecast_tomorrow_total": "sensor.dummy_os_solar_forecast_tomorrow_total",
    "do_solar_forecast_next_quarter": "sensor.dummy_os_solar_forecast_next_quarter",
    "do_solar_actual_power_north": "sensor.dummy_os_solar_actual_power_north",
    "do_solar_actual_power_south": "sensor.dummy_os_solar_actual_power_south",
    "do_solar_actual_power_total": "sensor.dummy_os_solar_actual_power_total",
    "do_solar_evaluation_last_completed_quarter": "sensor.dummy_os_solar_evaluation_last_completed_quarter",
    "do_solar_model": "sensor.dummy_os_solar_forecast_model",
}

# Explicit aliases observed or possible for the short-lived alpha.11.4 Home
# Power input layer. These entities are safe to remove because they were newly
# introduced for validation and have not been adopted by forecast/EMS consumers.
OBSOLETE_HOME_INPUT_ENTITY_ALIASES: dict[str, set[str]] = {
    "do_input_home_power_raw": {
        "sensor.dummy_os_input_home_power_raw",
        "sensor.do_input_home_power_raw",
    },
    "do_home_power": {
        "sensor.dummy_os_home_power",
        "sensor.do_home_power",
    },
    "do_home_import_power": {
        "sensor.dummy_os_home_import_power",
        "sensor.do_home_import_power",
    },
    "do_home_export_power": {
        "sensor.dummy_os_home_export_power",
        "sensor.do_home_export_power",
    },
}

# Redundant aliases for definitive do_data_* entities. Their entity names are
# deliberately "DO Data ..." so first-time automatic generation should already
# yield the target ID; this mapping is an extra safety net.
DATA_GENERATED_ENTITY_ID_ALIASES: dict[str, set[str]] = {
    "do_data_grid_import_power": {"sensor.dummy_os_do_data_grid_import_power"},
    "do_data_grid_export_power": {"sensor.dummy_os_do_data_grid_export_power"},
    "do_data_solar_power": {"sensor.dummy_os_do_data_solar_power"},
    "do_data_battery_charge_power": {"sensor.dummy_os_do_data_battery_charge_power"},
    "do_data_battery_discharge_power": {"sensor.dummy_os_do_data_battery_discharge_power"},
    "do_data_home_power": {"sensor.dummy_os_do_data_home_power"},
}


def is_known_generated_entity_id(platform: str, unique_id: str, entity_id: str) -> bool:
    """Return whether an entity ID is a safe, known automatic ID to migrate."""
    legacy_prefix = f"{platform}.dummy_os_data_dummy_os_"
    if entity_id.startswith(legacy_prefix):
        return True
    if entity_id == SOLAR_GENERATED_ENTITY_ID_ALIASES.get(unique_id):
        return True
    if entity_id in OBSOLETE_HOME_INPUT_ENTITY_ALIASES.get(unique_id, set()):
        return True
    return entity_id in DATA_GENERATED_ENTITY_ID_ALIASES.get(unique_id, set())
