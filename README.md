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
- provide stable timeline interfaces for dashboards and future planning logic.

Dummy OS EMS is intentionally a separate layer. EMS should consume normalized data and forecasts from Dummy OS Data rather than duplicate source-specific logic.

## Core architecture

The integration uses these design principles:

- **15-minute native resolution**
- **rolling 72-hour horizon**
- **288 forecast slots**
- **stable entity IDs and unique IDs**
- **source-quality and freshness monitoring**
- **forecast evaluation before model factors are promoted into production use**
- **separate Normal and Away Home Forecast histories**
- **market prices separated from tariff composition**
- **import and export tariffs modeled independently for 2027 compatibility**
- **tariff profiles are versionable and historical tariff snapshots must remain immutable**

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

It provides completed 15-minute home-energy observations, persistent history, separate `normal` and `away` profiles, a rolling 72-hour / 288-slot forecast, recency-weighted historical baseline modelling, weekday/weekend fallback logic and forecast-versus-actual evaluation.

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

### Weather Forecast

The Weather module fetches forecast data directly from Open-Meteo and normalizes it into the Dummy OS 15-minute forecast architecture.

Current Weather behavior includes current observations, 15-minute forecast data, a rolling 72-hour timeline, seven-day daily source summary, hourly refresh with retry/backoff, source-status monitoring and preservation of the last successful dataset when a later fetch fails.

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

### Solar Forecast Shadow Layer

The native Solar module uses two independent Open-Meteo
`global_tilted_irradiance` requests and converts the radiation forecast into
15-minute PV energy for the north and south roof planes. It publishes a rolling
72-hour / 288-slot timeline for north, south and total. Radiation timestamps are
shifted to slot start because Open-Meteo radiation is a backward interval
average.

Default installation parameters:

- location: `51.828981, 4.839871`;
- north: 2.96 kWp DC, 2.45 kW AC, 37 degrees, Open-Meteo azimuth 180 degrees, factor 0.90;
- south: 1.48 kWp DC, 1.23 kW AC, 37 degrees, Open-Meteo azimuth 0 degrees, factor 0.90;
- actual total AC: `sensor.sb3_6_1av_41_857_pv_power`;
- actual north DC input: `sensor.sb3_6_1av_41_857_pv_power_a`;
- actual south DC input: `sensor.sb3_6_1av_41_857_pv_power_b`.

The north/south actual AC-equivalent split uses total inverter AC power in the
same ratio as SMA inputs A and B. The module is observation/shadow only. Solcast
and package 86 remain active as benchmarks until daily history and forecast
quality are validated.

Important Solar entities include:

- `sensor.do_solar_status`
- `sensor.do_solar_forecast_timeline`
- `sensor.do_solar_forecast_today_north`
- `sensor.do_solar_forecast_today_south`
- `sensor.do_solar_forecast_today_total`
- `sensor.do_solar_forecast_tomorrow_north`
- `sensor.do_solar_forecast_tomorrow_south`
- `sensor.do_solar_forecast_tomorrow_total`
- `sensor.do_solar_forecast_next_quarter`
- `sensor.do_solar_actual_power_north`
- `sensor.do_solar_actual_power_south`
- `sensor.do_solar_actual_power_total`
- `sensor.do_solar_model`

### Prices Shadow Layer

The first Prices alpha is observation-only. It does not perform physical control and does not replace EMS execution logic.

Electricity:

- known market prices: `https://stroomvoorspeller.nl/data/prices.json`;
- native known price source: `prices_15m[]` when `has_pt15m` is true;
- hourly `prices[]` is retained only as a fallback and is expanded to four 15-minute slots;
- forecast source: `https://stroomvoorspeller.nl/data/forecast.json`;
- hourly forecast values are expanded to four 15-minute slots while retaining `source_resolution_minutes: 60`;
- known prices always take precedence over forecast values for overlapping timestamps;
- raw Stroomvoorspeller EPEX values are normalized from EUR/MWh to EUR/kWh;
- Dummy OS calculates its own import/export all-in prices from configurable tariff components.

Gas:

- actual gas market price is read from the configured EnergyZero Home Assistant sensor;
- default source entity: `sensor.energyzero_today_gas_current_hour_price`;
- gas is treated as a daily price and can later be projected onto the common 15-minute time axis;
- Dummy OS adds the configured gas supplier component and energy tax itself.

Important Prices shadow entities:

- `sensor.do_prices_status`
- `sensor.do_prices_market_current`
- `sensor.do_prices_import_current`
- `sensor.do_prices_export_current`
- `sensor.do_prices_timeline`
- `sensor.do_prices_tariff_profile`
- `sensor.do_prices_gas_market`
- `sensor.do_prices_gas_all_in`

Tariff values are configurable through the integration options. The engine does not contain operational supplier/tax price values. The current tariff profile contains separate fields for import, export, gas, VAT and fixed costs. Import and export are separate even when their current values are temporarily equal.

