# Dummy OS Data

Dummy OS Data is the forecast and historical data layer for Dummy OS.

## 0.1.0-alpha.7 - Weather Forecast Foundation

Alpha.7 adds the first Weather Forecast module to the existing Dummy OS Data integration while leaving the Home Forecast model behavior unchanged.

### Weather source

Weather data is provided by [Open-Meteo](https://open-meteo.com/). The integration uses the public Forecast API endpoint at `api.open-meteo.com/v1/forecast`.

Configured source location:

- latitude: `51.828981`
- longitude: `4.839871`
- timezone: `Europe/Berlin`
- model selection: Open-Meteo `best_match`

These coordinates intentionally match the configured Solcast site coordinates so later weather/solar comparisons use the same geographical reference.

### Refresh and source quality

- Initial fetch during integration setup.
- Scheduled refresh each hour at `:00:05`.
- Retry/backoff on a failed refresh: immediate, +5 seconds, +15 seconds.
- The last successful dataset remains available if a later refresh fails.
- Source status and freshness are exposed separately.
- Fresh: under 90 minutes old.
- Stale: 90 to under 180 minutes old, or a failed refresh while usable data remains.
- Expired: 180 minutes or older.

### Rolling Weather Forecast timeline

The source request uses Open-Meteo `forecast_minutely_15` rather than a calendar-day-only range. Dummy OS normalizes the returned data into its native forecast architecture:

- 15-minute resolution;
- rolling horizon;
- 72 hours;
- exactly 288 usable slots;
- compact live timeline for dashboards and future Home/Solar/Heat/Boiler consumers;
- timeline points are excluded from Recorder attributes, matching the Recorder-safe Home Forecast pattern.

Each timeline point contains:

`[unix_ms, temperature_2m, relative_humidity_2m, dew_point_2m, apparent_temperature, precipitation, rain, weather_code, wind_speed_10m, wind_direction_10m, wind_gusts_10m, shortwave_radiation, sunshine_duration, diffuse_radiation, direct_normal_irradiance, is_day, direct_radiation]`

Solar-radiation values are the normal interval values, not the `instant` variants. GTI is deliberately not part of this first Weather module.

### Current Weather entities

- `sensor.do_weather_temperature`
- `sensor.do_weather_apparent_temperature`
- `sensor.do_weather_relative_humidity`
- `sensor.do_weather_precipitation`
- `sensor.do_weather_cloud_cover`
- `sensor.do_weather_wind_speed`
- `sensor.do_weather_wind_direction`
- `sensor.do_weather_wind_gusts`
- `sensor.do_weather_weather_code`

### Forecast/source entities

- `sensor.do_weather_forecast_timeline`
- `sensor.do_weather_source_status`
- `sensor.do_weather_source_freshness`
- `sensor.do_weather_last_update`
- `sensor.do_weather_model`

### Daily source data

The live timeline sensor also keeps the requested seven-day daily Open-Meteo summary available as an unrecorded attribute, including min/max temperature, sunrise/sunset, daylight/sunshine duration, precipitation totals/hours, maximum wind/gusts and shortwave-radiation sum.

### Home Forecast regression boundary

Alpha.7 does not change Home Forecast model calculations. The existing Home Forecast remains:

- `sensor.home_power` as canonical actual source;
- native 15-minute resolution;
- rolling 72-hour / 288-slot horizon;
- separate `normal` and `away` profiles;
- recency-weighted historical baseline model version `0.4`;
- forecast-versus-actual evaluation with Accuracy, MAE and Bias;
- Recorder-safe live Home Forecast timeline.

Weather is not yet used as an input factor for Home Forecast. It is first exposed independently so its runtime quality can be validated before model coupling.

### Next analysis opportunities

Once Weather has proven stable, the same normalized timeline can be evaluated for:

- Solar Forecast;
- Home Forecast temperature/weather correction;
- heat-demand modelling;
- boiler modelling;
- degree-day calculations based on Dummy OS weather data.

No degree-day calculation is introduced in alpha.7; this alpha establishes the source data required to assess that next.
