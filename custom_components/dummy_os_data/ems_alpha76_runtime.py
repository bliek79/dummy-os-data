"""Full Dummy OS EMS alpha76 runtime fed by Dummy OS Data forecasts.

The vendored ``ems_alpha76`` package is the functional authority.  This runtime
replaces only the old forecast ingestion: it builds the current Dummy OS Data
15-minute/72-hour input contract, adapts that contract to the exact alpha76
forecast schema and then runs the original EMS chain unchanged.

Physical automatic execution is intentionally *not* auto-started here.  The
original Execution Controller is instantiated and fully evaluated/testable, but
no listener in this module calls ``async_execute_automatic_plan``.  Operational
cutover is a later, explicit gate after parity and live-shadow validation.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .ems_alpha76.action_controller import AnkerEmsActionController
from .ems_alpha76.coordinator import AnkerEmsCoordinator
from .ems_alpha76.execution import AnkerEmsExecutionController
from .ems_alpha76.physical_test import AnkerEmsPhysicalTestController
from .ems_alpha76.plan_store import AnkerEmsPlanStore
from .ems_alpha76.planner_action_bridge import build_planner_action_bridge
from .ems_alpha76.prestart_validator import AnkerEmsPreStartValidator
from .ems_alpha76.safety_guard import AnkerEmsSafetyGuard
from .ems_alpha76.scheduler import AnkerEmsScheduler
from .ems_alpha76.source_monitor import AnkerEmsSourceMonitor
from .ems_alpha76.const import (
    ABSOLUTE_MAX_CHARGE_POWER_W,
    ABSOLUTE_MAX_DISCHARGE_POWER_W,
    CONF_ACTION_DIRECTION_ENTITY,
    CONF_CHARGE_EFFICIENCY_PERCENT,
    CONF_CHARGE_POWER_ENTITY,
    CONF_DEVICE_STATUS_ENTITY,
    CONF_DISCHARGE_EFFICIENCY_PERCENT,
    CONF_DISCHARGE_POWER_ENTITY,
    CONF_ELECTRICAL_PROFILE,
    CONF_GRID_EXPORT_POWER_ENTITY,
    CONF_GRID_IMPORT_POWER_ENTITY,
    CONF_MAX_CHARGE_POWER_W,
    CONF_MAX_DISCHARGE_POWER_W,
    CONF_MINIMUM_TRADE_MARGIN,
    CONF_OPERATING_MODE_ENTITY,
    CONF_POWER_SETPOINT_ENTITY,
    CONF_SIMULATION_MODE,
    CONF_SOC_ENTITY,
    CONF_SOFTWARE_RESERVE_PERCENT,
    CONF_SOLAR_POWER_ENTITY,
    DEFAULT_CHARGE_EFFICIENCY_PERCENT,
    DEFAULT_DISCHARGE_EFFICIENCY_PERCENT,
    DEFAULT_ELECTRICAL_PROFILE,
    DEFAULT_MINIMUM_TRADE_MARGIN,
    DEFAULT_SHARED_MAX_POWER_W,
    DEFAULT_SOFTWARE_RESERVE_PERCENT,
    ELECTRICAL_PROFILE_SHARED,
)
from .ems_alpha76_adapter import (
    forecast_from_input,
    planner_reference,
    run_energy_need,
    run_plan72,
    run_preview,
)
from .planner_time_runtime import read_soc_bridge
from .do_plan_soc_contract_sensor import get_do_plan_soc_contract_runtime

_LOGGER = logging.getLogger(__name__)
_RUNTIME_ATTR = "_dummy_os_ems_alpha76_runtime"
_OLD_DOMAIN = "anker_ems"


class DummyOSEmsAlpha76Runtime(AnkerEmsCoordinator):
    """Original alpha76 EMS chain with Dummy OS Data as forecast source."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, host: Any) -> None:
        self.host = host
        self._legacy_entry = self._find_legacy_entry(hass)

        plan_store = AnkerEmsPlanStore(hass, entry.entry_id)
        scheduler = AnkerEmsScheduler(plan_store)
        safety_guard = AnkerEmsSafetyGuard()
        action_controller = AnkerEmsActionController()
        physical_test = AnkerEmsPhysicalTestController(hass, entry.entry_id)
        execution = AnkerEmsExecutionController(hass, entry.entry_id)
        source_monitor = AnkerEmsSourceMonitor(hass, entry.entry_id)

        super().__init__(
            hass,
            entry,
            plan_store,
            scheduler,
            safety_guard,
            action_controller,
            physical_test,
            execution,
            source_monitor,
        )
        physical_test.attach_coordinator(self)
        execution.attach_coordinator(self)
        self.update_interval = None
        self._host_unsub = None
        self._refresh_task = None
        self._runtime_initialized = False
        self._auto_execution_armed = False
        self._cached_72h_plan = None
        self._last_input_rows_signature = None
        self._last_planner_window_id = None

    @staticmethod
    def _find_legacy_entry(hass: HomeAssistant) -> ConfigEntry | None:
        entries = hass.config_entries.async_entries(_OLD_DOMAIN)
        if len(entries) == 1:
            return entries[0]
        if len(entries) > 1:
            _LOGGER.warning(
                "Multiple legacy anker_ems entries found; alpha76 parity runtime will not inherit controls"
            )
        return None

    def _legacy_setting(self, key: str, default: Any = None) -> Any:
        legacy = self._legacy_entry
        if legacy is not None:
            if key in legacy.options:
                return legacy.options[key]
            if key in legacy.data:
                return legacy.data[key]
        if key in self.entry.options:
            return self.entry.options[key]
        if key in self.entry.data:
            return self.entry.data[key]
        return default

    @property
    def simulation_mode(self) -> bool:
        # Recovery releases remain non-actuating regardless of the old setting.
        # The inherited value is exposed separately for diagnostics.
        return True

    @property
    def inherited_simulation_mode(self) -> bool:
        return bool(self._legacy_setting(CONF_SIMULATION_MODE, True))

    @property
    def electrical_profile(self) -> str:
        return str(self._legacy_setting(CONF_ELECTRICAL_PROFILE, DEFAULT_ELECTRICAL_PROFILE))

    def _power_limit(self, key: str, absolute: int) -> int:
        fallback = DEFAULT_SHARED_MAX_POWER_W if self.electrical_profile == ELECTRICAL_PROFILE_SHARED else absolute
        raw = self._legacy_setting(key, fallback)
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            value = fallback
        cap = DEFAULT_SHARED_MAX_POWER_W if self.electrical_profile == ELECTRICAL_PROFILE_SHARED else absolute
        return max(100, min(cap, value))

    @property
    def max_charge_power_w(self) -> int:
        return self._power_limit(CONF_MAX_CHARGE_POWER_W, ABSOLUTE_MAX_CHARGE_POWER_W)

    @property
    def max_discharge_power_w(self) -> int:
        return self._power_limit(CONF_MAX_DISCHARGE_POWER_W, ABSOLUTE_MAX_DISCHARGE_POWER_W)

    def _entity_id(self, key: str, default: str | None = None) -> str | None:
        value = self._legacy_setting(key, default)
        return str(value) if value else None

    @property
    def control_entity_ids(self) -> dict[str, str | None]:
        return {
            "operating_mode": self._entity_id(CONF_OPERATING_MODE_ENTITY),
            "action_direction": self._entity_id(CONF_ACTION_DIRECTION_ENTITY),
            "power_setpoint": self._entity_id(CONF_POWER_SETPOINT_ENTITY),
        }

    def _live_number(self, key: str) -> float | None:
        entity_id = self._entity_id(key)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in {"unknown", "unavailable", "none", ""}:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _live_state(self, key: str) -> Any:
        entity_id = self._entity_id(key)
        state = self.hass.states.get(entity_id) if entity_id else None
        return None if state is None else state.state

    async def async_initialize_shadow(self) -> None:
        """Load original persistent runtimes and subscribe to forecast changes."""
        if self._runtime_initialized:
            return
        await self.plan_store.async_load()
        await self.physical_test.async_load()
        await self.execution.async_load()
        await self.source_monitor.async_load()
        # Never recover into a physical command from the recovery integration.
        # If copied storage ever reports an interrupted action, clear it via the
        # original safe-stop routine before exposing the runtime as initialized.
        await self.physical_test.async_recover_if_needed()
        await self.execution.async_recover_if_needed()
        self._runtime_initialized = True

        def host_changed() -> None:
            if self._refresh_task is not None and not self._refresh_task.done():
                return
            self._refresh_task = self.hass.async_create_task(
                self.async_request_refresh(), "Dummy OS EMS alpha76 shadow refresh"
            )

        self._host_unsub = self.host.async_add_listener(host_changed)
        await self.async_request_refresh()

    async def async_shutdown_shadow(self) -> None:
        if self._host_unsub is not None:
            self._host_unsub()
            self._host_unsub = None
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
        if self.execution.data.get("active"):
            await self.execution.async_stop("integration_unload", emergency=True)
        if self.physical_test.data.get("active"):
            await self.physical_test.async_stop("integration_unload", emergency=True)

    def _source_monitor_specs_from_input(self, input_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
        rows = input_result.get("rows") or []
        home = [
            {"start": row.get("start"), "home_kwh": row.get("home_kwh")}
            for row in rows if isinstance(row, dict)
        ]
        solar = [
            {"start": row.get("start"), "solar_kwh": row.get("solar_kwh")}
            for row in rows if isinstance(row, dict)
        ]
        prices = [
            {
                "start": row.get("start"),
                "import_price": row.get("import_price"),
                "export_price": row.get("export_price"),
            }
            for row in rows if isinstance(row, dict)
        ]
        return {
            "home_forecast": {"entity_ids": [], "content": home},
            "solcast_forecast": {"entity_ids": [], "content": solar},
            "stroomvoorspeller": {"entity_ids": [], "content": prices},
            "energyzero_prices": {"entity_ids": [], "content": prices},
            "price_forecast": {"entity_ids": [], "content": prices},
        }

    async def _build_new_input(self) -> tuple[dict[str, Any], dict[str, Any], float | None]:
        # Lazy import avoids creating a platform import cycle during integration setup.
        from .sensor import _build_plan_input_from_snapshot, _planner_runtime_snapshot

        reference = dt_util.utcnow()
        soc_contract = get_do_plan_soc_contract_runtime(self.host).result(now=reference)
        measured_soc = soc_contract.get("soc_percent")
        snapshot = _planner_runtime_snapshot(
            self.host, now=reference, soc_percent=measured_soc
        )
        bridge = read_soc_bridge(self.host, snapshot, soc_contract)
        snapshot["soc_bridge"] = bridge
        snapshot["soc_percent"] = (
            bridge.get("planner_start_soc_percent") if bridge.get("valid") else None
        )
        input_result = await self.hass.async_add_executor_job(
            _build_plan_input_from_snapshot, snapshot
        )
        return input_result, bridge, measured_soc

    async def _async_update_data(self) -> dict[str, Any]:
        input_result, soc_bridge, measured_soc = await self._build_new_input()
        planner_soc = (
            soc_bridge.get("planner_start_soc_percent")
            if isinstance(soc_bridge, dict) and soc_bridge.get("valid") is True
            else None
        )
        forecast_ready = bool(
            input_result.get("status") == "ready" and input_result.get("valid") is True
        )

        data: dict[str, Any] = {
            "simulation_mode": True,
            "alpha76_inherited_simulation_mode": self.inherited_simulation_mode,
            "alpha76_runtime_shadow_only": True,
            "alpha76_physical_autostart_wired": False,
            "alpha76_source_tag": "0.0.1-alpha.76",
            "alpha76_forecast_source": "dummy_os_data",
            "alpha76_input_resolution_minutes": 15,
            "alpha76_input_slot_count": 288,
            "electrical_profile": self.electrical_profile,
            "max_charge_power_w": self.max_charge_power_w,
            "max_discharge_power_w": self.max_discharge_power_w,
            "battery_capacity_kwh": 7.2,
            "charge_efficiency_percent": float(
                self._legacy_setting(CONF_CHARGE_EFFICIENCY_PERCENT, DEFAULT_CHARGE_EFFICIENCY_PERCENT)
            ),
            "discharge_efficiency_percent": float(
                self._legacy_setting(CONF_DISCHARGE_EFFICIENCY_PERCENT, DEFAULT_DISCHARGE_EFFICIENCY_PERCENT)
            ),
            "minimum_trade_margin": float(
                self._legacy_setting(CONF_MINIMUM_TRADE_MARGIN, DEFAULT_MINIMUM_TRADE_MARGIN)
            ),
            "software_reserve_percent": float(
                self._legacy_setting(CONF_SOFTWARE_RESERVE_PERCENT, DEFAULT_SOFTWARE_RESERVE_PERCENT)
            ),
            "control_path_configured": all(
                bool(self.control_entity_ids.get(key))
                for key in ("operating_mode", "action_direction", "power_setpoint")
            ),
            "soc": measured_soc,
            "planner_start_soc": planner_soc,
            "soc_bridge": deepcopy(soc_bridge),
            "device_status": self._live_state(CONF_DEVICE_STATUS_ENTITY),
            "charge_power_w": self._live_number(CONF_CHARGE_POWER_ENTITY),
            "discharge_power_w": self._live_number(CONF_DISCHARGE_POWER_ENTITY),
            "grid_import_power_w": self._live_number(CONF_GRID_IMPORT_POWER_ENTITY),
            "grid_export_power_w": self._live_number(CONF_GRID_EXPORT_POWER_ENTITY),
            "solar_power_w": self._live_number(CONF_SOLAR_POWER_ENTITY),
            "operating_mode": self._live_state(CONF_OPERATING_MODE_ENTITY),
            "action_direction": self._live_state(CONF_ACTION_DIRECTION_ENTITY),
            "power_setpoint_w": self._live_number(CONF_POWER_SETPOINT_ENTITY),
            "forecast_ready": forecast_ready,
            "forecast_status": "ready" if forecast_ready else "waiting_for_sources",
            "forecast_horizon_hours": 72,
            "forecast_complete_hours": sum(
                1 for row in input_result.get("rows", [])
                if isinstance(row, dict) and row.get("fully_valid") is True
            ),
            "forecast_missing_sources": list(input_result.get("blockers") or []),
            "forecast_input_status": input_result.get("status"),
            "forecast_input_rows_signature": input_result.get("rows_signature"),
            "forecast_time_contract": deepcopy(input_result.get("time_contract")),
        }

        try:
            forecast = forecast_from_input(input_result)
        except (TypeError, ValueError) as err:
            data.update({
                "forecast": [],
                "forecast_ready": False,
                "forecast_status": "adapter_blocked",
                "forecast_missing_sources": ["alpha76_forecast_adapter_invalid"],
                "alpha76_adapter_error": str(err),
            })
            return data

        data["forecast"] = forecast
        data["forecast_price_hours"] = sum(1 for row in forecast if row.get("import_price") is not None)
        data["forecast_home_hours"] = sum(1 for row in forecast if row.get("home_consumption_kwh") is not None)
        data["forecast_solar_hours"] = sum(1 for row in forecast if row.get("solar_kwh") is not None)
        data.update(await self.source_monitor.async_observe(self._source_monitor_specs_from_input(input_result)))

        reserve_percent = float(
            self._legacy_setting(CONF_SOFTWARE_RESERVE_PERCENT, DEFAULT_SOFTWARE_RESERVE_PERCENT)
        )
        reference = planner_reference(input_result)
        energy_need = run_energy_need(
            input_result=input_result,
            soc_percent=planner_soc,
            safety_reserve_percent=reserve_percent,
            now=reference,
        )
        data.update(energy_need)
        data["energy_need_soc_time_basis"] = "planner_window_start_estimate"
        data["energy_need_measured_soc"] = measured_soc

        preview = run_preview(
            input_result=input_result,
            energy_need=energy_need,
            soc_percent=planner_soc,
            charge_efficiency_percent=data["charge_efficiency_percent"],
            discharge_efficiency_percent=data["discharge_efficiency_percent"],
            minimum_trade_margin=data["minimum_trade_margin"],
            max_charge_power_w=self.max_charge_power_w,
            now=reference,
        )
        data.update(preview)

        pre_cleanup_scheduler = self.scheduler.evaluate(
            self.max_charge_power_w, self.max_discharge_power_w
        )
        expired_slots = {
            int(slot)
            for slot, detail in (pre_cleanup_scheduler.get("scheduler_slots") or {}).items()
            if str((detail or {}).get("status") or "").lower() == "verlopen"
        }
        expired_release = await self.plan_store.async_release_expired_automatic_plans(expired_slots)
        data["auto_expired_release_changed"] = expired_release.get("changed", False)
        data["auto_expired_released_slots"] = expired_release.get("released_slots", [])

        scheduler_snapshot = self.scheduler.evaluate(
            self.max_charge_power_w, self.max_discharge_power_w
        )
        data.update(scheduler_snapshot)

        # Recompute when the authoritative input or planner window changes.
        rows_signature = input_result.get("rows_signature")
        window_id = (input_result.get("time_contract") or {}).get("window_id")
        if (
            self._cached_72h_plan is None
            or rows_signature != self._last_input_rows_signature
            or window_id != self._last_planner_window_id
        ):
            self._cached_72h_plan = run_plan72(
                input_result=input_result,
                energy_need=energy_need,
                planner_preview=preview,
                soc_percent=planner_soc,
                charge_efficiency_percent=data["charge_efficiency_percent"],
                discharge_efficiency_percent=data["discharge_efficiency_percent"],
                execution_buffer_percent=2.0,
                max_charge_power_w=self.max_charge_power_w,
                max_discharge_power_w=self.max_discharge_power_w,
                now=reference,
            )
            self._last_input_rows_signature = rows_signature
            self._last_planner_window_id = window_id
        data.update(deepcopy(self._cached_72h_plan or {}))
        data["auto_plan_72h_refresh_policy"] = "dummy_os_data_change_or_window_change"
        data["auto_plan_72h_refresh_cached"] = False

        bridge = build_planner_action_bridge(data)
        data.update(bridge)

        desired: dict[int, dict[str, Any]] = {}
        write_gate_open = bool(
            data.get("auto_bridge_valid")
            and data.get("forecast_ready")
            and not int(data.get("auto_bridge_invalid_candidate_count") or 0)
        )
        if write_gate_open:
            for proposal in data.get("auto_bridge_slot_preview") or []:
                if not proposal.get("plan_store_write_permitted"):
                    continue
                slot = proposal.get("suggested_slot")
                if isinstance(slot, int):
                    desired[slot] = proposal
            write_result = await self.plan_store.async_sync_automatic_plans(desired)
        else:
            write_result = {
                "changed": False, "written_slots": [], "cleared_slots": [],
                "skipped_slots": [], "preserved_due_gate_closed": True,
            }

        handoff_allowed: dict[int, str] = {}
        if write_gate_open:
            for proposal in data.get("auto_bridge_slot_preview") or []:
                if not proposal.get("scheduler_handoff_permitted"):
                    continue
                slot = proposal.get("suggested_slot")
                signature = proposal.get("planner_signature")
                if isinstance(slot, int) and isinstance(signature, str) and signature:
                    handoff_allowed[slot] = signature
        handoff_result = await self.plan_store.async_handoff_automatic_plans(
            handoff_allowed if write_gate_open else {}
        )
        data.update({
            "auto_bridge_plan_store_write_enabled": True,
            "auto_bridge_plan_store_write_gate_open": write_gate_open,
            "auto_bridge_plan_store_write_changed": write_result.get("changed", False),
            "auto_bridge_plan_store_written_slots": write_result.get("written_slots", []),
            "auto_bridge_plan_store_cleared_slots": write_result.get("cleared_slots", []),
            "auto_bridge_scheduler_handoff_enabled": True,
            "auto_bridge_scheduler_handoff_gate_open": write_gate_open,
            "auto_bridge_scheduler_handoff_changed": handoff_result.get("changed", False),
            "auto_bridge_scheduler_handoff_slots": handoff_result.get("handed_off_slots", []),
            # Hard recovery safety gate: copied planner is live, physical autostart is not.
            "auto_bridge_execution_enabled": False,
            "auto_bridge_observational_only": False,
        })

        data.update(self.scheduler.evaluate(self.max_charge_power_w, self.max_discharge_power_w))
        refreshed_bridge = build_planner_action_bridge(data)
        for key, value in refreshed_bridge.items():
            if key not in {
                "auto_bridge_plan_store_write_enabled",
                "auto_bridge_scheduler_handoff_enabled",
                "auto_bridge_execution_enabled",
                "auto_bridge_observational_only",
            }:
                data[key] = value

        data.update(AnkerEmsPreStartValidator().evaluate(data))
        data["physical_test_active"] = bool(self.physical_test.data.get("active"))
        data["execution_active"] = bool(self.execution.data.get("active"))
        data["execution_origin"] = self.execution.data.get("origin")
        data.update(self.safety_guard.evaluate_automatic_handoff(data))
        data.update(self.execution.evaluate_automatic_handoff(data))
        data.update(self.execution.evaluate_final_revalidation(data))
        data.update(self.execution.evaluate_mode_switch_transaction(data))

        # Reuse the original coordinator's exact final shadow-gate method.  The
        # arm is forced false in the recovery runtime, so this never authorizes
        # a physical command before cutover.
        self._auto_execution_armed = False
        data.update(AnkerEmsCoordinator._automatic_execution_shadow(self, data))
        data["auto_shadow_armed"] = False
        data["auto_shadow_execution_permitted"] = False
        data["auto_shadow_physical_control"] = False
        data["alpha76_physical_autostart_wired"] = False

        data.update(self.safety_guard.evaluate(data))
        data.update(self.action_controller.evaluate(data))
        for key, value in self.physical_test.data.items():
            data[f"physical_test_{key}"] = value
        for key, value in self.execution.data.items():
            data[f"execution_{key}"] = value
        return data


def get_ems_alpha76_runtime(coordinator: Any) -> DummyOSEmsAlpha76Runtime | None:
    runtime = getattr(coordinator, _RUNTIME_ATTR, None)
    return runtime if isinstance(runtime, DummyOSEmsAlpha76Runtime) else None


async def async_setup_ems_alpha76_runtime(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: Any
) -> DummyOSEmsAlpha76Runtime:
    runtime = get_ems_alpha76_runtime(coordinator)
    if runtime is not None:
        return runtime
    runtime = DummyOSEmsAlpha76Runtime(hass, entry, coordinator)
    setattr(coordinator, _RUNTIME_ATTR, runtime)
    # Old platform adapters expect this conventional coordinator location.
    hass.data.setdefault("dummy_os_data", {})[entry.entry_id] = runtime
    await runtime.async_initialize_shadow()
    return runtime
