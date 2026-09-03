# GitHub Release

**Tag:** `0.1.0-alpha.12.4`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.4 - Shared Dummy OS Brand Icon`

## Dummy OS Forecast 0.1.0-alpha.12.4

Deze pre-release is uitsluitend een branding-update. Dummy OS Forecast gebruikt vanaf deze versie exact hetzelfde integratie-icoon als Dummy OS EMS.

### Wijziging

- toegevoegd: `custom_components/dummy_os_data/brand/icon.png`;
- het bestand is byte-voor-byte gelijk aan `custom_components/anker_ems/brand/icon.png` uit Dummy OS EMS;
- geen aparte Forecast-variant: bewust gedeelde Dummy OS-branding.

### Ongewijzigd

- Integratienaam: **Dummy OS Forecast**.
- Technisch domain: `dummy_os_data`.
- Source, Energy, Solar, Weather, Degree Days en Prices zijn functioneel ongewijzigd.
- De Degree Days cleanup uit alpha.12.3 blijft ongewijzigd aanwezig.
- Native architectuur blijft **15 minuten / 72 uur / 288 slots**.
- Geen forecastmodel, berekening, migratie, entity-ID of fysieke EMS-sturing is gewijzigd.

### Controle na installatie

1. Controleer dat versie `0.1.0-alpha.12.4` draait onder **Dummy OS Forecast**.
2. Controleer dat het Dummy OS-icoon zichtbaar wordt bij de integratie. Home Assistant/HACS kan branding cachen; een volledige herstart en eventueel verversen van de frontend kan nodig zijn.
3. Controleer de Degree Days-set nogmaals na de alpha.12.3 cleanup: alleen de canonieke `sensor.do_degree_days_*` entiteiten horen over te blijven.
