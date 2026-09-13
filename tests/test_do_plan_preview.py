from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "custom_components/dummy_os_data/do_plan_preview.py"
SPEC = importlib.util.spec_from_file_location("do_plan_preview", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

BASE = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)


def _input(rows=None, **overrides):
    if rows is None:
        rows = []
        for idx in range(72):
            start = BASE + timedelta(hours=idx)
            solar = 0.0 if idx < 4 else (1.0 if idx < 10 else 0.0)
            rows.append(
                {
                    "index": idx,
                    "start": start.isoformat(),
                    "end": (start + timedelta(hours=1)).isoformat(),
                    "home_kwh": 0.4,
                    "solar_kwh": solar,
                    "import_price": 0.20 + idx * 0.001,
                    "export_price": 0.10 + idx * 0.001,
                    "fully_valid": True,
                }
            )
    result = {
        "status": "ready",
        "fully_valid_hours": 72,
        "rows_signature": "sig-step1",
        "rows": rows,
    }
    result.update(overrides)
    return result


def _reserve(**overrides):
    result = {
        "status": "ready",
        "valid": True,
        "reason": "reserve_deficit",
        "first_usable_solar": (BASE + timedelta(hours=4)).isoformat(),
        "battery_capacity_kwh": 7.2,
        "soc_percent": 21.0,
        "reserve_soc_target_percent": 23.569,
        "reserve_deficit_kwh": 0.185,
        "free_above_reserve_kwh": 0.0,
    }
    result.update(overrides)
    return result


def test_safety_charge_uses_step3_deficit_efficiency_and_remaining_hour() -> None:
    result = MOD.build_do_plan_preview(
        input_result=_input(),
        reserve_result=_reserve(),
        now=BASE + timedelta(minutes=30),
    )
    assert result["status"] == "ready"
    assert result["preview_decision"] == "safety_charge_preview"
    assert result["reserve_recalculated"] is False
    assert result["reserve_deficit_battery_kwh"] == 0.185
    assert result["required_grid_input_kwh"] == 0.201
    assert result["safety_schedule_sufficient"] is True
    assert result["safety_unallocated_battery_kwh"] == 0.0
    assert result["safety_charge_hour_count"] == 1
    assert result["safety_charge_hours"][0]["available_hour_fraction"] <= 1.0
    assert result["shadow_only"] is True
    assert result["active_use_permitted"] is False
    assert result["physical_execution_authority"] is False


def test_insufficient_pre_solar_window_keeps_unallocated_deficit_visible() -> None:
    result = MOD.build_do_plan_preview(
        input_result=_input(),
        reserve_result=_reserve(
            first_usable_solar=(BASE + timedelta(minutes=10)).isoformat(),
            reserve_deficit_kwh=2.0,
        ),
        now=BASE,
        max_charge_power_w=100,
    )
    assert result["preview_decision"] == "safety_charge_preview"
    assert result["safety_schedule_sufficient"] is False
    assert result["safety_unallocated_battery_kwh"] > 0


def test_missing_export_price_blocks_instead_of_falling_back() -> None:
    rows = _input()["rows"]
    rows[3] = {**rows[3], "export_price": None}
    result = MOD.build_do_plan_preview(
        input_result=_input(rows=rows),
        reserve_result=_reserve(),
        now=BASE,
    )
    assert result["status"] == "blocked"
    assert "row_3_invalid" in result["blockers"]
    assert result["prices_fallback_used"] is False
    assert result["missing_as_zero_used"] is False


def test_runtime_blocked_input_keeps_structural_shadow_preview_available() -> None:
    result = MOD.build_do_plan_preview(
        input_result=_input(status="runtime_blocked"),
        reserve_result=_reserve(),
        now=BASE,
    )
    assert result["status"] == "ready"
    assert result["valid"] is True
    assert result["physical_execution_authority"] is False


def test_reserve_deficit_always_suppresses_trade_decisions() -> None:
    rows = _input()["rows"]
    rows[0] = {**rows[0], "import_price": 0.01}
    rows[8] = {**rows[8], "import_price": 0.80, "export_price": 0.70}
    result = MOD.build_do_plan_preview(
        input_result=_input(rows=rows),
        reserve_result=_reserve(reserve_deficit_kwh=0.185),
        now=BASE,
    )
    assert result["preview_decision"] == "safety_charge_preview"
    assert result["safety_charge_needed"] is True


