# GitHub Release

**Tag:** `0.1.0-alpha.11.8`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.8 - Canonical Home Forecast Source`

## Dummy OS Data 0.1.0-alpha.11.8

Deze alpha sluit Home Forecast definitief aan op de canonieke Dummy OS Data-woningvermogenssensor `sensor.do_data_home_power`.

### Gewijzigd

- Home Forecast gebruikt voortaan vast `sensor.do_data_home_power` als actual-bron voor kwartierintegratie en nieuwe historie.
- De coordinator gebruikt hiervoor `CANONICAL_HOME_POWER_ENTITY`.
- De oude `home_power_entity`-config blijft uitsluitend bestaan voor compatibiliteit met bestaande config entries en bepaalt de productieketen niet meer.

### Behouden

- Bestaande Home Forecast-historie blijft behouden.
- Bestaande forecast snapshots blijven behouden.
- Bestaande Home Forecast-evaluaties blijven behouden.
- De native forecastarchitectuur blijft 15 minuten / 72 uur / 288 slots.
- Normal/Away-profielen en historical_baseline 0.4 blijven ongewijzigd.

### Ongewijzigd

- De zeven definitieve `sensor.do_data_*`-energiesensoren blijven ongewijzigd.
- Weather, Solar Forecast, Prices en Degree Days worden in deze release niet functioneel gewijzigd.
- Geen EMS-planning, SOC-logica, reservebeleid, safety of fysieke batterijsturing toegevoegd.

### Technische validatie

De bronwijziging uit PR #39 is vóór deze release technisch gevalideerd:

- Python compile geslaagd.
- JSON-validatie geslaagd.
- 25 tests geslaagd.
- Releaseconsistentietest controleert expliciet dat Home Forecast `sensor.do_data_home_power` gebruikt.

### Live validatie in Home Assistant

Na installatie en volledige herstart controleren:

1. Dummy OS Data toont versie `0.1.0-alpha.11.8`.
2. `sensor.do_data_home_power` blijft live correct berekend worden.
3. `sensor.do_home_actual_quarter` blijft elk afgerond kwartier vullen met minimaal 90% dekking wanneer de bron geldig is.
4. Nieuwe Home Forecast-kwartierobservaties worden opgebouwd uit `sensor.do_data_home_power` en niet meer uit `sensor.home_power`.
5. Bestaande historie, snapshots en evaluaties blijven aanwezig.
6. Home Forecast 72h / 288 slots, next quarter, accuracy, MAE, bias en model health blijven functioneren.

De bronwissel wordt pas als volledig Gereed gemarkeerd nadat deze live Home Assistant-validatie is uitgevoerd.
