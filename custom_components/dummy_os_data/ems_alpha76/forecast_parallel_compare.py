from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

LEGACY_HOME_FORECAST_ENTITY = "sensor.forecast_home_consumption_data"
CONTRACT_FORECAST_ENTITY = "sensor.do_energy_forecast_planner_contract"

_INVALID_STATES = {None, "", "unknown", "unavailable", "none", "None"}
_TIME_KEYS = ("time", "timestamp", "datetime", "start")
_ENERGY_KEYS = ("predicted", "value", "consumption", "kwh")


def _first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _aware_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalize_legacy_rows(
    rows: Any,
) -> tuple[dict[datetime, float], dict[datetime, str], dict[str, int]]:
    if not isinstance(rows, list):
        return {}, {}, {
            "raw_rows": 0,
            "unique_points": 0,
            "invalid_rows": 0,
            "negative_clamped_count": 0,
        }

    per_timestamp: dict[datetime, tuple[float, str | None]] = {}
    invalid_rows = 0
    negative_clamped_count = 0
    for row in rows:
        if not isinstance(row, dict):
            invalid_rows += 1
            continue
        stamp = _aware_utc(_first(row, _TIME_KEYS))
        value = _finite(_first(row, _ENERGY_KEYS))
        if stamp is None or value is None:
            invalid_rows += 1
            continue
        if value < 0.0:
            value = 0.0
            negative_clamped_count += 1
        raw_profile = row.get("profile")
        profile = str(raw_profile).strip().lower() if raw_profile not in (None, "") else None
        per_timestamp[stamp] = (value, profile)

    grouped_energy: dict[datetime, float] = {}
    grouped_profiles: dict[datetime, list[str | None]] = {}
    for stamp, (value, profile) in per_timestamp.items():
        hour = stamp.replace(minute=0, second=0, microsecond=0)
        grouped_energy[hour] = grouped_energy.get(hour, 0.0) + value
        grouped_profiles.setdefault(hour, []).append(profile)

    hourly_profile: dict[datetime, str] = {}
    for hour, profiles in grouped_profiles.items():
        if any(profile is None for profile in profiles):
            hourly_profile[hour] = "missing"
            continue
        distinct = {str(profile) for profile in profiles}
        hourly_profile[hour] = next(iter(distinct)) if len(distinct) == 1 else "mixed"

    return grouped_energy, hourly_profile, {
        "raw_rows": len(rows),
        "unique_points": len(per_timestamp),
        "invalid_rows": invalid_rows,
        "negative_clamped_count": negative_clamped_count,
    }


def _normalize_contract_rows(rows: Any) -> dict[datetime, float]:
    result: dict[datetime, float] = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = _aware_utc(row.get("time"))
        value = _finite(row.get("home_consumption_kwh"))
        if stamp is None or value is None or value < 0.0:
            continue
        result[stamp.replace(minute=0, second=0, microsecond=0)] = value
    return result


def _window(mapping: dict[datetime, float]) -> tuple[str | None, str | None]:
    if not mapping:
        return None, None
    keys = sorted(mapping)
    return keys[0].isoformat(), keys[-1].isoformat()


def _contiguous(hours: list[datetime]) -> bool:
    return all((b - a).total_seconds() == 3600 for a, b in zip(hours, hours[1:]))


def _resolve_legacy_profile(attrs: dict[str, Any]) -> tuple[str, str | None]:
    for key in ("profile", "mode", "operating_mode"):
        value = attrs.get(key)
        if value not in (None, ""):
            return str(value).strip().lower(), key
    return "unclassified", None