def test_free_above_reserve_zero_disables_discharge_preview() -> None:
    result = MOD.build_do_plan_preview(
        input_result=_input(),
        reserve_result=_reserve(
            reason="reserve_covered",
            reserve_deficit_kwh=0.0,
            free_above_reserve_kwh=0.0,
            soc_percent=30.0,
            reserve_soc_target_percent=30.0,
        ),
        now=BASE + timedelta(hours=12),
    )
    assert result["discharge_preview_allowed"] is False
    assert result["max_deliverable_from_free_kwh"] == 0.0


def test_solar_capacity_protection_suppresses_pre_solar_trade_charge() -> None:
    rows = _input()["rows"]
    rows[0] = {**rows[0], "import_price": 0.01}
    rows[8] = {**rows[8], "import_price": 0.80, "export_price": 0.70}
    result = MOD.build_do_plan_preview(
        input_result=_input(rows=rows),
        reserve_result=_reserve(
            reason="reserve_surplus",
            reserve_deficit_kwh=0.0,
            free_above_reserve_kwh=1.0,
            soc_percent=40.0,
            reserve_soc_target_percent=20.0,
        ),
        now=BASE,
    )
    assert result["solar_capacity_protection"] is True
    assert result["preview_decision"] == "wait_for_solar"


def test_self_use_and_export_pairs_use_separate_later_prices() -> None:
    rows = _input()["rows"]
    rows[0] = {**rows[0], "import_price": 0.05, "export_price": 0.01}
    rows[8] = {**rows[8], "import_price": 0.60, "export_price": 0.30}
    result = MOD.build_do_plan_preview(
        input_result=_input(rows=rows),
        reserve_result=_reserve(
            first_usable_solar=(BASE - timedelta(hours=1)).isoformat(),
            reason="reserve_surplus",
            soc_percent=40.0,
            reserve_soc_target_percent=20.0,
            reserve_deficit_kwh=0.0,
            free_above_reserve_kwh=1.0,
        ),
        now=BASE,
        minimum_trade_margin=0.10,
    )
    assert result["best_self_use_discharge_import_price"] is not None
    assert result["best_export_discharge_export_price"] is not None
    assert result["best_self_use_discharge_import_price"] != result["best_export_discharge_export_price"]
    assert result["self_use_trade_profitable"] is True
    expected = 0.60 - (0.05 / 0.8464)
    assert abs(result["best_self_use_margin"] - expected) < 1e-6


def test_real_zero_values_are_valid_but_nan_is_not() -> None:
    rows = _input()["rows"]
    rows[0] = {
        **rows[0],
        "home_kwh": 0.0,
        "solar_kwh": 0.0,
        "import_price": 0.0,
        "export_price": 0.0,
    }
    result = MOD.build_do_plan_preview(
        input_result=_input(rows=rows),
        reserve_result=_reserve(
            first_usable_solar=(BASE - timedelta(hours=1)).isoformat(),
            reserve_deficit_kwh=0.0,
            free_above_reserve_kwh=0.0,
            soc_percent=20.0,
            reserve_soc_target_percent=20.0,
        ),
        now=BASE,
    )
    assert result["status"] == "ready"
    assert result["valid"] is True

    bad_rows = _input()["rows"]
    bad_rows[0] = {**bad_rows[0], "import_price": float("nan")}
    blocked = MOD.build_do_plan_preview(
        input_result=_input(rows=bad_rows),
        reserve_result=_reserve(),
        now=BASE,
    )
    assert blocked["status"] == "blocked"
    assert "row_0_invalid" in blocked["blockers"]


def test_invalid_reserve_blocks() -> None:
    result = MOD.build_do_plan_preview(
        input_result=_input(),
        reserve_result=_reserve(status="infeasible", valid=False),
        now=BASE,
    )
    assert result["status"] == "blocked"
    assert "reserve_soc_not_ready" in result["blockers"]
