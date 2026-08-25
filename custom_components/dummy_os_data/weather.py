"""Open-Meteo weather source for Dummy OS Data."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientError

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import FORECAST_SLOTS

_LOGGER = logging.getLogger(__name__)

OPEN_METEO_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_LATITUDE = 51.828981
OPEN_METEO_LONGITUDE = 4.839871
OPEN_METEO_TIMEZONE = "Europe/Berlin"
OPEN_METEO_MODEL = "best_match"

CURRENT_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)

MINUTELY_15_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "shortwave_radiation",
    "sunshine_duration",
    "diffuse_radiation",
    "direct_normal_irradiance",
    "is_day",
    "direct_radiation",
)

DAILY_VARIABLES = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "sunrise",
    "sunset",
    "daylight_duration",
    "sunshine_duration",
    "precipitation_sum",
    "precipitation_hours",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "shortwave_radiation_sum",
)

POINT_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "shortwave_radiation",
    "sunshine_duration",
    "diffuse_radiation",
    "direct_normal_irradiance",
    "is_day",
    "direct_radiation",
)


class DummyOSWeatherCoordinator:
    """Fetch and normalize Open-Meteo weather data."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.current: dict[str, Any] = {}
        self.timeline: list[list[Any]] = []
        self.daily: list[dict[str, Any]] = []
        self.last_successful_update: datetime | None = None
        self.last_attempt: datetime | None = None
        self.last_error: str | None = None
        self.source_latitude: float | None = None
        self.source_longitude: float | None = None
        self.source_elevation: float | None = None
        self.generation_time_ms: float | None = None
        self.listeners: list[callback] = []
        self._unsubs: list[Any] = []

    async def async_setup(self) -> None:
        """Fetch immediately and then refresh on each whole hour."""
        await self.async_refresh()
        self._unsubs.append(
            async_track_time_change(
                self.hass,
                self._async_hourly_refresh,
                minute=0,
                second=5,
            )
        )

    async def async_shutdown(self) -> None:
        """Stop scheduled refreshes."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    def async_add_listener(self, listener: callback) -> callback:
        """Add a state update listener."""
        self.listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self.listeners:
                self.listeners.remove(listener)

        return remove_listener

    @callback
    def _notify(self) -> None:
        for listener in list(self.listeners):
            listener()

    async def _async_hourly_refresh(self, _now: datetime) -> None:
        await self.async_refresh()

    async def async_refresh(self) -> None:
        """Fetch the current Open-Meteo source snapshot."""
        self.last_attempt = dt_util.utcnow()
        params = {
            "latitude": OPEN_METEO_LATITUDE,
            "longitude": OPEN_METEO_LONGITUDE,
            "current": ",".join(CURRENT_VARIABLES),
            "minutely_15": ",".join(MINUTELY_15_VARIABLES),
            "daily": ",".join(DAILY_VARIABLES),
            "forecast_minutely_15": FORECAST_SLOTS,
            "timezone": OPEN_METEO_TIMEZONE,
        }
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(OPEN_METEO_ENDPOINT, params=params, timeout=20) as response:
                response.raise_for_status()
                payload = await response.json()
            self._apply_payload(payload)
            self.last_successful_update = dt_util.utcnow()
            self.last_error = None
        except (ClientError, asyncio.TimeoutError, ValueError, TypeError, KeyError) as err:
            self.last_error = f"{type(err).__name__}: {err}"
            _LOGGER.warning("Open-Meteo weather refresh failed: %s", self.last_error)
        self._notify()

    def _apply_payload(self, payload: dict[str, Any]) -> None:
        """Validate and normalize one Open-Meteo response."""
        current = payload.get("current")
        minutely = payload.get("minutely_15")
        if not isinstance(current, dict) or not isinstance(minutely, dict):
            raise ValueError("Open-Meteo response missing current or minutely_15 data")

        times = minutely.get("time")
        if not isinstance(times, list):
            raise ValueError("Open-Meteo response missing minutely_15 time axis")

        timezone = ZoneInfo(OPEN_METEO_TIMEZONE)
        points: list[list[Any]] = []
        for index, raw_time in enumerate(times[:FORECAST_SLOTS]):
            if not isinstance(raw_time, str):
                continue
            local_dt = datetime.fromisoformat(raw_time)
            if local_dt.tzinfo is None:
                local_dt = local_dt.replace(tzinfo=timezone)
            timestamp_ms = int(local_dt.astimezone(dt_util.UTC).timestamp() * 1000)
            values: list[Any] = [timestamp_ms]
            complete = True
            for field in POINT_FIELDS:
                series = minutely.get(field)
                if not isinstance(series, list) or index >= len(series):
                    complete = False
                    break
                values.append(series[index])
            if complete:
                points.append(values)

        if not points:
            raise ValueError("Open-Meteo response produced no usable 15-minute points")

        self.current = current
        self.timeline = points
        self.daily = self._normalize_daily(payload.get("daily"))
        self.source_latitude = self._as_float(payload.get("latitude"))
        self.source_longitude = self._as_float(payload.get("longitude"))
        self.source_elevation = self._as_float(payload.get("elevation"))
        self.generation_time_ms = self._as_float(payload.get("generationtime_ms"))

    @staticmethod
    def _normalize_daily(raw_daily: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_daily, dict):
            return []
        times = raw_daily.get("time")
        if not isinstance(times, list):
            return []
        result: list[dict[str, Any]] = []
        for index, day in enumerate(times):
            item: dict[str, Any] = {"date": day}
            for field in DAILY_VARIABLES:
                series = raw_daily.get(field)
                item[field] = series[index] if isinstance(series, list) and index < len(series) else None
            result.append(item)
        return result

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def source_status(self) -> str:
        """Return compact source health."""
        if self.last_successful_update is None:
            return "error" if self.last_error else "not_loaded"
        age = self.age_minutes
        if age is None:
            return "not_loaded"
        if self.last_error and age >= 90:
            return "stale"
        if age >= 180:
            return "expired"
        return "ok"

    @property
    def age_minutes(self) -> float | None:
        """Age of the last successful source update."""
        if self.last_successful_update is None:
            return None
        return round(max(0.0, (dt_util.utcnow() - self.last_successful_update).total_seconds()) / 60.0, 1)

    @property
    def freshness(self) -> str:
        """Human-readable source freshness state."""
        age = self.age_minutes
        if age is None:
            return "unknown"
        if age < 90:
            return "fresh"
        if age < 180:
            return "stale"
        return "expired"
