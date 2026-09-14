"""Adapter between Dummy OS Data forecast contracts and the alpha76 EMS engine.

This module is deliberately thin.  It may translate schemas and expose the
15-minute transport window, but it must not add or change EMS policy.  The
functional decisions are made by the vendored Dummy OS EMS 0.0.1-alpha.76
modules in ``ems_alpha76``.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from .ems_alpha76.energy_need import build_energy_need_analysis
from .ems_alpha76.planner_preview import build_planner_preview
from .ems_alpha76.planner_72h import build_72h_plan_preview

SOURCE_TAG = "0.0.1-alpha.76"
BATTERY_CAPACITY_KWH = 7.2
MIN_SOC_PERCENT = 5.0
SOFTWARE_RESERVE_PERCENT = 7.0
CHARGE_EFFICIENCY_PERCENT = 92.0
DISCHARGE_EFFICIENCY_PERCENT = 92.0
MINIMUM_TRADE_MARGIN = 0.10
EXECUTION_BUFFER_PERCENT = 2.0
MAX_CHARGE_POWER_W = 3200
MAX_DISCHARGE_POWER_W = 3200


def _aware(value: Any) -> datetime | None:
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


def planner_reference(input_result: dict[str, Any], fallback: datetime | None = None) -> datetime:
    """Return the exact start of the central 288-slot planner window.

    The new forecast architecture starts at the shared quarter boundary.  SOC is
    already bridged to this same instant.  Alpha76 therefore receives this
    instant as ``now``; this is an interface translation only, not planner
    policy.
    """
    contract = input_result.get("time_contract") or {}
    for key in ("window_start", "planner_start", "start"):
        parsed = _aware(contract.get(key))
        if parsed is not None:
            return parsed
    parsed = _aware(input_result.get("planner_start")) or _aware(input_result.get("window_start"))
    if parsed is not None:
        return parsed
    if fallback is not None:
        if fallback.tzinfo is None:
            raise ValueError("fallback reference must be timezone-aware")
        return fallback.astimezone(timezone.utc)
    raise ValueError("planner window start missing")


def forecast_from_input(input_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate the validated 72 transport rows to alpha76 forecast rows.

    Four native quarters remain the source truth for every transport row.  The
    adapter does not fill missing values, interpolate data or reinterpret
    prices.  Invalid/missing rows stay incomplete so alpha76 can apply its own
    original validity logic.
    """
    rows = input_result.get("rows")
    if not isinstance(rows, list) or len(rows) != 72:
        raise ValueError("alpha76 adapter requires exactly 72 transport rows")

    forecast: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise ValueError(f"planner row {index} is invalid")
        start = _aware(raw.get("start"))
        if start is None:
            raise ValueError(f"planner row {index} has invalid timestamp")

        source = raw.get("price_source")
        if source is None:
            quarters = raw.get("price_quarters") or []
            kinds = {
                str(item.get("kind"))
                for item in quarters
                if isinstance(item, dict) and item.get("kind") is not None
            }
            if kinds and all(kind.startswith("known") for kind in kinds):
                source = "known"
            elif kinds:
                source = "forecast"

        forecast.append(
            {
                "time": start.isoformat(),
                "home_consumption_kwh": raw.get("home_kwh"),
                "solar_kwh": raw.get("solar_kwh"),
                "price": raw.get("import_price"),
                "import_price": raw.get("import_price"),
                "export_price": raw.get("export_price"),
                "price_source": source,
                "import_price_source": raw.get("import_price_source") or source,
                "export_price_source": raw.get("export_price_source") or source,
                "adapter_row_index": index,
            }
        )
    return forecast


def run_energy_need(
    *,
    input_result: dict[str, Any],
    soc_percent: float | None,
    safety_reserve_percent: float = SOFTWARE_RESERVE_PERCENT,
    now: datetime | None = None,
) -> dict[str, Any]:
    forecast = forecast_from_input(input_result)
    reference = planner_reference(input_result, now)
    return build_energy_need_analysis(
        forecast,
        soc_percent,
        safety_reserve_percent,
        now=reference,
    )


