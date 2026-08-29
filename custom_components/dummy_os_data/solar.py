"""Native Open-Meteo solar forecast provider for Dummy OS Data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientError

from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SOLAR_ACTUAL_NORTH_DC_ENTITY,
    CONF_SOLAR_ACTUAL_SOUTH_DC_ENTITY,
    CONF_SOLAR_ACTUAL_TOTAL_ENTITY,
    CONF_SOLAR_LATITUDE,
    CONF_SOLAR_LONGITUDE,
    CONF_SOLAR_NORTH_AC_KW,
    CONF_SOLAR_NORTH_AZIMUTH,
    CONF_SOLAR_NORTH_DC_KWP,
    CONF_SOLAR_NORTH_FACTOR,
    CONF_SOLAR_NORTH_TILT,
    CONF_SOLAR_SOUTH_AC_KW,
    CONF_SOLAR_SOUTH_AZIMUTH,
    CONF_SOLAR_SOUTH_DC_KWP,
    CONF_SOLAR_SOUTH_FACTOR,
    CONF_SOLAR_SOUTH_TILT,
    DEFAULT_SOLAR_ACTUAL_NORTH_DC_ENTITY,
    DEFAULT_SOLAR_ACTUAL_SOUTH_DC_ENTITY,
    DEFAULT_SOLAR_ACTUAL_TOTAL_ENTITY,
    FORECAST_SLOTS,
    QUARTER_MINUTES,
)
from .solar_model import (
    backward_average_slot_start,
    next_complete_slot,
    pv_power_kw,
    slot_energy_kwh,
    split_ac_power,
)

_LOGGER = logging.getLogger(__name__)

OPEN_METEO_SOLAR_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_SOLAR_TIMEZONE = "Europe/Berlin"
OPEN_METEO_SOLAR_MODEL = "best_match"
SOLAR_RESOLUTION_MINUTES = 15


@dataclass(frozen=True, slots=True)
class RoofConfig:
    """One independently forecast PV roof plane."""

    key: str
    dc_capacity_kwp: float
    ac_limit_kw: float
    tilt_deg: float
    open_meteo_azimuth_deg: float
    performance_factor: float


@dataclass(frozen=True, slots=True)
class SolarPoint:
    """Normalized forecast point."""

    start: datetime
    north_kwh: float
    south_kwh: float
    total_kwh: float
    north_kw: float
    south_kw: float
    total_kw: float
    north_irradiance_wm2: float
    south_irradiance_wm2: float

    def as_list(self) -> list[int | float]:
        return [
            int(self.start.timestamp() * 1000),
            self.north_kwh,
            self.south_kwh,
            self.total_kwh,
            self.north_kw,
            self.south_kw,
            self.total_kw,
            self.north_irradiance_wm2,
            self.south_irradiance_wm2,
        ]


class DummyOSSolarCoordinator:
    """Fetch two roof forecasts and publish one source-neutral solar timeline."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.points: list[SolarPoint] = []
        self.last_successful_update: datetime | None = None
        self.last_attempt: datetime | None = None
        self.last_error: str | None = None
        self.source_generation_time_ms: dict[str, float | None] = {}
        self.listeners: list[callback] = []
        self._unsubs: list[Any] = []

    def _option(self, key: str, default: Any) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    def _num(self, key: str, default: float) -> float:
        try:
            return float(self._option(key, default))
        except (TypeError, ValueError):
            return default

    @property
    def latitude(self) -> float:
        return self._num(CONF_SOLAR_LATITUDE, 51.828981)

    @property
    def longitude(self) -> float:
        return self._num(CONF_SOLAR_LONGITUDE, 4.839871)

    @property
    def north(self) -> RoofConfig:
        return RoofConfig(
            "north",
            self._num(CONF_SOLAR_NORTH_DC_KWP, 2.96),
            self._num(CONF_SOLAR_NORTH_AC_KW, 2.45),
            self._num(CONF_SOLAR_NORTH_TILT, 37.0),
            self._num(CONF_SOLAR_NORTH_AZIMUTH, 180.0),
            self._num(CONF_SOLAR_NORTH_FACTOR, 0.9),
        )

    @property
    def south(self) -> RoofConfig:
        return RoofConfig(
            "south",
            self._num(CONF_SOLAR_SOUTH_DC_KWP, 1.48),
            self._num(CONF_SOLAR_SOUTH_AC_KW, 1.23),
            self._num(CONF_SOLAR_SOUTH_TILT, 37.0),
            self._num(CONF_SOLAR_SOUTH_AZIMUTH, 0.0),
            self._num(CONF_SOLAR_SOUTH_FACTOR, 0.9),
        )

    @property
    def actual_entities(self) -> tuple[str, str, str]:
        return (
            str(self._option(CONF_SOLAR_ACTUAL_TOTAL_ENTITY, DEFAULT_SOLAR_ACTUAL_TOTAL_ENTITY)),
            str(self._option(CONF_SOLAR_ACTUAL_NORTH_DC_ENTITY, DEFAULT_SOLAR_ACTUAL_NORTH_DC_ENTITY)),
            str(self._option(CONF_SOLAR_ACTUAL_SOUTH_DC_ENTITY, DEFAULT_SOLAR_ACTUAL_SOUTH_DC_ENTITY)),
        )

    async def async_setup(self) -> None:
        """Fetch immediately, hourly and republish actual-power changes."""
        await self.async_refresh()
        self._unsubs.append(async_track_time_change(self.hass, self._async_hourly_refresh, minute=0, second=20))
        self._unsubs.append(async_track_state_change_event(self.hass, list(self.actual_entities), self._actual_changed))

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    def async_add_listener(self, listener: callback) -> callback:
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

    @callback
    def _actual_changed(self, _event: Event) -> None:
        self._notify()

    async def _async_hourly_refresh(self, _now: datetime) -> None:
        await self.async_refresh()

    async def async_refresh(self) -> None:
        """Refresh both orientations while retaining the last valid timeline on failure."""
        last_error: Exception | None = None
        for attempt, delay in enumerate((0, 5, 15), start=1):
            if delay:
                await asyncio.sleep(delay)
            self.last_attempt = dt_util.utcnow()
            try:
                north_payload, south_payload = await asyncio.gather(
                    self._fetch_roof(self.north), self._fetch_roof(self.south)
                )
                self._apply_payloads(north_payload, south_payload)
                self.last_successful_update = dt_util.utcnow()
                self.last_error = None
                self._notify()
                return
            except (ClientError, asyncio.TimeoutError, ValueError, TypeError, KeyError) as err:
                last_error = err
                _LOGGER.warning("Open-Meteo solar refresh attempt %s/3 failed: %s", attempt, err)

        self.last_error = f"{type(last_error).__name__}: {last_error}" if last_error else "unknown_error"
        self._notify()

    async def _fetch_roof(self, roof: RoofConfig) -> dict[str, Any]:
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "minutely_15": "global_tilted_irradiance",
            # Two spare source stamps are required by backward-average alignment;
            # one additional stamp covers refreshes after an exact quarter boundary.
            "forecast_minutely_15": FORECAST_SLOTS + 3,
            "tilt": roof.tilt_deg,
            "azimuth": roof.open_meteo_azimuth_deg,
            "models": OPEN_METEO_SOLAR_MODEL,
            "timezone": OPEN_METEO_SOLAR_TIMEZONE,
        }
        session = async_get_clientsession(self.hass)
        async with session.get(OPEN_METEO_SOLAR_ENDPOINT, params=params, timeout=20) as response:
            response.raise_for_status()
            return await response.json()

    def _apply_payloads(self, north_payload: dict[str, Any], south_payload: dict[str, Any]) -> None:
        north_values = self._normalize_irradiance(north_payload)
        south_values = self._normalize_irradiance(south_payload)
        if set(north_values) != set(south_values):
            raise ValueError("North and south Open-Meteo timelines do not align")

        points: list[SolarPoint] = []
        for start in sorted(north_values):
            north_irradiance = north_values[start]
            south_irradiance = south_values[start]
            north_kw = pv_power_kw(north_irradiance, self.north.dc_capacity_kwp, self.north.ac_limit_kw, self.north.performance_factor)
            south_kw = pv_power_kw(south_irradiance, self.south.dc_capacity_kwp, self.south.ac_limit_kw, self.south.performance_factor)
            north_kwh = slot_energy_kwh(north_kw)
            south_kwh = slot_energy_kwh(south_kw)
            points.append(SolarPoint(start, north_kwh, south_kwh, round(north_kwh + south_kwh, 6), north_kw, south_kw, round(north_kw + south_kw, 6), north_irradiance, south_irradiance))

        if len(points) != FORECAST_SLOTS:
            raise ValueError(f"Open-Meteo solar produced {len(points)} aligned slots; expected {FORECAST_SLOTS}")
        self.points = points
        self.source_generation_time_ms = {
            "north": self._as_float(north_payload.get("generationtime_ms")),
            "south": self._as_float(south_payload.get("generationtime_ms")),
        }

    @staticmethod
    def _normalize_irradiance(payload: dict[str, Any]) -> dict[datetime, float]:
        minutely = payload.get("minutely_15")
        if not isinstance(minutely, dict):
            raise ValueError("Open-Meteo response missing minutely_15")
        times = minutely.get("time")
        values = minutely.get("global_tilted_irradiance")
        if not isinstance(times, list) or not isinstance(values, list):
            raise ValueError("Open-Meteo response missing solar time axis or irradiance")

        local_now = dt_util.as_local(dt_util.utcnow())
        next_quarter = next_complete_slot(local_now, QUARTER_MINUTES)
        cutoff_utc = dt_util.as_utc(next_quarter)
        timezone = ZoneInfo(OPEN_METEO_SOLAR_TIMEZONE)
        result: dict[datetime, float] = {}
        for index, raw_time in enumerate(times):
            if index >= len(values) or not isinstance(raw_time, str):
                continue
            local_dt = datetime.fromisoformat(raw_time)
            if local_dt.tzinfo is None:
                local_dt = local_dt.replace(tzinfo=timezone)
            # Open-Meteo radiation values are backward averages. A value stamped
            # 10:15 therefore represents the 10:00-10:15 energy interval.
            slot_start_utc = backward_average_slot_start(
                local_dt.astimezone(dt_util.UTC), SOLAR_RESOLUTION_MINUTES
            )
            if slot_start_utc < cutoff_utc:
                continue
            try:
                result[slot_start_utc] = max(0.0, float(values[index] or 0.0))
            except (TypeError, ValueError):
                raise ValueError(f"Invalid irradiance at {raw_time}") from None
            if len(result) >= FORECAST_SLOTS:
                break
        return result

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _state_number(self, entity_id: str) -> float | None:
        state: State | None = self.hass.states.get(entity_id)
        if state is None or state.state in {"unknown", "unavailable", "none", "None", ""}:
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        unit = state.attributes.get("unit_of_measurement")
        return value * 1000.0 if unit == "kW" else value

    @property
    def actual_power(self) -> dict[str, float | None]:
        total_entity, north_entity, south_entity = self.actual_entities
        total = self._state_number(total_entity)
        north_dc = self._state_number(north_entity)
        south_dc = self._state_number(south_entity)
        north, south = split_ac_power(total, north_dc, south_dc)
        return {"total": total, "north": north, "south": south, "method": "total_ac_x_dc_input_ratio"}

    def energy_for_local_date(self, date, roof: str = "total") -> float:
        field = {"north": "north_kwh", "south": "south_kwh", "total": "total_kwh"}[roof]
        return round(sum(getattr(point, field) for point in self.points if dt_util.as_local(point.start).date() == date), 3)

    @property
    def age_minutes(self) -> float | None:
        if self.last_successful_update is None:
            return None
        return round(max(0.0, (dt_util.utcnow() - self.last_successful_update).total_seconds()) / 60.0, 1)

    @property
    def source_status(self) -> str:
        if self.last_successful_update is None:
            return "error" if self.last_error else "not_loaded"
        if (self.age_minutes or 0) >= 180:
            return "expired"
        if self.last_error or (self.age_minutes or 0) >= 90:
            return "stale"
        return "ok"
