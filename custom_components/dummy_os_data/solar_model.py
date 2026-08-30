"""Pure calculation helpers for the Dummy OS Solar forecast."""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Sequence


def pv_power_kw(
    irradiance_wm2: float | int | None,
    dc_capacity_kwp: float,
    ac_limit_kw: float,
    performance_factor: float,
) -> float:
    """Convert plane-of-array irradiance to capped AC-equivalent power."""
    try:
        irradiance = float(irradiance_wm2 or 0.0)
        dc_capacity = float(dc_capacity_kwp)
        ac_limit = float(ac_limit_kw)
        factor = float(performance_factor)
    except (TypeError, ValueError):
        return 0.0
    if not all(math.isfinite(value) for value in (irradiance, dc_capacity, ac_limit, factor)):
        return 0.0
    irradiance = max(0.0, irradiance)
    dc_capacity = max(0.0, dc_capacity)
    ac_limit = max(0.0, ac_limit)
    factor = max(0.0, factor)

    uncapped_kw = irradiance / 1000.0 * dc_capacity * factor
    return round(min(ac_limit, uncapped_kw), 6)


def slot_energy_kwh(power_kw: float, resolution_minutes: int = 15) -> float:
    """Convert average slot power to energy."""
    try:
        power = float(power_kw)
        resolution = int(resolution_minutes)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(power) or resolution <= 0:
        return 0.0
    return round(max(0.0, power) * resolution / 60.0, 6)


def backward_average_slot_start(timestamp: datetime, resolution_minutes: int = 15) -> datetime:
    """Map a backward-average source timestamp to the energy-slot start."""
    return timestamp - timedelta(minutes=resolution_minutes)


def next_complete_slot(timestamp: datetime, resolution_minutes: int = 15) -> datetime:
    """Return the current boundary only when exactly on it, otherwise the next."""
    floor_minute = (timestamp.minute // resolution_minutes) * resolution_minutes
    floor = timestamp.replace(minute=floor_minute, second=0, microsecond=0)
    return floor if timestamp == floor else floor + timedelta(minutes=resolution_minutes)


def next_future_slot(timestamp: datetime, resolution_minutes: int = 15) -> datetime:
    """Return the first slot boundary strictly after the current quarter."""
    floor_minute = (timestamp.minute // resolution_minutes) * resolution_minutes
    floor = timestamp.replace(minute=floor_minute, second=0, microsecond=0)
    return floor + timedelta(minutes=resolution_minutes)


def next_future_slot_index(
    starts: Sequence[datetime],
    timestamp: datetime,
    resolution_minutes: int = 15,
) -> int | None:
    """Return the first timeline index at or after the next future boundary."""
    target = next_future_slot(timestamp, resolution_minutes)
    for index, slot_start in enumerate(starts):
        if slot_start >= target:
            return index
    return None


def split_ac_power(
    total_ac_w: float | int | None,
    north_dc_w: float | int | None,
    south_dc_w: float | int | None,
) -> tuple[float | None, float | None]:
    """Split inverter AC power using the two DC-input proportions."""
    try:
        total = float(total_ac_w)
    except (TypeError, ValueError):
        return None, None
    if not math.isfinite(total):
        return None, None
    total = max(0.0, total)

    # With zero AC output both roof contributions are unambiguously zero; a
    # missing/asleep DC-input sensor must not invalidate an overnight quarter.
    if total <= 0.0:
        return 0.0, 0.0

    try:
        north = float(north_dc_w)
        south = float(south_dc_w)
    except (TypeError, ValueError):
        return None, None
    if not all(math.isfinite(value) for value in (north, south)):
        return None, None
    north = max(0.0, north)
    south = max(0.0, south)

    dc_total = north + south
    if dc_total <= 0.0:
        return None, None

    north_ac = total * north / dc_total
    return round(north_ac, 3), round(total - north_ac, 3)
