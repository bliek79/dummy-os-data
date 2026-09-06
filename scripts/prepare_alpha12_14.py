from pathlib import Path
import json

OLD = "0.1.0-alpha.12.13"
NEW = "0.1.0-alpha.12.14"

sensor = Path("custom_components/dummy_os_data/sensor.py")
text = sensor.read_text()
text = text.replace(
    "from .evaluation import calculate_day_type_daypart_quality, calculate_day_type_quality, calculate_daypart_quality, calculate_hour_quality, calculate_peak_learning\n",
    "from .evaluation import calculate_day_type_daypart_quality, calculate_day_type_quality, calculate_daypart_quality, calculate_hour_quality, calculate_peak_learning\nfrom .time_windows import calculate_time_windows\n",
)
anchor = "            DummyOSEnergyPeakLearningSensor(coordinator),\n"
addition = anchor + "            DummyOSEnergyTimeWindowsSensor(coordinator),\n"
assert anchor in text
text = text.replace(anchor, addition, 1)
class_anchor = "\n\nclass DummyOSEnergyPeakLearningSensor(DummyOSBaseSensor):\n"
assert class_anchor in text
new_class = '''\n\nclass DummyOSEnergyTimeWindowsSensor(DummyOSBaseSensor):
    \"\"\"Observer-only Step 7 Energy Time Windows diagnostics.\"\"\"

    _attr_name = \"DO Energy Time Windows\"
    _attr_unique_id = \"do_energy_time_windows\"
    _attr_suggested_object_id = \"do_energy_time_windows\"
    _attr_icon = \"mdi:timeline-clock-outline\"

    def _result(self) -> dict[str, Any]:
        peak_result = calculate_peak_learning(self.coordinator.evaluations, self.coordinator.profile, dt_util.as_local)
        return calculate_time_windows(peak_result, self.coordinator.profile, dt_util.as_local)

    @property
    def native_value(self) -> str:
        return str(self._result()[\"status\"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._result()
        return {
            \"schema_version\": result[\"schema_version\"],
            \"algorithm_version\": result[\"algorithm_version\"],
            \"profile\": result[\"profile\"],
            \"context_key\": result[\"context_key\"],
            \"classification_source\": result[\"classification_source\"],
            \"observer_only\": result[\"observer_only\"],
            \"forecast_influence_enabled\": result[\"forecast_influence_enabled\"],
            \"ready_for_live_observation\": result[\"ready_for_live_observation\"],
            \"ready_for_forecast_influence\": result[\"ready_for_forecast_influence\"],
            \"event_count\": result[\"event_count\"],
            \"event_days\": result[\"event_days\"],
            \"rejected_event_count\": result[\"rejected_event_count\"],
            \"reject_reasons\": result[\"reject_reasons\"],
            \"window_start\": result[\"window_start\"],
            \"window_end\": result[\"window_end\"],
            \"window_width_minutes\": result[\"window_width_minutes\"],
            \"window_quarter_count\": result[\"window_quarter_count\"],
            \"p10_start_minute\": result[\"p10_start_minute\"],
            \"p90_end_minute\": result[\"p90_end_minute\"],
            \"median_center_minute\": result[\"median_center_minute\"],
            \"center_mad_minutes\": result[\"center_mad_minutes\"],
            \"contained_day_count\": result[\"contained_day_count\"],
            \"contained_day_ratio\": result[\"contained_day_ratio\"],
            \"median_event_duration_minutes\": result[\"median_event_duration_minutes\"],
            \"median_daily_energy_kwh\": result[\"median_daily_energy_kwh\"],
            \"energy_iqr_kwh\": result[\"energy_iqr_kwh\"],
            \"lodo_max_start_shift_minutes\": result[\"lodo_max_start_shift_minutes\"],
            \"lodo_max_end_shift_minutes\": result[\"lodo_max_end_shift_minutes\"],
            \"early_late_start_shift_minutes\": result[\"early_late_start_shift_minutes\"],
            \"early_late_end_shift_minutes\": result[\"early_late_end_shift_minutes\"],
            \"protected_window_overlap\": result[\"protected_window_overlap\"],
            \"native_resolution_minutes\": result[\"native_resolution_minutes\"],
            \"calibration_method\": result[\"calibration_method\"],
            \"minimum_event_days_collecting_exit\": result[\"minimum_event_days_collecting_exit\"],
            \"minimum_event_days_calibrated\": result[\"minimum_event_days_calibrated\"],
            \"minimum_event_days_stable\": result[\"minimum_event_days_stable\"],
            \"maximum_boundary_shift_minutes\": result[\"maximum_boundary_shift_minutes\"],
            \"source_basis\": result[\"source_basis\"],
            \"calibration_fingerprint\": result[\"calibration_fingerprint\"],
            \"blockers\": result[\"blockers\"],
        }
'''
text = text.replace(class_anchor, new_class + class_anchor, 1)
sensor.write_text(text)

