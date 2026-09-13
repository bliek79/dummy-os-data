"""Observer-only native 15-minute / 72-hour planner parity layer."""
from __future__ import annotations
from typing import Any
from custom_components.dummy_os_data.do_plan_native_common import (
    HOURS, SLOTS, SLOTS_PER_HOUR, SLOT_MINUTES, CHARGE_EFFICIENCY_PERCENT,
    DISCHARGE_EFFICIENCY_PERCENT, EXECUTION_BUFFER_PERCENT, MIN_SOC_PERCENT,
    SAFETY_RESERVE_PERCENT, USABLE_SOLAR_CONSECUTIVE_SLOTS, EPS, _finite,
    _blocked, _expand_native_slots, _dynamic_reserve_profile,
    _dynamic_safety_schedule, _external_safety_schedule, _select_native_trade,
)
from custom_components.dummy_os_data.do_plan_native_simulation import _simulate, _aggregate_hours


def _preview_trade_fallback(slots: list[dict[str, Any]], preview_result: dict[str, Any], charge_eff: float, discharge_eff: float) -> dict[str, Any] | None:
    by_start = {slot["start"]: slot for slot in slots}
    candidates: list[tuple[float, str, str, str]] = []
    if preview_result.get("self_use_trade_profitable"):
        margin = _finite(preview_result.get("best_self_use_margin"))
        charge = preview_result.get("best_self_use_charge_time")
        discharge = preview_result.get("best_self_use_discharge_time")
        if margin is not None and isinstance(charge, str) and isinstance(discharge, str):
            candidates.append((margin, charge, discharge, "self_use"))
    if preview_result.get("export_trade_profitable"):
        margin = _finite(preview_result.get("best_export_margin"))
        charge = preview_result.get("best_export_charge_time")
        discharge = preview_result.get("best_export_discharge_time")
        if margin is not None and isinstance(charge, str) and isinstance(discharge, str):
            candidates.append((margin, charge, discharge, "export"))
    candidates.sort(reverse=True)
    for margin, charge_time, discharge_time, kind in candidates:
        charge = by_start.get(charge_time)
        discharge = by_start.get(discharge_time)
        if charge is None or discharge is None:
            continue
        if charge.get("price_fallback_used") or discharge.get("price_fallback_used"):
            continue
        if str(charge.get("price_kind") or "").lower() == "interpolated" or str(discharge.get("price_kind") or "").lower() == "interpolated":
            continue
        effective_cost = charge["import_price"] / (charge_eff * discharge_eff)
        return {
            "kind": kind,
            "margin": margin,
            "charge_time": charge_time,
            "charge_price": charge["import_price"],
            "discharge_time": discharge_time,
            "discharge_price": discharge["import_price"] if kind == "self_use" else discharge["export_price"],
            "effective_charge_cost": effective_cost,
            "minimum_trade_margin": _finite(preview_result.get("minimum_trade_margin"), non_negative=True) or 0.10,
            "source": "preview_compatibility_fallback",
        }
    return None


