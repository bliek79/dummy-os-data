"""Registered Degree Days sensor entities for Dummy OS Forecast."""

from __future__ import annotations

from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import callback

from .const import DOMAIN, NAME, VERSION
from .degree_days import MAX_HISTORY_DAYS, MIN_VALID_HOURS


class DummyOSDegreeDaysBaseSensor(SensorEntity):
    """Base entity for the Degree Days feature layer."""

    _attr_should_poll = False

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self.degree_days = coordinator.degree_days
        self._remove_listener = None

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
        self._remove_listener = self.degree_days.async_add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def record(self) -> dict[str, Any]:
        return self.degree_days.last_record or {}


class DummyOSDegreeDaysValueSensor(DummyOSDegreeDaysBaseSensor):
    """Expose one scalar value from the latest completed Degree Days record."""

    def __init__(
        self,
        coordinator,
        *,
        object_id: str,
        name: str,
        value_getter: Callable[["DummyOSDegreeDaysValueSensor"], Any],
        unit: str | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = object_id
        self._attr_suggested_object_id = object_id
        self._attr_name = name
        self._value_getter = value_getter
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon

    @property
    def native_value(self) -> Any:
        return self._value_getter(self)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        record = self.record
        return {
            "date": record.get("date"),
            "valid": record.get("valid"),
            "sample_hours": record.get("sample_hours"),
            "coverage_percent": record.get("coverage_percent"),
            "base_temperature_c": record.get("base_temperature_c"),
            "source": record.get("source"),
        }


class DummyOSDegreeDaysLastDaySensor(DummyOSDegreeDaysBaseSensor):
    """Expose the complete latest completed-day Degree Days snapshot."""

    _attr_name = "DO Degree Days Last Day"
    _attr_unique_id = "do_degree_days_last_day"
    _attr_suggested_object_id = "do_degree_days_last_day"
    _attr_icon = "mdi:home-thermometer-outline"

    @property
    def native_value(self) -> str | None:
        return self.record.get("date")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "data_type": "completed_day_snapshot",
            "storage_limit_days": MAX_HISTORY_DAYS,
            "minimum_valid_hours": MIN_VALID_HOURS,
            **self.record,
        }


def build_degree_days_sensors(coordinator) -> list[SensorEntity]:
    """Build the fixed ten-entity Degree Days registry set."""
    return [
        DummyOSDegreeDaysValueSensor(
            coordinator,
            object_id="do_degree_days_status",
            name="DO Degree Days Status",
            value_getter=lambda sensor: sensor.degree_days.status,
            icon="mdi:database-check-outline",
        ),
        DummyOSDegreeDaysValueSensor(
            coordinator,
            object_id="do_degree_days_history_days",
            name="DO Degree Days History Days",
            value_getter=lambda sensor: sensor.degree_days.history_days,
            unit="d",
            icon="mdi:calendar-clock-outline",
        ),
        DummyOSDegreeDaysValueSensor(
            coordinator,
            object_id="do_degree_days_temperature_daily",
            name="DO Degree Days Temperature Daily",
            value_getter=lambda sensor: sensor.record.get("average_temperature_c"),
            unit="°C",
            icon="mdi:thermometer-lines",
        ),
        DummyOSDegreeDaysValueSensor(
            coordinator,
            object_id="do_degree_days_daily",
            name="DO Degree Days Daily",
            value_getter=lambda sensor: sensor.record.get("degree_days"),
            unit="dd",
            icon="mdi:weather-cloudy-clock",
        ),
        DummyOSDegreeDaysValueSensor(
            coordinator,
            object_id="do_degree_days_weighted_daily",
            name="DO Degree Days Weighted Daily",
            value_getter=lambda sensor: sensor.record.get("weighted_degree_days"),
            unit="wdd",
            icon="mdi:chart-line",
        ),
        DummyOSDegreeDaysValueSensor(
            coordinator,
            object_id="do_degree_days_reference_daily",
            name="DO Degree Days Reference Daily",
            value_getter=lambda sensor: sensor.record.get("reference_degree_days"),
            unit="dd",
            icon="mdi:compare",
        ),
        DummyOSDegreeDaysValueSensor(
            coordinator,
            object_id="do_degree_days_weighted_reference_daily",
            name="DO Degree Days Weighted Reference Daily",
            value_getter=lambda sensor: sensor.record.get("reference_weighted_degree_days"),
            unit="wdd",
            icon="mdi:compare-horizontal",
        ),
        DummyOSDegreeDaysValueSensor(
            coordinator,
            object_id="do_degree_days_difference",
            name="DO Degree Days Difference",
            value_getter=lambda sensor: sensor.record.get("degree_days_difference"),
            unit="dd",
            icon="mdi:delta",
        ),
        DummyOSDegreeDaysValueSensor(
            coordinator,
            object_id="do_degree_days_weighted_difference",
            name="DO Degree Days Weighted Difference",
            value_getter=lambda sensor: sensor.record.get("weighted_degree_days_difference"),
            unit="wdd",
            icon="mdi:delta",
        ),
        DummyOSDegreeDaysLastDaySensor(coordinator),
    ]
