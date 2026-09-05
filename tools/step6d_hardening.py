from pathlib import Path

path = Path('custom_components/dummy_os_data/evaluation.py')
text = path.read_text()
text = text.replace('PEAK_STRUCTURAL_MIN_EVENT_DAYS = 4\nPEAK_STRUCTURAL_MIN_REPEAT_RATE = 0.35\nPEAK_STABLE_TIMING_MAD_MINUTES = 15.0\n', '')
text = text.replace('coverage = float(item.get("actual_coverage", 1.0))', 'coverage = float(item["actual_coverage"])')
text = text.replace('if merged and merged[-1]["end"] == row["start"] and merged[-1]["local_date"] == row["local_date"]:', 'if merged and merged[-1]["end"] == row["start"]:')
old = '''    classifications = {}\n    for hour in range(24):\n        days = {row["local_date"] for row in by_hour[hour]}\n        hour_events = groups[hour]\n        event_days = {event["local_date"] for event in hour_events}\n        repeat_rate = len(event_days) / len(days) if days else None\n        centers = [event["center_minute_of_day"] for event in hour_events if event["center_minute_of_day"] is not None]\n        timing_mad = _timing_mad_minutes(centers)\n        if not hour_ready[hour]:\n            classification = "unresolved"\n        elif len(event_days) < PEAK_STRUCTURAL_MIN_EVENT_DAYS or (repeat_rate or 0.0) < PEAK_STRUCTURAL_MIN_REPEAT_RATE:\n            classification = "incidental"\n        elif hour == PEAK_GRILL_WINDOW_START_HOUR:\n            classification = "shifting_structural_grill"\n        elif timing_mad is not None and timing_mad <= PEAK_STABLE_TIMING_MAD_MINUTES:\n            classification = "structural"\n        else:\n            classification = "shifting_structural_grill"\n        classifications[f"hour_{hour:02d}"] = {\n            "classification": classification,\n            "event_count": len(hour_events),\n            "event_days": len(event_days),\n            "observed_days": len(days),\n            "repeat_rate": round(repeat_rate, 4) if repeat_rate is not None else None,\n            "timing_mad_minutes": round(timing_mad, 1) if timing_mad is not None else None,\n            "protected_window": hour == PEAK_GRILL_WINDOW_START_HOUR,\n        }\n\n    calibrated_hours = sum(hour_ready.values())\n'''
new = '''    group_metrics: dict[int, dict[str, Any]] = {}\n    repeat_rates_for_calibration: list[float] = []\n    timing_mads_for_calibration: list[float] = []\n    for hour in range(24):\n        days = {row["local_date"] for row in by_hour[hour]}\n        hour_events = groups[hour]\n        event_days = {event["local_date"] for event in hour_events}\n        repeat_rate = len(event_days) / len(days) if days else None\n        centers = [event["center_minute_of_day"] for event in hour_events if event["center_minute_of_day"] is not None]\n        timing_mad = _timing_mad_minutes(centers)\n        group_metrics[hour] = {\n            "event_count": len(hour_events),\n            "event_days": len(event_days),\n            "observed_days": len(days),\n            "repeat_rate": repeat_rate,\n            "timing_mad_minutes": timing_mad,\n        }\n        # A single event is by definition not repetition. Numeric separation\n        # between low/high recurrence is calibrated from the observed history.\n        if hour_ready[hour] and len(event_days) >= 2 and repeat_rate is not None:\n            repeat_rates_for_calibration.append(repeat_rate)\n            if timing_mad is not None:\n                timing_mads_for_calibration.append(timing_mad)\n\n    repeat_rate_threshold = _median(repeat_rates_for_calibration)\n    timing_mad_threshold = _median(timing_mads_for_calibration)\n    classifications = {}\n    for hour in range(24):\n        metrics = group_metrics[hour]\n        repeat_rate = metrics["repeat_rate"]\n        timing_mad = metrics["timing_mad_minutes"]\n        if not hour_ready[hour]:\n            classification = "unresolved"\n        elif metrics["event_days"] < 2:\n            classification = "incidental"\n        elif repeat_rate_threshold is None:\n            classification = "unresolved"\n        elif repeat_rate is None or repeat_rate < repeat_rate_threshold:\n            classification = "incidental"\n        elif hour == PEAK_GRILL_WINDOW_START_HOUR:\n            classification = "shifting_structural_grill"\n        elif timing_mad_threshold is None or timing_mad is None:\n            classification = "unresolved"\n        elif timing_mad <= timing_mad_threshold:\n            classification = "structural"\n        else:\n            classification = "shifting_structural_grill"\n        classifications[f"hour_{hour:02d}"] = {\n            "classification": classification,\n            "event_count": metrics["event_count"],\n            "event_days": metrics["event_days"],\n            "observed_days": metrics["observed_days"],\n            "repeat_rate": round(repeat_rate, 4) if repeat_rate is not None else None,\n            "timing_mad_minutes": round(timing_mad, 1) if timing_mad is not None else None,\n            "protected_window": hour == PEAK_GRILL_WINDOW_START_HOUR,\n        }\n\n    calibrated_hours = sum(hour_ready.values())\n'''
if old not in text:
    raise RuntimeError('classification block not found')
