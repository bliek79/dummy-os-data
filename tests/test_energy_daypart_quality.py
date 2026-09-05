from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components/dummy_os_data/evaluation.py"
SPEC = importlib.util.spec_from_file_location("energy_evaluation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

calculate_daypart_quality = MODULE.calculate_daypart_quality


def _iso(local_text: str) -> str:
    local = datetime.fromisoformat(local_text).replace(tzinfo=ZoneInfo("Europe/Amsterdam"))
    return local.astimezone(timezone.utc).isoformat()


def _record(local_text: str, profile: str = "normal", valid: bool = True):
    return {"start": _iso(local_text), "profile": profile, "valid": valid}


def _evaluation(local_text: str, actual: float = 1.0, forecast: float = 1.1, profile: str = "normal"):
    return {"start": _iso(local_text), "profile": profile, "actual_kwh": actual, "forecast_kwh": forecast}


def _localize(value):
    return value.astimezone(ZoneInfo("Europe/Amsterdam"))


def test_fixed_boundaries_assign_exact_quarters_to_expected_dayparts():
    times = ["2026-09-05T00:00", "2026-09-05T05:45", "2026-09-05T06:00", "2026-09-05T11:45", "2026-09-05T12:00", "2026-09-05T17:45", "2026-09-05T18:00", "2026-09-05T23:45"]
    records = [_record(t) for t in times]
    evaluations = [_evaluation(t) for t in times]
    result = calculate_daypart_quality(evaluations, records, "normal", _localize)
    for name in ("night", "morning", "afternoon", "evening"):
        assert result["dayparts"][name]["sample_count"] == 2
        assert result["dayparts"][name]["valid_actual_quarters"] == 2
        assert result["dayparts"][name]["evaluation_coverage_percent"] == 100.0


def test_profile_is_strict_and_invalid_actuals_do_not_enter_coverage_denominator():
    records = [
        _record("2026-09-05T06:00", "normal", True),
        _record("2026-09-05T06:15", "normal", False),
        _record("2026-09-05T06:30", "away", True),
    ]
    evaluations = [
        _evaluation("2026-09-05T06:00", profile="normal"),
        _evaluation("2026-09-05T06:30", profile="away"),
    ]
    result = calculate_daypart_quality(evaluations, records, "normal", _localize)
    morning = result["dayparts"]["morning"]
    assert morning["sample_count"] == 1
    assert morning["valid_actual_quarters"] == 1
    assert morning["evaluation_coverage_percent"] == 100.0


def test_missing_evaluation_values_are_skipped_not_zeroed():
    records = [_record("2026-09-05T12:00"), _record("2026-09-05T12:15")]
    evaluations = [
        _evaluation("2026-09-05T12:00", actual=1.0, forecast=1.2),
        {"start": _iso("2026-09-05T12:15"), "profile": "normal", "actual_kwh": None, "forecast_kwh": 0.0},
    ]
    result = calculate_daypart_quality(evaluations, records, "normal", _localize)
    afternoon = result["dayparts"]["afternoon"]
    assert afternoon["sample_count"] == 1
    assert afternoon["mae_kwh"] == 0.2
    assert afternoon["bias_kwh"] == 0.2
    assert afternoon["evaluation_coverage_percent"] == 50.0


def test_readiness_requires_32_samples_per_daypart():
    records = []
    evaluations = []
    for hour in (0, 6, 12, 18):
        for index in range(32):
            day = 1 + index // 4
            minute = (index % 4) * 15
            local_text = f"2026-09-{day:02d}T{hour:02d}:{minute:02d}"
            records.append(_record(local_text))
            evaluations.append(_evaluation(local_text))
    result = calculate_daypart_quality(evaluations, records, "normal", _localize)
    assert result["status"] == "sufficient_basis"
    assert all(item["status"] == "sufficient_basis" for item in result["dayparts"].values())


def test_dst_conversion_uses_local_quarter_start():
    # 2026-10-25 is the Europe/Amsterdam DST fallback day. Both UTC instants
    # map to a local 02:15 quarter and therefore remain in the night segment.
    records = [
        {"start": "2026-10-25T00:15:00+00:00", "profile": "normal", "valid": True},
        {"start": "2026-10-25T01:15:00+00:00", "profile": "normal", "valid": True},
    ]
    evaluations = [
        {"start": item["start"], "profile": "normal", "actual_kwh": 1.0, "forecast_kwh": 1.0}
        for item in records
    ]
    result = calculate_daypart_quality(evaluations, records, "normal", _localize)
    assert result["dayparts"]["night"]["sample_count"] == 2
    assert result["dayparts"]["night"]["valid_actual_quarters"] == 2
