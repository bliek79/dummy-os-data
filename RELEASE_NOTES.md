# GitHub Release

**Tag:** `0.1.0-alpha.12.14`  
**Release title:** Dummy OS Forecast 0.1.0-alpha.12.14 - Energy Time Windows Observer

## Dummy OS Forecast 0.1.0-alpha.12.14

Observer-only implementatie van Energy Forecast Stap 7D. Time Windows vertaalt uitsluitend door Peak Learning als `shifting_structural_grill` geclassificeerde events naar een diagnostisch lokaal tijdvenster. Er is geen forecast- of plannerinvloed.

### Nieuw
- Canonieke Home Assistant-entiteit `sensor.do_energy_time_windows`.
- `unique_id`: `do_energy_time_windows`.
- `suggested_object_id`: `do_energy_time_windows`.
- Friendly name: `DO Energy Time Windows`.
- Dagrepresentatieven zodat iedere lokale eventdag maximaal eenmaal meetelt.
- Deterministische p10-start / p90-eind-kalibratie met native 15-minuten-uitlijning.
- Leave-one-day-out stabiliteit vanaf 12 eventdagen.
- Early/late stabiliteitscontrole vanaf 16 eventdagen.
- Statussen `blocked`, `collecting`, `calibrating`, `calibrated_observer_only`, `stable_observer_only` en `unstable_no_window`.
- Strikte null-semantiek en compacte publieke attributen conform schema `7b.1`.

### Identity / compatibiliteit
- Eerste officiële Time Windows-identity; er wordt bewust geen fictieve legacy-migratie toegevoegd.
- Canonieke tuple: `sensor.do_energy_time_windows` / `do_energy_time_windows` / `do_energy_time_windows`.
- Geen alias-sensor, geen `do_home_*`, geen `dummy_os_data_*` identity en geen geaccepteerde `_2`-fallback.

### Bescherming
- Alleen `shifting_structural_grill` is window-eligible.
- 17:00-18:00 blijft protected; er wordt geen `preferred_quarter`, `fixed_peak_quarter` of andere exact-quarter waarheid gepubliceerd.
- `observer_only=true`, `forecast_influence_enabled=false` en `ready_for_forecast_influence=false` blijven altijd actief in Stap 7D.

### Ongewijzigd
- Native architectuur blijft exact 15 minuten / 72 uur / 288 slots.
- Geen wijziging aan Energy Forecast-waarden, confidence, recency, fallback, plannerfeed of uitvoering.
- Normal en Away blijven strikt gescheiden.
- Missing, unavailable en niet-berekende waarden worden nooit stilzwijgend nul.

### Validatie
- Contracttests voor collecting/null, quarter-alignment, stabiele en instabiele vensters, profielscheiding, classification eligibility en deterministic fingerprint.
- Identity- en publieke-attributengrenstest voor `sensor.do_energy_time_windows`.
- Regressietest voor 15 minuten / 72 uur / 288 slots.
- Volledige testsuite, Python compile en manifest JSON-validatie vóór release.
