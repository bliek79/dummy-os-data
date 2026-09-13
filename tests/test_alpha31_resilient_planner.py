"""Alpha 31 resilience regression tests."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load(name: str):
    path = ROOT / f"custom_components/dummy_os_data/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INPUT = _load("do_plan_input")
ENERGY = _load("do_plan_energy_need")
PLAN72 = _load("do_plan_72h")


@dataclass
class SolarPoint:
    start: datetime
    total_kwh: float


@dataclass
class PricePoint:
    start: datetime
    import_all_in: float
    export_all_in: float
    kind: str = "forecast_hour"
    source_resolution_minutes: int = 60


def _contract(start: datetime) -> dict:
    hours = []
    for index in range(72):
        hour_start = start + timedelta(hours=index)
        quarters = []
        for q in range(4):
            q_start = hour_start + timedelta(minutes=15*q)
            quarters.append({
                "start": q_start.isoformat(),
                "end": (q_start + timedelta(minutes=15)).isoformat(),
                "energy_kwh": 0.1,
            })
        hours.append({
            "index": index,
            "start": hour_start.isoformat(),
            "end": (hour_start + timedelta(hours=1)).isoformat(),
            "energy_kwh": 0.4,
            "quarters": quarters,
        })
    return {
        "contract_name": "dummy_os_forecast_to_planner",
        "contract_version": 1,
        "schema_version": 1,
        "profile_contract_version": 1,
        "ready_for_planner": True,
        "profile": "normal",
        "native_resolution_minutes": 15,
        "native_slot_count": 288,
        "planner_resolution_minutes": 60,
        "planner_hour_count": 72,
        "quarters_per_hour": 4,
        "planner_start": start.isoformat(),
        "planner_end": (start + timedelta(hours=72)).isoformat(),
        "padding_used": False,
        "second_forecast_architecture": False,
        "physical_execution_authority": False,
        "consumer_scope": "dummy_os_ems_planner",
        "runtime_input_status": "ok",
        "forecast_operational_input_ok": True,
        "runtime_blockers": [],
        "hours": hours,
    }


def _points(start: datetime):
    solar = []
    prices = []
    for index in range(288):
        quarter = start + timedelta(minutes=15*index)
        solar.append(SolarPoint(quarter, 0.2))
        prices.append(PricePoint(quarter, 0.20 + index/10000.0, 0.10 + index/10000.0))
    return solar, prices


def _build(start: datetime, prices):
    solar, _ = _points(start)
    return INPUT.build_do_plan_input_72h(
        contract=_contract(start),
        solar_points=solar,
        price_points=prices,
        solar_status="ok",
        prices_status="ok",
        prices_freshness="fresh",
    )


def test_single_isolated_price_gap_is_interpolated_with_provenance() -> None:
    start = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    _, prices = _points(start)
    before = prices[4].import_all_in
    after = prices[6].import_all_in
    prices.pop(5)
    result = _build(start, prices)
    quarter = result["rows"][1]["price_quarters"][1]
    assert result["status"] == "ready"
    assert result["fully_valid_hours"] == 72
    assert result["effective_horizon_hours"] == 72
    assert result["interpolated_price_slots"] == 1
    assert quarter["kind"] == "interpolated"
    assert quarter["fallback_used"] is True
    assert quarter["fallback_method"] == "neighbor_average"
    assert abs(quarter["import_price"] - ((before + after) / 2.0)) < 1e-12


def test_two_consecutive_trailing_price_gaps_are_not_interpolated() -> None:
    start = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    _, prices = _points(start)
    prices = [point for index, point in enumerate(prices) if index not in {284, 285}]
    result = _build(start, prices)
    assert result["status"] == "degraded"
    assert result["valid_price_hours"] == 71
    assert result["effective_horizon_hours"] == 71
    assert result["first_invalid_index"] == 71
    assert result["first_invalid_reason"] == "missing_price"
    assert result["trailing_incomplete_only"] is True
    assert result["interpolated_price_slots"] == 0


def test_trailing_price_gap_does_not_block_energy_need() -> None:
    start = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    _, prices = _points(start)
    prices = prices[:-4]
    inp = _build(start, prices)
    assert inp["status"] == "degraded"
    assert inp["effective_horizon_hours"] == 71
    need = ENERGY.build_do_plan_energy_need(input_result=inp, soc_percent=50.0, now=start)
    assert need["status"] == "ready"
    assert need["valid"] is True
    assert need["horizon_sufficient"] is True
    assert need["required_horizon_hours"] <= 71


def _plan_input(start: datetime) -> dict:
    rows = []
    for i in range(72):
        s = start + timedelta(hours=i)
        rows.append({
            "index": i,
            "start": s.isoformat(),
            "end": (s + timedelta(hours=1)).isoformat(),
            "home_kwh": 0.4,
            "solar_kwh": 0.0,
            "import_price": 0.2,
            "export_price": 0.1,
            "fully_valid": i < 71,
        })
    return {
        "status": "degraded",
        "fully_valid_hours": 71,
        "effective_horizon_hours": 71,
        "valid_through": (start + timedelta(hours=71)).isoformat(),
        "rows_signature": "alpha31-sig",
        "rows": rows,
    }


def test_plan72_publishes_reliable_prefix_instead_of_empty_plan() -> None:
    start = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    inp = _plan_input(start)
    reserve = {
        "status": "ready", "valid": True, "input_rows_signature": "alpha31-sig",
        "soc_percent": 60.0, "reserve_soc_target_percent": 12.0,
        "grid_support_required": False,
    }
    preview = {
        "status": "degraded", "valid": True, "input_rows_signature": "alpha31-sig",
        "safety_charge_hours": [], "self_use_trade_profitable": False,
        "export_trade_profitable": False,
    }
    result = PLAN72.build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    assert result["status"] == "degraded"
    assert result["valid"] is True
    assert result["hour_count"] == 71
    assert result["simulated_hour_count"] == 71
    assert len(result["hours"]) == 71
    assert result["valid_through"] == inp["valid_through"]


def test_plan72_exposes_separate_safety_and_trade_charge_values() -> None:
    start = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    inp = _plan_input(start)
    reserve = {
        "status": "ready", "valid": True, "input_rows_signature": "alpha31-sig",
        "soc_percent": 40.0, "reserve_soc_target_percent": 12.0,
        "grid_support_required": False,
    }
    preview = {
        "status": "degraded", "valid": True, "input_rows_signature": "alpha31-sig",
        "safety_charge_hours": [{"start": inp["rows"][0]["start"], "candidate_battery_energy_kwh": 0.5}],
        "self_use_trade_profitable": False, "export_trade_profitable": False,
    }
    result = PLAN72.build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    first = result["hours"][0]
    assert first["grid_to_battery_safety_kwh"] > 0
    assert first["grid_to_battery_trade_kwh"] == 0
    assert abs(first["grid_to_battery_kwh"] - (first["grid_to_battery_safety_kwh"] + first["grid_to_battery_trade_kwh"])) < 0.002
