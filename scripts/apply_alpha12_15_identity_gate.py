from pathlib import Path
import json

OLD = "0.1.0-alpha.12.14"
NEW = "0.1.0-alpha.12.15"

# 1. Canonical Time Windows entity-ID registration.
init_path = Path("custom_components/dummy_os_data/__init__.py")
text = init_path.read_text()
peak_line = '    ("sensor", "do_energy_peak_learning", "sensor.do_energy_peak_learning"),\n'
time_line = '    ("sensor", "do_energy_time_windows", "sensor.do_energy_time_windows"),\n'
assert peak_line in text
if time_line not in text:
    text = text.replace(peak_line, peak_line + time_line, 1)
init_path.write_text(text)

# 2. Explicitly recognize the bad alpha.12.14 HA-generated entity ID as safe for in-place migration.
migration_path = Path("custom_components/dummy_os_data/entity_migrations.py")
text = migration_path.read_text()
energy_anchor = '    "do_energy_forecast_quality_by_hour": "sensor.dummy_os_forecast_do_energy_forecast_quality_by_hour",\n'
time_alias = '    "do_energy_time_windows": "sensor.dummy_os_forecast_do_energy_time_windows",\n'
assert energy_anchor in text
if time_alias not in text:
    text = text.replace(energy_anchor, energy_anchor + time_alias, 1)
migration_path.write_text(text)

# 3. Structural identity release gate for all public Energy sensors.
test_path = Path("tests/test_release_consistency.py")
text = test_path.read_text()
old_version = f'VERSION = "{OLD}"'
assert old_version in text
text = text.replace(old_version, f'VERSION = "{NEW}"', 1)
needle = '''        self.assertNotIn('_attr_unique_id = "do_home_', sensor_source)\n        self.assertNotIn('_attr_unique_id = "do_home_profile"', select_source)\n'''
addition = '''        self.assertNotIn('_attr_unique_id = "do_home_', sensor_source)\n        self.assertNotIn('_attr_unique_id = "do_home_profile"', select_source)\n        # Mandatory identity release gate: every public Energy sensor must have\n        # an explicit path to its canonical sensor.<unique_id> registry ID.\n        for unique_id in EXPECTED_ENERGY_IDS:\n            direct = f'(\\"sensor\\", \\"{unique_id}\\", \\"sensor.{unique_id}\\")'\n            migrated = re.compile(\n                rf'\\(\\"sensor\\", \\"[^\\"]+\\", \\"{re.escape(unique_id)}\\", \\"sensor\\.{re.escape(unique_id)}\\"\\)'\n            )\n            self.assertTrue(\n                direct in init_source or migrated.search(init_source),\n                f'Missing canonical entity-ID route for {unique_id}',\n            )\n        self.assertNotIn('sensor.dummy_os_forecast_do_energy_time_windows', init_source)\n'''
assert needle in text
text = text.replace(needle, addition, 1)

marker = '    def test_degree_days_are_registered_sensor_entities(self) -> None:\n'
extra_test = '''    def test_time_windows_bad_alpha1214_id_is_safe_for_in_place_migration(self) -> None:\n        migrations_source = (ROOT / "custom_components/dummy_os_data/entity_migrations.py").read_text()\n        init_source = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()\n        self.assertIn(\n            '\"do_energy_time_windows\": \"sensor.dummy_os_forecast_do_energy_time_windows\"',\n            migrations_source,\n        )\n        self.assertTrue(\n            MIGRATION_MODULE.is_known_generated_entity_id(\n                "sensor",\n                "do_energy_time_windows",\n                "sensor.dummy_os_forecast_do_energy_time_windows",\n            )\n        )\n        self.assertIn(\n            '("sensor", "do_energy_time_windows", "sensor.do_energy_time_windows")',\n            init_source,\n        )\n\n'''
assert marker in text
if 'test_time_windows_bad_alpha1214_id_is_safe_for_in_place_migration' not in text:
    text = text.replace(marker, extra_test + marker, 1)
test_path.write_text(text)

# 4. Version metadata.
const_path = Path("custom_components/dummy_os_data/const.py")
text = const_path.read_text(); assert f'VERSION = "{OLD}"' in text
const_path.write_text(text.replace(f'VERSION = "{OLD}"', f'VERSION = "{NEW}"', 1))

manifest_path = Path("custom_components/dummy_os_data/manifest.json")
data = json.loads(manifest_path.read_text()); assert data["version"] == OLD
data["version"] = NEW
manifest_path.write_text(json.dumps(data, indent=2) + "\n")

Path("RELEASE_NOTES.md").write_text('''# GitHub Release\n\n**Tag:** `0.1.0-alpha.12.15`  \n**Release title:** Dummy OS Forecast 0.1.0-alpha.12.15 - Time Windows Canonical Identity Gate\n\n## Dummy OS Forecast 0.1.0-alpha.12.15\n\nGerichte hotfix voor de Home Assistant entity-ID van Energy Time Windows plus een structurele identity release-gate. Geen forecast- of modelgedrag verandert.\n\n### Fix\n- Registreert `do_energy_time_windows` expliciet op canonical `sensor.do_energy_time_windows`.\n- Herkent de door alpha.12.14 automatisch aangemaakte `sensor.dummy_os_forecast_do_energy_time_windows` uitsluitend als veilige generated alias.\n- Migreert die bestaande registry-entry in-place naar `sensor.do_energy_time_windows`; er wordt geen tweede sensor of `_2`-variant aangemaakt.\n- `unique_id`, `suggested_object_id` en friendly name blijven respectievelijk `do_energy_time_windows`, `do_energy_time_windows` en `DO Energy Time Windows`.\n\n### Structurele identity release-gate\n- Iedere publieke `do_energy_*`-sensor moet in tests een expliciet registry-pad naar `sensor.<unique_id>` hebben.\n- Alleen correcte `_attr_unique_id`/`_attr_suggested_object_id` is niet langer voldoende om de identity-gate te passeren.\n- De bekende foutieve alpha.12.14 Time Windows-ID heeft een expliciete veilige migratietest.\n- Gebruikershernoemde onbekende entity IDs blijven beschermd en worden niet geforceerd gemigreerd.\n\n### Ongewijzigd\n- Observer-only Time Windows-algoritme.\n- Peak Learning.\n- Forecastwaarden, confidence, recency, fallback en plannerfeed.\n- Native architectuur: exact 15 minuten / 72 uur / 288 slots.\n\n### Releasevalidatie\n- Python compile.\n- Volledige testsuite.\n- Manifest JSON-validatie.\n- Canonical identity gate voor alle publieke Energy-sensoren.\n''')
