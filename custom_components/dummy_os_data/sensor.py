"""Sensors for Dummy OS Forecast."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    FORECAST_SLOTS,
    NAME,
    PROFILE_LEARNING_OPTIONS,
    PROFILE_UNCLASSIFIED,
    QUARTER_MINUTES,
    VERSION,
)
from .coordinator import DummyOSHomeDataCoordinator
from .degree_days_sensor import build_degree_days_sensors
from .evaluation import (
    calculate_day_type_daypart_quality,
    calculate_day_type_quality,
    calculate_daypart_quality,
    calculate_hour_quality,
    calculate_metrics,
    calculate_peak_learning,
)
from .time_windows import calculate_time_windows
from .recency_weighting import calculate_recency_weighting
from .forecast import HomeBaselineForecast
from .planner_time_contract import build_time_contract, utc
from .planner_time_views import forecast_transport
from .planner_time_runtime import read_soc_bridge, subscribe_bridge_recovery
from .horizon_quality import calculate_horizon_quality
from .model_health import calculate_model_health_readiness
from .forecast_planner_contract import build_forecast_planner_contract
from .do_plan_input import build_do_plan_input_72h
from .do_plan_energy_need import build_do_plan_energy_need
from .do_plan_reserve_soc import build_do_plan_reserve_soc
from .do_plan_soc_contract_sensor import RAW_SOC_ENTITY, build_do_plan_soc_contract_sensors, get_do_plan_soc_contract_runtime
from .do_plan_preview_sensor import build_do_plan_preview_sensors
from .do_plan_72h_sensor import build_do_plan_72h_sensors
from .do_plan_grid_support_sensor import build_do_plan_grid_support_sensors
from .planner_hours import (
    aggregate_planner_hours,
    required_generated_slot_count,
)
from .home_input_sensor import build_home_input_sensors
from .solar_sensor import build_solar_sensors
from .weather import (
    OPEN_METEO_LATITUDE,
    OPEN_METEO_LONGITUDE,
    OPEN_METEO_MODEL,
    OPEN_METEO_TIMEZONE,
    POINT_FIELDS,
)

SUPPORTED_SOURCES = {"weekday_quarter", "day_type_quarter", "quarter_of_day"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Dummy OS Forecast sensors."""
    coordinator: DummyOSHomeDataCoordinator = entry.runtime_data
    async_add_entities(
        [
            *build_home_input_sensors(coordinator),
            DummyOSActualQuarterSensor(coordinator),
            DummyOSHistoryStatusSensor(coordinator),
            DummyOSHistoryDaysSensor(coordinator),
            DummyOSForecastModelSensor(coordinator),
            DummyOSHomeForecastSensor(coordinator),
            DummyOSHomeForecastTimelineSensor(coordinator),
            DummyOSEnergyForecastPlannerHoursSensor(coordinator),
            DummyOSEnergyForecastPlannerContractSensor(coordinator),
            DummyOSPlanInput72hSensor(coordinator),
            *build_do_plan_soc_contract_sensors(coordinator),
            DummyOSPlanEnergyNeedSensor(coordinator),
            DummyOSPlanReserveSOCSensor(coordinator),
            *build_do_plan_preview_sensors(coordinator),
            *build_do_plan_72h_sensors(coordinator),
            *build_do_plan_grid_support_sensors(coordinator),
            DummyOSHomeForecastNextQuarterSensor(coordinator),
            DummyOSHomeForecastCoverageSensor(coordinator),
            DummyOSHomeForecastConfidenceSensor(coordinator),
            DummyOSHomeForecastModelHealthSensor(coordinator),
            DummyOSHomeForecastAccuracySensor(coordinator),
            DummyOSHomeForecastMaeSensor(coordinator),
            DummyOSHomeForecastBiasSensor(coordinator),
            DummyOSHomeForecastEvaluationSamplesSensor(coordinator),
            DummyOSHomeForecastQualityByDaypartSensor(coordinator),
            DummyOSHomeForecastQualityByDayTypeSensor(coordinator),
            DummyOSHomeForecastQualityByDayTypeAndDaypartSensor(coordinator),
            DummyOSHomeForecastQualityByHourSensor(coordinator),
            DummyOSEnergyPeakLearningSensor(coordinator),
            DummyOSEnergyTimeWindowsSensor(coordinator),
            DummyOSEnergyRecencyWeightingSensor(coordinator),
            DummyOSWeatherCurrentSensor(coordinator, "temperature_2m", "Temperature", "°C", "mdi:thermometer", SensorDeviceClass.TEMPERATURE),
            DummyOSWeatherCurrentSensor(coordinator, "apparent_temperature", "Apparent Temperature", "°C", "mdi:thermometer-lines", SensorDeviceClass.TEMPERATURE),
            DummyOSWeatherCurrentSensor(coordinator, "relative_humidity_2m", "Relative Humidity", "%", "mdi:water-percent", SensorDeviceClass.HUMIDITY),
            DummyOSWeatherCurrentSensor(coordinator, "precipitation", "Precipitation", "mm", "mdi:weather-rainy"),
            DummyOSWeatherCurrentSensor(coordinator, "cloud_cover", "Cloud Cover", "%", "mdi:weather-cloudy"),
            DummyOSWeatherCurrentSensor(coordinator, "wind_speed_10m", "Wind Speed", "km/h", "mdi:weather-windy"),
            DummyOSWeatherCurrentSensor(coordinator, "wind_direction_10m", "Wind Direction", "°", "mdi:compass-outline"),
            DummyOSWeatherCurrentSensor(coordinator, "wind_gusts_10m", "Wind Gusts", "km/h", "mdi:weather-windy-variant"),
            DummyOSWeatherCurrentSensor(coordinator, "weather_code", "Weather Code", None, "mdi:weather-partly-cloudy"),
            DummyOSWeatherTimelineSensor(coordinator),
            DummyOSWeatherSourceStatusSensor(coordinator),
            DummyOSWeatherFreshnessSensor(coordinator),
            DummyOSWeatherLastUpdateSensor(coordinator),
            DummyOSWeatherModelSensor(coordinator),
            *build_solar_sensors(coordinator),
            *build_degree_days_sensors(coordinator),
        ]
    )


