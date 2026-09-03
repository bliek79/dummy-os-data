# GitHub Release

**Tag:** `0.1.0-alpha.12`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12 - Naming and Registry Migration`

## Dummy OS Forecast 0.1.0-alpha.12

Deze pre-release zet de publieke naam- en entiteitenstructuur van de forecastintegratie recht zonder de bestaande forecastberekeningen of de vaste tijdarchitectuur te veranderen.

### Integratienaam

- De zichtbare Home Assistant-integratienaam wordt **Dummy OS Forecast**.
- Het technische Home Assistant-domain blijft bewust `dummy_os_data` om een onnodige domainmigratie te vermijden.
- Bestaande automatisch aangemaakte config-entrytitel `Dummy OS` of `Dummy OS Data` wordt tijdens setup naar `Dummy OS Forecast` bijgewerkt; een handmatig aangepaste titel wordt niet overschreven.

### Source-laag

De zeven bestaande `do_data_*`-bronsensoren worden gecontroleerd gemigreerd naar één vaste Source-namespace:

- `sensor.do_source_grid_net_power`
- `sensor.do_source_grid_import_power`
- `sensor.do_source_grid_export_power`
- `sensor.do_source_solar_power`
- `sensor.do_source_battery_charge_power`
- `sensor.do_source_battery_discharge_power`
- `sensor.do_source_home_power`

De onderliggende vermogenslogica blijft gelijk. Netvermogen blijft positief voor import en negatief voor export; `unknown` en `unavailable` worden niet als nul geïnterpreteerd.

### Energy Forecast

De veertien bestaande `do_home_*`-forecast-/historie-/evaluatiesensoren worden naar `do_energy_*` gemigreerd:

- `sensor.do_energy_actual_quarter`
- `sensor.do_energy_history_status`
- `sensor.do_energy_history_days`
- `sensor.do_energy_forecast_model`
- `sensor.do_energy_forecast`
- `sensor.do_energy_forecast_timeline`
- `sensor.do_energy_forecast_next_quarter`
- `sensor.do_energy_forecast_coverage`
- `sensor.do_energy_forecast_confidence`
- `sensor.do_energy_forecast_model_health`
- `sensor.do_energy_forecast_accuracy`
- `sensor.do_energy_forecast_mae`
- `sensor.do_energy_forecast_bias`
- `sensor.do_energy_forecast_evaluation_samples`

Ook de profielselect wordt consequent:

- `select.do_energy_profile`

De bestaande opgeslagen Energy/Home-forecastdata blijft dezelfde store gebruiken; dit is een identitymigratie en geen modelreset.

### Degree Days

Degree Days wordt niet langer alleen via losse `hass.states.async_set()`-states gepubliceerd. De laag krijgt tien normale geregistreerde `SensorEntity`-entiteiten onder Dummy OS Forecast:

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

Bekende oude losse Degree Days-runtime-states worden tijdens setup gericht verwijderd voordat de geregistreerde entiteiten worden opgebouwd.

### Ongewijzigd

- Solar blijft `do_solar_*`.
- Weather blijft `do_weather_*`.
- Prices blijft `do_prices_*` en wordt in deze release nog niet naar het entity registry omgebouwd.
- Native architectuur blijft **15 minuten / 72 uur / 288 slots**.
- Solar horizon-snapshots en de vijf horizon-evaluatiesensoren uit alpha.11.11 blijven intact.
- Forecastmodellen, tariefberekeningen en fysieke bronformules worden door deze naam-/registryrelease niet inhoudelijk gewijzigd.
- Er wordt geen EMS- of batterijactie aangestuurd.

### Migratiecontrole na installatie

Na installatie en een volledige Home Assistant-herstart moet expliciet worden gecontroleerd:

1. De integratie wordt zichtbaar als **Dummy OS Forecast** en draait versie `0.1.0-alpha.12`.
2. Er zijn **65 geregistreerde entiteiten**: 64 sensors en 1 select.
3. Prefixverdeling: 7 Source-sensors, 14 Energy-sensors + 1 Energy-select, 19 Solar-sensors, 14 Weather-sensors en 10 Degree Days-sensors.
4. De oude `do_data_*`- en `do_home_*`-registry-entiteiten zijn niet als dubbele of verweesde entiteiten achtergebleven.
5. De oude Degree Days-varianten `do_weighted_degree_days_*` en `do_heat_degree_days_last_day` zijn niet als losse reststates achtergebleven.
6. Entity ID, unique ID en zichtbare naam sluiten per Source-, Energy- en Degree Days-entiteit op de nieuwe vaste naamstructuur aan.
7. `sensor.do_source_home_power` levert dezelfde canonieke vermogensbalans als vóór de migratie en Energy Forecast blijft nieuwe kwartieren verwerken.
8. Solar- en Weather-entiteiten blijven aanwezig met hun bestaande IDs en functionele states.
9. De vijf Solar-horizon-evaluatiesensoren blijven ongewijzigd doorlopen.

Live functionele validatie in Home Assistant blijft vereist voordat de migratie als volledig bevestigd wordt beschouwd.
