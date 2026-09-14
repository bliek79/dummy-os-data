"""Golden parity tests for the copied alpha76 EMS decision core."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.dummy_os_data.ems_alpha76.energy_need import build_energy_need_analysis
from custom_components.dummy_os_data.ems_alpha76.planner_preview import build_planner_preview
from custom_components.dummy_os_data.ems_alpha76.planner_72h import build_72h_plan_preview
from custom_components.dummy_os_data.ems_alpha76_adapter import (
    forecast_from_input,
    planner_reference,
    run_energy_need,
    run_preview,
    run_plan72,
)

BASE = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)


def make_input(*, soc=50.0, home=0.40, solar_start=8, solar=0.70, low_price=2, high_price=18):
    rows = []
    for i in range(72):
        start = BASE + timedelta(hours=i)
        home_kwh = float(home)
        solar_kwh = float(solar) if solar_start <= i <= solar_start + 4 else 0.0
        import_price = 0.18
        export_price = 0.12
        if i == low_price:
            import_price = 0.08
        if i == high_price:
            import_price = 0.45
            export_price = 0.38
        quarters = []
        for q in range(4):
            quarters.append({
                "start": (start + timedelta(minutes=15*q)).isoformat(),
                "kind": "known_pt15m",
            })
        rows.append({
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
            "home_kwh": home_kwh,
            "solar_kwh": solar_kwh,
            "import_price": import_price,
            "export_price": export_price,
            "price_source": "known",
            "price_quarters": quarters,
            "fully_valid": True,
        })
    return {
        "status": "ready",
        "valid": True,
        "rows": rows,
        "rows_signature": "fixture",
        "time_contract": {
            "window_start": BASE.isoformat(),
            "window_end": (BASE + timedelta(hours=72)).isoformat(),
            "window_id": "fixture-window",
        },
        "planner_resolution_minutes": 15,
        "planner_horizon_hours": 72,
        "planner_slot_count": 288,
    }, soc


def direct_chain(input_result, soc):
    forecast = forecast_from_input(input_result)
    now = planner_reference(input_result)
    need = build_energy_need_analysis(forecast, soc, 7.0, now=now)
    preview = build_planner_preview(
        forecast, need, soc, 92.0, 92.0, 0.10,
        max_charge_power_w=3200, now=now,
    )
    plan = build_72h_plan_preview(
        forecast, need, preview, soc, 92.0, 92.0,
        execution_buffer_percent=2.0,
        max_charge_power_w=3200,
        max_discharge_power_w=3200,
        now=now,
    )
    return need, preview, plan


def adapter_chain(input_result, soc):
    need = run_energy_need(input_result=input_result, soc_percent=soc, now=BASE)
    preview = run_preview(
        input_result=input_result, energy_need=need, soc_percent=soc,
        charge_efficiency_percent=92.0, discharge_efficiency_percent=92.0,
        minimum_trade_margin=0.10, max_charge_power_w=3200, now=BASE,
    )
    plan = run_plan72(
        input_result=input_result, energy_need=need, planner_preview=preview,
        soc_percent=soc, charge_efficiency_percent=92.0,
        discharge_efficiency_percent=92.0, execution_buffer_percent=2.0,
        max_charge_power_w=3200, max_discharge_power_w=3200, now=BASE,
    )
    return need, preview, plan


@pytest.mark.parametrize(
    "case,kwargs",
    [
        ("F01_idle_balanced", {"soc": 70.0, "home": 0.25, "solar_start": 2, "solar": 0.80}),
        ("F02_safety_shortage", {"soc": 15.0, "home": 0.65, "solar_start": 12, "solar": 0.90}),
        ("F03_100pct_reserve", {"soc": 20.0, "home": 0.75, "solar_start": 9, "solar": 0.90}),
        ("F04_low_soc", {"soc": 6.0, "home": 0.45, "solar_start": 5, "solar": 0.70}),
        ("F05_solar_delay", {"soc": 55.0, "home": 0.35, "solar_start": 3, "solar": 1.00}),
        ("F06_trade_charge", {"soc": 70.0, "home": 0.30, "solar_start": 7, "solar": 0.80, "low_price": 1, "high_price": 15}),
        ("F07_trade_discharge", {"soc": 90.0, "home": 0.20, "solar_start": 3, "solar": 0.80, "low_price": 1, "high_price": 8}),
        ("F08_no_trade", {"soc": 70.0, "home": 0.30, "solar_start": 5, "solar": 0.80, "low_price": 2, "high_price": 2}),
        ("F09_reserve_edge", {"soc": 25.0, "home": 0.50, "solar_start": 4, "solar": 0.60}),
        ("F10_long_shortage", {"soc": 35.0, "home": 0.55, "solar_start": 18, "solar": 0.90}),
        ("F11_high_solar", {"soc": 45.0, "home": 0.25, "solar_start": 1, "solar": 1.30}),
        ("F12_full_battery", {"soc": 100.0, "home": 0.35, "solar_start": 6, "solar": 0.80}),
        ("F13_near_min", {"soc": 5.1, "home": 0.35, "solar_start": 6, "solar": 0.80}),
        ("F14_morning_deficit", {"soc": 40.0, "home": 0.80, "solar_start": 7, "solar": 0.95}),
        ("F15_evening_value", {"soc": 85.0, "home": 0.30, "solar_start": 4, "solar": 0.85, "high_price": 11}),
        ("F16_two_usable_hours", {"soc": 50.0, "home": 0.40, "solar_start": 2, "solar": 0.40}),
        ("F17_safety_price_order", {"soc": 10.0, "home": 0.70, "solar_start": 10, "solar": 1.00, "low_price": 5}),
        ("F18_capacity_limit", {"soc": 8.0, "home": 0.95, "solar_start": 14, "solar": 1.20}),
        ("F19_home_priority", {"soc": 90.0, "home": 0.90, "solar_start": 5, "solar": 1.00, "high_price": 12}),
        ("F20_solar_first", {"soc": 50.0, "home": 0.20, "solar_start": 1, "solar": 1.20}),
        ("F21_trade_reservation", {"soc": 80.0, "home": 0.35, "solar_start": 3, "solar": 0.80, "low_price": 1, "high_price": 10}),
        ("F22_execution_buffer", {"soc": 18.0, "home": 0.55, "solar_start": 8, "solar": 0.85}),
        ("F23_multi_day", {"soc": 60.0, "home": 0.45, "solar_start": 20, "solar": 0.75}),
        ("F24_price_extremes", {"soc": 65.0, "home": 0.35, "solar_start": 6, "solar": 0.80, "low_price": 0, "high_price": 22}),
        ("F25_copy_baseline", {"soc": 50.0, "home": 0.40, "solar_start": 8, "solar": 0.70}),
    ],
)
def test_f01_f25_core_decisions_are_byte_for_byte_alpha76(case, kwargs):
    input_result, soc = make_input(**kwargs)
    expected = direct_chain(deepcopy(input_result), soc)
    actual = adapter_chain(deepcopy(input_result), soc)
    assert actual == expected, case


def test_adapter_does_not_fill_missing_home():
    input_result, _ = make_input()
    input_result["rows"][3]["home_kwh"] = None
    forecast = forecast_from_input(input_result)
    assert forecast[3]["home_consumption_kwh"] is None


def test_adapter_keeps_exact_72_rows_and_window_start():
    input_result, _ = make_input()
    forecast = forecast_from_input(input_result)
    assert len(forecast) == 72
    assert forecast[0]["time"] == BASE.isoformat()
    assert planner_reference(input_result) == BASE


def test_no_usable_solar_matches_alpha76_invalid_semantics():
    input_result, soc = make_input(solar_start=100)
    expected = direct_chain(input_result, soc)
    actual = adapter_chain(input_result, soc)
    assert actual == expected
    assert actual[0]["energy_need_valid"] is False
