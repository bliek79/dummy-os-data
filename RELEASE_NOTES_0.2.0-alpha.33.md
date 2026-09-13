## Dummy OS Energy 0.2.0-alpha.33

**Tag:** `0.2.0-alpha.33`

### Reserve, safety precharge and hourly Apex correction

Alpha 33 fixes the three live issues found immediately after the Alpha 32 native-288 planner rollout.

- Restores the old EMS usable-solar meaning on native quarter data. Two consecutive usable hours are now evaluated as two rolling 60-minute windows built from four quarters each. Each window is usable when total solar is positive and total solar is at least total home consumption. Alpha 32 incorrectly required all eight individual quarters to satisfy solar >= home.
- Keeps the planner engine native at 15 minutes / 72 hours / 288 slots. No return to an hourly calculation engine is introduced.
- Recalculates dynamic reserve from the corrected next-usable-solar point, preventing artificial long 100% reserve plateaus caused by the stricter Alpha 32 quarter interpretation.
- Keeps the old EMS alpha27 safety deadline semantics: the reserve applying after a quarter must be achievable by the end of that same quarter.
- Dynamic safety precharge is allocated to the cheapest technically usable quarter slots before the reserve deadline, with solar first priority and the shared 3.2 kW charge limit.
- Restores complete hourly Apex aggregation: `home_kwh` and `solar_kwh` are sums of the four underlying quarters, as are all energy-flow series. SOC and reserve series use the end value of the fourth quarter.
- Existing trade protection, Solar Charge Delay, Alpha31 price interpolation restrictions and shadow-only physical authority remain unchanged.

### Validation

The Alpha 33 release gate adds dedicated regressions for mixed-quarter usable-solar windows, non-saturated dynamic reserve, safety precharge before its deadline, and hourly home/solar aggregation. Alpha29, Alpha30, Alpha31 and Alpha32 regressions remain in the release gate.
