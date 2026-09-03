# Dummy OS Forecast

Dummy OS Forecast is a custom Home Assistant integration that provides the source-normalization, history, forecast and validation layer for the wider Dummy OS energy-management architecture.

The integration is designed around one common time axis: native **15-minute resolution**, a rolling **72-hour horizon** and **288 forecast slots**. Individual modules collect or derive data independently and expose stable Home Assistant interfaces for dashboards, validation and future consumers such as Dummy OS EMS.

> **Project status:** early alpha / active development. Interfaces and behavior may still change until the project reaches a stable release.

## Purpose

Dummy OS Forecast separates data collection and forecasting from physical energy control.

Its role is to:

- normalize canonical source data;
- retain useful historical observations;
- generate Energy, Weather and Solar forecast data;
- provide current and forecast price data;
- collect and validate Degree Days / heat-history data;
- evaluate forecast quality against actual measurements;
- expose source quality and freshness;
- provide stable timeline interfaces for dashboards and future planning logic.

Dummy OS EMS is intentionally a separate layer. EMS should consume normalized data and forecasts from Dummy OS Forecast rather than duplicate source-specific logic.

## Core architecture

The fixed architecture is:

- **15-minute native resolution**
- **rolling 72-hour horizon**
- **288 forecast slots**
- stable entity IDs and unique IDs
- source-quality and freshness monitoring
- forecast evaluation before model factors are promoted into production use
- separate `normal` and `away` Energy Forecast histories
- market prices separated from tariff composition
- import and export tariffs modeled independently for 2027 compatibility
- tariff profiles are versionable and historical tariff snapshots must remain immutable

The public entity namespaces are organized by function:

- `do_source_*`
- `do_energy_*`
- `do_weather_*`
- `do_solar_*`
- `do_prices_*`
- `do_degree_days_*`

The visible integration name is **Dummy OS Forecast**. The technical Home Assistant domain remains `dummy_os_data`.

## Current functionality

### Source layer

Dummy OS Forecast builds one canonical local energy-flow layer from four configurable underlying power sources. Grid power uses one bidirectional source: positive means import and negative means export. Missing, `unknown` or `unavailable` source values are not silently converted to zero.

Registered Source entities:

- `sensor.do_source_grid_net_power`
- `sensor.do_source_grid_import_power`
- `sensor.do_source_grid_export_power`
- `sensor.do_source_solar_power`
- `sensor.do_source_battery_charge_power`
- `sensor.do_source_battery_discharge_power`
- `sensor.do_source_home_power`

`do_source_home_power` uses the fixed balance:

`solar + grid_import + battery_discharge - grid_export - battery_charge`

### Energy Forecast

Energy Forecast consumes `sensor.do_source_home_power` as its canonical actual-power source.

It provides completed 15-minute energy observations, persistent history, separate `normal` and `away` profiles, a rolling 72-hour / 288-slot forecast, recency-weighted historical baseline modelling, weekday/weekend fallback logic and forecast-versus-actual evaluation.

Registered Energy entities:

- `sensor.do_energy_actual_quarter`
- `sensor.do_energy_history_status`
- `sensor.do_energy_history_days`
- `sensor.do_energy_forecast_model`
- `sensor.do_energy_forecast`
- `sensor.do_energy_forecast_timeline`
- `sensor.do_energy_forecast_next_quarter`
- `sensor.do_energy_forecast_coverage`
- `sensor.do_energy_forecast_confidence`
- `sensor.do_energy_forecast_model_health`
- `sensor.do_energy_forecast_accuracy`
- `sensor.do_energy_forecast_mae`
- `sensor.do_energy_forecast_bias`
- `sensor.do_energy_forecast_evaluation_samples`
- `select.do_energy_profile`

### Weather Forecast

The Weather module fetches forecast data directly from Open-Meteo and normalizes it into the Dummy OS 15-minute forecast architecture.

Current behavior includes current observations, 15-minute forecast data, a rolling 72-hour timeline, seven-day daily source summary, hourly refresh with retry/backoff, source-status monitoring and preservation of the last successful dataset when a later fetch fails.

Current configured source location:

- latitude: `51.828981`
- longitude: `4.839871`
- timezone: `Europe/Berlin`
- Open-Meteo model selection: `best_match`

Registered Weather entities:

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

### Solar Forecast

The native Solar module uses two independent Open-Meteo `global_tilted_irradiance` requests and converts radiation forecast data into 15-minute PV energy for the north and south roof planes. It publishes a rolling 72-hour / 288-slot timeline for north, south and total. Radiation timestamps are shifted to slot start because Open-Meteo radiation is a backward interval average.