def run_preview(
    *,
    input_result: dict[str, Any],
    energy_need: dict[str, Any],
    soc_percent: float | None,
    charge_efficiency_percent: float = CHARGE_EFFICIENCY_PERCENT,
    discharge_efficiency_percent: float = DISCHARGE_EFFICIENCY_PERCENT,
    minimum_trade_margin: float = MINIMUM_TRADE_MARGIN,
    max_charge_power_w: int = MAX_CHARGE_POWER_W,
    now: datetime | None = None,
) -> dict[str, Any]:
    forecast = forecast_from_input(input_result)
    reference = planner_reference(input_result, now)
    return build_planner_preview(
        forecast,
        energy_need,
        soc_percent,
        charge_efficiency_percent,
        discharge_efficiency_percent,
        minimum_trade_margin,
        max_charge_power_w=max_charge_power_w,
        now=reference,
    )


def run_plan72(
    *,
    input_result: dict[str, Any],
    energy_need: dict[str, Any],
    planner_preview: dict[str, Any],
    soc_percent: float | None,
    charge_efficiency_percent: float = CHARGE_EFFICIENCY_PERCENT,
    discharge_efficiency_percent: float = DISCHARGE_EFFICIENCY_PERCENT,
    execution_buffer_percent: float = EXECUTION_BUFFER_PERCENT,
    max_charge_power_w: int = MAX_CHARGE_POWER_W,
    max_discharge_power_w: int = MAX_DISCHARGE_POWER_W,
    now: datetime | None = None,
) -> dict[str, Any]:
    forecast = forecast_from_input(input_result)
    reference = planner_reference(input_result, now)
    return build_72h_plan_preview(
        forecast,
        energy_need,
        planner_preview,
        soc_percent,
        charge_efficiency_percent,
        discharge_efficiency_percent,
        execution_buffer_percent=execution_buffer_percent,
        max_charge_power_w=max_charge_power_w,
        max_discharge_power_w=max_discharge_power_w,
        now=reference,
    )


def energy_need_public(
    raw: dict[str, Any], *, input_result: dict[str, Any], soc_percent: float | None
) -> dict[str, Any]:
    """Expose alpha76 Energy Need through the current sensor contract."""
    result = {
        "status": "ready" if raw.get("energy_need_valid") else "waiting_for_usable_solar",
        "valid": bool(raw.get("energy_need_valid")),
        "reason": raw.get("energy_need_reason"),
        "blockers": [] if raw.get("energy_need_valid") else ["alpha76_energy_need_not_valid"],
        "input_status": input_result.get("status"),
        "input_rows_signature": input_result.get("rows_signature"),
        "battery_capacity_kwh": raw.get("energy_need_battery_capacity_kwh", BATTERY_CAPACITY_KWH),
        "min_soc_percent": raw.get("energy_need_min_soc_percent", MIN_SOC_PERCENT),
        "safety_reserve_percent": raw.get("energy_need_safety_reserve_percent", SOFTWARE_RESERVE_PERCENT),
        "soc_percent": soc_percent,
        "energy_need_until_solar_kwh": raw.get("energy_need_until_solar_kwh"),
        "first_usable_solar": raw.get("energy_need_first_usable_solar"),
        "available_battery_kwh": raw.get("energy_need_available_battery_kwh"),
        "safety_reserve_kwh": raw.get("energy_need_safety_reserve_kwh"),
        "required_including_reserve_kwh": raw.get("energy_need_required_including_reserve_kwh"),
        "additional_grid_charge_kwh": raw.get("energy_need_additional_grid_charge_kwh"),
        "tradable_battery_kwh": raw.get("energy_need_tradable_battery_kwh"),
        "contributing_hours": raw.get("energy_need_contributing_hours"),
        "usable_solar_rule": raw.get("energy_need_usable_solar_rule"),
        "ems_policy_source": SOURCE_TAG,
        "alpha76_energy_need": deepcopy(raw),
        "shadow_only": True,
        "active_use_permitted": False,
        "physical_execution_authority": False,
    }
    if input_result.get("time_contract") is not None:
        result["time_contract"] = deepcopy(input_result["time_contract"])
    for key in (
        "planner_resolution_minutes", "planner_horizon_hours", "planner_slot_count",
        "window_start", "window_end", "window_id",
    ):
        if key in input_result:
            result[key] = input_result[key]
    return result


