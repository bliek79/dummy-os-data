from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
import types

# prices.py is an integration module and CI deliberately does not install
# Home Assistant. Provide the minimal import-time stubs required to exercise
# the pure price-buffer helpers without changing their production location.
if "homeassistant" not in sys.modules:
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

core = types.ModuleType("homeassistant.core")
core.Event = object
core.HomeAssistant = object
core.callback = lambda func: func
sys.modules["homeassistant.core"] = core

helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []
sys.modules["homeassistant.helpers"] = helpers

aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
aiohttp_client.async_get_clientsession = lambda *_args, **_kwargs: None
sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

helpers_event = types.ModuleType("homeassistant.helpers.event")
helpers_event.async_track_state_change_event = lambda *_args, **_kwargs: None
helpers_event.async_track_time_interval = lambda *_args, **_kwargs: None
sys.modules["homeassistant.helpers.event"] = helpers_event

util = types.ModuleType("homeassistant.util")
util.__path__ = []
sys.modules["homeassistant.util"] = util

dt_module = types.ModuleType("homeassistant.util.dt")
dt_module.UTC = timezone.utc
dt_module.utcnow = lambda: datetime.now(timezone.utc)
dt_module.as_local = lambda value: value
dt_module.parse_datetime = lambda value: datetime.fromisoformat(value)
sys.modules["homeassistant.util.dt"] = dt_module
util.dt = dt_module

from custom_components.dummy_os_data.prices import (
    PLANNER_PRICE_SLOT_COUNT,
    PRICE_BUFFER_SLOT_COUNT,
    PricePoint,
    _deduplicate_price_points,
    _expected_quarter_starts,
    _select_exact_price_window,
)


def _point(start: datetime, kind: str = "forecast_hour", value: float = 0.2) -> PricePoint:
    return PricePoint(
        start=start,
        market_ex_vat=value,
        market_incl_vat=value,
        import_all_in=value,
        export_all_in=value,
        kind=kind,
        source_resolution_minutes=15 if kind == "known_pt15m" else 60,
    )


def test_76h_buffer_contains_304_native_quarters() -> None:
    start = datetime(2026, 9, 13, 7, 30, tzinfo=timezone.utc)
    starts = _expected_quarter_starts(start, PRICE_BUFFER_SLOT_COUNT)

    assert PRICE_BUFFER_SLOT_COUNT == 304
    assert len(starts) == 304
    assert starts[0] == start
    assert starts[-1] == start + timedelta(hours=75, minutes=45)


def test_exact_72h_planner_window_is_selected_from_76h_buffer() -> None:
    buffer_start = datetime(2026, 9, 13, 7, 30, tzinfo=timezone.utc)
    planner_start = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    points = [_point(start) for start in _expected_quarter_starts(buffer_start, PRICE_BUFFER_SLOT_COUNT)]
    indexed, duplicates = _deduplicate_price_points(points)

    selected, missing = _select_exact_price_window(
        indexed,
        start=planner_start,
        slot_count=PLANNER_PRICE_SLOT_COUNT,
    )

    assert duplicates == 0
    assert PLANNER_PRICE_SLOT_COUNT == 288
    assert len(selected) == 288
    assert missing == []
    assert selected[0].start == planner_start
    assert selected[-1].start == datetime(2026, 9, 16, 7, 45, tzinfo=timezone.utc)


def test_horizon_edge_slots_0730_and_0745_are_not_cut_off() -> None:
    buffer_start = datetime(2026, 9, 13, 7, 0, tzinfo=timezone.utc)
    planner_start = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    points = [_point(start, value=0.355132) for start in _expected_quarter_starts(buffer_start, PRICE_BUFFER_SLOT_COUNT)]
    indexed, _ = _deduplicate_price_points(points)

    selected, missing = _select_exact_price_window(
        indexed,
        start=planner_start,
        slot_count=PLANNER_PRICE_SLOT_COUNT,
    )

    assert missing == []
    assert selected[-2].start == datetime(2026, 9, 16, 7, 30, tzinfo=timezone.utc)
    assert selected[-1].start == datetime(2026, 9, 16, 7, 45, tzinfo=timezone.utc)
    assert selected[-2].import_all_in == 0.355132
    assert selected[-1].import_all_in == 0.355132


def test_missing_slots_are_reported_and_selection_never_shifts() -> None:
    planner_start = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    starts = _expected_quarter_starts(planner_start, PLANNER_PRICE_SLOT_COUNT)
    missing_expected = {starts[-2], starts[-1]}
    points = [_point(start) for start in starts if start not in missing_expected]
    indexed, _ = _deduplicate_price_points(points)

    selected, missing = _select_exact_price_window(
        indexed,
        start=planner_start,
        slot_count=PLANNER_PRICE_SLOT_COUNT,
    )

    assert len(selected) == 286
    assert missing == [starts[-2], starts[-1]]
    assert selected[-1].start == starts[-3]


def test_deduplication_prefers_pt15m_over_hourly_and_forecast() -> None:
    start = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    indexed, duplicate_count = _deduplicate_price_points(
        [
            _point(start, "forecast_hour", 0.10),
            _point(start, "known_hourly_fallback", 0.20),
            _point(start, "known_pt15m", 0.30),
        ]
    )

    assert duplicate_count == 2
    assert indexed[start].kind == "known_pt15m"
    assert indexed[start].import_all_in == 0.30


def test_timezone_equivalent_timestamps_deduplicate_to_one_slot() -> None:
    utc_start = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    cest = timezone(timedelta(hours=2))
    local_start = datetime(2026, 9, 13, 10, 0, tzinfo=cest)

    indexed, duplicate_count = _deduplicate_price_points(
        [
            _point(local_start, "forecast_hour", 0.10),
            _point(utc_start, "known_pt15m", 0.25),
        ]
    )

    assert duplicate_count == 1
    assert len(indexed) == 1
    assert indexed[utc_start].kind == "known_pt15m"
