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
# Compatibility diagnostic: the old EMS requires two consecutive usable hours.
# Alpha33 evaluates those two hours from native quarter data as two hour-aligned
# four-quarter windows, instead of incorrectly requiring every quarter itself
# to satisfy solar >= home.
USABLE_SOLAR_CONSECUTIVE_SLOTS = 8
USABLE_SOLAR_WINDOW_SLOTS = 4
USABLE_SOLAR_CONSECUTIVE_WINDOWS = 2
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


def _is_usable_solar_window(slots: list[dict[str, Any]], start_index: int) -> bool:
    """Old-EMS usable-hour semantics, evaluated from four native quarters."""
    end_index = start_index + USABLE_SOLAR_WINDOW_SLOTS
    if start_index < 0 or end_index > len(slots):
        return False
    window = slots[start_index:end_index]
    solar = sum(slot["solar_kwh"] for slot in window)
    home = sum(slot["home_kwh"] for slot in window)
    return solar > 0.0 and solar + 1e-12 >= home


def _find_next_usable_solar(slots: list[dict[str, Any]], index: int) -> int | None:
    """Return first hour-aligned quarter starting two consecutive usable hours.

    The calculation may be requested at any native quarter, but the old EMS
    classified complete hourly forecast rows. Therefore candidate solar blocks
    are aligned to the next full hour boundary, while the deficit before that
    boundary remains calculated from the exact native quarter index.
    """
    required_slots = USABLE_SOLAR_WINDOW_SLOTS * USABLE_SOLAR_CONSECUTIVE_WINDOWS
    last_candidate = len(slots) - required_slots
    first_candidate = max(0, index)
    for candidate in range(first_candidate, last_candidate + 1):
        candidate_start = _utc(slots[candidate]["start"])
        if candidate_start is None or candidate_start.minute != 0:
            continue
        if _is_usable_solar_window(slots, candidate) and _is_usable_solar_window(
            slots, candidate + USABLE_SOLAR_WINDOW_SLOTS
        ):
            return candidate
    return None


def _dynamic_reserve_profile(slots: list[dict[str, Any]], discharge_eff: float) -> list[dict[str, Any]]:
    """Build old-EMS dynamic reserve semantics from native quarter data."""
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
            usable_index = _find_next_usable_solar(slots, index)
            if usable_index is None:
                floor = base_floor
                need = 0.0
                first_usable = None
            else:
                need = sum(
                    max(0.0, slots[j]["home_kwh"] - slots[j]["solar_kwh"])
                    for j in range(index, usable_index)
                )
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
    """Compatibility entrypoint; production uses schedule AND carry commitments."""
    from .do_plan_native_safety import build_native_safety_plan
    return build_native_safety_plan(
        slots=slots, reserve_profile=reserve_profile, start_soc=start_soc,
        charge_eff=charge_eff, discharge_eff=DISCHARGE_EFFICIENCY_PERCENT / 100.0,
    )["schedule"]


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
    valid_slots = [
        slot
        for slot in slots
        if not slot.get("price_fallback_used")
        and str(slot.get("price_kind") or "").lower() != "interpolated"
    ]
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
