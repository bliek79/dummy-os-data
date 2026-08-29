"""Unit tests for Solar model calculations without Home Assistant runtime."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "dummy_os_data" / "solar_model.py"
SPEC = importlib.util.spec_from_file_location("solar_model", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
solar_model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(solar_model)


class SolarModelTests(unittest.TestCase):
    def test_zero_and_negative_irradiance(self) -> None:
        self.assertEqual(solar_model.pv_power_kw(0, 2.96, 2.45, 0.9), 0.0)
        self.assertEqual(solar_model.pv_power_kw(-20, 2.96, 2.45, 0.9), 0.0)

    def test_power_formula_and_ac_cap(self) -> None:
        self.assertEqual(solar_model.pv_power_kw(500, 2.96, 2.45, 0.9), 1.332)
        self.assertEqual(solar_model.pv_power_kw(1200, 2.96, 2.45, 0.9), 2.45)

    def test_quarter_energy(self) -> None:
        self.assertEqual(solar_model.slot_energy_kwh(2.0), 0.5)

    def test_backward_average_timestamp_maps_to_slot_start(self) -> None:
        stamp = datetime(2026, 8, 29, 10, 15, tzinfo=timezone.utc)
        self.assertEqual(
            solar_model.backward_average_slot_start(stamp),
            datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        )

    def test_actual_split_preserves_total(self) -> None:
        north, south = solar_model.split_ac_power(3000, 2000, 1000)
        self.assertEqual(north, 2000.0)
        self.assertEqual(south, 1000.0)

    def test_actual_split_requires_ratio_when_generating(self) -> None:
        self.assertEqual(solar_model.split_ac_power(1000, 0, 0), (None, None))
        self.assertEqual(solar_model.split_ac_power(0, 0, 0), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
