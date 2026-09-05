from pathlib import Path
import json

EVALUATION_APPEND = r'''

# STEP6D_PEAK_LEARNING_OBSERVER_V1
PEAK_MINIMUM_SAMPLES_PER_HOUR = 32
PEAK_MINIMUM_DISTINCT_DAYS_PER_HOUR = 8
PEAK_THRESHOLD_QUANTILE = 0.90
PEAK_STRUCTURAL_MIN_EVENT_DAYS = 4
PEAK_STRUCTURAL_MIN_REPEAT_RATE = 0.35
PEAK_STABLE_TIMING_MAD_MINUTES = 15.0
PEAK_GRILL_WINDOW_START_HOUR = 17


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _median(values: list[float]) -> float | None:
    return _quantile(values, 0.5)


def _timing_mad_minutes(event_centers: list[float]) -> float | None:
    center = _median(event_centers)
    if center is None:
        return None
    return _median([abs(value - center) for value in event_centers])


def calculate_peak_learning(evaluations: list[dict[str, Any]], profile: str, localize) -> dict[str, Any]:
    """Return observer-only Step 6 peak calibration and classification."""
    prepared: list[dict[str, Any]] = []
    for item in evaluations:
        if item.get("profile") != profile:
            continue
        start = _parse_aware_start(item.get("start"))
        end = _parse_aware_start(item.get("end"))
        if start is None or end is None:
            continue
        try:
            actual = float(item["actual_kwh"])
            forecast = float(item["forecast_kwh"])
            coverage = float(item.get("actual_coverage", 1.0))
        except (KeyError, TypeError, ValueError):
            continue
        if coverage < 0.90:
            continue
        local_start = localize(start)
        prepared.append({
            "start": start,
            "end": end,
            "local_start": local_start,
            "local_date": local_start.date().isoformat(),
            "local_hour": local_start.hour,
            "positive_residual_kwh": max(actual - forecast, 0.0),
        })

    by_hour = {hour: [] for hour in range(24)}
    for row in prepared:
        by_hour[row["local_hour"]].append(row)

    calibration = {}
    hour_ready = {}
    for hour in range(24):
        rows = by_hour[hour]
        days = {row["local_date"] for row in rows}
        ready = len(rows) >= PEAK_MINIMUM_SAMPLES_PER_HOUR and len(days) >= PEAK_MINIMUM_DISTINCT_DAYS_PER_HOUR
        hour_ready[hour] = ready
        threshold = _quantile([row["positive_residual_kwh"] for row in rows], PEAK_THRESHOLD_QUANTILE) if ready else None
        calibration[f"hour_{hour:02d}"] = {
            "status": "calibrated" if ready else "collecting",
            "sample_count": len(rows),
            "distinct_days": len(days),
            "threshold_kwh": round(threshold, 6) if threshold is not None else None,
        }

    candidates = []
    for row in prepared:
        comparison_rows = [other for other in by_hour[row["local_hour"]] if other["local_date"] != row["local_date"]]
        comparison_days = {other["local_date"] for other in comparison_rows}
        if len(comparison_rows) < PEAK_MINIMUM_SAMPLES_PER_HOUR or len(comparison_days) < PEAK_MINIMUM_DISTINCT_DAYS_PER_HOUR:
            continue
        threshold = _quantile([other["positive_residual_kwh"] for other in comparison_rows], PEAK_THRESHOLD_QUANTILE)
        if threshold is not None and row["positive_residual_kwh"] > threshold:
            candidates.append({**row, "threshold_kwh": threshold})

    candidates.sort(key=lambda row: row["start"])
    merged = []
    for row in candidates:
        if merged and merged[-1]["end"] == row["start"] and merged[-1]["local_date"] == row["local_date"]:
            merged[-1]["end"] = row["end"]
            merged[-1]["quarters"].append(row)
        else:
            merged.append({"start": row["start"], "end": row["end"], "local_date": row["local_date"], "quarters": [row]})

    events = []
    for event in merged:
        quarters = event["quarters"]
        residuals = [q["positive_residual_kwh"] for q in quarters]
        total = sum(residuals)
        weighted_center = None
        if total > 0:
            weighted_center = sum((q["local_start"].hour * 60 + q["local_start"].minute + 7.5) * q["positive_residual_kwh"] for q in quarters) / total
        peak = max(quarters, key=lambda q: q["positive_residual_kwh"])
        events.append({
            "start": event["start"].isoformat(),
            "end": event["end"].isoformat(),
            "local_date": event["local_date"],
            "quarter_count": len(quarters),
            "duration_minutes": len(quarters) * 15,
            "extra_energy_kwh": round(total, 6),
            "max_positive_residual_kwh": round(peak["positive_residual_kwh"], 6),
            "peak_quarter_start": peak["start"].isoformat(),
            "center_minute_of_day": round(weighted_center, 1) if weighted_center is not None else None,
        })

    groups = {hour: [] for hour in range(24)}
    for event in events:
        start = _parse_aware_start(event["start"])
        if start is not None:
            groups[localize(start).hour].append(event)

    classifications = {}
    for hour in range(24):
        days = {row["local_date"] for row in by_hour[hour]}
        hour_events = groups[hour]
        event_days = {event["local_date"] for event in hour_events}
        repeat_rate = len(event_days) / len(days) if days else None
        centers = [event["center_minute_of_day"] for event in hour_events if event["center_minute_of_day"] is not None]
        timing_mad = _timing_mad_minutes(centers)
        if not hour_ready[hour]:
            classification = "unresolved"
        elif len(event_days) < PEAK_STRUCTURAL_MIN_EVENT_DAYS or (repeat_rate or 0.0) < PEAK_STRUCTURAL_MIN_REPEAT_RATE:
            classification = "incidental"
        elif hour == PEAK_GRILL_WINDOW_START_HOUR:
            classification = "shifting_structural_grill"
        elif timing_mad is not None and timing_mad <= PEAK_STABLE_TIMING_MAD_MINUTES:
            classification = "structural"
        else:
            classification = "shifting_structural_grill"
        classifications[f"hour_{hour:02d}"] = {
            "classification": classification,
            "event_count": len(hour_events),
            "event_days": len(event_days),
            "observed_days": len(days),
            "repeat_rate": round(repeat_rate, 4) if repeat_rate is not None else None,
            "timing_mad_minutes": round(timing_mad, 1) if timing_mad is not None else None,
            "protected_window": hour == PEAK_GRILL_WINDOW_START_HOUR,
        }

    calibrated_hours = sum(hour_ready.values())
    if not prepared or calibrated_hours == 0:
        status = "collecting"
    elif calibrated_hours < 24:
        status = "calibrating"
    else:
        status = "calibrated_observer_only"

    return {
        "schema_version": 1,
        "algorithm_version": "peak_observer_v1",
        "profile": profile,
        "status": status,
        "observer_only": True,
        "forecast_influence_enabled": False,
        "ready_for_model_influence": False,
        "minimum_samples_per_hour": PEAK_MINIMUM_SAMPLES_PER_HOUR,
        "minimum_distinct_days_per_hour": PEAK_MINIMUM_DISTINCT_DAYS_PER_HOUR,
        "threshold_method": "leave_one_local_day_out_positive_residual_quantile",
        "threshold_quantile": PEAK_THRESHOLD_QUANTILE,
        "candidate_count": len(candidates),
        "event_count": len(events),
        "calibrated_hours": calibrated_hours,
        "calibration": calibration,
        "classifications": classifications,
        "protected_windows": {"17:00-18:00": {"policy": "no_exact_quarter_structural", "forced_classification_when_repeating": "shifting_structural_grill"}},
        "events": events,
    }
'''

