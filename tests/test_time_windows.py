import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

path = Path("custom_components/dummy_os_data/time_windows.py")
spec = importlib.util.spec_from_file_location("time_windows", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def localize(value):
    return value


def peak_result(days=0, starts=None, profile="normal", classification="shifting_structural_grill"):
    starts = starts or [17 * 60 + 15] * days
    events = []
    origin = datetime(2026, 8, 1, tzinfo=timezone.utc)
    for day, minute in enumerate(starts):
        start = origin + timedelta(days=day, hours=minute // 60, minutes=minute % 60)
        end = start + timedelta(minutes=30)
        events.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "local_date": start.date().isoformat(),
            "quarter_count": 2,
            "duration_minutes": 30,
            "extra_energy_kwh": 0.8,
            "max_positive_residual_kwh": 0.5,
            "peak_quarter_start": start.isoformat(),
            "center_minute_of_day": minute + 15.0,
        })
    return {
        "schema_version": 1,
        "algorithm_version": "peak_observer_v1",
        "calibration_fingerprint": "abc123",
        "source_basis": {"evaluation_count": 100},
        "profile": profile,
        "classifications": {"hour_17": {"classification": classification}},
        "events": events,
    }


def test_collecting_null_semantics():
    result = module.calculate_time_windows(peak_result(days=5), "normal", localize)
    assert result["status"] == "collecting"
    assert result["event_days"] == 5
    assert result["window_start"] is None
    assert result["p10_start_minute"] is None
    assert result["blockers"] == ["insufficient_event_days"]


def test_calibrating_candidate_is_quarter_aligned():
    result = module.calculate_time_windows(peak_result(days=8), "normal", localize)
    assert result["status"] == "calibrating"
    assert result["window_start"] == "17:15"
    assert result["window_end"] == "17:45"
    assert result["window_quarter_count"] == 2
    assert result["protected_window_overlap"] is True


def test_stable_observer_only_after_16_stable_days():
    result = module.calculate_time_windows(peak_result(days=16), "normal", localize)
    assert result["status"] == "stable_observer_only"
    assert result["ready_for_live_observation"] is True
    assert result["ready_for_forecast_influence"] is False
    assert result["lodo_max_start_shift_minutes"] == 0.0
    assert result["early_late_start_shift_minutes"] == 0.0


def test_unstable_has_no_public_window():
    starts = [17 * 60] * 8 + [17 * 60 + 45] * 8
    result = module.calculate_time_windows(peak_result(starts=starts), "normal", localize)
    assert result["status"] == "unstable_no_window"
    assert result["window_start"] is None
    assert result["window_end"] is None
    assert result["p10_start_minute"] is not None
    assert result["blockers"] == ["unstable_window_boundaries"]


def test_profile_mismatch_blocks():
    result = module.calculate_time_windows(peak_result(days=8, profile="away"), "normal", localize)
    assert result["status"] == "blocked"
    assert "invalid_profile" in result["blockers"]


def test_noneligible_classification_does_not_create_window():
    result = module.calculate_time_windows(peak_result(days=16, classification="incidental"), "normal", localize)
    assert result["status"] == "collecting"
    assert result["event_count"] == 0
    assert result["rejected_event_count"] == 16
    assert result["window_start"] is None


def test_fingerprint_is_deterministic_and_profile_specific():
    basis = peak_result(days=16)
    first = module.calculate_time_windows(basis, "normal", localize)
    second = module.calculate_time_windows(basis, "normal", localize)
    assert first["calibration_fingerprint"] == second["calibration_fingerprint"]
    away_basis = peak_result(days=16, profile="away")
    away = module.calculate_time_windows(away_basis, "away", localize)
    assert first["calibration_fingerprint"] != away["calibration_fingerprint"]


def test_sensor_identity_and_public_attribute_boundary():
    text = Path("custom_components/dummy_os_data/sensor.py").read_text()
    assert '_attr_name = "DO Energy Time Windows"' in text
    assert '_attr_unique_id = "do_energy_time_windows"' in text
    assert '_attr_suggested_object_id = "do_energy_time_windows"' in text
    assert text.count("DummyOSEnergyTimeWindowsSensor(coordinator)") == 1
    assert '"events": result["events"]' not in text[text.index("class DummyOSEnergyTimeWindowsSensor"):text.index("class DummyOSEnergyPeakLearningSensor")]
    assert "preferred_quarter" not in Path("custom_components/dummy_os_data/time_windows.py").read_text()


def test_native_forecast_contract_unchanged():
    text = Path("custom_components/dummy_os_data/const.py").read_text()
    assert "QUARTER_MINUTES = 15" in text
    assert "FORECAST_HORIZON_HOURS = 72" in text
    assert "FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES" in text
