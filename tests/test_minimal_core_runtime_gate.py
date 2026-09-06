"""Regression gate for the Dummy OS Forecast Minimal Core runtime."""

from __future__ import annotations

import ast
from pathlib import Path


COORDINATOR = Path("custom_components/dummy_os_data/coordinator.py")


def _method_source(method_name: str) -> str:
    source = COORDINATOR.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"method {method_name!r} not found")


def test_fast_home_power_updates_do_not_notify_forecast_entities() -> None:
    """A live power sample may integrate energy, but must not fan out into forecast analysis."""
    method = _method_source("_async_source_changed")
    assert "_integrate_until" in method
    assert "_last_power_w" in method
    assert "_notify" not in method


def test_quarter_boundary_remains_the_energy_forecast_refresh_point() -> None:
    """Completed quarters still publish the refreshed Energy Forecast state."""
    method = _method_source("_async_quarter_boundary")
    assert "_finalize_quarter" in method
    assert "_notify" in method


def test_profile_change_still_refreshes_energy_forecast_state() -> None:
    """A deliberate profile change remains a relevant forecast refresh trigger."""
    method = _method_source("async_set_profile")
    assert "_notify" in method