SENSOR_APPEND = r'''

class DummyOSEnergyPeakLearningSensor(DummyOSBaseSensor):
    """Observer-only Step 6 Energy peak learning diagnostics."""

    _attr_name = "DO Energy Peak Learning"
    _attr_unique_id = "dummy_os_data_energy_peak_learning"
    _attr_suggested_object_id = "do_energy_peak_learning"
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _unrecorded_attributes = frozenset({"calibration", "classifications", "events"})

    def _result(self) -> dict[str, Any]:
        return calculate_peak_learning(self.coordinator.evaluations, self.coordinator.profile, dt_util.as_local)

    @property
    def native_value(self) -> str:
        return str(self._result()["status"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._result()
        return {
            "schema_version": result["schema_version"],
            "algorithm_version": result["algorithm_version"],
            "profile": result["profile"],
            "observer_only": True,
            "forecast_influence_enabled": False,
            "ready_for_model_influence": False,
            "minimum_samples_per_hour": result["minimum_samples_per_hour"],
            "minimum_distinct_days_per_hour": result["minimum_distinct_days_per_hour"],
            "threshold_method": result["threshold_method"],
            "threshold_quantile": result["threshold_quantile"],
            "candidate_count": result["candidate_count"],
            "event_count": result["event_count"],
            "calibrated_hours": result["calibrated_hours"],
            "protected_windows": result["protected_windows"],
            "calibration": result["calibration"],
            "classifications": result["classifications"],
            "events": result["events"],
        }
'''

evaluation = Path("custom_components/dummy_os_data/evaluation.py")
text = evaluation.read_text()
if "# STEP6D_PEAK_LEARNING_OBSERVER_V1" not in text:
    evaluation.write_text(text + EVALUATION_APPEND)

sensor = Path("custom_components/dummy_os_data/sensor.py")
text = sensor.read_text()
old_import = "from .evaluation import calculate_day_type_daypart_quality, calculate_day_type_quality, calculate_daypart_quality, calculate_hour_quality"
new_import = old_import + ", calculate_peak_learning"
if old_import in text and "calculate_peak_learning" not in text.split("\n", 30)[-1]:
    text = text.replace(old_import, new_import, 1)
