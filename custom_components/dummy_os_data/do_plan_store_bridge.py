"""Translate validated Step-5 results into Step-6 shadow Plan Store candidates."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
from typing import Any

CAPACITY_KWH = 7.2
CHARGE_EFFICIENCY = 0.92
DISCHARGE_EFFICIENCY = 0.92
MAX_POWER_W = 3200
MIN_ENERGY_KWH = 0.01
MAX_CANDIDATES = 3

_REASON_PRIORITY = {"grid_support": 0, "safety_charge": 1, "trade_charge": 2, "trade_discharge": 3}


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime): parsed = value
    elif isinstance(value, str):
        try: parsed = datetime.fromisoformat(value)
        except ValueError: return None
    else: return None
    if parsed.tzinfo is None: return None
    return parsed.astimezone(timezone.utc)


def _finite(value: Any, *, non_negative: bool = False) -> float | None:
    try: number = float(value)
    except (TypeError, ValueError): return None
    if not math.isfinite(number) or (non_negative and number < 0): return None
    return number


def _round_power_up(value: float) -> int:
    if value <= 0: return 0
    return min(MAX_POWER_W, max(100, int(math.ceil(value / 10.0) * 10)))


def _identity(action: str, reason: str, starts: list[str], end: str) -> str:
    return "|".join((action, reason, ",".join(starts), end))


def _signature(identity: str, energy: float, target_soc: float | None) -> str:
    raw = f"{identity}|{energy:.3f}|{target_soc if target_soc is not None else 'none'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _candidate_id(identity: str) -> str:
    return f"step6-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]}"


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_start=_utc(a.get("start_time")); a_end=_utc(a.get("planned_end_time")); b_start=_utc(b.get("start_time")); b_end=_utc(b.get("planned_end_time"))
    if None in (a_start,a_end,b_start,b_end): return False
    return a_start < b_end and b_start < a_end


def _build_candidate(*, action: str, reason: str, starts: list[str], start: datetime, end: datetime, energy_kwh: float, start_soc: float | None, target_soc: float | None = None, source: str) -> dict[str, Any] | None:
    duration_h=(end-start).total_seconds()/3600.0
    if duration_h<=0 or energy_kwh<=MIN_ENERGY_KWH: return None
    required_power=energy_kwh*1000.0/duration_h
    if required_power>MAX_POWER_W+1: return None
    power_w=_round_power_up(required_power)
    if target_soc is None and start_soc is not None:
        if action=="charge": target_soc=min(100.0,start_soc+energy_kwh*CHARGE_EFFICIENCY/CAPACITY_KWH*100.0)
        else: target_soc=max(5.0,start_soc-energy_kwh/DISCHARGE_EFFICIENCY/CAPACITY_KWH*100.0)
    identity=_identity(action,reason,starts,end.isoformat()); signature=_signature(identity,energy_kwh,target_soc)
    return {"candidate_id":_candidate_id(identity),"planner_identity":identity,"planner_signature":signature,"action":action,"reason":reason,"start_time":start.isoformat(),"planned_end_time":end.isoformat(),"max_runtime_minutes":round(duration_h*60.0,3),"max_start_delay_minutes":10.0,"power_w":power_w,"planned_energy_kwh":round(energy_kwh,6),"target_soc_percent":round(target_soc,3) if target_soc is not None else None,"source":source,"shadow_only":True}


def _plan72_segments(plan72_result: dict[str, Any]) -> list[dict[str, Any]]:
    if plan72_result.get("status") not in {"ready","infeasible"}: return []
    rows=plan72_result.get("hours")
    if not isinstance(rows,list): return []
    prepared=[]
    for raw in rows:
        if not isinstance(raw,dict): continue
        start=_utc(raw.get("start")); end=_utc(raw.get("end"))
        if start is None or end is None or end<=start: continue
        marker=str(raw.get("action") or "baseline"); grid_charge=_finite(raw.get("grid_to_battery_kwh"),non_negative=True) or 0.0; grid_discharge=_finite(raw.get("battery_to_grid_kwh"),non_negative=True) or 0.0
        if marker=="trade_charge" and grid_charge>MIN_ENERGY_KWH: action,reason,energy="charge","trade_charge",grid_charge
        elif marker=="trade_discharge" and grid_discharge>MIN_ENERGY_KWH: action,reason,energy="discharge","trade_discharge",grid_discharge
        elif grid_charge>MIN_ENERGY_KWH: action,reason,energy="charge","safety_charge",grid_charge
        else: continue
        prepared.append({"start":start,"end":end,"action":action,"reason":reason,"energy":energy,"start_soc":_finite(raw.get("start_soc_percent"),non_negative=True),"source_start":start.isoformat()})
    prepared.sort(key=lambda row:row["start"]); segments=[]
    for row in prepared:
        if not segments: segments.append([row]); continue
        previous=segments[-1][-1]
        if row["start"]==previous["end"] and row["action"]==previous["action"] and row["reason"]==previous["reason"]: segments[-1].append(row)
        else: segments.append([row])
    candidates=[]
    for segment in segments:
        candidate=_build_candidate(action=segment[0]["action"],reason=segment[0]["reason"],starts=[row["source_start"] for row in segment],start=segment[0]["start"],end=segment[-1]["end"],energy_kwh=sum(float(row["energy"]) for row in segment),start_soc=segment[0]["start_soc"],source="do_plan_72h")
        if candidate is not None: candidates.append(candidate)
    return candidates


def _grid_support_segments(grid_support_result: dict[str, Any]) -> list[dict[str, Any]]:
    if grid_support_result.get("status")!="ready" or grid_support_result.get("valid") is not True or grid_support_result.get("grid_charge_triggered") is not True: return []
    rows=grid_support_result.get("selected_charge_slots")
    if not isinstance(rows,list): return []
    prepared=[]
    for raw in rows:
        if not isinstance(raw,dict): continue
        start=_utc(raw.get("start")); end=_utc(raw.get("end")); energy=_finite(raw.get("allocated_charge_input_kwh"),non_negative=True); target=_finite(raw.get("projected_soc_after_percent"),non_negative=True)
        if start is None or end is None or energy is None or energy<=MIN_ENERGY_KWH: continue
        prepared.append({"start":start,"end":end,"energy":energy,"target":target,"source_start":start.isoformat()})
    prepared.sort(key=lambda row:row["start"]); segments=[]
    for row in prepared:
        if not segments or row["start"]!=segments[-1][-1]["end"]: segments.append([row])
        else: segments[-1].append(row)
    candidates=[]
    for segment in segments:
        candidate=_build_candidate(action="charge",reason="grid_support",starts=[row["source_start"] for row in segment],start=segment[0]["start"],end=segment[-1]["end"],energy_kwh=sum(float(row["energy"]) for row in segment),start_soc=_finite(grid_support_result.get("soc_percent"),non_negative=True),target_soc=segment[-1]["target"],source="do_plan_grid_support")
        if candidate is not None: candidates.append(candidate)
    return candidates


def _native_plan72_segments(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Only validated native allocations may reach the shadow store.

    Do not widen a :15 charge to an hour or merge different power requests into
    an invented constant-power action. Hourly aggregation is for Apex only.
    """
    if result.get("status") not in {"ready", "degraded"} or result.get("valid") is not True:
        return []
    prepared = []
    for row in result.get("slots") or []:
        start = _utc(row.get("start")); end = _utc(row.get("end"))
        if start is None or end is None or (end-start).total_seconds() != 900:
            continue
        charge = _finite(row.get("grid_to_battery_kwh"), non_negative=True) or 0.0
        discharge = _finite(row.get("battery_to_grid_kwh"), non_negative=True) or 0.0
        safety = _finite(row.get("grid_to_battery_safety_kwh"), non_negative=True) or 0.0
        flows = [("charge", "safety_charge" if safety > MIN_ENERGY_KWH else "trade_charge", charge),
                 ("discharge", "trade_discharge", discharge)]
        for action, reason, energy in flows:
            if energy <= MIN_ENERGY_KWH:
                continue
            prepared.append({"start": start, "end": end, "energy": energy,
                             "action": action, "reason": reason,
                             "power": _round_power_up(energy * 4000.0),
                             "start_soc": _finite(row.get("start_soc_percent")),
                             "target": _finite(row.get("end_soc_percent"))})
    prepared.sort(key=lambda row: (row["start"], row["reason"]))
    segments = []
    for row in prepared:
        previous = segments[-1][-1] if segments else None
        if (previous and previous["end"] == row["start"]
                and all(previous[key] == row[key] for key in ("action", "reason", "power"))):
            segments[-1].append(row)
        else:
            segments.append([row])
    candidates = []
    for group in segments:
        candidate = _build_candidate(
            action=group[0]["action"], reason=group[0]["reason"],
            starts=[row["start"].isoformat() for row in group],
            start=group[0]["start"], end=group[-1]["end"],
            energy_kwh=sum(row["energy"] for row in group),
            start_soc=group[0]["start_soc"], target_soc=group[-1]["target"],
            source="do_plan_72h",
        )
        if candidate is not None:
            candidate["source_resolution_minutes"] = 15
            candidates.append(candidate)
    return candidates


