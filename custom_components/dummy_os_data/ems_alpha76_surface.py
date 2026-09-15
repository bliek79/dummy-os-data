"""Thin Home Assistant surface over the copied EMS alpha76 runtime.

This module contains no EMS policy.  It preserves the current Dummy OS Energy
entity identities where practical, but all manual plan values are read from and
written to the exact vendored alpha76 ``AnkerEmsPlanStore``.  Scheduler, Safety,
Controller and Execution presentation reads only ``DummyOSEmsAlpha76Runtime``.

The surface is deliberately non-actuating.  A write may request a fresh shadow
evaluation, but this module never calls the alpha76 execution controller.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.datetime import DateTimeEntity
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NAME, VERSION
from .ems_alpha76.const import PLAN_SLOT_COUNT
from .ems_alpha76_runtime import DummyOSEmsAlpha76Runtime, get_ems_alpha76_runtime

SOURCE_TAG = "0.0.1-alpha.76"


def _require_runtime(coordinator: Any) -> DummyOSEmsAlpha76Runtime:
    """Return the initialized alpha76 runtime or fail platform setup explicitly."""
    runtime = get_ems_alpha76_runtime(coordinator)
    if runtime is None:
        raise RuntimeError("Dummy OS EMS alpha76 shadow runtime is not initialized")
    return runtime


def _device_info() -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, "main")},
        name=NAME,
        manufacturer="Dummy OS",
        model="Energy Platform",
        sw_version=VERSION,
    )


class _Alpha76PlanEntityMixin:
    """Shared event wiring for controls backed by the exact alpha76 Plan Store."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def _init_plan_entity(self, runtime: DummyOSEmsAlpha76Runtime, slot: int) -> None:
        self.runtime = runtime
        self.plan_store = runtime.plan_store
        self.slot = slot
        self._remove_plan_listener = None
        self._attr_device_info = _device_info()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "ems_authority": "alpha76_plan_store",
            "alpha76_source_tag": SOURCE_TAG,
            "shadow_only": True,
            "physical_execution_authority": False,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_plan_listener = self.plan_store.add_listener(self._handle_plan_update)
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_plan_listener is not None:
            self._remove_plan_listener()
            self._remove_plan_listener = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_plan_update(self) -> None:
        self.async_write_ha_state()

    async def _refresh_shadow(self) -> None:
        """Refresh the old decision chain after a user edit; never execute it."""
        await self.runtime.async_request_refresh()


@dataclass(frozen=True)
class Alpha76NumberDefinition:
    unique_suffix: str
    store_field: str
    label: str
    minimum: float
    maximum: float
    step: float
    unit: str | None
    display_scale: float = 1.0


NUMBER_DEFINITIONS = (
    Alpha76NumberDefinition("power_w", "power_w", "Power", 100.0, 3500.0, 100.0, UnitOfPower.WATT),
    Alpha76NumberDefinition("target_soc_percent", "target_soc", "Target SOC", 5.0, 100.0, 1.0, PERCENTAGE),
    # Keep the already-published DO entity in minutes while storing the exact
    # alpha76 ``max_runtime_h`` value.  This is a unit-only presentation adapter.
    Alpha76NumberDefinition("max_runtime_minutes", "max_runtime_h", "Maximum Runtime", 15.0, 720.0, 15.0, UnitOfTime.MINUTES, 60.0),
    Alpha76NumberDefinition("max_start_delay_minutes", "max_start_delay_min", "Maximum Start Delay", 1.0, 120.0, 1.0, UnitOfTime.MINUTES),
)


class DummyOSAlpha76PlanNumber(_Alpha76PlanEntityMixin, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, runtime: DummyOSEmsAlpha76Runtime, slot: int, definition: Alpha76NumberDefinition) -> None:
        self._init_plan_entity(runtime, slot)
        self.definition = definition
        self._attr_name = f"DO Plan {slot} {definition.label}"
        self._attr_unique_id = f"do_plan_{slot}_{definition.unique_suffix}"
        self._attr_suggested_object_id = self._attr_unique_id
        self._attr_native_min_value = definition.minimum
        self._attr_native_max_value = (
            float(max(runtime.max_charge_power_w, runtime.max_discharge_power_w))
            if definition.store_field == "power_w"
            else definition.maximum
        )
        self._attr_native_step = definition.step
        self._attr_native_unit_of_measurement = definition.unit

    @property
    def native_value(self) -> float:
        raw = self.plan_store.get_value(self.slot, self.definition.store_field)
        return float(raw) * self.definition.display_scale

    async def async_set_native_value(self, value: float) -> None:
        maximum = self.native_max_value
        if self.definition.store_field == "power_w":
            action = self.plan_store.get_value(self.slot, "action")
            maximum = float(
                self.runtime.max_discharge_power_w
                if action == "ontladen"
                else self.runtime.max_charge_power_w
            )
        value = max(self.native_min_value, min(maximum, float(value)))
        steps = round((value - self.native_min_value) / self.native_step)
        value = self.native_min_value + steps * self.native_step
        store_value = value / self.definition.display_scale
        await self.plan_store.async_set_value(self.slot, self.definition.store_field, store_value)
        await self._refresh_shadow()