anchor = "            DummyOSHomeForecastQualityByHourSensor(coordinator),\n"
if "DummyOSEnergyPeakLearningSensor(coordinator)" not in text:
    if anchor not in text:
        raise RuntimeError("sensor registration anchor missing")
    text = text.replace(anchor, anchor + "            DummyOSEnergyPeakLearningSensor(coordinator),\n", 1)
if "class DummyOSEnergyPeakLearningSensor" not in text:
    text += SENSOR_APPEND
sensor.write_text(text)

const = Path("custom_components/dummy_os_data/const.py")
text = const.read_text().replace('VERSION = "0.1.0-alpha.12.11"', 'VERSION = "0.1.0-alpha.12.12"')
const.write_text(text)

manifest = Path("custom_components/dummy_os_data/manifest.json")
payload = json.loads(manifest.read_text())
payload["version"] = "0.1.0-alpha.12.12"
manifest.write_text(json.dumps(payload, indent=2) + "\n")

Path("tests/test_peak_learning.py").write_text(r'''from datetime import datetime, timedelta, timezone
from custom_components.dummy_os_data.evaluation import calculate_peak_learning


def _localize(value): return value

def _row(start, forecast, actual, profile="normal", coverage=1.0):
    return {"start": start.isoformat(), "end": (start + timedelta(minutes=15)).isoformat(), "profile": profile, "forecast_kwh": forecast, "actual_kwh": actual, "actual_coverage": coverage}

def _basis(days=12, hour=17, peak_minute=15):
    rows=[]; origin=datetime(2026,8,1,tzinfo=timezone.utc)
    for day in range(days):
        for minute in (0,15,30,45):
            actual=0.55 if minute==peak_minute and day%2==0 else 0.10
            rows.append(_row(origin+timedelta(days=day,hours=hour,minutes=minute),0.10,actual))
    return rows

def test_collecting_keeps_missing_threshold_null():
    result=calculate_peak_learning(_basis(days=2),"normal",_localize)
    assert result["status"]=="collecting"
    assert result["calibration"]["hour_17"]["threshold_kwh"] is None
    assert result["forecast_influence_enabled"] is False

def test_minimum_basis_32_quarters_8_days():
    result=calculate_peak_learning(_basis(days=8),"normal",_localize)
    assert result["calibration"]["hour_17"]["sample_count"]==32
    assert result["calibration"]["hour_17"]["distinct_days"]==8
    assert result["calibration"]["hour_17"]["status"]=="calibrated"

def test_profile_separation():
    rows=_basis(days=8)+[_row(datetime(2026,9,1,17,tzinfo=timezone.utc),0.1,5.0,profile="away")]
    result=calculate_peak_learning(rows,"normal",_localize)
    assert result["calibration"]["hour_17"]["sample_count"]==32

def test_1700_window_not_exact_structural():
    result=calculate_peak_learning(_basis(days=12),"normal",_localize)
    assert result["classifications"]["hour_17"]["classification"]!="structural"
    assert result["protected_windows"]["17:00-18:00"]["policy"]=="no_exact_quarter_structural"

def test_native_forecast_contract_unchanged():
    from custom_components.dummy_os_data.const import QUARTER_MINUTES, FORECAST_HORIZON_HOURS, FORECAST_SLOTS
    assert (QUARTER_MINUTES,FORECAST_HORIZON_HOURS,FORECAST_SLOTS)==(15,72,288)
''')

Path("RELEASE_NOTES.md").write_text('''# Dummy OS Forecast 0.1.0-alpha.12.12 - Energy Peak Learning Observer\n\n## Nieuw\n- Observer-only Energy Peak Learning op bestaande forward-looking Energy-evaluaties.\n- Nieuwe canonieke entiteit `sensor.do_energy_peak_learning`.\n- Kandidaatpieken via positieve residual en leave-one-local-day-out kalibratie.\n- Aangrenzende piekkwartieren worden samengevoegd tot één event.\n- Classificaties: `incidental`, `structural`, `shifting_structural_grill`, `unresolved`.\n- 17:00-18:00 blijft beschermd als structureel grillig venster.\n\n## Identity contract\n- entity_id: `sensor.do_energy_peak_learning`\n- unique_id: `dummy_os_data_energy_peak_learning`\n- suggested_object_id: `do_energy_peak_learning`\n- geen bedoelde alias; afwijkende alias vereist cleanup/migratie.\n\n## Ongewijzigd\n- 15 minuten / 72 uur / 288 slots.\n- Geen wijziging in forecast.py of forecastwaarden.\n- Geen planner-, execution-, confidence-, recency-, fallback- of Step-7 invloed.\n- Missing/niet-berekend blijft null en wordt nooit nul.\n\n## Validatie\n- Peak Learning contracttests, volledige test-suite, compile en JSON-validatie.\n- Na installatie live entity/state/attributes controleren.\n''')

for temporary in (Path("__noop__"),):
    if temporary.exists(): temporary.unlink()
