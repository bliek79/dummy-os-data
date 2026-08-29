"""Release metadata consistency checks."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
MIGRATION_MODULE_PATH = ROOT / "custom_components/dummy_os_data/entity_migrations.py"
MIGRATION_SPEC = importlib.util.spec_from_file_location("entity_migrations", MIGRATION_MODULE_PATH)
assert MIGRATION_SPEC is not None and MIGRATION_SPEC.loader is not None
MIGRATION_MODULE = importlib.util.module_from_spec(MIGRATION_SPEC)
MIGRATION_SPEC.loader.exec_module(MIGRATION_MODULE)
SOLAR_GENERATED_ENTITY_ID_ALIASES = MIGRATION_MODULE.SOLAR_GENERATED_ENTITY_ID_ALIASES
is_known_generated_entity_id = MIGRATION_MODULE.is_known_generated_entity_id

VERSION = "0.1.0-alpha.11.1"

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
    "do_solar_model": "sensor.dummy_os_solar_forecast_model",
}


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

    def test_all_observed_solar_entity_ids_have_exact_migration_aliases(self) -> None:
        self.assertEqual(EXPECTED_SOLAR_ENTITY_ID_ALIASES, SOLAR_GENERATED_ENTITY_ID_ALIASES)
        self.assertEqual(13, len(SOLAR_GENERATED_ENTITY_ID_ALIASES))

        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
        for unique_id in EXPECTED_SOLAR_ENTITY_ID_ALIASES:
            self.assertIn(
                f'("sensor", "{unique_id}", "sensor.{unique_id}")',
                init_source,
            )

        for unique_id, observed_entity_id in EXPECTED_SOLAR_ENTITY_ID_ALIASES.items():
            self.assertTrue(is_known_generated_entity_id("sensor", unique_id, observed_entity_id))
            self.assertFalse(is_known_generated_entity_id("sensor", unique_id, f"sensor.user_{unique_id}"))


if __name__ == "__main__":
    unittest.main()
