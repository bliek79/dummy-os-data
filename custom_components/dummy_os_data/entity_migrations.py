"""Known Home Assistant entity-ID aliases that require deterministic migration."""

from __future__ import annotations


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
    "do_solar_evaluation_horizon_1h": "sensor.dummy_os_solar_evaluation_horizon_1h",
    "do_solar_evaluation_horizon_6h": "sensor.dummy_os_solar_evaluation_horizon_6h",
    "do_solar_evaluation_horizon_24h": "sensor.dummy_os_solar_evaluation_horizon_24h",
    "do_solar_evaluation_horizon_48h": "sensor.dummy_os_solar_evaluation_horizon_48h",
    "do_solar_evaluation_horizon_72h": "sensor.dummy_os_solar_evaluation_horizon_72h",
    "do_solar_model": "sensor.dummy_os_solar_forecast_model",
}

DEGREE_DAYS_GENERATED_ENTITY_ID_ALIASES: dict[str, str] = {
    "do_degree_days_status": "sensor.dummy_os_forecast_do_degree_days_status",
    "do_degree_days_history_days": "sensor.dummy_os_forecast_do_degree_days_history_days",
    "do_degree_days_temperature_daily": "sensor.dummy_os_forecast_do_degree_days_temperature_daily",
    "do_degree_days_daily": "sensor.dummy_os_forecast_do_degree_days_daily",
    "do_degree_days_weighted_daily": "sensor.dummy_os_forecast_do_degree_days_weighted_daily",
    "do_degree_days_reference_daily": "sensor.dummy_os_forecast_do_degree_days_reference_daily",
    "do_degree_days_weighted_reference_daily": "sensor.dummy_os_forecast_do_degree_days_weighted_reference_daily",
    "do_degree_days_difference": "sensor.dummy_os_forecast_do_degree_days_difference",
    "do_degree_days_weighted_difference": "sensor.dummy_os_forecast_do_degree_days_weighted_difference",
    "do_degree_days_last_day": "sensor.dummy_os_forecast_do_degree_days_last_day",
}


ENERGY_GENERATED_ENTITY_ID_ALIASES: dict[str, str] = {
    "do_energy_forecast_quality_by_daypart": "sensor.dummy_os_forecast_do_energy_forecast_quality_by_daypart",
    "do_energy_forecast_quality_by_day_type": "sensor.dummy_os_forecast_do_energy_forecast_quality_by_day_type",
    "do_energy_forecast_quality_by_day_type_and_daypart": "sensor.dummy_os_forecast_do_energy_forecast_quality_by_day_type_and_daypart",
    "do_energy_forecast_quality_by_hour": "sensor.dummy_os_forecast_do_energy_forecast_quality_by_hour",
}

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

DATA_GENERATED_ENTITY_ID_ALIASES: dict[str, set[str]] = {
    "do_data_grid_net_power": {"sensor.dummy_os_do_data_grid_net_power"},
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
    if entity_id == DEGREE_DAYS_GENERATED_ENTITY_ID_ALIASES.get(unique_id):
        return True
    if entity_id == ENERGY_GENERATED_ENTITY_ID_ALIASES.get(unique_id):
        return True
    if entity_id in OBSOLETE_HOME_INPUT_ENTITY_ALIASES.get(unique_id, set()):
        return True
    return entity_id in DATA_GENERATED_ENTITY_ID_ALIASES.get(unique_id, set())
