from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "custom_components/dummy_os_data/recency_weighting.py"
SPEC = importlib.util.spec_from_file_location("recency_weighting", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RW)
UTC = timezone.utc


def localize(dt):
    return dt


def make_history(days=40, profile="normal", base=0.2, trend=0.0, quarters=(12,)):
    rows = []
    origin = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    for day in range(days):
        for hour in quarters:
            start = origin + timedelta(days=day, hours=hour)
            rows.append(
                {
                    "start": start.isoformat(),
                    "end": (start + timedelta(minutes=15)).isoformat(),
                    "energy_kwh": base + trend * day,
                    "coverage": 1.0,
                    "profile": profile,
                    "valid": True,
                }
            )
    return rows


def production_control(records, target, captured_at, profile="normal"):
    source, samples = RW._select_history_basis(
        records,
        profile=profile,
        target_start=target,
        captured_at=captured_at,
        localize=localize,
    )
    reference = target - timedelta(microseconds=1) if captured_at == target else captured_at
    forecast, _, _ = RW._weighted_forecast(
        samples,
        reference=reference,
        half_life_days=28.0,
    )
    return source, None if forecast is None else round(forecast, 6)


def make_evaluations(records, start_day=7, end_day=35, profile="normal", hours=(12,)):
    output = []
    origin = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    by_start = {row["start"]: row for row in records if row.get("profile") == profile}
    for day in range(start_day, end_day):
        for hour in hours:
            target = origin + timedelta(days=day, hours=hour)
            row = by_start.get(target.isoformat())
            if row is None:
                continue
            source, forecast = production_control(records, target, target, profile)
            if forecast is None:
                continue
            actual = float(row["energy_kwh"])
            output.append(
                {
                    "evaluation_schema_version": 1,
                    "start": target.isoformat(),
                    "end": (target + timedelta(minutes=15)).isoformat(),
                    "profile": profile,
                    "forecast_kwh": forecast,
                    "forecast_captured_at": target.isoformat(),
                    "actual_kwh": actual,
                    "actual_coverage": 1.0,
                    "source": source,
                    "confidence": 0.5,
                    "sample_count": 1,
                    "model": "historical_baseline",
                    "model_version": "0.4",
                }
            )
    return output


def test_exact_contract_and_weight_values():
    assert RW.SCHEMA_VERSION == "8a.1"
    assert RW.ALGORITHM_VERSION == "recency_weighting_observer_v1"
    assert RW.CANDIDATE_HALF_LIVES_DAYS == (14.0, 21.0, 28.0, 42.0)
    assert RW.recency_weight(0, 28) == 1.0
    assert abs(RW.recency_weight(14, 14) - 0.5) < 1e-12
    assert abs(RW.recency_weight(21, 21) - 0.5) < 1e-12
    assert abs(RW.recency_weight(28, 28) - 0.5) < 1e-12
    assert abs(RW.recency_weight(42, 42) - 0.5) < 1e-12


def test_collecting_null_and_control_semantics():
    records = make_history(20)
    evaluations = make_evaluations(records, end_day=14)
    result = RW.calculate_recency_weighting(records, evaluations, "normal", localize)
    assert result["status"] == "collecting"
    assert result["observer_only"] is True
    assert result["forecast_influence_enabled"] is False
    assert result["promotion_ready"] is False
    assert list(result["per_candidate_metrics"]) == ["14", "21", "28", "42"]
    assert result["per_candidate_metrics"]["28"]["comparison_to_control"] is None
    assert result["preferred_candidate_half_life_days"] in {14.0, 21.0, 28.0, 42.0}


def test_28_day_control_reproduces_stored_forward_forecast():
    records = make_history(40, trend=0.001)
    evaluations = make_evaluations(records, end_day=35)
    result = RW.calculate_recency_weighting(records, evaluations, "normal", localize)
    assert result["control_reproduction_checked_count"] > 0
    assert result["control_reproduction_ok"] is True
    assert result["control_reproduction_max_delta_kwh"] == 0.0


def test_control_mismatch_blocks_observer_promotion():
    records = make_history(40)
    evaluations = make_evaluations(records, end_day=35)
    evaluations[0]["forecast_kwh"] += 0.1
    result = RW.calculate_recency_weighting(records, evaluations, "normal", localize)
    assert result["status"] == "blocked"
    assert result["control_reproduction_ok"] is False
    assert "control_reproduction_failed" in result["blockers"]
    assert result["promotion_ready"] is False


