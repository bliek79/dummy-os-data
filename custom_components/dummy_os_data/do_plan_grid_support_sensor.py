"""Home Assistant adapters for non-authoritative grid-support diagnostics.

Step 8B deliberately removes the former Alpha35 shadow Plan Store / Scheduler /
Safety / Execution / Manual Interface bundle from the active entity surface.
Only the grid-support diagnostic remains here. Operational EMS presentation is
provided by ``ems_alpha76_surface`` and reads the exact alpha76 runtime.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .do_plan_grid_support import build_do_plan_grid_support
from .planner_time_runtime import aligned_reference, subscribe_upstream


def _stable_material(value: Any) -> str:
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}:{_stable_material(value[k])}" for k in sorted(value)) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable_material(item) for item in value) + "]"
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return repr(value)


def build_plan_store_bridge_refresh_key(snapshot: dict[str, Any]) -> str:
    """Retain the historical stable-key helper for diagnostics/tests only.

    The Alpha35 Plan Store bridge itself is no longer instantiated in Step 8B.
    Keeping the pure helper avoids needless migration churn for diagnostic tests.
    """
    bridge = snapshot.get("soc_bridge")
    if isinstance(bridge, dict):
        snapshot = dict(snapshot)
        snapshot["soc_percent"] = bridge.get("measured_soc_percent")
        snapshot["soc_bridge"] = {
            key: bridge.get(key)
            for key in (
                "valid",
                "method",
                "charge_power_w",
                "discharge_power_w",
                "measured_soc_percent",
                "blockers",
                "projected_at",
            )
        }
    now = snapshot.get("now")
    if isinstance(now, datetime):
        now_utc = now.astimezone(timezone.utc)
        quarter = now_utc.replace(
            minute=(now_utc.minute // 15) * 15,
            second=0,
            microsecond=0,
        ).isoformat()
    else:
        quarter = repr(now)
    material = {
        "window_id": (snapshot.get("time_contract") or {}).get("window_id"),
        "soc_bridge": snapshot.get("soc_bridge"),
        "quarter": quarter,
        "profile": snapshot.get("profile"),
        "source_available": snapshot.get("source_available"),
        "soc_percent": snapshot.get("soc_percent"),
        "solar_status": snapshot.get("solar_status"),
        "prices_status": snapshot.get("prices_status"),
        "prices_freshness": snapshot.get("prices_freshness"),
        "records": snapshot.get("records"),
        "evaluations": snapshot.get("evaluations"),
        "horizon_daily_stats": snapshot.get("horizon_daily_stats"),
        "solar_points": snapshot.get("solar_points"),
        "price_points": snapshot.get("price_points"),
    }
    return hashlib.sha256(_stable_material(material).encode("utf-8")).hexdigest()


def _state_contract(hass: Any, unique_id: str) -> tuple[str | None, dict[str, Any]]:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id)
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in {"unknown", "unavailable", "none", "None", ""}:
        return entity_id, {
            "status": "unavailable",
            "valid": False,
            "blockers": [f"{unique_id}_unavailable"],
        }
    result = dict(state.attributes)
    result["status"] = state.state
    return entity_id, result


def build_do_plan_grid_support_sensors(coordinator: Any) -> list[Any]:
    """Expose grid-support diagnostics plus the authoritative alpha76 status surface."""
    # Keep these imports lazy so the pure refresh-key helper can still be loaded
    # by the lightweight regression harness without importing full HA platforms.
    from .ems_alpha76_surface import build_alpha76_status_sensors
    from .sensor import DummyOSPlanReserveSOCSensor

    class DummyOSPlanGridSupportSensor(DummyOSPlanReserveSOCSensor):
        async def async_added_to_hass(self) -> None:
            await super().async_added_to_hass()
            self._remove_aligned_upstream = subscribe_upstream(
                self,
                ["do_plan_input_72h", "do_plan_energy_need", "do_plan_reserve_soc"],
            )

        async def async_will_remove_from_hass(self) -> None:
            remove = getattr(self, "_remove_aligned_upstream", None)
            if remove is not None:
                remove()
            await super().async_will_remove_from_hass()

        _attr_name = "DO Plan Grid Support"
        _attr_unique_id = "do_plan_grid_support"
        _attr_suggested_object_id = "do_plan_grid_support"
        _attr_icon = "mdi:transmission-tower-import"
        _unrecorded_attributes = frozenset({"selected_charge_slots"})
        GRID_CHARGE_TRIGGER_KWH = 0.25

        def _snapshot(self) -> dict[str, Any]:
            input_entity, input_result = _state_contract(self.hass, "do_plan_input_72h")
            need_entity, need = _state_contract(self.hass, "do_plan_energy_need")
            reserve_entity, reserve = _state_contract(self.hass, "do_plan_reserve_soc")
            return {
                "now": aligned_reference(input_result, dt_util.utcnow()),
                "input_entity": input_entity,
                "energy_need_entity": need_entity,
                "reserve_entity": reserve_entity,
                "input_result": input_result,
                "energy_need_result": need,
                "reserve_result": reserve,
            }

        def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
            input_result = snapshot["input_result"]
            need = snapshot["energy_need_result"]
            reserve = snapshot["reserve_result"]
            result = build_do_plan_grid_support(
                input_result=input_result,
                energy_need_result=need,
                reserve_result=reserve,
                trigger_kwh=self.GRID_CHARGE_TRIGGER_KWH,
            )
            result["input_entity"] = snapshot["input_entity"]
            result["energy_need_entity"] = snapshot["energy_need_entity"]
            result["reserve_entity"] = snapshot["reserve_entity"]
            result["soc_source_entity"] = reserve.get("soc_source_entity") or need.get("soc_source_entity")
            result["source_layer_status"] = reserve.get("source_layer_status") or need.get("source_layer_status")
            result["dependency_mode"] = "published_upstream_contracts_with_reserve_handoff"
            result["ems_authority"] = "alpha76_runtime"
            result["shadow_only"] = True
            result["physical_execution_authority"] = False
            return result

        def _initial_result(self) -> dict[str, Any]:
            return {
                "status": "initializing",
                "valid": False,
                "selected_charge_slots": [],
                "shadow_only": True,
                "active_use_permitted": False,
                "physical_execution_authority": False,
                "plan_store_write": False,
                "scheduler_invoked": False,
                "safety_chain_invoked": False,
                "service_calls_performed": False,
                "blockers": ["planner_calculation_pending"],
            }

        @property
        def native_value(self) -> str:
            return str(self._result().get("status", "initializing"))

        @property
        def extra_state_attributes(self) -> dict[str, Any]:
            return dict(self._result())

    return [
        DummyOSPlanGridSupportSensor(coordinator),
        *build_alpha76_status_sensors(coordinator),
    ]
