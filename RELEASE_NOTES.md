# GitHub Release

**Tag:** `0.1.0-alpha.12.1`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.1 - Degree Days and Display Name Fix`

## Dummy OS Forecast 0.1.0-alpha.12.1

Deze gerichte pre-release herstelt twee live bevestigde migratieproblemen uit alpha.12. Forecastmodellen, bronformules en de vaste tijdarchitectuur worden niet inhoudelijk gewijzigd.

### Degree Days registry-fix

Alpha.12 maakte de nieuwe Degree Days `SensorEntity`-laag inhoudelijk correct aan, maar oude runtime-states konden de gewenste `sensor.do_degree_days_*` entity-ID's nog bezet houden. Home Assistant registreerde de nieuwe entiteiten daardoor onder namen zoals `sensor.dummy_os_forecast_do_degree_days_daily`.

Alpha.12.1:

- verwijdert oude ongeregistreerde Degree Days-runtime-states zowel vóór als na platformsetup;
- migreert de tien geregistreerde Degree Days-unique IDs daarna expliciet naar hun canonieke entity-ID;
- verwijdert de oude gegenereerde entity-state nadat de registry-ID is gemigreerd;
- houdt de opgeslagen Degree Days-historie en berekeningen ongewijzigd.

De vaste Degree Days-set is:

- `sensor.do_degree_days_status`
- `sensor.do_degree_days_history_days`
- `sensor.do_degree_days_temperature_daily`
- `sensor.do_degree_days_daily`
- `sensor.do_degree_days_weighted_daily`
- `sensor.do_degree_days_reference_daily`
- `sensor.do_degree_days_weighted_reference_daily`
- `sensor.do_degree_days_difference`
- `sensor.do_degree_days_weighted_difference`
- `sensor.do_degree_days_last_day`

### Solar en Weather zichtbare namen

De entity-ID's van Solar en Weather waren in alpha.12 correct, maar de entiteitsnaam bevatte nog `Dummy OS` terwijl het apparaat al `Dummy OS Forecast` heet. Daardoor ontstonden friendly names zoals `Dummy OS Forecast Dummy OS Solar ...`.

Alpha.12.1 normaliseert de entiteitsnamen naar:

- `DO Solar ...`
- `DO Weather ...`

Hierdoor voegt Home Assistant de apparaatnaam nog maar één keer toe. Entity-ID's, unique IDs en functionele states van Solar en Weather blijven ongewijzigd.

### Ongewijzigd

- Integratienaam: **Dummy OS Forecast**.
- Technisch domain: `dummy_os_data`.
- Source blijft `do_source_*`.
- Energy blijft `do_energy_*` plus `select.do_energy_profile`.
- Solar blijft `do_solar_*`.
- Weather blijft `do_weather_*`.
- Prices blijft `do_prices_*`.
- Native architectuur blijft **15 minuten / 72 uur / 288 slots**.
- Geen forecastmodel, tariefberekening, PV-formule, Energy Forecast-model of fysieke EMS-sturing is gewijzigd.

### Live controle na installatie

Na installatie en een volledige Home Assistant-herstart:

1. Controleer dat versie `0.1.0-alpha.12.1` draait onder **Dummy OS Forecast**.
2. Controleer dat alle tien Degree Days-entiteiten exact `sensor.do_degree_days_*` gebruiken.
3. Controleer dat geen `sensor.dummy_os_forecast_do_degree_days_*`-varianten meer aanwezig zijn.
4. Controleer dat oude `sensor.do_weighted_degree_days_*`- en `sensor.do_heat_degree_days_last_day`-runtimevarianten niet als migratiedubbelen zijn achtergebleven.
5. Controleer dat Solar en Weather hun bestaande entity-ID's behouden en de zichtbare naam niet langer dubbel `Dummy OS Forecast Dummy OS ...` bevat.
6. Controleer Source en Energy opnieuw kort op hun reeds geslaagde alpha.12-migratie.
7. Controleer dat Energy, Solar en Weather waar van toepassing nog steeds 15 minuten / 72 uur / 288 slots publiceren.

Live Home Assistant-validatie blijft vereist voordat alpha.12.1 als volledig bevestigd wordt beschouwd.
