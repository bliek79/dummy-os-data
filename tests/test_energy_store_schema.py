from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components/dummy_os_data/energy_store.py"
SPEC = importlib.util.spec_from_file_location("energy_store", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

normalize_energy_store_payload = MODULE.normalize_energy_store_payload
UnsupportedEnergyStoreSchema = MODULE.UnsupportedEnergyStoreSchema


def test_legacy_payload_is_upgraded_without_losing_data():
    legacy = {
        "profile": "normal",
        "records": [{"start": "2026-09-01T00:00:00+00:00", "energy_kwh": 0.1}],
        "forecast_snapshots": {"a": {"forecast_kwh": 0.11}},
        "evaluations": [{"forecast_kwh": 0.11, "actual_kwh": 0.1}],
    }

    normalized = normalize_energy_store_payload(
        legacy,
        current_schema_version=1,
        default_profile="normal",
    )

    assert normalized["energy_store_schema_version"] == 1
    assert normalized["profile"] == legacy["profile"]
    assert normalized["records"] == legacy["records"]
    assert normalized["forecast_snapshots"] == legacy["forecast_snapshots"]
    assert normalized["evaluations"] == legacy["evaluations"]
    assert "energy_store_schema_version" not in legacy


def test_current_payload_roundtrips_unchanged_except_copy_identity():
    current = {
        "energy_store_schema_version": 1,
        "profile": "away",
        "records": [{"valid": True}],
        "forecast_snapshots": {"slot": {"captured_at": "2026-09-04T07:00:00+00:00"}},
        "evaluations": [{"evaluation_schema_version": 1}],
        "future_additive_field": {"kept": True},
    }

    normalized = normalize_energy_store_payload(
        current,
        current_schema_version=1,
        default_profile="normal",
    )

    assert normalized == current
    assert normalized is not current


def test_missing_collections_get_safe_empty_defaults():
    normalized = normalize_energy_store_payload(
        {},
        current_schema_version=1,
        default_profile="normal",
    )

    assert normalized == {
        "energy_store_schema_version": 1,
        "profile": "normal",
        "records": [],
        "forecast_snapshots": {},
        "evaluations": [],
    }


def test_future_schema_is_rejected_instead_of_silently_downgraded():
    try:
        normalize_energy_store_payload(
            {"energy_store_schema_version": 2, "records": [{"keep": True}]},
            current_schema_version=1,
            default_profile="normal",
        )
    except UnsupportedEnergyStoreSchema as err:
        assert "supported through 1" in str(err)
    else:
        raise AssertionError("future Energy schema must be rejected")


def test_invalid_schema_type_is_rejected():
    for invalid in (True, "1", 1.0, -1):
        try:
            normalize_energy_store_payload(
                {"energy_store_schema_version": invalid},
                current_schema_version=1,
                default_profile="normal",
            )
        except UnsupportedEnergyStoreSchema:
            pass
        else:
            raise AssertionError(f"invalid schema {invalid!r} must be rejected")


def test_step2_constants_keep_native_storage_and_forecast_contracts():
    const = (ROOT / "custom_components/dummy_os_data/const.py").read_text()
    assert "STORAGE_VERSION = 1" in const
    assert 'STORAGE_KEY = f"{DOMAIN}.home_forecast"' in const
    assert "ENERGY_STORE_SCHEMA_VERSION = 1" in const
    assert "ENERGY_EVALUATION_SCHEMA_VERSION = 1" in const
    assert "QUARTER_MINUTES = 15" in const
    assert "FORECAST_HORIZON_HOURS = 72" in const
    assert "FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES" in const
    assert "MIN_VALID_COVERAGE = 0.90" in const
