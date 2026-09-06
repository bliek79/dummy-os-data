# GitHub Release

**Tag:** `0.1.0-alpha.12.16`  
**Release title:** Dummy OS Forecast 0.1.0-alpha.12.16 - Observer Runtime Name Fix

## Dummy OS Forecast 0.1.0-alpha.12.16

Gerichte naamfix op basis van live Home Assistant-validatie. De canonical entity-ID-fix uit alpha.12.15 blijft ongewijzigd.

### Fix
- `sensor.do_energy_time_windows` publiceert runtime/friendly name expliciet als `DO Energy Time Windows`.
- `sensor.do_energy_peak_learning` publiceert runtime/friendly name expliciet als `DO Energy Peak Learning`.
- De zichtbare naam, `unique_id`, `suggested_object_id` en canonical entity-ID blijven ongewijzigd.

### Structurele identity-gate
- Runtime `name`/`friendly_name` is voortaan onderdeel van dezelfde release-gate als entity_id, unique_id, suggested_object_id en registry-migratie.
- De observer-sensoren mogen niet meer terugvallen op `Dummy` of een integratie/device-prefix.
- Geen `_2`-varianten of alias-sensoren.

### Ongewijzigd
- Time Windows observer-algoritme.
- Peak Learning observer-algoritme.
- Forecastwaarden, confidence, recency, fallback en plannerfeed.
- Native architectuur: exact 15 minuten / 72 uur / 288 slots.
