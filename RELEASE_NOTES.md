# GitHub Release

**Tag:** `0.1.0-alpha.11.2`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.2 - Solar Next-Quarter Rollover Hotfix`

## Dummy OS Data 0.1.0-alpha.11.2

Gerichte hotfix voor `sensor.do_solar_forecast_next_quarter`. De Solar-tijdlijn
werd ieder uur correct vernieuwd, maar de sensor bleef tussen twee bronupdates
altijd het eerste tijdlijnpunt tonen. Daardoor kon het gepubliceerde kwartier al
voorbij zijn.

### Opgelost

- De next-quarter-sensor leest niet langer onvoorwaardelijk `points[0]`.
- De sensor selecteert bij iedere uitlezing het eerste tijdlijnpunt dat strikt
  na de actuele kwartiergrens begint.
- Om `:00`, `:15`, `:30` en `:45` publiceert de Solar-coordinator de afgeleide
  sensorstaten opnieuw.
- Het doorschuiven gebruikt de al aanwezige 72-uurs tijdlijn en veroorzaakt geen
  extra Open-Meteo-verzoek.
- De attributen vermelden voortaan `selection: first_future_slot` en de lokale
  kwartierverversing.

### Preventie

- Nieuwe pure tijdhelpers scheiden een strikt toekomstig kwartier van de reeds
  bestaande bronnormalisatie voor complete kwartieren.
- Unit tests bewaken dat 05:36 UTC naar 05:45 UTC wijst, dat een exacte
  kwartiergrens naar het volgende toekomstige kwartier doorschuift en dat een
  uitgeputte tijdlijn veilig `None` oplevert.
- Een releaseconsistentietest bewaakt dat de sensor de dynamische selectie
  gebruikt en niet opnieuw rechtstreeks naar `points[0]` terugvalt.

### Ongewijzigd

- Alle 13 vaste `sensor.do_solar_*`-entity-ID's en hun `unique_id` blijven
  ongewijzigd.
- De alpha.11.1 entity-ID-migratie blijft ongewijzigd actief.
- Open-Meteo blijft ieder uur om `:00:20` verversen met dezelfde retry/backoff.
- 72-uurs horizon, 15-minutenresolutie, 288 punten en dakconfiguraties blijven
  ongewijzigd.
- Solar blijft `observation_shadow`; er is geen planner-invloed of fysieke
  EMS-sturing toegevoegd.
- Home Forecast, Weather, Prices, Degree Days, gas en package
  `86_solcast_evaluation` blijven ongewijzigd.

### Validatie

- Installeer alpha.11.2 en herstart Home Assistant volledig.
- Controleer dat Dummy OS Data versie `0.1.0-alpha.11.2` toont.
- Controleer op een willekeurig moment tussen twee kwartiergrenzen dat attribuut
  `start` van `sensor.do_solar_forecast_next_quarter` naar de eerstvolgende
  kwartiergrens wijst.
- Controleer na de volgende kwartiergrens dat `start` automatisch nog eens
  vijftien minuten doorschuift, zonder een herstart of handmatige bronrefresh.
- Controleer dat `selection` gelijk is aan `first_future_slot`.
- Controleer dat `sensor.do_solar_forecast_timeline` state `288` blijft tonen.
- Controleer dat Noord plus Zuid van het gekozen kwartier gelijk is aan de
  totaalstaat van de next-quarter-sensor.
- Controleer dat `last_attempt` van `sensor.do_solar_status` niet ieder kwartier
  verandert; Open-Meteo moet alleen op het bestaande uurschema worden bevraagd.
- Geen nieuwe `dummy_os_data` setup-, registry- of runtimefouten mogen in de
  Home Assistant-logboeken verschijnen.

### Installatiepakket

- Bestand: `Dummy_OS_Data_0.1.0-alpha.11.2_HA_install.zip`
- SHA-256: `7a3aa121c5cf7b58fea6a0205c9f75eb09112998e13a1411d359d47f83962a3e`
- De ZIP bevat `custom_components/dummy_os_data` en kan over de bestaande
  custom integration worden uitgepakt.
