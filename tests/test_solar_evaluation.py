"""Unit tests for Solar quarter evaluation without Home Assistant runtime."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "dummy_os_data"
    / "solar_evaluation.py"
)
SPEC = importlib.util.spec_from_file_location("solar_evaluation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
solar_evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(solar_evaluation)


class SolarEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start = datetime(2026, 8, 30, 14, 0, tzinfo=timezone.utc)
        self.forecast = {
            "north_kwh": 0.15,
            "south_kwh": 0.075,
            "total_kwh": 0.225,
            "provider": "open_meteo",
            "model": "open_meteo_gti_physical_v0.1",
            "source_update": (self.start - timedelta(minutes=59)).isoformat(),
            "captured_at": self.start.isoformat(),
        }

    def test_valid_quarter_is_flat_and_sheets_ready(self) -> None:
        record = solar_evaluation.build_quarter_evaluation(
            self.start,
            self.forecast,
            {
                "north": 0.15 * 3_600_000,
                "south": 0.075 * 3_600_000,
                "total": 0.225 * 3_600_000,
            },
            {"north": 900, "south": 900, "total": 900},
            sample_count=45,
            min_coverage=0.9,
        )
        self.assertEqual(record["status"], "ok")
        self.assertTrue(record["valid"])
        self.assertEqual(record["slot_id"], self.start.isoformat())
        self.assertEqual(record["actual_total_kwh"], 0.225)
        self.assertEqual(record["error_total_kwh"], 0.0)
        self.assertEqual(record["accuracy_total_percent"], 100.0)
        self.assertTrue(record["valid_total"])
        self.assertEqual(record["coverage_total_seconds"], 900.0)
        self.assertEqual(record["resolution_minutes"], 15)
        self.assertFalse(any(isinstance(value, dict) for value in record.values()))

    def test_late_forecast_snapshot_is_rejected(self) -> None:
        late = dict(self.forecast)
        late["captured_at"] = (self.start + timedelta(seconds=1)).isoformat()
        record = solar_evaluation.build_quarter_evaluation(
            self.start,
            late,
            {"north": 0, "south": 0, "total": 0},
            {"north": 900, "south": 900, "total": 900},
            sample_count=1,
            min_coverage=0.9,
        )
        self.assertEqual(record["status"], "missing_or_late_forecast_snapshot")
        self.assertFalse(record["valid"])
        self.assertIsNone(record["forecast_total_kwh"])

    def test_inconsistent_forecast_total_is_rejected(self) -> None:
        inconsistent = dict(self.forecast)
        inconsistent["total_kwh"] = 0.3
        record = solar_evaluation.build_quarter_evaluation(
            self.start,
            inconsistent,
            {"north": 0, "south": 0, "total": 0},
            {"north": 900, "south": 900, "total": 900},
            sample_count=1,
            min_coverage=0.9,
        )
        self.assertEqual(record["status"], "missing_or_late_forecast_snapshot")
        self.assertIsNone(record["forecast_total_kwh"])

    def test_missing_roof_coverage_is_not_silently_zeroed(self) -> None:
        record = solar_evaluation.build_quarter_evaluation(
            self.start,
            self.forecast,
            {"north": 0, "south": 0, "total": 0},
            {"north": 800, "south": 900, "total": 900},
            sample_count=20,
            min_coverage=0.9,
        )
        self.assertEqual(record["status"], "insufficient_roof_coverage")
        self.assertFalse(record["valid"])
        self.assertIsNone(record["actual_north_kwh"])
        self.assertEqual(record["actual_total_kwh"], 0.0)

    def test_total_coverage_below_threshold_is_invalid(self) -> None:
        record = solar_evaluation.build_quarter_evaluation(
            self.start,
            self.forecast,
            {"north": 0, "south": 0, "total": 0},
            {"north": 900, "south": 900, "total": 800},
            sample_count=20,
            min_coverage=0.9,
        )
        self.assertEqual(record["status"], "insufficient_total_coverage")
        self.assertIsNone(record["actual_total_kwh"])


if __name__ == "__main__":
    unittest.main()
