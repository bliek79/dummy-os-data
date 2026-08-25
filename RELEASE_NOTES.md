# GitHub Release

**Tag:** `0.1.0-alpha.6`  
**Release title:** `Dummy OS Data 0.1.0-alpha.6 - Home Forecast Dashboard Interface`

## Dummy OS Data 0.1.0-alpha.6

Deze release maakt de Home Forecast geschikt voor een volwaardig dashboard zonder de Recorder opnieuw met een te groot 288-slot attribuut te belasten.

### New
- Nieuwe `sensor.do_home_forecast_timeline` voor dashboard- en grafiekgebruik.
- De timeline levert de volledige actieve 72-uurs / 288-slot forecast als compacte `points`-reeks in formaat `[unix_ms, kwh]`.
- Het `points`-attribuut is expliciet uitgesloten van Recorder-opslag via Home Assistant `unrecorded_attributes`.
- `sensor.do_home_forecast` verwijst met `timeline_entity` naar de nieuwe timeline-entiteit.
- `sensor.do_home_forecast_model` rapporteert `dashboard_timeline_active: true`.

### Changed
- Integratieversie wordt `0.1.0-alpha.6`.
- De oude aanduiding `timeline_storage: internal_only` vervalt omdat de tijdlijn nu live beschikbaar is via een aparte Recorder-veilige entity.
- De forecastberekening zelf blijft modelversie `0.4`; alpha.6 verandert de interface, niet de forecastwiskunde.

### Unchanged
- Native resolutie blijft 15 minuten.
- Forecast-horizon blijft 72 uur / 288 slots.
- Recency weighting met 28 dagen half-life blijft actief.
- Weekday/weekend day-type fallback blijft actief.
- `normal` en `away` blijven strikt gescheiden.
- Accuracy, MAE, Bias, Evaluation Samples, Confidence en Model Health blijven behouden.
- Bestaande historie en evaluatiedata blijven behouden.
- Geen Weather/Solar-koppeling en geen EMS-uitvoering of fysieke sturing.

### Validation
- Na upgrade moeten 15 entiteiten aanwezig zijn.
- `sensor.do_home_forecast_timeline` moet bestaan en state `288` tonen wanneer alle forecastslots gevuld zijn.
- `sensor.do_home_forecast_timeline` moet een `points` attribuut bevatten met maximaal 288 `[unix_ms, kwh]` punten.
- `point_format` moet `[unix_ms, kwh]` zijn en `recorder_points` moet `excluded` tonen.
- `sensor.do_home_forecast_model` moet `dashboard_timeline_active: true` tonen.
- Bestaande History Days, Evaluation Samples, Accuracy, MAE, Bias, Confidence en Model Health moeten behouden blijven.
- Recorder mag geen oversized-attribute waarschuwing voor de Home Forecast of timeline geven.
- Er mogen geen nieuwe `dummy_os_data` setup- of runtimefouten ontstaan.
