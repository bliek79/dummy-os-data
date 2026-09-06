# GitHub Release

**Tag:** `0.1.0-alpha.12.15`  
**Release title:** Dummy OS Forecast 0.1.0-alpha.12.15 - Time Windows Canonical Identity Gate

## Dummy OS Forecast 0.1.0-alpha.12.15

Gerichte hotfix voor de Home Assistant entity-ID van Energy Time Windows plus een structurele identity release-gate. Geen forecast- of modelgedrag verandert.

### Fix
- Registreert `do_energy_time_windows` expliciet op canonical `sensor.do_energy_time_windows`.
- Herkent de door alpha.12.14 automatisch aangemaakte `sensor.dummy_os_forecast_do_energy_time_windows` uitsluitend als veilige generated alias.
- Migreert die bestaande registry-entry in-place naar `sensor.do_energy_time_windows`; er wordt geen tweede sensor of `_2`-variant aangemaakt.
- `unique_id`, `suggested_object_id` en friendly name blijven respectievelijk `do_energy_time_windows`, `do_energy_time_windows` en `DO Energy Time Windows`.

### Structurele identity release-gate
- Iedere publieke `do_energy_*`-sensor moet in tests een expliciet registry-pad naar `sensor.<unique_id>` hebben.
- Alleen correcte `_attr_unique_id`/`_attr_suggested_object_id` is niet langer voldoende om de identity-gate te passeren.
- De bekende foutieve alpha.12.14 Time Windows-ID heeft een expliciete veilige migratietest.
- Gebruikershernoemde onbekende entity IDs blijven beschermd en worden niet geforceerd gemigreerd.

### Ongewijzigd
- Observer-only Time Windows-algoritme.
- Peak Learning.
- Forecastwaarden, confidence, recency, fallback en plannerfeed.
- Native architectuur: exact 15 minuten / 72 uur / 288 slots.

### Releasevalidatie
- Python compile.
- Volledige testsuite.
- Manifest JSON-validatie.
- Canonical identity gate voor alle publieke Energy-sensoren.
