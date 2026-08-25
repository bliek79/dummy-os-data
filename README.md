# Dummy OS Data

Dummy OS Data is the forecast and historical data layer for Dummy OS.

## 0.1.0-alpha.3 - Entity ID and Recorder Hotfix

Alpha.3 is a focused hotfix on top of the alpha.2 Home Forecast Baseline Model. It keeps the forecast model and stored 15-minute history intact while correcting entity IDs and preventing oversized Home Assistant Recorder state attributes.

### What this alpha does

- Keeps the canonical Home Power source, default `sensor.home_power`.
- Keeps persistent actual energy history per completed 15-minute slot.
- Analyses history by profile, weekday and quarter-of-day.
- Builds a native 72-hour / 288-slot forecast internally.
- Uses a transparent fallback order when history is still sparse:
  1. same weekday + same quarter;
  2. same quarter-of-day within the active profile;
  3. active-profile mean as low-confidence fallback;
  4. unavailable when the active profile has no valid history.
- Keeps per-slot sample count, source and confidence metadata inside the forecast model.
- Keeps `normal` and `away` history structurally separated.
- Migrates known alpha.1/alpha.2 generated entity IDs to the permanent short `do_` entity IDs while preserving unique IDs.
- Keeps the full 288-slot forecast timeline internal instead of publishing it as one oversized state attribute.
- Does not yet evaluate forecast versus actual; accuracy, MAE and bias are reserved for a later alpha.

### Entities

Permanent entities:

- `sensor.do_home_actual_quarter`
- `sensor.do_home_history_status`
- `sensor.do_home_history_days`
- `sensor.do_home_forecast_model`
- `sensor.do_home_forecast`
- `sensor.do_home_forecast_next_quarter`
- `sensor.do_home_forecast_coverage`
- `select.do_home_profile`

The integration migrates only the known automatically generated alpha.1/alpha.2 IDs such as `sensor.dummy_os_data_dummy_os_home_forecast`. Entity IDs that a user has deliberately customized are not overwritten.

### Forecast exposure

`sensor.do_home_forecast` is a compact summary of the rolling 72-hour model. It exposes the forecast total and compact metadata including forecast start, resolution, horizon, slot count, populated slots, historically supported slots and coverage. The complete 288-slot timeline remains internal so Home Assistant Recorder does not have to store an attribute exceeding its state-attribute size limit.

`sensor.do_home_forecast_next_quarter` exposes the next 15-minute estimate together with its period, source, sample count and confidence. `sensor.do_home_forecast_coverage` reports historical support across the 288-slot horizon.

### State-class decisions

Forecast and completed-quarter kWh values are snapshots, not cumulative meters. They therefore use `device_class: energy` and unit `kWh`, but deliberately do **not** use `state_class: measurement`.

### Model maturity

The first forecast can already be generated after valid quarter history exists, but early results have low confidence. The model becomes more representative as each weekday/quarter/profile cell accumulates samples. Alpha.3 does not change the alpha.2 forecast mathematics; it fixes integration behavior around entity naming and Recorder-safe exposure.

### Validation

After installing alpha.3:

- Existing alpha.1/alpha.2 quarter history must remain available.
- The eight entities above should use the permanent short `do_` entity IDs.
- `sensor.do_home_history_status` should remain `ok` when the source is available.
- `sensor.do_home_forecast_model` should report `historical_baseline` and model version `0.2`.
- `sensor.do_home_forecast` should report a 72-hour horizon and 288 slots without a full `forecast` list attribute.
- `sensor.do_home_forecast_next_quarter` should show the next-quarter estimate when the active profile has history.
- `normal` and `away` must remain separated.
- No new `dummy_os_data` errors should appear in the Home Assistant log.
- Recorder should no longer warn that `sensor.do_home_forecast` state attributes exceed 16,384 bytes.

### Known alpha limitations

- No Recorder/InfluxDB backfill yet; learning uses the integration's own stored quarter history.
- No weather, season, recent-trend or presence correction yet.
- No forecast-versus-actual evaluation yet.
- The full 288-slot timeline currently remains internal; a Recorder-safe external interface will be designed separately rather than storing the entire timeline on one sensor state.
- A restart inside a quarter can reduce that quarter's coverage; quarters below 90% valid coverage remain invalid.
