from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "dummy_os_data"


def test_safety_identity_is_now_alpha76_runtime_backed():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    bundle = (COMP / "do_plan_grid_support_sensor.py").read_text()
    binary = (COMP / "binary_sensor.py").read_text()
    assert 'unique_id="do_plan_safety"' in surface
    assert 'value_key="safety_status"' in surface
    assert 'state_key="safety_safe"' in surface
    assert "build_alpha76_status_sensors(coordinator)" in bundle
    assert "build_alpha76_binary_sensors(coordinator)" in binary
    assert "build_do_plan_safety_sensors(coordinator)" not in bundle


def test_dormant_alpha35_safety_adapter_still_contains_no_service_writes():
    adapter = (COMP / "do_plan_safety_sensor.py").read_text()
    core = (COMP / "do_plan_safety.py").read_text()
    combined = core + adapter
    for forbidden in ("async_call(", "services.async_call"):
        assert forbidden not in combined


def test_active_alpha76_safety_presentation_contains_no_physical_execution_call():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    runtime = (COMP / "ems_alpha76_runtime.py").read_text()
    assert '"shadow_only": True' in surface
    assert '"physical_execution_authority": False' in surface
    assert '"alpha76_physical_autostart_wired": False' in runtime
    assert ".async_execute_automatic_plan(" not in surface
    assert ".async_execute_automatic_plan(" not in runtime


def test_alpha76_safety_source_remains_immutable_vendored_authority():
    source = (COMP / "ems_alpha76" / "safety_guard.py").read_text()
    assert "class AnkerEmsSafetyGuard" in source
