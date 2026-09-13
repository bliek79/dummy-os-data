"""Transport groups and clock-hour views derived from one native time axis."""
from __future__ import annotations
from collections import Counter
from datetime import timedelta
from typing import Any
from .planner_time_contract import expected_starts, time_fields, utc, STEP


def forecast_transport(slots: list[Any], *, profile: str, contract: dict[str, Any]) -> dict[str, Any]:
    starts = expected_starts(contract)
    if len(slots) != len(starts):
        raise ValueError("forecast_time_contract_slot_count_mismatch")
    for i, (slot, start) in enumerate(zip(slots, starts)):
        if utc(slot.start) != start or utc(slot.end) != start+STEP:
            raise ValueError(f"forecast_time_contract_slot_{i}_mismatch")
    hours = []
    for offset in range(0,len(slots),4):
        group = slots[offset:offset+4]
        populated = [s for s in group if s.energy_kwh is not None]
        supported = [s for s in group if s.source in {"weekday_quarter","day_type_quarter","quarter_of_day"}]
        hours.append({"index":len(hours),"start":group[0].start.isoformat(),"end":group[-1].end.isoformat(),
                      "energy_kwh":round(sum(s.energy_kwh for s in group),6) if len(populated)==4 else None,
                      "quarter_count":4,"populated_quarters":len(populated),"supported_quarters":len(supported),
                      "minimum_confidence":min((s.confidence for s in populated),default=None),
                      "average_confidence":sum(s.confidence for s in populated)/len(populated) if populated else None,
                      "source_distribution":dict(Counter(s.source for s in group)),"profile":profile,
                      "quarters":[{"index":i,"start":s.start.isoformat(),"end":s.end.isoformat(),
                                   "energy_kwh":s.energy_kwh,"source":s.source,"confidence":s.confidence}
                                  for i,s in enumerate(group)]})
    valid = sum(h["energy_kwh"] is not None for h in hours)
    return {**time_fields(contract),"status":"ok" if valid==72 else "partial","profile":profile,
            "model":"historical_baseline","model_version":"0.4","native_resolution_minutes":15,
            "native_public_slots":288,"planner_hour_count":72,"valid_hour_count":valid,"quarters_per_hour":4,
            "planner_start":contract["window_start"],"planner_end":contract["window_end"],
            "leading_quarter_offset":0,"extra_quarters_generated":0,"generated_quarter_count":288,
            "padding_used":False,"second_forecast_architecture":False,
            "hour_grouping":"window_relative_transport_not_apex","hours":hours}


FLOW_KEYS = ("home_kwh","solar_kwh","solar_to_home_kwh","solar_to_battery_kwh","solar_to_grid_kwh","grid_to_home_kwh",
             "grid_to_battery_kwh","grid_to_battery_safety_kwh","grid_to_battery_trade_kwh","battery_to_home_kwh","battery_to_grid_kwh")


def aggregate_clock_hours(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """UTC buckets keep repeated local DST hours separate. Partial edges stay partial."""
    grouped: dict[Any,list[dict[str,Any]]] = {}
    previous_end = None
    for slot in slots:
        start,end = utc(slot["start"]),utc(slot["end"])
        if end-start != STEP or (previous_end is not None and start!=previous_end):
            raise ValueError("apex_non_contiguous_native_slots")
        previous_end = end
        grouped.setdefault(start.replace(minute=0,second=0,microsecond=0),[]).append(slot)
    out = []
    for bucket,group in grouped.items():
        first,last = group[0],group[-1]
        duration = sum((utc(s["end"])-utc(s["start"])).total_seconds() for s in group)
        actions = list(dict.fromkeys(a for s in group for a in (s.get("action_parts") or []) if a!="baseline")) or ["baseline"]
        row = {"index":len(out),"start":first["start"],"end":last["end"],
               "bucket_start":bucket.isoformat(),"bucket_end":(bucket+timedelta(hours=1)).isoformat(),
               "coverage_minutes":duration/60.0,"partial_hour":len(group)!=4,"slot_count":len(group),
               "start_soc_percent":first["start_soc_percent"],"end_soc_percent":last["end_soc_percent"],
               "dynamic_reserve_start_soc_percent":first["dynamic_reserve_start_soc_percent"],
               "dynamic_reserve_end_soc_percent":last["dynamic_reserve_end_soc_percent"],
               "execution_reserve_start_soc_percent":first["execution_reserve_start_soc_percent"],
               "execution_reserve_end_soc_percent":last["execution_reserve_end_soc_percent"],
               "reserve_floor_soc_percent":last["dynamic_reserve_end_soc_percent"],
               "execution_floor_soc_percent":last["execution_reserve_end_soc_percent"],
               "dynamic_need_until_solar_kwh":first["dynamic_need_until_solar_kwh"],
               "dynamic_need_after_hour_kwh":last["dynamic_need_after_slot_kwh"],
               "next_usable_solar":first["next_usable_solar"],
               "solar_horizon_complete":all(s.get("solar_horizon_complete") is True for s in group),
               "execution_headroom_soc_percent":last["execution_headroom_soc_percent"],"action":"+".join(actions)}
        row.update({key:round(sum(s[key] for s in group),6) for key in FLOW_KEYS})
        for key in ("import_price","export_price"):
            row[key]=round(sum(s[key]*(utc(s["end"])-utc(s["start"])).total_seconds() for s in group)/duration,6)
        row["price_quarters"]=[{"start":s["start"],"end":s["end"],"import_price":s["import_price"],
                                "export_price":s["export_price"],"kind":s.get("price_kind"),
                                "fallback_used":s.get("price_fallback_used",False)} for s in group]
        out.append(row)
    return out
