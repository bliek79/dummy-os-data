"""Sensors for Dummy OS Data."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FORECAST_SLOTS, NAME, QUARTER_MINUTES, VERSION
from .coordinator import DummyOSHomeDataCoordinator
from .forecast import HomeBaselineForecast


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Dummy OS Data sensors."""
    coordinator: DummyOSHomeDataCoordinator = entry.runtime_data
    async_add_entities(
        [
            DummyOSActualQuarterSensor(coordinator),
            DummyOSHistoryStatusSensor(coordinator),
            DummyOSHistoryDaysSensor(coordinator),
            DummyOSForecastModelSensor(coordinator),
            DummyOSHomeForecastSensor(coordinator),
            DummyOSHomeForecastNextQuarterSensor(coordinator),
            DummyOSHomeForecastCoverageSensor(coordinator),
        ]
    )


class DummyOSBaseSensor(SensorEntity):
    """Base sensor."""

    _attr_should_poll = False

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
            model="Data Forecast Platform",
            sw_version=VERSION,
        )

    async def async_added_to_hass(self) -> None:
        """Register coordinator listener."""
        await super().async_added_to_hass()
        self._remove_listener = self.coordinator.async_add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister coordinator listener."""
        if self._remove_listener is not None:
            self._remove_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _forecast(self):
        local = dt_util.as_local(dt_util.utcnow())
        quarter_key = (
            local.date().isoformat(),
            local.hour,
            local.minute // QUARTER_MINUTES,
        )
        key = (self.coordinator.profile, len(self.coordinator.records), quarter_key)
        if key != self._forecast_cache_key:
            self._forecast_cache = HomeBaselineForecast(self.coordinator.records).build(
                self.coordinator.profile
            )
            self._forecast_cache_key = key
        return self._forecast_cache or []


class DummyOSActualQuarterSensor(DummyOSBaseSensor):
    """Most recently completed valid 15-minute home-energy snapshot."""

    _attr_name = "Dummy OS Home Actual Quarter"
    _attr_unique_id = "do_home_actual_quarter"
    _attr_suggested_object_id = "do_home_actual_quarter"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:home-lightning-bolt-outline"

    @property
    def native_value(self) -> float | None:
        result = self.coordinator.last_quarter
        return result.energy_kwh if result and result.valid else None

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
            "valid": result.valid,
            "source_entity": self.coordinator.source_entity,
            "profile": result.profile,
        }


class DummyOSHistoryStatusSensor(DummyOSBaseSensor):
    """Historical collection health."""

    _attr_name = "Dummy OS Home History Status"
    _attr_unique_id = "do_home_history_status"
    _attr_suggested_object_id = "do_home_history_status"
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
    """Number of local days with valid quarter-hour history."""

    _attr_name = "Dummy OS Home History Days"
    _attr_unique_id = "do_home_history_days"
    _attr_suggested_object_id = "do_home_history_days"
    _attr_native_unit_of_measurement = "d"
    _attr_icon = "mdi:calendar-clock-outline"

    @property
    def native_value(self) -> int:
        return self.coordinator.history_days

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "valid_quarters": self.coordinator.valid_quarters,
            "resolution_minutes": 15,
        }


class DummyOSForecastModelSensor(DummyOSBaseSensor):
    """Current Home Forecast model status."""

    _attr_name = "Dummy OS Home Forecast Model"
    _attr_unique_id = "do_home_forecast_model"
    _attr_suggested_object_id = "do_home_forecast_model"
    _attr_icon = "mdi:chart-timeline-variant-shimmer"

    @property
    def native_value(self) -> str:
        return "historical_baseline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        model = HomeBaselineForecast(self.coordinator.records)
        return {
            "model_version": "0.2",
            "forecast_active": True,
            "evaluation_active": False,
            "resolution_minutes": 15,
            "horizon_hours": 72,
            "forecast_slots": FORECAST_SLOTS,
            "profile": self.coordinator.profile,
            "profile_statistics": model.profile_statistics(self.coordinator.profile),
        }


class DummyOSHomeForecastSensor(DummyOSBaseSensor):
    """Rolling 72-hour home-consumption baseline forecast."""

    _attr_name = "Dummy OS Home Forecast"
    _attr_unique_id = "do_home_forecast"
    _attr_suggested_object_id = "do_home_forecast"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:home-clock-outline"

    @property
    def native_value(self) -> float | None:
        slots = self._forecast()
        values = [slot.energy_kwh for slot in slots if slot.energy_kwh is not None]
        return round(sum(values), 3) if values else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        slots = self._forecast()
        populated = sum(1 for slot in slots if slot.energy_kwh is not None)
        supported = sum(
            1 for slot in slots if slot.source in {"weekday_quarter", "quarter_of_day"}
        )
        return {
            "profile": self.coordinator.profile,
            "model": "historical_baseline",
            "model_version": "0.2",
            "forecast_start": slots[0].start.isoformat() if slots else None,
            "resolution_minutes": 15,
            "horizon_hours": 72,
            "slot_count": len(slots),
            "populated_slots": populated,
            "supported_slots": supported,
            "coverage_percent": round(supported / len(slots) * 100, 1) if slots else 0.0,
            "forecast": HomeBaselineForecast.serialize(slots),
        }


class DummyOSHomeForecastNextQuarterSensor(DummyOSBaseSensor):
    """Forecast energy for the next 15-minute slot."""

    _attr_name = "Dummy OS Home Forecast Next Quarter"
    _attr_unique_id = "do_home_forecast_next_quarter"
    _attr_suggested_object_id = "do_home_forecast_next_quarter"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:clock-fast"

    @property
    def native_value(self) -> float | None:
        slots = self._forecast()
        return slots[0].energy_kwh if slots else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        slots = self._forecast()
        if not slots:
            return {"status": "unavailable", "profile": self.coordinator.profile}
        slot = slots[0]
        return {
            "period_start": slot.start.isoformat(),
            "period_end": slot.end.isoformat(),
            "profile": self.coordinator.profile,
            "sample_count": slot.sample_count,
            "source": slot.source,
            "confidence": slot.confidence,
        }


class DummyOSHomeForecastCoverageSensor(DummyOSBaseSensor):
    """Historical support coverage of the 72-hour baseline forecast."""

    _attr_name = "Dummy OS Home Forecast Coverage"
    _attr_unique_id = "do_home_forecast_coverage"
    _attr_suggested_object_id = "do_home_forecast_coverage"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:chart-donut"

    @property
    def native_value(self) -> float:
        slots = self._forecast()
        if not slots:
            return 0.0
        supported = sum(
            1 for slot in slots if slot.source in {"weekday_quarter", "quarter_of_day"}
        )
        return round(supported / len(slots) * 100, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        slots = self._forecast()
        sources: dict[str, int] = {}
        for slot in slots:
            sources[slot.source] = sources.get(slot.source, 0) + 1
        populated = sum(1 for slot in slots if slot.energy_kwh is not None)
        supported = sum(
            1 for slot in slots if slot.source in {"weekday_quarter", "quarter_of_day"}
        )
        return {
            "profile": self.coordinator.profile,
            "slot_count": len(slots),
            "populated_slots": populated,
            "supported_slots": supported,
            "source_distribution": sources,
        }
