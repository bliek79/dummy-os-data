# GitHub Release

**Tag:** `0.1.0-alpha.5`  
**Release title:** `Dummy OS Data 0.1.0-alpha.5 - Home Forecast Model Quality`

## Dummy OS Data 0.1.0-alpha.5

Deze release verbetert de Home Forecast bovenop de bewezen alpha.4 evaluatiebasis. Het model krijgt recency weighting, een expliciete weekday/weekend-laag, forecast confidence en een model-health status.

### New
- Recency weighting voor alle historische gemiddelden met een halfwaardetijd van 28 dagen.
- Nieuwe fallback `day_type_quarter` voor weekday/weekend + hetzelfde kwartier.
- Nieuwe `sensor.do_home_forecast_confidence`.
- Nieuwe `sensor.do_home_forecast_model_health`.
- Model-health statussen `collecting`, `learning`, `usable`, `strong` en `source_unavailable`.
- Profielstatistieken tonen ook day-type coverage en de recency half-life.

### Changed
- Forecast fallbackvolgorde wordt: exact weekday+quarter -> day type+quarter -> quarter-of-day -> profile mean -> unavailable.
- Nieuwere historische kwartieren wegen geleidelijk zwaarder dan oudere kwartieren; oude historie blijft wel bruikbaar.
- `sensor.do_home_forecast_coverage` telt `day_type_quarter` als historisch ondersteunde forecastbron.
- `sensor.do_home_forecast_model` rapporteert modelversie `0.4`, `recency_weighting_active: true` en `day_type_active: true`.
- Nieuwe forecast snapshots worden als modelversie `0.4` opgeslagen zodat evaluaties herleidbaar blijven naar het model waarmee ze zijn gemaakt.
- Integratieversie wordt `0.1.0-alpha.5`.

### Unchanged
- Model-ID blijft `historical_baseline` om de bestaande modelidentiteit stabiel te houden.
- Native resolutie blijft 15 minuten.
- Forecast-horizon blijft 72 uur / 288 slots.
- `normal` en `away` blijven strikt gescheiden.
- Alpha.4 forecast-versus-actual opslag en Accuracy/MAE/Bias blijven behouden.
- Bestaande kwartierhistorie en evaluatiedata blijven behouden.
- De volledige 288-slot forecast blijft intern en Recorder-safe.
- Geen Weather/Solar-koppeling en geen EMS-uitvoering of fysieke sturing.

### Validation
- Na upgrade moeten 14 entiteiten aanwezig zijn.
- Nieuwe entiteiten moeten beschikbaar zijn als `sensor.do_home_forecast_confidence` en `sensor.do_home_forecast_model_health`.
- `sensor.do_home_forecast_model` moet `historical_baseline` tonen met modelversie `0.4`, `evaluation_active: true`, `recency_weighting_active: true` en `day_type_active: true`.
- Bestaande History Days, Evaluation Samples, Accuracy, MAE en Bias moeten behouden blijven.
- `sensor.do_home_forecast_model_health` mag met weinig historie `learning` tonen; dat is verwacht gedrag.
- Forecast Coverage mag veranderen ten opzichte van alpha.4 doordat weekday/weekend kwartieren nu als ondersteunde historische match meetellen.
- Accuracy kan na nieuwe alpha.5 evaluaties veranderen; bestaande alpha.4 evaluatieparen blijven bewaard.
- `normal` en `away` mogen niet door elkaar worden gebruikt.
- Recorder mag geen oversized-attribute waarschuwing voor `sensor.do_home_forecast` geven.
- Er mogen geen nieuwe `dummy_os_data` setup- of runtimefouten ontstaan.
