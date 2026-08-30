"""Sensor entities for the native Dummy OS Solar forecast."""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FORECAST_SLOTS, NAME, SOLAR_MIN_VALID_COVERAGE, VERSION
from .solar import OPEN_METEO_SOLAR_MODEL, SOLAR_RESOLUTION_MINUTES


def build_solar_sensors(coordinator) -> list[SensorEntity]:
    """Return all Solar shadow entities."""
    return [
        DummyOSSolarStatusSensor(coordinator),
        DummyOSSolarTimelineSensor(coordinator),
        DummyOSSolarDailySensor(coordinator, "today", "north"),
        DummyOSSolarDailySensor(coordinator, "today", "south"),
        DummyOSSolarDailySensor(coordinator, "today", "total"),
        DummyOSSolarDailySensor(coordinator, "tomorrow", "north"),
        DummyOSSolarDailySensor(coordinator, "tomorrow", "south"),
        DummyOSSolarDailySensor(coordinator, "tomorrow", "total"),
        DummyOSSolarNextQuarterSensor(coordinator),
        DummyOSSolarActualPowerSensor(coordinator, "north"),
        DummyOSSolarActualPowerSensor(coordinator, "south"),
        DummyOSSolarActualPowerSensor(coordinator, "total"),
        DummyOSSolarLastCompletedQuarterSensor(coordinator),
        DummyOSSolarModelSensor(coordinator),
    ]


class DummyOSSolarBaseSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator) -> None:
        self.solar = coordinator.solar
        self._remove_listener = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, "main")}, name=NAME, manufacturer="Dummy OS", model="Data Forecast Platform", sw_version=VERSION)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_listener = self.solar.async_add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class DummyOSSolarStatusSensor(DummyOSSolarBaseSensor):
    _attr_name = "Dummy OS Solar Source Status"
    _attr_unique_id = "do_solar_status"
    _attr_suggested_object_id = "do_solar_status"
    _attr_icon = "mdi:solar-power-variant-outline"

    @property
    def native_value(self) -> str:
        return self.solar.source_status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        actual = self.solar.actual_power
        evaluation = self.solar.last_evaluation
        return {
            "provider": "Open-Meteo",
            "attribution": "Weather data by Open-Meteo.com",
            "endpoint": "api.open-meteo.com/v1/forecast",
            "last_attempt": self.solar.last_attempt.isoformat() if self.solar.last_attempt else None,
            "last_successful_update": self.solar.last_successful_update.isoformat() if self.solar.last_successful_update else None,
            "age_minutes": self.solar.age_minutes,
            "last_error": self.solar.last_error,
            "slot_count": len(self.solar.points),
            "source_buffer_slot_count": self.solar.source_point_count,
            "refresh_schedule": "hourly at :00:20",
            "retry_backoff_seconds": [0, 5, 15],
            "actual_total_available": actual["total"] is not None,
            "actual_roof_split_available": (
                actual["north"] is not None and actual["south"] is not None
            ),
            "active_evaluation_quarter": (
                self.solar.active_quarter_start.isoformat()
                if self.solar.active_quarter_start
                else None
            ),
            "active_forecast_snapshot_available": self.solar.active_forecast_snapshot_available,
            "last_evaluation_status": evaluation.get("status") if evaluation else None,
            "last_evaluation_slot": evaluation.get("slot_id") if evaluation else None,
            "mode": "observation_shadow",
        }


class DummyOSSolarTimelineSensor(DummyOSSolarBaseSensor):
    _attr_name = "Dummy OS Solar Forecast Timeline"
    _attr_unique_id = "do_solar_forecast_timeline"
    _attr_suggested_object_id = "do_solar_forecast_timeline"
    _attr_icon = "mdi:chart-timeline-variant-shimmer"
    _unrecorded_attributes = frozenset({"points"})

    @property
    def native_value(self) -> int:
        return len(self.solar.points)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        points = self.solar.points
        return {
            "source": "open_meteo",
            "attribution": "Weather data by Open-Meteo.com",
            "model": OPEN_METEO_SOLAR_MODEL,
            "resolution_minutes": SOLAR_RESOLUTION_MINUTES,
            "horizon_hours": 72,
            "slot_count": FORECAST_SLOTS,
            "point_count": len(points),
            "source_buffer_point_count": self.solar.source_point_count,
            "point_format": "[unix_ms, north_kwh, south_kwh, total_kwh, north_kw, south_kw, total_kw, north_gti_wm2, south_gti_wm2]",
            "interval_semantics": "slot_start; Open-Meteo backward-average timestamp shifted by 15 minutes",
            "forecast_start": points[0].start.isoformat() if points else None,
            "last_slot_start": points[-1].start.isoformat() if points else None,
            "forecast_end": (
                (points[-1].start + timedelta(minutes=SOLAR_RESOLUTION_MINUTES)).isoformat()
                if points
                else None
            ),
            "recorder_points": "excluded",
            "points": [point.as_list() for point in points],
        }


