from pathlib import Path


def test_planner_heavy_sensors_are_executor_cached():
    sensor = Path("custom_components/dummy_os_data/sensor.py").read_text()
    preview = Path("custom_components/dummy_os_data/do_plan_preview_sensor.py").read_text()
    assert "class DummyOSAsyncPlannerResultSensor" in sensor
    assert "async_add_executor_job" in sensor
    for name in (
        "DummyOSEnergyForecastPlannerHoursSensor",
        "DummyOSEnergyForecastPlannerContractSensor",
        "DummyOSPlanInput72hSensor",
        "DummyOSPlanEnergyNeedSensor",
        "DummyOSPlanReserveSOCSensor",
        "DummyOSHomeForecastModelHealthSensor",
    ):
        block = sensor.split(f"class {name}", 1)[1].split("\n\nclass ", 1)[0]
        assert "_calculate_result" in block or name in {"DummyOSPlanEnergyNeedSensor"}
    assert "def _calculate_result" in preview
    assert "def _result" not in preview
    assert "planner_calculation_pending" in sensor


def test_planner_snapshot_isolation_contract():
    sensor = Path("custom_components/dummy_os_data/sensor.py").read_text()
    block = sensor.split("def _planner_runtime_snapshot", 1)[1].split("def _build_planner_hours_from_snapshot", 1)[0]
    assert '"records": list(coordinator.records)' in block
    assert '"evaluations": list(coordinator.evaluations)' in block
    assert '"solar_points": list(coordinator.solar.planner_points_for_window(contract))' in block
    assert '"price_points": list(coordinator.prices.planner_points_for_window(contract, include_neighbours=True))' in block