Default installation parameters:

- location: `51.828981, 4.839871`
- north: 2.96 kWp DC, 2.45 kW AC, 37 degrees, Open-Meteo azimuth 180 degrees, factor 0.90
- south: 1.48 kWp DC, 1.23 kW AC, 37 degrees, Open-Meteo azimuth 0 degrees, factor 0.90
- actual total AC: `sensor.sb3_6_1av_41_857_pv_power`
- actual north DC input: `sensor.sb3_6_1av_41_857_pv_power_a`
- actual south DC input: `sensor.sb3_6_1av_41_857_pv_power_b`

The north/south actual AC-equivalent split uses total inverter AC power in the same ratio as SMA inputs A and B. For each full quarter, Dummy OS freezes the forecast before actual production is known and integrates SMA power with a zero-order hold. A component is valid only with at least 90% time coverage; missing source data is not treated as zero. The module remains observation/shadow only.

Registered Solar entities:

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
- `sensor.do_solar_evaluation_last_completed_quarter`
- `sensor.do_solar_evaluation_horizon_1h`
- `sensor.do_solar_evaluation_horizon_6h`
- `sensor.do_solar_evaluation_horizon_24h`
- `sensor.do_solar_evaluation_horizon_48h`
- `sensor.do_solar_evaluation_horizon_72h`
- `sensor.do_solar_model`

### Prices

The Prices layer is observation-only. It does not perform physical control and does not replace EMS execution logic.

Electricity:

- known market prices: `https://stroomvoorspeller.nl/data/prices.json`
- native known source: `prices_15m[]` when `has_pt15m` is true
- hourly `prices[]` remains a fallback and is expanded to four 15-minute slots
- forecast source: `https://stroomvoorspeller.nl/data/forecast.json`
- hourly forecast values are expanded to four 15-minute slots while retaining their source resolution
- known prices take precedence over forecast values for overlapping timestamps
- raw EPEX values are normalized from EUR/MWh to EUR/kWh
- Dummy OS calculates its own import/export all-in prices from configurable tariff components

Gas:

- current gas market price is read from the configured EnergyZero Home Assistant sensor
- default source entity: `sensor.energyzero_today_gas_current_hour_price`
- gas is treated as a daily price and can later be projected onto the common 15-minute time axis
- Dummy OS adds the configured gas supplier component and energy tax internally

Current Prices runtime states:

- `sensor.do_prices_status`
- `sensor.do_prices_market_current`
- `sensor.do_prices_import_current`
- `sensor.do_prices_export_current`
- `sensor.do_prices_timeline`
- `sensor.do_prices_tariff_profile`
- `sensor.do_prices_gas_market`
- `sensor.do_prices_gas_all_in`

Prices remains a runtime-state layer in alpha.12 and is not included in the registered entity count below.

### Degree Days

Degree Days collects hourly Open-Meteo actual temperatures, freezes one completed record per local day and retains up to 400 days of internal history. A day requires at least 18 valid hourly samples. The base temperature is 18.0 °C. Seasonal weighting remains aligned with the existing legacy weighting: 1.1 for November-February, 1.0 for March/October and 0.8 for the other months.

From alpha.12 the layer is published through normal registered Home Assistant `SensorEntity` entities:

- `sensor.do_degree_days_status`
- `sensor.do_degree_days_history_days`
- `sensor.do_degree_days_temperature_daily`
- `sensor.do_degree_days_daily`
- `sensor.do_degree_days_weighted_daily`
- `sensor.do_degree_days_reference_daily`
- `sensor.do_degree_days_weighted_reference_daily`
- `sensor.do_degree_days_difference`
- `sensor.do_degree_days_weighted_difference`
- `sensor.do_degree_days_last_day`

## Registered entity inventory in alpha.12

After a successful migration, Dummy OS Forecast is intended to expose **65 registered entities**:

- Source: 7 sensors
- Energy: 14 sensors + 1 select
- Weather: 14 sensors
- Solar: 19 sensors
- Degree Days: 10 sensors

Total: **64 sensors + 1 select**.

Prices runtime states are separate from this entity-registry count.

## Installation

Dummy OS Forecast is currently intended for Home Assistant installations using custom integrations.

Typical installation methods during alpha development are:

1. install through HACS as a custom repository; or
2. copy `custom_components/dummy_os_data` into the Home Assistant `custom_components` directory.

After installation, restart Home Assistant and add **Dummy OS Forecast** through **Settings > Devices & services**.

Because the project is still in alpha, review the release notes before updating.

## Configuration

