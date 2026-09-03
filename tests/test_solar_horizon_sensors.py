"""Regression checks for Solar horizon evaluation sensors."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOLAR_SENSOR = ROOT / "custom_components" / "dummy_os_data" / "solar_sensor.py"


def _source() -> str:
    return SOLAR_SENSOR.read_text(encoding="utf-8")


def test_solar_sensor_source_parses() -> None:
    ast.parse(_source())


def test_all_fixed_horizon_sensors_are_built() -> None:
    source = _source()
    assert "SOLAR_HORIZON_HOURS" in source
    assert "DummyOSSolarHorizonEvaluationSensor" in source
    assert "for horizon_hours in SOLAR_HORIZON_HOURS" in source


def test_horizon_sensor_has_stable_identity() -> None:
    source = _source()
    assert 'object_id = f"do_solar_evaluation_horizon_{horizon_hours}h"' in source
    assert "self._attr_unique_id = object_id" in source
    assert "self._attr_suggested_object_id = object_id" in source


def test_horizon_sensor_exposes_existing_evaluation_record() -> None:
    source = _source()
    assert "self.solar.last_horizon_evaluations" in source
    assert 'evaluation.get("horizon_hours", 0)' in source
    assert 'return evaluation.get("snapshot_id") if evaluation else None' in source
    assert "return dict(evaluation)" in source


def test_horizon_sensor_waiting_state_is_explicit() -> None:
    source = _source()
    assert '"status": "waiting_for_first_completed_horizon"' in source
    assert '"horizon_hours": self.horizon_hours' in source
