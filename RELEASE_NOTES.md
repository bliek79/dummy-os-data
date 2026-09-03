# GitHub Release

**Tag:** `0.1.0-alpha.12.2`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.2 - Degree Days Alias Migration Fix`

## Dummy OS Forecast 0.1.0-alpha.12.2

Deze gerichte pre-release herstelt de concrete migratiefout die live in alpha.12.1 is bevestigd. De Degree Days-berekeningen, opgeslagen historie, Source-, Energy-, Solar-, Weather- en Prices-logica blijven inhoudelijk ongewijzigd.

### Oorzaak

Alpha.12.1 bevatte al registry-migratiecode voor de tien Degree Days-entiteiten, maar de veiligheidsfunctie `is_known_generated_entity_id()` herkende de door Home Assistant aangemaakte alpha.12 entity-ID's `sensor.dummy_os_forecast_do_degree_days_*` niet als bekende automatisch gegenereerde aliases. Daardoor werd de migratie naar de afgesproken `sensor.do_degree_days_*` IDs overgeslagen.

### Fix

Alpha.12.2:

- legt voor exact de tien Degree Days-unique IDs de bekende alpha.12 alias `sensor.dummy_os_forecast_do_degree_days_*` vast;
- behandelt alleen deze expliciet bekende aliases als veilig migreerbaar;
- laat de bestaande registry-migratie deze entiteiten in-place naar exact `sensor.do_degree_days_*` verplaatsen;
- verwijdert de oude gegenereerde state na een succesvolle registry-ID-migratie;
- laat onbekende of handmatig hernoemde entiteiten ongemoeid.

De vaste Degree Days-set blijft:

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
- Solar blijft `do_solar_*` en behoudt de display-namecorrectie uit alpha.12.1.
- Weather blijft `do_weather_*` en behoudt de display-namecorrectie uit alpha.12.1.
- Prices blijft `do_prices_*`.
- Native architectuur blijft **15 minuten / 72 uur / 288 slots**.
- Geen forecastmodel, bronformule, tariefberekening, PV-formule of fysieke EMS-sturing is gewijzigd.

### Live controle na installatie

Na installatie en een volledige Home Assistant-herstart:

1. Controleer dat versie `0.1.0-alpha.12.2` draait onder **Dummy OS Forecast**.
2. Controleer dat alle tien geregistreerde Degree Days-entiteiten exact `sensor.do_degree_days_*` gebruiken.
3. Controleer dat geen `sensor.dummy_os_forecast_do_degree_days_*` varianten meer aanwezig zijn.
4. Controleer dat oude `sensor.do_weighted_degree_days_*` en `sensor.do_heat_degree_days_last_day` runtime-dubbelen niet actief achterblijven.
5. Controleer dat de Degree Days-waarden en opgeslagen historie behouden zijn.
6. Controleer Source en Energy kort opnieuw op de eerder geslaagde migratie.
7. Controleer Solar en Weather op hun bestaande IDs en correcte zichtbare namen.

Live Home Assistant-validatie blijft vereist voordat alpha.12.2 als volledig bevestigd wordt beschouwd.
