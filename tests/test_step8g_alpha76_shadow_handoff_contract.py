from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "dummy_os_data"


def test_shadow_handoff_reproduces_only_alpha76_pre_execution_steps():
    source = (ROOT / "button.py").read_text(encoding="utf-8")
    assert 'async_set_value(\n            self.slot, "execution_mode", "direct"' in source
    assert 'async_mark_lifecycle(\n            self.slot, "pending", "shadow_start_ready_validation"' in source
    assert "await self.runtime.async_request_refresh()" in source
    assert "async_execute_selected_plan" not in source.replace(
        '``execution.async_execute_selected_plan()``', ""
    )
    assert "async_execute_automatic_plan" not in source
    assert "services.async_call" not in source
    assert "hass.services" not in source


def test_shadow_handoff_surface_keeps_physical_authority_closed():
    source = (ROOT / "button.py").read_text(encoding="utf-8")
    for marker in (
        '"shadow_only": True',
        '"simulation_mode": True',
        '"physical_execution_authority": False',
        '"alpha76_physical_autostart_wired": False',
        '"execution_controller_called": False',
    ):
        assert marker in source


def test_button_platform_is_registered_and_alpha39_versioned():
    const = (ROOT / "const.py").read_text(encoding="utf-8")
    manifest = (ROOT / "manifest.json").read_text(encoding="utf-8")
    assert '"button"' in const
    assert 'VERSION = "0.2.0-alpha.39"' in const
    assert '"version": "0.2.0-alpha.39"' in manifest


def test_shadow_handoff_uses_exact_vendored_plan_store_lifecycle_api():
    button = (ROOT / "button.py").read_text(encoding="utf-8")
    plan_store = (ROOT / "ems_alpha76" / "plan_store.py").read_text(encoding="utf-8")
    scheduler = (ROOT / "ems_alpha76" / "scheduler.py").read_text(encoding="utf-8")
    assert "async_mark_lifecycle" in plan_store
    assert 'lifecycle_status == "concept"' in scheduler
    assert 'detail["status"] = "concept"' in scheduler
    assert "runtime.plan_store" in button
