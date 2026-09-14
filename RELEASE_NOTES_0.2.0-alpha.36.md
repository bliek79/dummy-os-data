## Dummy OS Energy 0.2.0-alpha.36

**Tag:** `0.2.0-alpha.36`

**Doel:** gecontroleerde herstel-prerelease voor live stabiliteitsvalidatie. Deze versie is niet bedoeld als fysieke EMS-cutover.

### Alpha76 EMS-kopie als functionele autoriteit
- De bewezen EMS-logica uit `dummy-os-anker-ems` tag `0.0.1-alpha.76` is vendored als golden runtime.
- Kritieke planner-, Plan Store-, Scheduler-, Safety- en Execution-bronbestanden worden in CI byte-voor-byte tegen de immutable alpha76-tag gecontroleerd; alleen het integration-domain in `const.py` is geïsoleerd aangepast.
- De huidige Dummy OS Data forecastlaag levert de input via een adapter; er is geen nieuwe EMS-policy toegevoegd.
- De recovery runtime blijft shadow-only: automatische fysieke uitvoering is niet aangesloten en de arm wordt geforceerd uitgeschakeld.

### 15 minuten / 72 uur / 288 slots
- De native Dummy OS Data forecastarchitectuur blijft 15 minuten, 72 uur en 288 slots.
- Voor alpha76-beslissingen wordt de gevalideerde input naar de oorspronkelijke uurcontracten vertaald zonder beleidslogica te wijzigen.
- Afgeleide kwartierpresentatie is niet de autoriteit voor fysieke uitvoering.

### Home Assistant event-loop herstel
- Planner state-change callbacks zijn expliciet Home Assistant `@callback` callbacks.
- `_schedule_refresh()` blijft hierdoor op de HA event loop voordat `hass.async_create_task()` wordt aangeroepen.
- Dit repareert de live foutstorm met thread-unsafe `async_create_task` en niet-geawaitede planner-coroutines die in alpha35 is waargenomen.

### Lifecycle en migraties
- De bestaande alpha35 startup-/shutdown-afhandeling is behouden rond de nieuwe alpha76 shadow runtime.
- Background cloud-source taken worden bij unload geannuleerd en afgewacht.
- Solar, Prices, Degree Days en de hoofdcoordinator worden opnieuw correct afgesloten.
- Bestaande veilige entity-ID- en Degree Days-migraties zijn hersteld; de EMS-kopie mag deze bestaande forecastlaag-contracten niet beschadigen.

### CI-gate
- Python compile: verplicht groen.
- Vendored alpha76 bronvergelijking: verplicht groen.
- Golden EMS parity suite: 50/50 tests verplicht groen.
- Alle niet-uitgefaseerde regressietests: verplicht groen.
- Alpha35 planner-redesigntests die strijdig zijn met de gekozen alpha76-kopie zijn expliciet retired en tellen niet als releasecontract.

### Live acceptatie na installatie
Deze prerelease moet eerst in Home Assistant worden gevalideerd met Dummy OS Energy nog zonder fysieke automatische batterijbesturing:
1. schoon opstarten en logcontrole;
2. 15 minuten rusttest;
3. gecontroleerde refresh-/stresstest;
4. minimaal 6 uur, bij voorkeur 12-24 uur duurtest.

Hard fail bij nieuwe thread-unsafe `async_create_task`, niet-geawaitede planner-coroutines, planner-refresh exception-loops of blijvend abnormale CPU/loggroei.
