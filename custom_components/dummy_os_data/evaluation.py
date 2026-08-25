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
