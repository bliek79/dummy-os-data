"""Verify 15-minute presentation never changes the alpha76 hourly authority."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
from custom_components.dummy_os_data.ems_alpha76_adapter import plan72_public

BASE=datetime(2026,9,14,10,0,tzinfo=timezone.utc)


def _raw_plan():
    rows=[]
    for i in range(72):
        rows.append({
            "time":(BASE+timedelta(hours=i)).isoformat(),
            "action":"geen_actie",
            "solar_kwh":0.8+i*0.001,
            "home_consumption_kwh":0.4+i*0.001,
            "charge_from_grid_kwh":0.24 if i==0 else 0.0,
            "charge_from_grid_safety_kwh":0.16 if i==0 else 0.0,
            "charge_from_grid_trade_kwh":0.08 if i==0 else 0.0,
            "discharge_to_grid_kwh":0.12 if i==1 else 0.0,
            "discharge_to_home_kwh":0.20 if i==2 else 0.0,
            "grid_import_for_home_kwh":0.10 if i==3 else 0.0,
            "solar_export_kwh":0.30 if i==4 else 0.0,
            "soc_start":40.0+i*0.1,
            "soc_end":40.1+i*0.1,
        })
    return {
        "auto_plan_72h_valid":True,"auto_plan_72h_reason":"ready",
        "auto_plan_72h_plan":rows,"auto_plan_72h_start_soc":40.0,
        "auto_plan_72h_end_soc":47.2,"auto_plan_72h_min_soc":40.0,
        "auto_plan_72h_max_soc":47.2,"auto_plan_72h_execution_buffer_percent":2.0,
        "auto_plan_72h_execution_buffer_safe":True,
        "auto_plan_72h_execution_buffer_breach_hours":0,
        "auto_plan_72h_min_execution_headroom_soc":3.0,
    }


def test_public_contract_has_72_authoritative_hours_and_288_display_slots():
    out=plan72_public(_raw_plan(),input_result={"time_contract":{"window_start":BASE.isoformat()}})
    assert out["hour_count"]==72
    assert len(out["hours"])==72
    assert out["slot_count"]==288
    assert len(out["slots"])==288
    assert out["safety_plan_authority"]=="alpha76_plan72"
    assert out["physical_execution_authority"] is False


@pytest.mark.parametrize("hour_index",[0,1,2,3,4,17,71])
def test_four_display_slots_preserve_each_alpha76_hour_energy(hour_index):
    out=plan72_public(_raw_plan(),input_result={"time_contract":{"window_start":BASE.isoformat()}})
    hour=out["hours"][hour_index]
    slots=out["slots"][hour_index*4:(hour_index+1)*4]
    mapping={
        "solar_kwh":"solar_kwh",
        "home_consumption_kwh":"home_kwh",
        "charge_from_grid_kwh":"grid_to_battery_kwh",
        "charge_from_grid_safety_kwh":"grid_to_battery_safety_kwh",
        "charge_from_grid_trade_kwh":"grid_to_battery_trade_kwh",
        "discharge_to_grid_kwh":"battery_to_grid_kwh",
        "discharge_to_home_kwh":"battery_to_home_kwh",
        "grid_import_for_home_kwh":"grid_to_home_kwh",
        "solar_export_kwh":"solar_to_grid_kwh",
    }
    for old_key,new_key in mapping.items():
        assert sum(float(s[new_key]) for s in slots)==pytest.approx(float(hour[old_key]),abs=0.000004)


def test_display_slots_are_never_execution_authority():
    out=plan72_public(_raw_plan(),input_result={"time_contract":{"window_start":BASE.isoformat()}})
    assert all(s["derived_from_alpha76_hourly_decision"] is True for s in out["slots"])
    assert all(s["authoritative_for_execution"] is False for s in out["slots"])
