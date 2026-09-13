"""Alpha 32 native 288-slot planner parity regressions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.dummy_os_data.do_plan_72h import build_do_plan_72h


def _native_input(*, usable_solar_slots: int = 8, interpolated_index: int | None = None) -> tuple[dict, dict, dict]:
    start = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
    rows = []
    for hour in range(72):
        hour_start = start + timedelta(hours=hour)
        home_quarters = []
        solar_quarters = []
        price_quarters = []
        for q in range(4):
            idx = hour * 4 + q
            q_start = hour_start + timedelta(minutes=15 * q)
            home = 0.10
            solar = 0.15 if 48 <= idx < 48 + usable_solar_slots else 0.0
            price = 0.12 if idx == 4 else (0.45 if idx == 80 else 0.24)
            kind = "interpolated" if idx == interpolated_index else "known_pt15m"
            fallback = idx == interpolated_index
            home_quarters.append({"start": q_start.isoformat(), "end": (q_start + timedelta(minutes=15)).isoformat(), "kwh": home})
            solar_quarters.append({"start": q_start.isoformat(), "kwh": solar})
            price_quarters.append({
                "start": q_start.isoformat(),
                "import_price": price,
                "export_price": price - 0.08,
                "kind": kind,
                "fallback_used": fallback,
                "source_resolution_minutes": 15,
            })
        rows.append({
            "index": hour,
            "start": hour_start.isoformat(),
            "end": (hour_start + timedelta(hours=1)).isoformat(),
            "home_kwh": 0.4,
            "solar_kwh": sum(item["kwh"] for item in solar_quarters),
            "import_price": sum(item["import_price"] for item in price_quarters) / 4,
            "export_price": sum(item["export_price"] for item in price_quarters) / 4,
            "fully_valid": True,
            "home_quarters": home_quarters,
            "solar_quarters": solar_quarters,
            "price_quarters": price_quarters,
        })
    inp = {
        "status": "ready",
        "fully_valid_hours": 72,
        "effective_horizon_hours": 72,
        "valid_through": (start + timedelta(hours=72)).isoformat(),
        "rows_signature": "alpha32-native",
        "rows": rows,
    }
    reserve = {
        "status": "ready",
        "valid": True,
        "input_rows_signature": "alpha32-native",
        "soc_percent": 90.0,
        "reserve_soc_target_percent": 12.0,
        "grid_support_required": False,
    }
    preview = {
        "status": "ready",
        "valid": True,
        "input_rows_signature": "alpha32-native",
        "safety_charge_hours": [],
        "self_use_trade_profitable": False,
        "export_trade_profitable": False,
        "minimum_trade_margin": 0.10,
    }
    return inp, reserve, preview


def test_plan72_runs_native_288_slots_and_keeps_hourly_apex_view():
    inp, reserve, preview = _native_input()
    out = build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    assert out["slot_count"] == 288
    assert out["simulated_slot_count"] == 288
    assert out["hour_count"] == 72
    assert len(out["hours"]) == 72
    assert out["quarter_source"] == "native_quarters"
    assert out["planner_resolution_minutes"] == 15
    assert out["dashboard_resolution_minutes"] == 60
    assert out["apex_contract"] == "hourly_aggregation_derived_from_native_quarters"


def test_dynamic_reserve_is_not_flat_when_future_need_changes():
    inp, reserve, preview = _native_input()
    out = build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    values = [hour["dynamic_reserve_end_soc_percent"] for hour in out["hours"]]
    assert max(values) > min(values)
    assert out["reserve_recalculated"] is True
    assert out["dynamic_reserve_max_soc_percent"] > out["dynamic_reserve_min_soc_percent"]


def test_usable_solar_requires_full_eight_consecutive_quarters():
    inp7, reserve7, preview7 = _native_input(usable_solar_slots=7)
    out7 = build_do_plan_72h(input_result=inp7, reserve_result=reserve7, preview_result=preview7)
    assert out7["hours"][0]["next_usable_solar"] is None
    inp8, reserve8, preview8 = _native_input(usable_solar_slots=8)
    out8 = build_do_plan_72h(input_result=inp8, reserve_result=reserve8, preview_result=preview8)
    assert out8["hours"][0]["next_usable_solar"] is not None
    assert out8["usable_solar_consecutive_slots"] == 8
    assert out8["usable_solar_duration_hours"] == 2.0


def test_native_charge_and_discharge_limits_are_quarter_based():
    inp, reserve, preview = _native_input()
    preview["safety_charge_hours"] = [{"start": inp["rows"][0]["start"], "candidate_battery_energy_kwh": 3.0}]
    out = build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    for slot in out["slots"]:
        assert slot["grid_to_battery_kwh"] <= 0.800001
        assert slot["battery_to_home_kwh"] + slot["battery_to_grid_kwh"] <= 0.800001


def test_hourly_apex_energy_is_sum_of_four_native_slots():
    inp, reserve, preview = _native_input()
    out = build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    first_slots = out["slots"][:4]
    first_hour = out["hours"][0]
    for key in ("solar_to_battery_kwh", "grid_to_battery_safety_kwh", "grid_to_battery_trade_kwh", "battery_to_home_kwh", "battery_to_grid_kwh"):
        assert abs(first_hour[key] - round(sum(slot[key] for slot in first_slots), 3)) < 0.002
    assert first_hour["end_soc_percent"] == first_slots[-1]["end_soc_percent"]
    assert first_hour["dynamic_reserve_end_soc_percent"] == first_slots[-1]["dynamic_reserve_end_soc_percent"]


def test_interpolated_price_slot_never_becomes_trade_extremum():
    inp, reserve, preview = _native_input(interpolated_index=4)
    inp["rows"][1]["price_quarters"][0]["import_price"] = -1.0
    inp["rows"][1]["import_price"] = sum(q["import_price"] for q in inp["rows"][1]["price_quarters"]) / 4
    out = build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    trade = out["trade_candidate"]
    if trade is not None:
        assert trade["charge_time"] != inp["rows"][1]["price_quarters"][0]["start"]


def test_shadow_authority_remains_false():
    inp, reserve, preview = _native_input()
    out = build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    assert out["shadow_only"] is True
    assert out["active_use_permitted"] is False
    assert out["physical_execution_authority"] is False
