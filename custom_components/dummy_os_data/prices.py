"""Prices shadow layer for Dummy OS Data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any, Iterable

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ELECTRICITY_EXPORT_SUPPLIER,
    CONF_ELECTRICITY_EXPORT_TAX,
    CONF_ELECTRICITY_FIXED_SUPPLY_PER_DAY,
    CONF_ELECTRICITY_GRID_PER_DAY,
    CONF_ELECTRICITY_IMPORT_SUPPLIER,
    CONF_ELECTRICITY_IMPORT_TAX,
    CONF_ELECTRICITY_TAX_CREDIT_PER_DAY,
    CONF_GAS_FIXED_SUPPLY_PER_DAY,
    CONF_GAS_GRID_PER_DAY,
    CONF_GAS_MARKET_ENTITY,
    CONF_GAS_SUPPLIER,
    CONF_GAS_TAX,
    CONF_TARIFF_PROFILE_ID,
    CONF_TARIFF_SUPPLIER,
    CONF_TARIFF_VALID_FROM,
    CONF_VAT_PERCENT,
    DEFAULT_GAS_MARKET_ENTITY,
    FORECAST_SLOTS,
    QUARTER_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

PRICES_URL = "https://stroomvoorspeller.nl/data/prices.json"
FORECAST_URL = "https://stroomvoorspeller.nl/data/forecast.json"
SOURCE_ATTRIBUTION = "Data provided by Stroomvoorspeller.nl (CC BY 4.0)"
REFRESH_INTERVAL = timedelta(minutes=30)
SOURCE_STALE_AFTER = timedelta(hours=28)

PRICE_BUFFER_HOURS = 76
PRICE_BUFFER_SLOT_COUNT = PRICE_BUFFER_HOURS * 60 // QUARTER_MINUTES
PLANNER_HORIZON_HOURS = 72
PLANNER_PRICE_SLOT_COUNT = PLANNER_HORIZON_HOURS * 60 // QUARTER_MINUTES

_PRICE_SOURCE_PRIORITY = {
    "forecast_hour": 10,
    "known_hourly_fallback": 20,
    "known_pt15m": 30,
}


@dataclass(slots=True)
class PricePoint:
    start: datetime
    market_ex_vat: float | None
    market_incl_vat: float | None
    import_all_in: float | None
    export_all_in: float | None
    kind: str
    source_resolution_minutes: int
    lower_ex_vat: float | None = None
    upper_ex_vat: float | None = None
    forecast_generated_at: str | None = None
    uncertainty_pct: float | None = None
    regime: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "time": self.start.isoformat(),
            "market_ex_vat": self.market_ex_vat,
            "market_incl_vat": self.market_incl_vat,
            "import_all_in": self.import_all_in,
            "export_all_in": self.export_all_in,
            "kind": self.kind,
            "source_resolution_minutes": self.source_resolution_minutes,
            "lower_ex_vat": self.lower_ex_vat,
            "upper_ex_vat": self.upper_ex_vat,
            "forecast_generated_at": self.forecast_generated_at,
            "uncertainty_pct": self.uncertainty_pct,
            "regime": self.regime,
        }


def _utc_start(value: datetime) -> datetime:
    """Canonicalize an aware timestamp for exact slot indexing."""
    if value.tzinfo is None:
        raise ValueError("price timestamp must be timezone-aware")
    return value.astimezone(dt_util.UTC)


def _expected_quarter_starts(start: datetime, slot_count: int) -> list[datetime]:
    """Return exact consecutive 15-minute slot starts."""
    canonical_start = _utc_start(start)
    return [
        canonical_start + timedelta(minutes=index * QUARTER_MINUTES)
        for index in range(slot_count)
    ]


def _deduplicate_price_points(
    points: Iterable[PricePoint],
) -> tuple[dict[datetime, PricePoint], int]:
    """Index points by UTC timestamp and keep the strongest source on duplicates."""
    indexed: dict[datetime, PricePoint] = {}
    duplicate_count = 0
    for point in points:
        key = _utc_start(point.start)
        existing = indexed.get(key)
        if existing is None:
            indexed[key] = point
            continue
        duplicate_count += 1
        if _PRICE_SOURCE_PRIORITY.get(point.kind, 0) > _PRICE_SOURCE_PRIORITY.get(existing.kind, 0):
            indexed[key] = point
    return indexed, duplicate_count


def _select_exact_price_window(
    indexed: dict[datetime, PricePoint],
    *,
    start: datetime,
    slot_count: int,
) -> tuple[list[PricePoint], list[datetime]]:
    """Select exact expected timestamps; never shift around missing slots."""
    selected: list[PricePoint] = []
    missing: list[datetime] = []
    for expected_start in _expected_quarter_starts(start, slot_count):
        point = indexed.get(expected_start)
        if point is None:
            missing.append(expected_start)
        else:
            selected.append(point)
    return selected, missing


class DummyOSPricesCoordinator:
    """Fetch and normalize prices without controlling anything."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.listeners: list[callback] = []
        self._unsubs: list[Any] = []
        self.points: list[PricePoint] = []
        self._normalized_points_by_start: dict[datetime, PricePoint] = {}
        self._price_buffer_by_start: dict[datetime, PricePoint] = {}
        self._planner_points: list[PricePoint] = []
        self.price_buffer_start: datetime | None = None
        self.price_buffer_end: datetime | None = None
        self.price_buffer_valid_slots = 0
        self.price_buffer_missing_slots = PRICE_BUFFER_SLOT_COUNT
        self.price_buffer_duplicate_slots = 0
        self.price_buffer_missing_starts: list[datetime] = []
        self.planner_window_start: datetime | None = None
        self.planner_window_end: datetime | None = None
        self.planner_price_valid_slots = 0
        self.planner_price_missing_slots = PLANNER_PRICE_SLOT_COUNT
        self.planner_price_missing_starts: list[datetime] = []
        self.last_update: datetime | None = None
        self.source_generated_at: str | None = None
        self.forecast_generated_at: str | None = None
        self.status = "not_loaded"
        self.error: str | None = None
        self.has_pt15m = False
        self.pt15m_count = 0
        self.pt15m_first_time: datetime | None = None
        self.pt15m_last_time: datetime | None = None
        self.known_count = 0
        self.forecast_count = 0
        self.current_source = "missing"

    @property
    def options(self) -> dict[str, Any]:
        return dict(self.entry.options)

    def _num(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.entry.options.get(key, default))
        except (TypeError, ValueError):
            return default

    @property
    def gas_variable_addon(self) -> float:
        """Return the internally configured variable gas tariff components."""
        return self._num(CONF_GAS_SUPPLIER) + self._num(CONF_GAS_TAX)

    @property
    def tariff_snapshot(self) -> dict[str, Any]:
        opts = self.options
        return {
            "profile_id": opts.get(CONF_TARIFF_PROFILE_ID, "unconfigured"),
            "supplier": opts.get(CONF_TARIFF_SUPPLIER, "unconfigured"),
            "valid_from": opts.get(CONF_TARIFF_VALID_FROM),
            "vat_percent": self._num(CONF_VAT_PERCENT, 21.0),
            "electricity_import_supplier_incl_vat": self._num(CONF_ELECTRICITY_IMPORT_SUPPLIER),
            "electricity_import_tax_incl_vat": self._num(CONF_ELECTRICITY_IMPORT_TAX),
            "electricity_export_supplier_incl_vat": self._num(CONF_ELECTRICITY_EXPORT_SUPPLIER),
            "electricity_export_tax_incl_vat": self._num(CONF_ELECTRICITY_EXPORT_TAX),
            "electricity_fixed_supply_per_day": self._num(CONF_ELECTRICITY_FIXED_SUPPLY_PER_DAY),
            "electricity_grid_per_day": self._num(CONF_ELECTRICITY_GRID_PER_DAY),
            "electricity_tax_credit_per_day": self._num(CONF_ELECTRICITY_TAX_CREDIT_PER_DAY),
            "gas_supplier_incl_vat": self._num(CONF_GAS_SUPPLIER),
            "gas_tax_incl_vat": self._num(CONF_GAS_TAX),
            "gas_variable_addon_used": round(self.gas_variable_addon, 5),
            "gas_variable_addon_source": "dummy_os_data_options",
            "gas_fixed_supply_per_day": self._num(CONF_GAS_FIXED_SUPPLY_PER_DAY),
            "gas_grid_per_day": self._num(CONF_GAS_GRID_PER_DAY),
            "tariff_edit_surface": "Dummy OS Data Options",
        }

    @property
    def gas_market_entity(self) -> str:
        return str(self.entry.options.get(CONF_GAS_MARKET_ENTITY, DEFAULT_GAS_MARKET_ENTITY))

    @property
    def gas_market_price(self) -> float | None:
        state = self.hass.states.get(self.gas_market_entity)
        if state is None or state.state in {"unknown", "unavailable", "none", "None", ""}:
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    @property
    def gas_all_in_price(self) -> float | None:
        market = self.gas_market_price
        return None if market is None else round(market + self.gas_variable_addon, 5)

    async def async_setup(self) -> None:
        await self.async_refresh()
        self._unsubs.append(async_track_time_interval(self.hass, self._scheduled_refresh, REFRESH_INTERVAL))
        self._unsubs.append(
            async_track_state_change_event(
                self.hass,
                [self.gas_market_entity],
                self._gas_source_changed,
            )
        )

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    def async_add_listener(self, listener: callback) -> callback:
        self.listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self.listeners:
                self.listeners.remove(listener)

        return remove_listener

    @callback
    def _notify(self) -> None:
        for listener in list(self.listeners):
            listener()

    @callback
    def _scheduled_refresh(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_refresh())

    @callback
    def _gas_source_changed(self, _event: Event) -> None:
        """Republish gas states as soon as the external gas market price changes."""
        self._publish_states()
        self._notify()

    async def async_refresh(self) -> None:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(PRICES_URL, timeout=20) as response:
                response.raise_for_status()
                prices_payload = await response.json()
            async with session.get(FORECAST_URL, timeout=20) as response:
                response.raise_for_status()
                forecast_payload = await response.json()

            self.points = self._build_timeline(prices_payload, forecast_payload)
            self.last_update = dt_util.utcnow()
            self.source_generated_at = prices_payload.get("generated_at") or prices_payload.get("generated")
            self.forecast_generated_at = forecast_payload.get("generated_at") or forecast_payload.get("generated")
            self.error = None
            self.status = "ok" if self.points else "empty"
        except Exception as err:
            self.error = f"{type(err).__name__}: {err}"
            self.status = "error"
            _LOGGER.warning("Dummy OS Prices refresh failed: %s", self.error)
        self._publish_states()
        self._notify()

    @staticmethod
    def _floor_local_quarter(value: datetime) -> datetime:
        local = dt_util.as_local(value)
        return local.replace(
            minute=(local.minute // QUARTER_MINUTES) * QUARTER_MINUTES,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def _next_complete_local_hour(value: datetime) -> datetime:
        quarter = DummyOSPricesCoordinator._floor_local_quarter(value)
        if quarter.minute == 0:
            return quarter
        return (quarter + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    def _build_timeline(self, prices_payload: dict[str, Any], forecast_payload: dict[str, Any]) -> list[PricePoint]:
        """Build public 72h prices plus a timestamp-indexed 76h planner buffer."""
        pt15_raw = prices_payload.get("prices_15m") or []
        self.has_pt15m = prices_payload.get("has_pt15m") is True and bool(pt15_raw)

        known: dict[datetime, PricePoint] = {}
        for item in prices_payload.get("prices") or []:
            start = self._parse_time(item.get("time") or item.get("timestamp") or item.get("start"))
            market = self._eur_mwh_to_kwh(item.get("price"))
            if start is None or market is None:
                continue
            for quarter in range(4):
                q_start = start + timedelta(minutes=quarter * QUARTER_MINUTES)
                known[q_start] = self._compose_point(q_start, market, "known_hourly_fallback", 60)

        pt15_count = 0
        pt15_times: list[datetime] = []
        if self.has_pt15m:
            for item in pt15_raw:
                start = self._parse_time(item.get("time") or item.get("timestamp") or item.get("start"))
                market = self._eur_mwh_to_kwh(item.get("price"))
                if start is None or market is None:
                    continue
                known[start] = self._compose_point(start, market, "known_pt15m", 15)
                pt15_times.append(start)
                pt15_count += 1
        self.pt15m_count = pt15_count
        self.pt15m_first_time = min(pt15_times) if pt15_times else None
        self.pt15m_last_time = max(pt15_times) if pt15_times else None
        self.known_count = len(known)

        forecast_generated = forecast_payload.get("generated_at") or forecast_payload.get("generated")
        future: dict[datetime, PricePoint] = {}
        for item in forecast_payload.get("forecasts") or []:
            start = self._parse_time(item.get("time") or item.get("timestamp") or item.get("start"))
            predicted = self._eur_mwh_to_kwh(item.get("predicted"))
            if start is None or predicted is None:
                continue
            for quarter in range(4):
                q_start = start + timedelta(minutes=quarter * QUARTER_MINUTES)
                point = self._compose_point(q_start, predicted, "forecast_hour", 60)
                point.lower_ex_vat = self._eur_mwh_to_kwh(item.get("lower"))
                point.upper_ex_vat = self._eur_mwh_to_kwh(item.get("upper"))
                point.forecast_generated_at = forecast_generated
                point.uncertainty_pct = self._safe_float(item.get("uncertainty_pct"))
                point.regime = item.get("regime")
                future[q_start] = point

        self.forecast_count = len(future)
        indexed, duplicate_count = _deduplicate_price_points(
            [*future.values(), *known.values()]
        )
        self._normalized_points_by_start = indexed
        self.price_buffer_duplicate_slots = duplicate_count

        current_quarter = self._floor_local_quarter(dt_util.utcnow())
        buffer_starts = _expected_quarter_starts(current_quarter, PRICE_BUFFER_SLOT_COUNT)
        buffer_points, missing = _select_exact_price_window(
            indexed,
            start=current_quarter,
            slot_count=PRICE_BUFFER_SLOT_COUNT,
        )
        self.price_buffer_start = _utc_start(current_quarter)
        self.price_buffer_end = self.price_buffer_start + timedelta(hours=PRICE_BUFFER_HOURS)
        self.price_buffer_valid_slots = len(buffer_points)
        self.price_buffer_missing_slots = len(missing)
        self.price_buffer_missing_starts = missing
        self._price_buffer_by_start = {
            _utc_start(point.start): point for point in buffer_points
        }

        public_points, _ = _select_exact_price_window(
            self._price_buffer_by_start,
            start=current_quarter,
            slot_count=FORECAST_SLOTS,
        )
        point = self._find_current_point(public_points)
        self.current_source = point.kind if point is not None else "missing"

        # Keep a precomputed compatibility view. The property below recalculates
        # the exact 72h planner window on access so a 15-minute clock advance
        # between price refreshes cannot shift the consumer horizon by list slicing.
        planner_start = self._next_complete_local_hour(current_quarter)
        self._planner_points, self.planner_price_missing_starts = _select_exact_price_window(
            self._price_buffer_by_start,
            start=planner_start,
            slot_count=PLANNER_PRICE_SLOT_COUNT,
        )
        self.planner_window_start = _utc_start(planner_start)
        self.planner_window_end = self.planner_window_start + timedelta(hours=PLANNER_HORIZON_HOURS)
        self.planner_price_valid_slots = len(self._planner_points)
        self.planner_price_missing_slots = len(self.planner_price_missing_starts)

        # Keep this variable explicit for diagnostics/readability: the 76h
        # buffer is positional and may contain holes, even though only valid
        # points are stored in the dict/list views.
        _ = buffer_starts
        return public_points

    def _compose_point(self, start: datetime, market_ex_vat: float, kind: str, source_resolution: int) -> PricePoint:
        vat_factor = 1.0 + self._num(CONF_VAT_PERCENT, 21.0) / 100.0
        market_incl_vat = market_ex_vat * vat_factor
        import_all_in = market_incl_vat + self._num(CONF_ELECTRICITY_IMPORT_SUPPLIER) + self._num(CONF_ELECTRICITY_IMPORT_TAX)
        export_all_in = market_incl_vat + self._num(CONF_ELECTRICITY_EXPORT_SUPPLIER) + self._num(CONF_ELECTRICITY_EXPORT_TAX)
        return PricePoint(
            start=start,
            market_ex_vat=round(market_ex_vat, 6),
            market_incl_vat=round(market_incl_vat, 6),
            import_all_in=round(import_all_in, 6),
            export_all_in=round(export_all_in, 6),
            kind=kind,
            source_resolution_minutes=source_resolution,
        )

    @staticmethod
    def _find_current_point(points: list[PricePoint]) -> PricePoint | None:
        now = dt_util.as_local(dt_util.utcnow())
        for point in points:
            local = dt_util.as_local(point.start)
            if local <= now < local + timedelta(minutes=QUARTER_MINUTES):
                return point
        return None

    @property
    def current_point(self) -> PricePoint | None:
        return self._find_current_point(self.points)

    @property
    def planner_points(self) -> list[PricePoint]:
        """Return the exact current 72h/288-slot planner price window."""
        if not self._price_buffer_by_start:
            return []
        planner_start = self._next_complete_local_hour(dt_util.utcnow())
        selected, missing = _select_exact_price_window(
            self._price_buffer_by_start,
            start=planner_start,
            slot_count=PLANNER_PRICE_SLOT_COUNT,
        )
        self._planner_points = selected
        self.planner_price_missing_starts = missing
        self.planner_window_start = _utc_start(planner_start)
        self.planner_window_end = self.planner_window_start + timedelta(hours=PLANNER_HORIZON_HOURS)
        self.planner_price_valid_slots = len(selected)
        self.planner_price_missing_slots = len(missing)
        return list(selected)

    def _publish_states(self) -> None:
        point = self.current_point
        common = self.attributes
        point_attrs = point.as_dict() if point else {}
        self.hass.states.async_set("sensor.do_prices_status", self.status, common)
        self.hass.states.async_set(
            "sensor.do_prices_market_current",
            point.market_incl_vat if point else None,
            {**common, **point_attrs, "unit_of_measurement": "EUR/kWh", "price_basis": "market_incl_vat"},
        )
        self.hass.states.async_set(
            "sensor.do_prices_import_current",
            point.import_all_in if point else None,
            {**common, **point_attrs, "unit_of_measurement": "EUR/kWh", "price_basis": "marginal_import_all_in"},
        )
        self.hass.states.async_set(
            "sensor.do_prices_export_current",
            point.export_all_in if point else None,
            {**common, **point_attrs, "unit_of_measurement": "EUR/kWh", "price_basis": "marginal_export_all_in"},
        )
        self.hass.states.async_set(
            "sensor.do_prices_timeline",
            len(self.points),
            {**common, "point_format": "dict", "recorder_recommendation": "exclude this timeline sensor from Recorder", "points": [p.as_dict() for p in self.points]},
        )
        tariff = self.tariff_snapshot
        self.hass.states.async_set(
            "sensor.do_prices_tariff_profile",
            tariff.get("profile_id") or "unconfigured",
            {**tariff, "immutable_history_rule": True, "future_profile_changes_do_not_reprice_history": True},
        )
        gas_market = self.gas_market_price
        self.hass.states.async_set(
            "sensor.do_prices_gas_market",
            gas_market,
            {"unit_of_measurement": "EUR/m3", "source": "EnergyZero", "source_entity": self.gas_market_entity, "resolution": "daily", "internal_resolution_minutes": 15},
        )
        self.hass.states.async_set(
            "sensor.do_prices_gas_all_in",
            self.gas_all_in_price,
            {
                "unit_of_measurement": "EUR/m3",
                "source": "EnergyZero + Dummy OS tariff profile",
                "market_price_incl_vat": gas_market,
                "variable_addon_incl_vat": round(self.gas_variable_addon, 5),
                "variable_addon_source": "dummy_os_data_options",
                "configured_supplier_component_incl_vat": self._num(CONF_GAS_SUPPLIER),
                "configured_energy_tax_incl_vat": self._num(CONF_GAS_TAX),
                "gas_fixed_supply_per_day": self._num(CONF_GAS_FIXED_SUPPLY_PER_DAY),
                "gas_grid_per_day": self._num(CONF_GAS_GRID_PER_DAY),
                "tariff_profile_id": tariff.get("profile_id"),
                "tariff_valid_from": tariff.get("valid_from"),
                "tariff_edit_surface": "Dummy OS Data Options",
            },
        )

    @staticmethod
    def _eur_mwh_to_kwh(value: Any) -> float | None:
        v = DummyOSPricesCoordinator._safe_float(value)
        return v / 1000.0 if v is not None else None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = dt_util.parse_datetime(str(value))
        except (TypeError, ValueError):
            return None
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)
        return parsed

    @property
    def freshness(self) -> str:
        if self.last_update is None:
            return "not_loaded"
        age = dt_util.utcnow() - self.last_update
        return "stale" if age > SOURCE_STALE_AFTER else "fresh"

    @property
    def attributes(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "freshness": self.freshness,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "prices_generated_at": self.source_generated_at,
            "forecast_generated_at": self.forecast_generated_at,
            "has_pt15m": self.has_pt15m,
            "pt15m_slots": self.pt15m_count,
            "pt15m_first_time": self.pt15m_first_time.isoformat() if self.pt15m_first_time else None,
            "pt15m_last_time": self.pt15m_last_time.isoformat() if self.pt15m_last_time else None,
            "known_slots": self.known_count,
            "forecast_slots": self.forecast_count,
            "timeline_slots": len(self.points),
            "resolution_minutes": QUARTER_MINUTES,
            "price_buffer_hours": PRICE_BUFFER_HOURS,
            "price_buffer_expected_slots": PRICE_BUFFER_SLOT_COUNT,
            "price_buffer_valid_slots": self.price_buffer_valid_slots,
            "price_buffer_missing_slots": self.price_buffer_missing_slots,
            "price_buffer_duplicate_slots": self.price_buffer_duplicate_slots,
            "price_buffer_start": self.price_buffer_start.isoformat() if self.price_buffer_start else None,
            "price_buffer_end": self.price_buffer_end.isoformat() if self.price_buffer_end else None,
            "price_buffer_first_missing": self.price_buffer_missing_starts[0].isoformat() if self.price_buffer_missing_starts else None,
            "price_buffer_last_missing": self.price_buffer_missing_starts[-1].isoformat() if self.price_buffer_missing_starts else None,
            "planner_price_expected_slots": PLANNER_PRICE_SLOT_COUNT,
            "planner_price_valid_slots": self.planner_price_valid_slots,
            "planner_price_missing_slots": self.planner_price_missing_slots,
            "planner_window_start": self.planner_window_start.isoformat() if self.planner_window_start else None,
            "planner_window_end": self.planner_window_end.isoformat() if self.planner_window_end else None,
            "planner_price_first_missing": self.planner_price_missing_starts[0].isoformat() if self.planner_price_missing_starts else None,
            "planner_price_last_missing": self.planner_price_missing_starts[-1].isoformat() if self.planner_price_missing_starts else None,
            "current_price_source": self.current_source,
            "actual_source": "stroomvoorspeller_prices_15m_with_hourly_gap_fallback" if self.has_pt15m else "stroomvoorspeller_prices_hourly_fallback",
            "forecast_source": "stroomvoorspeller_forecast",
            "attribution": SOURCE_ATTRIBUTION,
            "error": self.error,
            "tariff_snapshot": self.tariff_snapshot,
        }
