# Dummy OS Data

Dummy OS Data is the forecast and historical data layer for Dummy OS.

## 0.1.0-alpha.5 - Home Forecast Model Quality

Alpha.5 builds on the working alpha.4 evaluation foundation and improves the Home Forecast itself while keeping the model transparent and fully history-driven.

### What this alpha does

- Keeps `sensor.home_power` as the canonical Home Power source by default.
- Keeps persistent actual energy history per completed 15-minute slot.
- Keeps the native 72-hour / 288-slot Home Forecast.
- Keeps `normal` and `away` structurally separated.
- Keeps persistent forecast-versus-actual evaluation from alpha.4.
- Adds recency weighting with a 28-day half-life so newer observations gradually count more strongly than old ones.
- Adds an explicit weekday/weekend (`day_type`) fallback between exact weekday matching and generic quarter-of-day matching.
- Keeps exact weekday + quarter as the strongest historical match.
- Adds forecast confidence as a permanent sensor.
- Adds model health as a permanent sensor.
- Keeps the full 288-slot forecast timeline internal and Recorder-safe.

### Forecast fallback order

1. Same weekday + same quarter (`weekday_quarter`).
2. Same day type (weekday/weekend) + same quarter (`day_type_quarter`).
3. Same quarter-of-day within the active profile (`quarter_of_day`).
4. Recency-weighted active-profile mean (`profile_mean`).
5. Unavailable when no valid history exists for the active profile.

All historical means use exponential recency weighting with a 28-day half-life. This does not discard older history; its influence decreases gradually as newer valid observations accumulate.

### Permanent entities

- `sensor.do_home_actual_quarter`
- `sensor.do_home_history_status`
- `sensor.do_home_history_days`
- `sensor.do_home_forecast_model`
- `sensor.do_home_forecast`
- `sensor.do_home_forecast_next_quarter`
- `sensor.do_home_forecast_coverage`
- `sensor.do_home_forecast_confidence`
- `sensor.do_home_forecast_model_health`
- `sensor.do_home_forecast_accuracy`
- `sensor.do_home_forecast_mae`
- `sensor.do_home_forecast_bias`
- `sensor.do_home_forecast_evaluation_samples`
- `select.do_home_profile`

### Confidence and model health

`sensor.do_home_forecast_confidence` reports the average confidence of the currently generated 288 forecast slots. Confidence remains intentionally conservative while the history is sparse and rises as stronger historical matches gain samples.

`sensor.do_home_forecast_model_health` provides a compact maturity state:

- `collecting`: no valid quarter history yet;
- `learning`: model works but historical/evaluation support is still limited;
- `usable`: at least 40% supported 72-hour coverage, 32 evaluation samples and 45% average confidence;
- `strong`: at least 80% supported coverage, 96 evaluation samples and 65% average confidence;
- `source_unavailable`: canonical Home Power source is currently unavailable.

These thresholds describe model maturity, not a guarantee of forecast accuracy. Accuracy, MAE and bias remain the evidence layer for judging actual forecast performance.

### Evaluation method

Accuracy remains the aggregate WAPE-like alpha.4 metric:

`max(0, 100 * (1 - sum(abs(forecast - actual)) / max(sum(actual), epsilon)))`

MAE is mean absolute error per evaluated quarter. Bias is signed mean `forecast - actual`. Evaluations remain profile-separated and only use valid actual quarters that had a forecast frozen beforehand.

### State-class decisions

Forecast, completed-quarter and error kWh values are snapshots/metrics rather than cumulative meters. They deliberately do not use an inappropriate cumulative/measurement state class.

### Known alpha limitations

- No Recorder/InfluxDB backfill yet; learning and evaluation use the integration's persistent storage.
- Weather, season, recent short-term trend and presence correction are not yet part of this Home model.
- The complete 288-slot timeline remains internal until a Recorder-safe dashboard/EMS consumer interface is added.
- A restart inside a quarter can make that actual quarter invalid because coverage drops below the 90% threshold.
