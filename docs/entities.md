# Entity specification - 0.1.0-alpha.11.0

| Entity | Meaning | Unit | Device class | State class | Update |
|---|---|---|---|---|---|
| `sensor.do_home_actual_quarter` | Last completed valid 15-minute home energy | kWh | energy | none | quarter boundary |
| `sensor.do_home_history_status` | Historical collection health | text | none | none | source/profile/quarter event |
| `sensor.do_home_history_days` | Local days containing valid quarter history | d | none | none | quarter boundary |
| `sensor.do_home_forecast_model` | Active stage/model identifier | text | none | none | model/profile event |
| `select.do_home_profile` | Historical/forecast regime | normal/away | n/a | n/a | user choice |

## Reserved future evaluation entities

These are intentionally **not created yet** until their formulas are implemented and validated:

- `sensor.do_home_forecast_error`
- `sensor.do_home_forecast_mae`
- `sensor.do_home_forecast_bias`
- `sensor.do_home_forecast_accuracy_24h`
- `sensor.do_home_forecast_accuracy_7d`
- `sensor.do_home_forecast_confidence`
- `sensor.do_home_forecast_coverage`
- `sensor.do_home_forecast_health`

The percentage accuracy formula will be defined before these entities are activated, with explicit handling for quarters where actual consumption is zero or near zero.

## Solar shadow entities

| Entity | Meaning | Unit/state | Recorder |
|---|---|---|---|
| `sensor.do_solar_status` | Open-Meteo Solar source quality and freshness | text | normal |
| `sensor.do_solar_forecast_timeline` | Rolling north/south/total 72h forecast | 288 slots | `points` excluded |
| `sensor.do_solar_forecast_today_north` | Remaining forecast for local today, north | kWh | normal |
| `sensor.do_solar_forecast_today_south` | Remaining forecast for local today, south | kWh | normal |
| `sensor.do_solar_forecast_today_total` | Remaining forecast for local today, total | kWh | normal |
| `sensor.do_solar_forecast_tomorrow_north` | Forecast for local tomorrow, north | kWh | normal |
| `sensor.do_solar_forecast_tomorrow_south` | Forecast for local tomorrow, south | kWh | normal |
| `sensor.do_solar_forecast_tomorrow_total` | Forecast for local tomorrow, total | kWh | normal |
| `sensor.do_solar_forecast_next_quarter` | Total forecast for next complete quarter | kWh | normal |
| `sensor.do_solar_actual_power_north` | North AC-equivalent actual power | W | normal |
| `sensor.do_solar_actual_power_south` | South AC-equivalent actual power | W | normal |
| `sensor.do_solar_actual_power_total` | Inverter total actual AC power | W | normal |
| `sensor.do_solar_model` | Model, roof configuration and calculation metadata | text | normal |

Solar remains observation/shadow in alpha.11.0. Package 86 and Solcast remain
the reference until forecast snapshots, completed-day actuals and error metrics
have been validated.
