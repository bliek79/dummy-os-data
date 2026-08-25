# Dummy OS Data

Dummy OS Data is the forecast and historical data layer for Dummy OS.

## 0.1.0-alpha.2 - Home Forecast Baseline Model

Alpha.2 keeps the permanent 15-minute history introduced in alpha.1 and adds the first rolling Home Consumption Forecast. The model is intentionally simple and transparent: it learns from actual completed quarters and separates the `normal` and `away` profiles.

### What this alpha does

- Keeps the canonical Home Power source, default `sensor.home_power`.
- Keeps persistent actual energy history per completed 15-minute slot.
- Analyses history by profile, weekday and quarter-of-day.
- Builds a native 72-hour / 288-slot forecast.
- Uses a transparent fallback order when history is still sparse:
  1. same weekday + same quarter;
  2. same quarter-of-day within the active profile;
  3. active-profile mean as low-confidence fallback;
  4. unavailable when the active profile has no valid history.
- Adds per-slot sample count, source and confidence metadata.
- Keeps `normal` and `away` history structurally separated.
- Does not yet evaluate forecast versus actual; accuracy, MAE and bias are reserved for a later alpha.

### Entities

Existing permanent entities:

- `sensor.do_home_actual_quarter`
- `sensor.do_home_history_status`
- `sensor.do_home_history_days`
- `sensor.do_home_forecast_model`
- `select.do_home_profile`

New in alpha.2:

- `sensor.do_home_forecast` - rolling 72-hour forecast total; attribute `forecast` contains 288 native 15-minute slots.
- `sensor.do_home_forecast_next_quarter` - forecast for the next 15-minute slot.
- `sensor.do_home_forecast_coverage` - percentage of forecast slots that can currently be populated from the active profile history.

> Home Assistant can append a suffix if an entity ID already exists. The integration provides permanent unique IDs and suggests the `do_` IDs above.

### State-class decisions

Forecast and completed-quarter kWh values are snapshots, not cumulative meters. They therefore use `device_class: energy` and unit `kWh`, but deliberately do **not** use `state_class: measurement`.

### Model maturity

The first forecast can already be generated after valid quarter history exists, but early results have low confidence. The model becomes more representative as each weekday/quarter/profile cell accumulates samples. Alpha.2 is a baseline model intended to create a measurable starting point for later forecast evaluation and calibration.

### Validation

After installing alpha.2:

- Existing alpha.1 history must remain available.
- `sensor.do_home_history_status` should remain `ok` when the source is available.
- `sensor.do_home_forecast_model` should report `historical_baseline` and model version `0.2`.
- `sensor.do_home_forecast` should expose a 72-hour horizon with 288 slots.
- `sensor.do_home_forecast_next_quarter` should show the next-quarter estimate when the active profile has history.
- `normal` and `away` must remain separated.
- No new `dummy_os_data` errors should appear in the Home Assistant log.

### Known alpha limitations

- No Recorder/InfluxDB backfill yet; learning uses the integration's own stored quarter history.
- No weather, season, recent-trend or presence correction yet.
- No forecast-versus-actual evaluation yet.
- A restart inside a quarter can reduce that quarter's coverage; quarters below 90% valid coverage remain invalid.
