import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _migration_module():
    path = ROOT / "custom_components/dummy_os_data/entity_migrations.py"
    spec = importlib.util.spec_from_file_location("recency_entity_migrations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recency_weighting_sensor_full_identity_and_registration_contract():
    sensor_source = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()
    init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
    migration_source = (ROOT / "custom_components/dummy_os_data/entity_migrations.py").read_text()
    marker = "class DummyOSEnergyRecencyWeightingSensor(DummyOSBaseSensor):"
    assert sensor_source.count("DummyOSEnergyRecencyWeightingSensor(coordinator)") == 1
    assert sensor_source.count(marker) == 1
    start = sensor_source.index(marker)
    next_class = sensor_source.find("\n\nclass ", start + 1)
    block = sensor_source[start:] if next_class == -1 else sensor_source[start:next_class]
    assert '_attr_name = "DO Energy Recency Weighting"' in block
    assert '_attr_unique_id = "do_energy_recency_weighting"' in block
    assert '_attr_suggested_object_id = "do_energy_recency_weighting"' in block
    assert 'return "DO Energy Recency Weighting"' in block
    assert 'return "Dummy"' not in block
    assert '_unrecorded_attributes = frozenset({"per_candidate_metrics", "segment_metrics", "early_late_metrics"})' in block
    assert '("sensor", "do_energy_recency_weighting", "sensor.do_energy_recency_weighting")' in init_source
    assert '"do_energy_recency_weighting": "sensor.dummy_os_forecast_do_energy_recency_weighting"' in migration_source
    migrations = _migration_module()
    assert migrations.is_known_generated_entity_id("sensor", "do_energy_recency_weighting", "sensor.dummy_os_forecast_do_energy_recency_weighting")
    assert not migrations.is_known_generated_entity_id("sensor", "do_energy_recency_weighting", "sensor.user_named_recency_weighting")
    assert "sensor.do_energy_recency_weighting_2" not in sensor_source + init_source + migration_source


def test_step8a_is_observer_only_and_native_architecture_is_unchanged():
    forecast_source = (ROOT / "custom_components/dummy_os_data/forecast.py").read_text()
    const_source = (ROOT / "custom_components/dummy_os_data/const.py").read_text()
    recency_source = (ROOT / "custom_components/dummy_os_data/recency_weighting.py").read_text()
    assert "RECENCY_HALF_LIFE_DAYS = 28.0" in forecast_source
    assert 'forecast_influence_enabled": False' in recency_source
    assert 'observer_only": True' in recency_source
    assert "QUARTER_MINUTES = 15" in const_source
    assert "FORECAST_HORIZON_HOURS = 72" in const_source
    assert "FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES" in const_source
