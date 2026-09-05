from pathlib import Path
ROOT=Path(__file__).parents[1]
def test_exact_identity_and_observer_contract():
    s=(ROOT/'custom_components/dummy_os_data/sensor.py').read_text(); i=(ROOT/'custom_components/dummy_os_data/__init__.py').read_text(); m=(ROOT/'custom_components/dummy_os_data/entity_migrations.py').read_text(); u='do_energy_forecast_quality_by_day_type_and_daypart'
    assert f'_attr_unique_id = "{u}"' in s and f'_attr_suggested_object_id = "{u}"' in s and 'DummyOSHomeForecastQualityByDayTypeAndDaypartSensor(coordinator)' in s and f'("sensor", "{u}", "sensor.{u}")' in i and f'"{u}": "sensor.dummy_os_forecast_{u}"' in m
def test_native_architecture_remains_15_72_288():
    c=(ROOT/'custom_components/dummy_os_data/const.py').read_text(); assert 'QUARTER_MINUTES = 15' in c and 'FORECAST_HORIZON_HOURS = 72' in c and 'FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES' in c
