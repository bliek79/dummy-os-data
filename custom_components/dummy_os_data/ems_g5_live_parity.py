"""Pure G5 frozen-live parity comparison for Dummy OS Energy.

G5 is an acceptance diagnostic only. A single already-materialized live
Dummy OS Data input is deep-copied into two paths:

* ``golden`` calls the immutable/vendored EMS alpha76 decision core directly;
* ``copy`` calls the Dummy OS Data -> alpha76 adapter used by the new runtime.

Both paths receive the same reference time, SOC and configuration. This
module never touches Home Assistant state, the Plan Store, Scheduler, Safety,
Execution Controller or services and therefore has no physical authority.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from typing import Any

from .ems_alpha76.energy_need import build_energy_need_analysis
from .ems_alpha76.planner_72h import build_72h_plan_preview
from .ems_alpha76.planner_preview import build_planner_preview
from .ems_alpha76_adapter import (
    forecast_from_input,
    planner_reference,
    run_energy_need,
    run_plan72,
    run_preview,
)
from .planner_time_contract import validate_time_contract

MAX_REPORTED_DIFFERENCES = 40
EXPECTED_TRANSPORT_ROWS = 72
EXPECTED_NATIVE_SLOTS = 288
EXPECTED_NATIVE_RESOLUTION_MINUTES = 15
EXPECTED_TRANSPORT_RESOLUTION_MINUTES = 60


def _jsonable(value: Any) -> Any:
    """Return a deterministic JSON-compatible representation."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    """Hash the full frozen evidence payload with stable ordering."""
    raw = json.dumps(
        _jsonable(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _differences(
    left: Any,
    right: Any,
    path: str = "$",
    *,
    limit: int = MAX_REPORTED_DIFFERENCES,
) -> list[str]:
    """Return compact structural difference paths, capped for HA attributes."""
    found: list[str] = []

    def walk(a: Any, b: Any, current: str) -> None:
        if len(found) >= limit:
            return
        if type(a) is not type(b):
            found.append(
                f"{current}: type {type(a).__name__} != {type(b).__name__}"
            )
            return
        if isinstance(a, dict):
            keys = sorted(set(a) | set(b), key=str)
            for key in keys:
                if len(found) >= limit:
                    return
                child = f"{current}.{key}"
                if key not in a:
                    found.append(f"{child}: missing in golden")
                elif key not in b:
                    found.append(f"{child}: missing in copy")
                else:
                    walk(a[key], b[key], child)
            return
        if isinstance(a, (list, tuple)):
            if len(a) != len(b):
                found.append(f"{current}: length {len(a)} != {len(b)}")
            for index, (item_a, item_b) in enumerate(zip(a, b, strict=False)):
                if len(found) >= limit:
                    return
                walk(item_a, item_b, f"{current}[{index}]")
            return
        if a != b:
            found.append(f"{current}: {a!r} != {b!r}")

    walk(left, right, path)
    return found


def _input_contract_blockers(input_result: Any) -> list[str]:
    """Validate the real production Dummy OS Data planner-input contract.

    Alpha40 incorrectly required a top-level ``valid=True`` marker. The live
    planner contract does not publish that marker. Its acceptance state is
    represented by ``status``, exact 72 transport rows / 288 native slots,
    per-row/per-slot validity, time alignment and explicit blocker lists.
    """
    if not isinstance(input_result, dict):
        return ["input_missing"]

    blockers: list[str] = []
    status = str(input_result.get("status") or "missing")
    if status != "ready":
        blockers.append(f"input_status_{status}")

    rows = input_result.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_TRANSPORT_ROWS:
        blockers.append("input_not_72_transport_rows")
    elif any(
        not isinstance(row, dict) or row.get("fully_valid") is not True
        for row in rows
    ):
        blockers.append("input_transport_rows_not_fully_valid")

    slots = input_result.get("slots")
    if not isinstance(slots, list) or len(slots) != EXPECTED_NATIVE_SLOTS:
        blockers.append("input_not_288_native_slots")
    elif any(
        not isinstance(slot, dict) or slot.get("valid") is not True
        for slot in slots
    ):
        blockers.append("input_native_slots_not_fully_valid")

    if input_result.get("native_expected_slot_count") != EXPECTED_NATIVE_SLOTS:
        blockers.append("input_native_expected_slot_count_not_288")
    if input_result.get("native_valid_slot_count") != EXPECTED_NATIVE_SLOTS:
        blockers.append("input_native_valid_slot_count_not_288")
    if input_result.get("planner_resolution_minutes") != EXPECTED_NATIVE_RESOLUTION_MINUTES:
        blockers.append("input_native_resolution_not_15")
    if input_result.get("transport_resolution_minutes") != EXPECTED_TRANSPORT_RESOLUTION_MINUTES:
        blockers.append("input_transport_resolution_not_60")
    if input_result.get("time_alignment_valid") is not True:
        blockers.append("input_time_alignment_invalid")

    for error in validate_time_contract(input_result.get("time_contract")):
        blockers.append(f"input_{error}")

    for source_blocker in input_result.get("blockers") or []:
        blockers.append(f"input_blocker:{source_blocker}")
    for runtime_blocker in input_result.get("runtime_blockers") or []:
        blockers.append(f"input_runtime_blocker:{runtime_blocker}")

    return sorted(set(blockers))


def _decision_summary(
    chain: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> dict[str, Any]:
    """Keep the dashboard/Recorder surface compact while preserving decisions."""
    need, preview, plan72 = chain
    plan = plan72.get("auto_plan_72h_plan") or []
    action_counts: dict[str, int] = {}
    first_action: dict[str, Any] | None = None
    for row in plan:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
        if first_action is None and action not in {
            "geen_actie",
            "unknown",
            "none",
            "None",
        }:
            first_action = {
                "time": row.get("time"),
                "action": row.get("action"),
                "charge_from_grid_kwh": row.get("charge_from_grid_kwh"),
                "charge_from_grid_safety_kwh": row.get(
                    "charge_from_grid_safety_kwh"
                ),
                "charge_from_grid_trade_kwh": row.get(
                    "charge_from_grid_trade_kwh"
                ),
                "discharge_to_grid_kwh": row.get("discharge_to_grid_kwh"),
                "discharge_to_home_kwh": row.get("discharge_to_home_kwh"),
                "soc_start": row.get("soc_start"),
                "soc_end": row.get("soc_end"),
                "reason": row.get("reason"),
            }
    return {
        "energy_need_valid": need.get("energy_need_valid"),
        "energy_need_reason": need.get("energy_need_reason"),
        "additional_grid_charge_kwh": need.get(
            "energy_need_additional_grid_charge_kwh"
        ),
        "first_usable_solar": need.get("energy_need_first_usable_solar"),
        "preview_status": preview.get("planner_preview_status"),
        "preview_decision": preview.get("planner_preview_decision"),
        "preview_reason": preview.get("planner_preview_reason"),
        "safety_charge_needed": preview.get("planner_preview_safety_charge_needed"),
        "plan72_valid": plan72.get("auto_plan_72h_valid"),
        "plan72_reason": plan72.get("auto_plan_72h_reason"),
        "plan72_start_soc": plan72.get("auto_plan_72h_start_soc"),
        "plan72_end_soc": plan72.get("auto_plan_72h_end_soc"),
        "plan72_hour_count": len(plan),
        "action_counts": action_counts,
        "first_action": first_action,
    }


def _golden_chain(
    input_result: dict[str, Any],
    planner_soc_percent: float,
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Run the vendored immutable alpha76 core directly."""
    forecast = forecast_from_input(deepcopy(input_result))
    reference = planner_reference(input_result)
    need = build_energy_need_analysis(
        forecast,
        planner_soc_percent,
        float(config["software_reserve_percent"]),
        now=reference,
    )
    preview = build_planner_preview(
        forecast,
        need,
        planner_soc_percent,
        float(config["charge_efficiency_percent"]),
        float(config["discharge_efficiency_percent"]),
        float(config["minimum_trade_margin"]),
        max_charge_power_w=int(config["max_charge_power_w"]),
        now=reference,
    )
    plan72 = build_72h_plan_preview(
        forecast,
        need,
        preview,
        planner_soc_percent,
        float(config["charge_efficiency_percent"]),
        float(config["discharge_efficiency_percent"]),
        execution_buffer_percent=float(config["execution_buffer_percent"]),
        max_charge_power_w=int(config["max_charge_power_w"]),
        max_discharge_power_w=int(config["max_discharge_power_w"]),
        now=reference,
    )
    return need, preview, plan72


