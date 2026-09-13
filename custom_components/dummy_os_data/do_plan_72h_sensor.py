"""Home Assistant sensor adapter for observer-only Planner Step 5."""

from __future__ import annotations
from typing import Any
from .do_plan_72h import build_do_plan_72h
from .do_plan_preview import build_do_plan_preview
from .do_plan_grid_support import build_do_plan_grid_support


def build_do_plan_72h_sensors(coordinator: Any) -> list[Any]:
    from .sensor import DummyOSPlanReserveSOCSensor, _build_plan_input_from_snapshot, _build_energy_need_from_snapshot, _build_reserve_from_snapshot

    class DummyOSPlan72hSensor(DummyOSPlanReserveSOCSensor):
        _attr_name = "DO Plan 72h"
        _attr_unique_id = "do_plan_72h"
        _attr_suggested_object_id = "do_plan_72h"
        _attr_icon = "mdi:timeline-clock-outline"
        _unrecorded_attributes = frozenset({"hours", "slots", "baseline", "candidate", "safety_plan", "rejected_trade_candidate"})

        def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
            input_result = _build_plan_input_from_snapshot(snapshot)
            energy_need_result = _build_energy_need_from_snapshot(snapshot)
            reserve_result = _build_reserve_from_snapshot(snapshot)
            preview_result = build_do_plan_preview(input_result=input_result, reserve_result=reserve_result, now=snapshot["now"], charge_efficiency_percent=92.0, discharge_efficiency_percent=92.0, minimum_trade_margin=0.10, max_charge_power_w=3200, max_discharge_power_w=3200)
            grid_support_result = build_do_plan_grid_support(input_result=input_result, energy_need_result=energy_need_result, reserve_result=reserve_result, trigger_kwh=0.25)
            result = build_do_plan_72h(input_result=input_result, reserve_result=reserve_result, preview_result=preview_result, grid_support_result=grid_support_result)
            result["input_entity"] = "sensor.do_plan_input_72h"
            result["reserve_entity"] = "sensor.do_plan_reserve_soc"
            result["preview_entity"] = "sensor.do_plan_preview"
            result["grid_support_entity"] = "sensor.do_plan_grid_support"
            result["soc_source_entity"] = reserve_result.get("soc_source_entity")
            result["source_layer_status"] = reserve_result.get("source_layer_status")
            return result

        def _initial_result(self) -> dict[str, Any]:
            return {"status":"initializing","valid":False,"slot_count":0,"hour_count":0,"slots":[],"hours":[],"shadow_only":True,"active_use_permitted":False,"physical_execution_authority":False,"plan_store_write":False,"scheduler_invoked":False,"safety_chain_invoked":False,"service_calls_performed":False,"blockers":["planner_calculation_pending"]}

        @property
        def native_value(self) -> str:
            return str(self._result().get("status", "initializing"))

        @property
        def extra_state_attributes(self) -> dict[str, Any]:
            return dict(self._result())

    return [DummyOSPlan72hSensor(coordinator)]
