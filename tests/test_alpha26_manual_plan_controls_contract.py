"""Regression contract for the native manual plan control surface.

The entity identities introduced in alpha26 remain usable, but from Step 8B the
control authority is the exact EMS alpha76 Plan Store rather than the retired
Alpha35 shadow/manual store.
"""
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "dummy_os_data"


def text(name: str) -> str:
    return (COMP / name).read_text(encoding="utf-8")


def test_platform_contract_remains_present() -> None:
    const = text("const.py")
    assert '"number"' in const
    assert "FORECAST_HORIZON_HOURS = 72" in const
    assert "FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES" in const


def test_current_plan_platforms_delegate_to_alpha76_surface() -> None:
    number = text("number.py")
    datetime = text("datetime.py")
    select = text("select.py")
    assert "build_alpha76_plan_number_entities" in number
    assert "build_alpha76_plan_datetime_entities" in datetime
    assert "build_alpha76_plan_select_entities" in select
    assert "get_do_plan_manual_interface_runtime" not in number
    assert "get_do_plan_manual_interface_runtime" not in datetime
    assert "get_do_plan_manual_interface_runtime" not in select


def test_three_slots_keep_current_identities_and_exact_alpha76_fields() -> None:
    surface = text("ems_alpha76_surface.py")
    assert "PLAN_SLOT_COUNT" in surface
    assert '"power_w", "power_w"' in surface
    assert '"target_soc_percent", "target_soc"' in surface
    assert '"max_runtime_minutes", "max_runtime_h"' in surface
    assert '"max_start_delay_minutes", "max_start_delay_min"' in surface
    assert '"execution_mode"' in surface
    assert '["geen", "laden", "ontladen"]' in surface
    assert '["direct", "gepland"]' in surface


def test_plan_store_is_alpha76_and_surface_stays_shadow_only() -> None:
    surface = text("ems_alpha76_surface.py")
    runtime = text("ems_alpha76_runtime.py")
    assert "self.plan_store = runtime.plan_store" in surface
    assert "await self.plan_store.async_set_value" in surface
    assert '"ems_authority": "alpha76_plan_store"' in surface
    assert '"shadow_only": True' in surface
    assert '"physical_execution_authority": False' in surface
    assert "def simulation_mode" in runtime
    assert "return True" in runtime
    assert '"alpha76_physical_autostart_wired": False' in runtime
    assert "async_execute_automatic_plan" not in surface
