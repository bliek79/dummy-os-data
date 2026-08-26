"""Constants for Dummy OS Data."""

from __future__ import annotations

DOMAIN = "dummy_os_data"
NAME = "Dummy OS"
VERSION = "0.1.0-alpha.10.2"

CONF_HOME_POWER_ENTITY = "home_power_entity"
DEFAULT_HOME_POWER_ENTITY = "sensor.home_power"

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

PLATFORMS = ["sensor", "select"]

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.home_forecast"

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
