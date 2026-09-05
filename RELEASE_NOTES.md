# GitHub Release

**Tag:** `0.1.0-alpha.12.8`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.8 - Energy Daypart Quality Diagnostics`

## Dummy OS Forecast 0.1.0-alpha.12.8

Gerichte uitbreiding voor Energy Forecast Stap 3: observer-only kwaliteitsdiagnostiek per vast lokaal dagdeel.

### Toegevoegd / verbeterd
- Nieuwe canonieke sensor `sensor.do_energy_forecast_quality_by_daypart`.
- Vaste lokale dagdelen: nacht 00:00-06:00, ochtend 06:00-12:00, middag 12:00-18:00 en avond 18:00-24:00.
- Per dagdeel worden sample count, MAE, bias, evaluation coverage, accuracy en het aantal geldige actual-kwartieren berekend.
- Diagnostiek blijft strikt gescheiden per actief profiel.
- Status blijft `collecting` totdat ieder dagdeel minimaal 32 geldige evaluatiepunten heeft; daarna wordt de basis als voldoende beschouwd.
- Evaluation coverage gebruikt geldige actual-kwartieren binnen hetzelfde profiel en dagdeel als noemer.
- Lokale tijd- en DST-grenzen zijn expliciet afgedekt met regressietests.
- Deterministische entity-identiteit en veilige migratie van automatisch gegenereerde aliases zijn opgenomen.

### Ongewijzigd
- Deze release is observer-only: forecastwaarden, fallback-hiërarchie en confidence-logica worden niet aangepast.
- Native architectuur blijft 15 minuten / 72 uur / 288 slots.
- Bestaande Energy-historie en evaluatiestore blijven leidend; er wordt geen parallelle historie opgebouwd.
- Solar, Weather, Prices, Degree Days en fysieke EMS-sturing zijn functioneel ongewijzigd.

### Live validatie na installatie
1. Controleer dat `sensor.do_energy_forecast_quality_by_daypart` exact onder deze entity-ID verschijnt.
2. Controleer dat de sensor het actieve profiel meldt en vier dagdelen bevat.
3. Controleer per dagdeel sample count, MAE, bias, evaluation coverage, accuracy en valid actual quarters.
4. Controleer dat de status bij onvoldoende basis `collecting` blijft en pas na minimaal 32 evaluatiepunten per dagdeel naar voldoende basis kan gaan.
5. Bevestig dat de bestaande Energy forecast, confidence, fallback, timeline en 288-slot horizon ongewijzigd blijven functioneren.
