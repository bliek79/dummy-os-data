# GitHub Release

**Tag:** `0.1.0-alpha.12.17`  
**Release title:** Dummy OS Forecast 0.1.0-alpha.12.17 - Energy Recency Weighting Observer

## Dummy OS Forecast 0.1.0-alpha.12.17

Stap 8A voegt de observer-only Energy Recency Weighting-laag toe. De bestaande productieforecast blijft exact de huidige 28-daagse recency-half-life gebruiken.

### Nieuw
- `sensor.do_energy_recency_weighting` met schema `8a.1` en algoritme `recency_weighting_observer_v1`.
- Forward-only replay van 14, 21, 28 en 42 dagen op exact dezelfde fallback- en samplebasis.
- Control-reproductiegate tegen de opgeslagen 28-daagse productieforecast.
- MAE, RMSE, bias, WMAPE, median, p90, paired win-rate, ESS, segment- en early/late-diagnostiek.
- Conservatieve promotiediagnostiek; `promotion_ready` kan observer-only waar worden, maar forecastinvloed blijft uit.

### Identity-gate
- Canonical `entity_id`: `sensor.do_energy_recency_weighting`.
- `unique_id` en `suggested_object_id`: `do_energy_recency_weighting`.
- Runtime/friendly name: `DO Energy Recency Weighting`.
- De mogelijke automatisch gegenereerde `sensor.dummy_os_forecast_do_energy_recency_weighting` is expliciet als veilige migratiealias vastgelegd.
- Geen `_2`-variant of alias-sensor.

### Ongewijzigd
- Productie-half-life blijft exact 28 dagen.
- `forecast.py` productiepad en confidenceformule blijven ongewijzigd.
- Peak Learning, Time Windows, fallback-hiërarchie, Model Health en plannerfeed blijven ongewijzigd.
- Native architectuur blijft exact 15 minuten / 72 uur / 288 slots.

### Validatie
- Volledige unit-/regressietestset.
- Compile en manifestcontrole.
- Identity/friendly-name release-gate.
- Na installatie: live Home Assistant-validatie van status, control reproduction en observer-only flags.
