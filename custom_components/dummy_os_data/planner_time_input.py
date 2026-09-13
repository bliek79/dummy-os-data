"""Validate the shared native input window, retaining missing slot positions."""
from __future__ import annotations
from collections import defaultdict
from typing import Any
from .planner_time_contract import STEP, expected_starts, finite, get, point_start, time_fields, utc

PRIORITY={"known_pt15m":30,"known_hourly_fallback":20,"forecast_hour":10}


def normalize_source(points:list[Any], *, price:bool) -> tuple[list[Any],dict[str,Any]]:
    grouped:dict[Any,list[Any]]=defaultdict(list)
    invalid=0
    for point in points:
        try:
            grouped[point_start(point)].append(point)
        except (ValueError,TypeError,OverflowError):
            invalid+=1
    selected=[]; conflicts=[]
    duplicates=sum(len(g)-1 for g in grouped.values())
    fields=("import_all_in","export_all_in","kind") if price else ("total_kwh",)
    for start,group in sorted(grouped.items()):
        if price:
            rank=max(PRIORITY.get(str(get(p,"kind")),0) for p in group)
            group=[p for p in group if PRIORITY.get(str(get(p,"kind")),0)==rank]
        values=[tuple(get(p,k) for k in fields) for p in group]
        if any(v!=values[0] for v in values[1:]):
            conflicts.append(start.isoformat())
        else:
            selected.append(group[0])
    return selected,{"duplicate_slots":duplicates,"conflicting_timestamps":conflicts,"invalid_timestamps":invalid}


def finalize_time_input(result:dict[str,Any],contract:dict[str,Any],source_audit:dict[str,Any]) -> dict[str,Any]:
    result.update(time_fields(contract))
    result.update(hour_grouping="window_relative_transport_not_apex",planner_resolution_minutes=15,
                  transport_resolution_minutes=60,source_time_audit=source_audit)
    starts=expected_starts(contract); rows=result.get("rows") or []
    if len(rows)!=72:
        result.update(time_alignment_valid=False,slots=[],native_valid_slot_count=0)
        return result
    slots=[]; errors=[]
    conflicts=set(source_audit["prices"]["conflicting_timestamps"])
    for i,row in enumerate(rows):
        for q in range(4):
            expected=starts[i*4+q]
            collections=[row.get(k) or [] for k in ("home_quarters","solar_quarters","price_quarters")]
            records=[items[q] if len(items)==4 else {} for items in collections]
            home,solar,price=records
            try:
                aligned=all(utc(r.get("start"))==expected for r in records) and utc(home.get("end"))==expected+STEP
            except (ValueError,TypeError,OverflowError):
                aligned=False
            if not aligned:
                errors.append(f"native_slot_{i*4+q}_timestamp_mismatch")
            if expected.isoformat() in conflicts:
                price.update(import_price=None,export_price=None,kind=None,fallback_used=False)
            hv=finite(home.get("kwh")); sv=finite(solar.get("kwh"))
            pv=finite(price.get("import_price")); ev=finite(price.get("export_price"))
            home_ok=hv is not None and hv>=0
            solar_ok=sv is not None and sv>=0
            price_ok=pv is not None and ev is not None
            slots.append({"index":i*4+q,"start":expected.isoformat(),"end":(expected+STEP).isoformat(),
                          "home_kwh":hv if home_ok and aligned else None,"solar_kwh":sv if solar_ok and aligned else None,
                          "import_price":pv if price_ok and aligned else None,"export_price":ev if price_ok and aligned else None,
                          "price_kind":price.get("kind"),"price_fallback_used":price.get("fallback_used",False),
                          "valid":aligned and home_ok and solar_ok and price_ok})
        group=slots[i*4:(i+1)*4]
        row["home_valid"]=row["home_quarters_valid"]=all(s["home_kwh"] is not None for s in group)
        row["solar_valid"]=all(s["solar_kwh"] is not None for s in group)
        row["price_valid"]=all(s["import_price"] is not None and s["export_price"] is not None for s in group)
        row["fully_valid"]=all(s["valid"] for s in group)
        row["price_interpolated"]=any(p.get("fallback_used") is True for p in row["price_quarters"])
        if not row["price_valid"]:
            row["import_price"]=row["export_price"]=None
    from .do_plan_input import _effective_horizon,_signature
    effective,first,reason,trailing=_effective_horizon(rows)
    result.update(slots=slots,time_alignment_valid=not errors,native_valid_slot_count=sum(s["valid"] for s in slots),
                  native_expected_slot_count=288,effective_horizon_hours=effective,
                  interpolated_price_slots=sum(q.get("fallback_used") is True for r in rows for q in r["price_quarters"]),
                  first_invalid_index=first,first_invalid_reason=reason,trailing_incomplete_only=trailing,
                  fully_valid_hours=sum(r["fully_valid"] for r in rows),
                  valid_through=rows[effective-1]["end"] if effective else None,rows_signature=_signature(rows))
    for kind in ("home","solar","price"):
        result[f"valid_{kind}_hours"]=sum(r[f"{kind}_valid"] for r in rows)
        result[f"missing_{kind}_hours"]=72-result[f"valid_{kind}_hours"]
        if result[f"missing_{kind}_hours"] and f"{kind}_hours_incomplete" not in result["blockers"]:
            result["blockers"].append(f"{kind}_hours_incomplete")
    if errors:
        result.update(status="blocked",blockers=sorted(set(result["blockers"]+errors)))
    elif result["fully_valid_hours"]<72 and result["status"] in {"ready","degraded"}:
        result["status"]="partial"
    return result
