# Dummy OS Data

Dummy OS Data is the forecast and historical data layer for Dummy OS.

## 0.1.0-alpha.4 - Home Forecast Evaluation Foundation

Alpha.4 keeps the existing 15-minute Home Forecast and adds the first persistent forecast-versus-actual evaluation layer. Forecast mathematics remain deliberately transparent while evaluation begins collecting evidence for later model improvements.

### What this alpha does

- Keeps the canonical Home Power source, default `sensor.home_power`.
- Keeps persistent actual energy history per completed 15-minute slot.
- Builds a native 72-hour / 288-slot Home Forecast internally.
- Keeps `normal` and `away` structurally separated for both learning and evaluation.
- Freezes a forecast snapshot before each evaluated quarter begins.
- Compares the frozen forecast with the valid completed actual quarter.
- Persists compact evaluation records for up to the same 400-day horizon as Home history.
- Calculates aggregate active-profile accuracy, MAE, bias and evaluation sample count.
- Keeps the full 288-slot forecast timeline internal instead of publishing it as one oversized Recorder attribute.

### Permanent entities

- `sensor.do_home_actual_quarter`
- `sensor.do_home_history_status`
- `sensor.do_home_history_days`
- `sensor.do_home_forecast_model`
- `sensor.do_home_forecast`
- `sensor.do_home_forecast_next_quarter`
- `sensor.do_home_forecast_coverage`
- `sensor.do_home_forecast_accuracy`
- `sensor.do_home_forecast_mae`
- `sensor.do_home_forecast_bias`
- `sensor.do_home_forecast_evaluation_samples`
- `select.do_home_profile`

The integration migrates known automatically generated Dummy OS Data entity IDs to the permanent short `do_` IDs while preserving unique IDs. Deliberately user-customized entity IDs are not overwritten.

### Evaluation method

Accuracy is calculated over all valid evaluation pairs for the active profile with an aggregate WAPE-like metric:

`max(0, 100 * (1 - sum(abs(forecast - actual)) / max(sum(actual), epsilon)))`

Using an aggregate denominator avoids unstable percentages for individual 15-minute quarters where actual energy is near zero. MAE is the mean absolute error per evaluated quarter. Bias is the signed mean `forecast - actual`, so a positive bias means systematic overprediction and a negative bias means underprediction.

A quarter is evaluated only when a forecast was frozen before that quarter and the completed actual quarter passes the existing data-quality rules. Mixed-profile or insufficient-coverage quarters are excluded.

### Forecast exposure

`sensor.do_home_forecast` remains a compact summary with forecast total, forecast start, resolution, horizon, slot count, populated slots, historically supported slots and coverage. The complete 288-slot timeline stays internal to avoid Recorder attribute-size problems.

`sensor.do_home_forecast_next_quarter` exposes the next 15-minute estimate and its source/sample/confidence metadata. Evaluation sensors expose compact aggregate quality metrics suitable for dashboards and long-term trend monitoring.

### State-class decisions

Forecast, completed-quarter and error kWh values are snapshots/metrics rather than cumulative meters. They use appropriate units/device classes but deliberately do **not** use `state_class: measurement` when that would conflict with Home Assistant energy semantics.

### Validation

After installing alpha.4:

- Existing alpha.1-alpha.3 history and profile selection must remain available.
- All 12 entities above should use the permanent short `do_` IDs.
- `sensor.do_home_history_status` should remain `ok` with an available source.
- `sensor.do_home_forecast_model` should report `historical_baseline`, model version `0.3` and `evaluation_active: true`.
- Accuracy, MAE and Bias may initially be unknown while zero evaluation samples exist.
- After the first fully pre-forecast and valid completed quarter, Evaluation Samples should increase and Accuracy/MAE/Bias should become available.
- Recorder should not warn that Home Forecast attributes exceed 16,384 bytes.
- No new `dummy_os_data` setup/runtime errors should appear.

### Known alpha limitations

- No Recorder/InfluxDB backfill yet; learning/evaluation use the integration's own persistent storage.
- No weather, season, recent-trend or presence correction yet.
- The full 288-slot timeline remains internal; a Recorder-safe consumer interface will be designed separately for dashboard/EMS use.
- A restart inside a quarter can reduce that quarter's actual coverage; incomplete quarters remain invalid and are not evaluated.
