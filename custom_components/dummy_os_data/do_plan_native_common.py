"""Observer-only native 15-minute / 72-hour sequential planner simulation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

HOURS = 72
SLOTS_PER_HOUR = 4
SLOT_MINUTES = 15
SLOTS = HOURS * SLOTS_PER_HOUR
CAPACITY_KWH = 7.2
MIN_SOC_PERCENT = 5.0
SAFETY_RESERVE_PERCENT = 7.0
EXECUTION_BUFFER_PERCENT = 2.0
CHARGE_EFFICIENCY_PERCENT = 92.0
DISCHARGE_EFFICIENCY_PERCENT = 92.0
MAX_CHARGE_POWER_W = 3200
MAX_DISCHARGE_POWER_W = 3200
DEFAULT_MINIMUM_TRADE_MARGIN = 0.10
USABLE_SOLAR_CONSECUTIVE_SLOTS = 8
EPS = 0.01


def _finite(value: Any, *, non_negative: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if non_negative and number < 0:
        return None
    return number


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _blocked(base: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    return {
        **base,
        "status": "blocked",
        "valid": False,
        "reason": blockers[0],
        "blockers": sorted(set(blockers)),
        "slot_count": 0,
        "simulated_slot_count": 0,
        "hour_count": 0,
        "simulated_hour_count": 0,
        "slots": [],
        "hours": [],
        "baseline": None,
        "candidate": None,
    }


def _hour_quarters(row: dict[str, Any], key: str) -> list[dict[str, Any]] | None:
    value = row.get(key)
    if isinstance(value, list) and len(value) == SLOTS_PER_HOUR:
        return value
    return None


def _expand_native_slots(raw_rows: list[dict[str, Any]], effective_horizon_hours: int) -> tuple[list[dict[str, Any]], list[str], str]:
    """Expand hourly compatibility rows into the authoritative native quarter sequence.

    Production DO Plan Input contains exact quarter arrays. The even-split path is
    retained only as a compatibility bridge for older/unit-test callers and is
    explicitly reported via quarter_source.
    """
    slots: list[dict[str, Any]] = []
    blockers: list[str] = []
    source_mode = "native_quarters"
    previous_end: datetime | None = None

    for hour_index, raw in enumerate(raw_rows[:effective_horizon_hours]):
        if not isinstance(raw, dict) or raw.get("fully_valid") is not True:
            blockers.append(f"row_{hour_index}_not_fully_valid_inside_effective_horizon")
            continue
        hour_start = _utc(raw.get("start"))
        hour_end = _utc(raw.get("end"))
        if hour_start is None or hour_end is None or hour_end - hour_start != timedelta(hours=1):
            blockers.append(f"row_{hour_index}_timestamp_invalid")
            continue
        if previous_end is not None and hour_start != previous_end:
            blockers.append(f"row_{hour_index}_not_contiguous")
        previous_end = hour_end

        home_quarters = _hour_quarters(raw, "home_quarters")
        solar_quarters = _hour_quarters(raw, "solar_quarters")
        price_quarters = _hour_quarters(raw, "price_quarters")
        use_native = home_quarters is not None and solar_quarters is not None and price_quarters is not None

        if not use_native:
            source_mode = "compat_hour_split"
            home_hour = _finite(raw.get("home_kwh"), non_negative=True)
            solar_hour = _finite(raw.get("solar_kwh"), non_negative=True)
            imp_hour = _finite(raw.get("import_price"))
            exp_hour = _finite(raw.get("export_price"))
            if None in (home_hour, solar_hour, imp_hour, exp_hour):
                blockers.append(f"row_{hour_index}_quarter_inputs_missing")
                continue

        for quarter_index in range(SLOTS_PER_HOUR):
            start = hour_start + timedelta(minutes=SLOT_MINUTES * quarter_index)
            end = start + timedelta(minutes=SLOT_MINUTES)
            if use_native:
                hq = home_quarters[quarter_index]
                sq = solar_quarters[quarter_index]
                pq = price_quarters[quarter_index]
                home_start = _utc(hq.get("start")) if isinstance(hq, dict) else None
                home_end = _utc(hq.get("end")) if isinstance(hq, dict) else None
                solar_start = _utc(sq.get("start")) if isinstance(sq, dict) else None
                price_start = _utc(pq.get("start")) if isinstance(pq, dict) else None
                home = _finite(hq.get("kwh"), non_negative=True) if isinstance(hq, dict) else None
                solar = _finite(sq.get("kwh"), non_negative=True) if isinstance(sq, dict) else None
                imp = _finite(pq.get("import_price")) if isinstance(pq, dict) else None
                exp = _finite(pq.get("export_price")) if isinstance(pq, dict) else None
                if home_start != start or home_end != end or solar_start != start or price_start != start or None in (home, solar, imp, exp):
                    blockers.append(f"slot_{hour_index * 4 + quarter_index}_invalid")
                    continue
                kind = pq.get("kind")
                fallback_used = bool(pq.get("fallback_used"))
                source_resolution_minutes = pq.get("source_resolution_minutes")
            else:
                assert home_hour is not None and solar_hour is not None and imp_hour is not None and exp_hour is not None
                home = home_hour / SLOTS_PER_HOUR
                solar = solar_hour / SLOTS_PER_HOUR
                imp = imp_hour
                exp = exp_hour
                kind = "compat_hourly"
                fallback_used = False
                source_resolution_minutes = 60

            slots.append(
                {
                    "index": len(slots),
                    "hour_index": hour_index,
                    "quarter_index": quarter_index,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "home_kwh": float(home),
                    "solar_kwh": float(solar),
                    "import_price": float(imp),
                    "export_price": float(exp),
                    "price_kind": kind,
                    "price_fallback_used": fallback_used,
                    "price_source_resolution_minutes": source_resolution_minutes,
                }
            )

    return slots, sorted(set(blockers)), source_mode


def _is_usable_solar(slots: list[dict[str, Any]], index: int) -> bool:
    if index < 0 or index >= len(slots):
        return False
    slot = slots[index]
    return slot["solar_kwh"] > 0 and slot["solar_kwh"] >= slot["home_kwh"]


def _dynamic_reserve_profile(slots: list[dict[str, Any]], discharge_eff: float) -> list[dict[str, Any]]:
    """Build old-EMS-equivalent reserve semantics on native quarter slots."""
    minimum_stored = CAPACITY_KWH * MIN_SOC_PERCENT / 100.0
    base_floor = CAPACITY_KWH * (MIN_SOC_PERCENT + SAFETY_RESERVE_PERCENT) / 100.0
    base_floor = min(CAPACITY_KWH, max(minimum_stored, base_floor))
    buffer_kwh = CAPACITY_KWH * EXECUTION_BUFFER_PERCENT / 100.0
    profile: list[dict[str, Any]] = []

    for index in range(len(slots) + 1):
        if index >= len(slots):
            floor = base_floor
            need = 0.0
            first_usable = None
        else:
            usable_index: int | None = None
            last_candidate = len(slots) - USABLE_SOLAR_CONSECUTIVE_SLOTS
            for candidate in range(index, last_candidate + 1):
                if all(_is_usable_solar(slots, candidate + offset) for offset in range(USABLE_SOLAR_CONSECUTIVE_SLOTS)):
                    usable_index = candidate
                    break
            if usable_index is None:
                floor = base_floor
                need = 0.0
                first_usable = None
            else:
                need = sum(max(0.0, slots[j]["home_kwh"] - slots[j]["solar_kwh"]) for j in range(index, usable_index))
                stored_need = need / discharge_eff
                floor = min(CAPACITY_KWH, max(minimum_stored, base_floor + stored_need))
                first_usable = slots[usable_index]["start"]
        execution_floor = min(CAPACITY_KWH, floor + buffer_kwh)
        profile.append(
            {
                "dynamic_floor_kwh": floor,
                "execution_floor_kwh": execution_floor,
                "need_until_solar_kwh": need,
                "next_usable_solar": first_usable,
                "solar_horizon_complete": first_usable is not None,
            }
        )
    return profile


def _dynamic_safety_schedule(slots: list[dict[str, Any]], reserve_profile: list[dict[str, Any]], start_soc: float, charge_eff: float) -> dict[str, float]:
    """Pre-plan safety energy before each future execution-reserve peak."""
    planned: dict[str, float] = {}
    if not slots:
        return planned

    base_floor = CAPACITY_KWH * (MIN_SOC_PERCENT + SAFETY_RESERVE_PERCENT) / 100.0
    requirements: list[tuple[int, float, str | None]] = []
    for idx in range(len(slots)):
        end_req = reserve_profile[idx + 1]
        requirements.append((idx, end_req["execution_floor_kwh"], end_req["next_usable_solar"]))

    peaks: list[tuple[int, float]] = []
    for idx, floor_kwh, next_solar in requirements:
        if next_solar is None:
            continue
        prev_floor = requirements[idx - 1][1] if idx > 0 else base_floor
        next_floor = requirements[idx + 1][1] if idx + 1 < len(requirements) else base_floor
        if floor_kwh > prev_floor + EPS and floor_kwh >= next_floor - EPS:
            peaks.append((idx, floor_kwh))

    slot_input_limit = MAX_CHARGE_POWER_W / 1000.0 / SLOTS_PER_HOUR
    for deadline_idx, required_floor in peaks:
        estimated = CAPACITY_KWH * start_soc / 100.0
        for sim_idx in range(deadline_idx + 1):
            slot = slots[sim_idx]
            solar_surplus = max(0.0, slot["solar_kwh"] - slot["home_kwh"])
            solar_input = min(solar_surplus, slot_input_limit)
            estimated = min(CAPACITY_KWH, estimated + solar_input * charge_eff)
            estimated = min(CAPACITY_KWH, estimated + planned.get(slot["start"], 0.0))
        deficit_stored = max(0.0, required_floor - estimated)
        if deficit_stored <= EPS:
            continue

        candidates: list[tuple[float, datetime, int, float]] = []
        for cand_idx in range(deadline_idx + 1):
            slot = slots[cand_idx]
            price = slot["import_price"]
            start = _utc(slot["start"])
            assert start is not None
            solar_surplus = max(0.0, slot["solar_kwh"] - slot["home_kwh"])
            charge_headroom_input = max(0.0, slot_input_limit - min(slot_input_limit, solar_surplus))
            existing_stored = planned.get(slot["start"], 0.0)
            max_stored = max(0.0, charge_headroom_input * charge_eff - existing_stored)
            if max_stored > EPS:
                candidates.append((price, start, cand_idx, max_stored))
        candidates.sort(key=lambda item: (item[0], item[1]))
        for _price, _start, cand_idx, max_stored in candidates:
            if deficit_stored <= EPS:
                break
            key = slots[cand_idx]["start"]
            add = min(deficit_stored, max_stored)
            planned[key] = planned.get(key, 0.0) + add
            deficit_stored -= add
    return planned


def _external_safety_schedule(slots: list[dict[str, Any]], preview_result: dict[str, Any], grid_support_result: dict[str, Any] | None) -> tuple[dict[str, float], str]:
    by_start = {slot["start"]: slot for slot in slots}
    safety: dict[str, float] = {}
    if grid_support_result is not None and grid_support_result.get("status") in {"ready", "degraded"} and grid_support_result.get("valid") is True:
        for item in grid_support_result.get("selected_charge_slots") or []:
            if not isinstance(item, dict):
                continue
            start = item.get("start")
            stored = _finite(item.get("stored_battery_kwh"), non_negative=True)
            if isinstance(start, str) and start in by_start and stored is not None:
                safety[start] = safety.get(start, 0.0) + stored
        return safety, "grid_support_selected_slots"

    slot_max_stored = MAX_CHARGE_POWER_W / 1000.0 / SLOTS_PER_HOUR * (CHARGE_EFFICIENCY_PERCENT / 100.0)
    for item in preview_result.get("safety_charge_hours") or []:
        if not isinstance(item, dict):
            continue
        hour_start = _utc(item.get("start"))
        energy = _finite(item.get("candidate_battery_energy_kwh"), non_negative=True)
        if hour_start is None or energy is None:
            continue
        remaining = energy
        for q in range(SLOTS_PER_HOUR):
            key = (hour_start + timedelta(minutes=q * SLOT_MINUTES)).isoformat()
            if key not in by_start or remaining <= EPS:
                continue
            add = min(remaining, slot_max_stored)
            safety[key] = safety.get(key, 0.0) + add
            remaining -= add
    return safety, "preview_hour_distributed_to_native_slots"


def _select_native_trade(slots: list[dict[str, Any]], preview_result: dict[str, Any], charge_eff: float, discharge_eff: float) -> dict[str, Any] | None:
    min_margin = _finite(preview_result.get("minimum_trade_margin"), non_negative=True)
    if min_margin is None:
        min_margin = DEFAULT_MINIMUM_TRADE_MARGIN
    valid_slots = [slot for slot in slots if not slot.get("price_fallback_used") and str(slot.get("price_kind") or "").lower() != "interpolated"]
    best: dict[str, Any] | None = None
    roundtrip = charge_eff * discharge_eff
    for i, charge in enumerate(valid_slots):
        effective_cost = charge["import_price"] / roundtrip
        for discharge in valid_slots[i + 1 :]:
            pairs = (
                ("self_use", discharge["import_price"] - effective_cost, discharge["import_price"]),
                ("export", discharge["export_price"] - effective_cost, discharge["export_price"]),
            )
            for kind, margin, discharge_price in pairs:
                if margin < min_margin:
                    continue
                if best is None or margin > best["margin"]:
                    best = {
                        "kind": kind,
                        "margin": margin,
                        "charge_time": charge["start"],
                        "charge_price": charge["import_price"],
                        "discharge_time": discharge["start"],
                        "discharge_price": discharge_price,
                        "effective_charge_cost": effective_cost,
                        "minimum_trade_margin": min_margin,
                    }
    return best


def _future_solar_charge_potential(slots: list[dict[str, Any]], from_index: int, until_index: int, charge_eff: float) -> float:
    slot_input_limit = MAX_CHARGE_POWER_W / 1000.0 / SLOTS_PER_HOUR
    stored = 0.0
    for future in slots[from_index + 1 : until_index + 1]:
        surplus = max(0.0, future["solar_kwh"] - future["home_kwh"])
        stored += min(surplus, slot_input_limit) * charge_eff
    return stored
