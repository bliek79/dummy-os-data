import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

path = Path('custom_components/dummy_os_data/evaluation.py')
spec = importlib.util.spec_from_file_location('energy_peak_learning', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def localize(value):
    return value


def row(start, forecast, actual, profile='normal', coverage=1.0):
    return {
        'start': start.isoformat(),
        'end': (start + timedelta(minutes=15)).isoformat(),
        'profile': profile,
        'forecast_kwh': forecast,
        'actual_kwh': actual,
        'actual_coverage': coverage,
    }


def basis(days=12, hour=17, peak_minute=15):
    rows = []
    origin = datetime(2026, 8, 1, tzinfo=timezone.utc)
    for day in range(days):
        for minute in (0, 15, 30, 45):
            actual = 0.55 if minute == peak_minute and day % 2 == 0 else 0.10
            rows.append(row(origin + timedelta(days=day, hours=hour, minutes=minute), 0.10, actual))
    return rows


def flat_basis(days, hour):
    rows = []
    origin = datetime(2026, 8, 1, tzinfo=timezone.utc)
    for day in range(days):
        for minute in (0, 15, 30, 45):
            rows.append(row(origin + timedelta(days=day, hours=hour, minutes=minute), 0.10, 0.10))
    return rows


def test_collecting_keeps_missing_threshold_null():
    result = module.calculate_peak_learning(basis(days=2), 'normal', localize)
    assert result['status'] == 'collecting'
    assert result['calibration']['hour_17']['threshold_kwh'] is None
    assert result['forecast_influence_enabled'] is False


def test_minimum_basis_32_quarters_8_days():
    result = module.calculate_peak_learning(basis(days=8), 'normal', localize)
    assert result['calibration']['hour_17']['sample_count'] == 32
    assert result['calibration']['hour_17']['distinct_days'] == 8
    assert result['calibration']['hour_17']['status'] == 'calibrated'


def test_profile_separation():
    rows = basis(days=8) + [row(datetime(2026, 9, 1, 17, tzinfo=timezone.utc), 0.1, 5.0, profile='away')]
    result = module.calculate_peak_learning(rows, 'normal', localize)
    assert result['calibration']['hour_17']['sample_count'] == 32


def test_leave_one_day_out_detects_target_without_self_setting_threshold():
    rows = flat_basis(9, 17)
    target = datetime(2026, 8, 10, 17, 15, tzinfo=timezone.utc)
    rows.append(row(target, 0.10, 1.00))
    result = module.calculate_peak_learning(rows, 'normal', localize)
    assert result['candidate_count'] == 1
    assert result['event_count'] == 1
    assert result['events'][0]['start'] == target.isoformat()


def test_adjacent_candidates_merge_and_gap_does_not_bridge():
    rows = flat_basis(9, 17)
    target_day = datetime(2026, 8, 10, 17, 0, tzinfo=timezone.utc)
    rows.extend([
        row(target_day, 0.10, 1.00),
        row(target_day + timedelta(minutes=15), 0.10, 1.00),
        row(target_day + timedelta(minutes=45), 0.10, 1.00),
    ])
    result = module.calculate_peak_learning(rows, 'normal', localize)
    day_events = [event for event in result['events'] if event['local_date'] == '2026-08-10']
    assert len(day_events) == 2
    assert sorted(event['quarter_count'] for event in day_events) == [1, 2]


def test_event_can_cross_hour_boundary():
    rows = flat_basis(9, 16) + flat_basis(9, 17)
    target_day = datetime(2026, 8, 10, 16, 45, tzinfo=timezone.utc)
    rows.extend([
        row(target_day, 0.10, 1.00),
        row(target_day + timedelta(minutes=15), 0.10, 1.00),
    ])
    result = module.calculate_peak_learning(rows, 'normal', localize)
    crossing = [event for event in result['events'] if event['start'] == target_day.isoformat()]
    assert len(crossing) == 1
    assert crossing[0]['quarter_count'] == 2
    assert crossing[0]['end'] == (target_day + timedelta(minutes=30)).isoformat()


def test_1700_window_not_exact_structural():
    result = module.calculate_peak_learning(basis(days=12), 'normal', localize)
    assert result['classifications']['hour_17']['classification'] != 'structural'
    assert result['protected_windows']['17:00-18:00']['policy'] == 'no_exact_quarter_structural'


def test_native_forecast_contract_unchanged():
    text = Path('custom_components/dummy_os_data/const.py').read_text()
    assert 'QUARTER_MINUTES = 15' in text
    assert 'FORECAST_HORIZON_HOURS = 72' in text
    assert 'FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES' in text


def test_sensor_identity_contract():
    text = Path('custom_components/dummy_os_data/sensor.py').read_text()
    assert '_attr_unique_id = "dummy_os_data_energy_peak_learning"' in text
    assert '_attr_suggested_object_id = "do_energy_peak_learning"' in text
    assert 'DummyOSEnergyPeakLearningSensor(coordinator)' in text
    assert '_unrecorded_attributes = frozenset({"calibration", "classifications", "events"})' in text



def test_missing_actual_coverage_is_not_assumed_valid():
    start = datetime(2026, 8, 1, 17, 0, tzinfo=timezone.utc)
    rows = flat_basis(8, 17)
    rows[0].pop('actual_coverage')
    result = module.calculate_peak_learning(rows, 'normal', localize)
    assert result['calibration']['hour_17']['sample_count'] == 31
    assert result['calibration']['hour_17']['status'] == 'collecting'


def test_calibration_fingerprint_is_deterministic():
    rows = flat_basis(9, 17)
    first = module.calculate_peak_learning(rows, 'normal', localize)
    second = module.calculate_peak_learning(rows, 'normal', localize)
    assert first['calibration_fingerprint'] == second['calibration_fingerprint']
    assert len(first['calibration_fingerprint']) == 16


def test_classification_thresholds_are_history_derived_or_null():
    result = module.calculate_peak_learning(flat_basis(9, 17), 'normal', localize)
    calibration = result['classification_calibration']
    assert calibration['basis'] == 'median_of_repeating_ready_hours'
    assert calibration['repeat_rate_threshold'] is None
    assert calibration['timing_mad_threshold_minutes'] is None
