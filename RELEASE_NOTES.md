# GitHub Release

**Tag:** `0.1.0-alpha.11.6`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.6 - Bidirectional Grid Power Input`

## Dummy OS Data 0.1.0-alpha.11.6

Deze alpha corrigeert de netvermogensbron voor installaties met één bidirectionele netmeter. Dummy OS Data gebruikt nu één geselecteerde netsensor waarbij positief vermogen netafname betekent en negatief vermogen teruglevering. Import en export worden daar intern uit afgeleid.

### Nieuw en gecorrigeerd

- Eén configureerbare netvermogensbron: `grid_net_power_entity`.
- Vaste tekenconventie voor deze bron:
  - positief = netafname / import;
  - negatief = teruglevering / export.
- Nieuwe canonieke signed netsensor:
  - `sensor.do_data_grid_net_power`.
- Afgeleide positieve stromen:
  - `sensor.do_data_grid_import_power = max(grid_net, 0)`;
  - `sensor.do_data_grid_export_power = max(-grid_net, 0)`.
- De aparte bronselectors voor solar, batterij laden en batterij ontladen blijven behouden.
- `sensor.do_data_home_power` blijft berekend volgens:
  `solar + grid_import + battery_discharge - grid_export - battery_charge`.

### Migratie vanaf alpha.11.5

- De twee tijdelijke velden voor afzonderlijke grid import/export-bronnen worden niet meer gebruikt als actieve bronconfiguratie.
- Wanneer in alpha.11.5 dezelfde bidirectionele sensor voor zowel import als export was geselecteerd, wordt die sensor automatisch als voorinvulling gebruikt voor `grid_net_power_entity`.
- De definitieve `sensor.do_data_*`-entity-ID-regie blijft actief.

### Validatie in Home Assistant

Controleer na installatie en volledige herstart:

1. Dat Dummy OS Data versie `0.1.0-alpha.11.6` toont.
2. Dat in de opties nog maar één netveld zichtbaar is: `Bron netvermogen (+ afname / - teruglevering)`.
3. Dat daarnaast aparte bronnen zichtbaar zijn voor solar, batterij laden en batterij ontladen.
4. Dat `sensor.do_data_grid_net_power` exact dezelfde tekenrichting en vermogensgrootte volgt als de gekozen bidirectionele netsensor, omgerekend naar watt.
5. Dat bij positieve netwaarde `sensor.do_data_grid_import_power` dezelfde positieve waarde toont en `sensor.do_data_grid_export_power` 0 W toont.
6. Dat bij negatieve netwaarde `sensor.do_data_grid_import_power` 0 W toont en `sensor.do_data_grid_export_power` de positieve grootte van de teruglevering toont.
7. Dat `sensor.do_data_home_power` gelijk loopt met de energiebalans en als referentie vergeleken kan worden met de bestaande `sensor.home_power`.
8. Dat bestaande Home Forecast-functionaliteit en historische kwartierdata ongewijzigd blijven functioneren.

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
