# Dummy OS Data

Dummy OS Data is a custom Home Assistant integration that provides the data, normalization, history and forecast layer for the wider Dummy OS energy-management architecture.

The integration is designed around one common time axis: native 15-minute resolution with a rolling 72-hour horizon of 288 forecast slots. Individual modules collect or derive data independently and expose stable Home Assistant entities for dashboards, analysis and future consumers such as Dummy OS EMS.

> **Project status:** early alpha / active development. Interfaces and behavior may still change until the project reaches a stable release.

## Purpose

Dummy OS Data separates data collection and forecasting from physical energy control.

Its role is to:

- collect canonical source data;
- normalize external and internal sources to a common format;
- retain useful historical observations;
- generate forecasts;
- evaluate forecast quality against actual measurements;
- expose source quality and freshness;
- provide Recorder-safe timeline interfaces for dashboards and future planning logic.

Dummy OS EMS is intentionally a separate layer. EMS should consume normalized data and forecasts from Dummy OS Data rather than duplicate source-specific logic.

## Core architecture

The integration uses these design principles:

- **15-minute native resolution**
- **rolling 72-hour horizon**
- **288 forecast slots**
- **stable entity IDs and unique IDs**
- **source-quality and freshness monitoring**
- **large live timelines excluded from Recorder attributes**
- **forecast evaluation before model factors are promoted into production use**
- **separate Normal and Away Home Forecast histories**

Planned and current modules are organized around the same architecture:

- Home
- Weather
- Solar
- Prices
- Heat
- Boiler
- Quality / evaluation

Not every module listed above is implemented yet.

## Current functionality

### Home Forecast

The Home module currently uses `sensor.home_power` as the canonical actual home-power source by default.

It provides:

- completed 15-minute home-energy observations;
- persistent history;
- separate `normal` and `away` profiles;
- rolling 72-hour / 288-slot Home Forecast;
- recency-weighted historical baseline modelling;
- weekday/weekend fallback logic;
- forecast confidence and model-health indicators;
- forecast-versus-actual evaluation using Accuracy, MAE and Bias;
- a Recorder-safe live forecast timeline.

Important Home entities include:

- `sensor.do_home_actual_quarter`
- `sensor.do_home_history_status`
- `sensor.do_home_history_days`
- `sensor.do_home_forecast`
- `sensor.do_home_forecast_timeline`
- `sensor.do_home_forecast_next_quarter`
- `sensor.do_home_forecast_coverage`
- `sensor.do_home_forecast_confidence`
- `sensor.do_home_forecast_model_health`
- `sensor.do_home_forecast_accuracy`
- `sensor.do_home_forecast_mae`
- `sensor.do_home_forecast_bias`
- `sensor.do_home_forecast_evaluation_samples`
- `select.do_home_profile`

Weather is not yet used as a correction factor in the Home Forecast model. New factors are intended to be evaluated before becoming part of the active model.

### Weather Forecast

The Weather module fetches forecast data directly from Open-Meteo and normalizes it into the Dummy OS 15-minute forecast architecture.

Current Weather behavior:

- current weather observations from the selected Open-Meteo location;
- 15-minute weather forecast data;
- rolling 72-hour timeline;
- exactly 288 normalized forecast points;
- seven-day daily source summary;
- hourly source refresh;
- retry/backoff on temporary source failures;
- source-status and freshness monitoring;
- preservation of the last successful dataset when a later fetch temporarily fails.

Current configured source location:

- latitude: `51.828981`
- longitude: `4.839871`
- timezone: `Europe/Berlin`
- Open-Meteo model selection: `best_match`

Important Weather entities include:

- `sensor.do_weather_temperature`
- `sensor.do_weather_apparent_temperature`
- `sensor.do_weather_relative_humidity`
- `sensor.do_weather_precipitation`
- `sensor.do_weather_cloud_cover`
- `sensor.do_weather_wind_speed`
- `sensor.do_weather_wind_direction`
- `sensor.do_weather_wind_gusts`
- `sensor.do_weather_weather_code`
- `sensor.do_weather_forecast_timeline`
- `sensor.do_weather_source_status`
- `sensor.do_weather_source_freshness`
- `sensor.do_weather_last_update`
- `sensor.do_weather_model`

The Weather timeline includes temperature, humidity, dew point, apparent temperature, precipitation, rain, weather code, wind, solar-radiation components, sunshine duration and day/night information for each 15-minute slot.

