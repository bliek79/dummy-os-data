# GitHub Release

**Tag:** `0.1.0-alpha.11.9`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.9 - Internal Gas Tariff Profile`

## Dummy OS Data 0.1.0-alpha.11.9

Deze alpha maakt de interne Dummy OS Data-tariefconfiguratie leidend voor gas. Alleen de gasmarktprijs blijft extern; leverancierstoeslag, energiebelasting, vaste leveringskosten en netbeheerkosten worden binnen Dummy OS Data beheerd en blijven eenvoudig wijzigbaar via de Options Flow.

### Gewijzigd

- `gas_variable_addon` wordt uitsluitend berekend uit `gas_supplier_incl_vat + gas_tax_incl_vat` uit Dummy OS Data Options.
- `sensor.do_prices_gas_all_in` gebruikt daardoor geen externe gas-markup-helper meer.
- Prices luistert voor gas alleen nog naar de externe gasmarktprijsbron.
- `sensor.do_prices_gas_all_in` rapporteert `variable_addon_source: dummy_os_data_options`.
- De attributen tonen ook de intern geconfigureerde vaste leveringskosten en netbeheerkosten.
- `tariff_edit_surface: Dummy OS Data Options` maakt expliciet waar toekomstige tariefwijzigingen moeten worden gedaan.

### Tarieven eenvoudig aanpassen

De bestaande Dummy OS Data Options Flow blijft de centrale plek voor tariefwijzigingen. Voor gas zijn daar onder meer beschikbaar:

- `gas_supplier_incl_vat`
- `gas_tax_incl_vat`
- `gas_fixed_supply_per_day`
- `gas_grid_per_day`
- `tariff_valid_from`

Voor elektriciteit blijven aparte import- en exportcomponenten beschikbaar en ongewijzigd.

### Externe bron

- Alleen de gasmarktprijs blijft extern via de ingestelde `gas_market_entity`.
- De standaardbron blijft `sensor.energyzero_today_gas_current_hour_price`.
- `input_number.gas_markup_per_m3` maakt geen deel meer uit van de Dummy OS Data Prices-productieketen.

### Behouden

- Home Forecast blijft de canonieke `sensor.do_data_home_power` gebruiken.
- De native forecastarchitectuur blijft 15 minuten / 72 uur / 288 slots.
- Weather, Solar Forecast en Degree Days blijven functioneel ongewijzigd.
- Geen EMS-planning of fysieke batterijsturing toegevoegd.

### Technische validatie

De gasprijswijziging uit PR #42 is vóór deze release technisch gevalideerd:

- Python compile geslaagd.
- Volledige unit-testset geslaagd.
- Gerichte regressietest controleert dat `input_number.gas_markup_per_m3` niet terugkomt in de Prices-productieketen.
- Releaseconsistentietest controleert de interne gas-tariefarchitectuur.

### Live validatie in Home Assistant

Na installatie en volledige herstart controleren:

1. Dummy OS Data toont versie `0.1.0-alpha.11.9`.
2. `sensor.do_prices_gas_market` blijft de externe marktprijs tonen.
3. `sensor.do_prices_gas_all_in` gebruikt de interne Dummy OS Data-tariefcomponenten.
4. `variable_addon_source` is `dummy_os_data_options`.
5. Wijzigen van de gaswaarden via Dummy OS Data Options werkt correct na reload/herstart.
6. De oude `input_number.gas_markup_per_m3` heeft geen invloed meer op `sensor.do_prices_gas_all_in`.
7. Elektriciteits-import/exportprijzen en overige forecastlagen blijven ongewijzigd functioneren.

De wijziging wordt pas als volledig live gevalideerd gemarkeerd nadat deze controles in Home Assistant zijn uitgevoerd.