def preview_public(raw: dict[str, Any], *, input_result: dict[str, Any]) -> dict[str, Any]:
    """Expose alpha76 preview without changing its decision."""
    decision_map = {
        "wachten": "wait_for_solar" if raw.get("planner_preview_solar_charge_delay") else "wait_for_later_candidate",
        "veiligheidsladen": "safety_charge_preview",
        "ontladen": "export_trade_preview",
        "handelsladen": "trade_charge_preview",
        "geen_actie": "no_action",
    }
    return {
        "status": "ready" if raw.get("planner_preview_status") == "ready" else "blocked",
        "valid": raw.get("planner_preview_status") == "ready",
        "reason": raw.get("planner_preview_reason"),
        "blockers": [] if raw.get("planner_preview_status") == "ready" else ["alpha76_preview_not_ready"],
        "preview_decision": decision_map.get(raw.get("planner_preview_decision"), raw.get("planner_preview_decision")),
        "alpha76_preview_decision": raw.get("planner_preview_decision"),
        "first_usable_solar": raw.get("planner_preview_first_usable_solar"),
        "soc_percent": None,
        "reserve_soc_target_percent": raw.get("planner_preview_required_min_soc"),
        "reserve_deficit_battery_kwh": raw.get("planner_preview_safety_charge_kwh"),
        "free_above_reserve_battery_kwh": raw.get("planner_preview_energy_above_reserve_kwh"),
        "safety_charge_needed": raw.get("planner_preview_safety_charge_needed"),
        "safety_charge_hours": deepcopy(raw.get("planner_preview_safety_charge_hours") or []),
        "safety_charge_hour_count": raw.get("planner_preview_safety_charge_hour_count"),
        "safety_schedule_sufficient": raw.get("planner_preview_safety_schedule_sufficient"),
        "solar_capacity_protection": raw.get("planner_preview_solar_charge_delay"),
        "self_use_trade_profitable": raw.get("planner_preview_trade_profitable"),
        "export_trade_profitable": raw.get("planner_preview_trade_profitable"),
        "ems_policy_source": SOURCE_TAG,
        "alpha76_planner_preview": deepcopy(raw),
        "shadow_only": True,
        "active_use_permitted": False,
        "physical_execution_authority": False,
        "time_contract": deepcopy(input_result.get("time_contract")) if input_result.get("time_contract") else None,
    }


