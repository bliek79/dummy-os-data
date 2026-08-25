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
    CONF_HOME_POWER_ENTITY,
    MAX_HISTORY_DAYS,
    MIN_VALID_COVERAGE,
    PROFILE_NORMAL,
    STORAGE_KEY,
    STORAGE_VERSION,
)

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
    """Collect and persist 15-minute home-consumption history."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.profile = PROFILE_NORMAL
        self.records: list[dict[str, Any]] = []
        self.last_quarter: QuarterResult | None = None
        self.listeners: list[callback] = []

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
        """Return configured source entity."""
        return self.entry.options.get(
            CONF_HOME_POWER_ENTITY,
            self.entry.data[CONF_HOME_POWER_ENTITY],
        )

    @property
    def source_state(self) -> State | None:
        """Return current source state."""
        return self.hass.states.get(self.source_entity)

    async def async_setup(self) -> None:
        """Load storage and start listeners."""
        stored = await self.store.async_load() or {}
        self.profile = stored.get("profile", PROFILE_NORMAL)
        self.records = stored.get("records", [])
        self._prune_records()

        now = dt_util.utcnow()
        self._start_new_quarter(now)
        self._set_initial_power(now)

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

    async def async_shutdown(self) -> None:
        """Stop listeners and persist data."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
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
        """Integrate power until source state change and refresh availability state."""
        now = dt_util.utcnow()
        self._integrate_until(now)
        new_state = event.data.get("new_state")
        self._last_power_w = self._power_from_state(new_state)
        self._last_sample_time = now
        self._notify()

    async def _async_quarter_boundary(self, now: datetime) -> None:
        """Finalize the just-completed local quarter."""
        now_utc = dt_util.as_utc(now)
        self._integrate_until(now_utc)
        await self._finalize_quarter(now_utc)
        self._start_new_quarter(now_utc)
        self._last_power_w = self._power_from_state(self.source_state)
        self._last_sample_time = now_utc
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
        self._prune_records()
        await self._async_save()

    async def async_set_profile(self, profile: str) -> None:
        """Persist selected forecast profile."""
        if profile != self.profile:
            self._profile_changed_in_quarter = True
        self.profile = profile
        await self._async_save()
        self._notify()

    async def _async_save(self) -> None:
        await self.store.async_save({"profile": self.profile, "records": self.records})

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
        _LOGGER.warning(
            "Unsupported unit %s for %s; expected W or kW",
            unit,
            state.entity_id,
        )
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
