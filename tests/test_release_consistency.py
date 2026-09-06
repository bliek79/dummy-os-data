"""Release metadata and alpha.12.8 naming/registry consistency checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).parents[1]
MIGRATION_MODULE_PATH = ROOT / "custom_components/dummy_os_data/entity_migrations.py"
MIGRATION_SPEC = importlib.util.spec_from_file_location("entity_migrations", MIGRATION_MODULE_PATH)
assert MIGRATION_SPEC is not None and MIGRATION_SPEC.loader is not None
MIGRATION_MODULE = importlib.util.module_from_spec(MIGRATION_SPEC)
MIGRATION_SPEC.loader.exec_module(MIGRATION_MODULE)
SOLAR_GENERATED_ENTITY_ID_ALIASES = MIGRATION_MODULE.SOLAR_GENERATED_ENTITY_ID_ALIASES
DEGREE_DAYS_GENERATED_ENTITY_ID_ALIASES = MIGRATION_MODULE.DEGREE_DAYS_GENERATED_ENTITY_ID_ALIASES
OBSOLETE_HOME_INPUT_ENTITY_ALIASES = MIGRATION_MODULE.OBSOLETE_HOME_INPUT_ENTITY_ALIASES

VERSION = "0.1.0-alpha.12.13"

EXPECTED_SOLAR_ENTITY_ID_ALIASES = {
    "do_solar_status": "sensor.dummy_os_solar_source_status",
    "do_solar_forecast_timeline": "sensor.dummy_os_solar_forecast_timeline",
    "do_solar_forecast_today_north": "sensor.dummy_os_solar_forecast_today_north",
    "do_solar_forecast_today_south": "sensor.dummy_os_solar_forecast_today_south",
    "do_solar_forecast_today_total": "sensor.dummy_os_solar_forecast_today_total",
    "do_solar_forecast_tomorrow_north": "sensor.dummy_os_solar_forecast_tomorrow_north",
    "do_solar_forecast_tomorrow_south": "sensor.dummy_os_solar_forecast_tomorrow_south",
    "do_solar_forecast_tomorrow_total": "sensor.dummy_os_solar_forecast_tomorrow_total",
    "do_solar_forecast_next_quarter": "sensor.dummy_os_solar_forecast_next_quarter",
    "do_solar_actual_power_north": "sensor.dummy_os_solar_actual_power_north",
    "do_solar_actual_power_south": "sensor.dummy_os_solar_actual_power_south",
    "do_solar_actual_power_total": "sensor.dummy_os_solar_actual_power_total",
    "do_solar_evaluation_last_completed_quarter": "sensor.dummy_os_solar_evaluation_last_completed_quarter",
    "do_solar_evaluation_horizon_1h": "sensor.dummy_os_solar_evaluation_horizon_1h",
    "do_solar_evaluation_horizon_6h": "sensor.dummy_os_solar_evaluation_horizon_6h",
    "do_solar_evaluation_horizon_24h": "sensor.dummy_os_solar_evaluation_horizon_24h",
    "do_solar_evaluation_horizon_48h": "sensor.dummy_os_solar_evaluation_horizon_48h",
    "do_solar_evaluation_horizon_72h": "sensor.dummy_os_solar_evaluation_horizon_72h",
    "do_solar_model": "sensor.dummy_os_solar_forecast_model",
}

EXPECTED_SOURCE_IDS = (
    "do_source_grid_net_power",
    "do_source_grid_import_power",
    "do_source_grid_export_power",
    "do_source_solar_power",
    "do_source_battery_charge_power",
    "do_source_battery_discharge_power",
    "do_source_home_power",
)

EXPECTED_ENERGY_IDS = (
    "do_energy_actual_quarter",
    "do_energy_history_status",
    "do_energy_history_days",
    "do_energy_forecast_model",
    "do_energy_forecast",
    "do_energy_forecast_timeline",
    "do_energy_forecast_next_quarter",
    "do_energy_forecast_coverage",
    "do_energy_forecast_confidence",
    "do_energy_forecast_model_health",
    "do_energy_forecast_accuracy",
    "do_energy_forecast_mae",
    "do_energy_forecast_bias",
    "do_energy_forecast_evaluation_samples",
    "do_energy_forecast_quality_by_daypart",
    "do_energy_forecast_quality_by_day_type",
    "do_energy_forecast_quality_by_day_type_and_daypart",
    "do_energy_forecast_quality_by_hour",
    "do_energy_peak_learning",
)

EXPECTED_DEGREE_DAYS_IDS = (
    "do_degree_days_status",
    "do_degree_days_history_days",
    "do_degree_days_temperature_daily",
    "do_degree_days_daily",
    "do_degree_days_weighted_daily",
    "do_degree_days_reference_daily",
    "do_degree_days_weighted_reference_daily",
    "do_degree_days_difference",
    "do_degree_days_weighted_difference",
    "do_degree_days_last_day",
)

EXPECTED_DEGREE_DAYS_ENTITY_ID_ALIASES = {
    unique_id: f"sensor.dummy_os_forecast_{unique_id}" for unique_id in EXPECTED_DEGREE_DAYS_IDS
}


class ReleaseConsistencyTests(unittest.TestCase):
    def test_manifest_const_and_release_notes_match(self) -> None:
        manifest = json.loads((ROOT / "custom_components/dummy_os_data/manifest.json").read_text())
        const = (ROOT / "custom_components/dummy_os_data/const.py").read_text()
        notes = (ROOT / "RELEASE_NOTES.md").read_text()
        self.assertEqual(manifest["version"], VERSION)
        self.assertEqual(manifest["domain"], "dummy_os_data")
        self.assertEqual(manifest["name"], "Dummy OS Forecast")
        self.assertIn('NAME = "Dummy OS Forecast"', const)
        self.assertIn(f'VERSION = "{VERSION}"', const)
        self.assertIn(f"**Tag:** `{VERSION}`", notes)
        self.assertIn(f"## Dummy OS Forecast {VERSION}", notes)

    def test_translation_key_sets_match(self) -> None:
        strings = json.loads((ROOT / "custom_components/dummy_os_data/strings.json").read_text())
        english = json.loads((ROOT / "custom_components/dummy_os_data/translations/en.json").read_text())
        dutch = json.loads((ROOT / "custom_components/dummy_os_data/translations/nl.json").read_text())
        expected = set(strings["options"]["step"]["init"]["data"])
        self.assertEqual(expected, set(english["options"]["step"]["init"]["data"]))
        self.assertEqual(expected, set(dutch["options"]["step"]["init"]["data"]))
        expected_config = set(strings["config"]["step"]["user"]["data"])
        self.assertEqual(expected_config, set(english["config"]["step"]["user"]["data"]))
        self.assertEqual(expected_config, set(dutch["config"]["step"]["user"]["data"]))
        self.assertEqual(strings["config"]["step"]["user"]["title"], "Dummy OS Forecast")
        self.assertEqual(dutch["options"]["step"]["init"]["title"], "Dummy OS Forecast-opties")

    def test_source_namespace_is_complete_and_canonical(self) -> None:
        sensor_source = (ROOT / "custom_components/dummy_os_data/home_input_sensor.py").read_text()
        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        const_source = (ROOT / "custom_components/dummy_os_data/const.py").read_text()
        coordinator_source = (ROOT / "custom_components/dummy_os_data/coordinator.py").read_text()
        for unique_id in EXPECTED_SOURCE_IDS:
            self.assertIn(unique_id, sensor_source)
        self.assertIn('CANONICAL_HOME_POWER_ENTITY = "sensor.do_source_home_power"', const_source)
        self.assertIn("return CANONICAL_HOME_POWER_ENTITY", coordinator_source)
        self.assertIn('("sensor", "do_data_home_power", "do_source_home_power", "sensor.do_source_home_power")', init_source)
        self.assertNotIn('_attr_unique_id = "do_data_', sensor_source)

    def test_energy_namespace_contains_exact_public_sensor_ids(self) -> None:
        sensor_source = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()
        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        select_source = (ROOT / "custom_components/dummy_os_data/select.py").read_text()
        for unique_id in EXPECTED_ENERGY_IDS:
            self.assertIn(f'_attr_unique_id = "{unique_id}"', sensor_source)
        self.assertEqual(19, sum(sensor_source.count(f'_attr_unique_id = "{unique_id}"') for unique_id in EXPECTED_ENERGY_IDS))
        self.assertIn('_attr_unique_id = "do_energy_profile"', select_source)
        self.assertIn('_attr_name = "DO Energy Profile"', select_source)
        self.assertIn('("select", "do_home_profile", "do_energy_profile", "select.do_energy_profile")', init_source)
        self.assertNotIn('_attr_unique_id = "do_home_', sensor_source)
        self.assertNotIn('_attr_unique_id = "do_home_profile"', select_source)

    def test_degree_days_are_registered_sensor_entities(self) -> None:
        degree_source = (ROOT / "custom_components/dummy_os_data/degree_days.py").read_text()
        entity_source = (ROOT / "custom_components/dummy_os_data/degree_days_sensor.py").read_text()
        sensor_platform = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()
        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        for unique_id in EXPECTED_DEGREE_DAYS_IDS:
            self.assertIn(unique_id, entity_source)
            self.assertIn(f'("sensor", "{unique_id}", "sensor.{unique_id}")', init_source)
        self.assertIn("*build_degree_days_sensors(coordinator)", sensor_platform)
        self.assertNotIn("hass.states.async_set", degree_source)
        self.assertIn("_DEGREE_DAYS_RUNTIME_STATE_ALIASES", init_source)
        self.assertIn('"sensor.do_weighted_degree_days_daily"', init_source)
        self.assertIn('"sensor.do_heat_degree_days_last_day"', init_source)
        self.assertGreaterEqual(init_source.count("_async_remove_degree_days_runtime_states(hass)"), 2)
        self.assertIn("hass.states.async_remove(current_entity_id)", init_source)

    def test_alpha12_degree_days_generated_aliases_are_explicitly_safe(self) -> None:
        self.assertEqual(EXPECTED_DEGREE_DAYS_ENTITY_ID_ALIASES, DEGREE_DAYS_GENERATED_ENTITY_ID_ALIASES)
        self.assertEqual(10, len(DEGREE_DAYS_GENERATED_ENTITY_ID_ALIASES))
        for unique_id, entity_id in EXPECTED_DEGREE_DAYS_ENTITY_ID_ALIASES.items():
            self.assertTrue(MIGRATION_MODULE.is_known_generated_entity_id("sensor", unique_id, entity_id))
            self.assertFalse(MIGRATION_MODULE.is_known_generated_entity_id("sensor", unique_id, f"sensor.user_named_{unique_id}"))

    def test_alpha12_degree_days_stale_states_are_explicitly_cleaned(self) -> None:
        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        for entity_id in EXPECTED_DEGREE_DAYS_ENTITY_ID_ALIASES.values():
            self.assertIn(f'"{entity_id}"', init_source)
        self.assertIn("if registry.async_get(entity_id) is not None:", init_source)
        self.assertIn("hass.states.async_remove(entity_id)", init_source)

    def test_solar_and_weather_display_names_do_not_repeat_dummy_os(self) -> None:
        sensor_source = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()
        solar_source = (ROOT / "custom_components/dummy_os_data/solar_sensor.py").read_text()
        self.assertNotIn('"Dummy OS Weather ', sensor_source)
        self.assertNotIn('f"Dummy OS Weather ', sensor_source)
        self.assertNotIn('"Dummy OS Solar ', solar_source)
        self.assertNotIn('f"Dummy OS Solar ', solar_source)
        self.assertIn('f"DO Weather {label}"', sensor_source)
        self.assertIn('"DO Solar Source Status"', solar_source)

    def test_identity_migrations_cover_all_source_energy_and_profile_entities(self) -> None:
        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        source_pairs = {
            "do_data_grid_net_power": "do_source_grid_net_power",
            "do_data_grid_import_power": "do_source_grid_import_power",
            "do_data_grid_export_power": "do_source_grid_export_power",
            "do_data_solar_power": "do_source_solar_power",
            "do_data_battery_charge_power": "do_source_battery_charge_power",
            "do_data_battery_discharge_power": "do_source_battery_discharge_power",
            "do_data_home_power": "do_source_home_power",
        }
        energy_pairs = {
            "do_home_actual_quarter": "do_energy_actual_quarter",
            "do_home_history_status": "do_energy_history_status",
            "do_home_history_days": "do_energy_history_days",
            "do_home_forecast_model": "do_energy_forecast_model",
            "do_home_forecast": "do_energy_forecast",
            "do_home_forecast_timeline": "do_energy_forecast_timeline",
            "do_home_forecast_next_quarter": "do_energy_forecast_next_quarter",
            "do_home_forecast_coverage": "do_energy_forecast_coverage",
            "do_home_forecast_confidence": "do_energy_forecast_confidence",
            "do_home_forecast_model_health": "do_energy_forecast_model_health",
            "do_home_forecast_accuracy": "do_energy_forecast_accuracy",
            "do_home_forecast_mae": "do_energy_forecast_mae",
            "do_home_forecast_bias": "do_energy_forecast_bias",
            "do_home_forecast_evaluation_samples": "do_energy_forecast_evaluation_samples",
            "dummy_os_data_energy_peak_learning": "do_energy_peak_learning",
        }
        for old, new in {**source_pairs, **energy_pairs}.items():
            self.assertRegex(init_source, rf'\("sensor", "{old}", "{new}", "sensor\.{new}"\)')
        self.assertIn("new_unique_id=new_unique_id", init_source)
        self.assertIn("new_entity_id=target_entity_id", init_source)

    def test_bidirectional_grid_contract_is_fixed(self) -> None:
        sensor_source = (ROOT / "custom_components/dummy_os_data/home_input_sensor.py").read_text()
        config_flow = (ROOT / "custom_components/dummy_os_data/config_flow.py").read_text()
        const_source = (ROOT / "custom_components/dummy_os_data/const.py").read_text()
        self.assertIn('CONF_GRID_NET_POWER_ENTITY = "grid_net_power_entity"', const_source)
        self.assertIn('LEGACY_CONF_GRID_IMPORT_POWER_ENTITY = "grid_import_power_entity"', const_source)
        self.assertIn('LEGACY_CONF_GRID_EXPORT_POWER_ENTITY = "grid_export_power_entity"', const_source)
        self.assertIn("max(grid_net, 0.0)", sensor_source)
        self.assertIn("max(-grid_net, 0.0)", sensor_source)
        self.assertIn("positive_import_negative_export", sensor_source)
        self.assertIn("CONF_GRID_NET_POWER_ENTITY", config_flow)
        self.assertNotIn("\n    CONF_GRID_IMPORT_POWER_ENTITY,", config_flow)
        self.assertNotIn("\n    CONF_GRID_EXPORT_POWER_ENTITY,", config_flow)

    def test_temporary_home_input_aliases_are_explicitly_cleaned(self) -> None:
        expected = {"do_input_home_power_raw", "do_home_power", "do_home_import_power", "do_home_export_power"}
        self.assertEqual(expected, set(OBSOLETE_HOME_INPUT_ENTITY_ALIASES))
        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        self.assertIn("hass.states.async_remove(registered_entity_id)", init_source)
        self.assertIn("hass.states.async_remove(alias_entity_id)", init_source)
        self.assertIn("_is_obsolete_home_input_state", init_source)
        self.assertGreaterEqual(init_source.count("_async_remove_obsolete_home_input_entities(hass)"), 2)

    def test_all_observed_solar_entity_ids_have_exact_migration_aliases(self) -> None:
        self.assertEqual(EXPECTED_SOLAR_ENTITY_ID_ALIASES, SOLAR_GENERATED_ENTITY_ID_ALIASES)
        self.assertEqual(19, len(SOLAR_GENERATED_ENTITY_ID_ALIASES))
        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        for unique_id in EXPECTED_SOLAR_ENTITY_ID_ALIASES:
            self.assertIn(f'("sensor", "{unique_id}", "sensor.{unique_id}")', init_source)

    def test_gas_tariff_uses_internal_options_only(self) -> None:
        prices_source = (ROOT / "custom_components/dummy_os_data/prices.py").read_text()
        self.assertNotIn("GAS_VARIABLE_ADDON_ENTITY", prices_source)
        self.assertNotIn("input_number.gas_markup_per_m3", prices_source)
        self.assertIn("return self._num(CONF_GAS_SUPPLIER) + self._num(CONF_GAS_TAX)", prices_source)
        self.assertIn('"gas_variable_addon_source": "dummy_os_data_options"', prices_source)

    def test_solar_examples_reference_only_registered_entities(self) -> None:
        sensor_source = (ROOT / "custom_components/dummy_os_data/solar_sensor.py").read_text()
        registered_unique_ids = set(re.findall(r'_attr_unique_id = "(do_solar_[^"]+)"', sensor_source))
        registered_unique_ids.update(re.findall(r'object_id = f"(do_solar_[^"]+)', sensor_source))
        for example in (ROOT / "examples").glob("*.yaml"):
            for entity_id in re.findall(r"sensor\.(do_solar_[a-z0-9_]+)", example.read_text()):
                self.assertIn(entity_id, registered_unique_ids, f"{example.name} references unregistered sensor.{entity_id}")
        self.assertIn("do_solar_evaluation_last_completed_quarter", registered_unique_ids)

    def test_solar_horizon_snapshot_release_contract(self) -> None:
        solar_source = (ROOT / "custom_components/dummy_os_data/solar.py").read_text()
        self.assertIn("SOLAR_HORIZON_HOURS = (1, 6, 24, 48, 72)", solar_source)
        self.assertIn('"horizon_snapshots": self._horizon_snapshots', solar_source)
        self.assertIn('self._horizon_snapshots.setdefault(snapshot["snapshot_id"], snapshot)', solar_source)
        self.assertIn('"horizon_snapshot_vs_completed_quarter_v1"', solar_source)
        self.assertIn('"horizon_evaluations"', solar_source)
        self.assertIn('"pending_horizon_snapshot_count"', solar_source)


if __name__ == "__main__":
    unittest.main()
