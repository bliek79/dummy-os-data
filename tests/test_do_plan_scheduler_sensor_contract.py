from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "dummy_os_data"


def test_scheduler_status_and_ready_entities_use_alpha76_surface():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    bundle = (COMP / "do_plan_grid_support_sensor.py").read_text()
    binary = (COMP / "binary_sensor.py").read_text()
    const = (COMP / "const.py").read_text()

    assert 'unique_id="do_plan_scheduler"' in surface
    assert 'unique_id="do_plan_scheduler_ready"' in surface
    assert "build_alpha76_status_sensors(coordinator)" in bundle
    assert "build_alpha76_binary_sensors(coordinator)" in binary
    assert '"binary_sensor"' in const


def test_scheduler_uses_exact_alpha76_plan_store_and_runtime():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    runtime = (COMP / "ems_alpha76_runtime.py").read_text()
    assert "self.plan_store = runtime.plan_store" in surface
    assert '"ems_authority": "alpha76_runtime"' in surface
    assert "AnkerEmsScheduler(plan_store)" in runtime


def test_scheduler_operational_rights_remain_closed():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    runtime = (COMP / "ems_alpha76_runtime.py").read_text()
    combined = surface + runtime
    for needle in (
        '"shadow_only": True',
        '"physical_execution_authority": False',
        '"alpha76_physical_autostart_wired": False',
    ):
        assert needle in combined
    assert ".async_execute_automatic_plan(" not in surface
    assert ".async_execute_automatic_plan(" not in runtime


def test_legacy_alpha35_scheduler_surface_is_not_active():
    bundle = (COMP / "do_plan_grid_support_sensor.py").read_text()
    binary = (COMP / "binary_sensor.py").read_text()
    assert "build_do_plan_scheduler_sensors(coordinator)" not in bundle
    assert "build_do_plan_scheduler_binary_sensors(coordinator)" not in binary
