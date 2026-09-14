"""Dummy OS Energy Step 4 backed by the original EMS alpha76 preview."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from custom_components.dummy_os_data.ems_alpha76_adapter import (
    CHARGE_EFFICIENCY_PERCENT,
    DISCHARGE_EFFICIENCY_PERCENT,
    MAX_CHARGE_POWER_W,
    MINIMUM_TRADE_MARGIN,
    preview_public,
    run_preview,
)

DEFAULT_CHARGE_EFFICIENCY_PERCENT = CHARGE_EFFICIENCY_PERCENT
DEFAULT_DISCHARGE_EFFICIENCY_PERCENT = DISCHARGE_EFFICIENCY_PERCENT
DEFAULT_MINIMUM_TRADE_MARGIN = MINIMUM_TRADE_MARGIN
DEFAULT_MAX_CHARGE_POWER_W = MAX_CHARGE_POWER_W
DEFAULT_MAX_DISCHARGE_POWER_W = 3200
ENERGY_EPSILON_KWH = 0.01


def build_do_plan_preview(
    *,
    input_result: dict[str, Any],
    reserve_result: dict[str, Any],
    now: datetime,
    charge_efficiency_percent: float = DEFAULT_CHARGE_EFFICIENCY_PERCENT,
    discharge_efficiency_percent: float = DEFAULT_DISCHARGE_EFFICIENCY_PERCENT,
    minimum_trade_margin: float = DEFAULT_MINIMUM_TRADE_MARGIN,
    max_charge_power_w: int = DEFAULT_MAX_CHARGE_POWER_W,
    max_discharge_power_w: int = DEFAULT_MAX_DISCHARGE_POWER_W,
) -> dict[str, Any]:
    raw_need = reserve_result.get("alpha76_energy_need")
    if not isinstance(raw_need, dict):
        return {"status":"blocked","valid":False,"reason":"alpha76_energy_need_missing","blockers":["alpha76_energy_need_missing"],"preview_decision":"blocked","ems_policy_source":"0.0.1-alpha.76","shadow_only":True,"active_use_permitted":False,"physical_execution_authority":False}
    try:
        raw = run_preview(input_result=input_result, energy_need=raw_need, soc_percent=reserve_result.get("soc_percent"), charge_efficiency_percent=charge_efficiency_percent, discharge_efficiency_percent=discharge_efficiency_percent, minimum_trade_margin=minimum_trade_margin, max_charge_power_w=max_charge_power_w, now=now)
    except (TypeError, ValueError) as err:
        return {"status":"blocked","valid":False,"reason":str(err),"blockers":["alpha76_forecast_adapter_invalid"],"preview_decision":"blocked","ems_policy_source":"0.0.1-alpha.76","shadow_only":True,"active_use_permitted":False,"physical_execution_authority":False}
    result = preview_public(raw, input_result=input_result)
    result["soc_percent"] = reserve_result.get("soc_percent")
    result["reserve_source"] = "alpha76_energy_need"
    result["reserve_recalculated"] = False
    result["input_rows_signature"] = input_result.get("rows_signature")
    result["input_status"] = input_result.get("status")
    result["reserve_status"] = reserve_result.get("status")
    result["max_charge_power_w"] = int(max_charge_power_w)
    result["max_discharge_power_w"] = int(max_discharge_power_w)
    return result
