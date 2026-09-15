## Dummy OS Energy 0.2.0-alpha.41

**Tag:** `0.2.0-alpha.41`

## Doel

Alpha41 corrigeert uitsluitend de G5.2 frozen-live acceptatievalidatie zodat deze het werkelijke productiecontract van Dummy OS Data beoordeelt. Er wordt geen EMS-beslislogica gewijzigd.

## Aanleiding

De eerste echte Alpha40 live capture werd correct opgeslagen, maar G5.2 stopte met `blocked` / `input_invalid` voordat de A/B-berekening begon.

De oorzaak was een fout in de G5-wrapper: Alpha40 vereiste een top-level `valid=True` op de plannerinput. De live Dummy OS Data plannerinput publiceert die marker niet. De geldigheid wordt in productie bepaald door de combinatie van status, 72 transporturen, 288 native kwartierslots, tijdsuitlijning, per-row/per-slot validity en expliciete blocker-lijsten.

## Wijziging

Alpha41 vervangt de foutieve `valid=True`-controle door een expliciete productiecontractcontrole:

- `status == ready`;
- exact 72 transportrows;
- iedere transportrow `fully_valid=True`;
- exact 288 native 15-minutenslots;
- ieder native slot `valid=True`;
- `native_expected_slot_count == 288`;
- `native_valid_slot_count == 288`;
- `planner_resolution_minutes == 15`;
- `transport_resolution_minutes == 60`;
- `time_alignment_valid == True`;
- het gedeelde 15m/72h/288 time contract valideert zonder fouten;
- geen inputblockers;
- geen runtimeblockers.

De regression fixture gebruikt nu bewust dezelfde structuur als de echte live productieinput en bevat juist geen top-level `valid`-veld.

## Niet gewijzigd

- immutable/vendored EMS `0.0.1-alpha.76` kern;
- energy need;
- planner preview;
- Plan72-logica;
- reserve-/tradebeleid;
- Plan Store;
- Scheduler;
- Prestart/Safety;
- Controller/Execution;
- forecastarchitectuur 15 minuten / 72 uur / 288 slots;
- fysieke aansturing.

## Harde shadow-only grens

G5.2 blijft uitsluitend diagnostisch:

- `physical_execution_authority=False`;
- `service_calls_performed=False`;
- `plan_store_mutated=False`;
- `cutover_permitted=False`;
- geen fysieke execution call;
- geen batterijsetpoint of operating-mode wijziging.

## Live acceptatie

Na installatie en herstart blijft hetzelfde G5-dashboard bruikbaar. Druk `G5.2 · Frozen A/B uitvoeren` eenmaal in.

Verwachte acceptatie:

- `pass` + `exact_match=True` + `difference_count=0`: G5.2 parity groen;
- `mismatch`: G5 blijft open en verschillen worden onderzocht;
- `blocked`: G5 blijft open en de weergegeven inputblockers worden onderzocht.

G6 start pas nadat G5 volledig groen is. Fysieke cutover blijft gesloten tot een aparte expliciete autorisatie.