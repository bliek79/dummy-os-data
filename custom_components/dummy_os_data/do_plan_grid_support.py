"""Observer-only Planner Step 5 grid-support trigger and economic charge window."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import math
from typing import Any

BATTERY_CAPACITY_KWH=7.2
MIN_SOC_PERCENT=5.0
SAFETY_RESERVE_PERCENT=7.0
EXECUTION_BUFFER_PERCENT=2.0
CHARGE_EFFICIENCY_PERCENT=92.0
DISCHARGE_EFFICIENCY_PERCENT=92.0
MAX_CHARGE_POWER_W=3200
MAX_DISCHARGE_POWER_W=3200
DEFAULT_GRID_CHARGE_TRIGGER_KWH=0.25
NATIVE_RESOLUTION_MINUTES=15
NATIVE_SLOT_COUNT=288
PLANNER_HOUR_COUNT=72
EPS=0.01
PRICE_TIE_EUR_PER_KWH=0.001


def _finite(value:Any,*,non_negative:bool=False)->float|None:
    try: n=float(value)
    except (TypeError,ValueError): return None
    if not math.isfinite(n) or (non_negative and n<0): return None
    return n


def _utc(value:Any)->datetime|None:
    if isinstance(value,datetime): p=value
    elif isinstance(value,str):
        try: p=datetime.fromisoformat(value)
        except ValueError: return None
    else: return None
    if p.tzinfo is None: return None
    return p.astimezone(timezone.utc)


def _base(input_result:dict[str,Any],trigger:float)->dict[str,Any]:
    effective=input_result.get('effective_horizon_hours')
    if not isinstance(effective,int): effective=PLANNER_HOUR_COUNT if input_result.get('fully_valid_hours')==PLANNER_HOUR_COUNT else 0
    return {
        'input_rows_signature':input_result.get('rows_signature'),
        'native_resolution_minutes':15,'native_slot_count':288,'planner_hour_count':72,
        'effective_horizon_hours':max(0,min(PLANNER_HOUR_COUNT,effective)),'valid_through':input_result.get('valid_through'),
        'battery_capacity_kwh':BATTERY_CAPACITY_KWH,'grid_charge_trigger_kwh':round(trigger,3),
        'trigger_rule':'grid_support_deficit_kwh > grid_charge_trigger_kwh',
        'charge_efficiency_percent':CHARGE_EFFICIENCY_PERCENT,'discharge_efficiency_percent':DISCHARGE_EFFICIENCY_PERCENT,
        'max_charge_power_w':MAX_CHARGE_POWER_W,'max_discharge_power_w':MAX_DISCHARGE_POWER_W,
        'shadow_only':True,'active_use_permitted':False,'physical_execution_authority':False,
        'plan_store_write':False,'scheduler_invoked':False,'safety_chain_invoked':False,'service_calls_performed':False,
        'missing_as_zero_used':False,'prices_fallback_used':bool(input_result.get('interpolated_price_slots',0)),'price_direction':'import_only','safety_priority_over_trade':True,
        'planning_role':'pre_solar_advice','authoritative_safety_plan':False,
    }


def _blocked(base, blockers):
    return {**base,'status':'blocked','valid':False,'reason':blockers[0],'blockers':sorted(set(blockers)),'grid_charge_triggered':False,'selected_charge_slots':[],'selected_charge_slot_count':0}


def _native_slots(rows:list[dict[str,Any]])->tuple[list[dict[str,Any]],list[str]]:
    slots=[]; blockers=[]
    expected_index=0
    for row in rows:
        homes=row.get('home_quarters'); solars=row.get('solar_quarters'); prices=row.get('price_quarters')
        if row.get('home_quarters_valid') is not True or not isinstance(homes,list) or len(homes)!=4:
            blockers.append(f'row_{row.get("index")}_home_quarters_invalid'); continue
        if not isinstance(solars,list) or len(solars)!=4 or not isinstance(prices,list) or len(prices)!=4:
            blockers.append(f'row_{row.get("index")}_native_quarters_invalid'); continue
        for q in range(4):
            h=homes[q]; s=solars[q]; p=prices[q]
            start=_utc(h.get('start') if isinstance(h,dict) else None)
            end=_utc(h.get('end') if isinstance(h,dict) else None)
            solar_start=_utc(s.get('start') if isinstance(s,dict) else None)
            price_start=_utc(p.get('start') if isinstance(p,dict) else None)
            home=_finite(h.get('kwh') if isinstance(h,dict) else None,non_negative=True)
            solar=_finite(s.get('kwh') if isinstance(s,dict) else None,non_negative=True)
            imp=_finite(p.get('import_price') if isinstance(p,dict) else None)
            exp=_finite(p.get('export_price') if isinstance(p,dict) else None)
            if None in (start,end,solar_start,price_start,home,solar,imp,exp) or start!=solar_start or start!=price_start or end-start!=timedelta(minutes=15):
                blockers.append(f'native_slot_{expected_index}_invalid'); expected_index+=1; continue
            slots.append({'index':expected_index,'start':start.isoformat(),'end':end.isoformat(),'home_kwh':home,'solar_kwh':solar,'import_price':imp,'export_price':exp,'source_resolution_minutes':p.get('source_resolution_minutes'),'kind':p.get('kind'),'price_interpolated':str(p.get('kind') or '').lower()=='interpolated'})
            expected_index+=1
    expected=len(rows)*4
    if len(slots)!=expected: blockers.append(f'native_slot_count_not_{expected}')
    return slots,sorted(set(blockers))


def _simulate(slots:list[dict[str,Any]], *, start_soc:float, charge_plan:dict[str,float]|None=None)->dict[str,Any]:
    stored=BATTERY_CAPACITY_KWH*start_soc/100.0
    floor=BATTERY_CAPACITY_KWH*(MIN_SOC_PERCENT+SAFETY_RESERVE_PERCENT+EXECUTION_BUFFER_PERCENT)/100.0
    ce=CHARGE_EFFICIENCY_PERCENT/100.0; de=DISCHARGE_EFFICIENCY_PERCENT/100.0
    max_in=MAX_CHARGE_POWER_W/1000.0*0.25; max_out=MAX_DISCHARGE_POWER_W/1000.0*0.25
    net_cost=0.0; import_cost=0.0; export_revenue=0.0; solar_to_batt_total=0.0; grid_to_batt_total=0.0; grid_to_home_total=0.0
    first_floor_need=None; timeline=[]
    for slot in slots:
        start_stored=stored; home=slot['home_kwh']; solar=slot['solar_kwh']; imp=slot['import_price']; exp=slot['export_price']
        solar_to_home=min(home,solar); rem_home=home-solar_to_home; surplus=solar-solar_to_home
        solar_input=min(surplus,max_in,max(0.0,(BATTERY_CAPACITY_KWH-stored)/ce)); solar_stored=solar_input*ce; stored+=solar_stored
        solar_to_batt_total+=solar_stored
        solar_to_grid=max(0.0,surplus-solar_input); export_revenue+=solar_to_grid*exp
        grid_headroom=max(0.0,max_in-solar_input)
        requested=(charge_plan or {}).get(slot['start'],0.0)
        grid_batt=min(requested,grid_headroom,max(0.0,(BATTERY_CAPACITY_KWH-stored)/ce)); stored+=grid_batt*ce; grid_to_batt_total+=grid_batt; import_cost+=grid_batt*imp
        available=max(0.0,(stored-floor)*de); batt_home=min(rem_home,max_out,available); stored-=batt_home/de
        grid_home=rem_home-batt_home; grid_to_home_total+=grid_home; import_cost+=grid_home*imp
        if grid_home>EPS and first_floor_need is None: first_floor_need=slot['end']
        stored=min(BATTERY_CAPACITY_KWH,max(0.0,stored)); net_cost=import_cost-export_revenue
        timeline.append({'start':slot['start'],'end':slot['end'],'start_soc_percent':round(start_stored/BATTERY_CAPACITY_KWH*100,3),'end_soc_percent':round(stored/BATTERY_CAPACITY_KWH*100,3),'grid_to_battery_kwh':round(grid_batt,6),'grid_to_home_kwh':round(grid_home,6),'solar_to_battery_stored_kwh':round(solar_stored,6),'solar_to_grid_kwh':round(solar_to_grid,6)})
    return {'end_soc_percent':round(stored/BATTERY_CAPACITY_KWH*100,3),'first_grid_support_need':first_floor_need,'import_cost_eur':round(import_cost,6),'export_revenue_eur':round(export_revenue,6),'net_grid_cost_eur':round(net_cost,6),'solar_to_battery_stored_kwh':round(solar_to_batt_total,6),'grid_to_battery_input_kwh':round(grid_to_batt_total,6),'grid_to_home_kwh':round(grid_to_home_total,6),'timeline':timeline}


def _handoff(reserve_result:dict[str,Any]|None, energy_need_result:dict[str,Any]|None, input_result:dict[str,Any])->tuple[float|None,float|None,datetime|None,str,list[str]]:
    blockers=[]
    if isinstance(reserve_result,dict) and reserve_result.get('status')=='ready' and reserve_result.get('valid') is True and reserve_result.get('grid_support_required') is True:
        if reserve_result.get('input_rows_signature')!=input_result.get('rows_signature'): blockers.append('reserve_input_signature_mismatch')
        return (_finite(reserve_result.get('grid_support_deficit_kwh'),non_negative=True),_finite(reserve_result.get('soc_percent'),non_negative=True),_utc(reserve_result.get('first_usable_solar')),'reserve_soc_grid_support_handoff',blockers)
    need=energy_need_result or {}
    if need.get('status')!='ready' or need.get('valid') is not True: blockers.append('energy_need_not_ready')
    if need.get('input_rows_signature')!=input_result.get('rows_signature'): blockers.append('input_signature_mismatch')
    return (_finite(need.get('additional_grid_charge_kwh'),non_negative=True),_finite(need.get('soc_percent'),non_negative=True),_utc(need.get('first_usable_solar')),'energy_need_fallback',blockers)


def _legacy_build_do_plan_grid_support(*,input_result:dict[str,Any],energy_need_result:dict[str,Any]|None=None,reserve_result:dict[str,Any]|None=None,trigger_kwh:float=DEFAULT_GRID_CHARGE_TRIGGER_KWH)->dict[str,Any]:
    trigger=_finite(trigger_kwh,non_negative=True); base=_base(input_result,trigger if trigger is not None else DEFAULT_GRID_CHARGE_TRIGGER_KWH); blockers=[]
    if trigger is None: blockers.append('grid_charge_trigger_invalid')
    if input_result.get('status') not in {'ready','runtime_blocked','degraded','partial'}: blockers.append('planner_input_not_structurally_available')
    all_rows=input_result.get('rows'); effective=base['effective_horizon_hours']
    raw,soc,first_solar,handoff_source,handoff_blockers=_handoff(reserve_result,energy_need_result,input_result)
    blockers.extend(handoff_blockers)
    if not isinstance(all_rows,list) or len(all_rows)!=72: blockers.append('rows_not_exactly_72')
    if effective<=0: blockers.append('effective_horizon_empty')
    if raw is None: blockers.append('grid_support_deficit_invalid')
    if soc is None or soc>100: blockers.append('soc_invalid')
    if first_solar is None: blockers.append('first_usable_solar_invalid')
    if blockers: return _blocked({**base,'handoff_source':handoff_source},blockers)
    assert trigger is not None and raw is not None and soc is not None and first_solar is not None and isinstance(all_rows,list)
    rows=all_rows[:effective]
    if any(not isinstance(row,dict) or row.get('fully_valid') is not True for row in rows): return _blocked({**base,'handoff_source':handoff_source},['invalid_row_inside_effective_horizon'])
    slots,native_blockers=_native_slots(rows)
    if native_blockers: return _blocked({**base,'handoff_source':handoff_source},native_blockers)

    ce=CHARGE_EFFICIENCY_PERCENT/100.0
    required_input=raw/ce if raw>EPS else 0.0
    triggered=raw>trigger
    current_free_capacity=BATTERY_CAPACITY_KWH*max(100.0-soc,0.0)/100.0
    target_soc=min(100.0,soc+(min(raw,current_free_capacity)/BATTERY_CAPACITY_KWH*100.0))
    common={**base,'handoff_source':handoff_source,'additional_grid_charge_kwh':round(raw,3),'grid_support_deficit_battery_kwh':round(raw,3),'grid_charge_triggered':triggered,'chargeable_deficit_battery_kwh':round(raw,3),'unavoidable_shortfall_battery_kwh':0.0,'required_grid_charge_input_kwh':round(required_input,3),'target_soc_after_safety_charge_percent':round(target_soc,3),'capacity_limited_shortfall':False,'first_usable_solar':first_solar.isoformat(),'soc_percent':round(soc,3),'feasibility_basis':'dynamic_pre_solar_charge_window','effective_native_slot_count':len(slots)}
    result_status='degraded' if effective<PLANNER_HOUR_COUNT else 'ready'
    if not triggered:
        return {**common,'status':result_status,'valid':True,'reason':'below_trigger','trigger_reason':'below_trigger','blockers':[],'grid_charge_deadline':None,'eligible_charge_slot_count':0,'selected_charge_slots':[],'selected_charge_slot_count':0,'selected_charge_input_kwh_total':0.0,'selected_charge_stored_kwh_total':0.0,'weighted_average_import_price':None,'effective_stored_cost_per_kwh':None,'candidate_charge_cost_eur':0.0,'baseline_grid_support_cost_eur':0.0,'candidate_72h_net_cost_eur':None,'economic_delta_eur':0.0,'solar_displacement_kwh':0.0,'safety_charge_fully_allocated':True,'unallocated_chargeable_deficit_battery_kwh':0.0}

    baseline=_simulate(slots,start_soc=soc)
    deadline=first_solar
    eligible=[slot for slot in slots if (_utc(slot['start']) is not None and _utc(slot['start'])<deadline)]
    def key(slot):
        surplus=max(slot['solar_kwh']-slot['home_kwh'],0.0)
        return (round(slot['import_price']/PRICE_TIE_EUR_PER_KWH),surplus,-_utc(slot['start']).timestamp())
    eligible.sort(key=key)
    max_slot_input=MAX_CHARGE_POWER_W/1000.0*0.25
    plan:dict[str,float]={}
    previous_actual=0.0
    for slot in eligible:
        if previous_actual*ce+1e-6>=raw: break
        solar_surplus=max(slot['solar_kwh']-slot['home_kwh'],0.0)
        request=min(max(0.0,max_slot_input-solar_surplus), max(0.0,required_input-previous_actual))
        if request<=1e-9: continue
        plan[slot['start']]=request
        candidate=_simulate(slots,start_soc=soc,charge_plan=plan)
        actual=candidate['grid_to_battery_input_kwh']
        if actual<=previous_actual+1e-9:
            plan.pop(slot['start'],None); continue
        previous_actual=actual

    candidate=_simulate(slots,start_soc=soc,charge_plan=plan)
    actual_input=candidate['grid_to_battery_input_kwh']; actual_stored=actual_input*ce
    unallocated=max(raw-actual_stored,0.0); fully=unallocated<=EPS
    timeline_by_start={item['start']:item for item in candidate['timeline']}
    selected=[]
    for slot in eligible:
        item=timeline_by_start.get(slot['start'])
        actual_slot=_finite(item.get('grid_to_battery_kwh') if isinstance(item,dict) else None,non_negative=True) or 0.0
        if actual_slot<=EPS: continue
        stored=actual_slot*ce
        selected.append({'start':slot['start'],'end':slot['end'],'import_price_all_in':round(slot['import_price'],6),'available_charge_input_kwh':round(MAX_CHARGE_POWER_W/1000.0*0.25-max(slot['solar_kwh']-slot['home_kwh'],0.0),6),'allocated_charge_input_kwh':round(actual_slot,6),'stored_battery_kwh':round(stored,6),'selection_reason':'lowest_import_price_with_dynamic_battery_headroom','source_resolution_minutes':slot.get('source_resolution_minutes'),'kind':slot.get('kind'),'price_interpolated':slot.get('price_interpolated',False)})
    solar_displacement=max(0.0,baseline['solar_to_battery_stored_kwh']-candidate['solar_to_battery_stored_kwh'])
    charge_cost=sum(item['allocated_charge_input_kwh']*item['import_price_all_in'] for item in selected)
    selected_input=sum(item['allocated_charge_input_kwh'] for item in selected)
    weighted=(charge_cost/selected_input) if selected_input>EPS else None
    effective_cost=(weighted/ce) if weighted is not None else None
    if not fully:
        status='infeasible'; reason='safe_charge_window_capacity_insufficient'; output_blockers=['safe_charge_window_capacity_insufficient']
    else:
        status=result_status; reason='grid_support_charge_window_sufficient'; output_blockers=[]
    return {**common,'status':status,'valid':fully,'reason':reason,'trigger_reason':'meaningful_shortfall','blockers':output_blockers,'grid_charge_deadline':deadline.isoformat(),'eligible_charge_slot_count':len(eligible),'selected_charge_slots':selected,'selected_charge_slot_count':len(selected),'selected_charge_input_kwh_total':round(actual_input,3),'selected_charge_stored_kwh_total':round(actual_stored,3),'weighted_average_import_price':round(weighted,6) if weighted is not None else None,'effective_stored_cost_per_kwh':round(effective_cost,6) if effective_cost is not None else None,'candidate_charge_cost_eur':round(charge_cost,4),'baseline_grid_support_cost_eur':round(baseline['net_grid_cost_eur'],4),'candidate_72h_net_cost_eur':round(candidate['net_grid_cost_eur'],4),'economic_delta_eur':round(candidate['net_grid_cost_eur']-baseline['net_grid_cost_eur'],4),'solar_displacement_kwh':round(solar_displacement,3),'safety_charge_fully_allocated':fully,'unallocated_chargeable_deficit_battery_kwh':round(unallocated,3),'baseline_end_soc_percent':baseline['end_soc_percent'],'candidate_end_soc_percent':candidate['end_soc_percent'],'source_resolution_minutes_seen':sorted({slot['source_resolution_minutes'] for slot in selected if slot['source_resolution_minutes'] is not None}),'candidate_resimulation_performed':True}


def build_do_plan_grid_support(**kwargs: Any) -> dict[str, Any]:
    from custom_components.dummy_os_data.planner_time_contract import propagate_time, window_errors
    sources = [kwargs["input_result"]]
    for key in ("energy_need_result", "reserve_result"):
        if kwargs.get(key) is not None:
            sources.append(kwargs[key])
    errors = window_errors(*sources)
    result = {"status": "blocked", "valid": False, "blockers": errors, "selected_charge_slots": []} if errors else _legacy_build_do_plan_grid_support(**kwargs)
    return propagate_time(result, *sources)
