"""Observer-only Step 7 Energy Time Windows calibration."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from json import dumps
from math import ceil, floor
from typing import Any

SCHEMA_VERSION = "7b.1"
ALGORITHM_VERSION = "time_windows_observer_v1"
CLASSIFICATION_SOURCE = "shifting_structural_grill"
PEAK_SOURCE_ENTITY = "sensor.do_energy_peak_learning"
NATIVE_RESOLUTION_MINUTES = 15
CALIBRATION_METHOD = "daily_representative_p10_start_p90_end"
MINIMUM_EVENT_DAYS_COLLECTING_EXIT = 8
MINIMUM_EVENT_DAYS_CALIBRATED = 12
MINIMUM_EVENT_DAYS_STABLE = 16
MAXIMUM_BOUNDARY_SHIFT_MINUTES = 15
PROTECTED_START_MINUTE = 17 * 60
PROTECTED_END_MINUTE = 18 * 60
VALID_PROFILES = {"normal", "away"}


def _parse_aware(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _median(values: list[float]) -> float | None:
    return _quantile(values, 0.5)


def _minute_of_day(value: datetime) -> int:
    return value.hour * 60 + value.minute


def _aligned_floor(value: float) -> int:
    return int(floor(value / NATIVE_RESOLUTION_MINUTES) * NATIVE_RESOLUTION_MINUTES)


def _aligned_ceil(value: float) -> int:
    return int(ceil(value / NATIVE_RESOLUTION_MINUTES) * NATIVE_RESOLUTION_MINUTES)


def _format_wall_minute(value: int) -> str:
    minute = value % (24 * 60)
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _overlaps_protected(start_minute: float, end_minute: float) -> bool:
    intervals = [(start_minute, end_minute)]
    if end_minute > 24 * 60:
        intervals.append((start_minute - 24 * 60, end_minute - 24 * 60))
    return any(start < PROTECTED_END_MINUTE and end > PROTECTED_START_MINUTE for start, end in intervals)


def _candidate(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(observations) < MINIMUM_EVENT_DAYS_COLLECTING_EXIT:
        return None
    p10_start = _quantile([float(item["earliest_start_minute"]) for item in observations], 0.10)
    p90_end = _quantile([float(item["latest_end_minute"]) for item in observations], 0.90)
    if p10_start is None or p90_end is None:
        return None
    aligned_start = _aligned_floor(p10_start)
    aligned_end = _aligned_ceil(p90_end)
    if aligned_end <= aligned_start:
        return None
    protected = _overlaps_protected(aligned_start, aligned_end)
    return {
        "p10_start_minute": p10_start,
        "p90_end_minute": p90_end,
        "window_start_minute": aligned_start,
        "window_end_minute": aligned_end,
        "protected_window_overlap": protected,
    }


def _empty_diagnostics() -> dict[str, Any]:
    return {
        "window_start": None,
        "window_end": None,
        "window_width_minutes": None,
        "window_quarter_count": None,
        "p10_start_minute": None,
        "p90_end_minute": None,
        "median_center_minute": None,
        "center_mad_minutes": None,
        "contained_day_count": None,
        "contained_day_ratio": None,
        "median_event_duration_minutes": None,
        "median_daily_energy_kwh": None,
        "energy_iqr_kwh": None,
        "lodo_max_start_shift_minutes": None,
        "lodo_max_end_shift_minutes": None,
        "early_late_start_shift_minutes": None,
        "early_late_end_shift_minutes": None,
    }


def _fingerprint(profile: str, event_days: list[str], source_fingerprints: list[str]) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "profile": profile,
        "context_key": f"{profile}|{CLASSIFICATION_SOURCE}",
        "classification_source": CLASSIFICATION_SOURCE,
        "event_day_identifiers": sorted(event_days),
        "peak_learning_calibration_fingerprints": sorted(set(source_fingerprints)),
        "native_resolution_minutes": NATIVE_RESOLUTION_MINUTES,
        "calibration_method": CALIBRATION_METHOD,
        "minimum_event_days_collecting_exit": MINIMUM_EVENT_DAYS_COLLECTING_EXIT,
        "minimum_event_days_calibrated": MINIMUM_EVENT_DAYS_CALIBRATED,
        "minimum_event_days_stable": MINIMUM_EVENT_DAYS_STABLE,
        "maximum_boundary_shift_minutes": MAXIMUM_BOUNDARY_SHIFT_MINUTES,
    }
    digest = sha256(dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    return f"tw_{digest}"


def calculate_time_windows(peak_result: dict[str, Any], profile: str, localize) -> dict[str, Any]:
    """Return deterministic observer-only Step 7 Time Windows diagnostics."""
    context_key = f"{profile}|{CLASSIFICATION_SOURCE}"
    reject_reasons: dict[str, int] = {}
    blockers: set[str] = set()

    def reject(reason: str) -> None:
        reject_reasons[reason] = reject_reasons.get(reason, 0) + 1

    if profile not in VALID_PROFILES:
        blockers.add("invalid_profile")
    if not isinstance(peak_result, dict) or peak_result.get("schema_version") != 1 or peak_result.get("algorithm_version") != "peak_observer_v1":
        blockers.add("invalid_schema")
    if isinstance(peak_result, dict) and peak_result.get("profile") != profile:
        blockers.add("invalid_profile")

    peak_source_basis = peak_result.get("source_basis") if isinstance(peak_result, dict) else None
    if not isinstance(peak_source_basis, dict):
        blockers.add("missing_source_basis")
    peak_fingerprint = peak_result.get("calibration_fingerprint") if isinstance(peak_result, dict) else None
    if not isinstance(peak_fingerprint, str) or not peak_fingerprint:
        blockers.add("source_fingerprint_missing")
        source_fingerprints: list[str] = []
    else:
        source_fingerprints = [peak_fingerprint]

    source_basis = {
        "peak_learning_entity": PEAK_SOURCE_ENTITY,
        "peak_learning_calibration_fingerprints": sorted(set(source_fingerprints)),
    }

    classifications = peak_result.get("classifications", {}) if isinstance(peak_result, dict) else {}
    events = peak_result.get("events", []) if isinstance(peak_result, dict) else []
    if not isinstance(classifications, dict) or not isinstance(events, list):
        blockers.add("invalid_schema")
        classifications = {}
        events = []

    valid_events: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            reject("invalid_time_contract")
            continue
        start = _parse_aware(event.get("start"))
        end = _parse_aware(event.get("end"))
        peak_quarter = _parse_aware(event.get("peak_quarter_start"))
        if start is None or end is None or peak_quarter is None or end <= start:
            reject("invalid_time_contract")
            continue

        local_start = localize(start)
        local_end = localize(end)
        local_peak = localize(peak_quarter)
        if local_start.tzinfo is None or local_end.tzinfo is None or local_peak.tzinfo is None:
            reject("invalid_time_contract")
            continue
        if local_start.utcoffset() != local_end.utcoffset():
            reject("dst_transition_overlap")
            continue
        if any(value.second != 0 or value.microsecond != 0 or value.minute % NATIVE_RESOLUTION_MINUTES != 0 for value in (local_start, local_end, local_peak)):
            reject("invalid_time_contract")
            continue

        try:
            duration = int(event["duration_minutes"])
            quarter_count = int(event["quarter_count"])
            extra_energy = float(event["extra_energy_kwh"])
            center = float(event["center_minute_of_day"])
        except (KeyError, TypeError, ValueError):
            reject("invalid_time_contract")
            continue
        if duration <= 0 or duration % NATIVE_RESOLUTION_MINUTES != 0 or quarter_count <= 0 or quarter_count * NATIVE_RESOLUTION_MINUTES != duration or extra_energy <= 0:
            reject("invalid_time_contract")
            continue

        local_date = local_start.date().isoformat()
        if event.get("local_date") != local_date:
            reject("invalid_time_contract")
            continue
        hour_key = f"hour_{local_start.hour:02d}"
        classification = classifications.get(hour_key, {}).get("classification") if isinstance(classifications.get(hour_key), dict) else None
        if classification != CLASSIFICATION_SOURCE:
            reject("classification_not_eligible")
            continue

        start_minute = _minute_of_day(local_start)
        end_minute = _minute_of_day(local_end)
        if local_end.date() > local_start.date() or end_minute <= start_minute:
            end_minute += 24 * 60
        protected = _overlaps_protected(start_minute, end_minute)
        valid_events.append({
            "local_date": local_date,
            "start_minute": float(start_minute),
            "end_minute": float(end_minute),
            "center_minute": center,
            "duration_minutes": float(duration),
            "extra_energy_kwh": extra_energy,
            "protected_window_overlap": protected,
        })

    by_day: dict[str, list[dict[str, Any]]] = {}
    for event in valid_events:
        by_day.setdefault(event["local_date"], []).append(event)

    observations: list[dict[str, Any]] = []
    for local_date in sorted(by_day):
        day_events = by_day[local_date]
        total_energy = sum(item["extra_energy_kwh"] for item in day_events)
        center = None
        if total_energy > 0:
            center = sum(item["center_minute"] * item["extra_energy_kwh"] for item in day_events) / total_energy
        observations.append({
            "local_date": local_date,
            "earliest_start_minute": min(item["start_minute"] for item in day_events),
            "latest_end_minute": max(item["end_minute"] for item in day_events),
            "daily_center_minute": center,
            "daily_energy_kwh": total_energy,
            "protected_window_overlap": any(item["protected_window_overlap"] for item in day_events),
        })

    event_count = len(valid_events)
    event_days = len(observations)
    rejected_event_count = sum(reject_reasons.values())
    protected_window_overlap = any(item["protected_window_overlap"] for item in observations)
    diagnostics = _empty_diagnostics()
    candidate = _candidate(observations)

    contract_blocked = bool(blockers)
    if not contract_blocked and rejected_event_count > 0 and event_count == 0 and any(reason in reject_reasons for reason in ("invalid_time_contract", "dst_transition_overlap")):
        blockers.add("invalid_time_contract")
        contract_blocked = True

    lodo_stable = False
    early_late_stable = False
    if candidate is not None:
        centers = [float(item["daily_center_minute"]) for item in observations if item["daily_center_minute"] is not None]
        median_center = _median(centers)
        center_mad = _median([abs(value - median_center) for value in centers]) if median_center is not None else None
        daily_energies = [float(item["daily_energy_kwh"]) for item in observations]
        durations = [float(item["duration_minutes"]) for item in valid_events]
        p25_energy = _quantile(daily_energies, 0.25)
        p75_energy = _quantile(daily_energies, 0.75)
        aligned_start = int(candidate["window_start_minute"])
        aligned_end = int(candidate["window_end_minute"])
        contained = sum(1 for item in observations if item["earliest_start_minute"] >= aligned_start and item["latest_end_minute"] <= aligned_end)
        diagnostics.update({
            "window_start": _format_wall_minute(aligned_start),
            "window_end": _format_wall_minute(aligned_end),
            "window_width_minutes": aligned_end - aligned_start,
            "window_quarter_count": (aligned_end - aligned_start) // NATIVE_RESOLUTION_MINUTES,
            "p10_start_minute": round(float(candidate["p10_start_minute"]), 1),
            "p90_end_minute": round(float(candidate["p90_end_minute"]), 1),
            "median_center_minute": round(float(median_center), 1) if median_center is not None else None,
            "center_mad_minutes": round(float(center_mad), 1) if center_mad is not None else None,
            "contained_day_count": contained,
            "contained_day_ratio": round(contained / event_days, 4) if event_days else None,
            "median_event_duration_minutes": round(float(_median(durations)), 1) if durations else None,
            "median_daily_energy_kwh": round(float(_median(daily_energies)), 6) if daily_energies else None,
            "energy_iqr_kwh": round(float(p75_energy - p25_energy), 6) if p25_energy is not None and p75_energy is not None else None,
        })
        protected_window_overlap = bool(protected_window_overlap or candidate["protected_window_overlap"])

        if event_days >= MINIMUM_EVENT_DAYS_CALIBRATED:
            start_shifts: list[float] = []
            end_shifts: list[float] = []
            for index in range(event_days):
                subset = observations[:index] + observations[index + 1 :]
                sub_candidate = _candidate(subset)
                if sub_candidate is None:
                    continue
                start_shifts.append(abs(float(sub_candidate["window_start_minute"]) - aligned_start))
                end_shifts.append(abs(float(sub_candidate["window_end_minute"]) - aligned_end))
            if start_shifts and end_shifts:
                diagnostics["lodo_max_start_shift_minutes"] = round(max(start_shifts), 1)
                diagnostics["lodo_max_end_shift_minutes"] = round(max(end_shifts), 1)
                lodo_stable = max(start_shifts) <= MAXIMUM_BOUNDARY_SHIFT_MINUTES and max(end_shifts) <= MAXIMUM_BOUNDARY_SHIFT_MINUTES

        if event_days >= MINIMUM_EVENT_DAYS_STABLE:
            early_candidate = _candidate(observations[:8])
            late_candidate = _candidate(observations[-8:])
            if early_candidate is not None and late_candidate is not None:
                early_late_start = abs(float(early_candidate["window_start_minute"]) - float(late_candidate["window_start_minute"]))
                early_late_end = abs(float(early_candidate["window_end_minute"]) - float(late_candidate["window_end_minute"]))
                diagnostics["early_late_start_shift_minutes"] = round(early_late_start, 1)
                diagnostics["early_late_end_shift_minutes"] = round(early_late_end, 1)
                early_late_stable = (
                    early_late_start <= MAXIMUM_BOUNDARY_SHIFT_MINUTES
                    and early_late_end <= MAXIMUM_BOUNDARY_SHIFT_MINUTES
                    and bool(early_candidate["protected_window_overlap"]) == bool(late_candidate["protected_window_overlap"])
                )

    if contract_blocked:
        status = "blocked"
        diagnostics = _empty_diagnostics()
        ready_for_live_observation = False
    elif event_days < MINIMUM_EVENT_DAYS_COLLECTING_EXIT:
        status = "collecting"
        blockers.add("insufficient_event_days")
        diagnostics = _empty_diagnostics()
        ready_for_live_observation = False
    elif event_days < MINIMUM_EVENT_DAYS_CALIBRATED:
        status = "calibrating"
        blockers.add("insufficient_event_days")
        ready_for_live_observation = False
    elif event_days < MINIMUM_EVENT_DAYS_STABLE:
        if lodo_stable:
            status = "calibrated_observer_only"
            ready_for_live_observation = True
        else:
            status = "calibrating"
            blockers.add("lodo_not_stable")
            ready_for_live_observation = False
    elif lodo_stable and early_late_stable:
        status = "stable_observer_only"
        ready_for_live_observation = True
    else:
        status = "unstable_no_window"
        blockers = {"unstable_window_boundaries"}
        ready_for_live_observation = False
        diagnostics["window_start"] = None
        diagnostics["window_end"] = None
        diagnostics["window_width_minutes"] = None
        diagnostics["window_quarter_count"] = None

    event_day_ids = [item["local_date"] for item in observations]
    calibration_fingerprint = None if contract_blocked else _fingerprint(profile, event_day_ids, source_fingerprints)

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "status": status,
        "profile": profile,
        "context_key": context_key,
        "classification_source": CLASSIFICATION_SOURCE,
        "observer_only": True,
        "forecast_influence_enabled": False,
        "ready_for_live_observation": ready_for_live_observation,
        "ready_for_forecast_influence": False,
        "event_count": event_count,
        "event_days": event_days,
        "rejected_event_count": rejected_event_count,
        "reject_reasons": {key: reject_reasons[key] for key in sorted(reject_reasons)},
        **diagnostics,
        "protected_window_overlap": protected_window_overlap,
        "native_resolution_minutes": NATIVE_RESOLUTION_MINUTES,
        "calibration_method": CALIBRATION_METHOD,
        "minimum_event_days_collecting_exit": MINIMUM_EVENT_DAYS_COLLECTING_EXIT,
        "minimum_event_days_calibrated": MINIMUM_EVENT_DAYS_CALIBRATED,
        "minimum_event_days_stable": MINIMUM_EVENT_DAYS_STABLE,
        "maximum_boundary_shift_minutes": MAXIMUM_BOUNDARY_SHIFT_MINUTES,
        "source_basis": source_basis,
        "calibration_fingerprint": calibration_fingerprint,
        "blockers": sorted(blockers),
    }
