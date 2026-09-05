"""Evaluation helpers for Dummy OS Home Forecast."""

from __future__ import annotations

from typing import Any

EVALUATION_EPSILON_KWH = 0.01


def calculate_metrics(
    evaluations: list[dict[str, Any]],
    profile: str | None = None,
) -> dict[str, Any]:
    """Calculate compact forecast evaluation metrics.

    Accuracy uses an aggregate WAPE-like definition:
    max(0, 100 * (1 - sum(abs(error)) / max(sum(actual), epsilon))).
    Aggregating actual energy across the evaluation window avoids unstable
    percentage errors for individual near-zero 15-minute quarters.
    """
    selected: list[dict[str, Any]] = []
    for item in evaluations:
        if profile is not None and item.get("profile") != profile:
            continue
        try:
            actual = float(item["actual_kwh"])
            forecast = float(item["forecast_kwh"])
        except (KeyError, TypeError, ValueError):
            continue
        selected.append({**item, "actual_kwh": actual, "forecast_kwh": forecast})

    samples = len(selected)
    if not selected:
        return {
            "samples": 0,
            "accuracy_percent": None,
            "mae_kwh": None,
            "bias_kwh": None,
            "actual_total_kwh": 0.0,
            "forecast_total_kwh": 0.0,
        }

    absolute_errors = [abs(item["forecast_kwh"] - item["actual_kwh"]) for item in selected]
    signed_errors = [item["forecast_kwh"] - item["actual_kwh"] for item in selected]
    actual_total = sum(item["actual_kwh"] for item in selected)
    forecast_total = sum(item["forecast_kwh"] for item in selected)
    error_total = sum(absolute_errors)

    denominator = max(actual_total, EVALUATION_EPSILON_KWH)
    accuracy = max(0.0, 100.0 * (1.0 - error_total / denominator))

    return {
        "samples": samples,
        "accuracy_percent": round(accuracy, 1),
        "mae_kwh": round(error_total / samples, 6),
        "bias_kwh": round(sum(signed_errors) / samples, 6),
        "actual_total_kwh": round(actual_total, 6),
        "forecast_total_kwh": round(forecast_total, 6),
    }

DAYPART_MINIMUM_SAMPLES = 32
DAYPARTS: tuple[tuple[str, int, int], ...] = (
    ("night", 0, 6),
    ("morning", 6, 12),
    ("afternoon", 12, 18),
    ("evening", 18, 24),
)


def _parse_aware_start(value: Any):
    """Parse an ISO timestamp and require timezone information."""
    from datetime import datetime

    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _daypart_for_local_start(local_start) -> str:
    """Return the fixed Step 3 daypart for a local quarter start."""
    hour = local_start.hour
    if hour < 6:
        return "night"
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "evening"


def calculate_daypart_quality(
    evaluations: list[dict[str, Any]],
    records: list[dict[str, Any]],
    profile: str,
    localize,
) -> dict[str, Any]:
    """Calculate observer-only forecast quality per fixed local daypart.

    Evaluation coverage is the number of usable forward-looking
    evaluations divided by valid actual quarters for the same profile
    and daypart. Invalid/missing values are never reconstructed as zero.
    """
    valid_actual_counts = {name: 0 for name, _, _ in DAYPARTS}
    selected = {name: [] for name, _, _ in DAYPARTS}

    for record in records:
        if record.get("profile") != profile or record.get("valid") is not True:
            continue
        start = _parse_aware_start(record.get("start"))
        if start is None:
            continue
        daypart = _daypart_for_local_start(localize(start))
        valid_actual_counts[daypart] += 1

    for item in evaluations:
        if item.get("profile") != profile:
            continue
        start = _parse_aware_start(item.get("start"))
        if start is None:
            continue
        try:
            float(item["actual_kwh"])
            float(item["forecast_kwh"])
        except (KeyError, TypeError, ValueError):
            continue
        daypart = _daypart_for_local_start(localize(start))
        selected[daypart].append(item)

    result: dict[str, Any] = {}
    all_sufficient = True
    for name, start_hour, end_hour in DAYPARTS:
        metrics = calculate_metrics(selected[name], profile=None)
        samples = int(metrics["samples"])
        denominator = valid_actual_counts[name]
        coverage = None
        if denominator > 0:
            coverage = round(min(100.0, samples / denominator * 100.0), 1)
        status = "sufficient_basis" if samples >= DAYPART_MINIMUM_SAMPLES else "collecting"
        if status != "sufficient_basis":
            all_sufficient = False
        result[name] = {
            "start_local": f"{start_hour:02d}:00",
            "end_local": f"{end_hour:02d}:00",
            "status": status,
            "sample_count": samples,
            "mae_kwh": metrics["mae_kwh"],
            "bias_kwh": metrics["bias_kwh"],
            "evaluation_coverage_percent": coverage,
            "accuracy_percent": metrics["accuracy_percent"],
            "valid_actual_quarters": denominator,
        }

    return {
        "profile": profile,
        "status": "sufficient_basis" if all_sufficient else "collecting",
        "minimum_samples_for_sufficient_basis": DAYPART_MINIMUM_SAMPLES,
        "observer_only": True,
        "dayparts": result,
    }