class DummyOSSolarDailySensor(DummyOSSolarBaseSensor):
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator, day: str, roof: str) -> None:
        super().__init__(coordinator)
        self.day = day
        self.roof = roof
        object_id = f"do_solar_forecast_{day}_{roof}"
        self._attr_name = f"Dummy OS Solar Forecast {day.title()} {roof.title()}"
        self._attr_unique_id = object_id
        self._attr_suggested_object_id = object_id

    @property
    def native_value(self) -> float | None:
        if not self.solar.points:
            return None
        local_today = dt_util.as_local(dt_util.utcnow()).date()
        target = local_today if self.day == "today" else local_today + timedelta(days=1)
        return self.solar.energy_for_local_date(target, self.roof)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        roof = getattr(self.solar, self.roof) if self.roof != "total" else None
        return {
            "provider": "open_meteo",
            "roof": self.roof,
            "source_status": self.solar.source_status,
            "dc_capacity_kwp": roof.dc_capacity_kwp if roof else round(self.solar.north.dc_capacity_kwp + self.solar.south.dc_capacity_kwp, 3),
            "ac_limit_kw": roof.ac_limit_kw if roof else round(self.solar.north.ac_limit_kw + self.solar.south.ac_limit_kw, 3),
        }


class DummyOSSolarNextQuarterSensor(DummyOSSolarBaseSensor):
    _attr_name = "Dummy OS Solar Forecast Next Quarter"
    _attr_unique_id = "do_solar_forecast_next_quarter"
    _attr_suggested_object_id = "do_solar_forecast_next_quarter"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:solar-power-variant"

    @property
    def native_value(self) -> float | None:
        point = self.solar.next_quarter_point()
        return point.total_kwh if point else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        point = self.solar.next_quarter_point()
        return {
            "start": point.start.isoformat() if point else None,
            "north_kwh": point.north_kwh if point else None,
            "south_kwh": point.south_kwh if point else None,
            "selection": "first_future_slot",
            "refresh_schedule": "quarter-hourly at :00",
        }


class DummyOSSolarActualPowerSensor(DummyOSSolarBaseSensor):
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:solar-panel"

    def __init__(self, coordinator, roof: str) -> None:
        super().__init__(coordinator)
        self.roof = roof
        object_id = f"do_solar_actual_power_{roof}"
        self._attr_name = f"Dummy OS Solar Actual Power {roof.title()}"
        self._attr_unique_id = object_id
        self._attr_suggested_object_id = object_id

    @property
    def native_value(self) -> float | None:
        return self.solar.actual_power[self.roof]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"method": self.solar.actual_power["method"], "source_entities": list(self.solar.actual_entities)}


class DummyOSSolarLastCompletedQuarterSensor(DummyOSSolarBaseSensor):
    """Expose one immutable, flat record for automation and Sheets export."""

    _attr_name = "Dummy OS Solar Evaluation Last Completed Quarter"
    _attr_unique_id = "do_solar_evaluation_last_completed_quarter"
    _attr_suggested_object_id = "do_solar_evaluation_last_completed_quarter"
    _attr_icon = "mdi:chart-box-outline"

    @property
    def native_value(self) -> str | None:
        evaluation = self.solar.last_evaluation
        return evaluation.get("slot_id") if evaluation else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        evaluation = self.solar.last_evaluation
        if evaluation is None:
            return {
                "status": "waiting_for_first_completed_quarter",
                "resolution_minutes": SOLAR_RESOLUTION_MINUTES,
                "minimum_coverage_percent": SOLAR_MIN_VALID_COVERAGE * 100.0,
            }
        return dict(evaluation)


class DummyOSSolarModelSensor(DummyOSSolarBaseSensor):
    _attr_name = "Dummy OS Solar Forecast Model"
    _attr_unique_id = "do_solar_model"
    _attr_suggested_object_id = "do_solar_model"
    _attr_icon = "mdi:information-outline"

    @property
    def native_value(self) -> str:
        return "open_meteo_gti_physical_v0.1"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "provider": "Open-Meteo",
            "source_variable": "global_tilted_irradiance",
            "source_timezone": "UTC",
            "resolution_minutes": SOLAR_RESOLUTION_MINUTES,
            "horizon_hours": 72,
            "forecast_slots": FORECAST_SLOTS,
            "north": asdict(self.solar.north),
            "south": asdict(self.solar.south),
            "azimuth_convention": "Open-Meteo: 0=south, +/-180=north",
            "calculation": "gti/1000 x dc_kwp x performance_factor; capped per roof at ac_limit_kw",
            "actual_energy_calculation": "zero-order-hold integration of total AC; north/south split by SMA DC input ratio",
            "evaluation": "forecast frozen at slot start and compared after a completed quarter with at least 90% coverage",
            "mode": "observation_shadow",
        }
