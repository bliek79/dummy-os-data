"""Canonical energy-flow input sensors for Dummy OS Data."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import Event, EventStateChangedData, State, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_BATTERY_CHARGE_POWER_ENTITY,
    CONF_BATTERY_DISCHARGE_POWER_ENTITY,
    CONF_DATA_SOLAR_POWER_ENTITY,
    CONF_GRID_EXPORT_POWER_ENTITY,
    CONF_GRID_IMPORT_POWER_ENTITY,
    DOMAIN,
    NAME,
    VERSION,
)
from .coordinator import DummyOSHomeDataCoordinator

SOURCE_DEFINITIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        CONF_GRID_IMPORT_POWER_ENTITY,
        "do_data_grid_import_power",
        "DO Data Grid Import Power",
        "mdi:transmission-tower-import",
    ),
    (
        CONF_GRID_EXPORT_POWER_ENTITY,
        "do_data_grid_export_power",
        "DO Data Grid Export Power",
        "mdi:transmission-tower-export",
    ),
    (
        CONF_DATA_SOLAR_POWER_ENTITY,
        "do_data_solar_power",
        "DO Data Solar Power",
        "mdi:solar-power",
    ),
    (
        CONF_BATTERY_CHARGE_POWER_ENTITY,
        "do_data_battery_charge_power",
        "DO Data Battery Charge Power",
        "mdi:battery-arrow-up-outline",
    ),
    (
        CONF_BATTERY_DISCHARGE_POWER_ENTITY,
        "do_data_battery_discharge_power",
        "DO Data Battery Discharge Power",
        "mdi:battery-arrow-down-outline",
    ),
)


def source_power_magnitude_w(state: State | None) -> float | None:
    """Return one positive power-flow magnitude in watts."""
    if state is None or state.state in {"unknown", "unavailable", "none", ""}:
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None

    unit = state.attributes.get("unit_of_measurement")
    if unit == "kW":
        value *= 1000.0
    elif unit not in {"W", None}:
        return None

    # Separate import/export/charge/discharge sources represent magnitudes.
    # A negative value therefore indicates invalid source semantics and must
    # never be silently converted with abs().
    if value < 0:
        return None
    return value


class DummyOSDataPowerBaseSensor(SensorEntity):
    """Base entity for canonical Dummy OS Data power-flow sensors."""

    _attr_should_poll = False
    _attr_has_entity_name = False
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

    def _configured_entity(self, key: str) -> str | None:
        return self.coordinator.entry.options.get(
            key,
            self.coordinator.entry.data.get(key),
        )

    def _source_state(self, key: str) -> State | None:
        entity_id = self._configured_entity(key)
        return self.coordinator.hass.states.get(entity_id) if entity_id else None

    def _source_value(self, key: str) -> float | None:
        return source_power_magnitude_w(self._source_state(key))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        entities = [entity_id for _, entity_id in self._source_entities() if entity_id]
        if entities:
            self._remove_listener = async_track_state_change_event(
                self.coordinator.hass,
                entities,
                self._handle_source_update,
            )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_source_update(self, event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    def _source_entities(self) -> list[tuple[str, str | None]]:
        raise NotImplementedError


class DummyOSDataSourcePowerSensor(DummyOSDataPowerBaseSensor):
    """One normalized positive source-flow magnitude."""

    def __init__(
        self,
        coordinator: DummyOSHomeDataCoordinator,
        config_key: str,
        object_id: str,
        name: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self.config_key = config_key
        self._attr_name = name
        self._attr_unique_id = object_id
        self._attr_suggested_object_id = object_id
        self._attr_icon = icon

    def _source_entities(self) -> list[tuple[str, str | None]]:
        return [(self.config_key, self._configured_entity(self.config_key))]

    @property
    def available(self) -> bool:
        return self._source_value(self.config_key) is not None

    @property
    def native_value(self) -> float | None:
        value = self._source_value(self.config_key)
        return round(value, 3) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        entity_id = self._configured_entity(self.config_key)
        state = self._source_state(self.config_key)
        raw_state = state.state if state is not None else None
        return {
            "source_entity": entity_id,
            "source_unit": state.attributes.get("unit_of_measurement") if state else None,
            "source_state": raw_state,
            "source_available": self.available,
            "normalization": "positive_power_magnitude_to_w",
            "negative_source_values_allowed": False,
        }


class DummyOSDataHomePowerSensor(DummyOSDataPowerBaseSensor):
    """Canonical Home Power derived from the complete local power balance."""

    _attr_name = "DO Data Home Power"
    _attr_unique_id = "do_data_home_power"
    _attr_suggested_object_id = "do_data_home_power"
    _attr_icon = "mdi:home-lightning-bolt-outline"

    def _source_entities(self) -> list[tuple[str, str | None]]:
        return [
            (key, self._configured_entity(key))
            for key, _, _, _ in SOURCE_DEFINITIONS
        ]

    def _values(self) -> dict[str, float | None]:
        return {
            key: self._source_value(key)
            for key, _, _, _ in SOURCE_DEFINITIONS
        }

    @property
    def available(self) -> bool:
        return all(value is not None for value in self._values().values())

    @property
    def native_value(self) -> float | None:
        values = self._values()
        if any(value is None for value in values.values()):
            return None

        grid_import = values[CONF_GRID_IMPORT_POWER_ENTITY]
        grid_export = values[CONF_GRID_EXPORT_POWER_ENTITY]
        solar = values[CONF_DATA_SOLAR_POWER_ENTITY]
        battery_charge = values[CONF_BATTERY_CHARGE_POWER_ENTITY]
        battery_discharge = values[CONF_BATTERY_DISCHARGE_POWER_ENTITY]
        assert grid_import is not None
        assert grid_export is not None
        assert solar is not None
        assert battery_charge is not None
        assert battery_discharge is not None

        home_power = (
            solar
            + grid_import
            + battery_discharge
            - grid_export
            - battery_charge
        )
        return round(home_power, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        values = self._values()
        missing = [key for key, value in values.items() if value is None]
        return {
            "formula": "solar + grid_import + battery_discharge - grid_export - battery_charge",
            "source_entities": {
                key: self._configured_entity(key)
                for key, _, _, _ in SOURCE_DEFINITIONS
            },
            "source_values_w": values,
            "missing_sources": missing,
            "canonical_layer": "dummy_os_data",
            "reference_entity": "sensor.home_power",
            "reference_only": True,
        }


def build_home_input_sensors(
    coordinator: DummyOSHomeDataCoordinator,
) -> list[SensorEntity]:
    """Build the definitive canonical Data energy-flow sensor set."""
    entities: list[SensorEntity] = [
        DummyOSDataSourcePowerSensor(
            coordinator,
            config_key,
            object_id,
            name,
            icon,
        )
        for config_key, object_id, name, icon in SOURCE_DEFINITIONS
    ]
    entities.append(DummyOSDataHomePowerSensor(coordinator))
    return entities
