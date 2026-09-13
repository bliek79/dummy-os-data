"""Alpha 33 live-regression fixes for reserve, safety and hourly Apex output."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.dummy_os_data.do_plan_native_common import (
    CAPACITY_KWH,
    CHARGE_EFFICIENCY_PERCENT,
    DISCHARGE_EFFICIENCY_PERCENT,
    _dynamic_reserve_profile,
    _dynamic_safety_schedule,
    _find_next_usable_solar,
)
from custom_components.dummy_os_data.do_plan_native_simulation import _aggregate_hours


def _slot(index: int, *, home: float = 0.1, solar: float = 0.0, price: float = 0.20) -> dict:
    start = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * index)
    return {
        "index": index,
        "hour_index": index // 4,
        "quarter_index": index % 4,
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=15)).isoformat(),
        "home_kwh": home,
        "solar_kwh": solar,
        "import_price": price,
        "export_price": price - 0.08,
        "price_kind": "known_pt15m",
        "price_fallback_used": False,
    }


def test_usable_solar_keeps_old_two_hour_semantics_from_quarter_sums() -> None:
    slots = [_slot(i) for i in range(20)]
    # Each hour totals 0.40 kWh solar versus 0.40 kWh home, but two individual
    # quarters in each hour are below home. Alpha32 rejected this incorrectly.
    pattern = [0.0, 0.2, 0.2, 0.0, 0.0, 0.2, 0.2, 0.0]
    for i, solar in enumerate(pattern):
        slots[i]["solar_kwh"] = solar
    assert _find_next_usable_solar(slots, 0) == 0


def test_dynamic_reserve_does_not_saturate_from_alpha32_quarter_rule() -> None:
    slots = [_slot(i) for i in range(40)]
    # Two dark hours followed by two usable hours built from mixed quarters.
    pattern = [0.0, 0.2, 0.2, 0.0, 0.0, 0.2, 0.2, 0.0]
    for offset, solar in enumerate(pattern, start=8):
        slots[offset]["solar_kwh"] = solar
    profile = _dynamic_reserve_profile(slots, DISCHARGE_EFFICIENCY_PERCENT / 100.0)
    first_soc = profile[0]["dynamic_floor_kwh"] / CAPACITY_KWH * 100.0
    solar_soc = profile[8]["dynamic_floor_kwh"] / CAPACITY_KWH * 100.0
    assert profile[0]["next_usable_solar"] == slots[8]["start"]
    assert 12.0 < first_soc < 100.0
    assert solar_soc == 12.0
    assert first_soc > solar_soc


def test_dynamic_safety_precharge_allocates_before_reserve_deadline() -> None:
    slots = [_slot(i, price=0.30 - i * 0.01) for i in range(12)]
    base = 0.864
    profile = []
    for i in range(13):
        execution = 5.0 if i == 5 else base + 0.144
        dynamic = 4.856 if i == 5 else base
        profile.append({
            "dynamic_floor_kwh": dynamic,
            "execution_floor_kwh": execution,
            "need_until_solar_kwh": 0.0,
            "next_usable_solar": slots[8]["start"] if i <= 5 else None,
            "solar_horizon_complete": i <= 5,
        })
    planned = _dynamic_safety_schedule(
        slots,
        profile,
        start_soc=20.0,
        charge_eff=CHARGE_EFFICIENCY_PERCENT / 100.0,
    )
    assert len(planned) >= 2
    deadline = datetime.fromisoformat(slots[4]["end"])
    assert all(datetime.fromisoformat(key) < deadline for key in planned)
    assert sum(planned.values()) > 0.0


def test_hourly_apex_output_contains_home_and_solar_sums() -> None:
    slots = []
    for i in range(4):
        slot = _slot(i, home=0.10 + i * 0.01, solar=0.02 + i * 0.01)
        slot.update({
            "start_soc_percent": 80.0 - i,
            "end_soc_percent": 79.0 - i,
            "dynamic_reserve_start_soc_percent": 40.0 - i,
            "dynamic_reserve_end_soc_percent": 39.0 - i,
            "execution_reserve_start_soc_percent": 42.0 - i,
            "execution_reserve_end_soc_percent": 41.0 - i,
            "dynamic_need_until_solar_kwh": 1.0,
            "dynamic_need_after_slot_kwh": 0.9,
            "next_usable_solar": None,
            "solar_horizon_complete": False,
            "execution_headroom_soc_percent": 20.0,
            "action_parts": ["baseline"],
            "solar_to_home_kwh": 0.02,
            "solar_to_battery_kwh": 0.0,
            "solar_to_grid_kwh": 0.0,
            "grid_to_home_kwh": 0.08,
            "grid_to_battery_kwh": 0.0,
            "grid_to_battery_safety_kwh": 0.0,
            "grid_to_battery_trade_kwh": 0.0,
            "battery_to_home_kwh": 0.0,
            "battery_to_grid_kwh": 0.0,
        })
        slots.append(slot)
    hours = _aggregate_hours(slots)
    assert len(hours) == 1
    assert hours[0]["home_kwh"] == round(sum(slot["home_kwh"] for slot in slots), 3)
    assert hours[0]["solar_kwh"] == round(sum(slot["solar_kwh"] for slot in slots), 3)
    assert hours[0]["end_soc_percent"] == slots[-1]["end_soc_percent"]
    assert hours[0]["dynamic_reserve_end_soc_percent"] == slots[-1]["dynamic_reserve_end_soc_percent"]
