# GitHub Release

**Tag:** `0.1.0-alpha.10.1`  
**Release title:** `Dummy OS Data 0.1.0-alpha.10.1 - Current Price Selection Fix`

## Dummy OS Data 0.1.0-alpha.10.1

Gerichte hotfix voor de Prices-shadowlaag. In alpha.10.0 kon een ontbrekend passend huidig PT15M-punt ertoe leiden dat de `*_current`-sensoren het eerste toekomstige forecastpunt gebruikten. Deze release voorkomt dat en houdt actuele bekende prijzen en forecast strikt uit elkaar.

### Opgelost
- `sensor.do_prices_market_current`, `sensor.do_prices_import_current` en `sensor.do_prices_export_current` vallen niet langer terug op het eerste toekomstige forecastpunt.
- De volledige bekende uurprijsreeks uit Stroomvoorspeller wordt nu altijd als gap-fallback naar kwartierslots genormaliseerd.
- Echte `prices_15m[]`-punten overschrijven de bijbehorende uurfallbacks en blijven dus primair waar beschikbaar.
- Forecastwaarden vullen uitsluitend timestamps waarvoor geen bekende prijs bestaat.
- Bij een echte datagap wordt de huidige prijs `None` in plaats van stilzwijgend een toekomstige forecast als actuele prijs te tonen.

### Gewijzigd
- Integratieversie naar `0.1.0-alpha.10.1`.
- Diagnostiek uitgebreid met `pt15m_slots` en `current_price_source`.
- `actual_source` maakt nu expliciet zichtbaar dat PT15M primair is met uurdata als gap-fallback.

### Ongewijzigd
- Tariefprofiel en ANWB-componenten blijven volledig configureerbaar.
- Import en export blijven afzonderlijk gemodelleerd.
- Gas actual blijft afkomstig uit EnergyZero.
- `input_number.gas_markup_per_m3` blijft de actieve variabele gasopslag leveren.
- Geen fysieke EMS-sturing toegevoegd.

### Validatie
Na update/herladen controleren:
1. `sensor.do_prices_status` = `ok`.
2. `sensor.do_prices_market_current` heeft een timestamp van het actuele kwartier, niet van morgen.
3. `current_price_source` is bij voorkeur `known_pt15m`; `known_hourly_fallback` is toegestaan wanneer PT15M voor het actuele slot ontbreekt.
4. `sensor.do_prices_import_current` = markt incl. btw + 0,01800 + 0,11085 EUR/kWh voor het huidige ANWB-profiel.
5. `sensor.do_prices_export_current` gebruikt de afzonderlijke exportcomponenten.
6. `sensor.do_prices_gas_market` blijft de EnergyZero-gasmarktprijs tonen.
7. `sensor.do_prices_gas_all_in` blijft marktprijs + actieve gasopslag tonen.
8. Geen nieuwe `dummy_os_data` runtimefouten in het Home Assistant-logboek.