def _copy_chain(
    input_result: dict[str, Any],
    planner_soc_percent: float,
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Run the new Dummy OS Data adapter over the same frozen input."""
    reference = planner_reference(input_result)
    need = run_energy_need(
        input_result=deepcopy(input_result),
        soc_percent=planner_soc_percent,
        safety_reserve_percent=float(config["software_reserve_percent"]),
        now=reference,
    )
    preview = run_preview(
        input_result=deepcopy(input_result),
        energy_need=need,
        soc_percent=planner_soc_percent,
        charge_efficiency_percent=float(config["charge_efficiency_percent"]),
        discharge_efficiency_percent=float(config["discharge_efficiency_percent"]),
        minimum_trade_margin=float(config["minimum_trade_margin"]),
        max_charge_power_w=int(config["max_charge_power_w"]),
        now=reference,
    )
    plan72 = run_plan72(
        input_result=deepcopy(input_result),
        energy_need=need,
        planner_preview=preview,
        soc_percent=planner_soc_percent,
        charge_efficiency_percent=float(config["charge_efficiency_percent"]),
        discharge_efficiency_percent=float(config["discharge_efficiency_percent"]),
        execution_buffer_percent=float(config["execution_buffer_percent"]),
        max_charge_power_w=int(config["max_charge_power_w"]),
        max_discharge_power_w=int(config["max_discharge_power_w"]),
        now=reference,
    )
    return need, preview, plan72


def compare_frozen_live_snapshot(
    frozen_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate G5 using one immutable real-live snapshot.

    The full raw outputs remain in the returned evidence payload for persistent
    Store use. The HA sensor only publishes the compact summary.
    """
    input_result = deepcopy(frozen_snapshot.get("input_result"))
    config = deepcopy(frozen_snapshot.get("config"))
    planner_soc = frozen_snapshot.get("planner_start_soc_percent")
    blockers = _input_contract_blockers(input_result)

    try:
        planner_soc_value = float(planner_soc)
    except (TypeError, ValueError):
        planner_soc_value = None
        blockers.append("planner_soc_missing")
    if planner_soc_value is not None and not 0.0 <= planner_soc_value <= 100.0:
        blockers.append("planner_soc_invalid")

    required_config = {
        "battery_capacity_kwh",
        "min_soc_percent",
        "software_reserve_percent",
        "execution_buffer_percent",
        "max_charge_power_w",
        "max_discharge_power_w",
        "charge_efficiency_percent",
        "discharge_efficiency_percent",
        "minimum_trade_margin",
    }
    if not isinstance(config, dict):
        blockers.append("config_missing")
        config = {}
    else:
        missing = sorted(required_config - set(config))
        blockers.extend(f"config_missing:{key}" for key in missing)

    fingerprint = snapshot_fingerprint(frozen_snapshot)
    blockers = sorted(set(blockers))
    if blockers:
        return {
            "status": "blocked",
            "exact_match": False,
            "snapshot_fingerprint": fingerprint,
            "blockers": blockers,
            "difference_count": 0,
            "differences": [],
            "shadow_only": True,
            "physical_execution_authority": False,
            "service_calls_performed": False,
            "plan_store_mutated": False,
        }

    assert isinstance(input_result, dict)
    assert planner_soc_value is not None
    golden = _golden_chain(input_result, planner_soc_value, config)
    copy = _copy_chain(input_result, planner_soc_value, config)
    differences = _differences(golden, copy)
    exact = golden == copy
    return {
        "status": "pass" if exact else "mismatch",
        "exact_match": exact,
        "snapshot_fingerprint": fingerprint,
        "blockers": [],
        "difference_count": 0 if exact else len(differences),
        "differences": differences,
        "differences_capped_at": MAX_REPORTED_DIFFERENCES,
        "golden_source": "Dummy OS EMS 0.0.1-alpha.76 immutable vendored core",
        "copy_path": "Dummy OS Data frozen input -> alpha76 adapter -> alpha76 core",
        "golden_decision": _decision_summary(golden),
        "copy_decision": _decision_summary(copy),
        "golden_raw": {
            "energy_need": golden[0],
            "preview": golden[1],
            "plan72": golden[2],
        },
        "copy_raw": {
            "energy_need": copy[0],
            "preview": copy[1],
            "plan72": copy[2],
        },
        "shadow_only": True,
        "physical_execution_authority": False,
        "service_calls_performed": False,
        "plan_store_mutated": False,
    }
