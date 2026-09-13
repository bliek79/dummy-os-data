"""Observer-only reserve and SOC protection analysis for Dummy OS Energy."""

from __future__ import annotations

import math
from typing import Any

ENERGY_EPSILON_KWH = 0.01


def _finite(value: Any, *, non_negative: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if non_negative and number < 0:
        return None
    return number


def _legacy_build_do_plan_reserve_soc(*, energy_need_result: dict[str, Any]) -> dict[str, Any]:
    """Translate Step-2 energy need into a protected reserve-SOC position.

    Reserve demand above static battery capacity is not by itself infeasible:
    the remaining deficit is a grid-support requirement. Feasibility of that
    requirement belongs to the downstream charge-window planner.
    """
    base = {
        "energy_need_status": energy_need_result.get("status"),
        "energy_need_reason": energy_need_result.get("reason"),
        "input_status": energy_need_result.get("input_status"),
        "input_rows_signature": energy_need_result.get("input_rows_signature"),
        "first_usable_solar": energy_need_result.get("first_usable_solar"),
        "shadow_only": True,
        "active_use_permitted": False,
        "physical_execution_authority": False,
        "calculation_scope": "protected_battery_energy_position_with_grid_support_handoff",
        "efficiency_applied": False,
    }

    blockers: list[str] = []
    if energy_need_result.get("status") != "ready" or energy_need_result.get("valid") is not True:
        blockers.append("energy_need_not_ready")

    capacity = _finite(energy_need_result.get("battery_capacity_kwh"), non_negative=True)
    min_soc = _finite(energy_need_result.get("min_soc_percent"), non_negative=True)
    reserve_percent = _finite(energy_need_result.get("safety_reserve_percent"), non_negative=True)
    soc = _finite(energy_need_result.get("soc_percent"), non_negative=True)
    energy_need = _finite(energy_need_result.get("energy_need_until_solar_kwh"), non_negative=True)
    reserve_kwh = _finite(energy_need_result.get("safety_reserve_kwh"), non_negative=True)
    required = _finite(energy_need_result.get("required_including_reserve_kwh"), non_negative=True)

    if capacity is None or capacity <= 0: blockers.append("battery_capacity_invalid")
    if min_soc is None or min_soc > 100: blockers.append("min_soc_invalid")
    if reserve_percent is None or reserve_percent > 30: blockers.append("safety_reserve_invalid")
    if soc is None or soc > 100: blockers.append("soc_invalid")
    if energy_need is None: blockers.append("energy_need_invalid")
    if reserve_kwh is None: blockers.append("reserve_energy_invalid")
    if required is None: blockers.append("required_energy_invalid")

    if blockers:
        return {
            **base, "status": "blocked", "valid": False, "reason": blockers[0],
            "blockers": sorted(set(blockers)), "battery_capacity_kwh": capacity,
            "soc_percent": soc, "min_soc_percent": min_soc,
            "safety_reserve_percent": reserve_percent,
            "energy_need_until_solar_kwh": energy_need, "safety_reserve_kwh": reserve_kwh,
            "required_including_reserve_kwh": required, "available_battery_kwh": None,
            "usable_capacity_above_min_kwh": None, "current_usable_above_min_kwh": None,
            "max_usable_above_min_kwh": None, "reserve_soc_raw_percent": None,
            "reserve_soc_target_percent": None, "reserve_deficit_kwh": None,
            "reserve_deficit_percent": None, "free_above_reserve_kwh": None,
            "free_above_reserve_percent": None, "unmet_reserve_at_full_soc_kwh": None,
            "grid_support_required": False, "grid_support_deficit_kwh": None,
        }

    assert None not in (capacity, min_soc, reserve_percent, soc, energy_need, reserve_kwh, required)
    available_battery_kwh = capacity * max(soc - min_soc, 0.0) / 100.0
    usable_capacity_above_min_kwh = capacity * max(100.0 - min_soc, 0.0) / 100.0
    reserve_soc_raw_percent = min_soc + (required / capacity * 100.0)
    reserve_soc_target_percent = min(100.0, reserve_soc_raw_percent)
    reserve_deficit_kwh = max(required - available_battery_kwh, 0.0)
    free_above_reserve_kwh = max(available_battery_kwh - required, 0.0)
    reserve_deficit_percent = reserve_deficit_kwh / capacity * 100.0
    free_above_reserve_percent = free_above_reserve_kwh / capacity * 100.0
    unmet_at_full = max(required - usable_capacity_above_min_kwh, 0.0)
    grid_support_required = reserve_deficit_kwh > ENERGY_EPSILON_KWH

    if unmet_at_full > ENERGY_EPSILON_KWH:
        status, valid = "ready", True
        reason = "grid_support_required_beyond_static_battery_capacity"
        output_blockers = []
    elif reserve_deficit_kwh > ENERGY_EPSILON_KWH:
        status, valid = "ready", True
        reason = "reserve_deficit"
        output_blockers = []
    elif free_above_reserve_kwh > ENERGY_EPSILON_KWH:
        status, valid = "ready", True
        reason = "reserve_surplus"
        output_blockers = []
    else:
        status, valid = "ready", True
        reason = "reserve_covered"
        output_blockers = []

    return {
        **base, "status": status, "valid": valid, "reason": reason,
        "blockers": output_blockers, "battery_capacity_kwh": round(capacity, 3),
        "soc_percent": round(soc, 3), "min_soc_percent": round(min_soc, 3),
        "safety_reserve_percent": round(reserve_percent, 3),
        "energy_need_until_solar_kwh": round(energy_need, 3),
        "safety_reserve_kwh": round(reserve_kwh, 3),
        "required_including_reserve_kwh": round(required, 3),
        "available_battery_kwh": round(available_battery_kwh, 3),
        "usable_capacity_above_min_kwh": round(usable_capacity_above_min_kwh, 3),
        "current_usable_above_min_kwh": round(available_battery_kwh, 3),
        "max_usable_above_min_kwh": round(usable_capacity_above_min_kwh, 3),
        "reserve_soc_raw_percent": round(reserve_soc_raw_percent, 3),
        "reserve_soc_target_percent": round(reserve_soc_target_percent, 3),
        "reserve_deficit_kwh": round(reserve_deficit_kwh, 3),
        "reserve_deficit_percent": round(reserve_deficit_percent, 3),
        "free_above_reserve_kwh": round(free_above_reserve_kwh, 3),
        "free_above_reserve_percent": round(free_above_reserve_percent, 3),
        "unmet_reserve_at_full_soc_kwh": round(unmet_at_full, 3),
        "grid_support_required": grid_support_required,
        "grid_support_deficit_kwh": round(reserve_deficit_kwh, 3),
        "static_capacity_shortfall_kwh": round(unmet_at_full, 3),
        "feasibility_deferred_to_charge_window_planner": grid_support_required,
    }


def build_do_plan_reserve_soc(**kwargs: Any) -> dict[str, Any]:
    from custom_components.dummy_os_data.planner_time_contract import propagate_time
    need = kwargs["energy_need_result"]
    result = propagate_time(_legacy_build_do_plan_reserve_soc(**kwargs), need)
    for key in ("soc_bridge", "measured_soc_percent", "planner_start_soc_percent", "soc_time_basis"):
        if key in need:
            result[key] = need[key]
    return result
