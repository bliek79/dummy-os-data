# GitHub Release

**Tag:** `0.1.0-alpha.12.12`  
**Release title:** Dummy OS Forecast 0.1.0-alpha.12.12 - Energy Peak Learning Observer

## Dummy OS Forecast 0.1.0-alpha.12.12

Observer-only implementatie van Energy Forecast Stap 6D. De nieuwe laag detecteert en classificeert piekgedrag uit de bestaande forward-looking Energy-evaluatiehistorie zonder de forecast zelf te wijzigen.

### Nieuw
- Canonieke Home Assistant-entiteit `sensor.do_energy_peak_learning`.
- `unique_id`: `dummy_os_data_energy_peak_learning`.
- `suggested_object_id`: `do_energy_peak_learning`.
- Kandidaatpiekdetectie op positieve residual `actual_kwh - forecast_kwh`.
- Leave-one-local-day-out kalibratie met minimum 32 geldige kwartieren en 8 verschillende lokale dagen per uur.
- Exact aangrenzende kandidaatkwartieren worden tot een event samengevoegd; gaten worden niet overbrugd en een event mag een uurgrens passeren.
- Observer-only classificaties `incidental`, `structural`, `shifting_structural_grill` en `unresolved`.
- Het venster 17:00-18:00 heeft vaste bescherming `no_exact_quarter_structural`.

### Identity / migratie / cleanup
- Nieuwe entiteit; er bestaat geen oudere canonical identity die gemigreerd moet worden.
- Er is geen gegenereerde alias bedoeld. Na installatie moet de entity registry exact `sensor.do_energy_peak_learning` bevatten; een afwijkende suffix/alias geldt als migratie- of cleanupafwijking.
- Detailattributen `calibration`, `classifications` en `events` zijn uitgesloten van Recorder.

### Ongewijzigd
- Native architectuur blijft exact 15 minuten / 72 uur / 288 slots.
- `forecast.py` en forecastwaarden worden niet gewijzigd.
- Geen planner-, execution-, confidence-, recency-, fallback- of Stap-7 time-windowinvloed.
- Normal en Away blijven strikt gescheiden.
- Missing, unavailable en niet-berekende kalibratiewaarden blijven `null` en worden nooit stilzwijgend `0`.

### Validatie
- Contracttests voor minimum databasis, profielscheiding en null-semantiek.
- Expliciete leave-one-day-out-test.
- Eventtests voor adjacency, geen gap-bridging en uurgrensoverschrijding.
- Beschermingstest voor 17:00-18:00.
- Identity-contracttest voor unique_id/suggested_object_id/registratie.
- Regressietest voor 15 minuten / 72 uur / 288 slots.
- Volledige bestaande testsuite, Python compile en manifest JSON-validatie vóór merge.
- Na installatie live valideren dat `sensor.do_energy_peak_learning` exact onder de canonical entity_id verschijnt en observer-only blijft.
