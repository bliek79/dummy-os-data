"""Pure calculation helpers for the Dummy OS Solar forecast."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta


def pv_power_kw(
    irradiance_wm2: float | int | None,
    dc_capacity_kwp: float,
    ac_limit_kw: float,
    performance_factor: float,
) -> float:
    """Convert plane-of-array irradiance to capped AC-equivalent power."""
    try:
        irradiance = max(0.0, float(irradiance_wm2 or 0.0))
        dc_capacity = max(0.0, float(dc_capacity_kwp))
        ac_limit = max(0.0, float(ac_limit_kw))
        factor = max(0.0, float(performance_factor))
    except (TypeError, ValueError):
        return 0.0

    uncapped_kw = irradiance / 1000.0 * dc_capacity * factor
    return round(min(ac_limit, uncapped_kw), 6)


def slot_energy_kwh(power_kw: float, resolution_minutes: int = 15) -> float:
    """Convert average slot power to energy."""
    return round(max(0.0, float(power_kw)) * resolution_minutes / 60.0, 6)


def backward_average_slot_start(timestamp: datetime, resolution_minutes: int = 15) -> datetime:
    """Map a backward-average source timestamp to the energy-slot start."""
    return timestamp - timedelta(minutes=resolution_minutes)


def next_complete_slot(timestamp: datetime, resolution_minutes: int = 15) -> datetime:
    """Return the current boundary only when exactly on it, otherwise the next."""
    floor_minute = (timestamp.minute // resolution_minutes) * resolution_minutes
    floor = timestamp.replace(minute=floor_minute, second=0, microsecond=0)
    return floor if timestamp == floor else floor + timedelta(minutes=resolution_minutes)


def next_future_slot(timestamp: datetime, resolution_minutes: int = 15) -> datetime:
    """Return the first slot boundary strictly after the supplied timestamp."""
    floor_minute = (timestamp.minute // resolution_minutes) * resolution_minutes
    floor = timestamp.replace(minute=floor_minute, second=0, microsecond=0)
    return floor + timedelta(minutes=resolution_minutes)


def next_future_slot_index(
    slot_starts: Sequence[datetime],
    timestamp: datetime,
    resolution_minutes: int = 15,
) -> int | None:
    """Return the first timeline index belonging to a future complete slot."""
    target = next_future_slot(timestamp, resolution_minutes)
    for index, slot_start in enumerate(slot_starts):
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
        total = max(0.0, float(total_ac_w))
        north = max(0.0, float(north_dc_w))
        south = max(0.0, float(south_dc_w))
    except (TypeError, ValueError):
        return None, None

    dc_total = north + south
    if dc_total <= 0.0:
        return (0.0, 0.0) if total <= 0.0 else (None, None)

    north_ac = total * north / dc_total
    return round(north_ac, 3), round(total - north_ac, 3)
