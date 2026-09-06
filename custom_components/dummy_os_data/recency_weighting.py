"""Observer-only Step 8A recency-weighting evaluation for Energy Forecast."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
from math import pow, sqrt
from typing import Any, Callable

SCHEMA_VERSION = "8a.1"
ALGORITHM_VERSION = "recency_weighting_observer_v1"
CONTROL_HALF_LIFE_DAYS = 28.0
CANDIDATE_HALF_LIVES_DAYS: tuple[float, ...] = (14.0, 21.0, 28.0, 42.0)
MIN_COLLECTING_EXIT_DAYS = 14
MIN_CALIBRATED_DAYS = 28
MIN_PAIRED_QUARTERS = 256
MIN_SEGMENT_PAIRED_QUARTERS = 32
MIN_MAE_GAIN_PCT = 3.0
MIN_PAIRED_WIN_RATE = 0.55
MAX_ABSOLUTE_BIAS_DEGRADATION_KWH = 0.005
MAX_P90_DEGRADATION_PCT = 5.0
MAX_SEGMENT_MAE_DEGRADATION_PCT = 5.0
CONTROL_REPRODUCTION_TOLERANCE_KWH = 0.000001
NATIVE_RESOLUTION_MINUTES = 15
SUPPORTED_PROFILES = {"normal", "away"}
SUPPORTED_MODEL = "historical_baseline"
SUPPORTED_MODEL_VERSION = "0.4"
DAYPARTS: tuple[tuple[str, int, int], ...] = (
    ("night", 0, 6),
    ("morning", 6, 12),
    ("afternoon", 12, 18),
    ("evening", 18, 24),
)


def _parse_aware(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _day_type(local_dt: datetime) -> str:
    return "weekend" if local_dt.weekday() >= 5 else "weekday"


def _daypart(local_dt: datetime) -> str:
    hour = local_dt.hour
    for name, start, end in DAYPARTS:
        if start <= hour < end:
            return name
    return "evening"


def _quarter_index(local_dt: datetime) -> int:
    return local_dt.hour * 4 + local_dt.minute // NATIVE_RESOLUTION_MINUTES


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


def recency_weight(age_days: float, half_life_days: float) -> float:
    """Return the exact exponential recency weight used by the production model."""
    age = max(0.0, float(age_days))
    return pow(0.5, age / float(half_life_days))


def _select_history_basis(
    records: list[dict[str, Any]],
    *,
    profile: str,
    target_start: datetime,
    captured_at: datetime,
    localize: Callable[[datetime], datetime],
) -> tuple[str, list[tuple[datetime, float]]]:
    target_local = localize(target_start)
    target_qidx = _quarter_index(target_local)
    target_day_type = _day_type(target_local)

    exact: list[tuple[datetime, float]] = []
    day_type: list[tuple[datetime, float]] = []
    quarter: list[tuple[datetime, float]] = []
    all_values: list[tuple[datetime, float]] = []

    for record in records:
        if record.get("valid") is not True or record.get("profile") != profile:
            continue
        start = _parse_aware(record.get("start"))
        if start is None or start >= captured_at:
            continue
        try:
            energy = float(record["energy_kwh"])
        except (KeyError, TypeError, ValueError):
            continue
        local_start = localize(start)
        sample = (start, energy)
        all_values.append(sample)
        if _quarter_index(local_start) == target_qidx:
            quarter.append(sample)
            if _day_type(local_start) == target_day_type:
                day_type.append(sample)
            if local_start.weekday() == target_local.weekday():
                exact.append(sample)

    if exact:
        return "weekday_quarter", exact
    if day_type:
        return "day_type_quarter", day_type
    if quarter:
        return "quarter_of_day", quarter
    if all_values:
        return "profile_mean", all_values
    return "unavailable", []


def _weighted_forecast(
    samples: list[tuple[datetime, float]],
    *,
    reference: datetime,
    half_life_days: float,
) -> tuple[float | None, float, float | None]:
    if not samples:
        return None, 0.0, None
    weighted_total = 0.0
    weight_sum = 0.0
    weight_sq_sum = 0.0
    for sample_start, energy in samples:
        age_days = max(0.0, (reference - sample_start).total_seconds() / 86400.0)
        weight = recency_weight(age_days, half_life_days)
        weighted_total += energy * weight
        weight_sum += weight
        weight_sq_sum += weight * weight
    if weight_sum <= 0.0:
        return None, 0.0, None
    forecast = weighted_total / weight_sum
    ess = (weight_sum * weight_sum / weight_sq_sum) if weight_sq_sum > 0 else None
    return forecast, weight_sum, ess


def _empty_candidate_metrics(half_life_days: float) -> dict[str, Any]:
    return {
        "half_life_days": half_life_days,
        "evaluation_count": 0,
        "distinct_local_days": 0,
        "mae_kwh": None,
        "rmse_kwh": None,
        "bias_kwh": None,
        "absolute_bias_kwh": None,
        "wmape_pct": None,
        "median_absolute_error_kwh": None,
        "p90_absolute_error_kwh": None,
        "mean_effective_sample_size": None,
        "mean_effective_weight_sum": None,
        "comparison_to_control": None,
        "promotion_criteria_met": False,
        "blockers": [],
    }


def _aggregate(rows: list[dict[str, Any]], half_life_days: float, localize) -> dict[str, Any]:
    result = _empty_candidate_metrics(half_life_days)
    usable = [row for row in rows if row["candidates"][half_life_days]["forecast_kwh"] is not None]
    result["evaluation_count"] = len(usable)
    result["distinct_local_days"] = len({localize(row["target_start"]).date().isoformat() for row in usable})
    if not usable:
        return result
    details = [row["candidates"][half_life_days] for row in usable]
    abs_errors = [detail["absolute_error_kwh"] for detail in details]
    signed_errors = [detail["error_kwh"] for detail in details]
    squared = [detail["squared_error_kwh2"] for detail in details]
    actual_total = sum(row["actual_kwh"] for row in usable)
    abs_error_total = sum(abs_errors)
    bias = sum(signed_errors) / len(signed_errors)
    result.update(
        {
            "mae_kwh": round(abs_error_total / len(abs_errors), 6),
            "rmse_kwh": round(sqrt(sum(squared) / len(squared)), 6),
            "bias_kwh": round(bias, 6),
            "absolute_bias_kwh": round(abs(bias), 6),
            "wmape_pct": round(abs_error_total / actual_total * 100.0, 3) if actual_total > 0 else None,
            "median_absolute_error_kwh": round(_quantile(abs_errors, 0.5), 6),
            "p90_absolute_error_kwh": round(_quantile(abs_errors, 0.9), 6),
            "mean_effective_sample_size": round(sum(detail["effective_sample_size"] for detail in details if detail["effective_sample_size"] is not None) / sum(1 for detail in details if detail["effective_sample_size"] is not None), 3) if any(detail["effective_sample_size"] is not None for detail in details) else None,
            "mean_effective_weight_sum": round(sum(detail["effective_weight_sum"] for detail in details) / len(details), 3),
        }
    )
    return result


def _improvement(control: float | None, candidate: float | None) -> float | None:
    if control is None or candidate is None:
        return None
    if control == 0:
        return 0.0 if candidate == 0 else None
    return round((control - candidate) / control * 100.0, 3)


def _comparison(rows: list[dict[str, Any]], half_life_days: float) -> dict[str, Any] | None:
    if half_life_days == CONTROL_HALF_LIFE_DAYS:
        return None
    paired = [
        row for row in rows
        if row["candidates"][CONTROL_HALF_LIFE_DAYS]["forecast_kwh"] is not None
        and row["candidates"][half_life_days]["forecast_kwh"] is not None
    ]
    if not paired:
        return {
            "mae_improvement_pct": None,
            "median_absolute_error_improvement_pct": None,
            "p90_improvement_pct": None,
            "paired_win_rate": None,
            "bias_change_kwh": None,
        }
    control_abs = [row["candidates"][CONTROL_HALF_LIFE_DAYS]["absolute_error_kwh"] for row in paired]
    candidate_abs = [row["candidates"][half_life_days]["absolute_error_kwh"] for row in paired]
    control_signed = [row["candidates"][CONTROL_HALF_LIFE_DAYS]["error_kwh"] for row in paired]
    candidate_signed = [row["candidates"][half_life_days]["error_kwh"] for row in paired]
    control_mae = sum(control_abs) / len(control_abs)
    candidate_mae = sum(candidate_abs) / len(candidate_abs)
    wins = sum(1 for c, k in zip(control_abs, candidate_abs) if k < c)
    return {
        "mae_improvement_pct": _improvement(control_mae, candidate_mae),
        "median_absolute_error_improvement_pct": _improvement(_quantile(control_abs, 0.5), _quantile(candidate_abs, 0.5)),
        "p90_improvement_pct": _improvement(_quantile(control_abs, 0.9), _quantile(candidate_abs, 0.9)),
        "paired_win_rate": round(wins / len(paired), 3),
        "bias_change_kwh": round(sum(candidate_signed) / len(candidate_signed) - sum(control_signed) / len(control_signed), 6),
    }


def _segment_metrics(rows: list[dict[str, Any]], localize) -> dict[str, Any]:
    segments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        local = localize(row["target_start"])
        segments[f"{_day_type(local)}_{_daypart(local)}"].append(row)
    result: dict[str, Any] = {}
    for key in sorted(segments):
        segment_rows = segments[key]
        local = localize(segment_rows[0]["target_start"])
        paired = [row for row in segment_rows if row["candidates"][CONTROL_HALF_LIFE_DAYS]["forecast_kwh"] is not None]
        control_abs = [row["candidates"][CONTROL_HALF_LIFE_DAYS]["absolute_error_kwh"] for row in paired]
        control_mae = sum(control_abs) / len(control_abs) if control_abs else None
        candidate_mae: dict[str, float | None] = {}
        changes: dict[str, float | None] = {}
        guards: dict[str, bool | None] = {}
        for half_life in CANDIDATE_HALF_LIVES_DAYS:
            vals = [row["candidates"][half_life]["absolute_error_kwh"] for row in paired if row["candidates"][half_life]["forecast_kwh"] is not None]
            mae = sum(vals) / len(vals) if len(vals) == len(paired) and vals else None
            candidate_mae[str(int(half_life))] = round(mae, 6) if mae is not None else None
            change = None
            if control_mae is not None and mae is not None:
                change = round((mae - control_mae) / control_mae * 100.0, 3) if control_mae > 0 else (0.0 if mae == 0 else None)
            changes[str(int(half_life))] = change
            if len(paired) < MIN_SEGMENT_PAIRED_QUARTERS or half_life == CONTROL_HALF_LIFE_DAYS:
                guards[str(int(half_life))] = None
            else:
                guards[str(int(half_life))] = change is not None and change <= MAX_SEGMENT_MAE_DEGRADATION_PCT
        result[key] = {
            "segment_key": key,
            "day_type": _day_type(local),
            "daypart": _daypart(local),
            "paired_count": len(paired),
            "control_mae_kwh": round(control_mae, 6) if control_mae is not None else None,
            "candidate_mae_kwh": candidate_mae,
            "mae_change_pct_vs_control": changes,
            "regression_guard_passed": guards,
        }
    return result


def _half_metrics(rows: list[dict[str, Any]], half_life: float) -> tuple[float | None, float | None]:
    paired = [row for row in rows if row["candidates"][CONTROL_HALF_LIFE_DAYS]["forecast_kwh"] is not None and row["candidates"][half_life]["forecast_kwh"] is not None]
    if not paired:
        return None, None
    control = sum(row["candidates"][CONTROL_HALF_LIFE_DAYS]["absolute_error_kwh"] for row in paired) / len(paired)
    candidate = sum(row["candidates"][half_life]["absolute_error_kwh"] for row in paired) / len(paired)
    return _improvement(control, candidate), candidate


def _preferred_by_mae(rows: list[dict[str, Any]]) -> float:
    candidates: list[tuple[float, float]] = []
    for half_life in CANDIDATE_HALF_LIVES_DAYS:
        paired = [row for row in rows if row["candidates"][half_life]["forecast_kwh"] is not None]
        if not paired:
            continue
        mae = sum(row["candidates"][half_life]["absolute_error_kwh"] for row in paired) / len(paired)
        candidates.append((mae, half_life))
    return min(candidates)[1] if candidates else CONTROL_HALF_LIFE_DAYS


def _early_late_metrics(rows: list[dict[str, Any]], distinct_days: int) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row["target_start"])
    split_index = len(ordered) // 2 if distinct_days >= MIN_CALIBRATED_DAYS and len(ordered) >= 2 else None
    if split_index is None:
        return {
            "split_index": None,
            "split_target_time": None,
            "early_count": 0,
            "late_count": 0,
            "per_candidate": {str(int(h)): {"mae_improvement_pct_early": None, "mae_improvement_pct_late": None} for h in CANDIDATE_HALF_LIVES_DAYS},
            "preferred_candidate_early": None,
            "preferred_candidate_late": None,
            "stable_preference": None,
        }
    early = ordered[:split_index]
    late = ordered[split_index:]
    per_candidate: dict[str, Any] = {}
    for half_life in CANDIDATE_HALF_LIVES_DAYS:
        early_improvement, _ = _half_metrics(early, half_life)
        late_improvement, _ = _half_metrics(late, half_life)
        per_candidate[str(int(half_life))] = {
            "mae_improvement_pct_early": None if half_life == CONTROL_HALF_LIFE_DAYS else early_improvement,
            "mae_improvement_pct_late": None if half_life == CONTROL_HALF_LIFE_DAYS else late_improvement,
        }
    preferred_early = _preferred_by_mae(early)
    preferred_late = _preferred_by_mae(late)
    return {
        "split_index": split_index,
        "split_target_time": ordered[split_index]["target_start"].isoformat(),
        "early_count": len(early),
        "late_count": len(late),
        "per_candidate": per_candidate,
        "preferred_candidate_early": preferred_early,
        "preferred_candidate_late": preferred_late,
        "stable_preference": preferred_early == preferred_late,
    }


def _fingerprint(profile: str, evaluation_ids: list[str], models: list[str]) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "profile": profile,
        "control_half_life_days": CONTROL_HALF_LIFE_DAYS,
        "candidate_half_lives_days": list(CANDIDATE_HALF_LIVES_DAYS),
        "native_resolution_minutes": NATIVE_RESOLUTION_MINUTES,
        "minimum_distinct_days_calibrated": MIN_CALIBRATED_DAYS,
        "minimum_paired_quarters": MIN_PAIRED_QUARTERS,
        "minimum_mae_gain_pct": MIN_MAE_GAIN_PCT,
        "minimum_paired_win_rate": MIN_PAIRED_WIN_RATE,
        "maximum_absolute_bias_degradation_kwh": MAX_ABSOLUTE_BIAS_DEGRADATION_KWH,
        "maximum_p90_degradation_pct": MAX_P90_DEGRADATION_PCT,
        "maximum_segment_mae_degradation_pct": MAX_SEGMENT_MAE_DEGRADATION_PCT,
        "evaluation_ids": sorted(evaluation_ids),
        "models": sorted(models),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "rw_" + hashlib.sha256(encoded).hexdigest()[:16]


def calculate_recency_weighting(
    records: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    profile: str,
    localize: Callable[[datetime], datetime],
) -> dict[str, Any]:
    """Replay fixed recency candidates without changing the production forecast."""
    blockers: set[str] = set()
    if profile not in SUPPORTED_PROFILES:
        blockers.add("invalid_profile")

    replay_rows: list[dict[str, Any]] = []
    evaluation_ids: list[str] = []
    model_versions: set[str] = set()
    control_checked = 0
    control_max_delta: float | None = None
    control_failed = False
    any_evaluation_basis = False
    any_history_basis = False

    if profile in SUPPORTED_PROFILES:
        for item in evaluations:
            if item.get("profile") != profile:
                continue
            any_evaluation_basis = True
            target_start = _parse_aware(item.get("start"))
            target_end = _parse_aware(item.get("end"))
            captured_at = _parse_aware(item.get("forecast_captured_at"))
            if target_start is None or target_end is None or captured_at is None:
                blockers.add("invalid_time_contract")
                continue
            if abs((target_end - target_start).total_seconds() - NATIVE_RESOLUTION_MINUTES * 60) > 1e-6 or captured_at > target_start:
                blockers.add("invalid_time_contract")
                continue
            try:
                stored_forecast = float(item["forecast_kwh"])
                actual = float(item["actual_kwh"])
                coverage = float(item["actual_coverage"])
            except (KeyError, TypeError, ValueError):
                continue
            if coverage < 0.90:
                continue

            source, samples = _select_history_basis(
                records,
                profile=profile,
                target_start=target_start,
                captured_at=captured_at,
                localize=localize,
            )
            if not samples:
                continue
            any_history_basis = True
            reference = captured_at
            if captured_at == target_start:
                reference = target_start - timedelta(microseconds=1)

            candidates: dict[float, dict[str, Any]] = {}
            for half_life in CANDIDATE_HALF_LIVES_DAYS:
                forecast, weight_sum, ess = _weighted_forecast(samples, reference=reference, half_life_days=half_life)
                if forecast is None:
                    candidates[half_life] = {
                        "forecast_kwh": None,
                        "error_kwh": None,
                        "absolute_error_kwh": None,
                        "squared_error_kwh2": None,
                        "source": source,
                        "raw_sample_count": len(samples),
                        "effective_weight_sum": round(weight_sum, 6),
                        "effective_sample_size": None,
                    }
                    continue
                rounded_forecast = round(forecast, 6)
                error = actual - rounded_forecast
                candidates[half_life] = {
                    "forecast_kwh": rounded_forecast,
                    "error_kwh": round(error, 6),
                    "absolute_error_kwh": round(abs(error), 6),
                    "squared_error_kwh2": round(error * error, 12),
                    "source": source,
                    "raw_sample_count": len(samples),
                    "effective_weight_sum": round(weight_sum, 6),
                    "effective_sample_size": round(ess, 6) if ess is not None else None,
                }

            evaluation_id = f"{profile}|{target_start.isoformat()}|{captured_at.isoformat()}"
            evaluation_ids.append(evaluation_id)
            model = item.get("model")
            model_version = item.get("model_version")
            model_versions.add(f"{model or 'unknown'}:{model_version or 'unknown'}")
            replay_rows.append(
                {
                    "evaluation_id": evaluation_id,
                    "target_start": target_start,
                    "target_end": target_end,
                    "captured_at": captured_at,
                    "actual_kwh": actual,
                    "stored_forecast_kwh": stored_forecast,
                    "stored_source": item.get("source"),
                    "model": model,
                    "model_version": model_version,
                    "candidates": candidates,
                }
            )

            if model == SUPPORTED_MODEL and model_version == SUPPORTED_MODEL_VERSION:
                control_checked += 1
                replay_control = candidates[CONTROL_HALF_LIFE_DAYS]["forecast_kwh"]
                if item.get("source") != source or replay_control is None:
                    control_failed = True
                else:
                    delta = abs(replay_control - stored_forecast)
                    control_max_delta = delta if control_max_delta is None else max(control_max_delta, delta)
                    if delta > CONTROL_REPRODUCTION_TOLERANCE_KWH:
                        control_failed = True

    if not any_evaluation_basis:
        blockers.add("missing_evaluation_basis")
    if any_evaluation_basis and not any_history_basis:
        blockers.add("missing_history_basis")
    if control_failed:
        blockers.add("control_reproduction_failed")

    per_candidate: dict[str, Any] = {}
    for half_life in CANDIDATE_HALF_LIVES_DAYS:
        metrics = _aggregate(replay_rows, half_life, localize)
        metrics["comparison_to_control"] = _comparison(replay_rows, half_life)
        per_candidate[str(int(half_life))] = metrics

    evaluation_count = per_candidate["28"]["evaluation_count"]
    distinct_days = per_candidate["28"]["distinct_local_days"]
    if distinct_days < MIN_CALIBRATED_DAYS:
        blockers.add("insufficient_distinct_days")
    if evaluation_count < MIN_PAIRED_QUARTERS:
        blockers.add("insufficient_paired_quarters")

    segment_metrics = _segment_metrics(replay_rows, localize)
    early_late = _early_late_metrics(replay_rows, distinct_days)

    qualifying: list[float] = []
    for half_life in CANDIDATE_HALF_LIVES_DAYS:
        key = str(int(half_life))
        metrics = per_candidate[key]
        candidate_blockers: list[str] = []
        if half_life == CONTROL_HALF_LIFE_DAYS:
            metrics["promotion_criteria_met"] = False
            metrics["blockers"] = []
            continue
        comparison = metrics["comparison_to_control"] or {}
        if metrics["mae_kwh"] is None or comparison.get("mae_improvement_pct") is None:
            candidate_blockers.append("candidate_metrics_incomplete")
        if distinct_days < MIN_CALIBRATED_DAYS:
            candidate_blockers.append("insufficient_distinct_days")
        if evaluation_count < MIN_PAIRED_QUARTERS:
            candidate_blockers.append("insufficient_paired_quarters")
        if (comparison.get("mae_improvement_pct") is None or comparison["mae_improvement_pct"] < MIN_MAE_GAIN_PCT):
            candidate_blockers.append("mae_gain_below_threshold")
        if (comparison.get("median_absolute_error_improvement_pct") is None or comparison["median_absolute_error_improvement_pct"] < 0):
            candidate_blockers.append("median_guard_failed")
        if (comparison.get("paired_win_rate") is None or comparison["paired_win_rate"] < MIN_PAIRED_WIN_RATE):
            candidate_blockers.append("win_rate_guard_failed")
        control_abs_bias = per_candidate["28"]["absolute_bias_kwh"]
        candidate_abs_bias = metrics["absolute_bias_kwh"]
        if control_abs_bias is None or candidate_abs_bias is None or candidate_abs_bias > control_abs_bias + MAX_ABSOLUTE_BIAS_DEGRADATION_KWH:
            candidate_blockers.append("bias_guard_failed")
        control_p90 = per_candidate["28"]["p90_absolute_error_kwh"]
        candidate_p90 = metrics["p90_absolute_error_kwh"]
        if control_p90 is None or candidate_p90 is None or (control_p90 > 0 and candidate_p90 > control_p90 * 1.05) or (control_p90 == 0 and candidate_p90 > 0):
            candidate_blockers.append("p90_guard_failed")
        segment_failed = any(
            segment["paired_count"] >= MIN_SEGMENT_PAIRED_QUARTERS
            and segment["regression_guard_passed"].get(key) is False
            for segment in segment_metrics.values()
        )
        if segment_failed:
            candidate_blockers.append("segment_regression")
        early_values = early_late["per_candidate"].get(key, {})
        if distinct_days >= MIN_CALIBRATED_DAYS and (
            early_values.get("mae_improvement_pct_early") is None
            or early_values.get("mae_improvement_pct_late") is None
            or early_values["mae_improvement_pct_early"] <= 0
            or early_values["mae_improvement_pct_late"] <= 0
        ):
            candidate_blockers.append("early_late_unstable")
        metrics["blockers"] = sorted(set(candidate_blockers))
        metrics["promotion_criteria_met"] = not candidate_blockers
        if not candidate_blockers:
            qualifying.append(half_life)

    preferred = CONTROL_HALF_LIFE_DAYS
    if qualifying:
        best = min(qualifying, key=lambda h: per_candidate[str(int(h))]["mae_kwh"])
        best_gain = per_candidate[str(int(best))]["comparison_to_control"]["mae_improvement_pct"]
        near_best = [
            h for h in qualifying
            if best_gain - per_candidate[str(int(h))]["comparison_to_control"]["mae_improvement_pct"] < 1.0
        ]
        preferred = max(near_best) if near_best else best

    promotion_ready = preferred != CONTROL_HALF_LIFE_DAYS and per_candidate[str(int(preferred))]["promotion_criteria_met"] and not control_failed

    stable_preference = early_late.get("stable_preference")
    if distinct_days >= MIN_CALIBRATED_DAYS:
        if preferred == CONTROL_HALF_LIFE_DAYS:
            stable_preference = early_late.get("preferred_candidate_early") == CONTROL_HALF_LIFE_DAYS and early_late.get("preferred_candidate_late") == CONTROL_HALF_LIFE_DAYS
        else:
            values = early_late["per_candidate"][str(int(preferred))]
            stable_preference = (
                early_late.get("preferred_candidate_early") == preferred
                and early_late.get("preferred_candidate_late") == preferred
                and values.get("mae_improvement_pct_early") is not None
                and values.get("mae_improvement_pct_late") is not None
                and values["mae_improvement_pct_early"] > 0
                and values["mae_improvement_pct_late"] > 0
            )
        early_late["stable_preference"] = stable_preference
        if not stable_preference:
            blockers.add("early_late_unstable")

    if profile not in SUPPORTED_PROFILES or control_failed:
        status = "blocked"
    elif distinct_days < MIN_COLLECTING_EXIT_DAYS:
        status = "collecting"
    elif distinct_days < MIN_CALIBRATED_DAYS:
        status = "calibrating"
    elif stable_preference:
        status = "stable_observer_only"
    else:
        status = "calibrated_observer_only"

    selected_metrics = per_candidate[str(int(preferred))]
    for blocker in selected_metrics.get("blockers", []):
        blockers.add(blocker)

    source_basis = {
        "record_count": sum(1 for record in records if record.get("valid") is True and record.get("profile") == profile),
        "evaluation_count_input": sum(1 for item in evaluations if item.get("profile") == profile),
        "replayed_evaluation_count": len(replay_rows),
        "models": sorted(model_versions),
        "control_model": f"{SUPPORTED_MODEL}:{SUPPORTED_MODEL_VERSION}",
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "status": status,
        "profile": profile,
        "observer_only": True,
        "forecast_influence_enabled": False,
        "control_half_life_days": CONTROL_HALF_LIFE_DAYS,
        "candidate_half_lives_days": list(CANDIDATE_HALF_LIVES_DAYS),
        "preferred_candidate_half_life_days": preferred,
        "promotion_ready": bool(promotion_ready),
        "evaluation_count": evaluation_count,
        "distinct_local_days": distinct_days,
        "control_reproduction_checked_count": control_checked,
        "control_reproduction_max_delta_kwh": round(control_max_delta, 6) if control_max_delta is not None else None,
        "control_reproduction_ok": None if control_checked == 0 else not control_failed,
        "source_basis": source_basis,
        "per_candidate_metrics": per_candidate,
        "segment_metrics": segment_metrics,
        "early_late_metrics": early_late,
        "blockers": sorted(blockers),
        "calibration_fingerprint": _fingerprint(profile, evaluation_ids, sorted(model_versions)),
    }
