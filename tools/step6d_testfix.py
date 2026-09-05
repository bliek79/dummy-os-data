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
''')

release_test = Path('tests/test_release_consistency.py')
text = release_test.read_text()
text = text.replace('VERSION = "0.1.0-alpha.12.11"', 'VERSION = "0.1.0-alpha.12.12"')
needle = '    "do_energy_forecast_quality_by_hour",\n)'
replacement = '    "do_energy_forecast_quality_by_hour",\n    "dummy_os_data_energy_peak_learning",\n)'
if needle in text:
    text = text.replace(needle, replacement, 1)
text = text.replace('self.assertEqual(18, sum(sensor_source.count(f\'_attr_unique_id = "{unique_id}"\') for unique_id in EXPECTED_ENERGY_IDS))', 'self.assertEqual(19, sum(sensor_source.count(f\'_attr_unique_id = "{unique_id}"\') for unique_id in EXPECTED_ENERGY_IDS))')
release_test.write_text(text)

Path('RELEASE_NOTES.md').write_text('''# GitHub Release\n\n**Tag:** `0.1.0-alpha.12.12`  \n**Release title:** Dummy OS Forecast 0.1.0-alpha.12.12 - Energy Peak Learning Observer\n\n## Dummy OS Forecast 0.1.0-alpha.12.12\n\nObserver-only implementatie van Energy Forecast Stap 6D. De nieuwe laag detecteert en classificeert piekgedrag uit de bestaande forward-looking Energy-evaluatiehistorie zonder de forecast zelf te wijzigen.\n\n### Nieuw\n- Canonieke Home Assistant-entiteit `sensor.do_energy_peak_learning`.\n- `unique_id`: `dummy_os_data_energy_peak_learning`.\n- `suggested_object_id`: `do_energy_peak_learning`.\n- Kandidaatpiekdetectie op positieve residual `actual_kwh - forecast_kwh`.\n- Leave-one-local-day-out kalibratie met minimum 32 geldige kwartieren en 8 verschillende lokale dagen per uur.\n- Exact aangrenzende kandidaatkwartieren worden tot een event samengevoegd; gaten worden niet overbrugd en een event mag een uurgrens passeren.\n- Observer-only classificaties `incidental`, `structural`, `shifting_structural_grill` en `unresolved`.\n- Het venster 17:00-18:00 heeft vaste bescherming `no_exact_quarter_structural`.\n\n### Identity / migratie / cleanup\n- Nieuwe entiteit; er bestaat geen oudere canonical identity die gemigreerd moet worden.\n- Er is geen gegenereerde alias bedoeld. Na installatie moet de entity registry exact `sensor.do_energy_peak_learning` bevatten; een afwijkende suffix/alias geldt als migratie- of cleanupafwijking.\n- Detailattributen `calibration`, `classifications` en `events` zijn uitgesloten van Recorder.\n\n### Ongewijzigd\n- Native architectuur blijft exact 15 minuten / 72 uur / 288 slots.\n- `forecast.py` en forecastwaarden worden niet gewijzigd.\n- Geen planner-, execution-, confidence-, recency-, fallback- of Stap-7 time-windowinvloed.\n- Normal en Away blijven strikt gescheiden.\n- Missing, unavailable en niet-berekende kalibratiewaarden blijven `null` en worden nooit stilzwijgend `0`.\n\n### Validatie\n- Contracttests voor minimum databasis, profielscheiding en null-semantiek.\n- Expliciete leave-one-day-out-test.\n- Eventtests voor adjacency, geen gap-bridging en uurgrensoverschrijding.\n- Beschermingstest voor 17:00-18:00.\n- Identity-contracttest voor unique_id/suggested_object_id/registratie.\n- Regressietest voor 15 minuten / 72 uur / 288 slots.\n- Volledige bestaande testsuite, Python compile en manifest JSON-validatie vóór merge.\n- Na installatie live valideren dat `sensor.do_energy_peak_learning` exact onder de canonical entity_id verschijnt en observer-only blijft.\n''')
