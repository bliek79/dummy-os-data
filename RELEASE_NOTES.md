# GitHub Release

**Tag:** `0.1.0-alpha.10.0`  
**Release title:** `Dummy OS Data 0.1.0-alpha.10.0 - Prices Shadow Layer`

## Dummy OS Data 0.1.0-alpha.10.0

Deze release introduceert de eerste native Prices-shadowlaag voor Dummy OS Data. De module is uitsluitend observerend en berekent prijzen; er is nog geen EMS-uitvoering of fysieke sturing gekoppeld.

### Nieuw
- Nieuwe native Prices-coordinator in `prices.py`.
- Bekende stroomprijzen uit Stroomvoorspeller `prices.json` met voorkeur voor echte `prices_15m[]` PT15M-data.
- Automatische fallback naar uurprijzen als PT15M tijdelijk niet beschikbaar is; uurwaarden blijven herkenbaar als `known_hourly_fallback`.
- Stroomforecast uit Stroomvoorspeller `forecast.json`.
- Uurforecast wordt op de interne 15-minuten tijdas geplaatst, maar blijft expliciet gemarkeerd met `source_resolution_minutes: 60`.
- Bekende marktprijzen hebben altijd voorrang boven forecastwaarden op overlappende timestamps.
- Marktprijsnormalisatie van EUR/MWh naar EUR/kWh.
- Eigen import- en exportprijsberekening op basis van configureerbare tariefcomponenten.
- Import en export zijn architectonisch volledig gescheiden zodat de 2027-situatie zonder herbouw ondersteund kan worden.
- EnergyZero-gassensor als actuele gasmarktbron.
- Eigen all-in gasprijsberekening bovenop de EnergyZero-marktprijs.
- Nieuw configureerbaar tariefprofiel met profiel-ID, leverancier en `valid_from`.
- Nieuwe shadow-entiteiten:
  - `sensor.do_prices_status`
  - `sensor.do_prices_market_current`
  - `sensor.do_prices_import_current`
  - `sensor.do_prices_export_current`
  - `sensor.do_prices_timeline`
  - `sensor.do_prices_tariff_profile`
  - `sensor.do_prices_gas_market`
  - `sensor.do_prices_gas_all_in`

### Gewijzigd
- Integratieversie naar `0.1.0-alpha.10.0`.
- Options Flow uitgebreid met afzonderlijke stroom-import-, stroom-export- en gastariefcomponenten.
- Vaste leveringskosten, netbeheerkosten en vermindering energiebelasting worden apart geconfigureerd en niet in de marginale kwartierprijs verstopt.
- README bevat nu expliciete bronvermelding voor Stroomvoorspeller.nl en CC BY 4.0.

### Ontwerpregels
- De operationele tariefwaarden zijn niet hardcoded in de prijsengine.
- Ruwe EPEX-marktprijs, leverancierscomponent, belasting en all-in resultaat blijven afzonderlijk zichtbaar.
- Historische kosten moeten later de daadwerkelijk gebruikte tariefsnapshot bewaren; toekomstige tariefwijzigingen mogen bestaande historie nooit herprijzen.
- Import en export worden vanaf de eerste implementatie als afzonderlijke prijsstromen behandeld, ook wanneer de actuele tariefwaarden voorlopig gelijk zijn.
- Stroomforecast en bekende prijs houden hun oorspronkelijke bronresolutie zichtbaar om schijnbare kwartiernauwkeurigheid te voorkomen.

### Ongewijzigd
- Home Forecast blijft modelversie 0.4.
- Weather blijft de bestaande Open-Meteo 15-minuten / 72-uurs bronlaag gebruiken.
- Degree Days / Heat History blijft als aparte shadowlaag actief.
- Bestaande Home-, Weather- en Degree Days-entiteiten worden niet hernoemd.
- Geen batterij-, boiler-, warmtepomp- of andere fysieke sturing toegevoegd.

### Validatie
Na installatie/herladen controleren:

1. `sensor.do_prices_status` wordt `ok`.
2. Attribuut `has_pt15m` is `true` als Stroomvoorspeller echte kwartierdata levert.
3. `sensor.do_prices_timeline` bevat maximaal 288 punten en `resolution_minutes: 15`.
4. Bekende punten hebben `kind: known_pt15m`; forecastpunten `kind: forecast_hour` en `source_resolution_minutes: 60`.
5. `sensor.do_prices_market_current` toont de actuele marktprijs incl. btw in EUR/kWh.
6. `sensor.do_prices_import_current` en `sensor.do_prices_export_current` reageren afzonderlijk op de ingestelde tariefcomponenten.
7. `sensor.do_prices_tariff_profile` toont het actieve profiel en `valid_from`.
8. `sensor.do_prices_gas_market` volgt de ingestelde EnergyZero-gassensor.
9. `sensor.do_prices_gas_all_in` is marktprijs + ingestelde gasleverancierscomponent + energiebelasting.
10. Geen nieuwe `dummy_os_data` setup- of runtimefouten in het Home Assistant-logboek.
11. `sensor.do_prices_timeline` tijdens deze alpha uit Recorder houden vanwege het grote live `points`-attribuut.
