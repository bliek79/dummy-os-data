## Dummy OS Energy 0.2.0-alpha.37

**Tag:** `0.2.0-alpha.37`

**Doel:** gecontroleerde herstel-prerelease voor de tweede live stabiliteitsvalidatie van de alpha76 EMS-kopie. Deze versie is uitsluitend shadow-only en is niet bedoeld als fysieke EMS-cutover.

### Livebevinding alpha36
- De Home Assistant event-loopfix uit alpha36 is live bevestigd: de eerdere thread-unsafe `hass.async_create_task`, niet-geawaitede `_async_refresh_result`-coroutines en bijbehorende RuntimeError/RuntimeWarning kwamen niet terug.
- Alpha36 bracht wel een afzonderlijke Plan72-belastingsfout aan het licht: `sensor.dummy_os_energy_do_plan_72h` publiceerde een te grote dubbele alpha76-plannerstructuur en werd door ruwe SOC- en actuele PV-telemetrie te vaak herberekend.

### Plan72 state/Recorder herstel
- De exacte interne `alpha76_plan72`-uitvoer blijft beschikbaar in de planner-cache voor parity en diagnostiek, maar wordt niet meer als Home Assistant state attribute gepubliceerd.
- `alpha76_plan72` staat daarnaast expliciet in de on-recorded attribute-set.
- Hiermee mag de eerdere `State attributes ... exceed maximum size of 16384 bytes`-waarschuwing voor DO Plan 72h niet meer terugkeren.

### Begrensde zware plannerrefresh
- DO Plan 72h omzeilt de generieke parent-listeners die iedere ruwe SOC-update en iedere Solar/Prices-notificatie als zware refresh behandelden.
- Solar-notificaties leiden alleen tot een nieuwe Plan72-berekening wanneer de forecastbron-signature werkelijk verandert; actuele PV-vermogenssamples alleen zijn geen trigger meer.
- Prices-notificaties leiden alleen tot een nieuwe berekening wanneer de elektriciteitsprijsbron/signature werkelijk verandert; gas-only republish/no-op notifications zijn geen zware Plan72-trigger.
- SOC wordt nog steeds in iedere Plan72-snapshot actueel ingelezen. Een SOC-state-update op zichzelf start echter geen zware Plan72-berekening meer; alleen herstel van een eerder ongeldige SOC-bridge mag een recovery-refresh veroorzaken.
- Periodieke zware Plan72-refresh blijft begrensd op eenmaal per uur om `:05` tussen 05:00 en 22:00. Startup, echte bronwijziging en herstel blijven geldige refreshredenen.

### EMS-beleid ongewijzigd
- De functionele EMS-autoriteit blijft `dummy-os-anker-ems` tag `0.0.1-alpha.76`.
- De vendored planner-, Plan Store-, Scheduler-, Safety- en Execution-bronnen worden nog steeds byte-voor-byte tegen de immutable alpha76-tag gecontroleerd, met uitsluitend de geïsoleerde domain-aanpassing in `const.py`.
- Native forecastarchitectuur blijft 15 minuten / 72 uur / 288 slots.
- Geen plannerpolicy, reserveberekening, handelslogica, safetylogica of executiongedrag is gewijzigd.
- Automatische fysieke batterijbesturing blijft niet aangesloten.

### CI-gate
- Python compile verplicht groen.
- Immutable alpha76 bronvergelijking verplicht groen.
- Golden EMS parity suite 50/50 verplicht groen.
- Alle niet-retired regressietests verplicht groen.
- Nieuwe alpha37-regressiegate controleert expliciet het Plan72 state/Recorder-contract, het ontbreken van raw-SOC refresh wiring, bron-signature filtering, het periodieke refreshvenster en het gesloten fysieke control path.

### Live acceptatie
Na installatie wordt Stap 4 opnieuw uitgevoerd: gecontroleerd inschakelen, circa twee minuten startupcontrole en daarna minimaal tien minuten idle observatie. Hard fail bij terugkeer van thread/coroutinefouten, 16 KB Plan72-attribuutwaarschuwingen of een nieuwe zware Plan72-refreshstorm. Pas daarna mag Stap 5 van de stabiliteitsroute beginnen.
