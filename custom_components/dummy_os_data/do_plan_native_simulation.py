"""Native 15-minute sequential battery simulation and hourly aggregation."""
from __future__ import annotations
from typing import Any
from custom_components.dummy_os_data.do_plan_native_common import (
    CAPACITY_KWH, MIN_SOC_PERCENT, MAX_CHARGE_POWER_W, MAX_DISCHARGE_POWER_W,
    SLOTS_PER_HOUR, EPS, _future_solar_charge_potential,
)


def _simulate(
    *,
    slots: list[dict[str, Any]],
    start_soc: float,
    reserve_profile: list[dict[str, Any]],
    safety_slots: dict[str, float],
    trade: dict[str, Any] | None,
    charge_eff: float,
    discharge_eff: float,
) -> dict[str, Any]:
    stored = CAPACITY_KWH * start_soc / 100.0
    slot_charge_input_limit = MAX_CHARGE_POWER_W / 1000.0 / SLOTS_PER_HOUR
    slot_discharge_output_limit = MAX_DISCHARGE_POWER_W / 1000.0 / SLOTS_PER_HOUR
    out: list[dict[str, Any]] = []
    totals = {k: 0.0 for k in (
        "solar_to_home_kwh", "solar_to_battery_kwh", "solar_to_grid_kwh", "grid_to_home_kwh",
        "grid_to_battery_kwh", "grid_to_battery_safety_kwh", "grid_to_battery_trade_kwh",
        "battery_to_home_kwh", "battery_to_grid_kwh",
    )}
    reserve_breaches = 0
    buffer_breaches = 0
    trade_reserved_kwh = 0.0
    trade_discharge_index = None
    trade_charge_index = None
    if trade is not None:
        trade_charge_index = next((i for i, slot in enumerate(slots) if slot["start"] == trade.get("charge_time")), None)
        trade_discharge_index = next((i for i, slot in enumerate(slots) if slot["start"] == trade.get("discharge_time")), None)

    for index, slot in enumerate(slots):
        start_stored = stored
        reserve_start = reserve_profile[index]
        reserve_end = reserve_profile[index + 1]
        execution_floor_end = reserve_end["execution_floor_kwh"]

        home = slot["home_kwh"]
        solar = slot["solar_kwh"]
        solar_to_home = min(home, solar)
        remaining_home = home - solar_to_home
        solar_surplus = solar - solar_to_home

        solar_input = min(solar_surplus, slot_charge_input_limit, max(0.0, (CAPACITY_KWH - stored) / charge_eff))
        solar_to_battery = solar_input * charge_eff
        stored += solar_to_battery
        solar_to_grid = max(0.0, solar_surplus - solar_input)
        charge_input_left = max(0.0, slot_charge_input_limit - solar_input)

        safety_input = 0.0
        wanted_safety_stored = safety_slots.get(slot["start"], 0.0)
        if wanted_safety_stored > EPS and charge_input_left > EPS:
            requested = wanted_safety_stored / charge_eff
            safety_input = min(requested, charge_input_left, max(0.0, (CAPACITY_KWH - stored) / charge_eff))
            stored += safety_input * charge_eff
            charge_input_left -= safety_input

        trade_input = 0.0
        if trade is not None and trade_charge_index == index and charge_input_left > EPS and stored < CAPACITY_KWH - EPS:
            free_capacity = max(0.0, CAPACITY_KWH - stored)
            solar_fill = _future_solar_charge_potential(slots, index, trade_discharge_index if trade_discharge_index is not None else index, charge_eff)
            required_trade_stored = max(0.0, free_capacity - solar_fill)
            if required_trade_stored > EPS:
                trade_input = min(charge_input_left, required_trade_stored / charge_eff, max(0.0, (CAPACITY_KWH - stored) / charge_eff))
                stored_added = trade_input * charge_eff
                stored += stored_added
                trade_reserved_kwh += stored_added

        operational_floor = min(CAPACITY_KWH, execution_floor_end + trade_reserved_kwh)
        available_stored_above_floor = max(0.0, stored - operational_floor)
        max_output_from_storage = available_stored_above_floor * discharge_eff

        threshold_price = None
        if trade is not None:
            threshold_price = trade["effective_charge_cost"] + trade["minimum_trade_margin"]
        allow_home_discharge = trade_reserved_kwh <= EPS
        if threshold_price is not None and slot["import_price"] >= threshold_price:
            allow_home_discharge = True

        battery_to_home = 0.0
        if allow_home_discharge:
            battery_to_home = min(remaining_home, slot_discharge_output_limit, max_output_from_storage)
            if battery_to_home > EPS:
                stored_used = battery_to_home / discharge_eff
                stored -= stored_used
                remaining_home -= battery_to_home
                if trade_reserved_kwh > EPS:
                    trade_reserved_kwh = max(0.0, trade_reserved_kwh - stored_used)
        grid_to_home = max(0.0, remaining_home)

        battery_to_grid = 0.0
        remaining_output_limit = max(0.0, slot_discharge_output_limit - battery_to_home)
        if trade is not None and trade_discharge_index == index and remaining_output_limit > EPS:
            available_export = max(0.0, stored - execution_floor_end) * discharge_eff
            battery_to_grid = min(remaining_output_limit, available_export)
            if battery_to_grid > EPS:
                stored_used = battery_to_grid / discharge_eff
                stored -= stored_used
                trade_reserved_kwh = max(0.0, trade_reserved_kwh - stored_used)

        stored = min(CAPACITY_KWH, max(CAPACITY_KWH * MIN_SOC_PERCENT / 100.0, stored))
        end_soc = stored / CAPACITY_KWH * 100.0
        execution_headroom = end_soc - reserve_end["execution_floor_kwh"] / CAPACITY_KWH * 100.0
        if stored + EPS < reserve_end["dynamic_floor_kwh"]:
            reserve_breaches += 1
        if stored + EPS < reserve_end["execution_floor_kwh"]:
            buffer_breaches += 1

        action_parts: list[str] = []
        if safety_input > EPS:
            action_parts.append("safety_charge")
        if trade_input > EPS:
            action_parts.append("trade_charge")
        if solar_input > EPS:
            action_parts.append("solar_charge")
        if battery_to_home > EPS:
            action_parts.append("home_discharge")
        if battery_to_grid > EPS:
            action_parts.append("trade_discharge")
        if not action_parts:
            action_parts.append("baseline")

        values = {
            "solar_to_home_kwh": solar_to_home,
            "solar_to_battery_kwh": solar_to_battery,
            "solar_to_grid_kwh": solar_to_grid,
            "grid_to_home_kwh": grid_to_home,
            "grid_to_battery_kwh": safety_input + trade_input,
            "grid_to_battery_safety_kwh": safety_input,
            "grid_to_battery_trade_kwh": trade_input,
            "battery_to_home_kwh": battery_to_home,
            "battery_to_grid_kwh": battery_to_grid,
        }
        for key, value in values.items():
            totals[key] += value

        out.append(
            {
                "index": slot["index"],
                "hour_index": slot["hour_index"],
                "quarter_index": slot["quarter_index"],
                "start": slot["start"],
                "end": slot["end"],
                "home_kwh": round(home, 6),
                "solar_kwh": round(solar, 6),
                "import_price": round(slot["import_price"], 6),
                "export_price": round(slot["export_price"], 6),
                "price_kind": slot.get("price_kind"),
                "price_fallback_used": bool(slot.get("price_fallback_used")),
                "start_soc_percent": round(start_stored / CAPACITY_KWH * 100.0, 3),
                "end_soc_percent": round(end_soc, 3),
                "dynamic_reserve_start_soc_percent": round(reserve_start["dynamic_floor_kwh"] / CAPACITY_KWH * 100.0, 3),
                "dynamic_reserve_end_soc_percent": round(reserve_end["dynamic_floor_kwh"] / CAPACITY_KWH * 100.0, 3),
                "execution_reserve_start_soc_percent": round(reserve_start["execution_floor_kwh"] / CAPACITY_KWH * 100.0, 3),
                "execution_reserve_end_soc_percent": round(reserve_end["execution_floor_kwh"] / CAPACITY_KWH * 100.0, 3),
                "reserve_floor_soc_percent": round(reserve_end["dynamic_floor_kwh"] / CAPACITY_KWH * 100.0, 3),
                "execution_floor_soc_percent": round(reserve_end["execution_floor_kwh"] / CAPACITY_KWH * 100.0, 3),
                "dynamic_need_until_solar_kwh": round(reserve_start["need_until_solar_kwh"], 3),
                "dynamic_need_after_slot_kwh": round(reserve_end["need_until_solar_kwh"], 3),
                "next_usable_solar": reserve_start["next_usable_solar"],
                "solar_horizon_complete": reserve_start["solar_horizon_complete"],
                "execution_headroom_soc_percent": round(execution_headroom, 3),
                "trade_reserved_kwh": round(trade_reserved_kwh, 3),
                "action": "+".join(action_parts),
                "action_parts": action_parts,
                **{key: round(value, 6) for key, value in values.items()},
            }
        )

    return {
        "slots": out,
        "end_soc_percent": round(stored / CAPACITY_KWH * 100.0, 3),
        "reserve_breach_slots": reserve_breaches,
        "execution_buffer_breach_slots": buffer_breaches,
        **{key: round(value, 3) for key, value in totals.items()},
    }


