## Dummy OS Energy 0.2.0-alpha.38

**Tag:** `0.2.0-alpha.38`

**Doel:** Step 8B shadow-prerelease waarin de Home Assistant EMS-bedienings- en statuslaag rechtstreeks op de bewezen EMS `0.0.1-alpha.76` runtime is aangesloten. Deze release blijft nadrukkelijk **shadow-only** en voert geen fysieke batterijcommando's uit.

### Alpha76 blijft functionele autoriteit
- Golden source blijft `bliek79/dummy-os-anker-ems` tag `0.0.1-alpha.76`.
- Energy Need, Preview, Plan72, Plan Store, Scheduler, Prestart, Safety, Action Controller en Execution blijven de vendored alpha76-bronnen.
- De immutable bronvergelijking blijft verplicht: kernbestanden worden byte-voor-byte met de alpha76-tag vergeleken; `const.py` mag uitsluitend de geïsoleerde domeinvervanging bevatten.
- Native forecastarchitectuur blijft 15 minuten / 72 uur / 288 slots.
- Geen reserve-, handels-, safety- of executionpolicy is opnieuw ontworpen.

### Handmatige planbediening nu direct op alpha76 Plan Store
- De drie planplaatsen lezen en schrijven rechtstreeks via `DummyOSEmsAlpha76Runtime.plan_store`, de exacte `AnkerEmsPlanStore` uit alpha76.
- Bestaande Dummy OS Energy entiteitsidentiteiten blijven waar mogelijk behouden.
- Actie gebruikt exact de alpha76 waarden `geen`, `laden`, `ontladen`.
- Execution mode gebruikt exact `direct` of `gepland`.
- Starttijd, vermogen, doel-SOC, maximale looptijd en maximale startvertraging worden op de overeenkomstige alpha76 Plan Store velden gemapt.
- De huidige minutenweergave voor maximale looptijd is uitsluitend een presentatieconversie naar het alpha76 veld `max_runtime_h`; er wordt geen EMS-logica toegevoegd.

### Scheduler / Safety / Controller / Execution status
- De actieve Home Assistant statuslaag leest nu rechtstreeks uit `DummyOSEmsAlpha76Runtime.data`.
- `DO Plan Scheduler` en `DO Plan Scheduler Ready` gebruiken de alpha76 Scheduler-uitvoer.
- `DO Plan Safety` en `DO Plan Safety Safe` gebruiken de alpha76 Safety-uitvoer.
- `DO Plan Execution Preview` en `DO Plan Execution Preview Ready` representeren de alpha76 Controller-uitvoer.
- Extra read-only status is beschikbaar voor Controller Ready en Execution Active.
- De oude Alpha35 Plan Store-, Scheduler-, Safety-, Execution Preview-, Operating Mode- en Manual Interface-bundel wordt niet meer door de actieve grid-support sensorbundle geregistreerd.

### Shadow-only grens blijft hard dicht
- `simulation_mode` blijft geforceerd `True`.
- `alpha76_runtime_shadow_only = True`.
- `alpha76_physical_autostart_wired = False`.
- De nieuwe entity surface bevat geen aanroep naar `async_execute_automatic_plan`.
- Het wijzigen van een handmatig plan mag alleen de Plan Store aanpassen en een nieuwe **shadow-evaluatie** aanvragen.
- Er wordt geen fysieke operating mode, richting of vermogenssetpoint aangestuurd.
- Fysieke cutover valt expliciet buiten deze release en vereist later afzonderlijke toestemming.

### Niet-EMS bediening behouden
- Energy Profile blijft beschikbaar.
- Presence Away Start / End en de bestaande Presence-schakelaars blijven behouden.
- Forecast-, prijs-, solar- en historiearchitectuur worden door Step 8B niet gewijzigd.

### CI-gate
Voor publicatie moet alles groen zijn:
- Python compile;
- immutable alpha76 source compare;
- golden EMS parity suite 50/50;
- alle niet-retired regressietests;
- Step 8B shadow-surface contract;
- release-consistency en package-verificatie.

### Live acceptatie na installatie
Na installatie blijft de integratie shadow-only. De eerste livegate bestaat uit één gecontroleerde Home Assistant-herstart en controle van de drie planplaatsen plus Scheduler/Safety/Controller-status. Hard fail bij fysieke batterijactie, setup/runtime exceptions, dubbele entity-registratie, terugkeer van Plan72 refreshstorm of afwijking van de alpha76 Plan Store/statusautoriteit.