Historical cost records are intended to store the tariff values that were actually used at the time. Later tariff changes must never silently reprice historical periods.

During this alpha, `sensor.do_prices_timeline` is a validation/shadow entity with a large live `points` attribute. Exclude this entity from Recorder while the formal Recorder-safe timeline entity is being finalized.

## Installation

Dummy OS Data is currently intended for Home Assistant installations using custom integrations.

Typical installation methods during alpha development are:

1. install through HACS as a custom repository; or
2. copy `custom_components/dummy_os_data` into the Home Assistant `custom_components` directory.

After installation, restart Home Assistant and add **Dummy OS Data** through **Settings > Devices & services**.

Because the project is still in alpha, users should review release notes before updating.

## Configuration

The Home Forecast source defaults to `sensor.home_power`.

The active Home Forecast profile can be selected through `select.do_home_profile`.

Prices tariff components are configured under the Dummy OS Data integration options. Price components should be entered on the basis indicated by the option name. The current alpha uses inclusive-VAT supplier/tax components and applies the configured VAT percentage to the raw EPEX market component.

Solar source entities, roof geometry, capacity limits and performance factors
are also configurable through the integration options. Solar azimuth values use
the Open-Meteo convention: 0 degrees is south and +/-180 degrees is north.

## Data and Recorder behavior

Dummy OS Data distinguishes between operational state and large timeline payloads.

Compact states and useful metadata can be recorded normally by Home Assistant. Large timeline attributes should be excluded from Recorder. Home, Weather and Solar use formal Recorder-safe entity attributes; the first Prices shadow timeline should be manually excluded during alpha validation.

Home Forecast historical observations and evaluation data are also persisted internally by the integration.

## Forecast evaluation

Forecast quality is treated as a first-class part of the architecture.

The Home Forecast currently evaluates forecast snapshots against completed actual 15-minute observations. Future Prices evaluation will compare the forecast available at decision time with the later known market price, including MAE/bias and economic impact.

## Sources and attribution

Dummy OS Data uses external projects, documentation and data providers. External sources remain traceable in the repository and should not be introduced without documenting their purpose and applicable terms.

### Home Assistant

- Project: https://www.home-assistant.io/
- Developer documentation: https://developers.home-assistant.io/
- Used for: integration framework, entity model, configuration entries, Recorder interfaces and runtime platform APIs.

Home Assistant is a separate project. Dummy OS Data is not affiliated with or endorsed by the Home Assistant project or Nabu Casa.

### Open-Meteo

- Project: https://open-meteo.com/
- Forecast API documentation: https://open-meteo.com/en/docs
- Used for: current weather, 15-minute weather forecast, daily summaries, wind, precipitation, humidity and solar-radiation inputs.

Dummy OS Data transforms and normalizes Open-Meteo source data into its own rolling 72-hour / 15-minute timeline. Open-Meteo data remains subject to the licensing, attribution and usage conditions published by Open-Meteo.

### Stroomvoorspeller.nl

- Project: https://stroomvoorspeller.nl/
- Integration documentation: https://stroomvoorspeller.nl/integraties
- Known electricity price feed: https://stroomvoorspeller.nl/data/prices.json
- Forecast feed: https://stroomvoorspeller.nl/data/forecast.json
- Used for: Dutch EPEX day-ahead market prices and multi-day electricity price forecasts.
- Licence/attribution: Stroomvoorspeller data is used under **CC BY 4.0**; attribution to Stroomvoorspeller.nl must be retained.

Dummy OS Data uses the market/forecast data as source material and calculates its own import/export tariff composition. The indicative consumer all-in calculations published by Stroomvoorspeller are not used as the authoritative Dummy OS all-in tariff.

### EnergyZero

- Project: https://www.energyzero.nl/
- Used for: current daily gas market price through the Home Assistant EnergyZero integration.

EnergyZero is used as an actual/reference source for gas. Supplier-specific tariff components remain separate inside Dummy OS Data.

## Roadmap

Planned development areas include:

- Prices validation dashboard and Google Sheets evaluation;
- immutable price/tariff history and actual import/export cost records;
- Solar forecast evaluation, calibration and Solcast benchmark history;
- heat-demand and gas forecast models;
- gas/TTF forecast evaluation;
- broader forecast-quality diagnostics;
- stable interfaces for Dummy OS EMS.

## Releases and change history

Version-specific changes are documented in GitHub Releases and `RELEASE_NOTES.md`.

Alpha and beta versions should be treated as pre-releases until a stable release is explicitly published.

## Independence and disclaimer

Dummy OS Data is an independent open-source community project.

It is not affiliated with, sponsored by or endorsed by Home Assistant, Nabu Casa, Open-Meteo, Stroomvoorspeller.nl, EnergyZero, Anker Innovations or other third-party providers mentioned in the project documentation.

The software is provided for experimentation and Home Assistant automation/data purposes. Users remain responsible for reviewing configuration, source terms, data quality and any actions performed by systems that consume Dummy OS Data.
