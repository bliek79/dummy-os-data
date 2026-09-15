"""Regression contract for the G5 frozen-live A/B parity gate."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from custom_components.dummy_os_data import ems_g5_live_parity as parity
from custom_components.dummy_os_data.planner_time_contract import build_time_contract

BASE = datetime(2026, 9, 15, 9, 30, tzinfo=timezone.utc)


def _snapshot() -> dict:
    time_contract = build_time_contract(BASE)
    window_start = datetime.fromisoformat(time_contract["window_start"])
    rows = []
    slots = []
    for hour in range(72):
        start = window_start + timedelta(hours=hour)
        solar = 0.9 if 5 <= hour <= 9 else 0.0
        import_price = 0.08 if hour == 2 else 0.22
        export_price = 0.38 if hour == 18 else 0.10
        price_quarters = []
        for quarter in range(4):
            q_start = start + timedelta(minutes=15 * quarter)
            q_end = q_start + timedelta(minutes=15)
            price_quarters.append(
                {"start": q_start.isoformat(), "kind": "known_pt15m"}
            )
            slots.append(
                {
                    "index": hour * 4 + quarter,
                    "start": q_start.isoformat(),
                    "end": q_end.isoformat(),
                    "home_kwh": 0.105,
                    "solar_kwh": solar / 4.0,
                    "import_price": import_price,
                    "export_price": export_price,
                    "valid": True,
                }
            )
        rows.append(
            {
                "start": start.isoformat(),
                "end": (start + timedelta(hours=1)).isoformat(),
                "home_kwh": 0.42,
                "solar_kwh": solar,
                "import_price": import_price,
                "export_price": export_price,
                "price_source": "known",
                "price_quarters": price_quarters,
                "fully_valid": True,
            }
        )
    input_result = {
        # Deliberately no top-level `valid`: the production input contract does
        # not expose it. Alpha40 incorrectly required it.
        "status": "ready",
        "blockers": [],
        "runtime_blockers": [],
        "rows": rows,
        "slots": slots,
        "rows_signature": "g5-production-live-fixture",
        "time_contract": time_contract,
        "planner_resolution_minutes": 15,
        "transport_resolution_minutes": 60,
        "native_expected_slot_count": 288,
        "native_valid_slot_count": 288,
        "time_alignment_valid": True,
    }
    return {
        "schema_version": 1,
        "captured_at": time_contract["window_start"],
        "input_result": input_result,
        "input_rows_signature": input_result["rows_signature"],
        "time_contract": deepcopy(input_result["time_contract"]),
        "measured_soc_percent": 17.0,
        "planner_start_soc_percent": 17.0,
        "soc_bridge": {"valid": True, "planner_start_soc_percent": 17.0},
        "profile": "normal",
        "config": {
            "battery_capacity_kwh": 7.2,
            "min_soc_percent": 5.0,
            "software_reserve_percent": 7.0,
            "execution_buffer_percent": 2.0,
            "max_charge_power_w": 3200,
            "max_discharge_power_w": 3200,
            "charge_efficiency_percent": 92.0,
            "discharge_efficiency_percent": 92.0,
            "minimum_trade_margin": 0.10,
            "electrical_profile": "dedicated_group",
        },
        "shadow_only": True,
        "physical_execution_authority": False,
    }


def test_same_frozen_production_input_is_exact_alpha76_match():
    snapshot = _snapshot()
    assert "valid" not in snapshot["input_result"]
    result = parity.compare_frozen_live_snapshot(snapshot)
    assert result["status"] == "pass"
    assert result["exact_match"] is True
    assert result["difference_count"] == 0
    assert result["differences"] == []
    assert result["shadow_only"] is True
    assert result["physical_execution_authority"] is False
    assert result["service_calls_performed"] is False
    assert result["plan_store_mutated"] is False
    assert result["golden_decision"] == result["copy_decision"]


def test_snapshot_fingerprint_is_deterministic_and_content_sensitive():
    first = _snapshot()
    second = deepcopy(first)
    assert parity.snapshot_fingerprint(first) == parity.snapshot_fingerprint(second)
    second["input_result"]["rows"][0]["home_kwh"] = 0.43
    assert parity.snapshot_fingerprint(first) != parity.snapshot_fingerprint(second)


def test_missing_or_incomplete_input_blocks_without_running_decision_paths():
    snapshot = _snapshot()
    snapshot["input_result"]["rows"] = snapshot["input_result"]["rows"][:-1]
    result = parity.compare_frozen_live_snapshot(snapshot)
    assert result["status"] == "blocked"
    assert result["exact_match"] is False
    assert "input_not_72_transport_rows" in result["blockers"]
    assert result["service_calls_performed"] is False
    assert result["plan_store_mutated"] is False


def test_invalid_native_slot_blocks():
    snapshot = _snapshot()
    snapshot["input_result"]["slots"][25]["valid"] = False
    snapshot["input_result"]["native_valid_slot_count"] = 287
    result = parity.compare_frozen_live_snapshot(snapshot)
    assert result["status"] == "blocked"
    assert "input_native_slots_not_fully_valid" in result["blockers"]
    assert "input_native_valid_slot_count_not_288" in result["blockers"]


def test_runtime_blocker_blocks():
    snapshot = _snapshot()
    snapshot["input_result"]["runtime_blockers"] = ["prices_freshness_stale"]
    result = parity.compare_frozen_live_snapshot(snapshot)
    assert result["status"] == "blocked"
    assert "input_runtime_blocker:prices_freshness_stale" in result["blockers"]


def test_mismatch_is_reported_with_compact_difference_paths(monkeypatch):
    snapshot = _snapshot()
    original = parity._copy_chain

    def altered_copy(input_result, planner_soc_percent, config):
        need, preview, plan72 = original(input_result, planner_soc_percent, config)
        changed = deepcopy(plan72)
        changed["auto_plan_72h_reason"] = "forced_g5_test_difference"
        return need, preview, changed

    monkeypatch.setattr(parity, "_copy_chain", altered_copy)
    result = parity.compare_frozen_live_snapshot(snapshot)
    assert result["status"] == "mismatch"
    assert result["exact_match"] is False
    assert result["difference_count"] >= 1
    assert any("auto_plan_72h_reason" in item for item in result["differences"])
