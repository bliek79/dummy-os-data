# GitHub Release

**Tag:** `0.1.0-alpha.11.1`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.1 - Solar Entity ID Migration Hotfix`

## Dummy OS Data 0.1.0-alpha.11.1

Hotfix voor de Solar-entiteitsregistratie uit alpha.11.0. De native Solar-laag
werkte inhoudelijk, maar Home Assistant registreerde de 13 nieuwe entiteiten
onder `sensor.dummy_os_solar_*` terwijl het vaste contract
`sensor.do_solar_*` voorschrijft.

### Opgelost

- De migratie gebruikt nu alle 13 werkelijk op alpha.11.0 waargenomen
  Home Assistant-entity-ID's als expliciete bronmapping.
- `sensor.dummy_os_solar_source_status` migreert naar
  `sensor.do_solar_status`.
- De forecast-, actual-power- en modelentiteiten migreren naar hun vaste
  `sensor.do_solar_*`-ID.
- De migratie blijft gekoppeld aan de bestaande `unique_id`; historie en
  entity-registry-instellingen blijven daardoor behouden.
- Er worden geen entiteiten verwijderd en er worden geen nieuwe functionele
  Solar-entiteiten toegevoegd.

### Preventie

- Nieuwe pure module `entity_migrations.py` bevat de 13 expliciete,
  waargenomen bron-ID's.
- Een releaseconsistentietest controleert dat alle 13 Solar-entiteiten zowel
  in de vaste entiteitenlijst als in de expliciete migratiemapping voorkomen.
- Een gegokt prefixpatroon wordt niet meer gebruikt voor deze Solar-migratie.
- De formele release-aanleveringsstandaard v1.1 vereist voortaan een echte
  Home Assistant-registratiecontrole bij nieuwe of gewijzigde entiteiten.

### Ongewijzigd

- Solar Forecast-provider, rekenmodel, 72-uurs tijdlijn en forecastwaarden uit
  alpha.11.0 blijven ongewijzigd.
- Open-Meteo-broninstellingen, dakconfiguraties en SMA-bronentiteiten blijven
  ongewijzigd.
- Package `86_solcast_evaluation` en Solcast blijven actief als benchmark.
- Home Forecast, Weather, Prices, Degree Days en gas blijven ongewijzigd.
- Geen forecastkalibratie, planner-invloed of fysieke EMS-sturing.

### Validatie

- Installeer alpha.11.1 over alpha.11.0 en herstart Home Assistant volledig.
- Geen van de 13 `sensor.dummy_os_solar_*`-entiteiten mag daarna nog als actieve
  Dummy OS Data-entiteit bestaan.
- De 13 vaste `sensor.do_solar_*`-entiteiten moeten bestaan zonder duplicaten.
- `sensor.do_solar_status` moet bij geldige brondata `ok` tonen.
- `sensor.do_solar_forecast_timeline` moet state `288` tonen.
- `sensor.do_solar_forecast_tomorrow_total` moet binnen 0,001 kWh gelijk zijn
  aan Noord plus Zuid.
- Controleer na een tweede volledige Home Assistant-herstart dat dezelfde
  entity-ID's behouden blijven.
- Controleer dat bestaande historie en instellingen aan de gemigreerde
  entiteiten gekoppeld zijn gebleven.
- Er mogen geen nieuwe `dummy_os_data` setup-, registry- of runtimefouten in de
  logboeken staan.

### Installatiepakket

- Bestand: `Dummy_OS_Data_0.1.0-alpha.11.1_HA_install.zip`
- SHA-256: `3b802983fcec532074922d676def3f6b001c65bca0dc4ea390adbca16fdd7c1c`
- De ZIP bevat `custom_components/dummy_os_data` en kan over de bestaande
  custom integration worden uitgepakt.
