"""Constants for Dummy OS Data."""

from __future__ import annotations

DOMAIN = "dummy_os_data"
NAME = "Dummy OS Data"
VERSION = "0.1.0-alpha.1"

CONF_HOME_POWER_ENTITY = "home_power_entity"
DEFAULT_HOME_POWER_ENTITY = "sensor.home_power"

PLATFORMS = ["sensor", "select"]

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.home_forecast"

PROFILE_NORMAL = "normal"
PROFILE_AWAY = "away"
PROFILE_OPTIONS = [PROFILE_NORMAL, PROFILE_AWAY]

QUARTER_MINUTES = 15
QUARTER_SECONDS = QUARTER_MINUTES * 60
MAX_HISTORY_DAYS = 400
MIN_VALID_COVERAGE = 0.90
