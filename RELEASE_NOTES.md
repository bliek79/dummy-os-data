# GitHub Release

**Tag:** `0.1.0-alpha.1`  
**Release title:** `Dummy OS Data 0.1.0-alpha.1 - Home Forecast Historical Foundation`

## Dummy OS Data 0.1.0-alpha.1

Eerste integreerbare alpha van Dummy OS Data. Deze release legt uitsluitend de permanente historische kwartierbasis voor de toekomstige Woning Forecast aan; er wordt nog geen forecast of plannersturing geactiveerd.

### Nieuw
- Nieuwe Home Assistant custom integration `dummy_os_data` met Config Flow.
- Configureerbare canonieke woningvermogensbron, standaard `sensor.home_power`.
- Native 15-minuten historische datalaag voor woningverbruik.
- Omrekening van werkelijk vermogen in W/kW naar gerealiseerde energie per afgesloten kwartier in kWh.
- Persistente opslag van kwartierrecords via Home Assistant `.storage`.
- Gescheiden historische profielen `normal` en `away` via `select.do_home_profile`.
- Permanente `do_`-entity-ID/unique-ID basis voor de Home Forecast-module.
- Datakwaliteitscontrole op bronbeschikbaarheid en kwartierdekking.

### Entiteiten
- `sensor.do_home_actual_quarter`
- `sensor.do_home_history_status`
- `sensor.do_home_history_days`
- `sensor.do_home_forecast_model`
- `select.do_home_profile`

### Gewijzigd
- De v2 Woning Forecast wordt vanaf deze release native op 15-minutenbasis opgebouwd.
- Forecast- en evaluatiemodellen bouwen later voort op dezelfde kwartierhistorie zonder de huidige entiteitsidentiteiten te wijzigen.

### Ongewijzigd
- Geen woningverbruiksforecast actief in deze alpha.
- Geen forecast accuracy/MAE/bias-berekening actief in deze alpha.
- Geen koppeling met de Dummy OS EMS-planner.
- Geen fysieke batterij- of andere actuatorsturing.
- Bestaande Home Assistant energiesensoren en packages worden niet gewijzigd.

### Validatie
- Integratie moet via de Home Assistant UI toegevoegd kunnen worden.
- `sensor.home_power` moet als standaard bron geselecteerd kunnen worden.
- Na een volledig geldig kwartier moet `sensor.do_home_actual_quarter` een kWh-waarde tonen.
- `sensor.do_home_history_status` moet na geldige historische opbouw `ok` tonen.
- `select.do_home_profile` moet `normal` en `away` ondersteunen en de keuze persistent bewaren.
- De actual-quarter sensor gebruikt `device_class: energy`, unit `kWh` en bewust geen `state_class`.
- Er mogen geen nieuwe `dummy_os_data`-fouten in de Home Assistant-log ontstaan.
