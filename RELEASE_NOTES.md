# GitHub Release

**Tag:** `0.1.0-alpha.11.7`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.7 - Obsolete Home Input Cleanup`

## Dummy OS Data 0.1.0-alpha.11.7

Deze alpha ruimt de tijdelijke Home-inputentiteiten uit alpha.11.4 structureel op voordat Home Forecast later op de definitieve Dummy OS Data-laag wordt aangesloten.

### Gecorrigeerd

- Bekende automatisch aangemaakte alpha.11.4 Home-inputentiteiten worden uit de Home Assistant entity registry verwijderd.
- Hun actieve Home Assistant-state wordt tegelijk verwijderd, zodat oude waarden niet zichtbaar blijven in Ontwikkelaarstools.
- Als een registry-entry al verdwenen is maar een stale state nog aanwezig is, wordt ook die state veilig opgeschoond.
- Stale-state cleanup gebeurt alleen bij exact bekende oude entity-ID's met de verwachte alpha.11.4-signatuur.
- Handmatig hernoemde entiteiten blijven behouden.
- De cleanup draait vóór platformsetup en opnieuw erna, zodat ook reload-restanten direct verdwijnen.

### Te verwijderen tijdelijke entiteiten

- `sensor.dummy_os_input_home_power_raw` / `sensor.do_input_home_power_raw`
- `sensor.dummy_os_home_power` / `sensor.do_home_power`
- `sensor.dummy_os_home_import_power` / `sensor.do_home_import_power`
- `sensor.dummy_os_home_export_power` / `sensor.do_home_export_power`

### Definitieve Data-laag blijft leidend

- `sensor.do_data_grid_net_power`
- `sensor.do_data_grid_import_power`
- `sensor.do_data_grid_export_power`
- `sensor.do_data_solar_power`
- `sensor.do_data_battery_charge_power`
- `sensor.do_data_battery_discharge_power`
- `sensor.do_data_home_power`

### Validatie in Home Assistant

Controleer na installatie en volledige herstart:

1. Dat Dummy OS Data versie `0.1.0-alpha.11.7` toont.
2. Dat de tijdelijke alpha.11.4 Home-inputentiteiten niet meer in Ontwikkelaarstools → Statussen voorkomen.
3. Dat de zeven definitieve `sensor.do_data_*`-vermogensentiteiten nog aanwezig zijn.
4. Dat `sensor.do_data_home_power` nog correct wordt berekend uit grid net, solar, batterij laden en batterij ontladen.
5. Dat bestaande Home Forecast-functionaliteit en historische kwartierdata ongewijzigd blijven functioneren.

### Technische validatie

- Python-bronnen compileren succesvol.
- 24 unit- en releaseconsistentietests slagen.
- Manifest, strings en Nederlandse/Engelse vertalingen zijn als JSON gevalideerd.
- Native forecastarchitectuur blijft 15 minuten / 72 uur / 288 slots.

### Ongewijzigd

- Home Forecast wordt in deze alpha nog niet omgezet naar `sensor.do_data_home_power`; eerst wordt de cleanup live gevalideerd.
- Weather, Solar Forecast, Prices en Degree Days blijven ongewijzigd.
- Geen EMS-planning of fysieke batterijsturing toegevoegd.
