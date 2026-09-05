from pathlib import Path

Path('tests/test_peak_learning.py').write_text(r'''import importlib.util
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


def test_1700_window_not_exact_structural():
    result = module.calculate_peak_learning(basis(days=12), 'normal', localize)
    assert result['classifications']['hour_17']['classification'] != 'structural'
    assert result['protected_windows']['17:00-18:00']['policy'] == 'no_exact_quarter_structural'


def test_native_forecast_contract_unchanged():
    const_path = Path('custom_components/dummy_os_data/const.py')
    text = const_path.read_text()
    assert 'QUARTER_MINUTES = 15' in text
    assert 'FORECAST_HORIZON_HOURS = 72' in text
    assert 'FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES' in text


def test_sensor_identity_contract():
    text = Path('custom_components/dummy_os_data/sensor.py').read_text()
    assert '_attr_unique_id = "dummy_os_data_energy_peak_learning"' in text
    assert '_attr_suggested_object_id = "do_energy_peak_learning"' in text
    assert 'DummyOSEnergyPeakLearningSensor(coordinator)' in text
''')
