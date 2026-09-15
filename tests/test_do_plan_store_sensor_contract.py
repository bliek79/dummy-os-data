from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "dummy_os_data"


def test_alpha35_store_entities_are_not_registered_in_step8b_active_bundle():
    adapter = (COMP / "do_plan_grid_support_sensor.py").read_text()
    assert "build_do_plan_store_sensors" not in adapter
    assert "DummyOSPlanStoreBridgeSensor" not in adapter
    assert "build_alpha76_status_sensors(coordinator)" in adapter


def test_active_manual_controls_use_exact_alpha76_plan_store():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    store = (COMP / "ems_alpha76" / "plan_store.py").read_text()
    assert "self.plan_store = runtime.plan_store" in surface
    assert "await self.plan_store.async_set_value" in surface
    assert "class AnkerEmsPlanStore" in store
    for field in (
        '"action"',
        '"execution_mode"',
        '"start_time"',
        '"power_w"',
        '"target_soc"',
        '"max_runtime_h"',
        '"max_start_delay_min"',
    ):
        assert field in store


def test_step8b_keeps_operational_rights_closed():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    runtime = (COMP / "ems_alpha76_runtime.py").read_text()
    combined = surface + runtime
    assert '"shadow_only": True' in combined
    assert '"physical_execution_authority": False' in combined
    assert '"alpha76_physical_autostart_wired": False' in combined
    assert ".async_execute_automatic_plan(" not in surface
    assert ".async_execute_automatic_plan(" not in runtime
