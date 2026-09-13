"""Stable versioned Forecast -> Planner contract for Step 15."""

from __future__ import annotations

from datetime import datetime
from typing import Any

CONTRACT_NAME = "dummy_os_forecast_to_planner"
CONTRACT_VERSION = 1
SCHEMA_VERSION = 1
PROFILE_CONTRACT_VERSION = 1
SUPPORTED_PROFILES = {"normal", "away"}
READY_MODEL_HEALTH = {"usable", "strong"}
NATIVE_RESOLUTION_MINUTES = 15
NATIVE_SLOT_COUNT = 288
PLANNER_RESOLUTION_MINUTES = 60
PLANNER_HOUR_COUNT = 72
QUARTERS_PER_HOUR = 4

_READINESS_FIELDS = (
    "history_days",
    "valid_quarters",
    "forecast_coverage_percent",
    "average_confidence_percent",
    "evaluation_samples",
    "accuracy_percent",
    "mae_kwh",
    "bias_kwh",
    "absolute_bias_kwh",
    "horizon_evidence_status",
    "horizon_observing_count",
    "horizon_sufficient_count",
    "weak_segment_count",
    "runtime_input_status",
    "forecast_operational_input_ok",
    "runtime_blockers",
)


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _validate_hours(hours: Any) -> list[str]:
    blockers: list[str] = []
    if not isinstance(hours, list):
        return ["hours_missing"]
    if len(hours) != PLANNER_HOUR_COUNT:
        blockers.append("planner_hour_count_not_72")
        return blockers

    previous_end: datetime | None = None
    for expected_index, hour in enumerate(hours):
        if not isinstance(hour, dict):
            blockers.append(f"hour_{expected_index}_invalid")
            continue
        if hour.get("index") != expected_index:
            blockers.append(f"hour_{expected_index}_index_mismatch")
        if hour.get("quarter_count") != QUARTERS_PER_HOUR:
            blockers.append(f"hour_{expected_index}_quarter_count_not_4")
        if hour.get("populated_quarters") != QUARTERS_PER_HOUR:
            blockers.append(f"hour_{expected_index}_not_fully_populated")
        try:
            float(hour["energy_kwh"])
        except (KeyError, TypeError, ValueError):
            blockers.append(f"hour_{expected_index}_energy_unavailable")

        start = _aware(hour.get("start"))
        end = _aware(hour.get("end"))
        if start is None or end is None:
            blockers.append(f"hour_{expected_index}_timestamp_invalid")
            continue
        if (end - start).total_seconds() != 3600:
            blockers.append(f"hour_{expected_index}_duration_not_60m")
        if previous_end is not None and start != previous_end:
            blockers.append(f"hour_{expected_index}_not_contiguous")
        previous_end = end
    return blockers


def build_forecast_planner_contract(
    *,
    planner_hours: dict[str, Any],
    model_health: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic, model-agnostic planner consumption contract."""
    profile = str(planner_hours.get("profile") or model_health.get("profile") or "unclassified")
    blockers: list[str] = []

    if profile not in SUPPORTED_PROFILES:
        blockers.append("profile_unclassified")
    if model_health.get("profile") not in {None, profile}:
        blockers.append("model_health_profile_mismatch")
    if planner_hours.get("status") != "ok":
        blockers.append("planner_hours_not_ok")
    if planner_hours.get("native_resolution_minutes") != NATIVE_RESOLUTION_MINUTES:
        blockers.append("native_resolution_not_15")
    if planner_hours.get("native_public_slots") != NATIVE_SLOT_COUNT:
        blockers.append("native_slot_count_not_288")
    if planner_hours.get("planner_hour_count") != PLANNER_HOUR_COUNT:
        blockers.append("planner_hour_count_not_72")
    if planner_hours.get("valid_hour_count") != PLANNER_HOUR_COUNT:
        blockers.append("valid_hour_count_not_72")
    if planner_hours.get("quarters_per_hour") != QUARTERS_PER_HOUR:
        blockers.append("quarters_per_hour_not_4")
    if planner_hours.get("padding_used") is not False:
        blockers.append("padding_detected")
    if planner_hours.get("second_forecast_architecture") is not False:
        blockers.append("second_forecast_architecture_detected")

    planner_start = _aware(planner_hours.get("planner_start"))
    planner_end = _aware(planner_hours.get("planner_end"))
    if planner_start is None or planner_end is None:
        blockers.append("planner_window_invalid")
    elif (planner_end - planner_start).total_seconds() != PLANNER_HOUR_COUNT * 3600:
        blockers.append("planner_window_not_72h")

    hours = planner_hours.get("hours")
    blockers.extend(_validate_hours(hours))

    model_health_status = str(model_health.get("readiness_status") or "unknown")
    if model_health_status not in READY_MODEL_HEALTH:
        blockers.append(f"model_health_{model_health_status}")

    blockers = sorted(set(blockers))
    ready = not blockers
    if profile not in SUPPORTED_PROFILES:
        status = "profile_unclassified"
    else:
        status = "ready" if ready else "blocked"

    result: dict[str, Any] = {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "profile_contract_version": PROFILE_CONTRACT_VERSION,
        "status": status,
        "ready_for_planner": ready,
        "blockers": blockers,
        "profile": profile,
        "model_health_status": model_health_status,
        "native_resolution_minutes": NATIVE_RESOLUTION_MINUTES,
        "native_slot_count": NATIVE_SLOT_COUNT,
        "planner_resolution_minutes": PLANNER_RESOLUTION_MINUTES,
        "planner_hour_count": PLANNER_HOUR_COUNT,
        "quarters_per_hour": QUARTERS_PER_HOUR,
        "planner_start": planner_hours.get("planner_start"),
        "planner_end": planner_hours.get("planner_end"),
        "leading_quarter_offset": planner_hours.get("leading_quarter_offset"),
        "extra_quarters_generated": planner_hours.get("extra_quarters_generated"),
        "generated_quarter_count": planner_hours.get("generated_quarter_count"),
        "padding_used": planner_hours.get("padding_used"),
        "second_forecast_architecture": planner_hours.get("second_forecast_architecture"),
        "native_timeline_entity": "sensor.do_energy_forecast_timeline",
        "planner_hours_entity": "sensor.do_energy_forecast_planner_hours",
        "model_health_entity": "sensor.do_energy_forecast_model_health",
        "consumer_scope": "dummy_os_ems_planner",
        "physical_execution_authority": False,
        "hours": hours if isinstance(hours, list) else [],
    }
    for field in _READINESS_FIELDS:
        result[field] = model_health.get(field)
    if planner_hours.get("time_contract") is not None:
        from custom_components.dummy_os_data.planner_time_contract import time_fields
        result.update(time_fields(planner_hours["time_contract"]))
        result["planner_resolution_minutes"] = 15
        result["transport_resolution_minutes"] = 60
        result["hour_grouping"] = "window_relative_transport_not_apex"
    return result
