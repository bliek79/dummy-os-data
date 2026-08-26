"""Degree days and heat-history shadow layer for Dummy OS Data."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .weather import DummyOSWeatherCoordinator

BASE_TEMPERATURE_C = 18.0
MIN_VALID_HOURS = 18
MAX_HISTORY_DAYS = 400
STORAGE_VERSION = 1
STORAGE_KEY = "dummy_os_data.degree_days_heat_history"

REFERENCE_ENTITIES = {
    "reference_temperature_c": "sensor.average_temperature_degree_days_calc",
    "reference_degree_days": "sensor.degree_days",
    "reference_weighted_degree_days": "sensor.weighted_degree_days",
    "reference_gas_per_degree_day": "sensor.gas_per_degree_day_calc",
    "reference_gas_per_weighted_degree_day": "sensor.gas_per_weighted_degree_day_calc",
}

HEAT_ENTITIES = {
    "gas_total_m3": "sensor.gas_volume_today",
    "solar_boiler_thermal_kwh": "sensor.boiler_charge_energy_today",
    "solar_boiler_gas_savings_m3": "sensor.boiler_gas_savings_today",
    "boiler_element_electric_kwh": "sensor.boiler_element_energy_today",
    "boiler_element_gas_equivalent_m3": "sensor.boiler_element_gas_equivalent_today",
    "total_heat_energy_kwh": "sensor.total_heat_energy_today",
    "total_heat_equivalent_m3": "sensor.total_heat_volume_today",
    "space_heating_equivalent_m3": "sensor.net_heat_volume_today",
    "boiler_energy_content_kwh": "sensor.boiler_energy_content",
}


class DummyOSDegreeDaysCoordinator:
    """Collect hourly Open-Meteo actuals and finalize one record per local day."""

    def __init__(self, hass: HomeAssistant, weather: DummyOSWeatherCoordinator) -> None:
        self.hass = hass
        self.weather = weather
        self.store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.samples: list[dict[str, Any]] = []
        self.records: list[dict[str, Any]] = []
        self.listeners: list[callback] = []
        self._unsubs: list[Any] = []

    async def async_setup(self) -> None:
        """Load stored history and start collection."""
        stored = await self.store.async_load() or {}
        self.samples = stored.get("samples", [])
        self.records = stored.get("records", [])
        self._prune()
        self._record_weather_sample()
        self._unsubs.append(self.weather.async_add_listener(self._weather_updated))
        self._unsubs.append(
            async_track_time_change(
                self.hass,
                self._async_finalize_day,
                hour=23,
                minute=59,
                second=50,
            )
        )
        self._publish_states()
        await self._async_save()

    async def async_shutdown(self) -> None:
        """Stop listeners and persist history."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self._async_save()

    def async_add_listener(self, listener: callback) -> callback:
        """Register an entity update listener."""
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
    def _weather_updated(self) -> None:
        self._record_weather_sample()
        self._publish_states()
        self.hass.async_create_task(self._async_save())
        self._notify()

    def _record_weather_sample(self) -> None:
        """Store at most one actual Open-Meteo temperature sample per local hour."""
        try:
            temperature = float(self.weather.current.get("temperature_2m"))
        except (TypeError, ValueError):
            return
        if not -30.0 < temperature < 50.0:
            return

        now_local = dt_util.as_local(dt_util.utcnow())
        hour_key = now_local.strftime("%Y-%m-%dT%H")
        sample = {
            "hour": hour_key,
            "timestamp": dt_util.as_utc(now_local).isoformat(),
            "date": now_local.date().isoformat(),
            "temperature_c": round(temperature, 2),
            "source": "open_meteo_current",
        }
        self.samples = [item for item in self.samples if item.get("hour") != hour_key]
        self.samples.append(sample)
        self._prune()

    async def _async_finalize_day(self, now: datetime) -> None:
        """Freeze the current local calendar day before daily utility meters reset."""
        local_now = dt_util.as_local(now)
        date_string = local_now.date().isoformat()
        record = self._build_record(date_string)
        self.records = [item for item in self.records if item.get("date") != date_string]
        self.records.append(record)
        self._prune()
        self._publish_states()
        await self._async_save()
        self._notify()

    def _build_record(self, date_string: str) -> dict[str, Any]:
        day_samples = [item for item in self.samples if item.get("date") == date_string]
        by_hour: dict[str, float] = {}
        for item in day_samples:
            try:
                by_hour[str(item["hour"])] = float(item["temperature_c"])
            except (KeyError, TypeError, ValueError):
                continue

        values = list(by_hour.values())
        sample_hours = len(values)
        coverage_percent = round(min(sample_hours / 24.0, 1.0) * 100.0, 1)
        valid = sample_hours >= MIN_VALID_HOURS
        average_temperature = round(sum(values) / sample_hours, 2) if values else None
        degree_days = (
            round(max(BASE_TEMPERATURE_C - average_temperature, 0.0), 2)
            if average_temperature is not None
            else None
        )
        month = int(date_string[5:7])
        factor = self.season_factor(month)
        weighted_degree_days = round(degree_days * factor, 2) if degree_days is not None else None

        record: dict[str, Any] = {
            "date": date_string,
            "valid": valid,
            "source": "dummy_os_weather_open_meteo_actual",
            "base_temperature_c": BASE_TEMPERATURE_C,
            "sample_hours": sample_hours,
            "coverage_percent": coverage_percent,
            "average_temperature_c": average_temperature,
            "degree_days": degree_days,
            "season_factor": factor,
            "weighted_degree_days": weighted_degree_days,
            "tapwater_m3": 0.65,
            "tapwater_source": "estimated_fixed_0_65_m3",
            "tapwater_quality": "estimated",
        }

        for key, entity_id in REFERENCE_ENTITIES.items():
            record[key] = self._state_float(entity_id)
        for key, entity_id in HEAT_ENTITIES.items():
            record[key] = self._state_float(entity_id)

        if degree_days and record.get("gas_total_m3") is not None:
            record["gas_per_degree_day_m3"] = round(record["gas_total_m3"] / degree_days, 3)
        else:
            record["gas_per_degree_day_m3"] = None
        if weighted_degree_days and record.get("gas_total_m3") is not None:
            record["gas_per_weighted_degree_day_m3"] = round(
                record["gas_total_m3"] / weighted_degree_days, 3
            )
        else:
            record["gas_per_weighted_degree_day_m3"] = None

        reference_dd = record.get("reference_degree_days")
        reference_wdd = record.get("reference_weighted_degree_days")
        record["degree_days_difference"] = (
            round(degree_days - reference_dd, 2)
            if degree_days is not None and reference_dd is not None
            else None
        )
        record["weighted_degree_days_difference"] = (
            round(weighted_degree_days - reference_wdd, 2)
            if weighted_degree_days is not None and reference_wdd is not None
            else None
        )
        return record

    @staticmethod
    def season_factor(month: int) -> float:
        """Match the legacy package weighting exactly."""
        if month in (11, 12, 1, 2):
            return 1.1
        if month in (3, 10):
            return 1.0
        return 0.8

    def _state_float(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in {"unknown", "unavailable", "none", "None", ""}:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    @property
    def last_record(self) -> dict[str, Any] | None:
        """Return the newest completed-day record."""
        if not self.records:
            return None
        return max(self.records, key=lambda item: str(item.get("date", "")))

    @property
    def history_days(self) -> int:
        """Return number of completed stored days."""
        return len({str(item.get("date")) for item in self.records if item.get("date")})

    @property
    def status(self) -> str:
        """Return collection status."""
        if self.weather.source_status in {"error", "not_loaded", "expired"}:
            return "source_unavailable"
        if not self.records:
            return "collecting"
        if not bool(self.last_record and self.last_record.get("valid")):
            return "partial_history"
        return "ok"

    def _publish_states(self) -> None:
        """Publish compact shadow sensors for dashboards, Recorder and Sheets export."""
        record = self.last_record or {}

        def set_sensor(entity_id: str, value: Any, friendly_name: str, unit: str | None = None, icon: str | None = None, extra: dict[str, Any] | None = None) -> None:
            attrs: dict[str, Any] = {"friendly_name": friendly_name}
            if unit is not None:
                attrs["unit_of_measurement"] = unit
            if icon is not None:
                attrs["icon"] = icon
            if extra:
                attrs.update(extra)
            state = "unknown" if value is None else value
            self.hass.states.async_set(entity_id, state, attrs)

        set_sensor("sensor.do_degree_days_status", self.status, "Dummy OS Degree Days Status", icon="mdi:database-check-outline")
        set_sensor("sensor.do_degree_days_history_days", self.history_days, "Dummy OS Degree Days History Days", "d", "mdi:calendar-clock-outline")
        set_sensor("sensor.do_degree_days_temperature_daily", record.get("average_temperature_c"), "Dummy OS Degree Days Daily Temperature", "°C", "mdi:thermometer-lines")
        set_sensor("sensor.do_degree_days_daily", record.get("degree_days"), "Dummy OS Degree Days Daily", "dd", "mdi:weather-cloudy-clock")
        set_sensor("sensor.do_weighted_degree_days_daily", record.get("weighted_degree_days"), "Dummy OS Weighted Degree Days Daily", "wdd", "mdi:chart-line")
        set_sensor("sensor.do_degree_days_reference_daily", record.get("reference_degree_days"), "Dummy OS Degree Days Reference Daily", "dd", "mdi:compare")
        set_sensor("sensor.do_weighted_degree_days_reference_daily", record.get("reference_weighted_degree_days"), "Dummy OS Weighted Degree Days Reference Daily", "wdd", "mdi:compare-horizontal")
        set_sensor("sensor.do_degree_days_difference", record.get("degree_days_difference"), "Dummy OS Degree Days Difference", "dd", "mdi:delta")
        set_sensor("sensor.do_weighted_degree_days_difference", record.get("weighted_degree_days_difference"), "Dummy OS Weighted Degree Days Difference", "wdd", "mdi:delta")
        set_sensor(
            "sensor.do_heat_degree_days_last_day",
            record.get("date"),
            "Dummy OS Heat Degree Days Last Day",
            icon="mdi:home-thermometer-outline",
            extra={
                "data_type": "completed_day_snapshot",
                "storage_limit_days": MAX_HISTORY_DAYS,
                "minimum_valid_hours": MIN_VALID_HOURS,
                **record,
            },
        )

    def _prune(self) -> None:
        cutoff_date = (dt_util.as_local(dt_util.utcnow()).date() - timedelta(days=MAX_HISTORY_DAYS)).isoformat()
        self.samples = [item for item in self.samples if str(item.get("date", "")) >= cutoff_date]
        self.records = [item for item in self.records if str(item.get("date", "")) >= cutoff_date]

    async def _async_save(self) -> None:
        await self.store.async_save({"samples": self.samples, "records": self.records})