DAY_TYPE_MINIMUM_SAMPLES = 32
DAY_TYPES: tuple[str, str] = ("weekday", "weekend")

def _day_type_for_local_start(local_start) -> str:
    return "weekend" if local_start.weekday() >= 5 else "weekday"

def calculate_day_type_quality(evaluations: list[dict[str, Any]], records: list[dict[str, Any]], profile: str, localize) -> dict[str, Any]:
    valid_actual_counts = {name: 0 for name in DAY_TYPES}
    selected = {name: [] for name in DAY_TYPES}
    for record in records:
        if record.get("profile") != profile or record.get("valid") is not True: continue
        start = _parse_aware_start(record.get("start"))
        if start is not None: valid_actual_counts[_day_type_for_local_start(localize(start))] += 1
    for item in evaluations:
        if item.get("profile") != profile: continue
        start = _parse_aware_start(item.get("start"))
        if start is None: continue
        try: float(item["actual_kwh"]); float(item["forecast_kwh"])
        except (KeyError, TypeError, ValueError): continue
        selected[_day_type_for_local_start(localize(start))].append(item)
    result = {}; all_sufficient = True
    for name in DAY_TYPES:
        metrics = calculate_metrics(selected[name], profile=None); samples = int(metrics["samples"]); denominator = valid_actual_counts[name]
        coverage = round(min(100.0, samples / denominator * 100.0), 1) if denominator > 0 else None
        status = "sufficient_basis" if samples >= DAY_TYPE_MINIMUM_SAMPLES else "collecting"; all_sufficient = all_sufficient and status == "sufficient_basis"
        result[name] = {"status": status, "sample_count": samples, "mae_kwh": metrics["mae_kwh"], "bias_kwh": metrics["bias_kwh"], "evaluation_coverage_percent": coverage, "accuracy_percent": metrics["accuracy_percent"], "valid_actual_quarters": denominator}
    return {"profile": profile, "status": "sufficient_basis" if all_sufficient else "collecting", "minimum_samples_for_sufficient_basis": DAY_TYPE_MINIMUM_SAMPLES, "observer_only": True, "day_types": result}


DAY_TYPE_DAYPART_MINIMUM_SAMPLES = 32
DAY_TYPE_DAYPART_KEYS: tuple[str, ...] = tuple(f"{day_type}_{daypart}" for day_type in DAY_TYPES for daypart, _, _ in DAYPARTS)

