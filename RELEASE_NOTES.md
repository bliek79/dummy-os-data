# GitHub Release

**Tag:** `0.1.0-alpha.11.10`

**Release title:** `Dummy OS Data 0.1.0-alpha.11.10 - Solar Horizon Snapshots`

## Dummy OS Data 0.1.0-alpha.11.10

Deze alpha voegt de ontbrekende meetlaag toe voor echte Solar Forecast-horizonvalidatie. Dummy OS Data bewaart voortaan immutable forecastsnapshots voor vaste vooruitkijkhorizons, zodat forecast en werkelijkheid later zonder hindsight met elkaar kunnen worden vergeleken.

### Nieuw

- Solar Forecast bewaart snapshots voor **1 uur, 6 uur, 24 uur, 48 uur en 72 uur vooruit**.
- Iedere snapshot bevat het oorspronkelijke doelkwartier, `forecast_captured_at`, provider, model, bronupdate en de voorspelde energie voor noord, zuid en totaal.
- Snapshots worden persistent opgeslagen en blijven behouden over een Home Assistant-herstart.
- Een eenmaal vastgelegde snapshot wordt niet achteraf overschreven door een nieuwere forecast voor hetzelfde doelkwartier en dezelfde horizon.
- Zodra het doelkwartier volledig is afgerond, wordt de snapshot gekoppeld aan de werkelijk gemeten kwartierenergie.
- De horizon-evaluatie gebruikt dezelfde coverage- en actual-integratielogica als de bestaande Solar-kwartierevaluatie.

### Validatie-uitvoer

De bestaande `sensor.do_solar_evaluation_last_completed_quarter` blijft de centrale vlakke exportbron. Daar komen voor beschikbare horizons aanvullende velden bij, waaronder:

- `horizon_evaluations`
- `horizon_evaluation_count`
- `horizon_hours_supported`
- `pending_horizon_snapshot_count`
- `horizon_1h_*`
- `horizon_6h_*`
- `horizon_24h_*`
- `horizon_48h_*`
- `horizon_72h_*`

Per beschikbare horizon worden onder meer forecast, actual, fout, absolute fout, bias, accuracy, coverage, capturetijd, provider en model gepubliceerd.

### Architectuurregels

- Native architectuur blijft **15 minuten / 72 uur / 288 slots**.
- De bestaande directe pre-slot kwartierevaluatie blijft intact en draait naast de nieuwe horizonlaag.
- `unknown` of `unavailable` wordt niet stilzwijgend als nul verwerkt.
- Horizonmetingen worden alleen geldig als de benodigde forecast en actualdekking daadwerkelijk beschikbaar zijn.
- De horizonlaag blijft observation/shadow en stuurt geen EMS- of batterijactie aan.

### Behouden

- Home Forecast blijft de canonieke `sensor.do_data_home_power` gebruiken.
- Weather, Degree Days en Prices blijven functioneel ongewijzigd.
- De interne gas-tariefarchitectuur uit alpha.11.9 blijft behouden.
- Elektriciteits-import en -export blijven afzonderlijk configureerbaar; de huidige gelijke contractwaarden tot en met 31 december 2026 worden niet door deze release gewijzigd.

### Technische validatie

Voor de Solar horizon-uitbreiding is vóór deze release gecontroleerd:

- Python-bronnen compileren zonder fouten.
- Volledige unit-testset slaagt.
- Gerichte regressietest controleert de vaste horizons `1, 6, 24, 48, 72`.
- Gerichte regressietest controleert persistente en immutable snapshots.
- Releaseconsistentietest controleert dat de horizonarchitectuur in deze release aanwezig blijft.

### Live validatie in Home Assistant

Na installatie en volledige herstart:

1. Controleer dat Dummy OS Data versie `0.1.0-alpha.11.10` draait.
2. Controleer dat de bestaande Solar Forecast en directe kwartierevaluatie normaal blijven werken.
3. Controleer dat `pending_horizon_snapshot_count` na kwartiergrenzen wordt opgebouwd.
4. Na minimaal 1 uur controleren of een geldige `horizon_1h_*` evaluatie verschijnt.
5. Na minimaal 6 uur controleren of `horizon_6h_*` verschijnt.
6. De 24h-, 48h- en 72h-validaties volgen zodra voldoende tijd sinds installatie is verstreken.
7. De opgebouwde resultaten daarna read-only controleren in het Google Sheets-validatiebestand.

De horizonvalidatie wordt pas als volledig gereed gemarkeerd nadat voor alle vijf horizons voldoende echte forecast-vs-actual-paren zijn opgebouwd en beoordeeld.