def _aggregate_hours(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the 60-minute Apex contract from four native quarter results."""
    hours: list[dict[str, Any]] = []
    for offset in range(0, len(slots), SLOTS_PER_HOUR):
        group = slots[offset : offset + SLOTS_PER_HOUR]
        if not group:
            continue
        flow_keys = (
            "solar_to_home_kwh", "solar_to_battery_kwh", "solar_to_grid_kwh", "grid_to_home_kwh",
            "grid_to_battery_kwh", "grid_to_battery_safety_kwh", "grid_to_battery_trade_kwh",
            "battery_to_home_kwh", "battery_to_grid_kwh",
        )
        actions: list[str] = []
        for item in group:
            for action in item.get("action_parts") or []:
                if action != "baseline" and action not in actions:
                    actions.append(action)
        if not actions:
            actions = ["baseline"]
        hours.append(
            {
                "index": len(hours),
                "start": group[0]["start"],
                "end": group[-1]["end"],
                "slot_count": len(group),
                # Apex energy inputs are exact sums of the four native quarters.
                "home_kwh": round(sum(item["home_kwh"] for item in group), 3),
                "solar_kwh": round(sum(item["solar_kwh"] for item in group), 3),
                "start_soc_percent": group[0]["start_soc_percent"],
                "end_soc_percent": group[-1]["end_soc_percent"],
                "dynamic_reserve_start_soc_percent": group[0]["dynamic_reserve_start_soc_percent"],
                "dynamic_reserve_end_soc_percent": group[-1]["dynamic_reserve_end_soc_percent"],
                "execution_reserve_start_soc_percent": group[0]["execution_reserve_start_soc_percent"],
                "execution_reserve_end_soc_percent": group[-1]["execution_reserve_end_soc_percent"],
                "reserve_floor_soc_percent": group[-1]["dynamic_reserve_end_soc_percent"],
                "execution_floor_soc_percent": group[-1]["execution_reserve_end_soc_percent"],
                "dynamic_need_until_solar_kwh": group[0]["dynamic_need_until_solar_kwh"],
                "dynamic_need_after_hour_kwh": group[-1]["dynamic_need_after_slot_kwh"],
                "next_usable_solar": group[0]["next_usable_solar"],
                "solar_horizon_complete": all(item.get("solar_horizon_complete") is True for item in group),
                "execution_headroom_soc_percent": group[-1]["execution_headroom_soc_percent"],
                "action": "+".join(actions),
                **{key: round(sum(item[key] for item in group), 3) for key in flow_keys},
            }
        )
    return hours
