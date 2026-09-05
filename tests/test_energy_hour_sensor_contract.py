from pathlib import Path

def test_hour_sensor_exact_identity_and_contract():
    sensor=Path('custom_components/dummy_os_data/sensor.py').read_text()
    init=Path('custom_components/dummy_os_data/__init__.py').read_text()
    mig=Path('custom_components/dummy_os_data/entity_migrations.py').read_text()
    evaluation=Path('custom_components/dummy_os_data/evaluation.py').read_text()
    assert '_attr_unique_id = "do_energy_forecast_quality_by_hour"' in sensor
    assert '_attr_suggested_object_id = "do_energy_forecast_quality_by_hour"' in sensor
    assert '("sensor", "do_energy_forecast_quality_by_hour", "sensor.do_energy_forecast_quality_by_hour")' in init
    assert '"do_energy_forecast_quality_by_hour": "sensor.dummy_os_forecast_do_energy_forecast_quality_by_hour"' in mig
    assert 'AFTERNOON_HOURS: tuple[int, ...] = tuple(range(12, 18))' in evaluation
    assert '"scope": "afternoon_12_18"' in evaluation
    assert '"hour_basis":"local_quarter_start"' in sensor
