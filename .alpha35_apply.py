"""Final checked cache regression repair; temporary feature-branch helper."""
from pathlib import Path
import json
C=Path('custom_components/dummy_os_data')
assert json.loads((C/'manifest.json').read_text())['version']=='0.2.0-alpha.35'
p=C/'do_plan_grid_support_sensor.py'
s=p.read_text()
old='''def build_plan_store_bridge_refresh_key(snapshot: dict[str, Any]) -> str:
    now = snapshot.get("now")'''
new='''def build_plan_store_bridge_refresh_key(snapshot: dict[str, Any]) -> str:
    # Diagnostic observation times must not turn every repeated notification into
    # an expensive full replay. Refresh on window or actual input changes. The
    # retained result keeps its original projection reference, never relabelled.
    bridge = snapshot.get("soc_bridge")
    if isinstance(bridge, dict):
        snapshot = dict(snapshot)
        snapshot["soc_percent"] = bridge.get("measured_soc_percent")
        snapshot["soc_bridge"] = {key: bridge.get(key) for key in (
            "valid", "method", "charge_power_w", "discharge_power_w",
            "measured_soc_percent", "blockers", "projected_at",
        )}
    now = snapshot.get("now")'''
assert s.count(old)==1
p.write_text(s.replace(old,new))
p=Path('tests/test_alpha35_shared_time_contract.py')
s=p.read_text()
s+='''

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
'''
p.write_text(s)
print('Alpha35: diagnostic time removed from material replay key; four regressions added')
