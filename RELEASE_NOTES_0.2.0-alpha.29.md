## Dummy OS Energy 0.2.0-alpha.29

**Tag:** `0.2.0-alpha.29`

### 76-hour Price Buffer and Exact 72-hour Planner Window

Alpha 29 hardens the electricity-price horizon after live Alpha 28 validation showed the final planner hour becoming invalid when the last two quarter-hour prices (`07:30` and `07:45` UTC) fell outside the internal price slice.

#### Fixed
- Prices now maintain a timestamp-indexed 76-hour internal buffer (`304` native 15-minute slots) while the planner contract remains exactly 72 hours / 288 slots.
- Price points are deduplicated by canonical UTC timestamp.
- Source priority is explicit: `known_pt15m` > `known_hourly_fallback` > `forecast_hour`.
- Hourly known and forecast values continue to normalize to all four native 15-minute slots before planner selection.
- The planner price window is selected by the exact expected timestamps instead of by slicing a sorted list by length.
- Missing timestamps remain missing and fail closed; no previous-price carry-forward, zero fill, or synthetic extrapolation is introduced.
- Buffer and planner-window diagnostics expose expected, valid, missing and duplicate slot counts plus the first/last missing timestamps.

#### Validation
- Added regression coverage for a 76-hour / 304-slot buffer and an exact 72-hour / 288-slot planner selection.
- Added the live horizon-edge regression case proving `2026-09-16T07:30:00+00:00` and `2026-09-16T07:45:00+00:00` remain inside the selected planner window when the source supplies them.
- Added fail-closed coverage proving missing final slots are reported and do not shift the window.
- Added deduplication tests proving native PT15M prices override hourly fallback and forecast values on the same timestamp.
- Added timezone-equivalent timestamp coverage.
- Native architecture remains 15 minutes / 72 hours / 288 planner slots.
- Physical battery execution remains outside this release boundary and `shadow_only` safety remains unchanged.

#### Live validation after installation
Confirm that `sensor.dummy_os_energy_do_plan_input_72h` returns to `ready` with `valid_price_hours: 72`, `fully_valid_hours: 72`, and no `price_hours_incomplete` blocker when the Stroomvoorspeller source contains the required horizon. Also verify the price diagnostics show a complete 288-slot planner window.
