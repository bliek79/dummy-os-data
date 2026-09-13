from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_preview_sensor_is_registered_once() -> None:
    sensor_source = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()
    adapter_source = (ROOT / "custom_components/dummy_os_data/do_plan_preview_sensor.py").read_text()
    assert sensor_source.count("build_do_plan_preview_sensors") == 2
    assert 'from .do_plan_preview_sensor import build_do_plan_preview_sensors' in sensor_source
    assert '*build_do_plan_preview_sensors(coordinator),' in sensor_source
    assert '_attr_unique_id = "do_plan_preview"' in adapter_source
    assert '_attr_suggested_object_id = "do_plan_preview"' in adapter_source
    assert '_attr_name = "DO Plan Preview"' in adapter_source


def test_preview_keeps_observer_only_authority_contract() -> None:
    core = (ROOT / "custom_components/dummy_os_data/do_plan_preview.py").read_text()
    assert '"shadow_only": True' in core
    assert '"active_use_permitted": False' in core
    assert '"physical_execution_authority": False' in core
    assert '"reserve_recalculated": False' in core
    assert '"prices_fallback_used"' in core
    assert '"missing_as_zero_used": False' in core
    assert '"calculation_scope": "planner_preview_reliable_prefix"' in core
    assert '"losses_included": True' in core
    assert '"preview_decision"' in core
    assert 'trade_rows_excluded_interpolated' in core


def test_preview_uses_separate_import_and_export_economics() -> None:
    core = (ROOT / "custom_components/dummy_os_data/do_plan_preview.py").read_text()
    assert '"best_self_use_discharge_import_price"' in core
    assert '"best_export_discharge_export_price"' in core
    assert '"best_self_use_margin"' in core
    assert '"best_export_margin"' in core
    assert 'export_price = _finite(raw.get("export_price"))' in core
    assert 'export_price = import_price' not in core


def test_preview_defaults_match_current_planner_design() -> None:
    adapter = (ROOT / "custom_components/dummy_os_data/do_plan_preview_sensor.py").read_text()
    assert 'CHARGE_EFFICIENCY_PERCENT = 92.0' in adapter
    assert 'DISCHARGE_EFFICIENCY_PERCENT = 92.0' in adapter
    assert 'MINIMUM_TRADE_MARGIN = 0.10' in adapter
    assert 'MAX_CHARGE_POWER_W = 3200' in adapter
    assert 'MAX_DISCHARGE_POWER_W = 3200' in adapter
