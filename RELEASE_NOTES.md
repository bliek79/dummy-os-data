# GitHub Release

**Tag:** `0.1.0-alpha.12.9`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.9 - Energy Weekday Weekend Quality Diagnostics`

## Dummy OS Forecast 0.1.0-alpha.12.9

Gerichte uitbreiding voor Energy Forecast Stap 4: observer-only kwaliteitsdiagnostiek voor werkdagen versus weekenden.

### Toegevoegd / verbeterd
- Nieuwe canonieke sensor `sensor.do_energy_forecast_quality_by_day_type`.
- Exacte indeling conform het bestaande forecastmodel: maandag-vrijdag = `weekday`, zaterdag-zondag = `weekend`, bepaald op lokale kwartierstart.
- Per segment worden sample count, MAE, bias, evaluation coverage, accuracy en geldige actual-kwartieren gepubliceerd.
- Diagnostiek blijft strikt gescheiden per actief profiel.
- Beide segmenten vereisen minimaal 32 geldige forward-looking evaluatiepunten voor status `sufficient_basis`.
- Evaluation coverage gebruikt geldige actual-kwartieren binnen hetzelfde profiel en dagtype als noemer.
- Lokale kalendergrenzen en DST-classificatie zijn met regressietests afgedekt.
- Deterministische entity-identiteit en migratie van automatisch gegenereerde alias-ID's zijn opgenomen.

### Ongewijzigd
- Observer-only: forecastwaarden, fallback-hiërarchie en confidence-logica worden niet aangepast.
- Native architectuur blijft 15 minuten / 72 uur / 288 slots.
- De bestaande persistente Energy-evaluatiehistorie blijft leidend; er wordt geen parallelle historie opgebouwd.
- Stap 3 dagdeelkwaliteit blijft ongewijzigd functioneren.
- Solar, Weather, Prices, Degree Days en fysieke EMS-sturing zijn functioneel ongewijzigd.
- Feestdagen worden in deze stap niet als apart dagtype behandeld.

### Live validatie na installatie
1. Controleer dat `sensor.do_energy_forecast_quality_by_day_type` exact onder deze entity-ID verschijnt.
2. Controleer dat de sensor het actieve profiel meldt en de segmenten `weekday` en `weekend` bevat.
3. Controleer per segment sample count, MAE, bias, evaluation coverage, accuracy en valid actual quarters.
4. Controleer dat status pas `sufficient_basis` wordt wanneer beide segmenten minimaal 32 evaluatiepunten bevatten.
5. Bevestig dat `sensor.do_energy_forecast_quality_by_daypart` en de bestaande 288-slot Energy Forecast ongewijzigd blijven functioneren.
