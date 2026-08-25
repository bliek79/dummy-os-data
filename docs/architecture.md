# Home Forecast historical foundation

## Canonical resolution

15 minutes. The future 72-hour model will therefore contain 288 forecast slots.

## Data flow

`Home Power sensor (W/kW)` -> runtime power integration -> completed 15-minute kWh record -> local persistent storage -> later forecast models -> evaluation -> calibration.

## Profile separation

Every completed quarter stores one profile:

- `normal`
- `away`

This prevents Away consumption from contaminating the normal household profile.

## Data quality

A completed quarter is considered valid when at least 90% of its real interval duration was covered by a valid W/kW source value. Zero power is valid. `unknown`, `unavailable`, invalid numeric values and unsupported units are not treated as zero.
