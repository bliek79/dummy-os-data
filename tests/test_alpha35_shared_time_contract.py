"""Behavioral regressions of production time-contract path and legacy compatibility."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import ast
import pytest
from custom_components.dummy_os_data.planner_time_contract import STEP,build_time_contract,expected_starts,validate_time_contract,window_errors,utc
from custom_components.dummy_os_data.planner_time_views import forecast_transport,aggregate_clock_hours,FLOW_KEYS
from custom_components.dummy_os_data.planner_soc_bridge import project_soc_to_window
from custom_components.dummy_os_data.forecast_planner_contract import build_forecast_planner_contract
from custom_components.dummy_os_data.do_plan_input import build_do_plan_input_72h
from custom_components.dummy_os_data.do_plan_energy_need import build_do_plan_energy_need
from custom_components.dummy_os_data.do_plan_reserve_soc import build_do_plan_reserve_soc
from custom_components.dummy_os_data.do_plan_preview import build_do_plan_preview
from custom_components.dummy_os_data.do_plan_grid_support import build_do_plan_grid_support
from custom_components.dummy_os_data.do_plan_72h import build_do_plan_72h
from custom_components.dummy_os_data.do_plan_native_common import _find_next_usable_solar
UTC=timezone.utc
AMS=ZoneInfo('Europe/Amsterdam')
ROOT=Path(__file__).parents[1]

@dataclass
class HomeSlot:
    start:datetime
    end:datetime
    energy_kwh:float|None
    source:str='weekday_quarter'
    confidence:float=.8


def inputs(reference,*,missing_price=None,missing_solar=None,duplicate_price=None):
    contract=build_time_contract(reference); starts=expected_starts(contract)
    transport=forecast_transport([HomeSlot(s,s+STEP,.05) for s in starts],profile='normal',contract=contract)
    fc=build_forecast_planner_contract(planner_hours=transport,model_health={'readiness_status':'strong','profile':'normal',
        'runtime_input_status':'available','forecast_operational_input_ok':True,'runtime_blockers':[]})
    solar=[SimpleNamespace(start=s,total_kwh=.08) for i,s in enumerate(starts) if i!=missing_solar]
    prices=[SimpleNamespace(start=s,import_all_in=.2,export_all_in=.1,kind='known_pt15m',source_resolution_minutes=15)
            for i,s in enumerate(starts) if i!=missing_price]
    if duplicate_price is not None:
        prices.append(SimpleNamespace(start=starts[duplicate_price],import_all_in=.9,export_all_in=.8,kind='known_pt15m',source_resolution_minutes=15))
    result=build_do_plan_input_72h(contract=fc,solar_points=solar,price_points=prices,solar_status='ok',prices_status='ok',prices_freshness='fresh')
    return contract,result,transport


def pipeline(reference):
    contract,inp,transport=inputs(reference)
    bridge=project_soc_to_window(contract=contract,soc=60,charge_power_w=0,discharge_power_w=0)
    need=build_do_plan_energy_need(input_result=inp,soc_percent=bridge['planner_start_soc_percent'],now=reference)
    need.update(soc_bridge=bridge,measured_soc_percent=60,planner_start_soc_percent=bridge['planner_start_soc_percent'])
    reserve=build_do_plan_reserve_soc(energy_need_result=need)
    preview=build_do_plan_preview(input_result=inp,reserve_result=reserve,now=reference)
    grid=build_do_plan_grid_support(input_result=inp,energy_need_result=need,reserve_result=reserve)
    plan=build_do_plan_72h(input_result=inp,reserve_result=reserve,preview_result=preview,grid_support_result=grid)
    return contract,inp,need,reserve,preview,grid,plan


@pytest.mark.parametrize('minute',range(60))
def test_every_minute_sources_select_identical_288_slots(minute):
    c,inp,transport=inputs(datetime(2026,9,13,18,minute,7,tzinfo=UTC))
    assert inp['status']=='ready' and len(inp['slots'])==288 and inp['native_valid_slot_count']==288
    assert inp['planner_start']==c['window_start']==transport['planner_start']
    assert inp['planner_end']==c['window_end']==transport['planner_end']
    assert transport['leading_quarter_offset']==0 and transport['generated_quarter_count']==288
    assert [utc(s['start']) for s in inp['slots']]==list(expected_starts(c))
    for r in inp['rows']:
        assert [q['start'] for q in r['home_quarters']]==[q['start'] for q in r['solar_quarters']]==[q['start'] for q in r['price_quarters']]


@pytest.mark.parametrize('reference',[
    '2026-09-13T18:00:00+00:00','2026-09-13T18:00:00.000001+00:00','2026-09-13T18:14:59.999999+00:00',
    '2026-09-13T18:15:00+00:00','2026-09-13T18:15:00.000001+00:00','2026-09-13T18:59:59+00:00',
    '2026-12-31T23:59:59+00:00','2026-03-29T01:59:59+01:00','2026-03-29T03:00:00+02:00',
    '2026-10-25T02:59:59+02:00','2026-10-25T02:00:00+01:00','2026-10-25T02:59:59+01:00'])
def test_exact_boundaries_microseconds_midnight_and_dst(reference):
    ref=utc(reference); c=build_time_contract(ref); starts=expected_starts(c)
    assert validate_time_contract(c)==[] and len(set(starts))==288
    assert all(b-a==STEP for a,b in zip(starts,starts[1:]))
    assert 0<=(starts[0]-ref).total_seconds()<900
    assert utc(c['window_end'])-starts[0]==timedelta(hours=72)
    assert starts[-1]+STEP==utc(c['window_end'])


def test_equivalent_offsets_share_window_identity():
    a=build_time_contract(datetime.fromisoformat('2026-09-13T20:16:00+02:00'))
    b=build_time_contract(datetime.fromisoformat('2026-09-13T18:16:00+00:00'))
    assert a==b and a['window_start']=='2026-09-13T18:30:00+00:00'


@pytest.mark.parametrize('key,value',[('window_start','2026-09-13T19:00:00+00:00'),('slot_count',287),('window_id','fake'),('end_exclusive',False),('resolution_minutes',60)])
def test_corrupt_contract_rejected(key,value):
    c=build_time_contract(datetime(2026,9,13,18,16,tzinfo=UTC));c[key]=value
    assert validate_time_contract(c)
    with pytest.raises(ValueError): expected_starts(c)


def test_naive_reference_rejected():
    with pytest.raises(ValueError): build_time_contract(datetime(2026,9,13,18,16))


def test_full_production_pipeline_shares_window_and_preserves_energy():
    c,inp,need,reserve,preview,grid,plan=pipeline(datetime(2026,9,13,18,16,tzinfo=UTC))
    assert all(x['window_id']==c['window_id'] for x in (inp,need,reserve,preview,grid,plan))
    assert plan['valid'] is True and plan['slot_count']==288 and plan['hour_count']==73
    assert plan['planner_resolution_minutes']==15 and plan['dashboard_resolution_minutes']==60
    assert plan['hours'][0]['coverage_minutes']==plan['hours'][-1]['coverage_minutes']==30
    assert all(not h['partial_hour'] for h in plan['hours'][1:-1])
    assert plan['hours'][0]['start']==c['window_start'] and plan['hours'][-1]['end']==c['window_end']
    assert plan['slots'][0]['start_soc_percent']==pytest.approx(60)
    assert plan['physical_execution_authority'] is False
    for key in FLOW_KEYS:
        assert sum(h[key] for h in plan['hours'])==pytest.approx(sum(s[key] for s in plan['slots']),abs=1e-5)


@pytest.mark.parametrize('minute,count',[(0,72),(15,73),(30,73),(45,73)])
def test_hourly_buckets_preserve_quarters_coverage_and_endpoints(minute,count):
    c,*_,p=pipeline(datetime(2026,9,13,18,minute,tzinfo=UTC))
    assert p['hour_count']==count
    assert sum(h['slot_count'] for h in p['hours'])==288
    assert sum(h['coverage_minutes'] for h in p['hours'])==4320
    for h in p['hours']:
        group=[s for s in p['slots'] if utc(h['start'])<=utc(s['start'])<utc(h['end'])]
        assert h['start_soc_percent']==group[0]['start_soc_percent']
        assert h['end_soc_percent']==group[-1]['end_soc_percent']
        assert h['dynamic_reserve_end_soc_percent']==group[-1]['dynamic_reserve_end_soc_percent']
        assert h['import_price']==pytest.approx(sum(s['import_price'] for s in group)/len(group))


def test_autumn_repeated_hour_remains_separate():
    _,*_,p=pipeline(datetime(2026,10,25,0,0,tzinfo=UTC))
    keys=[utc(h['bucket_start']).astimezone(AMS) for h in p['hours'][:4]]
    assert keys[0].hour==keys[1].hour==2
    assert keys[0].utcoffset()!=keys[1].utcoffset()
    assert len(p['hours'])==72


def test_usable_solar_starts_on_clock_hour_not_index_modulo_four():
    c,inp,_=inputs(datetime(2026,9,13,18,16,tzinfo=UTC))
    assert _find_next_usable_solar(inp['slots'],0)==2
    need=build_do_plan_energy_need(input_result=inp,soc_percent=60,now=utc(c['reference_utc']))
    assert need['first_usable_solar']=='2026-09-13T19:00:00+00:00'


def test_isolated_price_gap_interpolates_in_place():
    c,inp,_=inputs(datetime(2026,9,13,18,16,tzinfo=UTC),missing_price=37)
    assert len(inp['slots'])==288 and inp['slots'][37]['price_kind']=='interpolated'
    assert utc(inp['slots'][37]['start'])==expected_starts(c)[37]
    assert inp['interpolated_price_slots']==1


def test_missing_tail_keeps_geometry_and_independent_need():
    c,inp,_=inputs(datetime(2026,9,13,18,16,tzinfo=UTC),missing_price=287)
    assert inp['effective_horizon_hours']==71 and len(inp['slots'])==288
    assert inp['slots'][-1]['import_price'] is None
    need=build_do_plan_energy_need(input_result=inp,soc_percent=60,now=utc(c['reference_utc']))
    assert need['valid'] is True and need['window_id']==inp['window_id']


def test_conflicting_duplicate_never_last_wins_or_interpolated():
    _,inp,_=inputs(datetime(2026,9,13,18,16,tzinfo=UTC),duplicate_price=40)
    assert inp['slots'][40]['import_price'] is None and inp['slots'][40]['price_kind'] is None
    assert inp['source_time_audit']['prices']['duplicate_slots']==1
    assert inp['effective_horizon_hours']==10


def test_missing_solar_never_zero():
    _,inp,_=inputs(datetime(2026,9,13,18,16,tzinfo=UTC),missing_solar=1)
    assert inp['slots'][1]['solar_kwh'] is None and inp['slots'][1]['valid'] is False
    assert inp['effective_horizon_hours']==0


def test_mismatched_dependency_does_not_invalidate_upstream():
    _,inp,need,reserve,_,_,_=pipeline(datetime(2026,9,13,18,16,tzinfo=UTC))
    r=deepcopy(reserve);r['time_contract']=build_time_contract(datetime(2026,9,13,18,31,tzinfo=UTC))
    out=build_do_plan_preview(input_result=inp,reserve_result=r,now=datetime(2026,9,13,18,16,tzinfo=UTC))
    assert out['valid'] is False and 'time_window_mismatch' in out['blockers']
    assert inp['status']=='ready' and need['valid'] is True


@pytest.mark.parametrize('charge,discharge,delta',[(1000,0,1000*.92*840/3600000),(0,1000,-1000/.92*840/3600000),(0,0,0)])
def test_soc_bridge_explicit_reference_to_start_interval(charge,discharge,delta):
    c=build_time_contract(datetime(2026,9,13,18,16,tzinfo=UTC))
    b=project_soc_to_window(contract=c,soc=60,charge_power_w=charge,discharge_power_w=discharge)
    assert b['valid'] is True and b['duration_seconds']==840
    assert b['stored_energy_delta_kwh']==pytest.approx(delta)
    assert b['planner_start_soc_percent']==pytest.approx(60+delta/7.2*100)
    assert b['is_estimate'] is True and b['projected_at']==c['window_start']


@pytest.mark.parametrize('charge,discharge',[(None,0),(0,None),(float('nan'),0),(0,float('inf')),(-1,0),(100,100),(True,0)])
def test_invalid_power_is_not_zero(charge,discharge):
    c=build_time_contract(datetime(2026,9,13,18,16,tzinfo=UTC))
    b=project_soc_to_window(contract=c,soc=60,charge_power_w=charge,discharge_power_w=discharge)
    assert b['valid'] is False and b['planner_start_soc_percent'] is None


def test_exact_boundary_requires_no_projection():
    c=build_time_contract(datetime(2026,9,13,18,15,tzinfo=UTC))
    b=project_soc_to_window(contract=c,soc=60,charge_power_w=None,discharge_power_w=None)
    assert b['valid'] is True and b['is_estimate'] is False and b['planner_start_soc_percent']==60


def test_soc_saturation_does_not_invent_charge():
    c=build_time_contract(datetime(2026,9,13,18,16,tzinfo=UTC))
    b=project_soc_to_window(contract=c,soc=99,charge_power_w=3200,discharge_power_w=0)
    assert b['planner_start_soc_percent']==100 and b['capacity_or_device_floor_limited']
    b=project_soc_to_window(contract=c,soc=2,charge_power_w=1,discharge_power_w=0)
    assert 2<b['planner_start_soc_percent']<2.1


def test_wrong_soc_bridge_boundary_blocks_only_plan():
    _,inp,_,reserve,preview,grid,_=pipeline(datetime(2026,9,13,18,16,tzinfo=UTC))
    r=deepcopy(reserve);r['soc_bridge']['projected_at']='2026-09-13T19:00:00+00:00'
    p=build_do_plan_72h(input_result=inp,reserve_result=r,preview_result=preview,grid_support_result=grid)
    assert p['valid'] is False and 'planner_start_soc_not_aligned' in p['blockers']


def test_snapshot_uses_same_contract_before_selecting_sources():
    source=(ROOT/'custom_components/dummy_os_data/sensor.py').read_text()
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='_planner_runtime_snapshot')
    seen=[]
    class Source:
        source_status='ok';status='ok';freshness='fresh'
        def planner_points_for_window(self,contract,**kwargs):
            seen.append(contract);return []
    c=SimpleNamespace(records=[],evaluations=[],horizon_daily_stats={},profile='normal',source_available=True,solar=Source(),prices=Source())
    ref=datetime(2026,9,13,18,14,59,tzinfo=UTC)
    ns={'datetime':datetime,'Any':object,'DummyOSHomeDataCoordinator':object,'utc':utc,'build_time_contract':build_time_contract,'dt_util':SimpleNamespace(utcnow=lambda:ref)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<snapshot>','exec'),ns)
    s=ns['_planner_runtime_snapshot'](c)
    assert seen[0] is seen[1] is s['time_contract']
    assert s['now']==ref and s['records'] is not c.records


def test_publication_expiry_and_dependency_recovery_are_explicit():
    src=(ROOT/'custom_components/dummy_os_data/sensor.py').read_text()
    assert 'planner_window_elapsed' in src and 'time_alignment_current' in src
    assert 'subscribe_bridge_recovery(self)' in src
    for name in ('do_plan_preview_sensor.py','do_plan_grid_support_sensor.py'):
        src=(ROOT/'custom_components/dummy_os_data'/name).read_text()
        assert 'subscribe_upstream(self,' in src and 'aligned_reference(input_result,' in src


@pytest.mark.parametrize('minute',[0,1,5,14,15,16,29,30,44,45,59])
def test_real_prices_adapter_does_not_read_independent_clock(monkeypatch,minute):
    from custom_components.dummy_os_data import prices as m
    ref=datetime(2026,9,13,18,minute,5,tzinfo=UTC)
    c=m.DummyOSPricesCoordinator(None,SimpleNamespace(options={},data={}))
    begin=ref.replace(minute=0,second=0,microsecond=0)
    for i in range(304):
        start=begin+i*STEP
        c._price_buffer_by_start[start]=m.PricePoint(start,.1,.121,.2,.1,'known_pt15m',15)
    tc=build_time_contract(ref)
    def forbidden(): raise AssertionError('independent clock read')
    monkeypatch.setattr(m.dt_util,'utcnow',forbidden)
    selected=c.planner_points_for_window(tc)
    assert tuple(utc(p.start) for p in selected)==expected_starts(tc)
    assert c.planner_price_missing_slots==0
    assert c.planner_window_start==utc(tc['window_start']) and c.planner_window_end==utc(tc['window_end'])


def test_real_home_model_obeys_explicit_window_across_dst(monkeypatch):
    from custom_components.dummy_os_data import forecast as m
    monkeypatch.setattr(m.dt_util,'as_utc',utc,raising=False)
    monkeypatch.setattr(m.dt_util,'as_local',lambda d:utc(d).astimezone(AMS))
    ref=datetime(2026,10,25,0,59,59,tzinfo=UTC);tc=build_time_contract(ref)
    slots=m.HomeBaselineForecast([]).build('normal',now=ref,window_start=utc(tc['window_start']))
    assert tuple(s.start for s in slots)==expected_starts(tc)
    assert all(s.end-s.start==STEP and s.energy_kwh is None for s in slots)


@pytest.mark.parametrize('start',['2026-03-29T00:00:00+00:00','2026-10-25T00:00:00+00:00'])
def test_real_solar_normalizer_uses_unambiguous_utc_payload(start):
    import math
    from custom_components.dummy_os_data.solar_model import backward_average_slot_start
    src=(ROOT/'custom_components/dummy_os_data/solar.py').read_text()
    cls=next(n for n in ast.parse(src).body if isinstance(n,ast.ClassDef) and n.name=='DummyOSSolarCoordinator')
    fn=deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_normalize_irradiance'));fn.decorator_list=[]
    ns={'Any':object,'datetime':datetime,'ZoneInfo':ZoneInfo,'math':math,'OPEN_METEO_SOLAR_TIMEZONE':'Europe/Amsterdam',
        'dt_util':SimpleNamespace(UTC=UTC),'backward_average_slot_start':backward_average_slot_start,
        'SOLAR_RESOLUTION_MINUTES':15,'FORECAST_SLOTS':288,'SOLAR_BUFFER_SLOTS':4}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<solar>','exec'),ns)
    first=utc(start)
    payload={'timezone':'UTC','minutely_15':{'time':[(first+(i+1)*STEP).replace(tzinfo=None).isoformat() for i in range(296)],'global_tilted_irradiance':[100]*296}}
    values=ns['_normalize_irradiance'](payload,first)
    assert len(values)==292 and sorted(values)==[first+i*STEP for i in range(292)]


def test_expired_buffer_keeps_exact_missing_tail():
    from custom_components.dummy_os_data import prices as m
    c=m.DummyOSPricesCoordinator(None,SimpleNamespace(options={},data={}))
    begin=datetime(2026,9,13,18,0,tzinfo=UTC)
    for i in range(304):
        start=begin+i*STEP;c._price_buffer_by_start[start]=m.PricePoint(start,.1,.121,.2,.1,'known_pt15m',15)
    tc=build_time_contract(begin+timedelta(hours=6));chosen=c.planner_points_for_window(tc)
    assert len(chosen)==280 and c.planner_price_missing_slots==8
    assert c.planner_price_missing_starts==list(expected_starts(tc)[-8:])


def _material_key_function():
    import hashlib
    source=(ROOT/'custom_components/dummy_os_data/do_plan_grid_support_sensor.py').read_text()
    nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in {'_stable_material','build_plan_store_bridge_refresh_key'}]
    ns={'Any':object,'datetime':datetime,'timezone':timezone,'hashlib':hashlib}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<material-key>','exec'),ns)
    return ns['build_plan_store_bridge_refresh_key']


def test_repeated_notifications_do_not_force_safety_replay():
    key=_material_key_function()
    c=build_time_contract(datetime(2026,9,13,18,16,tzinfo=UTC))
    bridge=project_soc_to_window(contract=c,soc=60,charge_power_w=0,discharge_power_w=500)
    a={'now':utc(c['reference_utc']),'time_contract':c,'soc_bridge':bridge,'soc_percent':bridge['planner_start_soc_percent']}
    c2=build_time_contract(datetime(2026,9,13,18,17,tzinfo=UTC))
    bridge2=project_soc_to_window(contract=c2,soc=60,charge_power_w=0,discharge_power_w=500)
    b={'now':utc(c2['reference_utc']),'time_contract':c2,'soc_bridge':bridge2,'soc_percent':bridge2['planner_start_soc_percent']}
    assert a['soc_percent']!=b['soc_percent']
    assert key(a)==key(b)
    assert a['soc_bridge']['observed_at']==c['reference_utc']


@pytest.mark.parametrize('field,value',[('measured_soc_percent',61),('discharge_power_w',600),('projected_at','2026-09-13T18:45:00+00:00')])
def test_material_soc_or_window_change_invalidates_cached_plan(field,value):
    key=_material_key_function()
    c=build_time_contract(datetime(2026,9,13,18,16,tzinfo=UTC))
    bridge=project_soc_to_window(contract=c,soc=60,charge_power_w=0,discharge_power_w=500)
    a={'now':utc(c['reference_utc']),'time_contract':c,'soc_bridge':bridge,'soc_percent':bridge['planner_start_soc_percent']}
    b=deepcopy(a);b['soc_bridge'][field]=value
    assert key(a)!=key(b)
