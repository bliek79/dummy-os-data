# GitHub Release

**Tag:** `0.1.0-alpha.4`  
**Release title:** `Dummy OS Data 0.1.0-alpha.4 - Home Forecast Evaluation Foundation`

## Dummy OS Data 0.1.0-alpha.4

Deze release voegt de evaluatiebasis toe aan de bestaande Home Forecast. Vanaf deze versie worden voorspellingen vooraf per kwartier vastgelegd en na afloop automatisch vergeleken met het werkelijk gemeten woningverbruik.

### New
- Persistente forecast-snapshots voor toekomstige 15-minutenkwartieren.
- Automatische forecast-versus-actual evaluatie na ieder geldig afgesloten kwartier.
- Nieuwe `sensor.do_home_forecast_accuracy`.
- Nieuwe `sensor.do_home_forecast_mae`.
- Nieuwe `sensor.do_home_forecast_bias`.
- Nieuwe `sensor.do_home_forecast_evaluation_samples`.
- Accuracy gebruikt een robuuste WAPE-achtige vensterberekening zodat kwartieren met zeer laag werkelijk verbruik geen instabiele procentuele fout veroorzaken.
- Evaluaties blijven strikt per `normal` / `away` profiel gescheiden.
- Evaluatieregels bewaren forecast, actual, signed error, absolute error, bron, confidence en modelversie.

### Changed
- Home Forecast modelmetadata gaat naar modelversie `0.3` met `evaluation_active: true`.
- De bestaande `.storage` payload wordt achterwaarts compatibel uitgebreid met `forecast_snapshots` en `evaluations`; de bestaande historie blijft behouden.
- Op iedere kwartiergrens wordt de forecast voor het kwartier dat op dat moment begint vastgezet voordat werkelijke verbruiksdata van dat kwartier beschikbaar is.
- Bij een herstart midden in een kwartier wordt dat lopende kwartier niet achteraf als eerlijke evaluatie gebruikt; de eerstvolgende volledige kwartierforecast wordt vooraf vastgelegd.
- Nieuwe evaluatie-entiteiten worden eveneens gemigreerd naar de afgesproken korte `do_` entity-ID's wanneer Home Assistant eerst een langere automatisch gegenereerde naam aanmaakt.
- Integratieversie wordt `0.1.0-alpha.4`.

### Unchanged
- Native Home Forecast-resolutie blijft 15 minuten.
- Forecast-horizon blijft 72 uur / 288 slots.
- Forecastmodel blijft `historical_baseline`; de bestaande baselineberekening en fallbackvolgorde blijven inhoudelijk gelijk.
- Bestaande alpha.1-alpha.3 kwartierhistorie blijft behouden.
- `normal` en `away` blijven structureel gescheiden.
- De volledige 288-slot forecast blijft intern en wordt niet opnieuw als oversized Recorder state-attribuut gepubliceerd.
- Geen EMS-uitvoering of fysieke sturing.

### Validation
- Na upgrade moeten 12 entiteiten aanwezig zijn: de bestaande 8 plus Accuracy, MAE, Bias en Evaluation Samples.
- Alle entiteiten moeten de afgesproken korte `do_home_*` / `select.do_home_profile` entity-ID's gebruiken.
- Bestaande historie en actieve profielkeuze moeten behouden blijven.
- `sensor.do_home_forecast_model` moet `historical_baseline` tonen met modelversie `0.3` en `evaluation_active: true`.
- Direct na installatie mogen Accuracy, MAE en Bias `unknown` zijn zolang nog geen volledig vooraf voorspeld kwartier is geëvalueerd.
- Na het eerstvolgende volledig vooraf voorspelde en geldig gemeten kwartier moet `sensor.do_home_forecast_evaluation_samples` minimaal `1` worden en moeten Accuracy, MAE en Bias waarden krijgen.
- Een ongeldig of mixed-profile kwartier mag geen evaluatiesample toevoegen.
- Recorder mag geen oversized-attribute waarschuwing voor `sensor.do_home_forecast` geven.
- Er mogen geen nieuwe `dummy_os_data` setup- of runtimefouten ontstaan.
