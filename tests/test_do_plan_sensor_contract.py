"""Static integration contract for Planner Step 1."""
from pathlib import Path

ROOT = Path(__file__).parents[1]

def test_do_plan_input_sensor_is_registered_and_observer_only():
    sensor = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()
    init = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
    builder = (ROOT / "custom_components/dummy_os_data/do_plan_input.py").read_text()
    assert 'DummyOSPlanInput72hSensor(coordinator)' in sensor
    assert '_attr_unique_id = "do_plan_input_72h"' in sensor
    assert '_unrecorded_attributes = frozenset({"rows"})' in sensor
    assert '("sensor", "do_plan_input_72h", "sensor.do_plan_input_72h")' in init
    assert '"physical_execution_authority": False' in builder
    assert '"shadow_only": True' in builder
    assert '"active_use_permitted": False' in builder

def test_public_source_timelines_are_not_extended_for_planner():
    prices = (ROOT / "custom_components/dummy_os_data/prices.py").read_text()
    solar = (ROOT / "custom_components/dummy_os_data/solar.py").read_text()
    assert 'slot_count=FORECAST_SLOTS' in prices
    assert '[:FORECAST_SLOTS]' in solar
    assert 'PRICE_BUFFER_HOURS = 76' in prices
    assert 'PLANNER_PRICE_SLOT_COUNT' in prices
    assert 'def planner_points(self) -> list[PricePoint]:' in prices
    assert 'def planner_points(self) -> list[SolarPoint]:' in solar
