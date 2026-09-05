from __future__ import annotations
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
S=importlib.util.spec_from_file_location("eval_daytype",ROOT/"custom_components/dummy_os_data/evaluation.py"); M=importlib.util.module_from_spec(S); S.loader.exec_module(M)
calc=M.calculate_day_type_quality; LOCAL=ZoneInfo("Europe/Amsterdam")
def iso(s): return datetime.fromisoformat(s).replace(tzinfo=LOCAL).astimezone(timezone.utc).isoformat()
def ev(s,a=.1,f=.1,p="normal"): return {"start":iso(s),"profile":p,"actual_kwh":a,"forecast_kwh":f}
def rec(s,p="normal",v=True): return {"start":iso(s),"profile":p,"valid":v}
def loc(v): return v.astimezone(LOCAL)
def test_boundaries():
 t=["2026-09-04T23:45","2026-09-05T00:00","2026-09-06T23:45","2026-09-07T00:00"]; r=calc([ev(x) for x in t],[rec(x) for x in t],"normal",loc); assert r["day_types"]["weekday"]["sample_count"]==2 and r["day_types"]["weekend"]["sample_count"]==2
def test_missing_profile_and_metrics():
 r=calc([ev("2026-09-07T10:00",.1,.2),ev("2026-09-07T10:15",.5,.5,"away"),{"start":iso("2026-09-07T10:30"),"profile":"normal","actual_kwh":None,"forecast_kwh":.2}],[rec("2026-09-07T10:00"),rec("2026-09-07T10:30")],"normal",loc)["day_types"]["weekday"]; assert r["sample_count"]==1 and r["valid_actual_quarters"]==2 and r["evaluation_coverage_percent"]==50.0 and r["mae_kwh"]==0.1 and r["bias_kwh"]==0.1
def test_readiness_and_dst():
 e=[]; rr=[]
 for i in range(32):
  w=f"2026-09-07T{(i//4):02d}:{(i%4)*15:02d}"; z=f"2026-09-05T{(i//4):02d}:{(i%4)*15:02d}"; e += [ev(w),ev(z)]; rr += [rec(w),rec(z)]
 assert calc(e,rr,"normal",loc)["status"]=="sufficient_basis"
 d=calc([ev("2026-03-29T03:00"),ev("2026-03-30T00:00")],[rec("2026-03-29T03:00"),rec("2026-03-30T00:00")],"normal",loc); assert d["day_types"]["weekend"]["sample_count"]==1 and d["day_types"]["weekday"]["sample_count"]==1
