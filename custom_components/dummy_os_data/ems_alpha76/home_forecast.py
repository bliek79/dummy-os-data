from __future__ import annotations

from typing import Any


def build_internal_home_forecast(
    history: list[dict[str, Any]],
    now: Any | None = None,
) -> dict[str, Any]:
    """Compatibility stub for the removed legacy EMS Home Forecast.

    Alpha73 removes the alpha71/alpha72 internal Home Forecast runtime from EMS.
    The active Plan72 path continues to use the configured external Home Forecast.
    This temporary stub keeps older coordinator imports safe during the cleanup
    release and deliberately returns no 288-slot forecast or diagnostic arrays.
    """
    return {
        "internal_home_forecast_status": "removed",
        "internal_home_forecast_total_72h_kwh": None,
        "internal_home_forecast_coverage_percent": 0.0,
        "internal_home_forecast_confidence_percent": 0.0,
        "internal_home_forecast_pattern_coverage_percent": 0.0,
        "internal_home_forecast_generated_at": None,
        "internal_home_forecast_horizon_hours": 72,
        "internal_home_forecast_resolution_minutes": 15,
        "internal_home_forecast_history_days": 0,
        "internal_home_forecast_history_points": 0,
        "internal_home_forecast_direct_pattern_quarters": 0,
        "internal_home_forecast_fallback_quarters": 0,
        "internal_home_forecast_model": "removed_alpha73",
        "internal_home_forecast_min_source_coverage_percent": None,
        "internal_home_forecast_min_ready_history_days": None,
        "internal_home_forecast_forecasts": [],
        "internal_home_forecast_hourly": [],
        "internal_home_forecast_shadow_only": True,
        "internal_home_forecast_plan72_source": False,
    }
