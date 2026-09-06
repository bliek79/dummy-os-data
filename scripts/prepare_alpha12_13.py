from pathlib import Path
import json

VERSION_OLD = "0.1.0-alpha.12.12"
VERSION_NEW = "0.1.0-alpha.12.13"

sensor = Path("custom_components/dummy_os_data/sensor.py")
text = sensor.read_text()
text = text.replace(
    '_attr_unique_id = "dummy_os_data_energy_peak_learning"',
    '_attr_unique_id = "do_energy_peak_learning"',
)
assert '_attr_unique_id = "do_energy_peak_learning"' in text
assert '_attr_suggested_object_id = "do_energy_peak_learning"' in text
assert '_attr_name = "DO Energy Peak Learning"' in text
sensor.write_text(text)

init = Path("custom_components/dummy_os_data/__init__.py")
text = init.read_text()
migration = '    ("sensor", "dummy_os_data_energy_peak_learning", "do_energy_peak_learning", "sensor.do_energy_peak_learning"),\n'
anchor = '    ("sensor", "do_home_forecast_evaluation_samples", "do_energy_forecast_evaluation_samples", "sensor.do_energy_forecast_evaluation_samples"),\n'
if migration not in text:
    assert anchor in text
    text = text.replace(anchor, anchor + migration)
entity_migration = '    ("sensor", "do_energy_peak_learning", "sensor.do_energy_peak_learning"),\n'
entity_anchor = '    ("sensor", "do_energy_forecast_quality_by_hour", "sensor.do_energy_forecast_quality_by_hour"),\n'
if entity_migration not in text:
    assert entity_anchor in text
    text = text.replace(entity_anchor, entity_anchor + entity_migration)
init.write_text(text)

peak_test = Path("tests/test_peak_learning.py")
text = peak_test.read_text().replace(
    'assert \'_attr_unique_id = "dummy_os_data_energy_peak_learning"\' in text',
    'assert \'_attr_unique_id = "do_energy_peak_learning"\' in text',
)
peak_test.write_text(text)

release_test = Path("tests/test_release_consistency.py")
text = release_test.read_text()
text = text.replace(f'VERSION = "{VERSION_OLD}"', f'VERSION = "{VERSION_NEW}"')
text = text.replace('    "dummy_os_data_energy_peak_learning",', '    "do_energy_peak_learning",')
old_pair_anchor = '            "do_home_forecast_evaluation_samples": "do_energy_forecast_evaluation_samples",\n'
new_pair = '            "dummy_os_data_energy_peak_learning": "do_energy_peak_learning",\n'
if new_pair not in text:
    assert old_pair_anchor in text
    text = text.replace(old_pair_anchor, old_pair_anchor + new_pair)
release_test.write_text(text)

const = Path("custom_components/dummy_os_data/const.py")
const.write_text(const.read_text().replace(f'VERSION = "{VERSION_OLD}"', f'VERSION = "{VERSION_NEW}"'))

manifest = Path("custom_components/dummy_os_data/manifest.json")
data = json.loads(manifest.read_text())
assert data["version"] == VERSION_OLD
data["version"] = VERSION_NEW
manifest.write_text(json.dumps(data, indent=2) + "\n")

Path("RELEASE_NOTES.md").write_text("""# GitHub Release

**Tag:** `0.1.0-alpha.12.13`  
**Release title:** Dummy OS Forecast 0.1.0-alpha.12.13 - Peak Learning Identity Fix

## Dummy OS Forecast 0.1.0-alpha.12.13

Gerichte identity-correctie op de in alpha.12.12 geïntroduceerde observer-only Energy Peak Learning-sensor. Er is geen wijziging aan forecast-, kalibratie-, classificatie- of plannerlogica.

### Correctie
- Canonieke Home Assistant-entiteit blijft `sensor.do_energy_peak_learning`.
- `unique_id` is gecorrigeerd van `dummy_os_data_energy_peak_learning` naar `do_energy_peak_learning` zodat Peak Learning exact dezelfde Energy-namespace volgt als alle overige Energy-sensoren.
- `suggested_object_id` blijft `do_energy_peak_learning`.
- Friendly name blijft `DO Energy Peak Learning`, conform de bestaande `DO Energy ...`-naamgeving.

### Migratie / cleanup
- Een bestaande alpha.12.12 registry-entry met unique-id `dummy_os_data_energy_peak_learning` wordt in-place gemigreerd naar `do_energy_peak_learning` en naar exact `sensor.do_energy_peak_learning`.
- Daardoor hoort geen `_2`-entiteit en geen dubbele Peak Learning-entiteit te ontstaan.
- De canonical entity-id wordt ook opgenomen in de stabiele entity-id migratielijst.

### Ongewijzigd
- Native architectuur blijft exact 15 minuten / 72 uur / 288 slots.
- Peak Learning blijft strikt observer-only.
- `forecast_influence_enabled=false` en `ready_for_model_influence=false` blijven ongewijzigd.
- Geen wijziging aan thresholds, event-samenvoeging, classificatie, protected window 17:00-18:00, confidence, recency, fallback of plannerfeed.

### Validatie
- Identity-contracttest controleert nu `do_energy_peak_learning` als unique-id.
- Release-consistencytest controleert Peak Learning binnen de uniforme `do_energy_*` Energy-namespace.
- Migratiecontracttest controleert de overgang van de foutieve alpha.12.12 unique-id naar de canonical identity.
- Volledige testsuite, Python compile en manifest JSON-validatie worden vóór publicatie uitgevoerd.
""")
