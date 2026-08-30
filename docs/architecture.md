# Home Forecast historical foundation

## Canonical resolution

15 minutes. The future 72-hour model will therefore contain 288 forecast slots.

## Data flow

`Home Power sensor (W/kW)` -> runtime power integration -> completed 15-minute kWh record -> local persistent storage -> later forecast models -> evaluation -> calibration.

## Solar Forecast shadow flow

`Open-Meteo GTI north + GTI south` -> backward-average timestamp normalization
-> per-roof physical PV conversion -> AC cap -> 15-minute kWh -> combined
288-slot timeline.

Actual roof power is derived independently:

`SMA total AC x SMA input A/(A+B)` for north and the complementary share for
south.

At every quarter boundary, the matching Solar forecast is frozen before actual
production for that slot is known. Total AC and the two AC-equivalent roof
shares are then integrated with zero-order hold. At the next boundary the
completed actual kWh values are compared with the immutable snapshot. Each
component requires at least 90% time coverage; unavailable data remains missing
instead of becoming zero. Compact active and last-completed state survives an
integration reload through Home Assistant storage.

Forecast and actual data remain observation-only. The native quarter
evaluation does not calibrate the model or influence the planner; package 86
and Solcast remain independent benchmarks.

## Profile separation

Every completed quarter stores one profile:

- `normal`
- `away`

This prevents Away consumption from contaminating the normal household profile.

## Data quality

A completed quarter is considered valid when at least 90% of its real interval duration was covered by a valid W/kW source value. Zero power is valid. `unknown`, `unavailable`, invalid numeric values and unsupported units are not treated as zero.