text = text.replace(old, new, 1)
old_return = '''    return {\n        "schema_version": 1,\n        "algorithm_version": "peak_observer_v1",\n        "profile": profile,\n'''
new_return = '''    from hashlib import sha256\n    from json import dumps\n    source_basis = {\n        "evaluation_count": len(prepared),\n        "first_start": min((row["start"] for row in prepared), default=None).isoformat() if prepared else None,\n        "last_start": max((row["start"] for row in prepared), default=None).isoformat() if prepared else None,\n    }\n    fingerprint_payload = {\n        "algorithm_version": "peak_observer_v1",\n        "profile": profile,\n        "source_basis": source_basis,\n        "calibration": calibration,\n        "repeat_rate_threshold": repeat_rate_threshold,\n        "timing_mad_threshold": timing_mad_threshold,\n    }\n    calibration_fingerprint = sha256(dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]\n\n    return {\n        "schema_version": 1,\n        "algorithm_version": "peak_observer_v1",\n        "calibration_fingerprint": calibration_fingerprint,\n        "source_basis": source_basis,\n        "profile": profile,\n'''
if old_return not in text:
    raise RuntimeError('return anchor not found')
text = text.replace(old_return, new_return, 1)
text = text.replace('        "calibrated_hours": calibrated_hours,\n        "calibration": calibration,', '        "calibrated_hours": calibrated_hours,\n        "classification_calibration": {\n            "repeat_rate_threshold": round(repeat_rate_threshold, 4) if repeat_rate_threshold is not None else None,\n            "timing_mad_threshold_minutes": round(timing_mad_threshold, 1) if timing_mad_threshold is not None else None,\n            "basis": "median_of_repeating_ready_hours",\n        },\n        "calibration": calibration,', 1)
path.write_text(text)

sensor = Path('custom_components/dummy_os_data/sensor.py')
text = sensor.read_text()
text = text.replace('            "algorithm_version": result["algorithm_version"],\n            "profile": result["profile"],', '            "algorithm_version": result["algorithm_version"],\n            "calibration_fingerprint": result["calibration_fingerprint"],\n            "source_basis": result["source_basis"],\n            "profile": result["profile"],', 1)
text = text.replace('            "calibrated_hours": result["calibrated_hours"],\n            "protected_windows": result["protected_windows"],', '            "calibrated_hours": result["calibrated_hours"],\n            "classification_calibration": result["classification_calibration"],\n            "protected_windows": result["protected_windows"],', 1)
sensor.write_text(text)

tests = Path('tests/test_peak_learning.py')
text = tests.read_text()
text += r'''


def test_missing_actual_coverage_is_not_assumed_valid():
    start = datetime(2026, 8, 1, 17, 0, tzinfo=timezone.utc)
    rows = flat_basis(8, 17)
    rows[0].pop('actual_coverage')
    result = module.calculate_peak_learning(rows, 'normal', localize)
    assert result['calibration']['hour_17']['sample_count'] == 31
    assert result['calibration']['hour_17']['status'] == 'collecting'


def test_calibration_fingerprint_is_deterministic():
    rows = flat_basis(9, 17)
    first = module.calculate_peak_learning(rows, 'normal', localize)
    second = module.calculate_peak_learning(rows, 'normal', localize)
    assert first['calibration_fingerprint'] == second['calibration_fingerprint']
    assert len(first['calibration_fingerprint']) == 16


def test_classification_thresholds_are_history_derived_or_null():
    result = module.calculate_peak_learning(flat_basis(9, 17), 'normal', localize)
    calibration = result['classification_calibration']
    assert calibration['basis'] == 'median_of_repeating_ready_hours'
    assert calibration['repeat_rate_threshold'] is None
    assert calibration['timing_mad_threshold_minutes'] is None
'''
tests.write_text(text)

notes = Path('RELEASE_NOTES.md')
text = notes.read_text()
text = text.replace('- Observer-only classificaties `incidental`, `structural`, `shifting_structural_grill` en `unresolved`.\n', '- Observer-only classificaties `incidental`, `structural`, `shifting_structural_grill` en `unresolved`; recurrence- en timinggrenzen worden uit de beschikbare historie gekalibreerd en niet als vaste woning-specifieke waarden ingevoerd.\n')
text = text.replace('- Contracttests voor minimum databasis, profielscheiding en null-semantiek.\n', '- Contracttests voor minimum databasis, profielscheiding, null-semantiek en ontbrekende coverage.\n- Deterministische calibration fingerprint en historie-afgeleide classificatiegrenzen.\n')
notes.write_text(text)