## Installation

Dummy OS Data is currently intended for Home Assistant installations using custom integrations.

Typical installation methods during alpha development are:

1. install through HACS as a custom repository; or
2. copy `custom_components/dummy_os_data` into the Home Assistant `custom_components` directory.

After installation, restart Home Assistant and add **Dummy OS Data** through **Settings > Devices & services**.

Because the project is still in alpha, users should review release notes before updating.

## Configuration

The Home Forecast source defaults to:

```text
sensor.home_power
```

The active Home Forecast profile can be selected through:

```text
select.do_home_profile
```

Weather currently uses the fixed Open-Meteo source configuration documented above. Source configuration is expected to become more user-configurable as the integration matures.

## Data and Recorder behavior

Dummy OS Data distinguishes between operational state and large timeline payloads.

Compact states and useful metadata can be recorded normally by Home Assistant. Large timeline attributes, such as the full Home and Weather 288-point forecast arrays, are intentionally excluded from Recorder attributes while remaining available live to dashboards and future consumers.

Home Forecast historical observations and evaluation data are also persisted internally by the integration.

## Forecast evaluation

Forecast quality is treated as a first-class part of the architecture.

The Home Forecast currently evaluates forecast snapshots against completed actual 15-minute observations. Available aggregate metrics include:

- Accuracy
- MAE
- Bias
- evaluation sample count
- forecast coverage
- confidence
- model health

The current accuracy metric is WAPE-like:

```text
max(0, 100 * (1 - sum(abs(forecast - actual)) / max(sum(actual), epsilon)))
```

Future forecast modules should follow the same principle: new model inputs are first observed and evaluated before being treated as proven improvements.

## Sources and attribution

Dummy OS Data uses external projects, documentation and data providers. External sources should remain traceable in the repository and should not be introduced without documenting their purpose and applicable terms.

### Home Assistant

Dummy OS Data is implemented as a custom integration for Home Assistant.

- Project: https://www.home-assistant.io/
- Developer documentation: https://developers.home-assistant.io/
- Used for: integration framework, entity model, configuration entries, Recorder interfaces and runtime platform APIs.

Home Assistant is a separate project. Dummy OS Data is not affiliated with or endorsed by the Home Assistant project or Nabu Casa.

### Open-Meteo

Open-Meteo is the current weather-data provider for the Dummy OS Weather module.

- Project: https://open-meteo.com/
- Forecast API documentation: https://open-meteo.com/en/docs
- Used for: current weather, 15-minute weather forecast, daily summaries, wind, precipitation, humidity and solar-radiation inputs.

Dummy OS Data transforms and normalizes Open-Meteo source data into its own rolling 72-hour / 15-minute timeline. Open-Meteo data remains subject to the licensing, attribution and usage conditions published by Open-Meteo. Users and redistributors of this project should review the current Open-Meteo terms for their intended use.

### Other sources and references

Additional providers or external implementation references may be added as the project grows. When a new external source becomes part of the implementation, this section and relevant module documentation should be updated with:

- source/provider name;
- official project or documentation link;
- purpose within Dummy OS Data;
- applicable licensing or attribution requirements;
- whether the source is required, optional or only used for benchmarking/reference.

## Roadmap

Planned development areas include:

- Solar Forecast;
- degree-day and heat-demand calculations;
- Weather evaluation and possible Home Forecast correction;
- price normalization;
- heat and boiler data models;
- broader forecast-quality diagnostics;
- configurable source/provider settings;
- stable interfaces for Dummy OS EMS.

Roadmap items are intentions, not guarantees of a specific release date.

## Releases and change history

This README describes the current project and should not be used as a per-version changelog.

Version-specific changes are documented in:

- GitHub Releases: https://github.com/bliek79/dummy-os-data/releases
- `RELEASE_NOTES.md` in this repository

Alpha and beta versions should be treated as pre-releases until a stable release is explicitly published.

## Independence and disclaimer

Dummy OS Data is an independent open-source community project.

It is not affiliated with, sponsored by or endorsed by Home Assistant, Nabu Casa, Open-Meteo, Anker Innovations or other third-party providers mentioned in the project documentation.

The software is provided for experimentation and Home Assistant automation/data purposes. Users remain responsible for reviewing configuration, source terms, data quality and any actions performed by systems that consume Dummy OS Data.
