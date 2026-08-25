# Dummy OS Data

Dummy OS Data is the forecast and historical data layer for Dummy OS.

## 0.1.0-alpha.1 - Home Forecast Historical Foundation

This first alpha deliberately does **not** create a consumption forecast yet. It creates the permanent 15-minute historical foundation that later forecast models, evaluation metrics and calibration will use.

### What this alpha does

- Config flow for the canonical Home Power source (default `sensor.home_power`).
- Integrates power into actual energy per completed 15-minute slot.
- Persists quarter-hour records in Home Assistant `.storage`.
- Stores the active profile (`normal` / `away`) with every completed quarter.
- Exposes a small permanent entity set using the `do_` technical prefix.
- Keeps forecast and evaluation inactive until their own validated alpha.

### Entities

- `sensor.do_home_actual_quarter`
- `sensor.do_home_history_status`
- `sensor.do_home_history_days`
- `sensor.do_home_forecast_model`
- `select.do_home_profile`

> Home Assistant can append a suffix if an entity ID already exists. The integration provides permanent unique IDs and suggests the `do_` IDs above.

### State-class decisions

- `sensor.do_home_actual_quarter`: `device_class: energy`, unit `kWh`, **no state_class**. It is a completed-quarter snapshot, not a cumulative energy meter.
- History/status/model sensors: no energy device class and no energy state class.
- This follows the Dummy OS Home Assistant validation rule: forecast/snapshot/reference/evaluation kWh values are not automatically `measurement`.

### Installation for first test

1. Copy `custom_components/dummy_os_data` to `/config/custom_components/dummy_os_data`.
2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration**.
4. Search for **Dummy OS Data**.
5. Select `sensor.home_power` (or the canonical power sensor if different).
6. Keep `select.do_home_profile` on `normal` unless the home is actually in Away mode.
7. Wait until a complete quarter boundary has passed.

### First validation

- `sensor.do_home_history_status` should become `ok` after a valid completed quarter.
- `sensor.do_home_actual_quarter` should show kWh for the last completed quarter.
- Attribute `coverage` should normally be at least `0.9`.
- `sensor.do_home_history_days` should become `1` after the first valid quarter of a local calendar day.
- Changing `select.do_home_profile` must persist after reload/restart.
- No new Home Assistant log errors should appear for `dummy_os_data`.

### Known alpha limitation

This alpha integrates from installation/runtime onward. A Home Assistant restart inside a quarter can reduce that quarter's coverage; quarters below 90% valid coverage are stored as invalid and do not become `sensor.do_home_actual_quarter` values.
