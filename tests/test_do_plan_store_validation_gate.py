import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.dummy_os_data.do_plan_store import (
    new_store_snapshot,
    set_manual_plan,
    summarize_store,
    sync_automatic_candidates,
    validate_store_snapshot,
)
from custom_components.dummy_os_data.do_plan_store_lifecycle import transition_plan_status
from custom_components.dummy_os_data.do_plan_store_reconcile import prune_obsolete_automatic_pending

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)


def candidate(*, cid="c1", identity="id-1", signature="sig-1", start_h=2, energy=0.5):
    start = NOW + timedelta(hours=start_h)
    return {
        "candidate_id": cid,
        "planner_identity": identity,
        "planner_signature": signature,
        "action": "charge",
        "reason": "grid_support",
        "start_time": start.isoformat(),
        "planned_end_time": (start + timedelta(minutes=30)).isoformat(),
        "max_runtime_minutes": 30,
        "max_start_delay_minutes": 10,
        "power_w": 1200,
        "planned_energy_kwh": energy,
        "target_soc_percent": 70,
    }


def manual_plan():
    return {
        "action": "charge",
        "reason": "manual",
        "start_time": (NOW + timedelta(hours=3)).isoformat(),
        "max_runtime_minutes": 30,
        "power_w": 900,
        "planned_energy_kwh": 0.4,
        "target_soc_percent": 65,
    }


def test_snapshot_survives_json_roundtrip_as_restart_contract():
    store, _ = set_manual_plan(new_store_snapshot(NOW), 1, manual_plan(), NOW)
    store, _ = sync_automatic_candidates(store, [candidate()], NOW)
    restored = json.loads(json.dumps(store))
    valid, blockers = validate_store_snapshot(restored)
    assert valid is True
    assert blockers == []
    assert restored == store
    assert restored["slots"][0]["origin"] == "manual"
    assert restored["slots"][1]["origin"] == "automatic_72h_planner"


def test_manual_slot_survives_bridge_membership_refresh():
    store, _ = set_manual_plan(new_store_snapshot(NOW), 1, manual_plan(), NOW)
    store, _ = sync_automatic_candidates(store, [candidate()], NOW)
    refreshed, meta = prune_obsolete_automatic_pending(store, [], NOW + timedelta(minutes=5))
    assert meta["released_slots"] == [2]
    assert refreshed["slots"][0]["origin"] == "manual"
    assert refreshed["slots"][0]["manual_priority"] is True
    assert refreshed["slots"][0]["status"] == "pending"


def test_running_automatic_plan_is_never_pruned_by_new_bridge_membership():
    store, _ = sync_automatic_candidates(new_store_snapshot(NOW), [candidate()], NOW)
    store, result = transition_plan_status(store, 1, "running", NOW + timedelta(minutes=1))
    assert result["status"] == "running"
    refreshed, meta = prune_obsolete_automatic_pending(store, [], NOW + timedelta(minutes=2))
    assert meta["changed"] is False
    assert refreshed["slots"][0]["status"] == "running"
    assert refreshed["slots"][0]["origin"] == "automatic_72h_planner"


def test_reconciliation_keeps_plan_and_slot_identity():
    store, _ = sync_automatic_candidates(new_store_snapshot(NOW), [candidate()], NOW)
    original = dict(store["slots"][0])
    revised = candidate(cid="c2", signature="sig-2", energy=0.8)
    pruned, prune_meta = prune_obsolete_automatic_pending(store, [revised], NOW + timedelta(minutes=5))
    assert prune_meta["changed"] is False
    store2, meta = sync_automatic_candidates(pruned, [revised], NOW + timedelta(minutes=5))
    assert meta["reconciled_slots"] == [1]
    assert store2["slots"][0]["slot_id"] == original["slot_id"]
    assert store2["slots"][0]["plan_id"] == original["plan_id"]
    assert store2["slots"][0]["planner_signature"] == "sig-2"
    assert store2["slots"][0]["planned_energy_kwh"] == 0.8


def test_full_automatic_store_accepts_completely_new_set_in_same_refresh():
    old = [
        candidate(cid=f"old-{i}", identity=f"old-id-{i}", signature=f"old-sig-{i}", start_h=i + 1)
        for i in range(3)
    ]
    store, first = sync_automatic_candidates(new_store_snapshot(NOW), old, NOW)
    assert first["written_slots"] == [1, 2, 3]
    new = [
        candidate(cid=f"new-{i}", identity=f"new-id-{i}", signature=f"new-sig-{i}", start_h=i + 4)
        for i in range(3)
    ]
    pruned, prune_meta = prune_obsolete_automatic_pending(store, new, NOW + timedelta(minutes=5))
    assert prune_meta["released_slots"] == [1, 2, 3]
    refreshed, sync_meta = sync_automatic_candidates(pruned, new, NOW + timedelta(minutes=5))
    assert sync_meta["written_slots"] == [1, 2, 3]
    assert [slot["candidate_id"] for slot in refreshed["slots"]] == ["new-0", "new-1", "new-2"]


def test_corrupt_persistent_state_is_invalid_not_empty():
    corrupt = {"schema_version": 1, "updated_at": NOW.isoformat(), "slots": []}
    summary = summarize_store(corrupt, loaded=True)
    assert summary["status"] == "invalid"
    assert summary["store_valid"] is False
    assert "slot_structure_invalid" in summary["blockers"]


def test_step6_modules_contain_no_home_assistant_service_calls():
    for name in (
        "do_plan_store.py",
        "do_plan_store_bridge.py",
        "do_plan_store_lifecycle.py",
        "do_plan_store_reconcile.py",
        "do_plan_store_sensor.py",
    ):
        text = (ROOT / "custom_components/dummy_os_data" / name).read_text()
        assert ".services.async_call" not in text
        assert "hass.services" not in text


def test_step8b_active_bundle_no_longer_registers_alpha35_bridge_or_store():
    comp = ROOT / "custom_components/dummy_os_data"
    adapter = (comp / "do_plan_grid_support_sensor.py").read_text()
    surface = (comp / "ems_alpha76_surface.py").read_text()
    alpha76_store = (comp / "ems_alpha76/plan_store.py").read_text()
    assert "DummyOSPlanStoreBridgeSensor" not in adapter
    assert "build_do_plan_store_sensors" not in adapter
    assert "build_alpha76_status_sensors(coordinator)" in adapter
    assert "self.plan_store = runtime.plan_store" in surface
    assert "class AnkerEmsPlanStore" in alpha76_store
    assert "PLAN_SLOT_COUNT = 3" in (comp / "ems_alpha76/const.py").read_text()


def test_hard_safety_flags_remain_closed_in_retired_store_summary():
    summary = summarize_store(new_store_snapshot(NOW), loaded=True)
    assert summary["shadow_only"] is True
    assert summary["shadow_store_write"] is True
    assert summary["operational_plan_store_write"] is False
    assert summary["active_use_permitted"] is False
    assert summary["physical_execution_authority"] is False
    assert summary["scheduler_invoked"] is False
    assert summary["safety_chain_invoked"] is False
    assert summary["service_calls_performed"] is False
