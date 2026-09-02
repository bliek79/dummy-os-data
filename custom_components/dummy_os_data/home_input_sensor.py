"""Canonical Home Power input sensors for Dummy OS Data."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import State, callback
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_HOME_POWER_POSITIVE_DIRECTION,
    DOMAIN,
    HOME_POWER_POSITIVE_CONSUMPTION,
    NAME,
    VERSION,
)
from .coordinator import DummyOSHomeDataCoordinator


def source_power_w(state: State | None) -> float | None:
    """Return the source power in watts without changing its sign."""
    if state is None or state.state in {"unknown", "unavailable", "none", ""}:
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None

    unit = state.attributes.get("unit_of_measurement")
    if unit == "kW":
        return value * 1000.0
    if unit in {"W", None}:
        return value
    return None


def normalized_home_power_w(
    raw_power_w: float | None,
    positive_direction: str,
) -> float | None:
    """Normalize Home Power so positive always means consumption/import."""
    if raw_power_w is None:
        return None
    if positive_direction == HOME_POWER_POSITIVE_CONSUMPTION:
        return raw_power_w
    return -raw_power_w


class DummyOSHomeInputBaseSensor(SensorEntity):
    """Base entity for canonical Home Power input sensors."""

    _attr_should_poll = False
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

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

    @property
    def available(self) -> bool:
        return self._raw_power_w is not None

    @property
    def _raw_power_w(self) -> float | None:
        return source_power_w(self.coordinator.source_state)

    @property
    def _positive_direction(self) -> str:
        return self.coordinator.entry.options.get(
            CONF_HOME_POWER_POSITIVE_DIRECTION,
            self.coordinator.entry.data.get(
                CONF_HOME_POWER_POSITIVE_DIRECTION,
                HOME_POWER_POSITIVE_CONSUMPTION,
            ),
        )

    @property
    def _normalized_power_w(self) -> float | None:
        return normalized_home_power_w(self._raw_power_w, self._positive_direction)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.source_state
        return {
            "source_entity": self.coordinator.source_entity,
            "source_unit": state.attributes.get("unit_of_measurement") if state else None,
            "positive_direction": self._positive_direction,
            "canonical_sign": "positive_consumption_negative_export",
            "source_available": self.available,
        }

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


class DummyOSInputHomePowerRawSensor(DummyOSHomeInputBaseSensor):
    """Selected Home Power source converted to W, with source sign untouched."""

    _attr_name = "Dummy OS Input Home Power Raw"
    _attr_unique_id = "do_input_home_power_raw"
    _attr_suggested_object_id = "do_input_home_power_raw"
    _attr_icon = "mdi:home-lightning-bolt"

    @property
    def native_value(self) -> float | None:
        value = self._raw_power_w
        return round(value, 3) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        attrs["normalization"] = "unit_to_w_only_sign_unchanged"
        return attrs


class DummyOSHomePowerSensor(DummyOSHomeInputBaseSensor):
    """Canonical signed Home Power: positive consumption, negative export."""

    _attr_name = "Dummy OS Home Power"
    _attr_unique_id = "do_home_power"
    _attr_suggested_object_id = "do_home_power"
    _attr_icon = "mdi:home-lightning-bolt-outline"

    @property
    def native_value(self) -> float | None:
        value = self._normalized_power_w
        return round(value, 3) if value is not None else None


class DummyOSHomeImportPowerSensor(DummyOSHomeInputBaseSensor):
    """Positive-only consumption/import component of canonical Home Power."""

    _attr_name = "Dummy OS Home Import Power"
    _attr_unique_id = "do_home_import_power"
    _attr_suggested_object_id = "do_home_import_power"
    _attr_icon = "mdi:transmission-tower-import"

    @property
    def native_value(self) -> float | None:
        value = self._normalized_power_w
        return round(max(value, 0.0), 3) if value is not None else None


class DummyOSHomeExportPowerSensor(DummyOSHomeInputBaseSensor):
    """Positive-only export component of canonical Home Power."""

    _attr_name = "Dummy OS Home Export Power"
    _attr_unique_id = "do_home_export_power"
    _attr_suggested_object_id = "do_home_export_power"
    _attr_icon = "mdi:transmission-tower-export"

    @property
    def native_value(self) -> float | None:
        value = self._normalized_power_w
        return round(max(-value, 0.0), 3) if value is not None else None


def build_home_input_sensors(
    coordinator: DummyOSHomeDataCoordinator,
) -> list[SensorEntity]:
    """Build the canonical Home Power sensor set."""
    return [
        DummyOSInputHomePowerRawSensor(coordinator),
        DummyOSHomePowerSensor(coordinator),
        DummyOSHomeImportPowerSensor(coordinator),
        DummyOSHomeExportPowerSensor(coordinator),
    ]
