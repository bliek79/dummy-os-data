"""Explicit shadow-only SOC projection; never a measured future SOC."""
from __future__ import annotations
from typing import Any
from .planner_time_contract import finite, validate_time_contract


def project_soc_to_window(*, contract: dict[str, Any], soc: Any,
                          charge_power_w: Any, discharge_power_w: Any,
                          capacity_kwh: float = 7.2, charge_efficiency: float = .92,
                          discharge_efficiency: float = .92) -> dict[str, Any]:
    errors = validate_time_contract(contract)
    measured, charge, discharge = map(finite, (soc, charge_power_w, discharge_power_w))
    capacity, ce, de = map(finite, (capacity_kwh, charge_efficiency, discharge_efficiency))
    if measured is None or not 0 <= measured <= 100:
        errors.append("soc_bridge_soc_invalid")
    if capacity is None or capacity <= 0 or ce is None or de is None or not 0 < ce <= 1 or not 0 < de <= 1:
        errors.append("soc_bridge_parameters_invalid")
    duration = contract.get("bridge_seconds")
    if duration != 0:
        if charge is None or discharge is None or charge < 0 or discharge < 0:
            errors.append("soc_bridge_power_unavailable")
        elif charge > 3200 or discharge > 3200 or (charge > 25 and discharge > 25):
            errors.append("soc_bridge_power_inconsistent")
    result = {"valid": not errors, "blockers": sorted(set(errors)),
              "method": "live_ac_power_constant_until_window_start", "is_estimate": duration != 0,
              "physical_execution_authority": False, "observed_at": contract.get("reference_utc"),
              "projected_at": contract.get("window_start"), "duration_seconds": duration,
              "measured_soc_percent": measured, "charge_power_w": charge, "discharge_power_w": discharge,
              "assumption": "reported SOC at snapshot reference; constant reported AC power until next boundary",
              "planner_start_soc_percent": None, "stored_energy_delta_kwh": None}
    if errors:
        return result
    delta = 0.0 if duration == 0 else (charge*ce-discharge/de)*duration/3600000.0
    initial = capacity*measured/100.0
    # Preserve a below-minimum measurement; never invent charge to reach 5%.
    projected = min(capacity, max(min(initial, capacity*.05), initial+delta))
    result.update(planner_start_soc_percent=projected/capacity*100.0,
                  stored_energy_delta_kwh=projected-initial,
                  unconstrained_stored_energy_delta_kwh=delta,
                  capacity_or_device_floor_limited=abs(projected-initial-delta)>1e-9)
    return result
