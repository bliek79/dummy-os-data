from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "dummy_os_data"


def test_preview_consumes_published_upstream_contracts_only():
    source = (ROOT / "do_plan_preview_sensor.py").read_text(encoding="utf-8")
    assert "_build_plan_input_from_snapshot" not in source
    assert "_build_reserve_from_snapshot" not in source
    assert '"dependency_mode"] = "published_upstream_contracts"' in source
    assert 'async_get_entity_id("sensor", DOMAIN, unique_id)' in source


def test_grid_support_entity_consumes_published_contracts_with_reserve_handoff():
    source = (ROOT / "do_plan_grid_support_sensor.py").read_text(encoding="utf-8")
    assert "_build_plan_input_from_snapshot(snapshot)" not in source
    assert "_build_energy_need_from_snapshot(snapshot)" not in source
    assert "_build_reserve_from_snapshot(snapshot)" not in source
    assert 'result["dependency_mode"] = "published_upstream_contracts_with_reserve_handoff"' in source
    assert '_state_contract(self.hass, "do_plan_input_72h")' in source
    assert '_state_contract(self.hass, "do_plan_energy_need")' in source
    assert '_state_contract(self.hass, "do_plan_reserve_soc")' in source
    assert "DummyOSPlanStoreBridgeSensor" not in source
    assert "build_alpha76_status_sensors(coordinator)" in source


def test_retained_refresh_key_remains_pure_and_material_change_based():
    source = (ROOT / "do_plan_grid_support_sensor.py").read_text(encoding="utf-8")
    assert "def build_plan_store_bridge_refresh_key" in source
    assert 'hashlib.sha256(_stable_material(material).encode("utf-8")).hexdigest()' in source
    assert "from .ems_alpha76_surface import build_alpha76_status_sensors" in source
    # The import must remain inside the builder so pure helper tests do not pull
    # in full Home Assistant platform modules.
    before_builder = source.split("def build_do_plan_grid_support_sensors", 1)[0]
    assert "ems_alpha76_surface" not in before_builder


def test_performance_hotfix_does_not_add_control_authority():
    preview = (ROOT / "do_plan_preview_sensor.py").read_text(encoding="utf-8")
    grid = (ROOT / "do_plan_grid_support_sensor.py").read_text(encoding="utf-8")
    for source in (preview, grid):
        assert "async_call(" not in source
        assert "command_dispatched=True" not in source
        assert "physical_execution_authority=True" not in source
