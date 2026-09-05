# GitHub Release

**Tag:** `0.1.0-alpha.12.11`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.11 - Energy Hourly Quality Diagnostic`

## Dummy OS Forecast 0.1.0-alpha.12.11

Gerichte observer-only uitbreiding om de zwakke middagforecast per afzonderlijk lokaal uur te analyseren.

### Toegevoegd / verbeterd
- Nieuwe canonieke sensor `sensor.do_energy_forecast_quality_by_hour`.
- Exacte `unique_id` en `suggested_object_id`: `do_energy_forecast_quality_by_hour`.
- Zes lokale middaguren van 12:00-13:00 tot en met 17:00-18:00.
- Per uur: sample count, MAE, bias, evaluation coverage, accuracy en geldige actual-kwartieren.
- Indeling op lokale kwartierstart en strikt per actief profiel.
- Minimum 32 geldige forward-looking evaluatiepunten per uur voor `sufficient_basis`; totaalstatus pas voldoende als alle zes uren voldoende basis hebben.
- Onbekende, ontbrekende of ongeldige waarden worden nooit als nul gereconstrueerd.
- Deterministische migratie van de bekende automatisch gegenereerde alias-ID naar de canonieke entity-ID.

### Ongewijzigd
- Observer-only: geen wijziging aan forecastwaarden, modeltraining, fallback, recency weighting, confidence of EMS-sturing.
- Native architectuur blijft 15 minuten / 72 uur / 288 slots.
- Bestaande dagdeel-, dagtype- en gecombineerde kwaliteitsdiagnostiek blijven ongewijzigd.

### Live validatie na installatie
1. Controleer dat `sensor.do_energy_forecast_quality_by_hour` exact verschijnt.
2. Controleer `observer_only: true`, profiel en resolutie 15 minuten.
3. Controleer exact zes middaguren van 12:00 tot 18:00.
4. Vergelijk MAE, bias en accuracy per uur en bepaal het sterkst afwijkende uur.
5. Controleer coverage, sample count en valid actual quarters per uur.
6. Bevestig dat bestaande Energy Forecast-sensoren en 288-slot forecast ongewijzigd blijven functioneren.
