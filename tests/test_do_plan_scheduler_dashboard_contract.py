from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "dummy_os_data"


def test_scheduler_dashboard_identities_are_alpha76_runtime_backed():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    binary = (COMP / "binary_sensor.py").read_text()
    bundle = (COMP / "do_plan_grid_support_sensor.py").read_text()
    assert 'unique_id="do_plan_scheduler"' in surface
    assert 'unique_id="do_plan_scheduler_ready"' in surface
    assert 'value_key="scheduler_status"' in surface
    assert 'state_key="scheduler_ready"' in surface
    assert "build_alpha76_binary_sensors" in binary
    assert "build_alpha76_status_sensors(coordinator)" in bundle


def test_scheduler_presentation_reads_exact_runtime_data():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    assert '"ems_authority": "alpha76_runtime"' in surface
    assert 'self.runtime.data.get(self.value_key)' in surface
    assert 'self.runtime.data.get(self.state_key) is True' in surface


def test_scheduler_dashboard_stays_shadow_only():
    surface = (COMP / "ems_alpha76_surface.py").read_text()
    runtime = (COMP / "ems_alpha76_runtime.py").read_text()
    for needle in (
        '"shadow_only": True',
        '"physical_execution_authority": False',
        '"alpha76_physical_autostart_wired": False',
    ):
        assert needle in surface + runtime
    assert '.async_execute_automatic_plan(' not in surface
    assert '.async_execute_automatic_plan(' not in runtime


def test_legacy_alpha35_scheduler_is_not_registered():
    binary = (COMP / "binary_sensor.py").read_text()
    bundle = (COMP / "do_plan_grid_support_sensor.py").read_text()
    assert "build_do_plan_scheduler_binary_sensors" not in binary
    assert "build_do_plan_scheduler_sensors(coordinator)" not in bundle
