"""Constants for Dummy OS Forecast."""

from __future__ import annotations

DOMAIN = "dummy_os_data"
NAME = "Dummy OS Forecast"
VERSION = "0.1.0-alpha.12.8"

# Legacy Energy Forecast source key retained for config-entry compatibility only.
# Energy Forecast production always consumes the canonical Source Home Power entity.
CONF_HOME_POWER_ENTITY = "home_power_entity"
DEFAULT_HOME_POWER_ENTITY = "sensor.home_power"
CANONICAL_HOME_POWER_ENTITY = "sensor.do_source_home_power"
CONF_HOME_POWER_POSITIVE_DIRECTION = "home_power_positive_direction"
HOME_POWER_POSITIVE_CONSUMPTION = "consumption"
HOME_POWER_POSITIVE_EXPORT = "export"
HOME_POWER_POSITIVE_DIRECTION_OPTIONS = [
    HOME_POWER_POSITIVE_CONSUMPTION,
    HOME_POWER_POSITIVE_EXPORT,
]

# Canonical Dummy OS Forecast source-layer energy inputs.
# Grid power is one bidirectional source: positive = import, negative = export.
CONF_GRID_NET_POWER_ENTITY = "grid_net_power_entity"
CONF_DATA_SOLAR_POWER_ENTITY = "data_solar_power_entity"
CONF_BATTERY_CHARGE_POWER_ENTITY = "battery_charge_power_entity"
CONF_BATTERY_DISCHARGE_POWER_ENTITY = "battery_discharge_power_entity"
DATA_POWER_SOURCE_KEYS = [
    CONF_GRID_NET_POWER_ENTITY,
    CONF_DATA_SOLAR_POWER_ENTITY,
    CONF_BATTERY_CHARGE_POWER_ENTITY,
    CONF_BATTERY_DISCHARGE_POWER_ENTITY,
]

# Temporary alpha.11.5 option keys retained only to prefill migration safely.
LEGACY_CONF_GRID_IMPORT_POWER_ENTITY = "grid_import_power_entity"
LEGACY_CONF_GRID_EXPORT_POWER_ENTITY = "grid_export_power_entity"

CONF_TARIFF_PROFILE_ID = "tariff_profile_id"
CONF_TARIFF_SUPPLIER = "tariff_supplier"
CONF_TARIFF_VALID_FROM = "tariff_valid_from"
CONF_VAT_PERCENT = "vat_percent"
CONF_ELECTRICITY_IMPORT_SUPPLIER = "electricity_import_supplier_incl_vat"
CONF_ELECTRICITY_IMPORT_TAX = "electricity_import_tax_incl_vat"
CONF_ELECTRICITY_EXPORT_SUPPLIER = "electricity_export_supplier_incl_vat"
CONF_ELECTRICITY_EXPORT_TAX = "electricity_export_tax_incl_vat"
CONF_ELECTRICITY_FIXED_SUPPLY_PER_DAY = "electricity_fixed_supply_per_day"
CONF_ELECTRICITY_GRID_PER_DAY = "electricity_grid_per_day"
CONF_ELECTRICITY_TAX_CREDIT_PER_DAY = "electricity_tax_credit_per_day"
CONF_GAS_MARKET_ENTITY = "gas_market_entity"
CONF_GAS_SUPPLIER = "gas_supplier_incl_vat"
CONF_GAS_TAX = "gas_tax_incl_vat"
CONF_GAS_FIXED_SUPPLY_PER_DAY = "gas_fixed_supply_per_day"
CONF_GAS_GRID_PER_DAY = "gas_grid_per_day"

DEFAULT_GAS_MARKET_ENTITY = "sensor.energyzero_today_gas_current_hour_price"
GAS_VARIABLE_ADDON_ENTITY = "input_number.gas_markup_per_m3"

CONF_SOLAR_ACTUAL_TOTAL_ENTITY = "solar_actual_total_entity"
CONF_SOLAR_ACTUAL_NORTH_DC_ENTITY = "solar_actual_north_dc_entity"
CONF_SOLAR_ACTUAL_SOUTH_DC_ENTITY = "solar_actual_south_dc_entity"
CONF_SOLAR_LATITUDE = "solar_latitude"
CONF_SOLAR_LONGITUDE = "solar_longitude"
CONF_SOLAR_NORTH_DC_KWP = "solar_north_dc_kwp"
CONF_SOLAR_NORTH_AC_KW = "solar_north_ac_kw"
CONF_SOLAR_NORTH_TILT = "solar_north_tilt"
CONF_SOLAR_NORTH_AZIMUTH = "solar_north_open_meteo_azimuth"
CONF_SOLAR_NORTH_FACTOR = "solar_north_performance_factor"
CONF_SOLAR_SOUTH_DC_KWP = "solar_south_dc_kwp"
CONF_SOLAR_SOUTH_AC_KW = "solar_south_ac_kw"
CONF_SOLAR_SOUTH_TILT = "solar_south_tilt"
CONF_SOLAR_SOUTH_AZIMUTH = "solar_south_open_meteo_azimuth"
CONF_SOLAR_SOUTH_FACTOR = "solar_south_performance_factor"

DEFAULT_SOLAR_ACTUAL_TOTAL_ENTITY = "sensor.sb3_6_1av_41_857_pv_power"
DEFAULT_SOLAR_ACTUAL_NORTH_DC_ENTITY = "sensor.sb3_6_1av_41_857_pv_power_a"
DEFAULT_SOLAR_ACTUAL_SOUTH_DC_ENTITY = "sensor.sb3_6_1av_41_857_pv_power_b"

PLATFORMS = ["sensor", "select"]

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.home_forecast"
ENERGY_STORE_SCHEMA_VERSION = 1
ENERGY_EVALUATION_SCHEMA_VERSION = 1
SOLAR_STORAGE_VERSION = 1
SOLAR_STORAGE_KEY = f"{DOMAIN}.solar_evaluation"

PROFILE_NORMAL = "normal"
PROFILE_AWAY = "away"
PROFILE_OPTIONS = [PROFILE_NORMAL, PROFILE_AWAY]

QUARTER_MINUTES = 15
QUARTER_SECONDS = QUARTER_MINUTES * 60
QUARTERS_PER_DAY = 96
FORECAST_HORIZON_HOURS = 72
FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES
MAX_HISTORY_DAYS = 400
MIN_VALID_COVERAGE = 0.90
SOLAR_MIN_VALID_COVERAGE = 0.90
