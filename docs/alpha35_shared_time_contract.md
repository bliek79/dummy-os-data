# Alpha35 - Joint planner time contract v1

## Goal
One explicit UTC period for Home, Solar, Prices, SOC-dependent calculations and Plan72. Keep native 15 minutes / 72 actual hours / 288 slots, retain Alpha34 sequential safety, and derive hourly Apex output only after simulation. Different retrieval times are allowed; different selected timestamps within one calculation are not.

## Authority and selection
Capture reference_utc once before reading source buffers. window_start is the next UTC quarter boundary, including the boundary itself when reference is exact. window_end is exclusive, exactly 72 real hours later. Slot i is [start+i*15min, start+(i+1)*15min). A deterministic window_id covers contract version/start/end/resolution/count, separately from retrieval and forecast generation times.

Home receives the explicit start. Prices selects that exact window from its existing 76-hour timestamp-indexed buffer. Solar selects the same timestamps from its retained buffer. Ambiguous duplicate values are rejected, not silently last-wins. Missing values retain their expected position. Existing bounded isolated-price interpolation remains labelled and excluded from trading. Independent Energy Need remains useful when only later prices are missing.

The existing 72 rows with four exact quarters each remain window-relative transport groups, not an authoritative hourly planner and not clock-hour Apex output. No leading quarters are discarded for whole-hour alignment. Production explicitly passes time_contract; old pure-function callers without metadata retain their compatibility route.

## Initial SOC
The raw measured SOC contract remains distinct. On the captured reference, the reported SOC and reported AC charge/discharge power estimate storage at window_start, with the existing capacity and 92% efficiencies. The bridge is at most 15 minutes and outside the 288-slot horizon. It is explicitly a constant-reported-power estimate, not a measurement of future SOC. Source update/report timestamps are retained; device latency is not assumed away. Invalid/missing/contradictory power never becomes zero. Invalid SOC projection stops SOC-dependent planning, not source forecasts. Exact boundaries need no projection. There are no physical actions.

## Dependency and publication safety
Window metadata propagates through Input, Energy Need, Reserve, Grid Support, Preview, Plan72 and shadow handoff. Reject window mismatch locally. Published consumers subscribe to upstream completion so a transient boundary mismatch can recover. Executor results for an elapsed window are labelled stale rather than current valid. The shadow-store override applies the same check before any store mutation. Missing bridge telemetry can trigger recovery without recalculating on every normal power sample.

## Apex remains hourly
Group native results by UTC clock hour, localizing labels only for display. A 72-hour window beginning on :15/:30/:45 intersects 73 clock-hour buckets: partial first and last plus full middle hours. At :00 it intersects 72. Both contain exactly 288 quarters and 72 real hours. Publish actual start/end, bucket start/end, coverage_minutes and partial_hour. Do not inflate a partial sum into a full-hour estimate. Sum energy with six-decimal precision, time-weight prices, and preserve true beginning/ending SOC and reserve timestamps. End SOC belongs on end, not start. Existing dashboard YAML is not automatically replaced in this release.

## Preserved behavior
Keep dynamic reserve, 2% execution buffer, 7.2 kWh capacity, 3.2 kW AC limits, Alpha34 accepted-energy safety commitments, safety-only fallback when a trade is unsafe, and shadow-only authority. The old-EMS usable solar rule still requires two complete clock hours assembled from native quarters. At offset planner starts those candidates are found by timestamp, not index modulo four. Solar provider timestamps are requested in UTC to avoid DST ambiguity.

## Validation and limits
Reproduce all minute positions including the earlier :00-:14 mismatch, exact boundaries/microseconds, midnight/year rollover, equivalent UTC offsets, both Amsterdam DST changes, exhausted buffers, duplicate and missing source slots, preserved independent calculations, SOC bridge values and invalid telemetry, one-reference source selection, window mismatch and hourly energy/endpoint conservation. Run all existing regressions including Alpha34 sequential safety before merge and again before publication. Green CI is not live HA acceptance, global cost optimality or proof of complete old-EMS functional parity.

## Live acceptance
Use examples/alpha35_live_validation.jinja. Verify all dependent window IDs match; 288 exact native slots; hourly coverage totals 4320 minutes; first/last actual timestamps equal the published window; projected SOC is labelled and matches first native start; zero unexpected reserve/execution breaches. Review actual source telemetry latency and the constant-power bridge assumption. Then update the complete Apex card without changing the underlying native period.
