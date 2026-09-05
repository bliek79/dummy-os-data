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