const = Path("custom_components/dummy_os_data/const.py")
text = const.read_text(); assert f'VERSION = "{OLD}"' in text
const.write_text(text.replace(f'VERSION = "{OLD}"', f'VERSION = "{NEW}"'))

manifest = Path("custom_components/dummy_os_data/manifest.json")
data = json.loads(manifest.read_text()); assert data["version"] == OLD
data["version"] = NEW
manifest.write_text(json.dumps(data, indent=2) + "\n")

release_test = Path("tests/test_release_consistency.py")
text = release_test.read_text()
text = text.replace(f'VERSION = "{OLD}"', f'VERSION = "{NEW}"')
text = text.replace('    "do_energy_peak_learning",\n)', '    "do_energy_peak_learning",\n    "do_energy_time_windows",\n)')
text = text.replace('self.assertEqual(19, sum(sensor_source.count(f\'_attr_unique_id = "{unique_id}"\') for unique_id in EXPECTED_ENERGY_IDS))', 'self.assertEqual(20, sum(sensor_source.count(f\'_attr_unique_id = "{unique_id}"\') for unique_id in EXPECTED_ENERGY_IDS))')
release_test.write_text(text)

Path("tests/test_time_windows.py").write_text(r'''import importlib.util
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
    starts = [17 * 60] * 8 + [18 * 60] * 8
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
''')

Path("RELEASE_NOTES.md").write_text('''# GitHub Release

**Tag:** `0.1.0-alpha.12.14`  
**Release title:** Dummy OS Forecast 0.1.0-alpha.12.14 - Energy Time Windows Observer

## Dummy OS Forecast 0.1.0-alpha.12.14

Observer-only implementatie van Energy Forecast Stap 7D. Time Windows vertaalt uitsluitend door Peak Learning als `shifting_structural_grill` geclassificeerde events naar een diagnostisch lokaal tijdvenster. Er is geen forecast- of plannerinvloed.

### Nieuw
- Canonieke Home Assistant-entiteit `sensor.do_energy_time_windows`.
- `unique_id`: `do_energy_time_windows`.
- `suggested_object_id`: `do_energy_time_windows`.
- Friendly name: `DO Energy Time Windows`.
- Dagrepresentatieven zodat iedere lokale eventdag maximaal eenmaal meetelt.
- Deterministische p10-start / p90-eind-kalibratie met native 15-minuten-uitlijning.
- Leave-one-day-out stabiliteit vanaf 12 eventdagen.
- Early/late stabiliteitscontrole vanaf 16 eventdagen.
- Statussen `blocked`, `collecting`, `calibrating`, `calibrated_observer_only`, `stable_observer_only` en `unstable_no_window`.
- Strikte null-semantiek en compacte publieke attributen conform schema `7b.1`.

### Identity / compatibiliteit
- Eerste officiële Time Windows-identity; er wordt bewust geen fictieve legacy-migratie toegevoegd.
- Canonieke tuple: `sensor.do_energy_time_windows` / `do_energy_time_windows` / `do_energy_time_windows`.
- Geen alias-sensor, geen `do_home_*`, geen `dummy_os_data_*` identity en geen geaccepteerde `_2`-fallback.

### Bescherming
- Alleen `shifting_structural_grill` is window-eligible.
- 17:00-18:00 blijft protected; er wordt geen `preferred_quarter`, `fixed_peak_quarter` of andere exact-quarter waarheid gepubliceerd.
- `observer_only=true`, `forecast_influence_enabled=false` en `ready_for_forecast_influence=false` blijven altijd actief in Stap 7D.

### Ongewijzigd
- Native architectuur blijft exact 15 minuten / 72 uur / 288 slots.
- Geen wijziging aan Energy Forecast-waarden, confidence, recency, fallback, plannerfeed of uitvoering.
- Normal en Away blijven strikt gescheiden.
- Missing, unavailable en niet-berekende waarden worden nooit stilzwijgend nul.

### Validatie
- Contracttests voor collecting/null, quarter-alignment, stabiele en instabiele vensters, profielscheiding, classification eligibility en deterministic fingerprint.
- Identity- en publieke-attributengrenstest voor `sensor.do_energy_time_windows`.
- Regressietest voor 15 minuten / 72 uur / 288 slots.
- Volledige testsuite, Python compile en manifest JSON-validatie vóór release.
''')
