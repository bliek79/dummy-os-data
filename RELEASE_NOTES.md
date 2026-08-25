# GitHub Release

**Tag:** `0.1.0-alpha.2`  
**Release title:** `Dummy OS Data 0.1.0-alpha.2 - Home Forecast Baseline Model`

## Dummy OS Data 0.1.0-alpha.2

Tweede integreerbare alpha van Dummy OS Data. Deze release bouwt voort op de permanente 15-minutenhistorie uit alpha.1 en activeert de eerste transparante 72-uurs Woning Forecast op basis van historische kwartierprofielen.

### Nieuw
- Historische analyse per actief profiel, weekdag en kwartiernummer.
- Native 72-uurs forecast met 288 kwartierslots.
- Nieuwe `sensor.do_home_forecast` met de forecasttotalen en de volledige 15-minutentijdlijn als attribuut.
- Nieuwe `sensor.do_home_forecast_next_quarter` voor de eerstvolgende kwartierprognose.
- Nieuwe `sensor.do_home_forecast_coverage` voor de actuele beschikbaarheid van forecastslots.
- Transparante fallbackvolgorde bij beperkte historie: weekdag+kwartier -> kwartier van de dag -> profielgemiddelde -> unavailable.
- Per forecastslot metadata voor bron, sample count en confidence.
- Compacte profielstatistieken voor `normal` en `away` in de bestaande historiek-/modelstatus.
- DST-veilige opbouw van de rolling forecasttijdlijn in UTC met lokale weekdag/kwartierselectie.

### Gewijzigd
- `sensor.do_home_forecast_model` gaat van `historical_foundation` naar `historical_baseline`.
- Modelversie wordt `0.2` en `forecast_active` wordt `true`.
- Integratieversie wordt `0.1.0-alpha.2`.
- Documentatielink in `manifest.json` verwijst nu naar de definitieve repository `bliek79/dummy-os-data`.

### Ongewijzigd
- De bestaande alpha.1-opslagstructuur en historie blijven behouden.
- Bestaande unique IDs en entity-ID-basis worden niet gewijzigd.
- `normal` en `away` blijven strikt gescheiden.
- Geen Recorder/InfluxDB-backfill in deze alpha.
- Geen weather-, seizoen-, presence- of recent-trendcorrectie in deze alpha.
- Geen forecast accuracy, MAE of bias in deze alpha.
- Geen koppeling met Dummy OS EMS-planner of fysieke sturing.

### Validatie
- Bestaande alpha.1-historie moet na upgrade behouden blijven.
- `sensor.do_home_history_status` moet bij geldige bron `ok` blijven.
- `sensor.do_home_forecast_model` moet `historical_baseline` tonen met modelversie `0.2`.
- `sensor.do_home_forecast` moet een horizon van 72 uur en 288 slots rapporteren.
- `sensor.do_home_forecast_next_quarter` moet bij beschikbare profielhistorie een kWh-waarde tonen.
- Forecastslots moeten alleen data uit het actieve `normal`- of `away`-profiel gebruiken.
- Forecast-/snapshot-entiteiten met kWh gebruiken bewust geen `state_class: measurement`.
- Er mogen geen nieuwe `dummy_os_data`-fouten in de Home Assistant-log ontstaan.
