"""One replay-validated native safety plan for the entire available horizon.

The old EMS reserve profile and deadline meaning are preserved. Unlike the old
optimistic pre-estimator, every allocation is tested against the sequential SOC
path after earlier home consumption, solar, capacity limits and safety purchases.
This is a deterministic safety-first heuristic, not a global cost optimizer.
"""
from __future__ import annotations
from typing import Any

from .do_plan_native_common import MAX_CHARGE_POWER_W, SLOTS_PER_HOUR
from .do_plan_native_simulation import _simulate

TOL_KWH = 1e-6


def build_native_safety_plan(*, slots: list[dict[str, Any]], reserve_profile: list[dict[str, Any]],
                             start_soc: float, charge_eff: float, discharge_eff: float) -> dict[str, Any]:
    """Allocate only useful accepted energy at or before each reserve deadline.

    Safety commitments protect precharged energy from discretionary home/export
    discharge until their deadline. They do not modify the dynamic reserve. Each
    trial uses the SAME simulation as Plan72. Upstream Grid Support and Preview
    remain advice and are never merged into a second independent schedule.
    """
    plan: dict[str, float] = {}
    commitments: list[dict[str, Any]] = []
    replay_count = 0
    # Backward reachability prevents spending existing energy when there is too
    # little charging time left to restore it before a sharp reserve increase.
    precharge_floors = [row["execution_floor_kwh"] for row in reserve_profile]
    max_stored_per_slot = MAX_CHARGE_POWER_W / 1000.0 / SLOTS_PER_HOUR * charge_eff
    for index in range(len(slots) - 1, -1, -1):
        precharge_floors[index] = max(precharge_floors[index], precharge_floors[index+1] - max_stored_per_slot)

    def replay(length: int | None = None) -> dict[str, Any]:
        nonlocal replay_count
        replay_count += 1
        end = len(slots) if length is None else length
        return _simulate(slots=slots[:end], start_soc=start_soc,
                         reserve_profile=reserve_profile[:end+1], safety_slots=plan,
                         safety_commitments=commitments, precharge_floors=precharge_floors[:end+1], trade=None,
                         charge_eff=charge_eff, discharge_eff=discharge_eff)

    result = replay()
    for deadline in range(len(slots)):
        target = reserve_profile[deadline + 1]["execution_floor_kwh"]
        if result["slots"][deadline]["end_stored_kwh"] + TOL_KWH >= target:
            continue
        # Only headroom that exists on the current actual SOC path is eligible.
        # Price then timestamp retains the old EMS cheapest-before-deadline rule.
        candidates = sorted(range(deadline + 1), key=lambda i: (slots[i]["import_price"], slots[i]["start"]))
        changed = False
        for index in candidates:
            current = result["slots"][deadline]["end_stored_kwh"]
            deficit = target - current
            if deficit <= TOL_KWH:
                break
            available = result["slots"][index]["remaining_safety_charge_stored_kwh"]
            if available <= TOL_KWH:
                continue
            key = slots[index]["start"]
            previous = plan.get(key, 0.0)
            add = min(deficit, available)
            lot = {"start": key, "deadline_index": deadline,
                   "deadline": slots[deadline]["end"], "stored_battery_kwh": add}
            plan[key] = previous + add
            commitments.append(lot)
            trial = replay(deadline + 1)
            achieved = trial["slots"][deadline]["end_stored_kwh"]
            # Reject energy lost to a later full battery or another capacity pinch.
            if achieved <= current + TOL_KWH:
                commitments.pop()
                if previous > 0.0:
                    plan[key] = previous
                else:
                    plan.pop(key, None)
                continue
            result = trial
            changed = True
        # Rebuild the whole path only after useful allocations. Impossible early
        # deadlines stay visible; later reliable slots are not erased.
        if changed:
            result = replay()

    # Normalize the published schedule to ACCEPTED energy, not requested capacity.
    # Replaying this normalization must preserve the exact same storage path.
    actual_by_start = {s["start"]: s["accepted_safety_stored_kwh"] for s in result["slots"]}
    for lot in commitments:
        requested = plan[lot["start"]]
        ratio = min(1.0, actual_by_start[lot["start"]] / requested) if requested else 0.0
        lot["stored_battery_kwh"] *= ratio
    plan = {key: min(value, actual_by_start[key]) for key, value in plan.items() if actual_by_start[key] > TOL_KWH}
    result = replay()
    summary = summarize_native_safety_plan(result, reserve_profile, commitments)
    return {"precharge_floors": precharge_floors, "schedule": plan,
            "commitments": commitments, "simulation": result,
            "replay_count": replay_count,
            "requested_stored_kwh": round(sum(plan.values()), 6), **summary}


def summarize_native_safety_plan(simulation: dict[str, Any],
                                 reserve_profile: list[dict[str, Any]],
                                 commitments: list[dict[str, Any]]) -> dict[str, Any]:
    """Report accepted energy and breaches of the actually published replay."""
    selected = []
    breaches = []
    for index, item in enumerate(simulation["slots"]):
        accepted_input = item["grid_to_battery_safety_kwh"]
        if accepted_input > TOL_KWH:
            deadlines = [lot["deadline"] for lot in commitments if lot["start"] == item["start"]]
            selected.append({"start": item["start"], "end": item["end"],
                             "allocated_charge_input_kwh": accepted_input,
                             "stored_battery_kwh": round(item["accepted_safety_stored_kwh"], 6),
                             "import_price_all_in": item["import_price"],
                             "projected_soc_after_percent": item["end_soc_percent"],
                             "deadlines": sorted(set(deadlines)),
                             "kind": item.get("price_kind"),
                             "price_interpolated": item.get("price_kind") == "interpolated"})
        shortfall = reserve_profile[index + 1]["execution_floor_kwh"] - item["end_stored_kwh"]
        if shortfall > TOL_KWH:
            breaches.append({"index": index, "start": item["start"], "end": item["end"],
                             "required_soc_percent": item["execution_reserve_end_soc_percent"],
                             "projected_soc_percent": item["end_soc_percent"],
                             "shortfall_battery_kwh": round(shortfall, 6)})
    return {"selected_charge_slots": selected, "breaches": breaches,
            "fully_allocated": not breaches,
            "accepted_stored_kwh": round(sum(x["stored_battery_kwh"] for x in selected), 6),
            "accepted_grid_input_kwh": round(sum(x["allocated_charge_input_kwh"] for x in selected), 6)}