class DummyOSBaseSensor(SensorEntity):
    """Base Energy Forecast sensor."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        self.coordinator = coordinator
        self._remove_listener = None
        self._forecast_cache_key = None
        self._forecast_cache = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "main")},
            name=NAME,
            manufacturer="Dummy OS",
            model="Forecast Platform",
            sw_version=VERSION,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_listener = self.coordinator.async_add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def _profile_learnable(self) -> bool:
        return self.coordinator.profile in PROFILE_LEARNING_OPTIONS

    def _forecast(self):
        reference = dt_util.utcnow()
        contract = build_time_contract(reference)
        key = (self.coordinator.profile, len(self.coordinator.records), contract["window_id"])
        if key != self._forecast_cache_key:
            self._forecast_cache = HomeBaselineForecast(self.coordinator.records).build(
                self.coordinator.profile, now=reference, window_start=utc(contract["window_start"])
            )
            self._forecast_cache_key = key
        return self._forecast_cache or []


class DummyOSActualQuarterSensor(DummyOSBaseSensor):
    _attr_name = "DO Energy Actual Quarter"
    _attr_unique_id = "do_energy_actual_quarter"
    _attr_suggested_object_id = "do_energy_actual_quarter"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:home-lightning-bolt-outline"

    @property
    def native_value(self) -> float | None:
        result = self.coordinator.last_quarter
        return result.energy_kwh if result and result.measurement_valid else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self.coordinator.last_quarter
        if result is None:
            return {
                "resolution_minutes": 15,
                "source_entity": self.coordinator.source_entity,
                "profile": self.coordinator.profile,
                "status": "waiting_for_first_quarter",
            }
        return {
            "resolution_minutes": 15,
            "period_start": result.start.isoformat(),
            "period_end": result.end.isoformat(),
            "coverage": result.coverage,
            "measurement_valid": result.measurement_valid,
            "learning_valid": result.learning_valid,
            "learning_blocker": result.learning_blocker,
            "valid": result.valid,
            "source_entity": self.coordinator.source_entity,
            "profile": result.profile,
        }


class DummyOSHistoryStatusSensor(DummyOSBaseSensor):
    _attr_name = "DO Energy History Status"
    _attr_unique_id = "do_energy_history_status"
    _attr_suggested_object_id = "do_energy_history_status"
    _attr_icon = "mdi:database-check-outline"

    @property
    def native_value(self) -> str:
        if not self.coordinator.source_available:
            return "source_unavailable"
        if self.coordinator.valid_quarters == 0:
            return "collecting"
        return "ok"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        model = HomeBaselineForecast(self.coordinator.records)
        return {
            "source_entity": self.coordinator.source_entity,
            "source_available": self.coordinator.source_available,
            "valid_quarters": self.coordinator.valid_quarters,
            "history_days": self.coordinator.history_days,
            "profile": self.coordinator.profile,
            "storage_limit_days": 400,
            "profile_statistics": model.all_profile_statistics(),
        }


class DummyOSHistoryDaysSensor(DummyOSBaseSensor):
    _attr_name = "DO Energy History Days"
    _attr_unique_id = "do_energy_history_days"
    _attr_suggested_object_id = "do_energy_history_days"
    _attr_native_unit_of_measurement = "d"
    _attr_icon = "mdi:calendar-clock-outline"

    @property
    def native_value(self) -> int:
        return self.coordinator.history_days

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"valid_quarters": self.coordinator.valid_quarters, "resolution_minutes": 15}


class DummyOSForecastModelSensor(DummyOSBaseSensor):
    _attr_name = "DO Energy Forecast Model"
    _attr_unique_id = "do_energy_forecast_model"
    _attr_suggested_object_id = "do_energy_forecast_model"
    _attr_icon = "mdi:chart-timeline-variant-shimmer"

    @property
    def native_value(self) -> str:
        return "historical_baseline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        model = HomeBaselineForecast(self.coordinator.records)
        return {
            "model_version": "0.4",
            "forecast_active": self._profile_learnable,
            "evaluation_active": self._profile_learnable,
            "recency_weighting_active": self._profile_learnable,
            "day_type_active": self._profile_learnable,
            "dashboard_timeline_active": True,
            "resolution_minutes": 15,
            "horizon_hours": 72,
            "forecast_slots": FORECAST_SLOTS,
            "profile": self.coordinator.profile,
            "profile_statistics": model.profile_statistics(self.coordinator.profile),
        }


class DummyOSHomeForecastSensor(DummyOSBaseSensor):
    _attr_name = "DO Energy Forecast"
    _attr_unique_id = "do_energy_forecast"
    _attr_suggested_object_id = "do_energy_forecast"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:home-clock-outline"

    @property
    def native_value(self) -> float | None:
        values = [slot.energy_kwh for slot in self._forecast() if slot.energy_kwh is not None]
        return round(sum(values), 3) if values else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        slots = self._forecast()
        populated = sum(1 for slot in slots if slot.energy_kwh is not None)
        supported = sum(1 for slot in slots if slot.source in SUPPORTED_SOURCES)
        return {
            "status": "ok" if self._profile_learnable else "profile_unclassified",
            "profile": self.coordinator.profile,
            "model": "historical_baseline",
            "model_version": "0.4",
            "forecast_start": slots[0].start.isoformat() if slots else None,
            "resolution_minutes": 15,
            "horizon_hours": 72,
            "slot_count": len(slots),
            "populated_slots": populated,
            "supported_slots": supported,
            "coverage_percent": round(supported / len(slots) * 100, 1) if slots else 0.0,
            "average_confidence_percent": HomeBaselineForecast.average_confidence(slots),
            "timeline_entity": "sensor.do_energy_forecast_timeline",
        }


class DummyOSHomeForecastTimelineSensor(DummyOSBaseSensor):
    _attr_name = "DO Energy Forecast Timeline"
    _attr_unique_id = "do_energy_forecast_timeline"
    _attr_suggested_object_id = "do_energy_forecast_timeline"
    _attr_icon = "mdi:chart-line"
    _unrecorded_attributes = frozenset({"points"})

    @property
    def native_value(self) -> int:
        return sum(1 for slot in self._forecast() if slot.energy_kwh is not None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        slots = self._forecast()
        points = [[int(slot.start.timestamp() * 1000), slot.energy_kwh] for slot in slots if slot.energy_kwh is not None]
        return {
            "status": "ok" if self._profile_learnable else "profile_unclassified",
            "profile": self.coordinator.profile,
            "model": "historical_baseline",
            "model_version": "0.4",
            "resolution_minutes": 15,
            "horizon_hours": 72,
            "slot_count": len(slots),
            "point_count": len(points),
            "point_format": "[unix_ms, kwh]",
            "forecast_start": slots[0].start.isoformat() if slots else None,
            "forecast_end": slots[-1].end.isoformat() if slots else None,
            "recorder_points": "excluded",
            "points": points,
        }


def _planner_runtime_snapshot(
    coordinator: DummyOSHomeDataCoordinator,
    *,
    now: datetime | None = None,
    soc_percent: float | None = None,
) -> dict[str, Any]:
    """Capture time once before selecting all planner sources on the HA thread."""
    reference = utc(now or dt_util.utcnow())
    contract = build_time_contract(reference)
    return {
        "records": list(coordinator.records),
        "evaluations": list(coordinator.evaluations),
        "horizon_daily_stats": dict(coordinator.horizon_daily_stats),
        "profile": coordinator.profile,
        "source_available": coordinator.source_available,
        "solar_points": list(coordinator.solar.planner_points_for_window(contract)),
        "price_points": list(coordinator.prices.planner_points_for_window(contract, include_neighbours=True)),
        "solar_status": coordinator.solar.source_status,
        "prices_status": coordinator.prices.status,
        "prices_freshness": coordinator.prices.freshness,
        "now": reference,
        "soc_percent": soc_percent,
        "time_contract": contract,
    }


def _build_planner_hours_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    reference = snapshot["now"]
    contract = snapshot.get("time_contract") or build_time_contract(reference)
    profile = snapshot["profile"]
    slots = HomeBaselineForecast(snapshot["records"]).build(
        profile, now=reference, slot_count=FORECAST_SLOTS, window_start=utc(contract["window_start"])
    )
    result = forecast_transport(slots, profile=profile, contract=contract)
    if profile not in PROFILE_LEARNING_OPTIONS:
        result["status"] = "profile_unclassified"
    return result


def _build_model_health_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    profile = snapshot["profile"]
    records = snapshot["records"]
    evaluations = snapshot["evaluations"]
    slots = HomeBaselineForecast(records).build(profile, now=snapshot["now"])
    supported = sum(1 for slot in slots if slot.source in SUPPORTED_SOURCES)
    coverage = round(supported / len(slots) * 100, 1) if slots else None
    confidence = HomeBaselineForecast.average_confidence(slots)
    metrics = calculate_metrics(evaluations, profile)
    horizon_quality = calculate_horizon_quality(snapshot["horizon_daily_stats"], profile)
    day_type_daypart_quality = calculate_day_type_daypart_quality(
        evaluations, records, profile, dt_util.as_local
    )
    hour_quality = calculate_hour_quality(evaluations, records, profile, dt_util.as_local)
    return calculate_model_health_readiness(
        records=records,
        profile=profile,
        source_available=snapshot["source_available"],
        forecast_coverage_percent=coverage,
        average_confidence_percent=confidence,
        evaluation_metrics=metrics,
        horizon_quality=horizon_quality,
        day_type_daypart_quality=day_type_daypart_quality,
        hour_quality=hour_quality,
        localize=dt_util.as_local,
    )


def _build_public_forecast_from_snapshot(snapshot: dict[str, Any]) -> list[Any]:
    """Build the public 72-hour Energy forecast outside the HA main thread."""
    return HomeBaselineForecast(snapshot["records"]).build(
        snapshot["profile"], now=snapshot["now"]
    )


def _build_contract_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return build_forecast_planner_contract(
        planner_hours=_build_planner_hours_from_snapshot(snapshot),
        model_health=_build_model_health_from_snapshot(snapshot),
    )


def _build_plan_input_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return build_do_plan_input_72h(
        contract=_build_contract_from_snapshot(snapshot),
        solar_points=snapshot["solar_points"],
        price_points=snapshot["price_points"],
        solar_status=snapshot["solar_status"],
        prices_status=snapshot["prices_status"],
        prices_freshness=snapshot["prices_freshness"],
    )


def _build_energy_need_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    result = build_do_plan_energy_need(
        input_result=_build_plan_input_from_snapshot(snapshot),
        soc_percent=snapshot.get("soc_percent"),
        battery_capacity_kwh=7.2,
        min_soc_percent=5.0,
        safety_reserve_percent=7.0,
        now=snapshot["now"],
    )
    result["soc_bridge"] = snapshot.get("soc_bridge")
    if snapshot.get("soc_bridge") is not None:
        result["measured_soc_percent"] = snapshot["soc_bridge"].get("measured_soc_percent")
        result["planner_start_soc_percent"] = snapshot["soc_bridge"].get("planner_start_soc_percent")
        result["soc_time_basis"] = "planner_window_start_estimate"
    result["soc_source_entity"] = snapshot.get("soc_source_entity", "sensor.do_plan_soc_contract")
    result["source_layer_status"] = "central_soc_contract_v1"
    return result


def _build_reserve_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    energy_need_result = _build_energy_need_from_snapshot(snapshot)
    result = build_do_plan_reserve_soc(energy_need_result=energy_need_result)
    result["energy_need_entity"] = "sensor.do_plan_energy_need"
    result["soc_source_entity"] = energy_need_result.get("soc_source_entity")
    result["source_layer_status"] = energy_need_result.get("source_layer_status")
    return result


def _build_planner_hours_result(
    coordinator: DummyOSHomeDataCoordinator,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Backward-compatible synchronous helper for tests/internal callers."""
    return _build_planner_hours_from_snapshot(
        _planner_runtime_snapshot(coordinator, now=now)
    )