def test_history_cutoff_is_strictly_before_capture_and_profiles_never_mix():
    records = make_history(10)
    target = datetime(2026, 1, 8, 12, 0, tzinfo=UTC)
    records.append(
        {
            "start": target.isoformat(),
            "end": (target + timedelta(minutes=15)).isoformat(),
            "energy_kwh": 99.0,
            "profile": "normal",
            "valid": True,
        }
    )
    records.append(
        {
            "start": (target - timedelta(days=7)).isoformat(),
            "end": (target - timedelta(days=7) + timedelta(minutes=15)).isoformat(),
            "energy_kwh": 99.0,
            "profile": "away",
            "valid": True,
        }
    )
    _, samples = RW._select_history_basis(
        records,
        profile="normal",
        target_start=target,
        captured_at=target,
        localize=localize,
    )
    assert samples
    assert all(sample_start < target for sample_start, _ in samples)
    assert all(value != 99.0 for _, value in samples)


def test_invalid_profile_is_blocked_and_unknown_is_not_normal():
    result = RW.calculate_recency_weighting([], [], "unknown", localize)
    assert result["status"] == "blocked"
    assert "invalid_profile" in result["blockers"]
    assert result["control_reproduction_ok"] is None
    assert result["forecast_influence_enabled"] is False


def test_effective_sample_size_is_positive_and_not_above_raw_sample_count():
    records = make_history(40)
    evaluations = make_evaluations(records, end_day=20)
    result = RW.calculate_recency_weighting(records, evaluations, "normal", localize)
    mean_ess = result["per_candidate_metrics"]["14"]["mean_effective_sample_size"]
    assert mean_ess is not None and mean_ess > 0
    source, samples = RW._select_history_basis(
        records,
        profile="normal",
        target_start=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        captured_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        localize=localize,
    )
    assert source != "unavailable"
    _, _, ess = RW._weighted_forecast(
        samples,
        reference=datetime(2026, 1, 15, 12, 0, tzinfo=UTC) - timedelta(microseconds=1),
        half_life_days=14.0,
    )
    assert ess is not None and ess <= len(samples) + 1e-9


def test_fingerprint_is_deterministic_and_input_order_independent():
    records = make_history(40)
    evaluations = make_evaluations(records, end_day=35)
    first = RW.calculate_recency_weighting(records, evaluations, "normal", localize)
    second = RW.calculate_recency_weighting(list(reversed(records)), list(reversed(evaluations)), "normal", localize)
    assert first["calibration_fingerprint"] == second["calibration_fingerprint"]
    assert first["calibration_fingerprint"].startswith("rw_")


def test_segment_guard_marks_more_than_five_percent_regression():
    origin = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
    rows = []
    for index in range(64):
        start = origin + timedelta(days=index)
        candidates = {}
        for half_life in RW.CANDIDATE_HALF_LIVES_DAYS:
            abs_error = 0.10 if half_life == 28.0 else (0.106 if half_life == 14.0 else 0.10)
            candidates[half_life] = {
                "forecast_kwh": 0.2,
                "absolute_error_kwh": abs_error,
                "error_kwh": abs_error,
                "squared_error_kwh2": abs_error * abs_error,
                "effective_sample_size": 1.0,
                "effective_weight_sum": 1.0,
            }
        rows.append({"target_start": start, "actual_kwh": 0.3, "candidates": candidates})
    segments = RW._segment_metrics(rows, localize)
    assert any(segment["regression_guard_passed"]["14"] is False for segment in segments.values())


def test_early_late_instability_is_detected():
    origin = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    rows = []
    for index in range(40):
        candidates = {}
        early = index < 20
        for half_life in RW.CANDIDATE_HALF_LIVES_DAYS:
            if half_life == 28.0:
                error = 0.10
            elif half_life == 14.0:
                error = 0.05 if early else 0.15
            elif half_life == 42.0:
                error = 0.15 if early else 0.05
            else:
                error = 0.11
            candidates[half_life] = {
                "forecast_kwh": 0.2,
                "absolute_error_kwh": error,
                "error_kwh": error,
                "squared_error_kwh2": error * error,
                "effective_sample_size": 1.0,
                "effective_weight_sum": 1.0,
            }
        rows.append({"target_start": origin + timedelta(days=index), "actual_kwh": 0.3, "candidates": candidates})
    metrics = RW._early_late_metrics(rows, 40)
    assert metrics["preferred_candidate_early"] != metrics["preferred_candidate_late"]
    assert metrics["stable_preference"] is False
