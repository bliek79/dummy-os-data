from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "dummy_os_data"
GRID_ADAPTER = COMP / "do_plan_grid_support_sensor.py"
SURFACE = COMP / "ems_alpha76_surface.py"
RUNTIME = COMP / "ems_alpha76_runtime.py"
ALPHA76_STORE = COMP / "ems_alpha76" / "plan_store.py"


def test_step8b_active_bundle_uses_alpha76_status_surface_not_alpha35_store():
    grid = GRID_ADAPTER.read_text()
    assert "build_alpha76_status_sensors(coordinator)" in grid
    assert "build_do_plan_store_sensors(coordinator)" not in grid
    assert "get_do_plan_store_runtime(coordinator)" not in grid
    assert "DummyOSPlanStoreBridgeSensor" not in grid


def test_step8b_controls_share_exact_alpha76_plan_store_runtime():
    surface = SURFACE.read_text()
    store = ALPHA76_STORE.read_text()
    assert "self.plan_store = runtime.plan_store" in surface
    assert "await self.plan_store.async_set_value" in surface
    assert "class AnkerEmsPlanStore" in store
    assert "CONTROL_FIELDS" in store


def test_step8b_shadow_safety_contract_is_hard_closed():
    surface = SURFACE.read_text()
    runtime = RUNTIME.read_text()
    combined = surface + runtime
    for marker in (
        '"shadow_only": True',
        '"physical_execution_authority": False',
        '"alpha76_physical_autostart_wired": False',
    ):
        assert marker in combined
    assert "def simulation_mode" in runtime
    assert "return True" in runtime
    assert ".async_execute_automatic_plan(" not in surface
    assert ".async_execute_automatic_plan(" not in runtime
