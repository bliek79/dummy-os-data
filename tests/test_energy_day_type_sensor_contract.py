from pathlib import Path
ROOT=Path(__file__).parents[1]
def test_identity_and_architecture():
 s=(ROOT/"custom_components/dummy_os_data/sensor.py").read_text(); i=(ROOT/"custom_components/dummy_os_data/__init__.py").read_text(); m=(ROOT/"custom_components/dummy_os_data/entity_migrations.py").read_text(); c=(ROOT/"custom_components/dummy_os_data/const.py").read_text(); f=(ROOT/"custom_components/dummy_os_data/forecast.py").read_text(); u="do_energy_forecast_quality_by_day_type"
 assert f'_attr_unique_id = "{u}"' in s and f'_attr_suggested_object_id = "{u}"' in s and f'("sensor", "{u}", "sensor.{u}")' in i and f'"{u}": "sensor.dummy_os_forecast_{u}"' in m
 assert "QUARTER_MINUTES = 15" in c and "FORECAST_HORIZON_HOURS = 72" in c and "FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES" in c and 'return "weekend" if local_dt.weekday() >= 5 else "weekday"' in f
