"""Historical quarter-hour foundation for Dummy OS Home Forecast."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CANONICAL_HOME_POWER_ENTITY,
    ENERGY_EVALUATION_SCHEMA_VERSION,
    ENERGY_STORE_SCHEMA_VERSION,
    MAX_HISTORY_DAYS,
    MIN_VALID_COVERAGE,
    PROFILE_NORMAL,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .energy_store import normalize_energy_store_payload
from .evaluation import calculate_metrics
from .forecast import ForecastSlot, HomeBaselineForecast
from .weather import DummyOSWeatherCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class QuarterResult:
    """Completed quarter-hour measurement."""

    start: datetime
    end: datetime
    energy_kwh: float | None
    coverage: float
    profile: str
    valid: bool


class DummyOSHomeDataCoordinator:
    """Collect Home history and host shared Dummy OS Data modules."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.profile = PROFILE_NORMAL
        self.records: list[dict[str, Any]] = []
        self.forecast_snapshots: dict[str, dict[str, Any]] = {}
        self.evaluations: list[dict[str, Any]] = []
        self.last_quarter: QuarterResult | None = None
        self.listeners: list[callback] = []
        self.weather = DummyOSWeatherCoordinator(hass)

        self._quarter_start: datetime | None = None
        self._last_sample_time: datetime | None = None
        self._last_power_w: float | None = None
        self._energy_ws: float = 0.0
        self._covered_seconds: float = 0.0
        self._quarter_profile: str = PROFILE_NORMAL
        self._profile_changed_in_quarter: bool = False
        self._unsubs: list[Any] = []

    @property
    def source_entity(self) -> str:
        """Return the canonical internal Home Power source."""
        return CANONICAL_HOME_POWER_ENTITY

    @property
    def source_state(self) -> State | None:
        """Return current source state."""
        return self.hass.states.get(self.source_entity)

    async def async_setup(self) -> None:
        """Load storage and start Home and Weather listeners."""
        stored = normalize_energy_store_payload(
            await self.store.async_load(),
            current_schema_version=ENERGY_STORE_SCHEMA_VERSION,
            default_profile=PROFILE_NORMAL,
        )
        self.profile = stored.get("profile", PROFILE_NORMAL)
        self.records = stored.get("records", [])
        self.forecast_snapshots = stored.get("forecast_snapshots", {})
        self.evaluations = stored.get("evaluations", [])
        self._prune_records()
        self._prune_snapshots()
        self._prune_evaluations()

        now = dt_util.utcnow()
        self._start_new_quarter(now)
        self._set_initial_power(now)
        self._capture_next_quarter_forecast(now)
        await self._async_save()

        self._unsubs.append(
            async_track_state_change_event(
                self.hass,
                [self.source_entity],
                self._async_source_changed,
            )
        )
        self._unsubs.append(
            async_track_time_change(
                self.hass,
                self._async_quarter_boundary,
                minute=[0, 15, 30, 45],
                second=0,
            )
        )
        await self.weather.async_setup()

    async def async_shutdown(self) -> None:
        """Stop listeners and persist data."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self.weather.async_shutdown()
        await self._async_save()

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

    @callback
    def _async_source_changed(self, event: Event[EventStateChangedData]) -> None:
        """Integrate live power without refreshing forecast/analysis entities."""
        now = dt_util.utcnow()
        self._integrate_until(now)
        new_state = event.data.get("new_state")
        self._last_power_w = self._power_from_state(new_state)
        self._last_sample_time = now

    @staticmethod
    def _quarter_boundary_utc(now: datetime) -> datetime:
        """Normalize scheduler callback time to the exact 15-minute UTC boundary."""
        now_utc = dt_util.as_utc(now)
        minute = (now_utc.minute // 15) * 15
        return now_utc.replace(minute=minute, second=0, microsecond=0)

    async def _async_quarter_boundary(self, now: datetime) -> None:
        """Finalize the completed quarter and freeze forecast for the new one."""
        boundary_utc = self._quarter_boundary_utc(now)
        self._integrate_until(boundary_utc)
        await self._finalize_quarter(boundary_utc)
        self._start_new_quarter(boundary_utc)
        self._last_power_w = self._power_from_state(self.source_state)
        self._last_sample_time = boundary_utc
        if self._quarter_start is not None:
            self._capture_forecast_for_slot_start(
                self._quarter_start,
                captured_at=boundary_utc,
            )
        await self._async_save()
        self._notify()

    def _start_new_quarter(self, now_utc: datetime) -> None:
        local = dt_util.as_local(now_utc)
        minute = (local.minute // 15) * 15
        local_start = local.replace(minute=minute, second=0, microsecond=0)
        self._quarter_start = dt_util.as_utc(local_start)
        self._energy_ws = 0.0
        self._covered_seconds = 0.0
        self._quarter_profile = self.profile
        self._profile_changed_in_quarter = False
        self._last_sample_time = now_utc

    def _set_initial_power(self, now_utc: datetime) -> None:
        self._last_power_w = self._power_from_state(self.source_state)
        self._last_sample_time = now_utc

    def _integrate_until(self, now_utc: datetime) -> None:
        """Integrate current power using zero-order hold."""
        if self._last_sample_time is None:
            self._last_sample_time = now_utc
            return
        seconds = max(0.0, (now_utc - self._last_sample_time).total_seconds())
        if self._last_power_w is not None and seconds > 0:
            self._energy_ws += self._last_power_w * seconds
            self._covered_seconds += seconds
        self._last_sample_time = now_utc

    async def _finalize_quarter(self, end_utc: datetime) -> None:
        if self._quarter_start is None:
            return
        duration = max(1.0, (end_utc - self._quarter_start).total_seconds())
        coverage = min(1.0, self._covered_seconds / duration)
        valid = coverage >= MIN_VALID_COVERAGE and not self._profile_changed_in_quarter
        energy_kwh = self._energy_ws / 3_600_000 if valid else None
        result = QuarterResult(
            start=self._quarter_start,
            end=end_utc,
            energy_kwh=round(energy_kwh, 6) if energy_kwh is not None else None,
            coverage=round(coverage, 4),
            profile=self._quarter_profile if not self._profile_changed_in_quarter else "mixed",
            valid=valid,
        )
        self.last_quarter = result
        self.records.append(
            {
                "start": result.start.isoformat(),
                "end": result.end.isoformat(),
                "energy_kwh": result.energy_kwh,
                "coverage": result.coverage,
                "profile": result.profile,
                "valid": result.valid,
            }
        )
        self._evaluate_completed_quarter(result)
        self._prune_records()
        self._prune_evaluations()
        await self._async_save()

    def _capture_next_quarter_forecast(self, now_utc: datetime) -> None:
        """Capture the next complete quarter, useful during setup/profile changes."""
        slots = HomeBaselineForecast(self.records).build(self.profile, now=now_utc)
        if slots:
            self._store_forecast_snapshot(slots[0], captured_at=now_utc)

    def _capture_forecast_for_slot_start(self, slot_start_utc: datetime, captured_at: datetime) -> None:
        """Freeze a forecast for a quarter at the instant that quarter starts."""
        just_before = dt_util.as_utc(slot_start_utc) - timedelta(microseconds=1)
        slots = HomeBaselineForecast(self.records).build(self.profile, now=just_before)
        if not slots:
            return
        slot = slots[0]
        if slot.start != dt_util.as_utc(slot_start_utc):
            _LOGGER.warning(
                "Forecast snapshot timing mismatch: expected %s, got %s",
                dt_util.as_utc(slot_start_utc).isoformat(),
                slot.start.isoformat(),
            )
            return
        self._store_forecast_snapshot(slot, captured_at=captured_at)

    def _store_forecast_snapshot(self, slot: ForecastSlot, captured_at: datetime) -> None:
        """Store one compact pre-actual forecast snapshot."""
        if slot.energy_kwh is None:
            return
        key = slot.start.isoformat()
        self.forecast_snapshots[key] = {
            "start": slot.start.isoformat(),
            "end": slot.end.isoformat(),
            "profile": self.profile,
            "forecast_kwh": slot.energy_kwh,
            "sample_count": slot.sample_count,
            "source": slot.source,
            "confidence": slot.confidence,
            "model": "historical_baseline",
            "model_version": "0.4",
            "captured_at": dt_util.as_utc(captured_at).isoformat(),
        }
        self._prune_snapshots()

    def _evaluate_completed_quarter(self, result: QuarterResult) -> None:
        """Compare a valid completed quarter with the forecast captured beforehand."""
        if not result.valid or result.energy_kwh is None:
            return
        snapshot = self.forecast_snapshots.pop(result.start.isoformat(), None)
        if snapshot is None or snapshot.get("profile") != result.profile:
            return
        try:
            forecast_kwh = float(snapshot["forecast_kwh"])
            captured_at = datetime.fromisoformat(snapshot["captured_at"])
        except (KeyError, TypeError, ValueError):
            return
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=dt_util.UTC)
        captured_at = dt_util.as_utc(captured_at)
        if captured_at > dt_util.as_utc(result.start):
            _LOGGER.warning(
                "Ignoring late Energy forecast snapshot for %s: captured at %s",
                result.start.isoformat(),
                captured_at.isoformat(),
            )
            return
        error_kwh = forecast_kwh - result.energy_kwh
        self.evaluations.append(
            {
                "evaluation_schema_version": ENERGY_EVALUATION_SCHEMA_VERSION,
                "start": result.start.isoformat(),
                "end": result.end.isoformat(),
                "profile": result.profile,
                "forecast_kwh": round(forecast_kwh, 6),
                "forecast_captured_at": captured_at.isoformat(),
                "actual_kwh": result.energy_kwh,
                "actual_coverage": result.coverage,
                "error_kwh": round(error_kwh, 6),
                "absolute_error_kwh": round(abs(error_kwh), 6),
                "source": snapshot.get("source"),
                "confidence": snapshot.get("confidence"),
                "sample_count": snapshot.get("sample_count"),
                "model": snapshot.get("model"),
                "model_version": snapshot.get("model_version"),
            }
        )

    async def async_set_profile(self, profile: str) -> None:
        """Persist selected forecast profile."""
        if profile != self.profile:
            self._profile_changed_in_quarter = True
        self.profile = profile
        self._capture_next_quarter_forecast(dt_util.utcnow())
        await self._async_save()
        self._notify()

    async def _async_save(self) -> None:
        await self.store.async_save(
            {
                "energy_store_schema_version": ENERGY_STORE_SCHEMA_VERSION,
                "profile": self.profile,
                "records": self.records,
                "forecast_snapshots": self.forecast_snapshots,
                "evaluations": self.evaluations,
            }
        )

    def _prune_records(self) -> None:
        cutoff = dt_util.utcnow() - timedelta(days=MAX_HISTORY_DAYS)
        kept: list[dict[str, Any]] = []
        for record in self.records:
            try:
                start = datetime.fromisoformat(record["start"])
            except (KeyError, TypeError, ValueError):
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=dt_util.UTC)
            if start >= cutoff:
                kept.append(record)
        self.records = kept

    def _prune_snapshots(self) -> None:
        cutoff = dt_util.utcnow() - timedelta(days=4)
        kept: dict[str, dict[str, Any]] = {}
        for key, snapshot in self.forecast_snapshots.items():
            try:
                start = datetime.fromisoformat(snapshot["start"])
            except (KeyError, TypeError, ValueError):
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=dt_util.UTC)
            if start >= cutoff:
                kept[key] = snapshot
        self.forecast_snapshots = kept

    def _prune_evaluations(self) -> None:
        cutoff = dt_util.utcnow() - timedelta(days=MAX_HISTORY_DAYS)
        kept: list[dict[str, Any]] = []
        for item in self.evaluations:
            try:
                start = datetime.fromisoformat(item["start"])
            except (KeyError, TypeError, ValueError):
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=dt_util.UTC)
            if start >= cutoff:
                kept.append(item)
        self.evaluations = kept

    def evaluation_metrics(self, profile: str | None = None) -> dict[str, Any]:
        """Return aggregate forecast evaluation metrics."""
        return calculate_metrics(self.evaluations, profile)

    @staticmethod
    def _power_from_state(state: State | None) -> float | None:
        """Convert W/kW sensor state to watts."""
        if state is None or state.state in {"unknown", "unavailable", "none", ""}:
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        unit = state.attributes.get("unit_of_measurement")
        if unit == "kW":
            return value * 1000.0
        if unit == "W" or unit is None:
            return value
        _LOGGER.warning("Unsupported unit %s for %s; expected W or kW", unit, state.entity_id)
        return None

    @property
    def history_days(self) -> int:
        """Return number of local dates containing at least one valid quarter."""
        dates: set[str] = set()
        for record in self.records:
            if not record.get("valid"):
                continue
            try:
                start = datetime.fromisoformat(record["start"])
            except (KeyError, TypeError, ValueError):
                continue
            dates.add(dt_util.as_local(start).date().isoformat())
        return len(dates)

    @property
    def valid_quarters(self) -> int:
        """Return number of valid persisted quarters."""
        return sum(1 for record in self.records if record.get("valid"))

    @property
    def source_available(self) -> bool:
        """Return whether source currently yields a valid power value."""
        return self._power_from_state(self.source_state) is not None