The Source layer is built from four configurable underlying power sources. Energy Forecast then consumes `sensor.do_source_home_power` internally.

The active Energy Forecast profile can be selected through `select.do_energy_profile`.

Prices tariff components are configured under the Dummy OS Forecast integration options. Price components should be entered on the basis indicated by the option name. The current alpha uses inclusive-VAT supplier/tax components and applies the configured VAT percentage to the raw EPEX market component.

Solar source entities, roof geometry, capacity limits and performance factors are also configurable through the integration options. Solar azimuth values use the Open-Meteo convention: 0 degrees is south and +/-180 degrees is north.

## Data and Recorder behavior

Dummy OS Forecast distinguishes between operational state and large timeline payloads.

Compact states and useful metadata can be recorded normally by Home Assistant. Large timeline attributes should be excluded from Recorder. Energy, Weather and Solar use formal Recorder-safe entity attributes; the Prices timeline remains a validation/shadow state with a large live `points` attribute and should be excluded while its formal Recorder-safe interface is not yet finalized.

Energy Forecast historical observations and evaluation data are persisted internally by the integration. Degree Days also keeps its own internal stored history.

## Forecast evaluation

Forecast quality is treated as a first-class part of the architecture.

Energy Forecast evaluates forecast snapshots against completed actual 15-minute observations. Solar evaluates completed quarter forecasts and also supports persisted 1h, 6h, 24h, 48h and 72h horizon snapshots/evaluations. Future Prices evaluation can compare the forecast available at decision time with the later known market price.

## Sources and attribution

Dummy OS Forecast uses external projects, documentation and data providers. External sources remain traceable in the repository and should not be introduced without documenting their purpose and applicable terms.

### Home Assistant

- Project: https://www.home-assistant.io/
- Developer documentation: https://developers.home-assistant.io/
- Used for: integration framework, entity model, configuration entries, Recorder interfaces and runtime platform APIs.

Home Assistant is a separate project. Dummy OS Forecast is not affiliated with or endorsed by the Home Assistant project or Nabu Casa.

### Open-Meteo

- Project: https://open-meteo.com/
- Forecast API documentation: https://open-meteo.com/en/docs
- Used for: current weather, 15-minute weather forecast, daily summaries, wind, precipitation, humidity and solar-radiation inputs.

Dummy OS Forecast transforms and normalizes Open-Meteo source data into its own rolling 72-hour / 15-minute architecture. Open-Meteo data remains subject to the licensing, attribution and usage conditions published by Open-Meteo.

### Stroomvoorspeller.nl

- Project: https://stroomvoorspeller.nl/
- Integration documentation: https://stroomvoorspeller.nl/integraties
- Known electricity price feed: https://stroomvoorspeller.nl/data/prices.json
- Forecast feed: https://stroomvoorspeller.nl/data/forecast.json
- Used for: Dutch EPEX day-ahead market prices and multi-day electricity price forecasts.
- Licence/attribution: Stroomvoorspeller data is used under **CC BY 4.0**; attribution to Stroomvoorspeller.nl must be retained.

Dummy OS Forecast uses market/forecast data as source material and calculates its own import/export tariff composition. The indicative consumer all-in calculations published by Stroomvoorspeller are not used as the authoritative Dummy OS tariff.

### EnergyZero

- Project: https://www.energyzero.nl/
- Used for: current daily gas market price through the Home Assistant EnergyZero integration.

EnergyZero is used as an actual/reference source for gas. Supplier-specific tariff components remain separate inside Dummy OS Forecast.

## Roadmap

Planned development areas include:

- continued Energy/Solar/Weather/Prices/Degree Days validation;
- immutable price/tariff history and actual import/export cost records;
- Solar daily aggregation, calibration and benchmark history;
- heat-demand and gas forecast models;
- gas/TTF forecast evaluation;
- broader forecast-quality diagnostics;
- stable interfaces for Dummy OS EMS.

## Releases and change history

Version-specific changes are documented in GitHub Releases and `RELEASE_NOTES.md`.

Alpha and beta versions should be treated as pre-releases until a stable release is explicitly published.

## Independence and disclaimer

Dummy OS Forecast is an independent open-source community project.

It is not affiliated with, sponsored by or endorsed by Home Assistant, Nabu Casa, Open-Meteo, Stroomvoorspeller.nl, EnergyZero, Anker Innovations or other third-party providers mentioned in the project documentation.

The software is provided for experimentation and Home Assistant automation/data purposes. Users remain responsible for reviewing configuration, source terms, data quality and any actions performed by systems that consume Dummy OS Forecast.
