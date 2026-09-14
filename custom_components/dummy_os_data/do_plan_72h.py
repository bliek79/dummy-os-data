"""Dummy OS Energy Plan72 backed by the original EMS alpha76 planner.

The 15-minute / 288-slot layer remains the input and presentation contract.
EMS policy, reserve, safety charge, home discharge and trading decisions are
made exclusively by the vendored alpha76 planner.
"""

from __future__ import annotations

from typing import Any

from .ems_alpha76_adapter import plan72_public, run_plan72


def build_do_plan_72h(
    *,
    input_result: dict[str, Any],
    reserve_result: dict[str, Any],
    preview_result: dict[str, Any],
    grid_support_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_need = reserve_result.get("alpha76_energy_need")
    raw_preview = preview_result.get("alpha76_planner_preview")
    if not isinstance(raw_need, dict) or not isinstance(raw_preview, dict):
        return {
            "status": "blocked", "valid": False,
            "reason": "alpha76_upstream_contract_missing",
            "blockers": ["alpha76_upstream_contract_missing"],
            "hours": [], "slots": [], "hour_count": 0, "slot_count": 0,
            "ems_policy_source": "0.0.1-alpha.76",
            "shadow_only": True, "active_use_permitted": False,
            "physical_execution_authority": False,
        }

    bridge = reserve_result.get("soc_bridge")
    contract = input_result.get("time_contract")
    if contract is not None:
        if not isinstance(bridge, dict) or bridge.get("valid") is not True:
            return {
                "status": "blocked", "valid": False,
                "reason": "planner_start_soc_not_aligned",
                "blockers": ["planner_start_soc_not_aligned"],
                "hours": [], "slots": [], "hour_count": 0, "slot_count": 0,
                "ems_policy_source": "0.0.1-alpha.76",
                "shadow_only": True, "active_use_permitted": False,
                "physical_execution_authority": False,
                "time_contract": contract,
            }
        if bridge.get("projected_at") != contract.get("window_start"):
            return {
                "status": "blocked", "valid": False,
                "reason": "planner_start_soc_not_aligned",
                "blockers": ["planner_start_soc_not_aligned"],
                "hours": [], "slots": [], "hour_count": 0, "slot_count": 0,
                "ems_policy_source": "0.0.1-alpha.76",
                "shadow_only": True, "active_use_permitted": False,
                "physical_execution_authority": False,
                "time_contract": contract,
            }
        soc = bridge.get("planner_start_soc_percent")
    else:
        soc = reserve_result.get("soc_percent")

    try:
        raw = run_plan72(
            input_result=input_result,
            energy_need=raw_need,
            planner_preview=raw_preview,
            soc_percent=soc,
            charge_efficiency_percent=92.0,
            discharge_efficiency_percent=92.0,
            execution_buffer_percent=2.0,
            max_charge_power_w=3200,
            max_discharge_power_w=3200,
        )
    except (TypeError, ValueError) as err:
        return {
            "status": "blocked", "valid": False, "reason": str(err),
            "blockers": ["alpha76_forecast_adapter_invalid"],
            "hours": [], "slots": [], "hour_count": 0, "slot_count": 0,
            "ems_policy_source": "0.0.1-alpha.76",
            "shadow_only": True, "active_use_permitted": False,
            "physical_execution_authority": False,
        }

    result = plan72_public(raw, input_result=input_result)
    result["soc_bridge"] = bridge
    result["measured_soc_percent"] = reserve_result.get("measured_soc_percent")
    result["planner_start_soc_percent"] = soc
    result["soc_time_basis"] = "planner_window_start_estimate" if contract is not None else "input_soc"
    result["input_rows_signature"] = input_result.get("rows_signature")
    result["reserve_input_rows_signature"] = reserve_result.get("input_rows_signature")
    result["preview_input_rows_signature"] = preview_result.get("input_rows_signature")
    result["grid_support_status"] = grid_support_result.get("status") if isinstance(grid_support_result, dict) else None
    result["grid_support_advisory_only"] = True
    result["native_resolution_minutes"] = 15
    result["native_slot_count"] = len(result.get("slots") or [])
    result["planner_resolution_minutes"] = 15
    result["planner_slot_count"] = len(result.get("slots") or [])
    result["transport_hour_count"] = len(result.get("hours") or [])
    result["decision_resolution"] = "alpha76_hourly_over_native_15m_transport"
    return result
