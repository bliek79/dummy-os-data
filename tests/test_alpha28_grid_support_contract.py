from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

GRID = load("do_plan_grid_support_alpha28", "custom_components/dummy_os_data/do_plan_grid_support.py")
PLAN = load("do_plan_72h_alpha28", "custom_components/dummy_os_data/do_plan_72h.py")
BASE = datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)


def make_input(*, status: str = "runtime_blocked", home_quarter: float = 0.08) -> dict:
    rows = []
    for h in range(72):
        hs = BASE + timedelta(hours=h)
        home_quarters = []
        solar_quarters = []
        price_quarters = []
        for q in range(4):
            start = hs + timedelta(minutes=15 * q)
            end = start + timedelta(minutes=15)
            home_quarters.append({"start": start.isoformat(), "end": end.isoformat(), "kwh": home_quarter})
            solar_quarters.append({"start": start.isoformat(), "kwh": 0.0})
            price_quarters.append({"start": start.isoformat(), "import_price": 0.10 + 0.001 * h, "export_price": 0.05, "kind": "known_pt15m", "source_resolution_minutes": 15})
        rows.append({
            "index": h,
            "start": hs.isoformat(),
            "end": (hs + timedelta(hours=1)).isoformat(),
            "home_kwh": home_quarter * 4,
            "solar_kwh": 0.0,
            "import_price": 0.10 + 0.001 * h,
            "export_price": 0.05,
            "fully_valid": True,
            "home_quarters_valid": True,
            "home_quarters": home_quarters,
            "solar_quarters": solar_quarters,
            "price_quarters": price_quarters,
        })
    return {"status": status, "fully_valid_hours": 72, "rows_signature": "sig28", "rows": rows}


def reserve(deficit: float = 10.002, soc: float = 98.0) -> dict:
    return {
        "status": "ready",
        "valid": True,
        "input_rows_signature": "sig28",
        "grid_support_required": True,
        "grid_support_deficit_kwh": deficit,
        "reserve_deficit_kwh": deficit,
        "soc_percent": soc,
        "reserve_soc_target_percent": 100.0,
        "first_usable_solar": (BASE + timedelta(hours=18)).isoformat(),
    }


def test_runtime_blocked_but_complete_input_is_structurally_usable_for_grid_support() -> None:
    out = GRID.build_do_plan_grid_support(input_result=make_input(), reserve_result=reserve(), energy_need_result={"status": "blocked", "valid": False})
    assert out["handoff_source"] == "reserve_soc_grid_support_handoff"
    assert "planner_input_not_structurally_ready" not in out.get("blockers", [])
    assert out["required_grid_charge_input_kwh"] == 10.872
    assert out["grid_support_deficit_battery_kwh"] == 10.002


def test_grid_support_only_becomes_infeasible_after_charge_window_allocation() -> None:
    out = GRID.build_do_plan_grid_support(input_result=make_input(), reserve_result=reserve(), energy_need_result=None)
    assert out["status"] in {"ready", "infeasible"}
    if out["status"] == "infeasible":
        assert out["blockers"] == ["safe_charge_window_capacity_insufficient"]
        assert out["eligible_charge_slot_count"] > 0
        assert out["selected_charge_slot_count"] > 0


def test_plan72_treats_100_percent_reserve_as_target_during_grid_support() -> None:
    inp = make_input(status="ready", home_quarter=0.02)
    res = reserve(deficit=1.0, soc=80.0)
    preview = {
        "status": "ready",
        "valid": True,
        "input_rows_signature": "sig28",
        "safety_charge_hours": [],
        "self_use_trade_profitable": False,
        "export_trade_profitable": False,
    }
    grid = {
        "status": "ready",
        "valid": True,
        "input_rows_signature": "sig28",
        "selected_charge_slots": [],
    }
    out = PLAN.build_do_plan_72h(input_result=inp, reserve_result=res, preview_result=preview, grid_support_result=grid)
    assert out["simulation_reserve_floor_soc_percent"] == 12.0
    assert out["reserve_target_soc_percent"] == 100.0
    # Alpha34 keeps the pre-solar advice source visible, but only the replayed
    # native safety plan is authoritative; no max() merge of two schedules.
    assert out["upstream_safety_source"] == "grid_support_selected_slots"
    assert out["safety_charge_source"] == "native_sequential_deadline_plan"
    assert out["safety_plan_authority"] == "plan72_native"
    assert out["hour_count"] == 72
