# GitHub Release

**Tag:** `0.1.0-alpha.11.5`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.5 - Data Home Power Source Contract`

## Dummy OS Data 0.1.0-alpha.11.5

Deze alpha corrigeert de Home Power-inputlaag structureel. Dummy OS Data gebruikt niet langer een reeds samengestelde Home Power-sensor als primaire bron voor de nieuwe canonieke Data-laag, maar laat de gebruiker de onderliggende energiestromen selecteren en bouwt daaruit zelf het woningvermogen op.

### Nieuw

- Vijf configureerbare onderliggende vermogensbronnen in de Config/Options Flow:
  - netafname / grid import;
  - teruglevering / grid export;
  - solarproductie;
  - batterij laden;
  - batterij ontladen.
- Iedere bron wordt naar watt genormaliseerd en als positieve vermogensgrootte gebruikt.
- Dummy OS Data berekent canoniek woningvermogen volgens:
  `solar + grid_import + battery_discharge - grid_export - battery_charge`.
- Definitieve Data-entiteiten:
  - `sensor.do_data_grid_import_power`;
  - `sensor.do_data_grid_export_power`;
  - `sensor.do_data_solar_power`;
  - `sensor.do_data_battery_charge_power`;
  - `sensor.do_data_battery_discharge_power`;
  - `sensor.do_data_home_power`.

### Entity-ID-regie

- De tijdelijke alpha.11.4 Home-inputentiteiten worden alleen verwijderd wanneer ze aantoonbaar automatisch door Home Assistant zijn aangemaakt.
- Handmatig hernoemde entiteiten blijven ongemoeid.
- De definitieve `do_data_*`-namen worden geborgd via vaste unique-ID's, `suggested_object_id`, expliciete migratiedoelen en migratie vóór en na platformsetup.
- Daarmee wordt voorkomen dat Home Assistant opnieuw onverwachte `sensor.dummy_os_*`-entity-ID's als definitieve Data-entiteiten laat staan.

### Configuratie

- De eerdere primaire keuze `Bron woningvermogen` voor de nieuwe Data-inputlaag vervalt.
- De gebruiker kiest nu rechtstreeks de vijf onderliggende vermogensstromen waaruit Dummy OS Data Home Power opbouwt.
- Alleen vermogenssensoren met `W` of `kW` worden geaccepteerd.
- Ontbrekende of ongeldige bronwaarden worden niet stilzwijgend als `0 W` geïnterpreteerd.

### Validatie in Home Assistant

Controleer na installatie en volledige herstart:

1. Dat Dummy OS Data versie `0.1.0-alpha.11.5` toont.
2. Dat in de opties vijf afzonderlijke bronselectors voor grid import, grid export, solar, batterij laden en batterij ontladen zichtbaar zijn.
3. Dat de zes definitieve `sensor.do_data_*`-entiteiten bestaan.
4. Dat de vijf bronsensoren dezelfde actuele vermogensgrootte tonen als de gekozen HA-bronnen, omgerekend naar watt.
5. Dat `sensor.do_data_home_power` gelijk loopt met de verwachte formule en als referentie kan worden vergeleken met de bestaande `sensor.home_power`.
6. Dat automatisch gegenereerde tijdelijke alpha.11.4 Home-inputentiteiten niet als dubbele actieve Data-entiteiten blijven bestaan.
7. Dat bestaande Home Forecast-functionaliteit en historische kwartierdata niet onverwacht worden beschadigd.

### Technische validatie

- Python-bronnen compileren succesvol.
- 24 unit- en releaseconsistentietests slagen.
- Manifest, strings en Nederlandse/Engelse vertalingen zijn als JSON gevalideerd.
- Native forecastarchitectuur blijft 15 minuten / 72 uur / 288 slots.

### Ongewijzigd

- Home Forecast-model en evaluatielogica worden in deze alpha niet inhoudelijk aangepast.
- Weather, Solar Forecast, Prices en Degree Days blijven ongewijzigd.
- Geen EMS-planning of fysieke batterijsturing toegevoegd.
- Geen bestaande forecastbron wordt op basis van deze alpha uitgefaseerd.
