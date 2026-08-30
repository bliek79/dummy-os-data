# GitHub Release

**Tag:** `0.1.0-alpha.11.3`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.3 - Solar Evaluation & Reliability`

## Dummy OS Data 0.1.0-alpha.11.3

Uitbreiding en technische controle van de native Solar Forecast-laag uit
alpha.11.2. Deze release voegt een echte kwartierevaluatie toe, maakt de
72-uurs tijdlijn robuuster en corrigeert randgevallen rond kwartiergrenzen,
bronwaarden en nachtproductie. De module blijft uitsluitend
observation/shadow; Solcast en package 86 blijven actief als onafhankelijke
referentie.

### Nieuw

- Nieuwe entiteit
  `sensor.do_solar_evaluation_last_completed_quarter`.
- Per afgerond kwartier één onveranderlijk, vlak en Google Sheets-geschikt
  evaluatierecord.
- Forecastsnapshot wordt op de kwartiergrens vastgelegd voordat werkelijke
  productie voor dat kwartier bekend is.
- Werkelijke kwartierenergie voor Noord, Zuid en totaal via zero-order-hold
  integratie van het SMA AC-vermogen.
- Noord/Zuid-verdeling blijft gebaseerd op de verhouding tussen SMA
  DC-ingangen A en B.
- Forecast, werkelijk, signed error, absolute error, bias, accuracy en
  meetdekking per dakvlak en totaal.
- Minimaal 90% geldige tijddekking per component; ontbrekende waarden worden
  niet als nul verwerkt.
- Persistente opslag van het actieve kwartier en het laatst afgeronde
  evaluatierecord.
- Google Sheets-voorbeeldautomatisering voor ieder nieuw afgerond kwartier.
- Regressietest die Solar-entiteiten uit voorbeeld-YAML controleert tegen de
  werkelijk geregistreerde Solar-sensoren.

### Opgelost en verbeterd

- Open-Meteo Solar-tijdstempels worden intern in UTC verwerkt.
- Noord en Zuid gebruiken exact dezelfde tijdsgrens bij normalisatie.
- De 72-uurs tijdlijn houdt vier extra bronpunten vast en blijft tussen de
  uurlijkse updates 288 toekomstige kwartierslots leveren.
- Ongeldige, ontbrekende en niet-eindige stralingswaarden worden afgekeurd in
  plaats van stilzwijgend naar nul omgezet.
- Alleen werkelijke vermogensbronnen in `W` of `kW` worden geaccepteerd.
- Een geplande kwartiercallback gebruikt de exacte logische kwartiergrens,
  zodat event-loopvertraging geen geldige forecastsnapshot afkeurt.
- Bij `0 W` totaalvermogen zijn Noord en Zuid eveneens `0 W`, ook wanneer de
  DC-ingangssensoren 's nachts slapen of tijdelijk geen waarde leveren.
- Solar-opties valideren nu coördinaten, dakhelling, Open-Meteo-azimut,
  capaciteiten, AC-limieten en prestatiefactoren.
- `forecast_end` is expliciet het exclusieve einde van het laatste tijdslot;
  `last_slot_start` is afzonderlijk beschikbaar.
- Bronstatus bevat aanvullende buffer-, actual- en evaluatiediagnostiek.

### Validatie

- 21 unit- en releaseconsistentietests slagen.
- Python-bronnen compileren en zijn met AST gevalideerd.
- Manifest, vertalingen en JSON-bestanden zijn consistent.
- De generieke en installatiegebonden Google Sheets-automatisering zijn als
  YAML gevalideerd.
- `sensor.do_solar_forecast_timeline` blijft exact 288 punten publiceren.
- Het `points`-attribuut blijft Recorder-excluded.
- Noord plus Zuid blijft binnen afronding gelijk aan totaal.
- De vaste `sensor.do_solar_*`-entity-ID's blijven behouden.

### Ongewijzigd

- Het fysieke forecastmodel blijft
  `open_meteo_gti_physical_v0.1`.
- Standaard dakcapaciteiten, AC-limieten, hellingen, azimuts en
  prestatiefactoren blijven ongewijzigd.
- Package `86_solcast_evaluation` en Solcast blijven actief als benchmark.
- Package 07 en de zonneboilerlogica blijven ongewijzigd.
- Home Forecast, Weather, Prices, Degree Days en gas blijven ongewijzigd.
- Geen automatische forecastkalibratie, bronselectie, EMS-sturing of
  planner-invloed.