def calculate_day_type_daypart_quality(evaluations: list[dict[str, Any]], records: list[dict[str, Any]], profile: str, localize) -> dict[str, Any]:
    """Calculate observer-only Energy quality per day-type/daypart combination."""
    valid_actual_counts = {key: 0 for key in DAY_TYPE_DAYPART_KEYS}
    selected = {key: [] for key in DAY_TYPE_DAYPART_KEYS}
    for record in records:
        if record.get("profile") != profile or record.get("valid") is not True: continue
        start = _parse_aware_start(record.get("start"))
        if start is None: continue
        local_start = localize(start); key = f"{_day_type_for_local_start(local_start)}_{_daypart_for_local_start(local_start)}"
        valid_actual_counts[key] += 1
    for item in evaluations:
        if item.get("profile") != profile: continue
        start = _parse_aware_start(item.get("start"))
        if start is None: continue
        try: float(item["actual_kwh"]); float(item["forecast_kwh"])
        except (KeyError, TypeError, ValueError): continue
        local_start = localize(start); key = f"{_day_type_for_local_start(local_start)}_{_daypart_for_local_start(local_start)}"
        selected[key].append(item)
    result = {}; all_sufficient = True
    for key in DAY_TYPE_DAYPART_KEYS:
        metrics = calculate_metrics(selected[key], profile=None); samples = int(metrics["samples"]); denominator = valid_actual_counts[key]
        coverage = round(min(100.0, samples / denominator * 100.0), 1) if denominator > 0 else None
        status = "sufficient_basis" if samples >= DAY_TYPE_DAYPART_MINIMUM_SAMPLES else "collecting"
        all_sufficient = all_sufficient and status == "sufficient_basis"
        result[key] = {"status": status, "sample_count": samples, "mae_kwh": metrics["mae_kwh"], "bias_kwh": metrics["bias_kwh"], "evaluation_coverage_percent": coverage, "accuracy_percent": metrics["accuracy_percent"], "valid_actual_quarters": denominator}
    return {"profile": profile, "status": "sufficient_basis" if all_sufficient else "collecting", "minimum_samples_for_sufficient_basis": DAY_TYPE_DAYPART_MINIMUM_SAMPLES, "observer_only": True, "combinations": result}


AFTERNOON_HOUR_MINIMUM_SAMPLES = 32
AFTERNOON_HOURS: tuple[int, ...] = tuple(range(12, 18))

def calculate_hour_quality(evaluations: list[dict[str, Any]], records: list[dict[str, Any]], profile: str, localize) -> dict[str, Any]:
    """Calculate observer-only Energy quality per local afternoon hour."""
    valid_actual_counts = {hour: 0 for hour in AFTERNOON_HOURS}
    selected = {hour: [] for hour in AFTERNOON_HOURS}
    for record in records:
        if record.get("profile") != profile or record.get("valid") is not True:
            continue
        start = _parse_aware_start(record.get("start"))
        if start is None:
            continue
        hour = localize(start).hour
        if hour in valid_actual_counts:
            valid_actual_counts[hour] += 1
    for item in evaluations:
        if item.get("profile") != profile:
            continue
        start = _parse_aware_start(item.get("start"))
        if start is None:
            continue
        try:
            float(item["actual_kwh"]); float(item["forecast_kwh"])
        except (KeyError, TypeError, ValueError):
            continue
        hour = localize(start).hour
        if hour in selected:
            selected[hour].append(item)
    result = {}; all_sufficient = True
    for hour in AFTERNOON_HOURS:
        metrics = calculate_metrics(selected[hour], profile=None)
        samples = int(metrics["samples"]); denominator = valid_actual_counts[hour]
        coverage = round(min(100.0, samples / denominator * 100.0), 1) if denominator > 0 else None
        status = "sufficient_basis" if samples >= AFTERNOON_HOUR_MINIMUM_SAMPLES else "collecting"
        all_sufficient = all_sufficient and status == "sufficient_basis"
        result[f"hour_{hour:02d}"] = {
            "start_local": f"{hour:02d}:00",
            "end_local": f"{hour + 1:02d}:00",
            "status": status,
            "sample_count": samples,
            "mae_kwh": metrics["mae_kwh"],
            "bias_kwh": metrics["bias_kwh"],
            "evaluation_coverage_percent": coverage,
            "accuracy_percent": metrics["accuracy_percent"],
            "valid_actual_quarters": denominator,
        }
    return {
        "profile": profile,
        "status": "sufficient_basis" if all_sufficient else "collecting",
        "minimum_samples_for_sufficient_basis": AFTERNOON_HOUR_MINIMUM_SAMPLES,
        "observer_only": True,
        "scope": "afternoon_12_18",
        "hours": result,
    }


# STEP6D_PEAK_LEARNING_OBSERVER_V1
PEAK_MINIMUM_SAMPLES_PER_HOUR = 32
PEAK_MINIMUM_DISTINCT_DAYS_PER_HOUR = 8
PEAK_THRESHOLD_QUANTILE = 0.90
PEAK_GRILL_WINDOW_START_HOUR = 17


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


def _timing_mad_minutes(event_centers: list[float]) -> float | None:
    center = _median(event_centers)
    if center is None:
        return None
    return _median([abs(value - center) for value in event_centers])


