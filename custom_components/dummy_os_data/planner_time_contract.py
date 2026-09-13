"""Shared UTC time contract; retrieval times never select consumer horizons."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import math
from typing import Any, Iterable

VERSION = 1
SLOT_MINUTES = 15
SLOT_COUNT = 288
HORIZON_HOURS = 72
STEP = timedelta(minutes=15)


def utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc)


def floor_quarter(value: Any) -> datetime:
    value = utc(value)
    return value.replace(minute=value.minute // 15 * 15, second=0, microsecond=0)


def ceil_quarter(value: Any) -> datetime:
    value = utc(value)
    floor = floor_quarter(value)
    return floor if floor == value else floor + STEP


def build_time_contract(reference: datetime) -> dict[str, Any]:
    reference = utc(reference)
    start = ceil_quarter(reference)
    end = start + timedelta(hours=72)
    key = f"{VERSION}|{start.isoformat()}|{end.isoformat()}|15|288"
    return {
        "version": VERSION, "window_id": hashlib.sha256(key.encode()).hexdigest(),
        "reference_utc": reference.isoformat(), "window_start": start.isoformat(),
        "window_end": end.isoformat(), "end_exclusive": True,
        "resolution_minutes": 15, "slot_count": 288, "horizon_hours": 72,
        "alignment_policy": "ceil_utc_quarter_inclusive_exact_boundary",
        "bridge_seconds": (start-reference).total_seconds(),
        "dashboard_resolution_minutes": 60,
    }


def validate_time_contract(contract: Any) -> list[str]:
    if not isinstance(contract, dict):
        return ["time_contract_missing"]
    try:
        expected = build_time_contract(utc(contract.get("reference_utc")))
    except (ValueError, TypeError, OverflowError):
        return ["time_contract_timestamp_invalid"]
    return [f"time_contract_{key}_invalid" for key, value in expected.items() if contract.get(key) != value]


def expected_starts(contract: dict[str, Any]) -> tuple[datetime, ...]:
    errors = validate_time_contract(contract)
    if errors:
        raise ValueError(",".join(errors))
    start = utc(contract["window_start"])
    return tuple(start + i*STEP for i in range(288))


def time_fields(contract: dict[str, Any]) -> dict[str, Any]:
    return {"time_contract": dict(contract), "window_id": contract["window_id"],
            "window_start": contract["window_start"], "window_end": contract["window_end"],
            "calculation_reference_utc": contract["reference_utc"], "time_contract_version": VERSION}


def window_errors(*results: dict[str, Any]) -> list[str]:
    contracts = [r.get("time_contract") if isinstance(r, dict) else None for r in results]
    if not any(c is not None for c in contracts):
        return []
    errors = [e for c in contracts for e in validate_time_contract(c)]
    if len({c.get("window_id") for c in contracts if isinstance(c, dict)}) != 1:
        errors.append("time_window_mismatch")
    return sorted(set(errors))


def propagate_time(result: dict[str, Any], *sources: dict[str, Any]) -> dict[str, Any]:
    contract = next((s.get("time_contract") for s in sources if isinstance(s, dict) and isinstance(s.get("time_contract"), dict)), None)
    if contract is None:
        return result
    errors = window_errors(*sources)
    result.update(time_fields(contract))
    result["time_alignment_valid"] = not errors
    if errors:
        result.update(status="blocked", valid=False, reason=errors[0],
                      blockers=sorted(set([*(result.get("blockers") or []), *errors])))
    return result


def get(point: Any, key: str) -> Any:
    return point.get(key) if isinstance(point, dict) else getattr(point, key, None)


def point_start(point: Any) -> datetime:
    return utc(get(point, "start") or get(point, "time"))


def select_points(points: Iterable[Any], contract: dict[str, Any], *, neighbours: bool = False) -> list[Any]:
    starts = expected_starts(contract)
    allowed = set(starts)
    if neighbours:
        allowed.update((starts[0]-STEP, starts[-1]+STEP))
    selected = []
    for point in points:
        try:
            start = point_start(point)
        except (ValueError, TypeError, OverflowError):
            continue
        if start in allowed:
            selected.append(point)
    return sorted(selected, key=point_start)


def finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None
