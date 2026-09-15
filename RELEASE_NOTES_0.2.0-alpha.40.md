## Dummy OS Energy 0.2.0-alpha.40

**Tag:** `0.2.0-alpha.40`

## Doel

G5.2 live-parityacceptatie voorbereiden met één echte, bevroren live invoer die door twee beslispaden wordt herhaald, terwijl Dummy OS Energy volledig shadow-only blijft.

## Wat Alpha40 toevoegt

Alpha40 voegt een strikt diagnostische frozen-live paritylaag toe bovenop de in Alpha39 bewezen alpha76-kopie.

Bij één druk op `DO EMS G5 Capture Frozen Live Parity` gebeurt uitsluitend het volgende:

1. de actuele Dummy OS Data plannerinput wordt één keer opgebouwd;
2. referentietijd, 72 transporturen / 288 kwartierslots, planner-start-SOC, SOC-bridge, profiel en relevante EMS-configuratie worden als één snapshot bevroren;
3. dezelfde snapshot wordt rechtstreeks door de immutable/vendored EMS `0.0.1-alpha.76` kern verwerkt;
4. dezelfde snapshot wordt via de Dummy OS Data -> alpha76 adapterroute verwerkt;
5. beide resultaten worden exact structureel vergeleken;
6. de evidence en een deterministische SHA256 snapshot-fingerprint worden persistent opgeslagen.

De uitkomst is uitsluitend `pass`, `mismatch` of `blocked`.

## Nieuwe G5-entiteit

- `button.do_ems_g5_capture_frozen_live_parity`

Home Assistant kan door de bestaande device/entity naming de prefix `dummy_os_energy_` in het uiteindelijke entity-id opnemen. De knop publiceert na de capture onder meer `status`, `snapshot_fingerprint`, `exact_match`, `difference_count`, `differences`, `blockers`, `golden_decision` en `copy_decision` als attributen.

De knop is bedoeld om zichtbaar als drukknop in het bestaande vierkoloms G5 Live A/B-dashboard te worden opgenomen.

## Exacte A/B-definitie

Pad A - golden reference:

`frozen live input -> immutable/vendored alpha76 core`

Pad B - nieuwe kopie:

`dezelfde frozen live input -> Dummy OS Data alpha76 adapter -> dezelfde alpha76 core`

G5 is alleen groen wanneer de functionele uitvoer exact gelijk is en er geen onverklaarde verschillen worden gerapporteerd.

## Harde shadow-only grens

De G5-capture:

- muteert de Plan Store niet;
- schrijft niet naar Scheduler of Safety;
- roept de Execution Controller niet aan;
- voert geen `hass.services.async_call` uit;
- stuurt geen operating-mode-, direction- of power-setpointcommando;
- publiceert `physical_execution_authority=False`;
- publiceert `service_calls_performed=False`;
- publiceert `plan_store_mutated=False`;
- verleent geen cutoverbevoegdheid.

De bestaande Alpha39 shadow-lifecycleknoppen blijven ongewijzigd beschikbaar.

## Golden source

De bindende alpha76 kernbestanden blijven byte-voor-byte gelijk aan `bliek79/dummy-os-anker-ems` tag `0.0.1-alpha.76`:

- energy_need.py
- planner_preview.py
- planner_72h.py
- planner_action_bridge.py
- plan_store.py
- scheduler.py
- prestart_validator.py
- safety_guard.py
- action_controller.py
- execution.py

`const.py` in de vendored alpha76-laag mag uitsluitend de bekende geïsoleerde DOMAIN-vervanging bevatten.

## CI- en publicatiegate

Publicatie mag alleen plaatsvinden wanneer groen zijn:

- Python compile;
- immutable alpha76 source compare;
- bestaande golden EMS parity fixtures;
- alle niet-retired regressies;
- `tests/test_g5_frozen_live_parity.py`;
- Alpha40 versie-/button-/shadow-contractcontrole;
- package-verificatie.

## Live acceptatie na installatie

1. installeer Alpha40 over Alpha39 en herstart Home Assistant schoon;
2. controleer dat de G5 capturebutton aanwezig is;
3. neem de knop zichtbaar op in de bestaande G5 Live A/B-dashboardkaart;
4. druk de knop exact één keer in voor de G5.2-capture;
5. beoordeel de gepubliceerde status en attributen.

Acceptatie:

- `pass` + `exact_match=True` + `difference_count=0`: G5.2 parity groen;
- `mismatch`: G5 blijft open en de verschillen worden onderzocht;
- `blocked`: G5 blijft open omdat de snapshot niet volledig/bruikbaar was.

G6 start pas nadat G5 volledig groen is. Fysieke cutover blijft een aparte, later expliciet te autoriseren beslissing.
