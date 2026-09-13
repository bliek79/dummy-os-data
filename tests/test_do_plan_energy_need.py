from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "custom_components/dummy_os_data/do_plan_energy_need.py"
SPEC = importlib.util.spec_from_file_location("do_plan_energy_need", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def _input(*, start: datetime, usable_at: int = 8, home: float = 0.5, solar_before: float = 0.0) -> dict:
    rows = []
    for index in range(72):
        solar = 0.7 if usable_at <= index <= usable_at + 1 else solar_before
        rows.append(
            {
                "index": index,
                "start": (start + timedelta(hours=index)).isoformat(),
                "end": (start + timedelta(hours=index + 1)).isoformat(),
                "home_kwh": home,
                "solar_kwh": solar,
                "fully_valid": True,
            }
        )
    return {
        "status": "ready",
        "fully_valid_hours": 72,
        "rows_signature": "abc123",
        "rows": rows,
    }


def test_energy_need_matches_reference_intent() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    result = MOD.build_do_plan_energy_need(
        input_result=_input(start=start, usable_at=4, home=0.5),
        soc_percent=50.0,
        now=start,
    )
    assert result["status"] == "ready"
    assert result["valid"] is True
    assert result["energy_need_until_solar_kwh"] == 2.0
    assert result["first_usable_solar"] == (start + timedelta(hours=4)).isoformat()
    assert result["available_battery_kwh"] == 3.24
    assert result["safety_reserve_kwh"] == 0.504
    assert result["required_including_reserve_kwh"] == 2.504
    assert result["additional_grid_charge_kwh"] == 0.0
    assert result["tradable_battery_kwh"] == 0.736
    assert result["input_rows_signature"] == "abc123"
    assert result["shadow_only"] is True
    assert result["active_use_permitted"] is False
    assert result["physical_execution_authority"] is False


def test_real_zero_is_valid_not_missing() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    inp = _input(start=start, usable_at=2, home=0.0)
    inp["rows"][2]["home_kwh"] = 0.1
    inp["rows"][3]["home_kwh"] = 0.1
    result = MOD.build_do_plan_energy_need(input_result=inp, soc_percent=20.0, now=start)
    assert result["status"] == "ready"
    assert result["energy_need_until_solar_kwh"] == 0.0


def test_missing_relevant_input_blocks_instead_of_zero_fallback() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    inp = _input(start=start, usable_at=4)
    inp["rows"][1]["solar_kwh"] = None
    inp["fully_valid_hours"] = 71
    result = MOD.build_do_plan_energy_need(input_result=inp, soc_percent=50.0, now=start)
    assert result["status"] == "blocked"
    assert "row_1_solar_missing" in result["blockers"]
    assert result["energy_need_until_solar_kwh"] is None


def test_missing_soc_blocks() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    result = MOD.build_do_plan_energy_need(input_result=_input(start=start), soc_percent=None, now=start)
    assert result["status"] == "blocked"
    assert "soc_unavailable" in result["blockers"]


def test_no_usable_solar_does_not_assume_end_of_horizon() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    inp = _input(start=start, usable_at=80, home=0.5)
    result = MOD.build_do_plan_energy_need(input_result=inp, soc_percent=50.0, now=start)
    assert result["status"] == "waiting_for_usable_solar"
    assert result["valid"] is False
    assert result["energy_need_until_solar_kwh"] is None


def test_current_hour_is_fractional_when_present() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    inp = _input(start=start, usable_at=2, home=1.0)
    inp["rows"][2]["solar_kwh"] = 1.2
    inp["rows"][3]["solar_kwh"] = 1.2
    result = MOD.build_do_plan_energy_need(
        input_result=inp,
        soc_percent=50.0,
        now=start + timedelta(minutes=30),
    )
    assert result["energy_need_until_solar_kwh"] == 1.5
    assert result["contributing_hours"] == 1.5
