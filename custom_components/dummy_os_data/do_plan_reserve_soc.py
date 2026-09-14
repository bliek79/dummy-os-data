"""Reserve/SOC view derived from the copied alpha76 EMS Energy Need result.

This module is not an EMS policy authority.  It only exposes the reserve position
that alpha76 already uses so dashboards and downstream adapters can observe it.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CAPACITY_KWH = 7.2
MIN_SOC_PERCENT = 5.0
ENERGY_EPSILON_KWH = 0.01


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def build_do_plan_reserve_soc(*, energy_need_result: dict[str, Any]) -> dict[str, Any]:
    raw = energy_need_result.get("alpha76_energy_need")
    if not isinstance(raw, dict):
        return {
            "status": "blocked", "valid": False,
            "reason": "alpha76_energy_need_missing",
            "blockers": ["alpha76_energy_need_missing"],
            "ems_policy_source": "0.0.1-alpha.76",
            "shadow_only": True, "active_use_permitted": False,
            "physical_execution_authority": False,
        }

    soc = _number(energy_need_result.get("soc_percent"))
    need = _number(raw.get("energy_need_until_solar_kwh")) or 0.0
    reserve_kwh = _number(raw.get("energy_need_safety_reserve_kwh")) or 0.0
    required = _number(raw.get("energy_need_required_including_reserve_kwh")) or (need + reserve_kwh)
    available = _number(raw.get("energy_need_available_battery_kwh"))
    additional = _number(raw.get("energy_need_additional_grid_charge_kwh"))
    tradable = _number(raw.get("energy_need_tradable_battery_kwh"))

    required_min_soc = MIN_SOC_PERCENT + required / CAPACITY_KWH * 100.0
    required_min_soc = max(MIN_SOC_PERCENT, min(100.0, required_min_soc))
    available = available if available is not None else (
        CAPACITY_KWH * max((soc or MIN_SOC_PERCENT) - MIN_SOC_PERCENT, 0.0) / 100.0
        if soc is not None else None
    )
    deficit = additional if additional is not None else (
        max(required - available, 0.0) if available is not None else None
    )
    free = tradable if tradable is not None else (
        max(available - required, 0.0) if available is not None else None
    )

    result = {
        "status": "ready" if raw.get("energy_need_valid") else "blocked",
        "valid": bool(raw.get("energy_need_valid")),
        "reason": "alpha76_reserve_view",
        "blockers": [] if raw.get("energy_need_valid") else ["alpha76_energy_need_not_valid"],
        "battery_capacity_kwh": CAPACITY_KWH,
        "soc_percent": soc,
        "min_soc_percent": MIN_SOC_PERCENT,
        "safety_reserve_percent": raw.get("energy_need_safety_reserve_percent"),
        "energy_need_until_solar_kwh": need,
        "safety_reserve_kwh": reserve_kwh,
        "required_including_reserve_kwh": required,
        "available_battery_kwh": available,
        "reserve_soc_raw_percent": MIN_SOC_PERCENT + required / CAPACITY_KWH * 100.0,
        "reserve_soc_target_percent": round(required_min_soc, 3),
        "reserve_deficit_kwh": round(deficit, 3) if deficit is not None else None,
        "reserve_deficit_percent": round(deficit / CAPACITY_KWH * 100.0, 3) if deficit is not None else None,
        "free_above_reserve_kwh": round(free, 3) if free is not None else None,
        "free_above_reserve_percent": round(free / CAPACITY_KWH * 100.0, 3) if free is not None else None,
        "first_usable_solar": raw.get("energy_need_first_usable_solar"),
        "grid_support_required": bool(deficit is not None and deficit > ENERGY_EPSILON_KWH),
        "grid_support_deficit_kwh": round(deficit, 3) if deficit is not None else None,
        "efficiency_applied": False,
        "ems_policy_source": "0.0.1-alpha.76",
        "alpha76_energy_need": deepcopy(raw),
        "shadow_only": True,
        "active_use_permitted": False,
        "physical_execution_authority": False,
    }
    for key in (
        "time_contract", "soc_bridge", "measured_soc_percent",
        "planner_start_soc_percent", "soc_time_basis", "soc_source_entity",
        "source_layer_status", "input_rows_signature", "input_status",
    ):
        if key in energy_need_result:
            result[key] = deepcopy(energy_need_result[key])
    return result
