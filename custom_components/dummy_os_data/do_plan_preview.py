"""Observer-only Step 4 action preview for Dummy OS Energy."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

ENERGY_EPSILON_KWH = 0.01
DEFAULT_CHARGE_EFFICIENCY_PERCENT = 92.0
DEFAULT_DISCHARGE_EFFICIENCY_PERCENT = 92.0
DEFAULT_MINIMUM_TRADE_MARGIN = 0.10
DEFAULT_MAX_CHARGE_POWER_W = 3200
DEFAULT_MAX_DISCHARGE_POWER_W = 3200
SOLAR_PROTECTION_HOURS = 12
HOURS = 72


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
    return {
        **base,
        "status": "blocked",
        "valid": False,
        "reason": blockers[0],
        "blockers": sorted(set(blockers)),
        "preview_decision": "blocked",
        "safety_charge_needed": None,
        "safety_charge_hours": [],
        "safety_charge_hour_count": 0,
        "safety_schedule_sufficient": None,
        "safety_unallocated_battery_kwh": None,
        "required_grid_input_kwh": None,
        "max_deliverable_from_free_kwh": None,
        "free_capacity_kwh": None,
        "price_min_import": None,
        "price_max_import": None,
        "price_spread_import": None,
        "best_self_use_charge_time": None,
        "best_self_use_charge_price": None,
        "best_self_use_discharge_time": None,
        "best_self_use_discharge_import_price": None,
        "best_self_use_margin": None,
        "best_export_charge_time": None,
        "best_export_charge_price": None,
        "best_export_discharge_time": None,
        "best_export_discharge_export_price": None,
        "best_export_margin": None,
        "self_use_trade_profitable": False,
        "export_trade_profitable": False,
        "solar_capacity_protection": False,
    }


def build_do_plan_preview(
    *,
    input_result: dict[str, Any],
    reserve_result: dict[str, Any],
    now: datetime,
    charge_efficiency_percent: float = DEFAULT_CHARGE_EFFICIENCY_PERCENT,
    discharge_efficiency_percent: float = DEFAULT_DISCHARGE_EFFICIENCY_PERCENT,
    minimum_trade_margin: float = DEFAULT_MINIMUM_TRADE_MARGIN,
    max_charge_power_w: int = DEFAULT_MAX_CHARGE_POWER_W,
    max_discharge_power_w: int = DEFAULT_MAX_DISCHARGE_POWER_W,
) -> dict[str, Any]:
    """Build safety and financial preview over the reliable planner prefix.

    A trailing source gap degrades the available horizon but no longer destroys
    an otherwise valid preview. Interpolated price rows may support continuity
    and safety scheduling, but are excluded from trade-pair discovery.
    """
    now_utc = _utc(now)
    charge_eff = _finite(charge_efficiency_percent, non_negative=True)
    discharge_eff = _finite(discharge_efficiency_percent, non_negative=True)
    min_margin = _finite(minimum_trade_margin, non_negative=True)
    rows = input_result.get("rows")
    effective_horizon = input_result.get("effective_horizon_hours")
    if not isinstance(effective_horizon, int):
        effective_horizon = HOURS if input_result.get("fully_valid_hours") == HOURS else 0
    effective_horizon = max(0, min(HOURS, effective_horizon))

    base = {
        "input_status": input_result.get("status"),
        "reserve_status": reserve_result.get("status"),
        "input_rows_signature": input_result.get("rows_signature"),
        "first_usable_solar": reserve_result.get("first_usable_solar"),
        "soc_percent": reserve_result.get("soc_percent"),
        "reserve_soc_target_percent": reserve_result.get("reserve_soc_target_percent"),
        "reserve_deficit_battery_kwh": reserve_result.get("reserve_deficit_kwh"),
        "free_above_reserve_battery_kwh": reserve_result.get("free_above_reserve_kwh"),
        "effective_horizon_hours": effective_horizon,
        "valid_through": input_result.get("valid_through"),
        "shadow_only": True,
        "active_use_permitted": False,
        "physical_execution_authority": False,
        "calculation_scope": "planner_preview_reliable_prefix",
        "losses_included": True,
        "reserve_source": "do_plan_reserve_soc",
        "reserve_recalculated": False,
        "prices_fallback_used": bool(input_result.get("interpolated_price_slots", 0)),
        "missing_as_zero_used": False,
    }

    blockers: list[str] = []
    if now_utc is None:
        blockers.append("now_invalid")
    if input_result.get("status") not in {"ready", "runtime_blocked", "degraded", "partial"}:
        blockers.append("planner_input_not_available")
    if not isinstance(rows, list) or len(rows) != HOURS:
        blockers.append("planner_rows_not_exactly_72")
    if effective_horizon <= 0:
        blockers.append("planner_effective_horizon_empty")
    if reserve_result.get("status") != "ready" or reserve_result.get("valid") is not True:
        blockers.append("reserve_soc_not_ready")

    if charge_eff is None or not 50.0 <= charge_eff <= 100.0:
        blockers.append("charge_efficiency_invalid")
    if discharge_eff is None or not 50.0 <= discharge_eff <= 100.0:
        blockers.append("discharge_efficiency_invalid")
    if min_margin is None:
        blockers.append("minimum_trade_margin_invalid")
    if max_charge_power_w <= 0:
        blockers.append("max_charge_power_invalid")
    if max_discharge_power_w <= 0:
        blockers.append("max_discharge_power_invalid")

    capacity = _finite(reserve_result.get("battery_capacity_kwh"), non_negative=True)
    soc = _finite(reserve_result.get("soc_percent"), non_negative=True)
    reserve_target = _finite(reserve_result.get("reserve_soc_target_percent"), non_negative=True)
    reserve_deficit = _finite(reserve_result.get("reserve_deficit_kwh"), non_negative=True)
    free_above_reserve = _finite(reserve_result.get("free_above_reserve_kwh"), non_negative=True)
    first_usable = _utc(reserve_result.get("first_usable_solar"))
    if capacity is None or capacity <= 0:
        blockers.append("battery_capacity_invalid")
    if soc is None or soc > 100:
        blockers.append("soc_invalid")
    if reserve_target is None or reserve_target > 100:
        blockers.append("reserve_soc_target_invalid")
    if reserve_deficit is None:
        blockers.append("reserve_deficit_invalid")
    if free_above_reserve is None:
        blockers.append("free_above_reserve_invalid")
    if first_usable is None:
        blockers.append("first_usable_solar_invalid")

    parsed_rows: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for index, raw in enumerate(rows[:effective_horizon]):
            if not isinstance(raw, dict) or raw.get("fully_valid") is not True:
                blockers.append(f"row_{index}_not_fully_valid_inside_effective_horizon")
                continue
            start = _utc(raw.get("start"))
            end = _utc(raw.get("end"))
            home = _finite(raw.get("home_kwh"), non_negative=True)
            solar = _finite(raw.get("solar_kwh"), non_negative=True)
            import_price = _finite(raw.get("import_price"))
            export_price = _finite(raw.get("export_price"))
            if None in (start, end, home, solar, import_price, export_price):
                blockers.append(f"row_{index}_invalid")
                continue
            quarters = raw.get("price_quarters")
            price_interpolated = bool(raw.get("price_interpolated")) or (
                isinstance(quarters, list)
                and any(str(item.get("kind") or "").lower() == "interpolated" for item in quarters if isinstance(item, dict))
            )
            parsed_rows.append(
                {
                    "index": index,
                    "start": start,
                    "end": end,
                    "home_kwh": home,
                    "solar_kwh": solar,
                    "import_price": import_price,
                    "export_price": export_price,
                    "price_interpolated": price_interpolated,
                }
            )

    if blockers:
        return _blocked(base, blockers)

    assert now_utc is not None
    assert charge_eff is not None and discharge_eff is not None and min_margin is not None
    assert capacity is not None and soc is not None and reserve_target is not None
    assert reserve_deficit is not None and free_above_reserve is not None and first_usable is not None

    charge_ratio = charge_eff / 100.0
    discharge_ratio = discharge_eff / 100.0
    roundtrip_ratio = charge_ratio * discharge_ratio
    current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
    future_rows = [row for row in parsed_rows if row["end"] > now_utc]
    trade_rows = [row for row in future_rows if not row["price_interpolated"]]

    safety_charge_needed = reserve_deficit > ENERGY_EPSILON_KWH
    remaining_battery_kwh = reserve_deficit
    safety_hours: list[dict[str, Any]] = []
    safety_candidates = [row for row in future_rows if row["start"] < first_usable]
    safety_candidates.sort(key=lambda row: (row["import_price"], row["start"]))
    for row in safety_candidates:
        if remaining_battery_kwh <= ENERGY_EPSILON_KWH:
            break
        available_fraction = 1.0
        if row["start"] <= now_utc < row["end"]:
            available_fraction = max(0.0, min(1.0, (row["end"] - now_utc).total_seconds() / 3600.0))
        max_battery_energy = max_charge_power_w / 1000.0 * available_fraction * charge_ratio
        if max_battery_energy <= 0:
            continue
        battery_energy = min(remaining_battery_kwh, max_battery_energy)
        grid_input = battery_energy / charge_ratio
        safety_hours.append(
            {
                "start": row["start"].isoformat(),
                "end": row["end"].isoformat(),
                "import_price": round(row["import_price"], 6),
                "price_interpolated": row["price_interpolated"],
                "available_hour_fraction": round(available_fraction, 6),
                "max_battery_energy_kwh": round(max_battery_energy, 3),
                "candidate_battery_energy_kwh": round(battery_energy, 3),
                "required_grid_input_kwh": round(grid_input, 3),
            }
        )
        remaining_battery_kwh -= battery_energy

    safety_unallocated = max(remaining_battery_kwh, 0.0)
    safety_schedule_sufficient = not safety_charge_needed or safety_unallocated <= ENERGY_EPSILON_KWH
    required_grid_input = reserve_deficit / charge_ratio if safety_charge_needed else 0.0

    max_deliverable_from_free = free_above_reserve * discharge_ratio
    discharge_allowed = not safety_charge_needed and free_above_reserve > ENERGY_EPSILON_KWH and soc > reserve_target

    free_capacity_kwh = capacity * max(100.0 - soc, 0.0) / 100.0
    solar_capacity_protection = not safety_charge_needed and first_usable > now_utc and free_capacity_kwh > ENERGY_EPSILON_KWH
    solar_window_end_ts = first_usable.timestamp() + SOLAR_PROTECTION_HOURS * 3600
    solar_window = [row for row in parsed_rows if first_usable <= row["start"] and row["start"].timestamp() < solar_window_end_ts]
    solar_surplus_ac_kwh = sum(max(row["solar_kwh"] - row["home_kwh"], 0.0) for row in solar_window)

    import_prices = [row["import_price"] for row in future_rows]
    price_min_import = min(import_prices) if import_prices else None
    price_max_import = max(import_prices) if import_prices else None
    price_spread_import = price_max_import - price_min_import if price_min_import is not None and price_max_import is not None else None

    best_self_use: dict[str, Any] | None = None
    best_export: dict[str, Any] | None = None
    for i, charge_row in enumerate(trade_rows):
        effective_cost = charge_row["import_price"] / roundtrip_ratio
        for discharge_row in trade_rows[i + 1 :]:
            self_use_margin = discharge_row["import_price"] - effective_cost
            export_margin = discharge_row["export_price"] - effective_cost
            if best_self_use is None or self_use_margin > best_self_use["margin"]:
                best_self_use = {"charge_time": charge_row["start"], "charge_price": charge_row["import_price"], "discharge_time": discharge_row["start"], "discharge_price": discharge_row["import_price"], "effective_cost": effective_cost, "margin": self_use_margin}
            if best_export is None or export_margin > best_export["margin"]:
                best_export = {"charge_time": charge_row["start"], "charge_price": charge_row["import_price"], "discharge_time": discharge_row["start"], "discharge_price": discharge_row["export_price"], "effective_cost": effective_cost, "margin": export_margin}

    self_use_profitable = bool(best_self_use is not None and best_self_use["margin"] >= min_margin)
    export_profitable = bool(best_export is not None and best_export["margin"] >= min_margin)
    current_is_self_use_discharge = bool(best_self_use is not None and best_self_use["discharge_time"] == current_hour and self_use_profitable)
    current_is_export_discharge = bool(best_export is not None and best_export["discharge_time"] == current_hour and export_profitable)
    current_is_best_charge = bool(
        (best_self_use is not None and best_self_use["charge_time"] == current_hour and self_use_profitable)
        or (best_export is not None and best_export["charge_time"] == current_hour and export_profitable)
    )

    if safety_charge_needed:
        preview_decision = "safety_charge_preview"
        reason = "reserve_deficit_can_be_allocated_before_usable_solar" if safety_schedule_sufficient else "reserve_deficit_exceeds_available_pre_solar_charge_window"
    elif discharge_allowed and current_is_self_use_discharge:
        preview_decision = "discharge_self_use_preview"
        reason = "current_hour_best_self_use_discharge_candidate"
    elif discharge_allowed and current_is_export_discharge:
        preview_decision = "export_trade_preview"
        reason = "current_hour_best_export_discharge_candidate"
    elif current_is_best_charge and not solar_capacity_protection:
        preview_decision = "trade_charge_preview"
        reason = "current_hour_best_profitable_charge_candidate"
    elif solar_capacity_protection:
        preview_decision = "wait_for_solar"
        reason = "preserve_free_capacity_for_expected_usable_solar"
    elif self_use_profitable or export_profitable:
        preview_decision = "wait_for_later_candidate"
        reason = "profitable_pair_exists_but_current_hour_not_leading"
    else:
        preview_decision = "no_action"
        reason = "no_safety_need_and_no_profitable_pair"

    result_status = "degraded" if effective_horizon < HOURS or input_result.get("status") in {"degraded", "partial"} else "ready"
    return {
        **base,
        "status": result_status,
        "valid": True,
        "reason": reason,
        "blockers": [],
        "preview_decision": preview_decision,
        "required_grid_input_kwh": round(required_grid_input, 3),
        "safety_charge_needed": safety_charge_needed,
        "safety_charge_hours": safety_hours,
        "safety_charge_hour_count": len(safety_hours),
        "safety_schedule_sufficient": safety_schedule_sufficient,
        "safety_unallocated_battery_kwh": round(safety_unallocated, 3),
        "free_capacity_kwh": round(free_capacity_kwh, 3),
        "max_deliverable_from_free_kwh": round(max_deliverable_from_free, 3),
        "charge_efficiency_percent": round(charge_eff, 3),
        "discharge_efficiency_percent": round(discharge_eff, 3),
        "roundtrip_efficiency_percent": round(roundtrip_ratio * 100.0, 3),
        "minimum_trade_margin": round(min_margin, 6),
        "max_charge_power_w": int(max_charge_power_w),
        "max_discharge_power_w": int(max_discharge_power_w),
        "price_min_import": round(price_min_import, 6) if price_min_import is not None else None,
        "price_max_import": round(price_max_import, 6) if price_max_import is not None else None,
        "price_spread_import": round(price_spread_import, 6) if price_spread_import is not None else None,
        "best_self_use_charge_time": best_self_use["charge_time"].isoformat() if best_self_use else None,
        "best_self_use_charge_price": round(best_self_use["charge_price"], 6) if best_self_use else None,
        "best_self_use_discharge_time": best_self_use["discharge_time"].isoformat() if best_self_use else None,
        "best_self_use_discharge_import_price": round(best_self_use["discharge_price"], 6) if best_self_use else None,
        "best_self_use_margin": round(best_self_use["margin"], 6) if best_self_use else None,
        "best_export_charge_time": best_export["charge_time"].isoformat() if best_export else None,
        "best_export_charge_price": round(best_export["charge_price"], 6) if best_export else None,
        "best_export_discharge_time": best_export["discharge_time"].isoformat() if best_export else None,
        "best_export_discharge_export_price": round(best_export["discharge_price"], 6) if best_export else None,
        "best_export_margin": round(best_export["margin"], 6) if best_export else None,
        "self_use_trade_profitable": self_use_profitable,
        "export_trade_profitable": export_profitable,
        "solar_capacity_protection": solar_capacity_protection,
        "solar_surplus_ac_kwh": round(solar_surplus_ac_kwh, 3),
        "discharge_preview_allowed": discharge_allowed,
        "current_hour": current_hour.isoformat(),
        "trade_rows_excluded_interpolated": len(future_rows) - len(trade_rows),
    }
