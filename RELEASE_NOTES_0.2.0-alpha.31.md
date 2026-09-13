## Dummy OS Energy 0.2.0-alpha.31

**Tag:** `0.2.0-alpha.31`

### Resilient Planner Horizon and Isolated Price-Gap Recovery

Alpha 31 prevents one incomplete future price hour from collapsing the complete Dummy OS Energy planning chain. The native architecture remains 15 minutes / 72 hours / 288 slots, while each planner stage now uses only the reliable horizon it actually needs.

#### Fixed
- DO Plan Input 72h now publishes an explicit reliable prefix with `effective_horizon_hours`, `valid_through`, `first_invalid_index`, `first_invalid_reason`, `trailing_incomplete_only` and degraded-component diagnostics.
- A trailing source gap degrades the planner horizon instead of automatically emptying Energy Need, Reserve SOC, Preview and Plan72.
- Energy Need is isolated from unrelated trailing price gaps and only requires valid Home/Solar inputs through its own required horizon.
- Preview and Grid Support operate on the reliable prefix and keep valid safety information available when the far end of the 72-hour horizon is incomplete.
- Plan72 simulates sequentially only through the reliable prefix. It never simulates across an invalid gap and never invents SOC beyond `valid_through`.
- Plan72 now publishes separate `grid_to_battery_safety_kwh` and `grid_to_battery_trade_kwh` values while preserving total `grid_to_battery_kwh`, so the dashboard can reproduce the old EMS safety/trade split without subtraction heuristics.

#### Bounded price interpolation
- A single isolated missing 15-minute price may be reconstructed from the direct previous and next real price points using their arithmetic mean.
- Both neighbours must be finite, non-interpolated and belong to the same semantic source family (`known*` or `forecast*`).
- Interpolation is explicit: `kind=interpolated`, `fallback_used=true`, `fallback_method=neighbor_average`, including both neighbour timestamps.
- Two or more consecutive missing quarters are never interpolated.
- No beginning/end extrapolation, zero fill or forward fill is introduced.
- Interpolated prices may maintain energy/reserve continuity, but are excluded from trade-pair discovery so a synthetic point cannot create an arbitrage signal.

#### Safety and execution
- Physical execution remains `shadow_only` and `physical_execution_authority=false`.
- Final execution revalidation remains fail-closed per action.
- Source failures are isolated locally: unrelated valid forecast/SOC/planner information remains available rather than being cleared globally.

#### Validation
- Full repository tests and Python compile checks remain mandatory release gates.
- Alpha 29 price-buffer and Alpha 30 non-blocking-startup regression tests remain mandatory.
- Alpha 31 regression coverage validates isolated interpolation, consecutive-gap rejection, trailing-horizon degradation, downstream failure isolation, partial Plan72 simulation and separate safety/trade charge accounting.

#### Live validation after installation
Confirm `sensor.dummy_os_energy_do_plan_input_72h` reports either 72 reliable hours or a clear degraded `effective_horizon_hours`. When the final price hour is incomplete, confirm Energy Need and Reserve SOC remain usable when their own required horizon is complete, and confirm Plan72 publishes the reliable prefix instead of `hour_count: 0`. Also verify that interpolated price slots, when present, are explicitly identifiable and never become standalone trade extrema.
