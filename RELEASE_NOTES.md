# GitHub Release

**Tag:** `0.1.0-alpha.10.2`  
**Release title:** `Dummy OS Data 0.1.0-alpha.10.2 - Gas Source Listener Fix`

## Dummy OS Data 0.1.0-alpha.10.2

Gerichte runtimefix voor de gasprijslaag. Na een Home Assistant-herstart kon Dummy OS Data de EnergyZero-gassensor lezen voordat die beschikbaar was. Daardoor bleven `sensor.do_prices_gas_market` en `sensor.do_prices_gas_all_in` op `None` staan tot een latere prijsrefresh.

### Opgelost
- Dummy OS Data luistert nu rechtstreeks naar state-wijzigingen van de ingestelde EnergyZero-gasmarktprijs-sensor.
- Zodra EnergyZero na startup een geldige gasprijs publiceert, worden de Dummy OS-gassensoren direct opnieuw gepubliceerd.
- Ook wijzigingen van `input_number.gas_markup_per_m3` worden direct gevolgd, zodat de bestaande gasopslag-automatisering zonder wachttijd doorwerkt.

### Gewijzigd
- Integratieversie naar `0.1.0-alpha.10.2`.
- Gasstates zijn niet meer afhankelijk van de 30-minuten Stroomvoorspeller-refresh om na startup beschikbaar te worden.

### Ongewijzigd
- De alpha.10.1-fix voor de actuele stroomprijsselectie blijft ongewijzigd.
- PT15M blijft primair, met bekende uurprijzen als expliciete gap-fallback.
- Tariefprofiel en ANWB-componenten blijven volledig configureerbaar.
- EnergyZero blijft de actuele gasmarktbron.
- `input_number.gas_markup_per_m3` blijft de actieve variabele gasopslag leveren.
- Geen fysieke EMS-sturing toegevoegd.

### Validatie
Na update en Home Assistant-herstart controleren:
1. `sensor.do_prices_status` = `ok`.
2. `sensor.energyzero_today_gas_current_hour_price` krijgt een geldige waarde na startup.
3. `sensor.do_prices_gas_market` neemt die waarde automatisch over zonder 30 minuten te wachten.
4. `sensor.do_prices_gas_all_in` = gasmarktprijs + actieve `input_number.gas_markup_per_m3`.
5. Een wijziging van `input_number.gas_markup_per_m3` werkt direct door in `sensor.do_prices_gas_all_in`.
6. Geen nieuwe `dummy_os_data` runtimefouten in het Home Assistant-logboek.
