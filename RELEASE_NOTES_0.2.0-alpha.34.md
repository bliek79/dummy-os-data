## Dummy OS Energy 0.2.0-alpha.34

**Tag:** `0.2.0-alpha.34`

### Sequential safety planning and consistent native handoff

Alpha 33 restored the moving reserve curve and hourly Apex aggregates, but a
multi-day simulation could still be incorrectly marked infeasible. The safety
pre-estimator reused the initial battery charge at later reserve peaks without
subtracting earlier home consumption. Independent Grid Support allocations also
did not necessarily match the final Plan72 simulation.

### Fixed

- Build one authoritative native safety plan using the same sequential battery
  simulation that validates Plan72. Every purchase is checked against actual
  projected storage, solar-first charging, capacity and its reserve deadline.
- Protect accepted precharge energy until its deadline. A backward reachability
  bound prevents spending existing energy that cannot be restored in time within
  the configured power limit. The original dynamic reserve remains separately
  visible and is not lowered to make a failing plan pass.
- Keep Grid Support and Preview as upstream pre-solar advice; do not merge their
  independently placed purchases into a second operational safety schedule.
- Cap the final Grid Support allocation to the remaining requested deficit. A
  0.790 kWh stored-energy request is no longer allocated as two full 0.736 kWh
  quarters. AC input and stored battery energy remain distinct.
- Derive shadow-store candidates from the authoritative native slots, not hourly
  Apex rows. Preserve exact quarter boundaries and split differing power requests.
- Reject an unsafe trading candidate locally when the safety-only baseline is
  feasible. Retain that baseline instead of invalidating the entire plan.
- Account for small home/export flows in the actual battery balance rather than
  reporting a flow without subtracting it from storage.

### Diagnostics

- Publish reserve/execution breach counts, the first failing deadline and its
  battery-energy shortfall at the top level of Plan72.
- Publish `safety_plan` with accepted charge slots, AC/DC totals, deadline
  references, replay count and unresolved deadlines from the final published
  simulation. Upstream advice is explicitly marked as non-authoritative.
- Include `examples/alpha34_live_validation.jinja` for compact Home Assistant
  validation, including the first 12 hourly Apex rows.
- Exclude the additional large diagnostic payloads from Recorder attributes.

### Unchanged

- Native 15-minute / 72-hour / 288-slot calculation; Apex remains 72 hourly
  aggregates. Energy is summed; SOC and reserve use the final quarter value.
- Alpha 33's two hour-aligned usable-solar windows and the existing dynamic
  reserve meaning, 7.2 kWh capacity, 3.2 kW limits, efficiencies and execution buffer.
- Price-buffer handling, interpolation restrictions and degraded valid prefixes.
- Shadow-only operation; no physical execution authority or mode switching added.

### Validation and limits

- 25 dedicated regressions cover multi-day reserve peaks, tight feasible and
  genuinely impossible deadlines, early-cheap precharge, all-slot power and
  energy balance, precise native handoff, advice isolation, local trade rejection,
  12 seeded changing-deadline cases and final published energy accounting.
- Full local suite: 455 passed. CI and the publication workflow rerun the full
  suite and the targeted Alpha 29-34 planner regressions before release.
- The original Alpha 33 deterministic three-day regression failed with minimum
  execution headroom -83.7 percentage points; it now passes without breaches.
- This is a deterministic safety-first heuristic, not a global cost-optimal
  planner. Impossible deadlines remain infeasible and retain their data.
- The supplied live dump contained only the first 12 hours. The exact full
  -63.693-point live case still requires post-installation validation. Green CI
  does not establish complete old-EMS parity or live acceptance.