class DummyOSAlpha76PlanStart(_Alpha76PlanEntityMixin, DateTimeEntity):
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, runtime: DummyOSEmsAlpha76Runtime, slot: int) -> None:
        self._init_plan_entity(runtime, slot)
        self._attr_name = f"DO Plan {slot} Start"
        self._attr_unique_id = f"do_plan_{slot}_start_time"
        self._attr_suggested_object_id = self._attr_unique_id

    @property
    def native_value(self) -> datetime | None:
        raw = self.plan_store.get_value(self.slot, "start_time")
        if not raw:
            return None
        parsed = dt_util.parse_datetime(str(raw))
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return dt_util.as_local(parsed)

    async def async_set_value(self, value: datetime) -> None:
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        await self.plan_store.async_set_value(self.slot, "start_time", value)
        await self._refresh_shadow()


class DummyOSAlpha76PlanSelect(_Alpha76PlanEntityMixin, SelectEntity):
    _attr_icon = "mdi:battery-sync-outline"

    def __init__(
        self,
        runtime: DummyOSEmsAlpha76Runtime,
        slot: int,
        field: str,
        label: str,
        options: list[str],
        unique_suffix: str,
    ) -> None:
        self._init_plan_entity(runtime, slot)
        self.field = field
        self._attr_name = f"DO Plan {slot} {label}"
        self._attr_unique_id = f"do_plan_{slot}_{unique_suffix}"
        self._attr_suggested_object_id = self._attr_unique_id
        self._attr_options = options

    @property
    def current_option(self) -> str | None:
        value = self.plan_store.get_value(self.slot, self.field)
        return str(value) if value in self.options else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError(f"Unsupported {self.field}: {option}")
        await self.plan_store.async_set_value(self.slot, self.field, option)
        await self._refresh_shadow()