def build_do_plan_72h(*, input_result: dict[str, Any], reserve_result: dict[str, Any], preview_result: dict[str, Any], grid_support_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build native 288-slot EMS parity simulation and hourly Apex aggregation."""
    effective_horizon = input_result.get("effective_horizon_hours")
    if not isinstance(effective_horizon, int):
        effective_horizon = HOURS if input_result.get("fully_valid_hours") == HOURS else 0
    effective_horizon = max(0, min(HOURS, effective_horizon))
    base = {
        "shadow_only": True,
        "active_use_permitted": False,
        "physical_execution_authority": False,
        "plan_store_write": False,
        "scheduler_invoked": False,
        "safety_chain_invoked": False,
        "service_calls_performed": False,
        "native_resolution_minutes": SLOT_MINUTES,
        "native_slot_count": SLOTS,
        "planner_resolution_minutes": SLOT_MINUTES,
        "planner_slot_count": SLOTS,
        "dashboard_resolution_minutes": 60,
        "planner_hour_count": HOURS,
        "effective_horizon_hours": effective_horizon,
        "effective_horizon_slots": effective_horizon * SLOTS_PER_HOUR,
        "valid_through": input_result.get("valid_through"),
        "input_rows_signature": input_result.get("rows_signature"),
        "reserve_input_rows_signature": reserve_result.get("input_rows_signature"),
        "preview_input_rows_signature": preview_result.get("input_rows_signature"),
        "calculation_scope": "native_288_slot_old_ems_functional_parity_shadow",
        "apex_contract": "hourly_aggregation_derived_from_native_quarters",
    }

    blockers: list[str] = []
    if input_result.get("status") not in {"ready", "runtime_blocked", "degraded", "partial"}:
        blockers.append("planner_input_not_structurally_available")
    if effective_horizon <= 0:
        blockers.append("planner_effective_horizon_empty")
    if reserve_result.get("status") != "ready" or reserve_result.get("valid") is not True:
        blockers.append("reserve_soc_not_ready")
    if preview_result.get("status") not in {"ready", "degraded"} or preview_result.get("valid") is not True:
        blockers.append("planner_preview_not_ready")

    sig = input_result.get("rows_signature")
    if sig is None or reserve_result.get("input_rows_signature") != sig or preview_result.get("input_rows_signature") != sig:
        blockers.append("input_signature_mismatch")

    raw_rows = input_result.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) != HOURS:
        blockers.append("rows_not_exactly_72")
    soc = _finite(reserve_result.get("soc_percent"), non_negative=True)
    if soc is None or soc > 100:
        blockers.append("soc_invalid")

    slots: list[dict[str, Any]] = []
    quarter_source = "native_quarters"
    if isinstance(raw_rows, list):
        slots, slot_blockers, quarter_source = _expand_native_slots(raw_rows, effective_horizon)
        blockers.extend(slot_blockers)
    if blockers:
        return _blocked(base, blockers)
    assert soc is not None

    base["effective_horizon_slots"] = len(slots)
    base["valid_through_native"] = slots[-1]["end"] if slots else input_result.get("planner_start")
    base["quarter_source"] = quarter_source

    charge_eff = CHARGE_EFFICIENCY_PERCENT / 100.0
    discharge_eff = DISCHARGE_EFFICIENCY_PERCENT / 100.0
    reserve_profile = _dynamic_reserve_profile(slots, discharge_eff)
    dynamic_safety = _dynamic_safety_schedule(slots, reserve_profile, soc, charge_eff)
    external_safety, external_safety_source = _external_safety_schedule(slots, preview_result, grid_support_result)
    safety_slots = {key: max(dynamic_safety.get(key, 0.0), external_safety.get(key, 0.0)) for key in set(dynamic_safety) | set(external_safety)}
    trade = _select_native_trade(slots, preview_result, charge_eff, discharge_eff)
    if trade is None:
        trade = _preview_trade_fallback(slots, preview_result, charge_eff, discharge_eff)

    baseline = _simulate(slots=slots, start_soc=soc, reserve_profile=reserve_profile, safety_slots=safety_slots, trade=None, charge_eff=charge_eff, discharge_eff=discharge_eff)
    candidate = _simulate(slots=slots, start_soc=soc, reserve_profile=reserve_profile, safety_slots=safety_slots, trade=trade, charge_eff=charge_eff, discharge_eff=discharge_eff)
    candidate_hours = _aggregate_hours(candidate["slots"])
    baseline_hours = _aggregate_hours(baseline["slots"])
    solar_displacement = max(0.0, baseline["solar_to_battery_kwh"] - candidate["solar_to_battery_kwh"])

    infeasible = candidate["reserve_breach_slots"] > 0 or candidate["execution_buffer_breach_slots"] > 0
    if grid_support_result is not None and grid_support_result.get("status") == "infeasible":
        infeasible = True

    if infeasible:
        status = "infeasible"
        valid = False
        reason = "dynamic_reserve_or_execution_buffer_breach"
        output_blockers = ["simulated_reserve_breach"]
    else:
        status = "degraded" if effective_horizon < HOURS else "ready"
        valid = True
        reason = "native_288_slot_sequential_simulation_partial_horizon" if effective_horizon < HOURS else "native_288_slot_sequential_simulation_complete"
        output_blockers = []

    dynamic_reserve_values = [slot["dynamic_reserve_end_soc_percent"] for slot in candidate["slots"]]
    execution_reserve_values = [slot["execution_reserve_end_soc_percent"] for slot in candidate["slots"]]
    headroom_values = [slot["execution_headroom_soc_percent"] for slot in candidate["slots"]]
    reserve_target = _finite(reserve_result.get("reserve_soc_target_percent"), non_negative=True)

    return {
        **base,
        "status": status,
        "valid": valid,
        "reason": reason,
        "blockers": output_blockers,
        "slot_count": len(candidate["slots"]),
        "simulated_slot_count": len(candidate["slots"]),
        "hour_count": len(candidate_hours),
        "simulated_hour_count": len(candidate_hours),
        "slots": candidate["slots"],
        "hours": candidate_hours,
        "baseline": {key: value for key, value in baseline.items() if key != "slots"} | {"hours": baseline_hours},
        "candidate": {key: value for key, value in candidate.items() if key != "slots"},
        "trade_candidate": trade,
        "solar_displacement_kwh": round(solar_displacement, 3),
        "losses_included": True,
        "reserve_recalculated": True,
        "reserve_target_soc_percent": round(reserve_target, 3) if reserve_target is not None else None,
        "simulation_reserve_floor_soc_percent": MIN_SOC_PERCENT + SAFETY_RESERVE_PERCENT,
        "reserve_model": "old_ems_dynamic_need_until_next_usable_solar_native_15m",
        "usable_solar_consecutive_slots": USABLE_SOLAR_CONSECUTIVE_SLOTS,
        "usable_solar_duration_hours": USABLE_SOLAR_CONSECUTIVE_SLOTS * SLOT_MINUTES / 60.0,
        "dynamic_reserve_min_soc_percent": round(min(dynamic_reserve_values), 3) if dynamic_reserve_values else None,
        "dynamic_reserve_max_soc_percent": round(max(dynamic_reserve_values), 3) if dynamic_reserve_values else None,
        "execution_reserve_min_soc_percent": round(min(execution_reserve_values), 3) if execution_reserve_values else None,
        "execution_reserve_max_soc_percent": round(max(execution_reserve_values), 3) if execution_reserve_values else None,
        "minimum_execution_headroom_soc_percent": round(min(headroom_values), 3) if headroom_values else None,
        "execution_buffer_percent": EXECUTION_BUFFER_PERCENT,
        "dynamic_safety_slot_count": sum(1 for value in dynamic_safety.values() if value > EPS),
        "safety_charge_source": external_safety_source,
        "dynamic_safety_charge_source": "native_dynamic_reserve",
        "safety_charge_sources": ["native_dynamic_reserve", external_safety_source],
        "grid_support_status": grid_support_result.get("status") if grid_support_result is not None else None,
        "grid_support_fallback_to_preview": bool(grid_support_result is not None and grid_support_result.get("status") not in {"ready", "degraded", "infeasible"}),
        "missing_as_zero_used": False,
    }
