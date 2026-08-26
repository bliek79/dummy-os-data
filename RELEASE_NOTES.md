# GitHub Release

**Tag:** `0.1.0-alpha.10.3`  
**Release title:** `Dummy OS Data 0.1.0-alpha.10.3 - PT15M Window Diagnostics`

## Dummy OS Data 0.1.0-alpha.10.3

Kleine diagnostische verbetering voor de Prices-shadowlaag. Deze release verandert de prijsselectie niet, maar maakt zichtbaar welk tijdvenster de door Stroomvoorspeller aangeleverde `prices_15m`-reeks daadwerkelijk bestrijkt.

### Nieuw
- Nieuw attribuut `pt15m_first_time` op de Prices-status/tijdlijn-attributen.
- Nieuw attribuut `pt15m_last_time` op de Prices-status/tijdlijn-attributen.
- De waarden worden bepaald uit de daadwerkelijk geldige PT15M-punten die uit `prices_15m` zijn geparsed.

### Gewijzigd
- Integratieversie naar `0.1.0-alpha.10.3`.
- Geen wijziging aan de selectie- of tariefberekening.

### Ongewijzigd
- PT15M blijft primair waar timestamps overeenkomen met het rollende venster.
- Bekende uurprijzen blijven expliciete gap-fallback.
- Forecast vult alleen ontbrekende bekende timestamps.
- De alpha.10.2 gas-listenerfix blijft ongewijzigd.
- EnergyZero blijft de actuele gasmarktbron.
- Tarieven blijven volledig configureerbaar.
- Geen fysieke EMS-sturing toegevoegd.

### Validatie
Na update/herladen controleren:
1. `sensor.do_prices_status` = `ok`.
2. `pt15m_slots` bevat het aantal geldige PT15M-punten.
3. `pt15m_first_time` toont de eerste timestamp van de bronreeks.
4. `pt15m_last_time` toont de laatste timestamp van de bronreeks.
5. Vergelijk dit venster met het actuele kwartier en `current_price_source` om te verklaren waarom `known_pt15m` of `known_hourly_fallback` wordt gebruikt.
6. `sensor.do_prices_gas_market` en `sensor.do_prices_gas_all_in` blijven correct werken.
7. Geen nieuwe `dummy_os_data` runtimefouten in het Home Assistant-logboek.
