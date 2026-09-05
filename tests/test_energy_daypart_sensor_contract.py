from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_daypart_sensor_has_exact_public_identity_and_is_registered():
    sensor = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()
    init = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
    migrations = (ROOT / "custom_components/dummy_os_data/entity_migrations.py").read_text()
    assert '_attr_unique_id = "do_energy_forecast_quality_by_daypart"' in sensor
    assert '_attr_suggested_object_id = "do_energy_forecast_quality_by_daypart"' in sensor
    assert 'DummyOSHomeForecastQualityByDaypartSensor(coordinator)' in sensor
    assert '("sensor", "do_energy_forecast_quality_by_daypart", "sensor.do_energy_forecast_quality_by_daypart")' in init
    assert '"do_energy_forecast_quality_by_daypart": "sensor.dummy_os_forecast_do_energy_forecast_quality_by_daypart"' in migrations


def test_daypart_sensor_is_observer_only_and_keeps_native_architecture():
    sensor = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()
    const = (ROOT / "custom_components/dummy_os_data/const.py").read_text()
    assert '"observer_only": True' in sensor
    assert '"daypart_basis": "local_quarter_start"' in sensor
    assert "QUARTER_MINUTES = 15" in const
    assert "FORECAST_HORIZON_HOURS = 72" in const
    assert "FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES" in const
