"""Step 8B contract: HA controls/status point to alpha76 and stay shadow-only."""
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "dummy_os_data"


def text(name: str) -> str:
    return (COMP / name).read_text(encoding="utf-8")


def test_plan_platform_authority_is_alpha76_surface() -> None:
    for platform, builder in (
        ("number.py", "build_alpha76_plan_number_entities"),
        ("datetime.py", "build_alpha76_plan_datetime_entities"),
        ("select.py", "build_alpha76_plan_select_entities"),
    ):
        source = text(platform)
        assert builder in source
        assert "get_do_plan_manual_interface_runtime" not in source


def test_exact_alpha76_plan_store_fields_are_the_storage_contract() -> None:
    surface = text("ems_alpha76_surface.py")
    plan_store = text("ems_alpha76/plan_store.py")
    for field in (
        '"action"',
        '"execution_mode"',
        '"start_time"',
        '"power_w"',
        '"target_soc"',
        '"max_runtime_h"',
        '"max_start_delay_min"',
    ):
        assert field in plan_store
        assert field in surface
    assert "self.plan_store = runtime.plan_store" in surface
    assert "await self.plan_store.async_set_value" in surface


def test_scheduler_safety_and_execution_presentation_use_alpha76_runtime() -> None:
    binary = text("binary_sensor.py")
    surface = text("ems_alpha76_surface.py")
    assert "build_alpha76_binary_sensors" in binary
    assert "build_do_plan_scheduler_binary_sensors" not in binary
    assert "build_do_plan_execution_preview_binary_sensors" not in binary
    for key in (
        'state_key="scheduler_ready"',
        'state_key="safety_safe"',
        'state_key="controller_ready"',
        'state_key="execution_active"',
    ):
        assert key in surface
    assert '"ems_authority": "alpha76_runtime"' in surface


def test_shadow_boundary_is_hard_closed() -> None:
    surface = text("ems_alpha76_surface.py")
    runtime = text("ems_alpha76_runtime.py")
    assert '"shadow_only": True' in surface
    assert '"physical_execution_authority": False' in surface
    assert "def simulation_mode" in runtime
    assert "return True" in runtime
    assert '"alpha76_runtime_shadow_only": True' in runtime
    assert '"alpha76_physical_autostart_wired": False' in runtime
    assert ".async_execute_automatic_plan(" not in surface
    assert ".async_execute_automatic_plan(" not in runtime


def test_non_ems_controls_are_preserved() -> None:
    select = text("select.py")
    datetime = text("datetime.py")
    switch = text("switch.py")
    assert "DummyOSEnergyProfileSelect" in select
    assert "DummyOSPresenceAwayStart" in datetime
    assert "DummyOSPresenceAwayEnd" in datetime
    assert "DummyOSPresenceAwayScheduleEnabled" in switch


def test_runtime_contract_remains_native_15m_72h_288() -> None:
    runtime = text("ems_alpha76_runtime.py")
    assert '"alpha76_input_resolution_minutes": 15' in runtime
    assert '"alpha76_input_slot_count": 288' in runtime
    assert '"forecast_horizon_hours": 72' in runtime
