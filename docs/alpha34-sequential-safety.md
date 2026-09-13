# Alpha 34: authoritative native safety plan

## Goal and evidence

User-authorized correction of the Alpha 33 multi-day safety failure. The prior
release restored usable-solar semantics and hourly home/solar aggregates, but
reported `infeasible` with complete 288-slot input. Source baseline:
`e9284711166e644965523adf84903efc21976f8b`; old EMS reference:
`bliek79/dummy-os-anker-ems@2c81cd04148146d5a7785f7210d0512013e5860a`.

The old reserve/precharge implementation was inspected rather than assumed.
Its initial-SOC-plus-solar estimator is also optimistic across later cycles.
Merely copying that estimator again does not repair sequential feasibility.
This fix preserves the reserve and end-of-slot deadline meaning while validating
precharge on the actual simulated storage path.

## Inputs, operation and outputs

Input72h's native home/solar/price quarters and the validated observed SOC form
one immutable simulation input. The Alpha 33 reserve profile is unchanged.
`build_native_safety_plan` makes an empty-schedule replay, checks each quarter's
end reserve and tries eligible earlier charging quarters in price/time order.
A trial is accepted only when it improves the storage at that deadline. Every
accepted change is replayed; there is no start-SOC reuse, zero fill or fictional
storage correction. Stored energy allocated early is held until its deadline.

The backward reachable storage bound is `max(current execution reserve,
next reachable bound - maximum storable charge per quarter)`. It prevents
avoidable early discharge when too little charging time remains. It is reported
separately as `precharge_protection_soc_percent`, not substituted for the
original `dynamic_reserve_*` values.

The final replay, not theoretical slot capacity, defines `safety_plan` accepted
energy, SOC, deadlines and shortfalls. A separate trading replay uses the same
safety commitments. If trading invalidates a feasible baseline, that candidate
is rejected and the baseline remains published. No extra safety energy is bought
solely to conceal that unsafe trade.

## Authority and scope

`Plan72.safety_plan_authority = plan72_native`. Grid Support and Preview retain
their existing pre-solar diagnostic scope but are advice only for this native
path. The store bridge consumes final Plan72 native quarter flows and never
adds another Grid Support schedule. It never widens a quarter to an Apex hour.
Infeasible native plans emit no store candidates. Existing shadow-only rights
and the three-slot store limit are unchanged.

## Units and constraints

All energy uses kWh. Grid input is AC; accepted stored energy equals AC input
multiplied by the 0.92 charge efficiency. Battery-to-home/export outputs are AC
and reduce stored energy by output / 0.92. Solar-to-battery retains the existing
stored-energy convention. Combined charging is at most 0.8 kWh AC per quarter;
combined battery output is at most 0.8 kWh AC per quarter. Solar receives first
access to the shared charge limit. Comparisons use a 1e-6 kWh tolerance; display
rounding does not decide feasibility. Exact internal storage remains available
for diagnostics and balance tests.

Apex continues to use `hours`: sums of four quarters for energy and the last
quarter's SOC/reserve endpoint. Quarter arrays are not rendered as 288 points by
this change. The dashboard YAML itself has not been modified.

## Validation, status and remaining work

The deterministic original-source test reproduces a false infeasible result
(-83.7 percentage points minimum headroom). The corrected path has no breach.
25 focused tests include all 288 balance/limit checks, later-day reserve peaks,
existing-energy reachability, genuinely impossible deadlines, cheap precharge,
0.790 kWh quota, upstream advice isolation, exact quarter handoff, 71-hour
prefix preservation, local trade rejection, published accounting and seeded
changing deadlines. Two previous tests are adapted to the intentional authority
change; no previous regression is skipped or marked expected failure.

Full local suite: 455 passed. Publication is gated on CI and the release workflow.
Post-installation validation remains required with the full current input; the
user supplied only twelve hours, not enough for an exact replay of the entire
reported -63.693-point case. This change does not claim complete planner parity,
global economic optimality or physical-execution readiness.
