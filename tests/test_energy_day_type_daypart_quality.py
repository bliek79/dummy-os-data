from __future__ import annotations
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('energy_evaluation_step5',ROOT/'custom_components/dummy_os_data/evaluation.py'); assert SPEC and SPEC.loader
MODULE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE); calculate_quality=MODULE.calculate_day_type_daypart_quality
LOCAL=ZoneInfo('Europe/Amsterdam')
def iso(s): return datetime.fromisoformat(s).replace(tzinfo=LOCAL).astimezone(timezone.utc).isoformat()
def ev(s,a=.1,f=.1,p='normal'): return {'start':iso(s),'profile':p,'actual_kwh':a,'forecast_kwh':f}
def rec(s,p='normal',v=True): return {'start':iso(s),'profile':p,'valid':v}
def loc(v): return v.astimezone(LOCAL)
def test_exact_eight_combination_keys_and_boundaries():
    ts=['2026-09-04T05:45','2026-09-04T06:00','2026-09-04T12:00','2026-09-04T18:00','2026-09-05T05:45','2026-09-05T06:00','2026-09-05T12:00','2026-09-05T18:00']
    r=calculate_quality([ev(x) for x in ts],[rec(x) for x in ts],'normal',loc)
    assert set(r['combinations'])=={'weekday_night','weekday_morning','weekday_afternoon','weekday_evening','weekend_night','weekend_morning','weekend_afternoon','weekend_evening'}
    assert all(x['sample_count']==1 for x in r['combinations'].values())
def test_profile_separation_and_missing_not_zero():
    e=[ev('2026-09-07T12:00',.1,.2),ev('2026-09-07T12:15',.5,.5,'away'),{'start':iso('2026-09-07T12:30'),'profile':'normal','actual_kwh':None,'forecast_kwh':.2}]
    x=calculate_quality(e,[rec('2026-09-07T12:00'),rec('2026-09-07T12:30')],'normal',loc)['combinations']['weekday_afternoon']
    assert x['sample_count']==1 and x['valid_actual_quarters']==2 and x['evaluation_coverage_percent']==50.0 and x['mae_kwh']==.1 and x['bias_kwh']==.1
def test_total_readiness_requires_all_eight_segments():
    e=[]; rr=[]
    groups=[('2026-09-07','2026-09-08'),('2026-09-05','2026-09-06')]
    for dates in groups:
        for hour in (0,6,12,18):
            for date in dates:
                for index in range(16):
                    s=f'{date}T{hour + index//4:02d}:{(index%4)*15:02d}'
                    e.append(ev(s)); rr.append(rec(s))
    r=calculate_quality(e,rr,'normal',loc)
    assert r['status']=='sufficient_basis'
    assert all(x['sample_count']==32 and x['status']=='sufficient_basis' for x in r['combinations'].values())
def test_week_boundary_and_dst_use_local_calendar():
    ts=['2026-09-04T23:45','2026-09-05T00:00','2026-09-06T23:45','2026-09-07T00:00']; r=calculate_quality([ev(x) for x in ts],[rec(x) for x in ts],'normal',loc)
    assert r['combinations']['weekday_evening']['sample_count']==1 and r['combinations']['weekend_night']['sample_count']==1 and r['combinations']['weekend_evening']['sample_count']==1 and r['combinations']['weekday_night']['sample_count']==1
    d=calculate_quality([ev('2026-03-29T03:00')],[rec('2026-03-29T03:00')],'normal',loc); assert d['combinations']['weekend_night']['sample_count']==1
