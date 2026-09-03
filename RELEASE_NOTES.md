# GitHub Release

**Tag:** `0.1.0-alpha.11.11`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.11 - Solar Horizon Export Sensors`

## Dummy OS Data 0.1.0-alpha.11.11

Deze alpha maakt de in alpha.11.10 opgebouwde Solar-horizon-evaluaties direct en betrouwbaar beschikbaar aan Home Assistant-consumenten zoals de Google Sheets-validatieautomation.

### Nieuw

- Vijf afzonderlijke Solar horizon-evaluatiesensoren:
  - `sensor.do_solar_evaluation_horizon_1h`
  - `sensor.do_solar_evaluation_horizon_6h`
  - `sensor.do_solar_evaluation_horizon_24h`
  - `sensor.do_solar_evaluation_horizon_48h`
  - `sensor.do_solar_evaluation_horizon_72h`
- Iedere sensor publiceert het laatst voltooide evaluatierecord voor zijn vaste horizon.
- De sensorstate gebruikt het unieke `snapshot_id`, zodat een nieuwe afgeronde evaluatie als echte state-change kan dienen voor Home Assistant-automations.
- De volledige bestaande horizon-evaluatie wordt als vlakke attributes beschikbaar gemaakt, waaronder `slot_start`, `slot_end`, `horizon_hours`, `forecast_captured_at`, provider/model, forecast/actual/error/absolute error/bias/accuracy/valid/coverage voor noord, zuid en totaal.

### Gewijzigd

- `solar_sensor.py` leest de reeds bestaande `last_horizon_evaluations` uit de Solar coordinator en exposeert die als vijf zelfstandige shadow-sensoren.
- Er is geen tweede berekenpad toegevoegd; de sensoren gebruiken exact de horizon-evaluaties die alpha.11.10 al persistent opbouwt.

### Ongewijzigd

- Native architectuur blijft **15 minuten / 72 uur / 288 slots**.
- De bestaande `sensor.do_solar_evaluation_last_completed_quarter` en de directe kwartierevaluatie blijven intact.
- De horizon-snapshot- en evaluatielogica uit alpha.11.10 blijft ongewijzigd.
- Solar forecastmodel `open_meteo_gti_physical_v0.1` blijft ongewijzigd.
- Home Forecast, Weather, Prices, Degree Days en de canonieke Data Power-inputlaag worden niet inhoudelijk gewijzigd.
- `unknown` en `unavailable` worden niet stilzwijgend als nul verwerkt.
- De horizonlaag blijft observation/shadow en stuurt geen EMS- of batterijactie aan.

### Validatie

Na installatie en volledige Home Assistant-herstart:

1. Controleer dat Dummy OS Data versie `0.1.0-alpha.11.11` draait.
2. Controleer dat de vijf nieuwe horizon-sensoren aanwezig zijn.
3. Controleer dat een sensor vóór zijn eerste voltooide evaluatie `waiting_for_first_completed_horizon` als statusattribute toont.
4. Controleer na minimaal 1 uur dat `sensor.do_solar_evaluation_horizon_1h` een `snapshot_id` als state krijgt en een volledig evaluatierecord in de attributes heeft.
5. Controleer na minimaal 6 uur hetzelfde voor de 6h-sensor; 24h/48h/72h volgen zodra voldoende tijd is verstreken.
6. Controleer dat de bestaande `sensor.do_solar_evaluation_last_completed_quarter` normaal blijft doorlopen.
7. Richt daarna de aparte Google Sheets-tab `Solar Forecast Horizons` en exportautomation in en beoordeel de horizonresultaten read-only.

Live functionele validatie in Home Assistant blijft vereist voordat deze uitbreiding als volledig bevestigd wordt beschouwd.
