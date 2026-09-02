# GitHub Release

**Tag:** `0.1.0-alpha.11.4`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.4 - Canonical Home Power Input`

## Dummy OS Data 0.1.0-alpha.11.4

Deze alpha voegt de eerste formele input-/normalisatielaag voor Home Power toe. De bestaande Home Forecast blijft in deze release nog bewust op de huidige bron draaien, zodat eerst uitsluitend de nieuwe canonieke vermogenssensoren en tekenconventie live kunnen worden gevalideerd.

### Nieuw

- Configureerbare Home Power-bronrichting:
  - `consumption`: positief bronvermogen betekent verbruik/import;
  - `export`: positief bronvermogen betekent teruglevering/export.
- Nieuwe canonieke sensoren:
  - `sensor.do_input_home_power_raw`;
  - `sensor.do_home_power`;
  - `sensor.do_home_import_power`;
  - `sensor.do_home_export_power`.
- `sensor.do_input_home_power_raw` zet `W`/`kW` om naar watt zonder het bronteken te veranderen.
- `sensor.do_home_power` gebruikt intern altijd de vaste Dummy OS-conventie: positief = verbruik/import, negatief = export.
- `sensor.do_home_import_power` publiceert alleen de positieve verbruiks-/importcomponent.
- `sensor.do_home_export_power` publiceert alleen de positieve exportcomponent.
- Alle vier sensoren publiceren de gekozen bron, bronunit, tekenrichting en canonieke tekenconventie als attributen.

### Veiligheid en semantiek

- `unknown`, `unavailable`, lege of niet-numerieke bronwaarden worden niet naar `0 W` geconverteerd.
- Een ongeldige bron blijft als unavailable zichtbaar.
- De Config Flow accepteert uitsluitend een vermogenssensor in `W` of `kW`.
- De nieuwe inputlaag verandert bestaande historische forecastdata niet.
- Home Forecast wordt in deze alpha nog niet omgezet naar `sensor.do_home_power`; die koppeling volgt pas na geslaagde livevalidatie van de inputlaag.

### Validatie in Home Assistant

Controleer na installatie en volledige herstart:

1. Dat Dummy OS Data versie `0.1.0-alpha.11.4` toont.
2. Dat in de opties de Home Power-bron en de betekenis van een positieve bronwaarde kunnen worden gekozen.
3. Dat `sensor.do_input_home_power_raw` dezelfde richting/hetzelfde teken heeft als de geselecteerde bron, omgerekend naar watt.
4. Dat `sensor.do_home_power` bij verbruik positief en bij export negatief is.
5. Dat `sensor.do_home_import_power` bij verbruik gelijk is aan het positieve Home Power-vermogen en bij export `0 W` toont.
6. Dat `sensor.do_home_export_power` bij export de positieve grootte van de export toont en bij verbruik `0 W` toont.
7. Dat een tijdelijk unavailable bron niet als `0 W` wordt geregistreerd.
8. Dat de bestaande Home Forecast-entiteiten en 15-minutenhistorie ongewijzigd blijven functioneren.

### Ongewijzigd

- Native forecastarchitectuur blijft 15 minuten / 72 uur / 288 slots.
- Home Forecast-model en evaluatielogica blijven ongewijzigd.
- Weather, Solar, Prices en Degree Days blijven ongewijzigd.
- Geen EMS-planning of fysieke batterijsturing toegevoegd.
- Geen bestaande forecast- of packagebron uitgefaseerd.
