## Dummy OS Energy 0.2.0-alpha.35

**Tag:** `0.2.0-alpha.35`

### One joint native time contract
Capture one UTC reference before source selection. Home, Solar and Prices use its exact quarter-aligned 72-hour / 288-slot window. Prices selects the supplied window from the existing 76-hour buffer instead of independently rounding to an hour. This repairs the first-fifteen-minutes mismatch that could omit the final planner hour despite sufficient source data.

### Input and dependencies
- Explicit reference/start/exclusive-end/window ID propagate through Input, Energy Need, Reserve, Grid Support, Preview, Plan72 and shadow handoff.
- No leading native quarters are discarded for whole-hour alignment. Existing four-quarter rows are transport only; native values remain authoritative.
- Validate exact timestamps and finite data; reject conflicting duplicate source values. Preserve missing-slot positions and existing bounded isolated-price interpolation.
- Energy Need can remain useful when only later prices are missing. A mismatched consumer blocks locally and recovers on upstream publication, rather than shifting timestamps.
- Expired executor results are marked stale; no stale candidates are applied to the shadow store.
- UTC arithmetic and UTC Solar-provider timestamps preserve 288 distinct slots across daylight-saving changes.

### SOC at the actual simulation start
The raw measured SOC remains unchanged and separate. An explicit bridge projects the reported SOC to the next quarter boundary using the currently reported AC charge/discharge power and existing efficiencies. It is a labelled constant-power estimate over at most 15 minutes, not a measured future value. Source update/report timestamps remain available. Missing or contradictory power never becomes zero; only SOC-dependent planning is blocked. No physical commands are introduced.

### Hourly Apex output
Apex remains an hourly presentation. `hours` contains clock-hour buckets with actual start/end, coverage minutes and a partial flag. A quarter-start horizon normally intersects 73 clock-hour buckets (partial first/last); exact whole-hour starts intersect 72. Both contain 288 quarters and exactly 72 actual hours. Energy is summed without inflating partial hours, prices are time-weighted and SOC/reserve endpoints retain their real timestamps. Existing dashboard YAML is not silently rewritten.

### Preserved
Alpha34's sequential safety plan, dynamic reserve, execution buffer, capacity, power limits, efficiencies and shadow-only authority remain. The old-EMS two-full-clock-hour solar rule is preserved by timestamp-based candidate alignment, including quarter-offset horizons. Legacy pure-function callers without a time contract retain compatibility.

### Validation and live acceptance
Full tests and targeted time/SOC/aggregation plus Alpha29-34 regressions run before merge and again in the publication gate. The installation ZIP is compared byte-for-byte with tested sources. Use `examples/alpha35_live_validation.jinja` for window identity, 288 slots, 72/73 hourly coverage, explicit SOC bridge and safety checks. CI success does not establish live telemetry correctness, global economic optimality or complete old-EMS parity.
