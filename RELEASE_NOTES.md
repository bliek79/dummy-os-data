# GitHub Release

**Tag:** `0.1.0-alpha.11.0`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.0 - Native Solar Forecast Shadow Foundation`

## Dummy OS Data 0.1.0-alpha.11.0

Eerste native Solar Forecast-providerlaag voor Dummy OS Data. De release bouwt
rechtstreeks voort op alpha.10.3 en voegt een brononafhankelijke 72-uurs
Solar-tijdlijn toe voor Noord, Zuid en totaal. De module is uitsluitend
observation/shadow: package 86 en Solcast blijven actief als referentie.

### Nieuw

- Nieuwe module `solar.py` voor twee onafhankelijke Open-Meteo
  `global_tilted_irradiance`-bronnen.
- Nieuwe pure rekenlaag `solar_model.py` met PV-vermogensberekening,
  kwartierenergie en SMA AC-verdeling.
- Nieuwe `solar_sensor.py` met 13 vaste Solar-entiteiten.
- Native rollende Solar-tijdlijn van 72 uur / 288 kwartierslots.
- Gescheiden voorspelling voor Noord, Zuid en totaal.
- Dagtotalen voor vandaag en morgen per dakvlak en totaal.
- Eerstvolgende kwartierforecast voor toekomstig EMS-gebruik.
- Werkelijk SMA-vermogen voor totaal en een AC-equivalente verdeling over Noord
  en Zuid op basis van de verhouding tussen DC-ingang A en B.
- Solar-bronstatus, freshness, retry/backoff en behoud van de laatst geldige
  tijdlijn bij tijdelijke bronfouten.
- Configureerbare locatie, bronentiteiten, dakcapaciteiten, AC-limieten,
  hellingshoeken, Open-Meteo-azimut en prestatiefactoren.
- Nederlandse en Engelse optievertalingen.
- Acht unit-tests voor de onafhankelijke Solar-rekenlaag en twee
  releaseconsistentietests.

### Gewijzigd

- Integratieversie verhoogd van `0.1.0-alpha.10.3` naar
  `0.1.0-alpha.11.0`.
- `__init__.py` start en stopt nu ook de Solar-coordinator.
- `sensor.py` registreert de nieuwe Solar-entiteiten.
- Solarstraling wordt correct geïnterpreteerd als achterwaarts gemiddelde: de
  Open-Meteo-timestamp wordt 15 minuten teruggeschoven naar het begin van het
  energieslot.
- Open-Meteo-azimut gebruikt expliciet de bronconventie: 0 graden is zuid en
  +/-180 graden is noord.
- README en entiteit-/architectuurdocumentatie zijn uitgebreid met de native
  Solar-laag en het migratiepad.

### Ongewijzigd

- Home Forecast, historie, profielen en evaluatie blijven ongewijzigd.
- Weather 72h / 288-slot timeline en Open-Meteo-weatherrefresh blijven
  ongewijzigd.
- Prices alpha.10.3, PT15M-windowdiagnostiek, tarieven en gaslogica blijven
  ongewijzigd.
- Package `86_solcast_evaluation` blijft actief.
- Solcast blijft beschikbaar als onafhankelijke benchmark.
- Package 07 blijft de referentie voor zonneboiler- en warmteberekeningen.
- De zonneboiler gebruikt nog niet automatisch de nieuwe Solar Forecast.
- Geen forecastkalibratie, dagelijkse MAE/bias of automatische bronselectie in
  deze eerste Solar-release.
- Geen fysieke EMS-sturing of planner-invloed.

### Validatie

- Na update en Home Assistant-herstart moet `sensor.do_solar_status` bestaan en
  bij geldige brondata `ok` tonen.
- `sensor.do_solar_forecast_timeline` moet state `288` tonen.
- Het attribuut `points` moet exact 288 punten bevatten in het beschreven
  negenveldenformaat.
- `forecast_start` moet het eerstvolgende volledige lokale kwartier zijn.
- Noord gebruikt standaard Open-Meteo-azimut `180`; Zuid gebruikt standaard
  `0`; beide gebruiken tilt `37`.
- Standaard DC-capaciteit is 2,96 kWp Noord en 1,48 kWp Zuid.
- Standaard AC-limiet is 2,45 kW Noord en 1,23 kW Zuid.
- `sensor.do_solar_actual_power_total` moet de SMA-totaalsensor volgen.
- Noord plus Zuid AC-equivalent moet, binnen afronding, gelijk zijn aan het SMA
  totaal wanneer A+B groter is dan nul.
- `sensor.do_solar_forecast_tomorrow_total` moet gelijk zijn aan Noord plus Zuid
  binnen 0,001 kWh afronding.
- Het grote `points`-attribuut van de Solar-tijdlijn moet Recorder-excluded zijn.
- Package 86 en de bestaande Solcast-entiteiten moeten ongewijzigd blijven
  functioneren.
- Home, Weather, Prices, Degree Days en gas moeten zonder regressie blijven
  werken.
- Er mogen geen nieuwe `dummy_os_data` setup- of runtimefouten ontstaan.

### Installatiepakket

- Bestand: `Dummy_OS_Data_0.1.0-alpha.11.0_HA_install.zip`
- SHA-256: `1b9326e2627d3265915bf637a32fdd4dc74daf403c02f4ff1ffd1555f5846549`
- De ZIP bevat `custom_components/dummy_os_data` en kan over de bestaande
  custom integration worden uitgepakt.
