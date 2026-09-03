# GitHub Release

**Tag:** `0.1.0-alpha.12.3`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.3 - Degree Days Stale State Cleanup`

## Dummy OS Forecast 0.1.0-alpha.12.3

Deze gerichte pre-release ruimt de live bevestigde achtergebleven Degree Days-states op na de geslaagde registry-migratie uit alpha.12.2. De Degree Days-berekeningen, opgeslagen historie en overige forecastlagen blijven inhoudelijk ongewijzigd.

### Live bevestigde situatie na alpha.12.2

Alpha.12.2 heeft de tien geregistreerde Degree Days-entiteiten succesvol naar hun canonieke `sensor.do_degree_days_*` entity-ID's gemigreerd. De volledige attributes en waarden waren daar correct aanwezig.

Daarnaast bleven echter ook tien niet-geregistreerde oude states actief onder `sensor.dummy_os_forecast_do_degree_days_*`. Deze waren inhoudelijk duplicaten van de nieuwe canonieke entiteiten.

### Fix

Alpha.12.3:

- voegt exact de tien bekende `sensor.dummy_os_forecast_do_degree_days_*` states toe aan de bestaande Degree Days stale-state cleanup;
- verwijdert deze states uitsluitend wanneer er geen entity-registry entry voor die entity-ID bestaat;
- behoudt daarmee geregistreerde entiteiten en eventuele handmatig beheerde registry-IDs;
- voert de cleanup zowel vóór als na platformsetup uit, zoals de bestaande veilige migratieroute al deed.

De canonieke Degree Days-set blijft:

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

### Ongewijzigd

- Integratienaam: **Dummy OS Forecast**.
- Technisch domain: `dummy_os_data`.
- Source blijft `do_source_*`.
- Energy blijft `do_energy_*` plus `select.do_energy_profile`.
- Solar blijft `do_solar_*`.
- Weather blijft `do_weather_*`.
- Prices blijft `do_prices_*`.
- Native architectuur blijft **15 minuten / 72 uur / 288 slots**.
- Geen Degree Days-formule, opgeslagen historie, forecastmodel, bronformule, tariefberekening, PV-formule of fysieke EMS-sturing is gewijzigd.

### Live controle na installatie

Na installatie en een volledige Home Assistant-herstart:

1. Controleer dat versie `0.1.0-alpha.12.3` draait onder **Dummy OS Forecast**.
2. Controleer dat exact de tien geregistreerde Degree Days-entiteiten onder `sensor.do_degree_days_*` aanwezig zijn.
3. Controleer dat geen `sensor.dummy_os_forecast_do_degree_days_*` states meer aanwezig zijn.
4. Controleer dat de waarden en attributes van de canonieke Degree Days-entiteiten behouden zijn.
5. Controleer dat Source, Energy, Solar en Weather ongewijzigd functioneren.

Live Home Assistant-validatie blijft vereist voordat alpha.12.3 als volledig bevestigd wordt beschouwd.
