"""Home Assistant surface for the G5 frozen-live A/B acceptance gate.

The runtime captures one real live Dummy OS Data planner input exactly once,
persists that frozen evidence, and evaluates it with ``ems_g5_live_parity``.
It does not write the Plan Store and never calls any physical service.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.storage import Store

from .const import DOMAIN, NAME, VERSION
from .ems_alpha76_adapter import (
    BATTERY_CAPACITY_KWH,
    EXECUTION_BUFFER_PERCENT,
    MIN_SOC_PERCENT,
)
from .ems_alpha76_runtime import DummyOSEmsAlpha76Runtime, get_ems_alpha76_runtime
from .ems_g5_live_parity import compare_frozen_live_snapshot

_STORE_VERSION = 1
_RUNTIME_ATTR = "_dummy_os_g5_live_parity_runtime"


class DummyOSG5LiveParityRuntime:
    """Persistent, strictly shadow-only G5 acceptance diagnostic."""

    def __init__(self, coordinator: Any, ems_runtime: DummyOSEmsAlpha76Runtime) -> None:
        self.coordinator = coordinator
        self.ems_runtime = ems_runtime
        self.hass = coordinator.hass
        self.entry_id = coordinator.entry.entry_id
        self._store: Store[dict[str, Any]] = Store(
            self.hass,
            _STORE_VERSION,
            f"{DOMAIN}.{self.entry_id}.g5_frozen_live_parity",
        )
        self.evidence: dict[str, Any] | None = None
        self.loaded = False
        self.persistence_error: str | None = None
        self._listeners: set[Callable[[], None]] = set()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)

        def remove() -> None:
            self._listeners.discard(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    async def async_ensure_loaded(self) -> None:
        if self.loaded:
            return
        raw = await self._store.async_load()
        if isinstance(raw, dict):
            self.evidence = deepcopy(raw)
        self.loaded = True
        self._notify()

    def _config_snapshot(self) -> dict[str, Any]:
        runtime = self.ems_runtime
        return {
            "battery_capacity_kwh": BATTERY_CAPACITY_KWH,
            "min_soc_percent": MIN_SOC_PERCENT,
            "software_reserve_percent": float(runtime.software_reserve_percent),
            "execution_buffer_percent": EXECUTION_BUFFER_PERCENT,
            "max_charge_power_w": int(runtime.max_charge_power_w),
            "max_discharge_power_w": int(runtime.max_discharge_power_w),
            "charge_efficiency_percent": float(runtime.charge_efficiency_percent),
            "discharge_efficiency_percent": float(runtime.discharge_efficiency_percent),
            "minimum_trade_margin": float(runtime.minimum_trade_margin),
            "electrical_profile": runtime.electrical_profile,
        }

    async def async_capture_and_compare(self) -> dict[str, Any]:
        """Capture one live planner state and run both A/B paths on that copy."""
        await self.async_ensure_loaded()
        input_result, soc_bridge, measured_soc = await self.ems_runtime._build_new_input()
        planner_soc = (
            soc_bridge.get("planner_start_soc_percent")
            if isinstance(soc_bridge, dict) and soc_bridge.get("valid") is True
            else None
        )
        frozen_snapshot = {
            "schema_version": 1,
            "captured_at": (input_result.get("time_contract") or {}).get("reference_time")
            or (input_result.get("time_contract") or {}).get("window_start"),
            "input_result": deepcopy(input_result),
            "input_rows_signature": input_result.get("rows_signature"),
            "time_contract": deepcopy(input_result.get("time_contract")),
            "measured_soc_percent": measured_soc,
            "planner_start_soc_percent": planner_soc,
            "soc_bridge": deepcopy(soc_bridge),
            "config": self._config_snapshot(),
            "profile": getattr(self.coordinator, "profile", None),
            "shadow_only": True,
            "physical_execution_authority": False,
        }
        result = await self.hass.async_add_executor_job(
            compare_frozen_live_snapshot, deepcopy(frozen_snapshot)
        )
        self.evidence = {
            "snapshot": frozen_snapshot,
            "result": result,
        }
        try:
            await self._store.async_save(deepcopy(self.evidence))
            self.persistence_error = None
        except Exception as err:  # pragma: no cover - HA storage fault path
            self.persistence_error = type(err).__name__
        self.loaded = True
        self._notify()
        return deepcopy(self.evidence)

    def state(self) -> str:
        if not self.loaded:
            return "initializing"
        if self.evidence is None:
            return "not_captured"
        result = self.evidence.get("result") or {}
        return str(result.get("status") or "blocked")

    def attributes(self) -> dict[str, Any]:
        evidence = self.evidence or {}
        snapshot = evidence.get("snapshot") or {}
        result = evidence.get("result") or {}
        return {
            "gate": "G5",
            "step": "G5.2_frozen_live_ab",
            "captured": bool(evidence),
            "captured_at": snapshot.get("captured_at"),
            "snapshot_fingerprint": result.get("snapshot_fingerprint"),
            "input_rows_signature": snapshot.get("input_rows_signature"),
            "window_start": (snapshot.get("time_contract") or {}).get("window_start"),
            "window_end": (snapshot.get("time_contract") or {}).get("window_end"),
            "measured_soc_percent": snapshot.get("measured_soc_percent"),
            "planner_start_soc_percent": snapshot.get("planner_start_soc_percent"),
            "profile": snapshot.get("profile"),
            "config": deepcopy(snapshot.get("config")),
            "exact_match": result.get("exact_match"),
            "difference_count": result.get("difference_count"),
            "differences": deepcopy(result.get("differences") or []),
            "blockers": deepcopy(result.get("blockers") or []),
            "golden_decision": deepcopy(result.get("golden_decision")),
            "copy_decision": deepcopy(result.get("copy_decision")),
            "golden_source": result.get("golden_source"),
            "copy_path": result.get("copy_path"),
            "persistence_error": self.persistence_error,
            "shadow_only": True,
            "simulation_mode": True,
            "physical_execution_authority": False,
            "service_calls_performed": False,
            "plan_store_mutated": False,
            "cutover_permitted": False,
        }


def get_g5_live_parity_runtime(coordinator: Any) -> DummyOSG5LiveParityRuntime:
    runtime = getattr(coordinator, _RUNTIME_ATTR, None)
    if isinstance(runtime, DummyOSG5LiveParityRuntime):
        return runtime
    ems_runtime = get_ems_alpha76_runtime(coordinator)
    if ems_runtime is None:
        raise RuntimeError("Dummy OS EMS alpha76 shadow runtime is not initialized")
    runtime = DummyOSG5LiveParityRuntime(coordinator, ems_runtime)
    setattr(coordinator, _RUNTIME_ATTR, runtime)
    return runtime


class DummyOSG5LiveParitySensor(SensorEntity):
    """Compact result surface for the frozen G5 evidence."""

    _attr_name = "DO EMS G5 Frozen Live Parity"
    _attr_unique_id = "do_ems_g5_frozen_live_parity"
    _attr_suggested_object_id = "do_ems_g5_frozen_live_parity"
    _attr_icon = "mdi:compare-horizontal"
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, runtime: DummyOSG5LiveParityRuntime) -> None:
        self.runtime = runtime
        self._remove_listener = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "main")},
            name=NAME,
            manufacturer="Dummy OS",
            model="Energy Platform",
            sw_version=VERSION,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_listener = self.runtime.add_listener(self._handle_update)
        await self.runtime.async_ensure_loaded()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        return self.runtime.state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.runtime.attributes()


def build_g5_live_parity_sensors(coordinator: Any) -> list[SensorEntity]:
    return [DummyOSG5LiveParitySensor(get_g5_live_parity_runtime(coordinator))]
