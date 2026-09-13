"""Planner Step 1 tests for the observer-only DO Plan 72h input matrix."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "custom_components/dummy_os_data/do_plan_input.py"
SPEC = importlib.util.spec_from_file_location("do_plan_input", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
build_do_plan_input_72h = MODULE.build_do_plan_input_72h


@dataclass
class SolarPoint:
    start: datetime
    total_kwh: float


@dataclass
class PricePoint:
    start: datetime
    import_all_in: float
    export_all_in: float
    kind: str = "known_pt15m"
    source_resolution_minutes: int = 15


def _contract(start: datetime) -> dict:
    hours = []
    for index in range(72):
        hour_start = start + timedelta(hours=index)
        hours.append(
            {
                "index": index,
                "start": hour_start.isoformat(),
                "end": (hour_start + timedelta(hours=1)).isoformat(),
                "quarter_count": 4,
                "populated_quarters": 4,
                "energy_kwh": round(0.4 + index / 1000.0, 6),
            }
        )
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
        quarter = start + timedelta(minutes=15 * index)
        solar.append(SolarPoint(quarter, 0.0 if index == 0 else 0.05))
        prices.append(PricePoint(quarter, 0.20 + index / 100000.0, 0.10 + index / 100000.0))
    return solar, prices


def test_exact_72_hours_are_joined_on_exact_quarter_timestamps() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    solar, prices = _points(start)
    result = build_do_plan_input_72h(
        contract=_contract(start),
        solar_points=solar,
        price_points=prices,
        solar_status="ok",
        prices_status="ok",
        prices_freshness="fresh",
    )
    assert result["status"] == "ready"
    assert result["hour_count"] == 72
    assert result["fully_valid_hours"] == 72
    assert result["effective_horizon_hours"] == 72
    assert result["rows"][0]["solar_kwh"] == 0.15
    assert result["rows"][0]["solar_quarters"][0]["kwh"] == 0.0
    assert result["rows"][0]["price_valid"] is True
    assert result["rows_signature"]
    assert result["shadow_only"] is True
    assert result["active_use_permitted"] is False
    assert result["physical_execution_authority"] is False


def test_missing_solar_quarter_stays_missing_and_degrades_locally() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    solar, prices = _points(start)
    missing_start = start + timedelta(minutes=30)
    solar = [point for point in solar if point.start != missing_start]
    result = build_do_plan_input_72h(
        contract=_contract(start),
        solar_points=solar,
        price_points=prices,
        solar_status="ok",
        prices_status="ok",
        prices_freshness="fresh",
    )
    assert result["status"] == "degraded"
    assert result["valid_solar_hours"] == 71
    assert result["fully_valid_hours"] == 71
    assert result["effective_horizon_hours"] == 0
    assert result["first_invalid_index"] == 0
    assert result["rows"][0]["solar_valid"] is False
    assert result["rows"][0]["solar_kwh"] is None
    assert result["rows"][0]["solar_quarters"][2]["kwh"] is None


def test_single_nan_price_is_recovered_only_by_explicit_neighbor_interpolation() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    solar, prices = _points(start)
    expected = (prices[4].import_all_in + prices[6].import_all_in) / 2.0
    prices[5].import_all_in = float("nan")
    result = build_do_plan_input_72h(
        contract=_contract(start),
        solar_points=solar,
        price_points=prices,
        solar_status="ok",
        prices_status="ok",
        prices_freshness="fresh",
    )
    quarter = result["rows"][1]["price_quarters"][1]
    assert result["status"] == "ready"
    assert result["valid_price_hours"] == 72
    assert result["rows"][1]["price_valid"] is True
    assert result["interpolated_price_slots"] == 1
    assert quarter["kind"] == "interpolated"
    assert quarter["fallback_method"] == "neighbor_average"
    assert abs(quarter["import_price"] - expected) < 1e-12


def test_structural_data_can_be_runtime_blocked_without_becoming_invalid() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    solar, prices = _points(start)
    contract = _contract(start)
    contract["runtime_input_status"] = "source_unavailable"
    contract["forecast_operational_input_ok"] = False
    contract["runtime_blockers"] = ["source_unavailable"]
    result = build_do_plan_input_72h(
        contract=contract,
        solar_points=solar,
        price_points=prices,
        solar_status="ok",
        prices_status="ok",
        prices_freshness="fresh",
    )
    assert result["status"] == "runtime_blocked"
    assert result["fully_valid_hours"] == 72
    assert "source_unavailable" in result["runtime_blockers"]
    assert "forecast_runtime_not_operational" in result["runtime_blockers"]


def test_naive_timestamp_blocks_contract_instead_of_guessing_timezone() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    solar, prices = _points(start)
    contract = _contract(start)
    contract["hours"][0]["start"] = "2026-09-09T00:00:00"
    result = build_do_plan_input_72h(
        contract=contract,
        solar_points=solar,
        price_points=prices,
        solar_status="ok",
        prices_status="ok",
        prices_freshness="fresh",
    )
    assert result["status"] == "blocked"
    assert "hour_0_timestamp_invalid" in result["blockers"]
    assert result["rows"] == []
