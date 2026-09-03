# GitHub Release

**Tag:** `0.1.0-alpha.12.5`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.5 - Solar Horizon Runtime & Identity Hotfix`

## Dummy OS Forecast 0.1.0-alpha.12.5

Gerichte hotfix voor Solar horizonvalidatie en de afgesproken canonieke entity-ID's.

### Opgelost
- Scheduler-latency wordt vóór horizoncapture teruggebracht naar de exacte 15-minuten boundary.
- `pending_horizon_snapshot_count` wordt na capture bijgewerkt; `horizon_capture_boundary` wordt zichtbaar voor diagnose.
- De vijf verkeerd automatisch gegenereerde horizon-IDs migreren veilig naar `sensor.do_solar_evaluation_horizon_1h`, `_6h`, `_24h`, `_48h`, `_72h`.
- Zichtbare namen zijn opgeschoond naar `Dummy OS Forecast Solar Evaluation Horizon <h>h`.
- Nieuwe regressietests bewaken runtime-boundary en alle vijf identity-contracten.

### Ongewijzigd
- Native architectuur blijft 15 minuten / 72 uur / 288 slots.
- Solar-model, Energy, Weather, Prices, Degree Days en fysieke EMS-sturing zijn functioneel ongewijzigd.

### Live validatie
1. Na installatie moeten alleen de canonieke `sensor.do_solar_evaluation_horizon_*` IDs overblijven.
2. Na de eerstvolgende kwartiergrens moet `pending_horizon_snapshot_count` > 0 worden.
3. Na minimaal 1 uur moet de 1h-sensor een echte `snapshot_id` krijgen.
4. Daarna kan de Sheets-automation de eerste horizonregel exporteren.
