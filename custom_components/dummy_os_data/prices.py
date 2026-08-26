"""Prices shadow layer for Dummy OS Data.

This module deliberately separates market data from tariff composition.
Known electricity prices and the electricity forecast are sourced from
Stroomvoorspeller. Gas actuals are read from the EnergyZero Home Assistant
entity. All tariff components are configurable through the integration options.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
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


@dataclass(slots=True)
class PricePoint:
    """One normalized 15-minute price point."""

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


class DummyOSPricesCoordinator:
    """Fetch and normalize market prices without controlling anything."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.listeners: list[callback] = []
        self._unsubs: list[Any] = []
        self.points: list[PricePoint] = []
        self.last_update: datetime | None = None
        self.source_generated_at: str | None = None
        self.forecast_generated_at: str | None = None
        self.status = "not_loaded"
        self.error: str | None = None
        self.has_pt15m = False
        self.known_count = 0
        self.forecast_count = 0

    @property
    def options(self) -> dict[str, Any]:
        return dict(self.entry.options)

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
            "gas_fixed_supply_per_day": self._num(CONF_GAS_FIXED_SUPPLY_PER_DAY),
            "gas_grid_per_day": self._num(CONF_GAS_GRID_PER_DAY),
        }

    def _num(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.entry.options.get(key, default))
        except (TypeError, ValueError):
            return default

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
        if market is None:
            return None
        # EnergyZero's HA gas market sensor is already expressed in consumer
        # EUR/m3 including VAT, while supplier/tax components are configured in
        # the same inclusive basis.
        return round(market + self._num(CONF_GAS_SUPPLIER) + self._num(CONF_GAS_TAX), 5)

    async def async_setup(self) -> None:
        await self.async_refresh()
        self._unsubs.append(async_track_time_interval(self.hass, self._scheduled_refresh, REFRESH_INTERVAL))

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

    async def async_refresh(self) -> None:
        """Refresh known and forecast price sources."""
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
        except Exception as err:  # network/data errors must not break HA setup
            self.error = f"{type(err).__name__}: {err}"
            self.status = "error"
            _LOGGER.warning("Dummy OS Prices refresh failed: %s", self.error)
        self._notify()

    def _build_timeline(self, prices_payload: dict[str, Any], forecast_payload: dict[str, Any]) -> list[PricePoint]:
        known_raw = prices_payload.get("prices_15m") or []
        self.has_pt15m = prices_payload.get("has_pt15m") is True and bool(known_raw)
        if not self.has_pt15m:
            known_raw = prices_payload.get("prices") or []

        known: dict[datetime, PricePoint] = {}
        source_resolution = 15 if self.has_pt15m else 60
        for item in known_raw:
            start = self._parse_time(item.get("time") or item.get("timestamp") or item.get("start"))
            market = self._eur_mwh_to_kwh(item.get("price"))
            if start is None or market is None:
                continue
            point = self._compose_point(start, market, "known", source_resolution)
            if source_resolution == 15:
                known[start] = point
            else:
                for quarter in range(4):
                    q_start = start + timedelta(minutes=quarter * QUARTER_MINUTES)
                    known[q_start] = self._compose_point(q_start, market, "known_hourly_fallback", 60)

        self.known_count = len(known)
        last_known = max(known) if known else None

        forecast_generated = forecast_payload.get("generated_at") or forecast_payload.get("generated")
        forecasts = forecast_payload.get("forecasts") or []
        future: dict[datetime, PricePoint] = {}
        for item in forecasts:
            start = self._parse_time(item.get("time") or item.get("timestamp") or item.get("start"))
            predicted = self._eur_mwh_to_kwh(item.get("predicted"))
            if start is None or predicted is None:
                continue
            for quarter in range(4):
                q_start = start + timedelta(minutes=quarter * QUARTER_MINUTES)
                if last_known is not None and q_start <= last_known:
                    continue
                point = self._compose_point(q_start, predicted, "forecast_hour", 60)
                point.lower_ex_vat = self._eur_mwh_to_kwh(item.get("lower"))
                point.upper_ex_vat = self._eur_mwh_to_kwh(item.get("upper"))
                point.forecast_generated_at = forecast_generated
                point.uncertainty_pct = self._safe_float(item.get("uncertainty_pct"))
                point.regime = item.get("regime")
                future[q_start] = point

        self.forecast_count = len(future)
        merged = {**future, **known}
        now_local = dt_util.as_local(dt_util.utcnow())
        current_quarter = now_local.replace(minute=(now_local.minute // 15) * 15, second=0, microsecond=0)
        end = current_quarter + timedelta(minutes=FORECAST_SLOTS * QUARTER_MINUTES)
        return [merged[t] for t in sorted(merged) if current_quarter <= dt_util.as_local(t) < end][:FORECAST_SLOTS]

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
    def current_point(self) -> PricePoint | None:
        now = dt_util.as_local(dt_util.utcnow())
        for point in self.points:
            local = dt_util.as_local(point.start)
            if local <= now < local + timedelta(minutes=15):
                return point
        return self.points[0] if self.points else None

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
            "known_slots": self.known_count,
            "forecast_slots": self.forecast_count,
            "timeline_slots": len(self.points),
            "resolution_minutes": QUARTER_MINUTES,
            "actual_source": "stroomvoorspeller_prices_15m",
            "forecast_source": "stroomvoorspeller_forecast",
            "attribution": SOURCE_ATTRIBUTION,
            "error": self.error,
            "tariff_snapshot": self.tariff_snapshot,
        }