def calculate_peak_learning(evaluations: list[dict[str, Any]], profile: str, localize) -> dict[str, Any]:
    """Return observer-only Step 6 peak calibration and classification."""
    prepared: list[dict[str, Any]] = []
    for item in evaluations:
        if item.get("profile") != profile:
            continue
        start = _parse_aware_start(item.get("start"))
        end = _parse_aware_start(item.get("end"))
        if start is None or end is None:
            continue
        try:
            actual = float(item["actual_kwh"])
            forecast = float(item["forecast_kwh"])
            coverage = float(item["actual_coverage"])
        except (KeyError, TypeError, ValueError):
            continue
        if coverage < 0.90:
            continue
        local_start = localize(start)
        prepared.append({
            "start": start,
            "end": end,
            "local_start": local_start,
            "local_date": local_start.date().isoformat(),
            "local_hour": local_start.hour,
            "positive_residual_kwh": max(actual - forecast, 0.0),
        })

    by_hour = {hour: [] for hour in range(24)}
    for row in prepared:
        by_hour[row["local_hour"]].append(row)

    calibration = {}
    hour_ready = {}
    for hour in range(24):
        rows = by_hour[hour]
        days = {row["local_date"] for row in rows}
        ready = len(rows) >= PEAK_MINIMUM_SAMPLES_PER_HOUR and len(days) >= PEAK_MINIMUM_DISTINCT_DAYS_PER_HOUR
        hour_ready[hour] = ready
        threshold = _quantile([row["positive_residual_kwh"] for row in rows], PEAK_THRESHOLD_QUANTILE) if ready else None
        calibration[f"hour_{hour:02d}"] = {
            "status": "calibrated" if ready else "collecting",
            "sample_count": len(rows),
            "distinct_days": len(days),
            "threshold_kwh": round(threshold, 6) if threshold is not None else None,
        }

    candidates = []
    for row in prepared:
        comparison_rows = [other for other in by_hour[row["local_hour"]] if other["local_date"] != row["local_date"]]
        comparison_days = {other["local_date"] for other in comparison_rows}
        if len(comparison_rows) < PEAK_MINIMUM_SAMPLES_PER_HOUR or len(comparison_days) < PEAK_MINIMUM_DISTINCT_DAYS_PER_HOUR:
            continue
        threshold = _quantile([other["positive_residual_kwh"] for other in comparison_rows], PEAK_THRESHOLD_QUANTILE)
        if threshold is not None and row["positive_residual_kwh"] > threshold:
            candidates.append({**row, "threshold_kwh": threshold})

    candidates.sort(key=lambda row: row["start"])
    merged = []
    for row in candidates:
        if merged and merged[-1]["end"] == row["start"]:
            merged[-1]["end"] = row["end"]
            merged[-1]["quarters"].append(row)
        else:
            merged.append({"start": row["start"], "end": row["end"], "local_date": row["local_date"], "quarters": [row]})

    events = []
    for event in merged:
        quarters = event["quarters"]
        residuals = [q["positive_residual_kwh"] for q in quarters]
        total = sum(residuals)
        weighted_center = None
        if total > 0:
            weighted_center = sum((q["local_start"].hour * 60 + q["local_start"].minute + 7.5) * q["positive_residual_kwh"] for q in quarters) / total
        peak = max(quarters, key=lambda q: q["positive_residual_kwh"])
        events.append({
            "start": event["start"].isoformat(),
            "end": event["end"].isoformat(),
            "local_date": event["local_date"],
            "quarter_count": len(quarters),
            "duration_minutes": len(quarters) * 15,
            "extra_energy_kwh": round(total, 6),
            "max_positive_residual_kwh": round(peak["positive_residual_kwh"], 6),
            "peak_quarter_start": peak["start"].isoformat(),
            "center_minute_of_day": round(weighted_center, 1) if weighted_center is not None else None,
        })

    groups = {hour: [] for hour in range(24)}
    for event in events:
        start = _parse_aware_start(event["start"])
        if start is not None:
            groups[localize(start).hour].append(event)

    group_metrics: dict[int, dict[str, Any]] = {}
    repeat_rates_for_calibration: list[float] = []
    timing_mads_for_calibration: list[float] = []
    for hour in range(24):
        days = {row["local_date"] for row in by_hour[hour]}
        hour_events = groups[hour]
        event_days = {event["local_date"] for event in hour_events}
        repeat_rate = len(event_days) / len(days) if days else None
        centers = [event["center_minute_of_day"] for event in hour_events if event["center_minute_of_day"] is not None]
        timing_mad = _timing_mad_minutes(centers)
        group_metrics[hour] = {
            "event_count": len(hour_events),
            "event_days": len(event_days),
            "observed_days": len(days),
            "repeat_rate": repeat_rate,
            "timing_mad_minutes": timing_mad,
        }
        # A single event is by definition not repetition. Numeric separation
        # between low/high recurrence is calibrated from the observed history.
        if hour_ready[hour] and len(event_days) >= 2 and repeat_rate is not None:
            repeat_rates_for_calibration.append(repeat_rate)
            if timing_mad is not None:
                timing_mads_for_calibration.append(timing_mad)

    repeat_rate_threshold = _median(repeat_rates_for_calibration)
    timing_mad_threshold = _median(timing_mads_for_calibration)
    classifications = {}
    for hour in range(24):
        metrics = group_metrics[hour]
        repeat_rate = metrics["repeat_rate"]
        timing_mad = metrics["timing_mad_minutes"]
        if not hour_ready[hour]:
            classification = "unresolved"
        elif metrics["event_days"] < 2:
            classification = "incidental"
        elif repeat_rate_threshold is None:
            classification = "unresolved"
        elif repeat_rate is None or repeat_rate < repeat_rate_threshold:
            classification = "incidental"
        elif hour == PEAK_GRILL_WINDOW_START_HOUR:
            classification = "shifting_structural_grill"
        elif timing_mad_threshold is None or timing_mad is None:
            classification = "unresolved"
        elif timing_mad <= timing_mad_threshold:
            classification = "structural"
        else:
            classification = "shifting_structural_grill"
        classifications[f"hour_{hour:02d}"] = {
            "classification": classification,
            "event_count": metrics["event_count"],
            "event_days": metrics["event_days"],
            "observed_days": metrics["observed_days"],
            "repeat_rate": round(repeat_rate, 4) if repeat_rate is not None else None,
            "timing_mad_minutes": round(timing_mad, 1) if timing_mad is not None else None,
            "protected_window": hour == PEAK_GRILL_WINDOW_START_HOUR,
        }

    calibrated_hours = sum(hour_ready.values())
    if not prepared or calibrated_hours == 0:
        status = "collecting"
    elif calibrated_hours < 24:
        status = "calibrating"
    else:
        status = "calibrated_observer_only"

    from hashlib import sha256
    from json import dumps
    source_basis = {
        "evaluation_count": len(prepared),
        "first_start": min((row["start"] for row in prepared), default=None).isoformat() if prepared else None,
        "last_start": max((row["start"] for row in prepared), default=None).isoformat() if prepared else None,
    }
    fingerprint_payload = {
        "algorithm_version": "peak_observer_v1",
        "profile": profile,
        "source_basis": source_basis,
        "calibration": calibration,
        "repeat_rate_threshold": repeat_rate_threshold,
        "timing_mad_threshold": timing_mad_threshold,
    }
    calibration_fingerprint = sha256(dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]

    return {
        "schema_version": 1,
        "algorithm_version": "peak_observer_v1",
        "calibration_fingerprint": calibration_fingerprint,
        "source_basis": source_basis,
        "profile": profile,
        "status": status,
        "observer_only": True,
        "forecast_influence_enabled": False,
        "ready_for_model_influence": False,
        "minimum_samples_per_hour": PEAK_MINIMUM_SAMPLES_PER_HOUR,
        "minimum_distinct_days_per_hour": PEAK_MINIMUM_DISTINCT_DAYS_PER_HOUR,
        "threshold_method": "leave_one_local_day_out_positive_residual_quantile",
        "threshold_quantile": PEAK_THRESHOLD_QUANTILE,
        "candidate_count": len(candidates),
        "event_count": len(events),
        "calibrated_hours": calibrated_hours,
        "classification_calibration": {
            "repeat_rate_threshold": round(repeat_rate_threshold, 4) if repeat_rate_threshold is not None else None,
            "timing_mad_threshold_minutes": round(timing_mad_threshold, 1) if timing_mad_threshold is not None else None,
            "basis": "median_of_repeating_ready_hours",
        },
        "calibration": calibration,
        "classifications": classifications,
        "protected_windows": {"17:00-18:00": {"policy": "no_exact_quarter_structural", "forced_classification_when_repeating": "shifting_structural_grill"}},
        "events": events,
    }
