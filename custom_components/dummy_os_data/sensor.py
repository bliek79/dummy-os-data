"""Sensors for Dummy OS Data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, NAME, VERSION
from .coordinator import DummyOSHomeDataCoordinator


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
        ]
    )


class DummyOSBaseSensor(SensorEntity):
    """Base sensor."""

    _attr_should_poll = False

    def __init__(self, coordinator: DummyOSHomeDataCoordinator) -> None:
        self.coordinator = coordinator
        self._remove_listener = None

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


class DummyOSActualQuarterSensor(DummyOSBaseSensor):
    """Most recently completed valid 15-minute home-energy snapshot."""

    _attr_name = "Dummy OS Home Actual Quarter"
    _attr_unique_id = "do_home_actual_quarter"
    _attr_suggested_object_id = "do_home_actual_quarter"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    # Intentionally no state_class: this is a per-quarter snapshot, not a cumulative energy meter.
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
        return {
            "source_entity": self.coordinator.source_entity,
            "source_available": self.coordinator.source_available,
            "valid_quarters": self.coordinator.valid_quarters,
            "history_days": self.coordinator.history_days,
            "profile": self.coordinator.profile,
            "storage_limit_days": 400,
        }


class DummyOSHistoryDaysSensor(DummyOSBaseSensor):
    """Number of local days with valid quarter-hour history."""

    _attr_name = "Dummy OS Home History Days"
    _attr_unique_id = "do_home_history_days"
    _attr_suggested_object_id = "do_home_history_days"
    _attr_native_unit_of_measurement = "d"
    _attr_icon = "mdi:calendar-clock-outline"
    # Intentionally no state_class: this is a dataset-availability counter, not a measured physical quantity.

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
        return "historical_foundation"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "model_version": "0.1",
            "forecast_active": False,
            "evaluation_active": False,
            "resolution_minutes": 15,
            "horizon_hours": 72,
            "profile": self.coordinator.profile,
        }
