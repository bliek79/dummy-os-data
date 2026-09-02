"""Release metadata consistency checks."""

from __future__ import annotations

import json
import importlib.util
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
OBSOLETE_HOME_INPUT_ENTITY_ALIASES = MIGRATION_MODULE.OBSOLETE_HOME_INPUT_ENTITY_ALIASES
is_known_generated_entity_id = MIGRATION_MODULE.is_known_generated_entity_id

VERSION = "0.1.0-alpha.11.5"

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
    "do_solar_model": "sensor.dummy_os_solar_forecast_model",
}

EXPECTED_DATA_POWER_IDS = (
    "do_data_grid_net_power",
    "do_data_grid_import_power",
    "do_data_grid_export_power",
    "do_data_solar_power",
    "do_data_battery_charge_power",
    "do_data_battery_discharge_power",
    "do_data_home_power",
)


class ReleaseConsistencyTests(unittest.TestCase):
    def test_manifest_const_and_release_notes_match(self) -> None:
        manifest = json.loads((ROOT / "custom_components/dummy_os_data/manifest.json").read_text())
        const = (ROOT / "custom_components/dummy_os_data/const.py").read_text()
        notes = (ROOT / "RELEASE_NOTES.md").read_text()
        self.assertEqual(manifest["version"], VERSION)
        self.assertIn(f'VERSION = "{VERSION}"', const)
        self.assertIn(f"**Tag:** `{VERSION}`", notes)
        self.assertIn(f"## Dummy OS Data {VERSION}", notes)

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

    def test_all_observed_solar_entity_ids_have_exact_migration_aliases(self) -> None:
        self.assertEqual(EXPECTED_SOLAR_ENTITY_ID_ALIASES, SOLAR_GENERATED_ENTITY_ID_ALIASES)
        self.assertEqual(14, len(SOLAR_GENERATED_ENTITY_ID_ALIASES))
        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        for unique_id in EXPECTED_SOLAR_ENTITY_ID_ALIASES:
            self.assertIn(f'("sensor", "{unique_id}", "sensor.{unique_id}")', init_source)

    def test_data_power_entities_use_definitive_ids(self) -> None:
        sensor_source = (ROOT / "custom_components/dummy_os_data/home_input_sensor.py").read_text()
        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        sensor_platform = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()
        for unique_id in EXPECTED_DATA_POWER_IDS:
            self.assertIn(unique_id, sensor_source)
            self.assertIn(f'("sensor", "{unique_id}", "sensor.{unique_id}")', init_source)
        self.assertIn("*build_home_input_sensors(coordinator)", sensor_platform)

    def test_temporary_home_input_aliases_are_explicitly_cleaned(self) -> None:
        expected = {"do_input_home_power_raw", "do_home_power", "do_home_import_power", "do_home_export_power"}
        self.assertEqual(expected, set(OBSOLETE_HOME_INPUT_ENTITY_ALIASES))

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
        self.assertNotIn("CONF_GRID_IMPORT_POWER_ENTITY", config_flow)
        self.assertNotIn("CONF_GRID_EXPORT_POWER_ENTITY", config_flow)

    def test_solar_examples_reference_only_registered_entities(self) -> None:
        sensor_source = (ROOT / "custom_components/dummy_os_data/solar_sensor.py").read_text()
        registered_unique_ids = set(re.findall(r'_attr_unique_id = "(do_solar_[^"]+)"', sensor_source))
        registered_unique_ids.update(re.findall(r'object_id = f"(do_solar_[^"]+)', sensor_source))
        for example in (ROOT / "examples").glob("*.yaml"):
            for entity_id in re.findall(r"sensor\.(do_solar_[a-z0-9_]+)", example.read_text()):
                self.assertIn(entity_id, registered_unique_ids, f"{example.name} references unregistered sensor.{entity_id}")
        self.assertIn("do_solar_evaluation_last_completed_quarter", registered_unique_ids)


if __name__ == "__main__":
    unittest.main()
