"""Native Open-Meteo solar forecast provider for Dummy OS Data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import math
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientError

from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.storage import Store
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
    SOLAR_MIN_VALID_COVERAGE,
    SOLAR_STORAGE_KEY,
    SOLAR_STORAGE_VERSION,
)
from .solar_evaluation import ROOFS, build_quarter_evaluation
from .solar_model import (
    backward_average_slot_start,
    floor_slot_start,
    next_complete_slot,
    next_future_slot_index,
    pv_power_kw,
    slot_energy_kwh,
    split_ac_power,
)

_LOGGER = logging.getLogger(__name__)

OPEN_METEO_SOLAR_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_SOLAR_TIMEZONE = "UTC"
OPEN_METEO_SOLAR_MODEL = "best_match"
SOLAR_RESOLUTION_MINUTES = 15
SOLAR_BUFFER_SLOTS = 4
SOLAR_REQUEST_EXTRA_SLOTS = 7
SOLAR_STORAGE_SAVE_DELAY_SECONDS = 30
SOLAR_HORIZON_HOURS = (1, 6, 24, 48, 72)


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
        self._source_points: list[SolarPoint] = []
        self.last_successful_update: datetime | None = None
        self.last_attempt: datetime | None = None
        self.last_error: str | None = None
        self.source_generation_time_ms: dict[str, float | None] = {}
        self.listeners: list[callback] = []
        self._unsubs: list[Any] = []
        self.store: Store[dict[str, Any]] = Store(
            hass,
            SOLAR_STORAGE_VERSION,
            SOLAR_STORAGE_KEY,
        )
        self.last_evaluation: dict[str, Any] | None = None
        self.last_horizon_evaluations: list[dict[str, Any]] = []
        self._horizon_snapshots: dict[str, dict[str, Any]] = {}
        self._quarter_start: datetime | None = None
        self._forecast_snapshot: dict[str, Any] | None = None
        self._energy_ws: dict[str, float] = {roof: 0.0 for roof in ROOFS}
        self._covered_seconds: dict[str, float] = {roof: 0.0 for roof in ROOFS}
        self._last_sample_time: datetime | None = None
        self._last_actual: dict[str, float | None] = {roof: None for roof in ROOFS}
        self._sample_count = 0

    @property
    def points(self) -> list[SolarPoint]:
        """Return a rolling 72-hour window aligned to the next complete slot."""
        if not self._source_points:
            return []
        local_now = dt_util.as_local(dt_util.utcnow())
        cutoff = dt_util.as_utc(next_complete_slot(local_now, QUARTER_MINUTES))
        return [point for point in self._source_points if point.start >= cutoff][:FORECAST_SLOTS]

    @property
    def source_point_count(self) -> int:
        """Return raw aligned points retained for rolling-window continuity."""
        return len(self._source_points)

    @property
    def active_quarter_start(self) -> datetime | None:
        """Return the quarter currently collecting actual power."""
        return self._quarter_start

    @property
    def active_forecast_snapshot_available(self) -> bool:
        """Return whether the active quarter has a valid pre-actual forecast."""
        return self._forecast_snapshot is not None

    @property
    def pending_horizon_snapshot_count(self) -> int:
        """Return the number of immutable future horizon snapshots awaiting actuals."""
        return len(self._horizon_snapshots)

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
        """Load evaluation state, fetch Solar data and start listeners."""
        stored = await self.store.async_load() or {}
        self.last_evaluation = stored.get("last_evaluation")
        raw_horizon_evaluations = stored.get("last_horizon_evaluations")
        if isinstance(raw_horizon_evaluations, list):
            self.last_horizon_evaluations = [
                item for item in raw_horizon_evaluations if isinstance(item, dict)
            ]
        raw_horizon_snapshots = stored.get("horizon_snapshots")
        if isinstance(raw_horizon_snapshots, dict):
            self._horizon_snapshots = {
                str(key): value
                for key, value in raw_horizon_snapshots.items()
                if isinstance(value, dict)
            }
        await self.async_refresh()

        now = dt_util.utcnow()
        self._restore_or_start_quarter(stored.get("active_quarter"), now)
        self._prune_horizon_snapshots(self._quarter_start or now)
        self._set_actual_sample(now)

        self._unsubs.append(async_track_time_change(self.hass, self._async_hourly_refresh, minute=0, second=20))
        self._unsubs.append(
            async_track_time_change(
                self.hass,
                self._async_quarter_boundary,
                minute=[0, 15, 30, 45],
                second=0,
            )
        )
        self._unsubs.append(async_track_state_change_event(self.hass, list(self.actual_entities), self._actual_changed))
        await self.store.async_save(self._storage_data())

    async def async_shutdown(self) -> None:
        self._integrate_actual_until(dt_util.utcnow())
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self.store.async_save(self._storage_data())

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
        now = dt_util.utcnow()
        self._integrate_actual_until(now)
        self._set_actual_sample(now)
        self.store.async_delay_save(
            self._storage_data,
            SOLAR_STORAGE_SAVE_DELAY_SECONDS,
        )
        self._notify()

    async def _async_quarter_boundary(self, now: datetime) -> None:
        """Finalize actual energy, capture future horizons and freeze the new slot."""
        now_utc = dt_util.as_utc(now)
        boundary_utc = floor_slot_start(now_utc, QUARTER_MINUTES)
        self._integrate_actual_until(boundary_utc)
        self._finalize_quarter(boundary_utc)
        self._capture_horizon_snapshots(boundary_utc)
        if self.last_evaluation is not None:
            self.last_evaluation["pending_horizon_snapshot_count"] = len(self._horizon_snapshots)
            self.last_evaluation["horizon_capture_boundary"] = boundary_utc.isoformat()
        self._start_quarter(boundary_utc, scheduled_boundary=True)
        self._set_actual_sample(boundary_utc)
        await self.store.async_save(self._storage_data())
        self._notify()

    def _restore_or_start_quarter(
        self,
        stored: dict[str, Any] | None,
        now_utc: datetime,
    ) -> None:
        """Restore only the active local quarter; never bridge an offline gap."""
        local = dt_util.as_local(now_utc)
        minute = (local.minute // QUARTER_MINUTES) * QUARTER_MINUTES
        current_start = dt_util.as_utc(
            local.replace(minute=minute, second=0, microsecond=0)
        )
        if isinstance(stored, dict) and stored.get("start") == current_start.isoformat():
            self._quarter_start = current_start
            self._forecast_snapshot = (
                stored.get("forecast_snapshot")
                if isinstance(stored.get("forecast_snapshot"), dict)
                else None
            )
            for roof in ROOFS:
                try:
                    self._energy_ws[roof] = max(
                        0.0,
                        float(stored.get("energy_ws", {}).get(roof, 0.0)),
                    )
                    self._covered_seconds[roof] = max(
                        0.0,
                        float(stored.get("covered_seconds", {}).get(roof, 0.0)),
                    )
                except (AttributeError, TypeError, ValueError):
                    self._energy_ws[roof] = 0.0
                    self._covered_seconds[roof] = 0.0
            try:
                self._sample_count = max(0, int(stored.get("sample_count", 0)))
            except (TypeError, ValueError):
                self._sample_count = 0
            self._last_sample_time = now_utc
            return
        self._start_quarter(now_utc)

    def _start_quarter(
        self,
        now_utc: datetime,
        *,
        scheduled_boundary: bool = False,
    ) -> None:
        """Start the quarter containing now and freeze its current forecast."""
        local = dt_util.as_local(now_utc)
        minute = (local.minute // QUARTER_MINUTES) * QUARTER_MINUTES
        local_start = local.replace(minute=minute, second=0, microsecond=0)
        self._quarter_start = dt_util.as_utc(local_start)
        captured_at = self._quarter_start if scheduled_boundary else now_utc
        self._forecast_snapshot = self._snapshot_for_slot(
            self._quarter_start,
            captured_at,
        )
        self._energy_ws = {roof: 0.0 for roof in ROOFS}
        self._covered_seconds = {roof: 0.0 for roof in ROOFS}
        self._last_sample_time = now_utc
        self._sample_count = 0

    def _snapshot_for_slot(
        self,
        slot_start: datetime,
        captured_at: datetime,
    ) -> dict[str, Any] | None:
        """Freeze one forecast before any actual energy for that slot is known."""
        point = next(
            (
                item
                for item in self._source_points
                if item.start == dt_util.as_utc(slot_start)
            ),
            None,
        )
        captured = dt_util.as_utc(captured_at)
        if point is None or captured > dt_util.as_utc(slot_start):
            return None
        return {
            "start": point.start.isoformat(),
            "end": (point.start + timedelta(minutes=QUARTER_MINUTES)).isoformat(),
            "north_kwh": point.north_kwh,
            "south_kwh": point.south_kwh,
            "total_kwh": point.total_kwh,
            "provider": "open_meteo",
            "model": "open_meteo_gti_physical_v0.1",
            "source_update": (
                self.last_successful_update.isoformat()
                if self.last_successful_update
                else None
            ),
            "captured_at": captured.isoformat(),
        }

    def _capture_horizon_snapshots(self, captured_at: datetime) -> None:
        """Freeze the forecast for each configured future validation horizon."""
        captured = dt_util.as_utc(captured_at)
        self._prune_horizon_snapshots(captured)
        for horizon_hours in SOLAR_HORIZON_HOURS:
            target_start = captured + timedelta(hours=horizon_hours)
            snapshot = self._snapshot_for_slot(target_start, captured)
            if snapshot is None:
                continue
            snapshot["horizon_hours"] = horizon_hours
            snapshot["snapshot_id"] = (
                f"{target_start.isoformat()}|{horizon_hours}h"
            )
            self._horizon_snapshots.setdefault(snapshot["snapshot_id"], snapshot)

    def _prune_horizon_snapshots(self, current_slot_start: datetime) -> None:
        """Discard stale pending snapshots that can no longer receive an actual."""
        current = dt_util.as_utc(current_slot_start)
        stale: list[str] = []
        for key, snapshot in self._horizon_snapshots.items():
            try:
                target = datetime.fromisoformat(str(snapshot.get("start")))
                if target.tzinfo is None:
                    target = target.replace(tzinfo=dt_util.UTC)
                if dt_util.as_utc(target) < current:
                    stale.append(key)
            except (TypeError, ValueError):
                stale.append(key)
        for key in stale:
            self._horizon_snapshots.pop(key, None)

    def _set_actual_sample(self, now_utc: datetime) -> None:
        """Store the power values that apply from now onward."""
        actual = self.actual_power
        self._last_actual = {roof: actual[roof] for roof in ROOFS}
        self._last_sample_time = now_utc
        self._sample_count += 1

    def _integrate_actual_until(self, now_utc: datetime) -> None:
        """Integrate the previous sample with zero-order hold inside one slot."""
        if self._quarter_start is None or self._last_sample_time is None:
            self._last_sample_time = now_utc
            return
        quarter_end = self._quarter_start + timedelta(minutes=QUARTER_MINUTES)
        interval_start = max(self._last_sample_time, self._quarter_start)
        interval_end = min(now_utc, quarter_end)
        seconds = max(0.0, (interval_end - interval_start).total_seconds())
        if seconds > 0:
            for roof in ROOFS:
                power_w = self._last_actual.get(roof)
                if power_w is None:
                    continue
                self._energy_ws[roof] += max(0.0, power_w) * seconds
                self._covered_seconds[roof] += seconds
        self._last_sample_time = interval_end

    def _finalize_quarter(self, end_utc: datetime) -> None:
        """Publish the direct quarter record and any due horizon evaluations."""
        if self._quarter_start is None:
            return
        expected_end = self._quarter_start + timedelta(minutes=QUARTER_MINUTES)
        if end_utc < expected_end:
            return
        self.last_evaluation = build_quarter_evaluation(
            self._quarter_start,
            self._forecast_snapshot,
            self._energy_ws,
            self._covered_seconds,
            self._sample_count,
            SOLAR_MIN_VALID_COVERAGE,
        )

        slot_id = self._quarter_start.isoformat()
        due: list[tuple[str, dict[str, Any]]] = [
            (key, snapshot)
            for key, snapshot in self._horizon_snapshots.items()
            if snapshot.get("start") == slot_id
        ]
        horizon_evaluations: list[dict[str, Any]] = []
        for key, snapshot in due:
            evaluation = build_quarter_evaluation(
                self._quarter_start,
                snapshot,
                self._energy_ws,
                self._covered_seconds,
                self._sample_count,
                SOLAR_MIN_VALID_COVERAGE,
            )
            evaluation["evaluation_method"] = "horizon_snapshot_vs_completed_quarter_v1"
            evaluation["horizon_hours"] = int(snapshot.get("horizon_hours", 0))
            evaluation["snapshot_id"] = snapshot.get("snapshot_id", key)
            horizon_evaluations.append(evaluation)
            self._horizon_snapshots.pop(key, None)

        horizon_evaluations.sort(key=lambda item: int(item.get("horizon_hours", 0)))
        self.last_horizon_evaluations = horizon_evaluations
        self.last_evaluation["horizon_evaluations"] = horizon_evaluations
        self.last_evaluation["horizon_evaluation_count"] = len(horizon_evaluations)
        self.last_evaluation["horizon_hours_supported"] = list(SOLAR_HORIZON_HOURS)
        self.last_evaluation["pending_horizon_snapshot_count"] = len(self._horizon_snapshots)
        for evaluation in horizon_evaluations:
            hours = int(evaluation["horizon_hours"])
            prefix = f"horizon_{hours}h_"
            for field in (
                "status",
                "valid",
                "forecast_captured_at",
                "forecast_source_update",
                "forecast_provider",
                "forecast_model",
                "forecast_total_kwh",
                "actual_total_kwh",
                "error_total_kwh",
                "absolute_error_total_kwh",
                "bias_total_percent",
                "accuracy_total_percent",
                "coverage_total_percent",
            ):
                self.last_evaluation[prefix + field] = evaluation.get(field)

    def _storage_data(self) -> dict[str, Any]:
        """Return compact JSON-safe evaluation state."""
        active = None
        if self._quarter_start is not None:
            active = {
                "start": self._quarter_start.isoformat(),
                "forecast_snapshot": self._forecast_snapshot,
                "energy_ws": dict(self._energy_ws),
                "covered_seconds": dict(self._covered_seconds),
                "sample_count": self._sample_count,
            }
        return {
            "active_quarter": active,
            "last_evaluation": self.last_evaluation,
            "last_horizon_evaluations": self.last_horizon_evaluations,
            "horizon_snapshots": self._horizon_snapshots,
        }

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
            # Extra stamps cover backward-average alignment plus four rolling
            # quarter advances until the next hourly refresh.
            "forecast_minutely_15": FORECAST_SLOTS + SOLAR_REQUEST_EXTRA_SLOTS,
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
        local_now = dt_util.as_local(dt_util.utcnow())
        cutoff_utc = dt_util.as_utc(
            next_complete_slot(local_now, QUARTER_MINUTES)
        )
        north_values = self._normalize_irradiance(north_payload, cutoff_utc)
        south_values = self._normalize_irradiance(south_payload, cutoff_utc)
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

        if len(points) < FORECAST_SLOTS:
            raise ValueError(
                f"Open-Meteo solar produced {len(points)} aligned slots; "
                f"expected at least {FORECAST_SLOTS}"
            )
        self._source_points = points
        self.source_generation_time_ms = {
            "north": self._as_float(north_payload.get("generationtime_ms")),
            "south": self._as_float(south_payload.get("generationtime_ms")),
        }

    @staticmethod
    def _normalize_irradiance(
        payload: dict[str, Any],
        cutoff_utc: datetime,
    ) -> dict[datetime, float]:
        minutely = payload.get("minutely_15")
        if not isinstance(minutely, dict):
            raise ValueError("Open-Meteo response missing minutely_15")
        times = minutely.get("time")
        values = minutely.get("global_tilted_irradiance")
        if not isinstance(times, list) or not isinstance(values, list):
            raise ValueError("Open-Meteo response missing solar time axis or irradiance")

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
                if values[index] is None:
                    raise ValueError
                irradiance = float(values[index])
                if not math.isfinite(irradiance):
                    raise ValueError
                result[slot_start_utc] = max(0.0, irradiance)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid irradiance at {raw_time}") from None
            if len(result) >= FORECAST_SLOTS + SOLAR_BUFFER_SLOTS:
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
        if not math.isfinite(value):
            return None
        unit = state.attributes.get("unit_of_measurement")
        if unit == "kW":
            return value * 1000.0
        if unit == "W" or unit is None:
            return value
        _LOGGER.warning(
            "Unsupported Solar power unit %s for %s; expected W or kW",
            unit,
            entity_id,
        )
        return None

    @property
    def actual_power(self) -> dict[str, Any]:
        total_entity, north_entity, south_entity = self.actual_entities
        total = self._state_number(total_entity)
        north_dc = self._state_number(north_entity)
        south_dc = self._state_number(south_entity)
        total = max(0.0, total) if total is not None else None
        north, south = split_ac_power(total, north_dc, south_dc)
        return {"total": total, "north": north, "south": south, "method": "total_ac_x_dc_input_ratio"}

    def energy_for_local_date(self, date, roof: str = "total") -> float:
        field = {"north": "north_kwh", "south": "south_kwh", "total": "total_kwh"}[roof]
        return round(sum(getattr(point, field) for point in self.points if dt_util.as_local(point.start).date() == date), 3)

    def next_quarter_point(self, now_utc: datetime | None = None) -> SolarPoint | None:
        """Return the first Solar slot strictly after the current quarter."""
        if not self.points:
            return None
        reference = dt_util.as_utc(now_utc or dt_util.utcnow())
        index = next_future_slot_index(
            [point.start for point in self.points],
            reference,
            QUARTER_MINUTES,
        )
        return self.points[index] if index is not None else None

    @property
    def age_minutes(self) -> float | None:
        if self.last_successful_update is None:
            return None
        return round(max(0.0, (dt_util.utcnow() - self.last_successful_update).total_seconds()) / 60.0, 1)

    @property
    def source_status(self) -> str:
        if self.last_successful_update is None:
            return "error" if self.last_error else "not_loaded"
        if (self.age_minutes or 0) >= 180 or not self.points:
            return "expired"
        if (
            self.last_error
            or (self.age_minutes or 0) >= 90
            or len(self.points) < FORECAST_SLOTS
        ):
            return "stale"
        return "ok"
