# GitHub Release

**Tag:** `0.1.0-alpha.3`  
**Release title:** `Dummy OS Data 0.1.0-alpha.3 - Entity ID and Recorder Hotfix`

## Dummy OS Data 0.1.0-alpha.3

Gerichte hotfix op alpha.2. Deze release corrigeert de automatisch gegenereerde Home Assistant entity-ID's en voorkomt dat de volledige 288-slot forecast als te groot state-attribuut naar Recorder wordt geschreven.

### Fixed
- Bestaande door alpha.1/alpha.2 automatisch gegenereerde entity-ID's worden bij setup gemigreerd naar de afgesproken korte `do_`-namen.
- De migratie behoudt de bestaande unique IDs en daarmee de entity-registry-identiteit.
- Alleen bekende automatisch gegenereerde `dummy_os_data_dummy_os_*` entity-ID's worden aangepast; handmatig door de gebruiker gewijzigde entity-ID's blijven ongemoeid.
- De volledige 288-slot forecasttijdlijn wordt niet langer als attribuut van `sensor.do_home_forecast` gepubliceerd. Hiermee wordt de Home Assistant Recorder-waarschuwing over state-attributen groter dan 16.384 bytes voorkomen.

### Changed
- `sensor.do_home_forecast` blijft een compacte 72-uurs samenvattingssensor met totaalverbruik, forecast-start, 15-minutenresolutie, 288 slots, populated slots, historically supported slots en coverage.
- Het attribuut `timeline_storage: internal_only` maakt expliciet dat de volledige tijdlijn intern beschikbaar blijft en niet via Recorder-state-attributen wordt opgeslagen.
- Integratieversie wordt `0.1.0-alpha.3`.

### Unchanged
- De Home Forecast blijft `historical_baseline`, modelversie `0.2`.
- De native forecastresolutie blijft 15 minuten met 72 uur / 288 slots.
- De alpha.1 opslagstructuur en reeds opgebouwde kwartierhistorie blijven ongewijzigd.
- `normal` en `away` blijven strikt gescheiden.
- Forecastberekening, fallbackvolgorde, confidence en coverage-logica uit alpha.2 blijven functioneel ongewijzigd.
- Geen Recorder/InfluxDB-backfill.
- Geen accuracy/MAE/bias-evaluatie.
- Geen koppeling met Dummy OS EMS-planner of fysieke sturing.

### Validation
- Na upgrade moeten de acht entiteiten beschikbaar zijn als:
  - `sensor.do_home_actual_quarter`
  - `sensor.do_home_history_status`
  - `sensor.do_home_history_days`
  - `sensor.do_home_forecast_model`
  - `sensor.do_home_forecast`
  - `sensor.do_home_forecast_next_quarter`
  - `sensor.do_home_forecast_coverage`
  - `select.do_home_profile`
- Bestaande historie en profielkeuze moeten behouden blijven.
- `sensor.do_home_history_status` moet bij geldige bron `ok` blijven.
- `sensor.do_home_forecast_model` moet `historical_baseline` tonen met modelversie `0.2`.
- `sensor.do_home_forecast` moet 72 uur / 288 slots rapporteren zonder een volledige `forecast`-lijst als state-attribuut.
- De Recorder-log mag geen nieuwe waarschuwing meer bevatten dat de state-attributen van `sensor.do_home_forecast` de limiet van 16.384 bytes overschrijden.
- Er mogen geen nieuwe `dummy_os_data` setup- of runtimefouten ontstaan.
