from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from typing import Any

FORECAST_PLANNER_CONTRACT_ENTITY = "sensor.do_energy_forecast_planner_contract"
EXPECTED_CONTRACT_NAME = "dummy_os_forecast_to_planner"
EXPECTED_CONTRACT_VERSION = 1
EXPECTED_SCHEMA_VERSION = 1
EXPECTED_PROFILE_CONTRACT_VERSION = 1
SUPPORTED_PROFILES = {"normal", "away"}
EXPECTED_NATIVE_RESOLUTION_MINUTES = 15
EXPECTED_NATIVE_SLOT_COUNT = 288
EXPECTED_PLANNER_RESOLUTION_MINUTES = 60
EXPECTED_PLANNER_HOUR_COUNT = 72
EXPECTED_QUARTERS_PER_HOUR = 4
EXPECTED_CONSUMER_SCOPE = "dummy_os_ems_planner"

_INVALID_STATES = {None, "", "unknown", "unavailable", "none", "None"}


def _aware_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _finite_non_negative(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0.0:
        return None
    return parsed


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _consumer_signature(
    *,
    profile: str,
    planner_start: str,
    planner_end: str,
    hours: list[dict[str, Any]],
) -> str:
    payload = {
        "contract_name": EXPECTED_CONTRACT_NAME,
        "contract_version": EXPECTED_CONTRACT_VERSION,
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "profile_contract_version": EXPECTED_PROFILE_CONTRACT_VERSION,
        "profile": profile,
        "planner_start": planner_start,
        "planner_end": planner_end,
        "hours": hours,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_forecast_contract_shadow(
    *,
    entity_state: Any,
    attributes: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate and normalize Forecast -> Planner Contract v1 in shadow only.

    The returned normalized hours are intentionally internal coordinator data.
    Step 1 never feeds them into Energy Need, Plan72, Bridge, Scheduler, Safety,
    or Execution and never publishes the full 72-hour array as sensor attributes.
    """
    attrs = dict(attributes or {})
    blockers: list[str] = []

    if entity_state in _INVALID_STATES:
        blockers.append("contract_entity_unavailable")

    if attrs.get("contract_name") != EXPECTED_CONTRACT_NAME:
        blockers.append("contract_name_mismatch")
    if attrs.get("contract_version") != EXPECTED_CONTRACT_VERSION:
        blockers.append("contract_version_mismatch")
    if attrs.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        blockers.append("schema_version_mismatch")
    if attrs.get("profile_contract_version") != EXPECTED_PROFILE_CONTRACT_VERSION:
        blockers.append("profile_contract_version_mismatch")
    if attrs.get("consumer_scope") != EXPECTED_CONSUMER_SCOPE:
        blockers.append("consumer_scope_mismatch")
    if attrs.get("physical_execution_authority") is not False:
        blockers.append("physical_execution_authority_not_false")

    profile = str(attrs.get("profile") or "unclassified")
    if profile not in SUPPORTED_PROFILES:
        blockers.append("profile_unclassified")

    if attrs.get("status") != "ready":
        blockers.append("producer_status_not_ready")
    if attrs.get("ready_for_planner") is not True:
        blockers.append("producer_not_ready_for_planner")
        for blocker in _list(attrs.get("blockers")):
            blockers.append(f"producer:{blocker}")

    if attrs.get("native_resolution_minutes") != EXPECTED_NATIVE_RESOLUTION_MINUTES:
        blockers.append("native_resolution_not_15")
    if attrs.get("native_slot_count") != EXPECTED_NATIVE_SLOT_COUNT:
        blockers.append("native_slot_count_not_288")
    if attrs.get("planner_resolution_minutes") != EXPECTED_PLANNER_RESOLUTION_MINUTES:
        blockers.append("planner_resolution_not_60")
    if attrs.get("planner_hour_count") != EXPECTED_PLANNER_HOUR_COUNT:
        blockers.append("planner_hour_count_not_72")
    if attrs.get("quarters_per_hour") != EXPECTED_QUARTERS_PER_HOUR:
        blockers.append("quarters_per_hour_not_4")
    if attrs.get("padding_used") is not False:
        blockers.append("padding_detected")
    if attrs.get("second_forecast_architecture") is not False:
        blockers.append("second_forecast_architecture_detected")

    planner_start_raw = attrs.get("planner_start")
    planner_end_raw = attrs.get("planner_end")
    planner_start = _aware_datetime(planner_start_raw)
    planner_end = _aware_datetime(planner_end_raw)
    if planner_start is None or planner_end is None:
        blockers.append("planner_window_invalid")
    elif (planner_end - planner_start).total_seconds() != EXPECTED_PLANNER_HOUR_COUNT * 3600:
        blockers.append("planner_window_not_72h")

    raw_hours = attrs.get("hours")
    normalized_hours: list[dict[str, Any]] = []
    previous_end: datetime | None = None
    if not isinstance(raw_hours, list):
        blockers.append("hours_missing")
        raw_hours = []
    elif len(raw_hours) != EXPECTED_PLANNER_HOUR_COUNT:
        blockers.append("planner_hour_count_not_72")

    for expected_index, hour in enumerate(raw_hours):
        if not isinstance(hour, dict):
            blockers.append(f"hour_{expected_index}_invalid")
            continue
        if hour.get("index") != expected_index:
            blockers.append(f"hour_{expected_index}_index_mismatch")
        if hour.get("quarter_count") != EXPECTED_QUARTERS_PER_HOUR:
            blockers.append(f"hour_{expected_index}_quarter_count_not_4")
        if hour.get("populated_quarters") != EXPECTED_QUARTERS_PER_HOUR:
            blockers.append(f"hour_{expected_index}_not_fully_populated")
        if str(hour.get("profile") or "unclassified") != profile:
            blockers.append(f"hour_{expected_index}_profile_mismatch")

        start_raw = hour.get("start")
        end_raw = hour.get("end")
        start = _aware_datetime(start_raw)
        end = _aware_datetime(end_raw)
        if start is None or end is None:
            blockers.append(f"hour_{expected_index}_timestamp_invalid")
        else:
            if (end - start).total_seconds() != 3600:
                blockers.append(f"hour_{expected_index}_duration_not_60m")
            if previous_end is not None and start != previous_end:
                blockers.append(f"hour_{expected_index}_not_contiguous")
            previous_end = end

        energy_kwh = _finite_non_negative(hour.get("energy_kwh"))
        if energy_kwh is None:
            blockers.append(f"hour_{expected_index}_energy_unavailable")
            continue

        normalized_hours.append(
            {
                "time": start_raw,
                "home_consumption_kwh": energy_kwh,
            }
        )

    if planner_start is not None and raw_hours:
        first_start = _aware_datetime(raw_hours[0].get("start")) if isinstance(raw_hours[0], dict) else None
        if first_start != planner_start:
            blockers.append("planner_start_mismatch")
    if planner_end is not None and raw_hours:
        last_end = _aware_datetime(raw_hours[-1].get("end")) if isinstance(raw_hours[-1], dict) else None
        if last_end != planner_end:
            blockers.append("planner_end_mismatch")

    blockers = list(dict.fromkeys(blockers))
    structural_ready = not blockers and len(normalized_hours) == EXPECTED_PLANNER_HOUR_COUNT

    runtime_input_status = attrs.get("runtime_input_status")
    forecast_operational_input_ok = attrs.get("forecast_operational_input_ok") is True
    runtime_blockers = [str(item) for item in _list(attrs.get("runtime_blockers"))]
    runtime_operational = forecast_operational_input_ok and not runtime_blockers

    if not structural_ready:
        shadow_status = "blocked"
        normalized_hours = []
    elif not runtime_operational:
        shadow_status = "runtime_blocked"
    else:
        shadow_status = "ready"

    total_energy_kwh = (
        round(sum(row["home_consumption_kwh"] for row in normalized_hours), 6)
        if structural_ready
        else None
    )
    minimum_energy_kwh = (
        round(min(row["home_consumption_kwh"] for row in normalized_hours), 6)
        if structural_ready and normalized_hours
        else None
    )
    maximum_energy_kwh = (
        round(max(row["home_consumption_kwh"] for row in normalized_hours), 6)
        if structural_ready and normalized_hours
        else None
    )
    signature = (
        _consumer_signature(
            profile=profile,
            planner_start=str(planner_start_raw),
            planner_end=str(planner_end_raw),
            hours=normalized_hours,
        )
        if structural_ready
        else None
    )

    return {
        "forecast_contract_shadow_status": shadow_status,
        "forecast_contract_shadow_structural_ready": structural_ready,
        "forecast_contract_shadow_runtime_operational": runtime_operational,
        "forecast_contract_shadow_entity": FORECAST_PLANNER_CONTRACT_ENTITY,
        "forecast_contract_shadow_contract_name": attrs.get("contract_name"),
        "forecast_contract_shadow_contract_version": attrs.get("contract_version"),
        "forecast_contract_shadow_schema_version": attrs.get("schema_version"),
        "forecast_contract_shadow_profile_contract_version": attrs.get("profile_contract_version"),
        "forecast_contract_shadow_profile": profile,
        "forecast_contract_shadow_producer_status": attrs.get("status"),
        "forecast_contract_shadow_producer_ready_for_planner": attrs.get("ready_for_planner") is True,
        "forecast_contract_shadow_producer_blockers": [str(item) for item in _list(attrs.get("blockers"))],
        "forecast_contract_shadow_runtime_input_status": runtime_input_status,
        "forecast_contract_shadow_forecast_operational_input_ok": forecast_operational_input_ok,
        "forecast_contract_shadow_runtime_blockers": runtime_blockers,
        "forecast_contract_shadow_planner_start": planner_start_raw,
        "forecast_contract_shadow_planner_end": planner_end_raw,
        "forecast_contract_shadow_planner_hour_count": len(normalized_hours) if structural_ready else 0,
        "forecast_contract_shadow_native_resolution_minutes": attrs.get("native_resolution_minutes"),
        "forecast_contract_shadow_native_slot_count": attrs.get("native_slot_count"),
        "forecast_contract_shadow_planner_resolution_minutes": attrs.get("planner_resolution_minutes"),
        "forecast_contract_shadow_quarters_per_hour": attrs.get("quarters_per_hour"),
        "forecast_contract_shadow_padding_used": attrs.get("padding_used"),
        "forecast_contract_shadow_second_forecast_architecture": attrs.get("second_forecast_architecture"),
        "forecast_contract_shadow_physical_execution_authority": attrs.get("physical_execution_authority"),
        "forecast_contract_shadow_total_72h_kwh": total_energy_kwh,
        "forecast_contract_shadow_min_hour_kwh": minimum_energy_kwh,
        "forecast_contract_shadow_max_hour_kwh": maximum_energy_kwh,
        "forecast_contract_shadow_consumer_signature": signature,
        "forecast_contract_shadow_blockers": blockers,
        "forecast_contract_shadow_hours": normalized_hours,
        "forecast_contract_shadow_only": True,
        "forecast_contract_shadow_plan72_source": False,
    }
