from pathlib import Path

ROOT = Path(__file__).parents[1]
SENSOR_PATH = ROOT / "custom_components" / "dummy_os_data" / "do_plan_72h_sensor.py"


def _source() -> str:
    return SENSOR_PATH.read_text(encoding="utf-8")


def test_plan72_keeps_large_alpha76_payload_out_of_ha_state_and_recorder() -> None:
    source = _source()
    assert '"alpha76_plan72",' in source
    assert 'result.pop("alpha76_plan72", None)' in source


def test_plan72_bypasses_raw_soc_parent_subscriptions() -> None:
    source = _source()
    assert "await SensorEntity.async_added_to_hass(self)" in source
    assert "RAW_SOC_ENTITY" not in source
    assert "self._handle_soc_update" not in source


def test_plan72_filters_noisy_solar_and_price_notifications_by_source_signature() -> None:
    source = _source()
    assert "_solar_source_signature" in source
    assert "solar.last_successful_update" in source
    assert "solar.source_point_count" in source
    assert "_price_source_signature" in source
    assert "prices.source_generated_at" in source
    assert "prices.forecast_generated_at" in source
    assert "if signature == self._last_solar_source_signature" in source
    assert "if signature == self._last_price_source_signature" in source


def test_plan72_has_bounded_periodic_refresh_window() -> None:
    source = _source()
    assert "async_track_time_change" in source
    assert "minute=5" in source
    assert "second=0" in source
    assert "if 5 <= local.hour < 22:" in source


def test_plan72_only_uses_soc_contract_for_recovery_not_continuous_soc_refresh() -> None:
    source = _source()
    assert '"do_plan_soc_contract"' in source
    assert "_handle_soc_contract_recovery" in source
    assert 'new_state.state != "ready"' in source
    assert 'old_state.state == "ready"' in source
    assert 'getattr(self, "_last_soc_bridge_valid", True) is False' in source


def test_plan72_refresh_load_fix_does_not_open_physical_execution_path() -> None:
    source = _source()
    assert "hass.services.async_call" not in source
    assert '"active_use_permitted": True' not in source
    assert '"physical_execution_authority": True' not in source