class _Alpha76RuntimeEntityMixin:
    """Read-only presentation of values already produced by alpha76."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def _init_runtime_entity(self, runtime: DummyOSEmsAlpha76Runtime) -> None:
        self.runtime = runtime
        self._remove_runtime_listener = None
        self._attr_device_info = _device_info()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_runtime_listener = self.runtime.async_add_listener(self._handle_runtime_update)
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_runtime_listener is not None:
            self._remove_runtime_listener()
            self._remove_runtime_listener = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    def _shadow_attrs(self) -> dict[str, Any]:
        return {
            "ems_authority": "alpha76_runtime",
            "alpha76_source_tag": SOURCE_TAG,
            "shadow_only": True,
            "simulation_mode": True,
            "physical_execution_authority": False,
            "alpha76_physical_autostart_wired": False,
        }


class DummyOSAlpha76RuntimeSensor(_Alpha76RuntimeEntityMixin, SensorEntity):
    def __init__(
        self,
        runtime: DummyOSEmsAlpha76Runtime,
        *,
        name: str,
        unique_id: str,
        value_key: str,
        attrs: tuple[str, ...],
        default: str = "initializing",
    ) -> None:
        self._init_runtime_entity(runtime)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_suggested_object_id = unique_id
        self.value_key = value_key
        self.attr_keys = attrs
        self.default = default

    @property
    def native_value(self) -> str:
        return str(self.runtime.data.get(self.value_key) or self.default)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._shadow_attrs()
        result.update({key: self.runtime.data.get(key) for key in self.attr_keys})
        return result


class DummyOSAlpha76PlanStatusSensor(_Alpha76RuntimeEntityMixin, SensorEntity):
    def __init__(self, runtime: DummyOSEmsAlpha76Runtime, slot: int) -> None:
        self._init_runtime_entity(runtime)
        self.slot = slot
        self._attr_name = f"DO Plan {slot} Status"
        self._attr_unique_id = f"do_plan_{slot}_status"
        self._attr_suggested_object_id = self._attr_unique_id

    def _detail(self) -> dict[str, Any]:
        slots = self.runtime.data.get("scheduler_slots", {}) or {}
        return dict(slots.get(self.slot) or slots.get(str(self.slot)) or self.plan_store_value())

    def plan_store_value(self) -> dict[str, Any]:
        return self.runtime.plan_store.get_plan(self.slot)

    @property
    def native_value(self) -> str:
        detail = self._detail()
        return str(detail.get("status") or detail.get("lifecycle_status") or "concept")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._shadow_attrs()
        result.update(self._detail())
        return result


class DummyOSAlpha76RuntimeBinarySensor(_Alpha76RuntimeEntityMixin, BinarySensorEntity):
    def __init__(
        self,
        runtime: DummyOSEmsAlpha76Runtime,
        *,
        name: str,
        unique_id: str,
        state_key: str,
        attrs: tuple[str, ...],
        alias_of: str | None = None,
    ) -> None:
        self._init_runtime_entity(runtime)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_suggested_object_id = unique_id
        self.state_key = state_key
        self.attr_keys = attrs
        self.alias_of = alias_of

    @property
    def is_on(self) -> bool:
        return self.runtime.data.get(self.state_key) is True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._shadow_attrs()
        result.update({key: self.runtime.data.get(key) for key in self.attr_keys})
        if self.alias_of:
            result["compatibility_alias_of"] = self.alias_of
        return result


def build_alpha76_plan_number_entities(coordinator: Any) -> list[NumberEntity]:
    runtime = _require_runtime(coordinator)
    return [
        DummyOSAlpha76PlanNumber(runtime, slot, definition)
        for slot in range(1, PLAN_SLOT_COUNT + 1)
        for definition in NUMBER_DEFINITIONS
    ]


def build_alpha76_plan_datetime_entities(coordinator: Any) -> list[DateTimeEntity]:
    runtime = _require_runtime(coordinator)
    return [DummyOSAlpha76PlanStart(runtime, slot) for slot in range(1, PLAN_SLOT_COUNT + 1)]


def build_alpha76_plan_select_entities(coordinator: Any) -> list[SelectEntity]:
    runtime = _require_runtime(coordinator)
    entities: list[SelectEntity] = []
    for slot in range(1, PLAN_SLOT_COUNT + 1):
        entities.extend(
            [
                DummyOSAlpha76PlanSelect(runtime, slot, "action", "Action", ["geen", "laden", "ontladen"], "action"),
                DummyOSAlpha76PlanSelect(runtime, slot, "execution_mode", "Mode", ["direct", "gepland"], "execution_mode"),
            ]
        )
    return entities


def build_alpha76_status_sensors(coordinator: Any) -> list[SensorEntity]:
    runtime = _require_runtime(coordinator)
    return [
        DummyOSAlpha76RuntimeSensor(
            runtime,
            name="DO Plan Scheduler",
            unique_id="do_plan_scheduler",
            value_key="scheduler_status",
            attrs=("scheduler_selected_slot", "scheduler_selected_action", "scheduler_selected_execution_mode", "scheduler_selected_start_time", "scheduler_next_future_slot", "scheduler_next_future_start", "scheduler_slots"),
        ),
        DummyOSAlpha76RuntimeSensor(
            runtime,
            name="DO Plan Safety",
            unique_id="do_plan_safety",
            value_key="safety_status",
            attrs=("safety_selected_slot", "safety_reason", "safety_reasons", "safety_warnings"),
        ),
        DummyOSAlpha76RuntimeSensor(
            runtime,
            name="DO Plan Execution Preview",
            unique_id="do_plan_execution_preview",
            value_key="controller_status",
            attrs=("controller_ready", "controller_selected_slot", "controller_action", "controller_power_w", "controller_target_soc", "controller_max_runtime_h", "controller_execution_mode", "controller_reason", "execution_active", "execution_status", "execution_reason"),
        ),
        *[DummyOSAlpha76PlanStatusSensor(runtime, slot) for slot in range(1, PLAN_SLOT_COUNT + 1)],
    ]


def build_alpha76_binary_sensors(coordinator: Any) -> list[BinarySensorEntity]:
    runtime = _require_runtime(coordinator)
    return [
        DummyOSAlpha76RuntimeBinarySensor(
            runtime,
            name="DO Plan Scheduler Ready",
            unique_id="do_plan_scheduler_ready",
            state_key="scheduler_ready",
            attrs=("scheduler_status", "scheduler_selected_slot", "scheduler_selected_action", "scheduler_selected_execution_mode"),
        ),
        DummyOSAlpha76RuntimeBinarySensor(
            runtime,
            name="DO Plan Execution Preview Ready",
            unique_id="do_plan_execution_preview_ready",
            state_key="controller_ready",
            attrs=("controller_status", "controller_selected_slot", "controller_action", "controller_reason", "safety_status", "safety_safe"),
            alias_of="alpha76_controller_ready",
        ),
        DummyOSAlpha76RuntimeBinarySensor(
            runtime,
            name="DO Plan Safety Safe",
            unique_id="do_plan_safety_safe",
            state_key="safety_safe",
            attrs=("safety_status", "safety_reason", "safety_selected_slot"),
        ),
        DummyOSAlpha76RuntimeBinarySensor(
            runtime,
            name="DO Plan Controller Ready",
            unique_id="do_plan_controller_ready",
            state_key="controller_ready",
            attrs=("controller_status", "controller_selected_slot", "controller_action", "controller_reason"),
        ),
        DummyOSAlpha76RuntimeBinarySensor(
            runtime,
            name="DO Plan Execution Active",
            unique_id="do_plan_execution_active",
            state_key="execution_active",
            attrs=("execution_status", "execution_reason", "execution_slot", "execution_action", "execution_power_w", "execution_target_soc"),
        ),
    ]