def _quarter_display_rows(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive non-authoritative 15-minute display rows from alpha76 hours.

    Execution must never consume these rows.  They exist only so the native
    288-slot presentation contract remains available while the EMS decision
    itself is alpha76-hourly.
    """
    slots: list[dict[str, Any]] = []
    for hour_index, row in enumerate(plan):
        start = _aware(row.get("time"))
        if start is None:
            continue
        for quarter in range(4):
            qstart = start + timedelta(minutes=15 * quarter)
            qend = qstart + timedelta(minutes=15)
            item = {
                "index": hour_index * 4 + quarter,
                "start": qstart.isoformat(),
                "end": qend.isoformat(),
                "derived_from_alpha76_hourly_decision": True,
                "authoritative_for_execution": False,
                "action": row.get("action"),
            }
            for old_key, new_key in (
                ("solar_kwh", "solar_kwh"),
                ("home_consumption_kwh", "home_kwh"),
                ("charge_from_grid_kwh", "grid_to_battery_kwh"),
                ("charge_from_grid_safety_kwh", "grid_to_battery_safety_kwh"),
                ("charge_from_grid_trade_kwh", "grid_to_battery_trade_kwh"),
                ("discharge_to_grid_kwh", "battery_to_grid_kwh"),
                ("discharge_to_home_kwh", "battery_to_home_kwh"),
                ("grid_import_for_home_kwh", "grid_to_home_kwh"),
                ("solar_export_kwh", "solar_to_grid_kwh"),
            ):
                value = row.get(old_key)
                item[new_key] = round(float(value) / 4.0, 6) if value is not None else None
            soc_start = row.get("soc_start")
            soc_end = row.get("soc_end")
            if soc_start is not None and soc_end is not None:
                delta = (float(soc_end) - float(soc_start)) / 4.0
                item["start_soc_percent"] = round(float(soc_start) + quarter * delta, 6)
                item["end_soc_percent"] = round(float(soc_start) + (quarter + 1) * delta, 6)
            slots.append(item)
    return slots


def plan72_public(raw: dict[str, Any], *, input_result: dict[str, Any]) -> dict[str, Any]:
    plan = deepcopy(raw.get("auto_plan_72h_plan") or [])
    hours = []
    for row in plan:
        start = _aware(row.get("time"))
        end = start + timedelta(hours=1) if start is not None else None
        hours.append(
            {
                **deepcopy(row),
                "start": start.isoformat() if start else row.get("time"),
                "end": end.isoformat() if end else None,
                "start_soc_percent": row.get("soc_start"),
                "end_soc_percent": row.get("soc_end"),
                "grid_to_battery_kwh": row.get("charge_from_grid_kwh"),
                "grid_to_battery_safety_kwh": row.get("charge_from_grid_safety_kwh"),
                "grid_to_battery_trade_kwh": row.get("charge_from_grid_trade_kwh"),
                "battery_to_grid_kwh": row.get("discharge_to_grid_kwh"),
                "battery_to_home_kwh": row.get("discharge_to_home_kwh"),
            }
        )
    return {
        "status": "ready" if raw.get("auto_plan_72h_valid") else "blocked",
        "valid": bool(raw.get("auto_plan_72h_valid")),
        "reason": raw.get("auto_plan_72h_reason"),
        "blockers": [] if raw.get("auto_plan_72h_valid") else ["alpha76_plan72_not_valid"],
        "hour_count": len(hours),
        "slot_count": len(hours) * 4,
        "hours": hours,
        "slots": _quarter_display_rows(plan),
        "start_soc_percent": raw.get("auto_plan_72h_start_soc"),
        "end_soc_percent": raw.get("auto_plan_72h_end_soc"),
        "min_soc_percent": raw.get("auto_plan_72h_min_soc"),
        "max_soc_percent": raw.get("auto_plan_72h_max_soc"),
        "execution_buffer_percent": raw.get("auto_plan_72h_execution_buffer_percent"),
        "execution_buffer_safe": raw.get("auto_plan_72h_execution_buffer_safe"),
        "execution_buffer_breach_hours": raw.get("auto_plan_72h_execution_buffer_breach_hours"),
        "minimum_execution_headroom_soc": raw.get("auto_plan_72h_min_execution_headroom_soc"),
        "ems_policy_source": SOURCE_TAG,
        "safety_plan_authority": "alpha76_plan72",
        "alpha76_plan72": deepcopy(raw),
        "shadow_only": True,
        "active_use_permitted": False,
        "physical_execution_authority": False,
        "plan_store_write": False,
        "scheduler_invoked": False,
        "safety_chain_invoked": False,
        "service_calls_performed": False,
        "time_contract": deepcopy(input_result.get("time_contract")) if input_result.get("time_contract") else None,
    }
