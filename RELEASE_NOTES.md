# GitHub Release

**Tag:** `0.1.0-alpha.12.10`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.10 - Energy Combined Quality Matrix`

## Dummy OS Forecast 0.1.0-alpha.12.10

Gerichte uitbreiding voor Energy Forecast Stap 5: observer-only gecombineerde kwaliteitsanalyse van het eigen forecastmodel op dagtype en dagdeel.

### Toegevoegd / verbeterd
- Nieuwe canonieke sensor `sensor.do_energy_forecast_quality_by_day_type_and_daypart`.
- Acht vaste segmenten: `weekday_night`, `weekday_morning`, `weekday_afternoon`, `weekday_evening`, `weekend_night`, `weekend_morning`, `weekend_afternoon`, `weekend_evening`.
- Segmentatie gebeurt op lokale kwartierstart en combineert exact de reeds bestaande Stap 3 dagdelen met de Stap 4 weekday/weekend-indeling.
- Per segment: sample count, MAE, bias, evaluation coverage, accuracy en geldige actual-kwartieren.
- Strikte scheiding per actief profiel blijft behouden.
- Elk segment vereist minimaal 32 geldige forward-looking evaluatiepunten voor status `sufficient_basis`; totaalstatus is pas `sufficient_basis` wanneer alle acht segmenten voldoende basis hebben.
- Evaluation coverage gebruikt geldige actual-kwartieren binnen hetzelfde profiel en dezelfde combinatie als noemer.
- Onbekende, ontbrekende of ongeldige waarden worden niet als nul gereconstrueerd.
- Deterministische entity-identiteit en migratie van de bekende automatisch gegenereerde alias-ID zijn opgenomen.

### Ongewijzigd
- Observer-only: forecastwaarden, fallback-hiërarchie, recency weighting en confidence-logica worden niet aangepast.
- Native architectuur blijft 15 minuten / 72 uur / 288 slots.
- De bestaande persistente Energy-evaluatiehistorie blijft leidend; er wordt geen parallelle historie opgebouwd.
- Stap 3 dagdeelkwaliteit en Stap 4 weekday/weekendkwaliteit blijven ongewijzigd functioneren.
- Solar, Weather, Prices, Degree Days en fysieke EMS-sturing zijn functioneel ongewijzigd.

### Live validatie na installatie
1. Controleer dat `sensor.do_energy_forecast_quality_by_day_type_and_daypart` exact onder deze entity-ID verschijnt.
2. Controleer dat profiel, `observer_only: true`, resolutie 15 minuten en minimum 32 samples worden gemeld.
3. Controleer dat exact alle acht combinaties aanwezig zijn.
4. Controleer per segment sample count, MAE, bias, evaluation coverage, accuracy en valid actual quarters.
5. Controleer dat de totaalstatus alleen `sufficient_basis` is wanneer alle acht segmenten minimaal 32 samples hebben.
6. Bevestig dat de bestaande dagdeel-, dagtype- en 288-slot Energy Forecast-sensoren ongewijzigd blijven functioneren.