def build_do_plan_store_bridge(*,plan72_result:dict[str,Any],grid_support_result:dict[str,Any],now:datetime)->dict[str,Any]:
    """Build at most three deterministic candidates with safety-first arbitration."""
    now_utc=_utc(now)
    base={"shadow_only":True,"shadow_store_write":True,"operational_plan_store_write":False,"active_use_permitted":False,"physical_execution_authority":False,"scheduler_invoked":False,"safety_chain_invoked":False,"service_calls_performed":False,"max_candidates":MAX_CANDIDATES}
    if now_utc is None: return {**base,"status":"blocked","valid":False,"reason":"now_invalid","candidates":[],"suppressed_candidates":[],"blockers":["now_invalid"]}
    native_authority = plan72_result.get("safety_plan_authority") == "plan72_native"
    grid_candidates=_grid_support_segments(grid_support_result); suppressed=[]
    if native_authority:
        plan_candidates = _native_plan72_segments(plan72_result)
        for candidate in grid_candidates:
            suppressed.append({"candidate_id": candidate["candidate_id"],
                               "reason": "advisory_only_native_plan_authoritative", "source": candidate["source"]})
        grid_candidates = []
    else:
        plan_candidates = _plan72_segments(plan72_result)
    # Grid Support is the economic replacement for the older hourly safety-charge
    # placement. When it is valid/triggered, carrying both would double-count the
    # same reserve shortage even when their selected times do not overlap.
    if grid_candidates:
        retained=[]
        for candidate in plan_candidates:
            if candidate.get("reason")=="safety_charge": suppressed.append({"candidate_id":candidate.get("candidate_id"),"reason":"superseded_by_grid_support","source":candidate.get("source")})
            else: retained.append(candidate)
        plan_candidates=retained
    raw=[*grid_candidates,*plan_candidates]
    raw.sort(key=lambda item:(_REASON_PRIORITY.get(str(item.get("reason")),99),_utc(item.get("start_time")) or now_utc)); selected=[]
    for candidate in raw:
        start=_utc(candidate.get("start_time"))
        if start is None or start<=now_utc: suppressed.append({"candidate_id":candidate.get("candidate_id"),"reason":"candidate_not_future","source":candidate.get("source")}); continue
        if any(_overlap(candidate,current) for current in selected): suppressed.append({"candidate_id":candidate.get("candidate_id"),"reason":"overlap_lower_priority","source":candidate.get("source")}); continue
        selected.append(candidate)
    selected.sort(key=lambda item:_utc(item.get("start_time")) or now_utc); overflow=selected[MAX_CANDIDATES:]; selected=selected[:MAX_CANDIDATES]
    for candidate in overflow: suppressed.append({"candidate_id":candidate.get("candidate_id"),"reason":"store_capacity_three","source":candidate.get("source")})
    return {**base,"status":"ready","valid":True,"reason":"shadow_candidates_built","candidate_count":len(selected),"candidates":selected,"suppressed_candidate_count":len(suppressed),"suppressed_candidates":suppressed,"plan72_status":plan72_result.get("status"),"grid_support_status":grid_support_result.get("status"),"candidate_authority":"plan72_native" if native_authority else "legacy_contract","blockers":[]}
