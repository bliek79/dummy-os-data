"""Native Energy Need with old-EMS full clock-hour solar qualification."""
from __future__ import annotations
from math import ceil
from typing import Any
from .planner_time_contract import STEP,expected_starts,finite,time_fields,utc


def build_native_energy_need(*,input_result:dict[str,Any],base:dict[str,Any],soc:float,
                            capacity:float,min_soc:float,reserve_percent:float) -> dict[str,Any]:
    contract=input_result["time_contract"]; slots=input_result.get("slots") or []
    base={**base,**time_fields(contract),"soc_percent":soc,
          "usable_solar_rule":"two full clock hours from native quarters; sum solar >= sum home and solar > 0",
          "energy_need_until_solar_kwh":None,"first_usable_solar":None,"available_battery_kwh":None,
          "safety_reserve_kwh":None,"required_including_reserve_kwh":None,"additional_grid_charge_kwh":None,
          "tradable_battery_kwh":None,"contributing_hours":0.0,"required_horizon_hours":None,
          "required_horizon_slots":None,"horizon_sufficient":False}
    try:
        aligned=len(slots)==288 and all(utc(s["start"])==t and utc(s["end"])==t+STEP for s,t in zip(slots,expected_starts(contract)))
    except (ValueError,KeyError,TypeError):
        aligned=False
    if not aligned:
        return {**base,"status":"blocked","valid":False,"reason":"native_need_time_window_invalid","blockers":["native_need_time_window_invalid"]}
    usable=None
    for i in range(len(slots)-7):
        if utc(slots[i]["start"]).minute!=0:
            continue
        windows=(slots[i:i+4],slots[i+4:i+8])
        if all(all(finite(s.get("home_kwh")) is not None and finite(s.get("solar_kwh")) is not None for s in group)
               and sum(s["solar_kwh"] for s in group)>0
               and sum(s["solar_kwh"] for s in group)+1e-12>=sum(s["home_kwh"] for s in group) for group in windows):
            usable=i
            break
    if usable is None:
        return {**base,"status":"waiting_for_usable_solar","valid":False,
                "reason":"no_two_consecutive_usable_solar_hours_within_horizon","blockers":["usable_solar_not_found"]}
    missing=[s["start"] for s in slots[:usable+8] if finite(s.get("home_kwh")) is None or finite(s.get("solar_kwh")) is None]
    if missing:
        return {**base,"status":"blocked","valid":False,"reason":"relevant_input_missing",
                "blockers":["required_home_solar_horizon_incomplete"],"first_missing":missing[0]}
    need=sum(max(s["home_kwh"]-s["solar_kwh"],0) for s in slots[:usable])
    available=capacity*max(soc-min_soc,0)/100
    reserve=capacity*reserve_percent/100
    required=need+reserve; extra=max(required-available,0)
    return {**base,"status":"ready","valid":True,"blockers":[],
            "reason":"additional_energy_required_for_need_plus_reserve" if extra>.01 else "battery_covers_need_plus_reserve",
            "soc_percent":round(soc,3),"energy_need_until_solar_kwh":round(need,3),"first_usable_solar":slots[usable]["start"],
            "available_battery_kwh":round(available,3),"safety_reserve_kwh":round(reserve,3),
            "required_including_reserve_kwh":round(required,3),"additional_grid_charge_kwh":round(extra,3),
            "tradable_battery_kwh":round(max(available-required,0),3),"contributing_hours":usable/4,
            "required_horizon_hours":ceil((usable+8)/4),"required_horizon_slots":usable+8,"horizon_sufficient":True}
