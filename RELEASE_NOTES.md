# GitHub Release

**Tag:** `0.1.0-alpha.12.6`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.6 - Energy Forward Evaluation Foundation`

## Dummy OS Forecast 0.1.0-alpha.12.6

Gerichte uitbreiding voor Energy Forecast Stap 1: betrouwbare forward-looking evaluatie en duurzame evaluatiecontext.

### Toegevoegd / verbeterd
- Energy-evaluatierecords bewaren nu `forecast_captured_at` zodat aantoonbaar blijft wanneer de gebruikte voorspelling is vastgelegd.
- Energy-evaluatierecords bewaren nu `actual_coverage`, `sample_count`, `source`, `confidence`, `model` en `model_version` als duurzame context.
- Forecastsnapshots die pas na de start van het te beoordelen kwartier zijn vastgelegd, worden geweigerd als geldig evaluatiepunt.
- Scheduler-latency op de kwartiergrens wordt genormaliseerd naar de exacte 15-minuten boundary voordat actual-integratie, kwartierfinalisatie en forecastcapture plaatsvinden.
- Nieuwe regressietests bewaken de forward-looking recordvelden, late-snapshotblokkade en boundary-normalisatie.

### Ongewijzigd
- Native architectuur blijft 15 minuten / 72 uur / 288 slots.
- Canonieke Energy-entity-ID's blijven ongewijzigd; deze release voegt geen nieuwe Home Assistant-entiteiten toe.
- Bestaande historische evaluatierecords blijven bruikbaar voor de huidige accuracy/MAE/bias-berekening.
- Solar, Weather, Prices, Degree Days en fysieke EMS-sturing zijn functioneel ongewijzigd.

### Live validatie na installatie
1. Controleer dat de bestaande `sensor.do_energy_*` entiteiten normaal blijven publiceren en de timeline 288 punten houdt.
2. Laat minimaal één volledig kwartier na installatie verlopen.
3. Controleer dat accuracy/MAE/bias en evaluation samples blijven oplopen zonder reset van de bestaande historie.
4. Controleer in de persistente Energy-store of een nieuw evaluatierecord `forecast_captured_at`, `actual_coverage` en `sample_count` bevat.
5. Bevestig dat `forecast_captured_at` niet later is dan de `start` van het geëvalueerde kwartier.
