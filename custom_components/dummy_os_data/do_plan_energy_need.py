"""Dummy OS Energy Step 2 backed by the original EMS alpha76 logic."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from custom_components.dummy_os_data.ems_alpha76_adapter import (
    BATTERY_CAPACITY_KWH,
    MIN_SOC_PERCENT,
    SOFTWARE_RESERVE_PERCENT,
    energy_need_public,
    run_energy_need,
)

DEFAULT_BATTERY_CAPACITY_KWH = BATTERY_CAPACITY_KWH
DEFAULT_MIN_SOC_PERCENT = MIN_SOC_PERCENT
DEFAULT_SAFETY_RESERVE_PERCENT = SOFTWARE_RESERVE_PERCENT
ENERGY_EPSILON_KWH = 0.01


def build_do_plan_energy_need(
    *,
    input_result: dict[str, Any],
    soc_percent: float | None,
    battery_capacity_kwh: float = DEFAULT_BATTERY_CAPACITY_KWH,
    min_soc_percent: float = DEFAULT_MIN_SOC_PERCENT,
    safety_reserve_percent: float = DEFAULT_SAFETY_RESERVE_PERCENT,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run alpha76 Energy Need on the new validated forecast transport."""
    if abs(float(battery_capacity_kwh) - BATTERY_CAPACITY_KWH) > 1e-9:
        return {"status":"blocked","valid":False,"reason":"alpha76_battery_capacity_mismatch","blockers":["alpha76_battery_capacity_mismatch"],"ems_policy_source":"0.0.1-alpha.76","shadow_only":True,"active_use_permitted":False,"physical_execution_authority":False}
    if abs(float(min_soc_percent) - MIN_SOC_PERCENT) > 1e-9:
        return {"status":"blocked","valid":False,"reason":"alpha76_min_soc_mismatch","blockers":["alpha76_min_soc_mismatch"],"ems_policy_source":"0.0.1-alpha.76","shadow_only":True,"active_use_permitted":False,"physical_execution_authority":False}
    try:
        raw = run_energy_need(input_result=input_result, soc_percent=soc_percent, safety_reserve_percent=safety_reserve_percent, now=now)
    except (TypeError, ValueError) as err:
        return {"status":"blocked","valid":False,"reason":str(err),"blockers":["alpha76_forecast_adapter_invalid"],"ems_policy_source":"0.0.1-alpha.76","shadow_only":True,"active_use_permitted":False,"physical_execution_authority":False}
    return energy_need_public(raw, input_result=input_result, soc_percent=soc_percent)
