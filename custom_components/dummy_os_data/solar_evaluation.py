"""Pure helpers for quarter-hour Solar forecast evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any, Mapping

ROOFS = ("north", "south", "total")
EVALUATION_EPSILON_KWH = 0.01


def _round_optional(value: float | None, digits: int = 6) -> float | None:
    return round(value, digits) if value is not None else None


def _component_metrics(
    forecast_kwh: float | None,
    actual_kwh: float | None,
) -> dict[str, float | None]:
    """Return transparent signed-error and percentage metrics for one roof."""
    if forecast_kwh is None or actual_kwh is None:
        return {
            "error_kwh": None,
            "absolute_error_kwh": None,
            "bias_percent": None,
            "accuracy_percent": None,
        }

    error = forecast_kwh - actual_kwh
    denominator = max(actual_kwh, EVALUATION_EPSILON_KWH)
    bias_percent = 100.0 * error / denominator
    accuracy_percent = max(0.0, 100.0 * (1.0 - abs(error) / denominator))
    return {
        "error_kwh": round(error, 6),
        "absolute_error_kwh": round(abs(error), 6),
        "bias_percent": round(bias_percent, 1),
        "accuracy_percent": round(accuracy_percent, 1),
    }


def build_quarter_evaluation(
    slot_start: datetime,
    forecast: Mapping[str, Any] | None,
    energy_ws: Mapping[str, float],
    covered_seconds: Mapping[str, float],
    sample_count: int,
    min_coverage: float,
) -> dict[str, Any]:
    """Build one flat, Sheets-ready evaluation record.

    A forecast is valid only when it was frozen no later than the slot start.
    Actual energy uses zero-order-hold integration of the inverter AC power and
    its DC-input-ratio split. Each component requires the configured minimum
    time coverage; missing data is never converted to zero.
    """
    start = slot_start
    end = start + timedelta(minutes=15)
    duration_seconds = 15 * 60

    forecast_valid = forecast is not None
    captured_at: datetime | None = None
    if forecast_valid:
        try:
            raw_captured_at = forecast.get("captured_at")
            captured_at = datetime.fromisoformat(str(raw_captured_at))
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=start.tzinfo)
            forecast_valid = captured_at <= start
        except (TypeError, ValueError):
            forecast_valid = False

    coverage: dict[str, float] = {}
    actual: dict[str, float | None] = {}
    component_valid: dict[str, bool] = {}
    for roof in ROOFS:
        seconds = max(0.0, min(float(covered_seconds.get(roof, 0.0)), duration_seconds))
        coverage[roof] = seconds / duration_seconds
        component_valid[roof] = coverage[roof] >= min_coverage
        actual[roof] = (
            max(0.0, float(energy_ws.get(roof, 0.0))) / 3_600_000.0
            if component_valid[roof]
            else None
        )

    forecast_values: dict[str, float | None] = {roof: None for roof in ROOFS}
    if forecast_valid:
        for roof in ROOFS:
            try:
                value = float(forecast[f"{roof}_kwh"])
                if not math.isfinite(value):
                    raise ValueError
                forecast_values[roof] = max(0.0, value)
            except (KeyError, TypeError, ValueError):
                forecast_valid = False
                break
    if forecast_valid:
        forecast_valid = abs(
            (forecast_values["north"] or 0.0)
            + (forecast_values["south"] or 0.0)
            - (forecast_values["total"] or 0.0)
        ) <= 0.000001

    if not forecast_valid:
        status = "missing_or_late_forecast_snapshot"
    elif not component_valid["total"]:
        status = "insufficient_total_coverage"
    elif not component_valid["north"] or not component_valid["south"]:
        status = "insufficient_roof_coverage"
    else:
        status = "ok"

    result: dict[str, Any] = {
        "slot_id": start.isoformat(),
        "slot_start": start.isoformat(),
        "slot_end": end.isoformat(),
        "timezone": "UTC",
        "resolution_minutes": 15,
        "status": status,
        "valid": status == "ok",
        "sample_count": max(0, int(sample_count)),
        "minimum_coverage_percent": round(min_coverage * 100.0, 1),
        "actual_method": "total_ac_zero_order_hold_x_dc_input_ratio",
        "evaluation_method": "pre_slot_snapshot_vs_completed_quarter_v1",
        "forecast_captured_at": captured_at.isoformat() if captured_at else None,
        "forecast_source_update": forecast.get("source_update") if forecast_valid else None,
        "forecast_provider": forecast.get("provider") if forecast_valid else None,
        "forecast_model": forecast.get("model") if forecast_valid else None,
    }

    for roof in ROOFS:
        forecast_value = forecast_values[roof] if forecast_valid else None
        actual_value = actual[roof]
        metrics = _component_metrics(forecast_value, actual_value)
        result[f"forecast_{roof}_kwh"] = _round_optional(forecast_value)
        result[f"actual_{roof}_kwh"] = _round_optional(actual_value)
        result[f"error_{roof}_kwh"] = metrics["error_kwh"]
        result[f"absolute_error_{roof}_kwh"] = metrics["absolute_error_kwh"]
        result[f"bias_{roof}_percent"] = metrics["bias_percent"]
        result[f"accuracy_{roof}_percent"] = metrics["accuracy_percent"]
        result[f"valid_{roof}"] = forecast_valid and component_valid[roof]
        result[f"coverage_{roof}_seconds"] = round(
            coverage[roof] * duration_seconds,
            1,
        )
        result[f"coverage_{roof}_percent"] = round(coverage[roof] * 100.0, 1)

    return result
