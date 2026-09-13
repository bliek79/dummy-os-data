## Dummy OS Energy 0.2.0-alpha.30

**Tag:** `0.2.0-alpha.30`

### Non-blocking Startup for Forecast Sources

Alpha 30 removes the external forecast fetches from Home Assistant's critical config-entry startup path after live logs showed `dummy_os_data` platform setup exceeding 60 seconds.

#### Fixed
- Dummy OS Energy now loads local Home history/state first without waiting for the initial Weather cloud request.
- Sensor, select, binary sensor, switch, datetime and number platforms are registered before cloud-backed forecast sources are fetched.
- Weather, Prices and Solar are initialized in one background source wave instead of serially blocking config-entry setup.
- Degree Days is initialized after the source wave so it keeps its Weather dependency without delaying Home Assistant startup.
- The background source task is tracked and cancelled safely on integration unload/reload.
- Planner/model sensors receive a consolidated refresh after source initialization completes.
- Existing source-specific retry/backoff behavior is retained, but those waits no longer hold up Home Assistant's integration setup.

#### Unchanged contracts
- Native architecture remains 15 minutes / 72 hours / 288 planner slots.
- Alpha 29's 76-hour / 304-slot price buffer and exact 288-slot planner window are unchanged.
- Missing source data remains fail-closed; no zero fill, forward fill or synthetic forecast data is introduced.
- Forecast models, Reserve SOC, Grid Support, Preview and Plan72 decision logic are unchanged.
- Physical battery execution remains `shadow_only` and is not enabled by this release.

#### Validation
- Added Alpha 30 startup-contract tests covering platform-before-cloud ordering, concurrent source initialization, Degree Days dependency ordering, task cancellation on unload and version consistency.
- Full repository test suite, compile checks and existing Alpha 29 price-buffer regression tests remain release gates.

#### Live validation after installation
Restart Home Assistant and confirm the log no longer reports `Setup of platform dummy_os_data is taking longer than 60 seconds`. Then confirm Weather, Solar and Prices recover normally after startup and that `sensor.do_prices_timeline` still reports a complete 304-slot buffer and 288-slot planner window when Stroomvoorspeller supplies the full horizon.
