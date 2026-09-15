## Dummy OS Energy 0.2.0-alpha.39

**Tag:** `0.2.0-alpha.39`

## Doel

Step 8G shadow-validatie van de originele EMS alpha76 handmatige lifecycle-handoff, zonder fysieke batterijuitvoering.

## Aanleiding

Alpha38 bewees live dat de Home Assistant control surface rechtstreeks naar de alpha76 Plan Store schrijft en dat Scheduler, Safety en Controller uit dezelfde alpha76 runtime lezen. Bij een handmatige wijziging naar `action=laden` bleef het plan echter terecht op `lifecycle_status=concept` staan. De originele alpha76 Scheduler maakt een conceptplan nog niet kandidaat/startklaar; de originele `start_plan_now` service zet het plan eerst op `pending` en ververst daarna de runtime voordat fysieke uitvoering wordt aangeroepen.

## Alpha39 wijziging

Alpha39 voegt uitsluitend drie shadow-validatieknoppen toe, één per planplaats. Een druk op zo'n knop voert alleen de originele alpha76 pre-execution lifecycle uit:

1. `execution_mode` wordt `direct`;
2. de exacte vendored `AnkerEmsPlanStore.async_mark_lifecycle(...)` zet het plan op `pending`;
3. de alpha76 runtime wordt ververst;
4. de route stopt daar.

Er wordt geen Execution Controller aangeroepen en er wordt geen fysiek batterijcommando verstuurd.

## Nieuwe entiteiten

- `button.do_plan_1_shadow_start_ready`
- `button.do_plan_2_shadow_start_ready`
- `button.do_plan_3_shadow_start_ready`

Home Assistant kan door bestaande entity naming de device-prefix `dummy_os_energy_` in het uiteindelijke entity-id opnemen.

## Harde shadow-only grens

- `simulation_mode=True` blijft geforceerd;
- `alpha76_physical_autostart_wired=False` blijft gelden;
- geen call naar `async_execute_selected_plan`;
- geen call naar `async_execute_automatic_plan`;
- geen `hass.services.async_call` in de nieuwe handofflaag;
- geen operating-mode-, direction- of power-setpointcommando;
- physical execution blijft buiten Step 8 en vereist aparte expliciete toestemming.

## Golden source

De volgende bindende alpha76 kernbestanden blijven byte-voor-byte gelijk aan `bliek79/dummy-os-anker-ems` tag `0.0.1-alpha.76`:

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

## CI-gate

Publicatie mag alleen plaatsvinden wanneer groen zijn:

- Python compile;
- immutable alpha76 source compare;
- golden parity 50/50;
- alle niet-retired regressies;
- Step 8G shadow-handoff contract;
- release-consistency;
- package-verificatie.

## Live acceptatie

Na installatie blijft de release shadow-only. Voor Plan 1 wordt de reeds ingestelde testconfiguratie gebruikt. Na een druk op `DO Plan 1 Shadow Start Ready` moeten minimaal gelden:

- `lifecycle_status=pending`;
- Scheduler selecteert Plan 1 als `startklaar` wanneer overige alpha76 voorwaarden dit toelaten;
- Safety en Controller evalueren dezelfde geselecteerde Plan 1 context;
- `execution_active=false`;
- `physical_control=false`;
- de batterij ontvangt geen fysieke actie.
