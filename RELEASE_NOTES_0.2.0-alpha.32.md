## Dummy OS Energy 0.2.0-alpha.32

**Tag:** `0.2.0-alpha.32`

### Native 288-slot planner parity

Alpha 32 restores the core functional behaviour of the existing Dummy OS Anker EMS planner inside Dummy OS Energy while keeping the new architecture native at 15 minutes / 72 hours / 288 slots.

- Plan72 now runs its sequential battery simulation on native 15-minute slots instead of using the 72 hourly rows as the calculation engine.
- The 72-hour `hours` output remains available as a dashboard/Apex aggregation derived from four native quarter slots per hour.
- Dynamic reserve is recalculated for every quarter from the remaining home deficit until the next usable solar block.
- A usable solar block requires eight consecutive quarter slots (two hours) in which forecast solar is positive and at least covers forecast home consumption.
- Execution reserve is the dynamic reserve plus the existing 2 percentage point execution buffer.
- Safety precharge is planned ahead of future reserve peaks and allocated to cheaper technically usable quarter slots before the reserve deadline.
- Solar keeps first priority inside the 3.2 kW charge limit; the native full-quarter AC input ceiling is therefore 0.8 kWh before efficiency effects.
- Trade charging includes Solar Charge Delay: capacity expected to be filled by free solar before the chosen sell/use slot is not unnecessarily bought from the grid.
- Trade-reserved battery energy is protected from low-value early home discharge and can be used when current avoided import value is economically equal or better.
- Home demand keeps priority over grid export at a trade-discharge slot.
- Interpolated Alpha31 fallback prices remain excluded from trade-extremum discovery.
- Plan72 exposes native `slots` plus hourly `hours`; large planner arrays are marked unrecorded by the Home Assistant sensor adapter.
- Existing shadow-only safety remains unchanged: physical execution authority is still false.

### Dashboard contract

The Apex planner remains a 72-hour hourly presentation. Hourly energy series are the sum of the underlying four quarter slots. Expected SOC and dynamic reserve use the end value of the last quarter in each displayed hour. This keeps the graph readable while preserving native quarter decisions internally.

### Validation

Alpha 32 adds dedicated regressions for 288-slot execution, eight-quarter usable-solar detection, moving dynamic reserve, quarter charge/discharge limits, hourly energy conservation and interpolated-price trade exclusion. Existing Alpha29 price-buffer, Alpha30 startup and Alpha31 resilience regressions remain part of the release gate.
