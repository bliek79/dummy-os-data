import importlib.util
from datetime import datetime, timezone
from pathlib import Path

path = Path('custom_components/dummy_os_data/evaluation.py')
spec = importlib.util.spec_from_file_location('energy_evaluation_hour', path)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

def localize(value):
    return value

def item(hour, minute, actual=0.2, forecast=0.3, profile='normal'):
    return {'start': datetime(2026, 9, 1, hour, minute, tzinfo=timezone.utc).isoformat(), 'profile': profile, 'actual_kwh': actual, 'forecast_kwh': forecast}

def record(hour, minute, valid=True, profile='normal'):
    return {'start': datetime(2026, 9, 1, hour, minute, tzinfo=timezone.utc).isoformat(), 'profile': profile, 'valid': valid}

def test_exact_afternoon_hour_boundaries():
    evaluations = [item(11,45), item(12,0), item(12,45), item(17,45), item(18,0)]
    records = [record(11,45), record(12,0), record(12,45), record(17,45), record(18,0)]
    q = module.calculate_hour_quality(evaluations, records, 'normal', localize)
    assert q['hours']['hour_12']['sample_count'] == 2
    assert q['hours']['hour_17']['sample_count'] == 1
    assert sum(v['sample_count'] for v in q['hours'].values()) == 3

def test_profile_split_missing_values_and_metrics():
    evaluations = [item(13,0,0.2,0.3), item(13,15,profile='away'), {'start': item(13,30)['start'], 'profile':'normal', 'actual_kwh':'unknown', 'forecast_kwh':0.3}]
    records = [record(13,0), record(13,15), record(13,30)]
    q = module.calculate_hour_quality(evaluations, records, 'normal', localize)
    h = q['hours']['hour_13']
    assert h['sample_count'] == 1
    assert h['valid_actual_quarters'] == 3
    assert h['evaluation_coverage_percent'] == 33.3
    assert h['mae_kwh'] == 0.1
    assert h['bias_kwh'] == 0.1
    assert h['accuracy_percent'] == 50.0

def test_all_six_hours_ready_at_32_samples():
    evaluations=[]; records=[]
    for hour in range(12,18):
        for i in range(32):
            minute=(i % 4)*15
            day=1 + i//4
            start=datetime(2026,9,day,hour,minute,tzinfo=timezone.utc).isoformat()
            evaluations.append({'start':start,'profile':'normal','actual_kwh':0.2,'forecast_kwh':0.2})
            records.append({'start':start,'profile':'normal','valid':True})
    q=module.calculate_hour_quality(evaluations,records,'normal',localize)
    assert q['status']=='sufficient_basis'
    assert all(v['status']=='sufficient_basis' for v in q['hours'].values())
    assert set(q['hours']) == {f'hour_{h:02d}' for h in range(12,18)}
