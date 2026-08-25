# Entity specification - 0.1.0-alpha.1

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