def _signature(
    *,
    legacy_profile: str,
    contract_profile: str,
    legacy_window: tuple[str | None, str | None],
    contract_window: tuple[str | None, str | None],
    pairs: list[dict[str, Any]],
) -> str:
    payload = {
        "legacy_source": LEGACY_HOME_FORECAST_ENTITY,
        "contract_source": CONTRACT_FORECAST_ENTITY,
        "legacy_profile": legacy_profile,
        "contract_profile": contract_profile,
        "legacy_window": legacy_window,
        "contract_window": contract_window,
        "pairs": pairs,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_forecast_parallel_compare(
    *,
    legacy_entity_state: Any,
    legacy_attributes: dict[str, Any] | None,
    contract_shadow: dict[str, Any],
) -> dict[str, Any]:
    """Compare Package-41 and Contract-v1 forecasts on exact UTC hour starts only."""
    legacy_attrs = dict(legacy_attributes or {})
    blockers: list[str] = []
    warnings: list[str] = []

    legacy_available = legacy_entity_state not in _INVALID_STATES
    legacy_rows, legacy_hour_profiles, legacy_diag = _normalize_legacy_rows(
        legacy_attrs.get("forecasts")
    )
    contract_rows = _normalize_contract_rows(
        contract_shadow.get("forecast_contract_shadow_hours")
    )

    if not legacy_available:
        blockers.append("legacy_entity_unavailable")
    if not legacy_rows:
        blockers.append("legacy_rows_unavailable")
    if contract_shadow.get("forecast_contract_shadow_structural_ready") is not True:
        blockers.append("contract_structural_not_ready")
    if not contract_rows:
        blockers.append("contract_rows_unavailable")

    legacy_profile, legacy_profile_source = _resolve_legacy_profile(legacy_attrs)
    contract_profile = str(
        contract_shadow.get("forecast_contract_shadow_profile") or "unclassified"
    ).strip().lower()

    legacy_window = _window(legacy_rows)
    contract_window = _window(contract_rows)
    legacy_keys = set(legacy_rows)
    contract_keys = set(contract_rows)
    matched = sorted(legacy_keys & contract_keys)
    legacy_only = sorted(legacy_keys - contract_keys)
    contract_only = sorted(contract_keys - legacy_keys)
    matched_contiguous = _contiguous(matched) if matched else False

    matched_profile_counts: dict[str, int] = {}
    for stamp in matched:
        profile = legacy_hour_profiles.get(stamp, "missing")
        matched_profile_counts[profile] = matched_profile_counts.get(profile, 0) + 1
    matched_profile_normal_hours = matched_profile_counts.get("normal", 0)
    matched_profile_vacation_hours = matched_profile_counts.get("vacation", 0)
    matched_profile_missing_hours = matched_profile_counts.get("missing", 0)
    matched_profile_mixed_hours = matched_profile_counts.get("mixed", 0)
    matched_profile_other_hours = len(matched) - (
        matched_profile_normal_hours
        + matched_profile_vacation_hours
        + matched_profile_missing_hours
        + matched_profile_mixed_hours
    )
    matched_profile_explicit_hours = len(matched) - matched_profile_missing_hours

    profile_comparable = (
        bool(matched)
        and legacy_profile == "normal"
        and contract_profile == "normal"
        and matched_profile_normal_hours == len(matched)
    )
    if not profile_comparable:
        blockers.append("profile_gate_pending_step3")

    if blockers:
        status = "blocked"
    elif not matched:
        status = "no_overlap"
    elif len(matched) < 24:
        status = "limited_overlap"
    elif not matched_contiguous:
        blockers.append("matched_hours_not_contiguous")
        status = "blocked"
    elif len(matched) == 72:
        status = "ready_full"
    else:
        status = "ready_partial"

    metrics_allowed = not blockers and bool(matched)
    pairs: list[dict[str, Any]] = []
    if metrics_allowed:
        for stamp in matched:
            pairs.append(
                {
                    "time": stamp.isoformat(),
                    "legacy_kwh": round(legacy_rows[stamp], 9),
                    "contract_kwh": round(contract_rows[stamp], 9),
                }
            )

    legacy_total = sum(item["legacy_kwh"] for item in pairs) if pairs else None
    contract_total = sum(item["contract_kwh"] for item in pairs) if pairs else None
    deltas = [item["contract_kwh"] - item["legacy_kwh"] for item in pairs] if pairs else []
    abs_deltas = [abs(value) for value in deltas]

    if pairs and legacy_total is not None and contract_total is not None:
        total_delta = contract_total - legacy_total
        total_delta_percent = total_delta / legacy_total * 100.0 if legacy_total > 0.0 else None
        mean_abs = sum(abs_deltas) / len(abs_deltas)
        mean_signed = sum(deltas) / len(deltas)
        max_index = max(range(len(abs_deltas)), key=abs_deltas.__getitem__)
        max_abs = abs_deltas[max_index]
        max_at = pairs[max_index]["time"]
        comparison_signature = _signature(
            legacy_profile=legacy_profile,
            contract_profile=contract_profile,
            legacy_window=legacy_window,
            contract_window=contract_window,
            pairs=pairs,
        )
    else:
        total_delta = total_delta_percent = mean_abs = mean_signed = max_abs = max_at = comparison_signature = None

    window_start_offset_hours = None
    if legacy_window[0] and contract_window[0]:
        legacy_start = _aware_utc(legacy_window[0])
        contract_start = _aware_utc(contract_window[0])
        if legacy_start is not None and contract_start is not None:
            window_start_offset_hours = round((contract_start - legacy_start).total_seconds() / 3600.0, 6)

    coverage_denominator = min(len(legacy_rows), len(contract_rows))
    matched_coverage_percent = round(len(matched) / coverage_denominator * 100.0, 2) if coverage_denominator else 0.0

    if contract_shadow.get("forecast_contract_shadow_runtime_operational") is not True:
        warnings.append("contract_runtime_not_operational")

    return {
        "status": status,
        "legacy_source": LEGACY_HOME_FORECAST_ENTITY,
        "contract_source": CONTRACT_FORECAST_ENTITY,
        "legacy_profile": legacy_profile,
        "legacy_profile_source": legacy_profile_source,
        "contract_profile": contract_profile,
        "profile_comparable": profile_comparable,
        "matched_profile_counts": matched_profile_counts,
        "matched_profile_explicit_hours": matched_profile_explicit_hours,
        "matched_profile_normal_hours": matched_profile_normal_hours,
        "matched_profile_vacation_hours": matched_profile_vacation_hours,
        "matched_profile_missing_hours": matched_profile_missing_hours,
        "matched_profile_mixed_hours": matched_profile_mixed_hours,
        "matched_profile_other_hours": matched_profile_other_hours,
        "contract_structural_ready": contract_shadow.get("forecast_contract_shadow_structural_ready") is True,
        "contract_runtime_operational": contract_shadow.get("forecast_contract_shadow_runtime_operational") is True,
        "runtime_input_status": contract_shadow.get("forecast_contract_shadow_runtime_input_status"),
        "runtime_blockers": list(contract_shadow.get("forecast_contract_shadow_runtime_blockers") or []),
        "legacy_hour_count": len(legacy_rows),
        "contract_hour_count": len(contract_rows),
        "legacy_window_start": legacy_window[0],
        "legacy_window_end": legacy_window[1],
        "contract_window_start": contract_window[0],
        "contract_window_end": contract_window[1],
        "window_start_offset_hours": window_start_offset_hours,
        "first_matched_hour": matched[0].isoformat() if matched else None,
        "last_matched_hour": matched[-1].isoformat() if matched else None,
        "matched_hours": len(matched),
        "legacy_only_hours": len(legacy_only),
        "contract_only_hours": len(contract_only),
        "matched_coverage_percent": matched_coverage_percent,
        "matched_hours_contiguous": matched_contiguous,
        "legacy_matched_total_kwh": round(legacy_total, 6) if legacy_total is not None else None,
        "contract_matched_total_kwh": round(contract_total, 6) if contract_total is not None else None,
        "total_delta_kwh": round(total_delta, 6) if total_delta is not None else None,
        "total_delta_percent": round(total_delta_percent, 3) if total_delta_percent is not None else None,
        "mean_absolute_delta_kwh": round(mean_abs, 6) if mean_abs is not None else None,
        "mean_signed_delta_kwh": round(mean_signed, 6) if mean_signed is not None else None,
        "max_absolute_delta_kwh": round(max_abs, 6) if max_abs is not None else None,
        "max_absolute_delta_at": max_at,
        "legacy_raw_rows": legacy_diag["raw_rows"],
        "legacy_unique_points": legacy_diag["unique_points"],
        "legacy_invalid_rows": legacy_diag["invalid_rows"],
        "legacy_negative_clamped_count": legacy_diag["negative_clamped_count"],
        "comparison_signature": comparison_signature,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "shadow_only": True,
        "plan72_source": False,
        "active_use_permitted": False,
        "physical_execution_authority": False,
        "published_pairs": False,
    }