def _build_do_plan_input_result(coordinator: DummyOSHomeDataCoordinator) -> dict[str, Any]:
    """Backward-compatible synchronous helper for tests/internal callers."""
    return _build_plan_input_from_snapshot(_planner_runtime_snapshot(coordinator))


class DummyOSAsyncPlannerResultSensor(DummyOSBaseSensor):
    """Executor-backed cached result sensor for expensive planner/model calculations."""

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        super().__init__(coordinator)
        self._cached_result: dict[str, Any] | None = None
        self._refresh_task = None
        self._refresh_pending = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._schedule_refresh()

    async def async_will_remove_from_hass(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self._schedule_refresh()

    @callback
    def _schedule_refresh(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_pending = True
            return
        self._refresh_task = self.hass.async_create_task(self._async_refresh_result())

    async def _async_refresh_result(self) -> None:
        while True:
            self._refresh_pending = False
            snapshot = self._snapshot()
            result = await self.hass.async_add_executor_job(
                self._calculate_result, snapshot
            )
            contract = result.get("time_contract")
            if contract and contract["window_id"] != build_time_contract(dt_util.utcnow())["window_id"]:
                result = {**result, "status": "stale", "valid": False,
                          "reason": "planner_window_elapsed", "blockers": ["planner_window_elapsed"],
                          "time_alignment_current": False}
                if snapshot.get("time_contract") is not None:
                    self._refresh_pending = True
            else:
                result["time_alignment_current"] = True
            self._cached_result = result
            self.async_write_ha_state()
            if not self._refresh_pending:
                return

    def _snapshot(self) -> dict[str, Any]:
        return _planner_runtime_snapshot(self.coordinator)

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _initial_result(self) -> dict[str, Any]:
        return {
            "status": "initializing",
            "blockers": ["planner_calculation_pending"],
        }

    def _result(self) -> dict[str, Any]:
        return self._cached_result or self._initial_result()


class DummyOSEnergyForecastPlannerHoursSensor(DummyOSAsyncPlannerResultSensor):
    """Step 14 exact 72 complete planner-hour forecast interface."""

    _attr_name = "DO Energy Forecast Planner Hours"
    _attr_unique_id = "do_energy_forecast_planner_hours"
    _attr_suggested_object_id = "do_energy_forecast_planner_hours"
    _attr_icon = "mdi:clock-outline"
    _unrecorded_attributes = frozenset({"hours"})

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return _build_planner_hours_from_snapshot(snapshot)

    def _initial_result(self) -> dict[str, Any]:
        return {
            "status": "initializing",
            "valid_hour_count": 0,
            "hours": [],
            "blockers": ["planner_calculation_pending"],
        }

    @property
    def native_value(self) -> int:
        return int(self._result().get("valid_hour_count", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._result())


class DummyOSEnergyForecastPlannerContractSensor(DummyOSAsyncPlannerResultSensor):
    """Stable Step 15 Forecast -> Planner contract."""

    _attr_name = "DO Energy Forecast Planner Contract"
    _attr_unique_id = "do_energy_forecast_planner_contract"
    _attr_suggested_object_id = "do_energy_forecast_planner_contract"
    _attr_icon = "mdi:connection"
    _unrecorded_attributes = frozenset({"hours"})

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return _build_contract_from_snapshot(snapshot)

    @property
    def native_value(self) -> str:
        return str(self._result().get("status", "initializing"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._result())


class DummyOSPlanInput72hSensor(DummyOSAsyncPlannerResultSensor):
    """Observer-only exact 72-hour input matrix for the new internal planner."""

    _attr_name = "DO Plan Input 72h"
    _attr_unique_id = "do_plan_input_72h"
    _attr_suggested_object_id = "do_plan_input_72h"
    _attr_icon = "mdi:table-clock"
    _unrecorded_attributes = frozenset({"rows", "slots", "source_time_audit"})

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        super().__init__(coordinator)
        self._remove_solar_listener = None
        self._remove_prices_listener = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_solar_listener = self.coordinator.solar.async_add_listener(self._handle_update)
        self._remove_prices_listener = self.coordinator.prices.async_add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_solar_listener is not None:
            self._remove_solar_listener()
        if self._remove_prices_listener is not None:
            self._remove_prices_listener()
        await super().async_will_remove_from_hass()

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return _build_plan_input_from_snapshot(snapshot)

    @property
    def native_value(self) -> str:
        return str(self._result().get("status", "initializing"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._result())


class DummyOSPlanEnergyNeedSensor(DummyOSPlanInput72hSensor):
    """Observer-only battery energy need until usable solar returns."""

    _attr_name = "DO Plan Energy Need"
    _attr_unique_id = "do_plan_energy_need"
    _attr_suggested_object_id = "do_plan_energy_need"
    _attr_icon = "mdi:battery-clock-outline"

    SOC_ENTITY = "sensor.do_plan_soc_contract"
    BATTERY_CAPACITY_KWH = 7.2
    MIN_SOC_PERCENT = 5.0
    SAFETY_RESERVE_PERCENT = 7.0

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        super().__init__(coordinator)
        self._remove_soc_listener = None
        self._remove_bridge_recovery = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_bridge_recovery = subscribe_bridge_recovery(self)
        self._remove_soc_listener = async_track_state_change_event(
            self.coordinator.hass,
            [RAW_SOC_ENTITY],
            self._handle_soc_update,
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_bridge_recovery is not None:
            self._remove_bridge_recovery()
        if self._remove_soc_listener is not None:
            self._remove_soc_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_soc_update(self, _event) -> None:
        self._schedule_refresh()

    def _soc_contract(self) -> dict[str, Any]:
        return get_do_plan_soc_contract_runtime(self.coordinator).result()

    def _soc_percent(self) -> float | None:
        contract = self._soc_contract()
        if contract.get("status") != "ready" or contract.get("valid") is not True:
            return None
        try:
            value = float(contract.get("soc_percent"))
        except (TypeError, ValueError):
            return None
        return value if 0.0 <= value <= 100.0 else None

    def _snapshot(self) -> dict[str, Any]:
        reference = dt_util.utcnow()
        contract = get_do_plan_soc_contract_runtime(self.coordinator).result(now=reference)
        snapshot = _planner_runtime_snapshot(self.coordinator, now=reference, soc_percent=contract.get("soc_percent"))
        bridge = read_soc_bridge(self.coordinator, snapshot, contract)
        self._last_soc_bridge_valid = bridge["valid"]
        snapshot["soc_bridge"] = bridge
        snapshot["soc_percent"] = bridge.get("planner_start_soc_percent") if bridge["valid"] else None
        snapshot["soc_source_entity"] = "runtime:do_plan_soc_contract_v1"
        snapshot["soc_contract_entity"] = self.SOC_ENTITY
        snapshot["soc_contract_status"] = contract.get("status")
        snapshot["soc_contract_valid"] = contract.get("valid")
        snapshot["soc_raw_source_entity"] = contract.get("source_entity")
        return snapshot

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return _build_energy_need_from_snapshot(snapshot)


class DummyOSPlanReserveSOCSensor(DummyOSPlanEnergyNeedSensor):
    """Observer-only protected reserve-SOC position derived from Step 2."""

    _attr_name = "DO Plan Reserve SOC"
    _attr_unique_id = "do_plan_reserve_soc"
    _attr_suggested_object_id = "do_plan_reserve_soc"
    _attr_icon = "mdi:battery-lock-outline"

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return _build_reserve_from_snapshot(snapshot)


class DummyOSHomeForecastNextQuarterSensor(DummyOSAsyncPlannerResultSensor):
    _attr_name = "DO Energy Forecast Next Quarter"
    _attr_unique_id = "do_energy_forecast_next_quarter"
    _attr_suggested_object_id = "do_energy_forecast_next_quarter"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:clock-fast"

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        slots = _build_public_forecast_from_snapshot(snapshot)
        if not slots:
            return {"value": None, "status": "unavailable", "profile": snapshot["profile"]}
        slot = slots[0]
        learnable = snapshot["profile"] in PROFILE_LEARNING_OPTIONS
        return {
            "value": slot.energy_kwh,
            "status": "ok" if learnable and slot.energy_kwh is not None else ("profile_unclassified" if not learnable else "unavailable"),
            "period_start": slot.start.isoformat(),
            "period_end": slot.end.isoformat(),
            "profile": snapshot["profile"],
            "sample_count": slot.sample_count,
            "source": slot.source,
            "confidence": slot.confidence,
        }

    def _initial_result(self) -> dict[str, Any]:
        return {"value": None, "status": "initializing", "profile": self.coordinator.profile, "blockers": ["forecast_calculation_pending"]}

    @property
    def native_value(self) -> float | None:
        return self._result().get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = dict(self._result())
        result.pop("value", None)
        return result


class DummyOSHomeForecastCoverageSensor(DummyOSAsyncPlannerResultSensor):
    _attr_name = "DO Energy Forecast Coverage"
    _attr_unique_id = "do_energy_forecast_coverage"
    _attr_suggested_object_id = "do_energy_forecast_coverage"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:chart-donut"

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        slots = _build_public_forecast_from_snapshot(snapshot)
        sources: dict[str, int] = {}
        for slot in slots:
            sources[slot.source] = sources.get(slot.source, 0) + 1
        populated = sum(1 for slot in slots if slot.energy_kwh is not None)
        supported = sum(1 for slot in slots if slot.source in SUPPORTED_SOURCES)
        coverage = round(supported / len(slots) * 100, 1) if slots else 0.0
        return {
            "value": coverage,
            "status": "ok" if snapshot["profile"] in PROFILE_LEARNING_OPTIONS else "profile_unclassified",
            "profile": snapshot["profile"],
            "slot_count": len(slots),
            "populated_slots": populated,
            "supported_slots": supported,
            "source_distribution": sources,
        }

    def _initial_result(self) -> dict[str, Any]:
        return {
            "value": 0.0,
            "status": "initializing",
            "profile": self.coordinator.profile,
            "slot_count": 0,
            "populated_slots": 0,
            "supported_slots": 0,
            "source_distribution": {},
            "blockers": ["forecast_calculation_pending"],
        }

    @property
    def native_value(self) -> float:
        return float(self._result().get("value", 0.0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = dict(self._result())
        result.pop("value", None)
        return result


class DummyOSHomeForecastConfidenceSensor(DummyOSAsyncPlannerResultSensor):
    _attr_name = "DO Energy Forecast Confidence"
    _attr_unique_id = "do_energy_forecast_confidence"
    _attr_suggested_object_id = "do_energy_forecast_confidence"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:shield-check-outline"

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        slots = _build_public_forecast_from_snapshot(snapshot)
        return {
            "value": HomeBaselineForecast.average_confidence(slots),
            "status": "ok" if snapshot["profile"] in PROFILE_LEARNING_OPTIONS else "profile_unclassified",
            "profile": snapshot["profile"],
            "slot_count": len(slots),
            "model_version": "0.4",
            "confidence_basis": "historical_source_and_sample_support",
        }

    def _initial_result(self) -> dict[str, Any]:
        return {"value": None, "status": "initializing", "profile": self.coordinator.profile, "slot_count": 0, "model_version": "0.4", "confidence_basis": "historical_source_and_sample_support", "blockers": ["forecast_calculation_pending"]}

    @property
    def native_value(self) -> float | None:
        return self._result().get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = dict(self._result())
        result.pop("value", None)
        return result


def _build_model_health_result(
    coordinator: DummyOSHomeDataCoordinator,
    slots: list[Any],
) -> dict[str, Any]:
    """Backward-compatible synchronous helper for tests/internal callers."""
    snapshot = _planner_runtime_snapshot(coordinator)
    snapshot["now"] = slots[0].start if slots else snapshot["now"]
    return _build_model_health_from_snapshot(snapshot)


class DummyOSHomeForecastModelHealthSensor(DummyOSAsyncPlannerResultSensor):
    _attr_name = "DO Energy Forecast Model Health"
    _attr_unique_id = "do_energy_forecast_model_health"
    _attr_suggested_object_id = "do_energy_forecast_model_health"
    _attr_icon = "mdi:heart-pulse"

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return _build_model_health_from_snapshot(snapshot)

    def _initial_result(self) -> dict[str, Any]:
        return {
            "status": "initializing",
            "readiness_status": "initializing",
            "blockers": ["model_health_calculation_pending"],
        }

    @property
    def native_value(self) -> str:
        if not self._profile_learnable:
            return "profile_unclassified"
        return str(self._result().get("readiness_status", "initializing"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._result())


class DummyOSEvaluationBaseSensor(DummyOSBaseSensor):
    """Executor-backed shared evaluation metrics cache."""

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        super().__init__(coordinator)
        self._cached_metrics: dict[str, Any] | None = None
        self._refresh_task = None
        self._refresh_pending = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._schedule_refresh()

    async def async_will_remove_from_hass(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self._schedule_refresh()

    @callback
    def _schedule_refresh(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_pending = True
            return
        self._refresh_task = self.hass.async_create_task(self._async_refresh_metrics())

    async def _async_refresh_metrics(self) -> None:
        while True:
            self._refresh_pending = False
            evaluations = list(self.coordinator.evaluations)
            profile = self.coordinator.profile
            self._cached_metrics = await self.hass.async_add_executor_job(
                calculate_metrics, evaluations, profile
            )
            self.async_write_ha_state()
            if not self._refresh_pending:
                return

    @property
    def _metrics(self) -> dict[str, Any]:
        return self._cached_metrics or {
            "samples": 0,
            "accuracy_percent": None,
            "mae_kwh": None,
            "bias_kwh": None,
            "actual_total_kwh": 0.0,
            "forecast_total_kwh": 0.0,
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        metrics = self._metrics
        return {"profile": self.coordinator.profile, "samples": metrics["samples"], "actual_total_kwh": metrics["actual_total_kwh"], "forecast_total_kwh": metrics["forecast_total_kwh"], "evaluation_scope": "active_profile", "resolution_minutes": 15}


class DummyOSHomeForecastAccuracySensor(DummyOSEvaluationBaseSensor):
    _attr_name = "DO Energy Forecast Accuracy"
    _attr_unique_id = "do_energy_forecast_accuracy"
    _attr_suggested_object_id = "do_energy_forecast_accuracy"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:bullseye-arrow"

    @property
    def native_value(self) -> float | None:
        return self._metrics["accuracy_percent"]


class DummyOSHomeForecastMaeSensor(DummyOSEvaluationBaseSensor):
    _attr_name = "DO Energy Forecast MAE"
    _attr_unique_id = "do_energy_forecast_mae"
    _attr_suggested_object_id = "do_energy_forecast_mae"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    @property
    def native_value(self) -> float | None:
        return self._metrics["mae_kwh"]


class DummyOSHomeForecastBiasSensor(DummyOSEvaluationBaseSensor):
    _attr_name = "DO Energy Forecast Bias"
    _attr_unique_id = "do_energy_forecast_bias"
    _attr_suggested_object_id = "do_energy_forecast_bias"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:scale-balance"

    @property
    def native_value(self) -> float | None:
        return self._metrics["bias_kwh"]


class DummyOSHomeForecastEvaluationSamplesSensor(DummyOSEvaluationBaseSensor):
    _attr_name = "DO Energy Forecast Evaluation Samples"
    _attr_unique_id = "do_energy_forecast_evaluation_samples"
    _attr_suggested_object_id = "do_energy_forecast_evaluation_samples"
    _attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int:
        return int(self._metrics["samples"])


class DummyOSWeatherBaseSensor(SensorEntity):
    """Base for Open-Meteo-backed Weather entities."""

    _attr_should_poll = False

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        self.coordinator = coordinator
        self.weather = coordinator.weather
        self._remove_listener = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, "main")}, name=NAME, manufacturer="Dummy OS", model="Forecast Platform", sw_version=VERSION)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_listener = self.weather.async_add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class DummyOSAsyncQualitySensor(DummyOSAsyncPlannerResultSensor):
    """Executor-backed base for expensive observer-only quality diagnostics."""

    _empty_collection_key = "items"
    _initial_extra: dict[str, Any] = {}

    def _initial_result(self) -> dict[str, Any]:
        result = {
            "status": "initializing",
            "profile": self.coordinator.profile,
            "minimum_samples_for_sufficient_basis": 32,
            self._empty_collection_key: {},
            "blockers": ["quality_calculation_pending"],
        }
        result.update(self._initial_extra)
        return result

    @property
    def _quality(self) -> dict[str, Any]:
        return self._result()


class DummyOSHomeForecastQualityByDaypartSensor(DummyOSAsyncQualitySensor):
    """Observer-only Energy forecast quality split by fixed local dayparts."""

    _attr_name = "DO Energy Forecast Quality By Daypart"
    _attr_unique_id = "do_energy_forecast_quality_by_daypart"
    _attr_suggested_object_id = "do_energy_forecast_quality_by_daypart"
    _attr_icon = "mdi:chart-timeline-variant"

    _empty_collection_key = "dayparts"

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        profile = snapshot["profile"]
        if profile not in PROFILE_LEARNING_OPTIONS:
            return {"status": "blocked", "profile": profile, "minimum_samples_for_sufficient_basis": 32, "dayparts": {}, "blockers": ["profile_unclassified"]}
        return calculate_daypart_quality(snapshot["evaluations"], snapshot["records"], profile, dt_util.as_local)

    @property
    def native_value(self) -> str:
        return str(self._quality["status"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        quality = self._quality
        return {"profile": quality["profile"], "observer_only": True, "resolution_minutes": 15, "minimum_samples_for_sufficient_basis": quality["minimum_samples_for_sufficient_basis"], "daypart_basis": "local_quarter_start", "dayparts": quality["dayparts"], "blockers": quality.get("blockers", [])}


class DummyOSHomeForecastQualityByDayTypeSensor(DummyOSAsyncQualitySensor):
    _attr_name = "DO Energy Forecast Quality By Day Type"
    _attr_unique_id = "do_energy_forecast_quality_by_day_type"
    _attr_suggested_object_id = "do_energy_forecast_quality_by_day_type"
    _attr_icon = "mdi:calendar-week"

    _empty_collection_key = "day_types"

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        profile = snapshot["profile"]
        if profile not in PROFILE_LEARNING_OPTIONS:
            return {"status": "blocked", "profile": profile, "minimum_samples_for_sufficient_basis": 32, "day_types": {}, "blockers": ["profile_unclassified"]}
        return calculate_day_type_quality(snapshot["evaluations"], snapshot["records"], profile, dt_util.as_local)

    @property
    def native_value(self) -> str:
        return str(self._quality["status"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        q = self._quality
        return {"profile": q["profile"], "observer_only": True, "resolution_minutes": 15, "minimum_samples_for_sufficient_basis": q["minimum_samples_for_sufficient_basis"], "day_type_basis": "local_quarter_start_weekday_weekend", "day_types": q["day_types"], "blockers": q.get("blockers", [])}


class DummyOSHomeForecastQualityByDayTypeAndDaypartSensor(DummyOSAsyncQualitySensor):
    """Observer-only Energy forecast quality by day type and daypart."""

    _attr_name = "DO Energy Forecast Quality By Day Type And Daypart"
    _attr_unique_id = "do_energy_forecast_quality_by_day_type_and_daypart"
    _attr_suggested_object_id = "do_energy_forecast_quality_by_day_type_and_daypart"
    _attr_icon = "mdi:calendar-clock"

    _empty_collection_key = "combinations"

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        profile = snapshot["profile"]
        if profile not in PROFILE_LEARNING_OPTIONS:
            return {"status": "blocked", "profile": profile, "minimum_samples_for_sufficient_basis": 32, "combinations": {}, "blockers": ["profile_unclassified"]}
        return calculate_day_type_daypart_quality(snapshot["evaluations"], snapshot["records"], profile, dt_util.as_local)

    @property
    def native_value(self) -> str:
        return str(self._quality["status"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        q = self._quality
        return {"profile": q["profile"], "observer_only": True, "resolution_minutes": 15, "minimum_samples_for_sufficient_basis": q["minimum_samples_for_sufficient_basis"], "combination_basis": "local_quarter_start_day_type_and_daypart", "combinations": q["combinations"], "blockers": q.get("blockers", [])}


class DummyOSHomeForecastQualityByHourSensor(DummyOSAsyncQualitySensor):
    """Observer-only Energy forecast quality per local afternoon hour."""

    _attr_name = "DO Energy Forecast Quality By Hour"
    _attr_unique_id = "do_energy_forecast_quality_by_hour"
    _attr_suggested_object_id = "do_energy_forecast_quality_by_hour"
    _attr_icon = "mdi:clock-outline"

    _empty_collection_key = "hours"
    _initial_extra = {"scope": "afternoon_12_18"}

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        profile = snapshot["profile"]
        if profile not in PROFILE_LEARNING_OPTIONS:
            return {"status": "blocked", "profile": profile, "minimum_samples_for_sufficient_basis": 32, "scope": "afternoon_12_18", "hours": {}, "blockers": ["profile_unclassified"]}
        return calculate_hour_quality(snapshot["evaluations"], snapshot["records"], profile, dt_util.as_local)

    @property
    def native_value(self) -> str:
        return str(self._quality["status"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        q = self._quality
        return {"profile": q["profile"], "observer_only": True, "resolution_minutes": 15, "minimum_samples_for_sufficient_basis": q["minimum_samples_for_sufficient_basis"], "hour_basis": "local_quarter_start", "scope": q["scope"], "hours": q["hours"], "blockers": q.get("blockers", [])}


class DummyOSWeatherCurrentSensor(DummyOSWeatherBaseSensor):
    def __init__(self, coordinator: DummyOSHomeDataCoordinator, key: str, label: str, unit: str | None, icon: str, device_class: SensorDeviceClass | None = None) -> None:
        super().__init__(coordinator)
        self.key = key
        object_id = f"do_weather_{key.removesuffix('_2m').removesuffix('_10m')}"
        self._attr_name = f"DO Weather {label}"
        self._attr_unique_id = object_id
        self._attr_suggested_object_id = object_id
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        if device_class is not None:
            self._attr_device_class = device_class

    @property
    def native_value(self) -> Any:
        return self.weather.current.get(self.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"source": "open_meteo", "source_status": self.weather.source_status, "last_successful_update": self.weather.last_successful_update.isoformat() if self.weather.last_successful_update else None}


class DummyOSWeatherTimelineSensor(DummyOSWeatherBaseSensor):
    _attr_name = "DO Weather Forecast Timeline"
    _attr_unique_id = "do_weather_forecast_timeline"
    _attr_suggested_object_id = "do_weather_forecast_timeline"
    _attr_icon = "mdi:weather-partly-cloudy"
    _unrecorded_attributes = frozenset({"points", "daily"})

    @property
    def native_value(self) -> int:
        return len(self.weather.timeline)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        points = self.weather.timeline
        return {
            "source": "open_meteo",
            "model": OPEN_METEO_MODEL,
            "resolution_minutes": 15,
            "horizon_hours": 72,
            "slot_count": FORECAST_SLOTS,
            "point_count": len(points),
            "point_format": "[unix_ms, temperature_c, humidity_pct, dew_point_c, apparent_temperature_c, precipitation_mm, rain_mm, weather_code, wind_speed_kmh, wind_direction_deg, wind_gusts_kmh, ghi_wm2, sunshine_duration_s, dhi_wm2, dni_wm2, is_day, direct_radiation_wm2]",
            "fields": ["unix_ms", *POINT_FIELDS],
            "forecast_start": datetime.fromtimestamp(points[0][0] / 1000, tz=dt_util.UTC).isoformat() if points else None,
            "forecast_end": datetime.fromtimestamp(points[-1][0] / 1000, tz=dt_util.UTC).isoformat() if points else None,
            "requested_latitude": OPEN_METEO_LATITUDE,
            "requested_longitude": OPEN_METEO_LONGITUDE,
            "source_latitude": self.weather.source_latitude,
            "source_longitude": self.weather.source_longitude,
            "source_elevation_m": self.weather.source_elevation,
            "timezone": OPEN_METEO_TIMEZONE,
            "recorder_points": "excluded",
            "daily": self.weather.daily,
            "points": points,
        }


class DummyOSWeatherSourceStatusSensor(DummyOSWeatherBaseSensor):
    _attr_name = "DO Weather Source Status"
    _attr_unique_id = "do_weather_source_status"
    _attr_suggested_object_id = "do_weather_source_status"
    _attr_icon = "mdi:cloud-check-outline"

    @property
    def native_value(self) -> str:
        return self.weather.source_status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"source": "Open-Meteo", "endpoint": "api.open-meteo.com/v1/forecast", "requested_latitude": OPEN_METEO_LATITUDE, "requested_longitude": OPEN_METEO_LONGITUDE, "timezone": OPEN_METEO_TIMEZONE, "last_attempt": self.weather.last_attempt.isoformat() if self.weather.last_attempt else None, "last_successful_update": self.weather.last_successful_update.isoformat() if self.weather.last_successful_update else None, "last_error": self.weather.last_error, "age_minutes": self.weather.age_minutes, "refresh_schedule": "hourly at :00:05", "retry_backoff_seconds": [0, 5, 15]}


class DummyOSWeatherFreshnessSensor(DummyOSWeatherBaseSensor):
    _attr_name = "DO Weather Source Freshness"
    _attr_unique_id = "do_weather_source_freshness"
    _attr_suggested_object_id = "do_weather_source_freshness"
    _attr_icon = "mdi:clock-check-outline"

    @property
    def native_value(self) -> str:
        return self.weather.freshness

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"age_minutes": self.weather.age_minutes, "fresh_under_minutes": 90, "expired_from_minutes": 180}


class DummyOSWeatherLastUpdateSensor(DummyOSWeatherBaseSensor):
    _attr_name = "DO Weather Last Update"
    _attr_unique_id = "do_weather_last_update"
    _attr_suggested_object_id = "do_weather_last_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:update"

    @property
    def native_value(self) -> datetime | None:
        return self.weather.last_successful_update


class DummyOSWeatherModelSensor(DummyOSWeatherBaseSensor):
    _attr_name = "DO Weather Model"
    _attr_unique_id = "do_weather_model"
    _attr_suggested_object_id = "do_weather_model"
    _attr_icon = "mdi:cloud-sync-outline"

    @property
    def native_value(self) -> str:
        return OPEN_METEO_MODEL

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"provider": "Open-Meteo", "resolution_minutes": 15, "horizon_hours": 72, "forecast_slots": FORECAST_SLOTS, "current_variables": list(self.weather.current.keys()), "timeline_fields": list(POINT_FIELDS), "daily_days": len(self.weather.daily), "generation_time_ms": self.weather.generation_time_ms}


class DummyOSEnergyTimeWindowsSensor(DummyOSBaseSensor):
    """Observer-only Step 7 Energy Time Windows diagnostics."""

    _attr_name = "DO Energy Time Windows"
    _attr_unique_id = "do_energy_time_windows"
    _attr_suggested_object_id = "do_energy_time_windows"
    _attr_icon = "mdi:timeline-clock-outline"

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        super().__init__(coordinator)
        self._cached_result: dict[str, Any] | None = None
        self._refresh_task = None
        self._refresh_pending = False

    @property
    def name(self) -> str:
        """Return the canonical runtime name used for friendly_name."""
        return "DO Energy Time Windows"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._schedule_refresh()

    async def async_will_remove_from_hass(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self._schedule_refresh()

    @callback
    def _schedule_refresh(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_pending = True
            return
        self._refresh_task = self.hass.async_create_task(self._async_refresh_result())

    async def _async_refresh_result(self) -> None:
        while True:
            self._refresh_pending = False
            evaluations = list(self.coordinator.evaluations)
            profile = self.coordinator.profile
            result = await self.hass.async_add_executor_job(
                self._calculate_result, evaluations, profile
            )
            self._cached_result = result
            self.async_write_ha_state()
            if not self._refresh_pending:
                return

    @staticmethod
    def _empty_result(profile: str, *, status: str, blocker: str) -> dict[str, Any]:
        classification_source = "profile_unclassified" if blocker == "profile_unclassified" else "calculation_pending"
        return {
            "schema_version": "7b.1",
            "algorithm_version": "time_windows_observer_v1",
            "profile": profile,
            "context_key": f"{profile}|{classification_source}",
            "classification_source": classification_source,
            "observer_only": True,
            "forecast_influence_enabled": False,
            "ready_for_live_observation": False,
            "ready_for_forecast_influence": False,
            "event_count": 0,
            "event_days": 0,
            "rejected_event_count": 0,
            "reject_reasons": {},
            "window_start": None,
            "window_end": None,
            "window_width_minutes": None,
            "window_quarter_count": None,
            "p10_start_minute": None,
            "p90_end_minute": None,
            "median_center_minute": None,
            "center_mad_minutes": None,
            "contained_day_count": None,
            "contained_day_ratio": None,
            "median_event_duration_minutes": None,
            "median_daily_energy_kwh": None,
            "energy_iqr_kwh": None,
            "lodo_max_start_shift_minutes": None,
            "lodo_max_end_shift_minutes": None,
            "early_late_start_shift_minutes": None,
            "early_late_end_shift_minutes": None,
            "protected_window_overlap": False,
            "native_resolution_minutes": 15,
            "calibration_method": "daily_representative_p10_start_p90_end",
            "minimum_event_days_collecting_exit": 8,
            "minimum_event_days_calibrated": 12,
            "minimum_event_days_stable": 16,
            "maximum_boundary_shift_minutes": 15,
            "source_basis": {},
            "calibration_fingerprint": None,
            "blockers": [blocker],
            "status": status,
        }

    def _calculate_result(
        self, evaluations: list[dict[str, Any]], profile: str
    ) -> dict[str, Any]:
        if profile not in PROFILE_LEARNING_OPTIONS:
            return self._empty_result(
                profile, status="blocked", blocker="profile_unclassified"
            )
        peak_result = calculate_peak_learning(evaluations, profile, dt_util.as_local)
        return calculate_time_windows(peak_result, profile, dt_util.as_local)

    def _result(self) -> dict[str, Any]:
        return self._cached_result or self._empty_result(
            self.coordinator.profile,
            status="initializing",
            blocker="observer_calculation_pending",
        )

    @property
    def native_value(self) -> str:
        return str(self._result()["status"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._result()
        return {
            "schema_version": result["schema_version"],
            "algorithm_version": result["algorithm_version"],
            "profile": result["profile"],
            "context_key": result["context_key"],
            "classification_source": result["classification_source"],
            "observer_only": result["observer_only"],
            "forecast_influence_enabled": result["forecast_influence_enabled"],
            "ready_for_live_observation": result["ready_for_live_observation"],
            "ready_for_forecast_influence": result["ready_for_forecast_influence"],
            "event_count": result["event_count"],
            "event_days": result["event_days"],
            "rejected_event_count": result["rejected_event_count"],
            "reject_reasons": result["reject_reasons"],
            "window_start": result["window_start"],
            "window_end": result["window_end"],
            "window_width_minutes": result["window_width_minutes"],
            "window_quarter_count": result["window_quarter_count"],
            "p10_start_minute": result["p10_start_minute"],
            "p90_end_minute": result["p90_end_minute"],
            "median_center_minute": result["median_center_minute"],
            "center_mad_minutes": result["center_mad_minutes"],
            "contained_day_count": result["contained_day_count"],
            "contained_day_ratio": result["contained_day_ratio"],
            "median_event_duration_minutes": result["median_event_duration_minutes"],
            "median_daily_energy_kwh": result["median_daily_energy_kwh"],
            "energy_iqr_kwh": result["energy_iqr_kwh"],
            "lodo_max_start_shift_minutes": result["lodo_max_start_shift_minutes"],
            "lodo_max_end_shift_minutes": result["lodo_max_end_shift_minutes"],
            "early_late_start_shift_minutes": result["early_late_start_shift_minutes"],
            "early_late_end_shift_minutes": result["early_late_end_shift_minutes"],
            "protected_window_overlap": result["protected_window_overlap"],
            "native_resolution_minutes": result["native_resolution_minutes"],
            "calibration_method": result["calibration_method"],
            "minimum_event_days_collecting_exit": result["minimum_event_days_collecting_exit"],
            "minimum_event_days_calibrated": result["minimum_event_days_calibrated"],
            "minimum_event_days_stable": result["minimum_event_days_stable"],
            "maximum_boundary_shift_minutes": result["maximum_boundary_shift_minutes"],
            "source_basis": result["source_basis"],
            "calibration_fingerprint": result["calibration_fingerprint"],
            "blockers": result["blockers"],
        }


class DummyOSEnergyRecencyWeightingSensor(DummyOSBaseSensor):
    """Observer-only Step 8A Energy recency-weighting diagnostics."""

    _attr_name = "DO Energy Recency Weighting"
    _attr_unique_id = "do_energy_recency_weighting"
    _attr_suggested_object_id = "do_energy_recency_weighting"
    _attr_icon = "mdi:timeline-clock-outline"
    _unrecorded_attributes = frozenset({"per_candidate_metrics", "segment_metrics", "early_late_metrics"})

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        super().__init__(coordinator)
        self._cached_result: dict[str, Any] | None = None
        self._refresh_task = None
        self._refresh_pending = False

    @property
    def name(self) -> str:
        return "DO Energy Recency Weighting"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._schedule_refresh()

    async def async_will_remove_from_hass(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self._schedule_refresh()

    @callback
    def _schedule_refresh(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_pending = True
            return
        self._refresh_task = self.hass.async_create_task(self._async_refresh_result())

    async def _async_refresh_result(self) -> None:
        while True:
            self._refresh_pending = False
            records = list(self.coordinator.records)
            evaluations = list(self.coordinator.evaluations)
            profile = self.coordinator.profile
            result = await self.hass.async_add_executor_job(
                self._calculate_result, records, evaluations, profile
            )
            self._cached_result = result
            self.async_write_ha_state()
            if not self._refresh_pending:
                return

    def _calculate_result(
        self, records: list[dict[str, Any]], evaluations: list[dict[str, Any]], profile: str
    ) -> dict[str, Any]:
        if profile not in PROFILE_LEARNING_OPTIONS:
            return {"schema_version": "8a.1", "algorithm_version": "recency_weighting_observer_v1", "status": "blocked", "profile": profile, "observer_only": True, "forecast_influence_enabled": False, "promotion_ready": False, "blockers": ["profile_unclassified"]}
        return calculate_recency_weighting(records, evaluations, profile, dt_util.as_local)

    def _result(self) -> dict[str, Any]:
        return self._cached_result or {"schema_version": "8a.1", "algorithm_version": "recency_weighting_observer_v1", "status": "initializing", "profile": self.coordinator.profile, "observer_only": True, "forecast_influence_enabled": False, "promotion_ready": False, "blockers": ["observer_calculation_pending"]}

    @property
    def native_value(self) -> str:
        return str(self._result()["status"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._result())

class DummyOSEnergyPeakLearningSensor(DummyOSAsyncPlannerResultSensor):
    """Observer-only Step 6 Energy peak learning diagnostics."""

    _attr_name = "DO Energy Peak Learning"
    _attr_unique_id = "do_energy_peak_learning"
    _attr_suggested_object_id = "do_energy_peak_learning"
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _unrecorded_attributes = frozenset({"calibration", "classifications", "events"})

    @property
    def name(self) -> str:
        return "DO Energy Peak Learning"

    def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        profile = snapshot["profile"]
        if profile not in PROFILE_LEARNING_OPTIONS:
            return {
                "schema_version": 1,
                "algorithm_version": "peak_observer_v1",
                "calibration_fingerprint": None,
                "source_basis": {},
                "profile": profile,
                "status": "blocked",
                "minimum_samples_per_hour": 32,
                "minimum_distinct_days_per_hour": 8,
                "threshold_method": "leave_one_local_day_out_positive_residual_quantile",
                "threshold_quantile": 0.9,
                "candidate_count": 0,
                "event_count": 0,
                "calibrated_hours": 0,
                "classification_calibration": {},
                "protected_windows": {},
                "calibration": {},
                "classifications": {},
                "events": [],
                "blockers": ["profile_unclassified"],
            }
        return calculate_peak_learning(snapshot["evaluations"], profile, dt_util.as_local)

    def _initial_result(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "algorithm_version": "peak_observer_v1",
            "calibration_fingerprint": None,
            "source_basis": {},
            "profile": self.coordinator.profile,
            "status": "initializing",
            "minimum_samples_per_hour": 32,
            "minimum_distinct_days_per_hour": 8,
            "threshold_method": "leave_one_local_day_out_positive_residual_quantile",
            "threshold_quantile": 0.9,
            "candidate_count": 0,
            "event_count": 0,
            "calibrated_hours": 0,
            "classification_calibration": {},
            "protected_windows": {},
            "calibration": {},
            "classifications": {},
            "events": [],
            "blockers": ["observer_calculation_pending"],
        }

    @property
    def native_value(self) -> str:
        return str(self._result().get("status", "initializing"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._result()
        return {
            "schema_version": result["schema_version"],
            "algorithm_version": result["algorithm_version"],
            "calibration_fingerprint": result["calibration_fingerprint"],
            "source_basis": result["source_basis"],
            "profile": result["profile"],
            "observer_only": True,
            "forecast_influence_enabled": False,
            "ready_for_model_influence": False,
            "minimum_samples_per_hour": result["minimum_samples_per_hour"],
            "minimum_distinct_days_per_hour": result["minimum_distinct_days_per_hour"],
            "threshold_method": result["threshold_method"],
            "threshold_quantile": result["threshold_quantile"],
            "candidate_count": result["candidate_count"],
            "event_count": result["event_count"],
            "calibrated_hours": result["calibrated_hours"],
            "classification_calibration": result["classification_calibration"],
            "protected_windows": result["protected_windows"],
            "calibration": result["calibration"],
            "classifications": result["classifications"],
            "events": result["events"],
            "blockers": result.get("blockers", []),
        }

