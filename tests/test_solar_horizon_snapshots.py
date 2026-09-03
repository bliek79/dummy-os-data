"""Regression checks for persistent Solar horizon snapshots."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOLAR = ROOT / "custom_components" / "dummy_os_data" / "solar.py"


def _source() -> str:
    return SOLAR.read_text(encoding="utf-8")


def test_solar_source_parses() -> None:
    ast.parse(_source())


def test_required_horizons_are_fixed() -> None:
    source = _source()
    assert "SOLAR_HORIZON_HOURS = (1, 6, 24, 48, 72)" in source


def test_snapshots_are_persistent_and_immutable() -> None:
    source = _source()
    assert '"horizon_snapshots": self._horizon_snapshots' in source
    assert 'stored.get("horizon_snapshots")' in source
    assert 'self._horizon_snapshots.setdefault(snapshot["snapshot_id"], snapshot)' in source


def test_quarter_boundary_captures_future_horizons() -> None:
    source = _source()
    boundary = source.index("boundary_utc = floor_slot_start(now_utc, QUARTER_MINUTES)")
    finalize = source.index("self._finalize_quarter(boundary_utc)")
    capture = source.index("self._capture_horizon_snapshots(boundary_utc)")
    start = source.index("self._start_quarter(boundary_utc, scheduled_boundary=True)")
    assert boundary < finalize < capture < start


def test_horizon_evaluation_is_export_ready() -> None:
    source = _source()
    assert '"horizon_evaluations"' in source
    assert '"horizon_evaluation_count"' in source
    assert '"horizon_hours_supported"' in source
    assert '"horizon_snapshot_vs_completed_quarter_v1"' in source
    for horizon in (1, 6, 24, 48, 72):
        assert f"{horizon}" in source
    for field in (
        "forecast_captured_at",
        "forecast_total_kwh",
        "actual_total_kwh",
        "error_total_kwh",
        "absolute_error_total_kwh",
        "bias_total_percent",
        "accuracy_total_percent",
        "coverage_total_percent",
    ):
        assert f'"{field}"' in source
