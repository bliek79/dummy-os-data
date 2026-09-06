from pathlib import Path
import json

OLD = "0.1.0-alpha.12.15"
NEW = "0.1.0-alpha.12.16"

sensor = Path("custom_components/dummy_os_data/sensor.py")
text = sensor.read_text()

def add_explicit_name(class_name: str, expected_name: str) -> str:
    global text
    marker = f'class {class_name}(DummyOSBaseSensor):'
    start = text.index(marker)
    next_class = text.find('\n\nclass ', start + len(marker))
    end = len(text) if next_class == -1 else next_class
    block = text[start:end]
    assert f'_attr_name = "{expected_name}"' in block
    prop = f'''\n    @property\n    def name(self) -> str:\n        \"\"\"Return the canonical runtime name used for friendly_name.\"\"\"\n        return \"{expected_name}\"\n'''
    if 'def name(self)' not in block:
        insert_at = text.index('\n\n    def _result', start, end)
        text = text[:insert_at] + prop + text[insert_at:]
    return text

add_explicit_name("DummyOSEnergyTimeWindowsSensor", "DO Energy Time Windows")
add_explicit_name("DummyOSEnergyPeakLearningSensor", "DO Energy Peak Learning")
sensor.write_text(text)

# Version metadata
const = Path("custom_components/dummy_os_data/const.py")
text = const.read_text(); assert f'VERSION = "{OLD}"' in text
const.write_text(text.replace(f'VERSION = "{OLD}"', f'VERSION = "{NEW}"', 1))
manifest = Path("custom_components/dummy_os_data/manifest.json")
data = json.loads(manifest.read_text()); assert data["version"] == OLD
data["version"] = NEW
manifest.write_text(json.dumps(data, indent=2) + "\n")

# Strengthen identity release gate with runtime-name checks.
test = Path("tests/test_release_consistency.py")
text = test.read_text(); assert f'VERSION = "{OLD}"' in text
text = text.replace(f'VERSION = "{OLD}"', f'VERSION = "{NEW}"', 1)
marker = '    def test_degree_days_are_registered_sensor_entities(self) -> None:\n'
extra = '''    def test_observer_runtime_names_are_explicit_and_canonical(self) -> None:\n        sensor_source = (ROOT / "custom_components/dummy_os_data/sensor.py").read_text()\n        for class_name, expected_name in (\n            ("DummyOSEnergyPeakLearningSensor", "DO Energy Peak Learning"),\n            ("DummyOSEnergyTimeWindowsSensor", "DO Energy Time Windows"),\n        ):\n            start = sensor_source.index(f"class {class_name}(DummyOSBaseSensor):")\n            next_class = sensor_source.find("\\n\\nclass ", start + 1)\n            block = sensor_source[start:] if next_class == -1 else sensor_source[start:next_class]\n            self.assertIn(f'_attr_name = "{expected_name}"', block)\n            self.assertIn('def name(self) -> str:', block)\n            self.assertIn(f'return "{expected_name}"', block)\n            self.assertNotIn('return "Dummy"', block)\n\n'''
if 'test_observer_runtime_names_are_explicit_and_canonical' not in text:
    assert marker in text
    text = text.replace(marker, extra + marker, 1)
test.write_text(text)

Path("RELEASE_NOTES.md").write_text('''# GitHub Release\n\n**Tag:** `0.1.0-alpha.12.16`  \n**Release title:** Dummy OS Forecast 0.1.0-alpha.12.16 - Observer Runtime Name Fix\n\n## Dummy OS Forecast 0.1.0-alpha.12.16\n\nGerichte naamfix op basis van live Home Assistant-validatie. De canonical entity-ID-fix uit alpha.12.15 blijft ongewijzigd.\n\n### Fix\n- `sensor.do_energy_time_windows` publiceert runtime/friendly name expliciet als `DO Energy Time Windows`.\n- `sensor.do_energy_peak_learning` publiceert runtime/friendly name expliciet als `DO Energy Peak Learning`.\n- De zichtbare naam, `unique_id`, `suggested_object_id` en canonical entity-ID blijven ongewijzigd.\n\n### Structurele identity-gate\n- Runtime `name`/`friendly_name` is voortaan onderdeel van dezelfde release-gate als entity_id, unique_id, suggested_object_id en registry-migratie.\n- De observer-sensoren mogen niet meer terugvallen op `Dummy` of een integratie/device-prefix.\n- Geen `_2`-varianten of alias-sensoren.\n\n### Ongewijzigd\n- Time Windows observer-algoritme.\n- Peak Learning observer-algoritme.\n- Forecastwaarden, confidence, recency, fallback en plannerfeed.\n- Native architectuur: exact 15 minuten / 72 uur / 288 slots.\n''')
