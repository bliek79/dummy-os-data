"""Observer-only Planner Step 5 sequential 72-hour simulation."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

HOURS = 72
CAPACITY_KWH = 7.2
MIN_SOC_PERCENT = 5.0
SAFETY_RESERVE_PERCENT = 7.0
EXECUTION_BUFFER_PERCENT = 2.0
CHARGE_EFFICIENCY_PERCENT = 92.0
DISCHARGE_EFFICIENCY_PERCENT = 92.0
MAX_CHARGE_POWER_W = 3200
MAX_DISCHARGE_POWER_W = 3200
EPS = 0.01


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


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _blocked(base: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    return {**base, "status": "blocked", "valid": False, "reason": blockers[0], "blockers": sorted(set(blockers)), "hour_count": 0, "hours": [], "baseline": None, "candidate": None}


def _simulate(*, rows: list[dict[str, Any]], start_soc: float, reserve_soc: float, safety_hours: dict[str, float], trade: dict[str, Any] | None, charge_eff: float, discharge_eff: float) -> dict[str, Any]:
    stored = CAPACITY_KWH * start_soc / 100.0
    reserve_floor = CAPACITY_KWH * reserve_soc / 100.0
    buffer_kwh = CAPACITY_KWH * EXECUTION_BUFFER_PERCENT / 100.0
    execution_floor = min(CAPACITY_KWH, reserve_floor + buffer_kwh)
    out: list[dict[str, Any]] = []
    totals = {k: 0.0 for k in (
        "solar_to_home_kwh","solar_to_battery_kwh","solar_to_grid_kwh","grid_to_home_kwh",
        "grid_to_battery_kwh","grid_to_battery_safety_kwh","grid_to_battery_trade_kwh",
        "battery_to_home_kwh","battery_to_grid_kwh"
    )}
    reserve_breaches = 0
    buffer_breaches = 0
    for row in rows:
        start_stored = stored
        home = row["home_kwh"]
        solar = row["solar_kwh"]
        solar_to_home = min(home, solar)
        remaining_home = home - solar_to_home
        solar_surplus = solar - solar_to_home
        charge_input_limit = MAX_CHARGE_POWER_W / 1000.0
        solar_input = min(solar_surplus, charge_input_limit, max(0.0, (CAPACITY_KWH - stored) / charge_eff))
        solar_to_battery = solar_input * charge_eff
        stored += solar_to_battery
        solar_to_grid = max(0.0, solar_surplus - solar_input)
        charge_input_left = max(0.0, charge_input_limit - solar_input)

        safety_input = 0.0
        trade_input = 0.0
        safety_battery = safety_hours.get(row["start"], 0.0)
        if safety_battery > EPS and charge_input_left > 0:
            wanted_input = safety_battery / charge_eff
            safety_input = min(wanted_input, charge_input_left, max(0.0, (CAPACITY_KWH - stored) / charge_eff))
            stored += safety_input * charge_eff
            charge_input_left -= safety_input

        action = "baseline"
        if safety_battery > EPS and safety_input > EPS:
            action = "safety_charge"
        if trade and trade.get("charge_time") == row["start"] and charge_input_left > 0:
            trade_input = min(charge_input_left, max(0.0, (CAPACITY_KWH - stored) / charge_eff))
            stored += trade_input * charge_eff
            action = "trade_charge"
        grid_to_battery_input = safety_input + trade_input

        max_batt_output = MAX_DISCHARGE_POWER_W / 1000.0
        available_output = max(0.0, (stored - execution_floor) * discharge_eff)
        battery_to_home = min(remaining_home, max_batt_output, available_output)
        stored -= battery_to_home / discharge_eff
        grid_to_home = remaining_home - battery_to_home
        discharge_left = max(0.0, max_batt_output - battery_to_home)

        battery_to_grid = 0.0
        if trade and trade.get("discharge_time") == row["start"] and discharge_left > 0:
            available_export = max(0.0, (stored - execution_floor) * discharge_eff)
            battery_to_grid = min(discharge_left, available_export)
            stored -= battery_to_grid / discharge_eff
            action = "trade_discharge"

        stored = min(CAPACITY_KWH, max(0.0, stored))
        end_soc = stored / CAPACITY_KWH * 100.0
        if stored + EPS < reserve_floor:
            reserve_breaches += 1
        if stored + EPS < execution_floor:
            buffer_breaches += 1

        values = {
            "solar_to_home_kwh": solar_to_home,
            "solar_to_battery_kwh": solar_to_battery,
            "solar_to_grid_kwh": solar_to_grid,
            "grid_to_home_kwh": grid_to_home,
            "grid_to_battery_kwh": grid_to_battery_input,
            "grid_to_battery_safety_kwh": safety_input,
            "grid_to_battery_trade_kwh": trade_input,
            "battery_to_home_kwh": battery_to_home,
            "battery_to_grid_kwh": battery_to_grid,
        }
        for key, value in values.items():
            totals[key] += value
        out.append({
            "index": row["index"],
            "start": row["start"],
            "end": row["end"],
            "start_soc_percent": round(start_stored / CAPACITY_KWH * 100.0, 3),
            "end_soc_percent": round(end_soc, 3),
            "reserve_floor_soc_percent": round(reserve_soc, 3),
            "execution_floor_soc_percent": round(execution_floor / CAPACITY_KWH * 100.0, 3),
            "action": action,
            **{k: round(v, 3) for k,v in values.items()},
        })
    return {
        "hours": out,
        "end_soc_percent": round(stored / CAPACITY_KWH * 100.0, 3),
        "reserve_breach_hours": reserve_breaches,
        "execution_buffer_breach_hours": buffer_breaches,
        **{k: round(v, 3) for k,v in totals.items()},
    }


def build_do_plan_72h(*, input_result: dict[str, Any], reserve_result: dict[str, Any], preview_result: dict[str, Any], grid_support_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a sequential simulation over the reliable prefix of the 72h horizon."""
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
        "native_resolution_minutes": 15,
        "native_slot_count": 288,
        "planner_resolution_minutes": 60,
        "planner_hour_count": 72,
        "effective_horizon_hours": effective_horizon,
        "valid_through": input_result.get("valid_through"),
        "input_rows_signature": input_result.get("rows_signature"),
        "reserve_input_rows_signature": reserve_result.get("input_rows_signature"),
        "preview_input_rows_signature": preview_result.get("input_rows_signature"),
        "calculation_scope": "sequential_reliable_prefix_observer_simulation",
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

    grid_support_usable = bool(
        grid_support_result is not None
        and grid_support_result.get("status") in {"ready", "degraded"}
        and grid_support_result.get("valid") is True
    )
    if grid_support_result is not None and grid_support_result.get("status") == "infeasible":
        grid_support_usable = False

    sig = input_result.get("rows_signature")
    if sig is None or reserve_result.get("input_rows_signature") != sig or preview_result.get("input_rows_signature") != sig:
        blockers.append("input_signature_mismatch")
    if grid_support_usable and grid_support_result is not None and grid_support_result.get("input_rows_signature") != sig:
        blockers.append("grid_support_signature_mismatch")

    raw_rows = input_result.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) != HOURS:
        blockers.append("rows_not_exactly_72")
    soc = _finite(reserve_result.get("soc_percent"), non_negative=True)
    reserve_soc = _finite(reserve_result.get("reserve_soc_target_percent"), non_negative=True)
    if soc is None or soc > 100:
        blockers.append("soc_invalid")
    if reserve_soc is None or reserve_soc > 100:
        blockers.append("reserve_soc_invalid")

    rows: list[dict[str, Any]] = []
    if isinstance(raw_rows, list):
        previous_end = None
        for i, raw in enumerate(raw_rows[:effective_horizon]):
            if not isinstance(raw, dict) or raw.get("fully_valid") is not True:
                blockers.append(f"row_{i}_not_fully_valid_inside_effective_horizon")
                continue
            start = _utc(raw.get("start"))
            end = _utc(raw.get("end"))
            home = _finite(raw.get("home_kwh"), non_negative=True)
            solar = _finite(raw.get("solar_kwh"), non_negative=True)
            imp = _finite(raw.get("import_price"))
            exp = _finite(raw.get("export_price"))
            if None in (start,end,home,solar,imp,exp):
                blockers.append(f"row_{i}_invalid")
                continue
            if raw.get("index") != i:
                blockers.append(f"row_{i}_index_mismatch")
            if previous_end is not None and start != previous_end:
                blockers.append(f"row_{i}_not_contiguous")
            previous_end = end
            rows.append({"index":i,"start":start.isoformat(),"end":end.isoformat(),"home_kwh":home,"solar_kwh":solar,"import_price":imp,"export_price":exp})
    if blockers:
        return _blocked(base, blockers)
    assert soc is not None and reserve_soc is not None
    charge_eff = CHARGE_EFFICIENCY_PERCENT / 100.0
    discharge_eff = DISCHARGE_EFFICIENCY_PERCENT / 100.0

    safety_hours: dict[str,float] = {}
    safety_source = "preview"
    if grid_support_usable and grid_support_result is not None:
        for item in grid_support_result.get("selected_charge_slots") or []:
            if isinstance(item, dict):
                start = item.get("start")
                stored = _finite(item.get("stored_battery_kwh"), non_negative=True)
                if isinstance(start,str) and stored is not None:
                    safety_hours[start] = safety_hours.get(start,0.0) + stored
        safety_source = "grid_support_selected_slots"
    else:
        for item in preview_result.get("safety_charge_hours") or []:
            if isinstance(item, dict):
                start = item.get("start")
                energy = _finite(item.get("candidate_battery_energy_kwh"), non_negative=True)
                if isinstance(start,str) and energy is not None:
                    safety_hours[start] = energy

    trade = None
    candidates = []
    if preview_result.get("self_use_trade_profitable"):
        candidates.append((preview_result.get("best_self_use_margin"), preview_result.get("best_self_use_charge_time"), preview_result.get("best_self_use_discharge_time"), "self_use"))
    if preview_result.get("export_trade_profitable"):
        candidates.append((preview_result.get("best_export_margin"), preview_result.get("best_export_charge_time"), preview_result.get("best_export_discharge_time"), "export"))
    valid_candidates = []
    for margin, charge_time, discharge_time, kind in candidates:
        m = _finite(margin)
        if m is not None and isinstance(charge_time,str) and isinstance(discharge_time,str):
            valid_candidates.append((m,charge_time,discharge_time,kind))
    if valid_candidates:
        m,ct,dt,kind = max(valid_candidates,key=lambda x:x[0])
        trade = {"margin":m,"charge_time":ct,"discharge_time":dt,"kind":kind}

    simulation_reserve_soc = reserve_soc
    if reserve_result.get("grid_support_required") is True:
        simulation_reserve_soc = MIN_SOC_PERCENT + SAFETY_RESERVE_PERCENT

    baseline = _simulate(rows=rows,start_soc=soc,reserve_soc=simulation_reserve_soc,safety_hours=safety_hours,trade=None,charge_eff=charge_eff,discharge_eff=discharge_eff)
    candidate = _simulate(rows=rows,start_soc=soc,reserve_soc=simulation_reserve_soc,safety_hours=safety_hours,trade=trade,charge_eff=charge_eff,discharge_eff=discharge_eff)
    solar_displacement = max(0.0, baseline["solar_to_battery_kwh"] - candidate["solar_to_battery_kwh"])
    infeasible = candidate["reserve_breach_hours"] > 0 or candidate["execution_buffer_breach_hours"] > 0
    if grid_support_result is not None and grid_support_result.get("status") == "infeasible":
        infeasible = True

    if infeasible:
        status = "infeasible"
        valid = False
        reason = "reserve_or_execution_buffer_breach"
        output_blockers = ["simulated_reserve_breach"]
    else:
        status = "degraded" if effective_horizon < HOURS else "ready"
        valid = True
        reason = "sequential_simulation_partial_horizon" if effective_horizon < HOURS else "sequential_simulation_complete"
        output_blockers = []

    return {
        **base,
        "status": status,
        "valid": valid,
        "reason": reason,
        "blockers": output_blockers,
        "hour_count": len(rows),
        "simulated_hour_count": len(rows),
        "hours": candidate["hours"],
        "baseline": {k:v for k,v in baseline.items() if k!="hours"},
        "candidate": {k:v for k,v in candidate.items() if k!="hours"},
        "trade_candidate": trade,
        "solar_displacement_kwh": round(solar_displacement,3),
        "losses_included": True,
        "reserve_recalculated": False,
        "reserve_target_soc_percent": round(reserve_soc,3),
        "simulation_reserve_floor_soc_percent": round(simulation_reserve_soc,3),
        "safety_charge_source": safety_source,
        "grid_support_status": grid_support_result.get("status") if grid_support_result is not None else None,
        "grid_support_fallback_to_preview": bool(grid_support_result is not None and not grid_support_usable and grid_support_result.get("status") != "infeasible"),
        "missing_as_zero_used": False,
    }
