from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "dummy_os_data"


def test_execution_preview_identity_is_now_alpha76_runtime_backed():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    bundle = (COMP / "do_plan_grid_support_sensor.py").read_text()
    binary = (COMP / "binary_sensor.py").read_text()
    assert 'unique_id="do_plan_execution_preview"' in surface
    assert 'unique_id="do_plan_execution_preview_ready"' in surface
    assert 'value_key="controller_status"' in surface
    assert 'state_key="controller_ready"' in surface
    assert "build_alpha76_status_sensors(coordinator)" in bundle
    assert "build_alpha76_binary_sensors(coordinator)" in binary


def test_legacy_alpha35_execution_preview_is_not_registered():
    bundle = (COMP / "do_plan_grid_support_sensor.py").read_text()
    binary = (COMP / "binary_sensor.py").read_text()
    assert "build_do_plan_execution_preview_sensors(coordinator)" not in bundle
    assert "build_do_plan_execution_preview_binary_sensors(coordinator)" not in binary


def test_execution_presentation_has_no_physical_control_path():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    runtime = (COMP / "ems_alpha76_runtime.py").read_text()
    for needle in (
        '"shadow_only": True',
        '"physical_execution_authority": False',
        '"alpha76_physical_autostart_wired": False',
    ):
        assert needle in surface + runtime
    assert ".async_execute_automatic_plan(" not in surface
    assert ".async_execute_automatic_plan(" not in runtime
