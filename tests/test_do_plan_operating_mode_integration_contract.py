from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "dummy_os_data"


def read(name: str) -> str:
    return (COMP / name).read_text(encoding="utf-8")


def test_alpha35_operating_mode_is_removed_from_active_public_surface() -> None:
    select_py = read("select.py")
    aggregate = read("do_plan_grid_support_sensor.py")
    assert 'do_plan_operating_mode' not in select_py
    assert 'DummyOSPlanOperatingModeSelect' not in select_py
    assert 'build_do_plan_operating_mode_sensors' not in aggregate
    assert 'build_alpha76_plan_select_entities' in select_py


def test_alpha76_execution_mode_is_per_plan_store_slot() -> None:
    surface = read("ems_alpha76_surface.py")
    assert '"execution_mode"' in surface
    assert '["direct", "gepland"]' in surface
    assert 'self.plan_store = runtime.plan_store' in surface
    assert 'await self.plan_store.async_set_value' in surface


def test_no_physical_execution_path_is_added() -> None:
    surface = read("ems_alpha76_surface.py")
    runtime = read("ems_alpha76_runtime.py")
    assert '"physical_execution_authority": False' in surface
    assert '"shadow_only": True' in surface
    assert '"alpha76_physical_autostart_wired": False' in runtime
    assert '.async_execute_automatic_plan(' not in surface
    assert '.async_execute_automatic_plan(' not in runtime


def test_native_forecast_architecture_is_untouched() -> None:
    const = read("const.py")
    assert 'QUARTER_MINUTES = 15' in const
    assert 'FORECAST_HORIZON_HOURS = 72' in const
    assert 'FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES' in const
