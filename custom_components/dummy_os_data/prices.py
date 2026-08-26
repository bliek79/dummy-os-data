"""Prices shadow layer for Dummy OS Data."""

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
    GAS_VARIABLE_ADDON_ENTITY,
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
    """Fetch and normalize prices without controlling anything."""

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
        self.pt15m_count = 0
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
        state = self.hass.states.get(GAS_VARIABLE_ADDON_ENTITY)
        if state is not None and state.state not in {"unknown", "unavailable", "none", "None", ""}:
            try:
                return float(state.state)
            except ValueError:
                pass
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
            "gas_variable_addon_source": GAS_VARIABLE_ADDON_ENTITY,
            "gas_fixed_supply_per_day": self._num(CONF_GAS_FIXED_SUPPLY_PER_DAY),
            "gas_grid_per_day": self._num(CONF_GAS_GRID_PER_DAY),
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

    def _build_timeline(self, prices_payload: dict[str, Any], forecast_payload: dict[str, Any]) -> list[PricePoint]:
        """Build a rolling timeline with known prices always preferred.

        PT15M is primary. The full hourly day-ahead list is also normalized to
        quarter slots as a gap fallback. This prevents a missing/stale PT15M
        slice from making a future forecast look like the current price.
        """
        pt15_raw = prices_payload.get("prices_15m") or []
        self.has_pt15m = prices_payload.get("has_pt15m") is True and bool(pt15_raw)

        known: dict[datetime, PricePoint] = {}

        # Hourly known prices provide robust coverage for today/tomorrow.
        for item in prices_payload.get("prices") or []:
            start = self._parse_time(item.get("time") or item.get("timestamp") or item.get("start"))
            market = self._eur_mwh_to_kwh(item.get("price"))
            if start is None or market is None:
                continue
            for quarter in range(4):
                q_start = start + timedelta(minutes=quarter * QUARTER_MINUTES)
                known[q_start] = self._compose_point(q_start, market, "known_hourly_fallback", 60)

        # PT15M overrides matching hourly slots.
        pt15_count = 0
        if self.has_pt15m:
            for item in pt15_raw:
                start = self._parse_time(item.get("time") or item.get("timestamp") or item.get("start"))
                market = self._eur_mwh_to_kwh(item.get("price"))
                if start is None or market is None:
                    continue
                known[start] = self._compose_point(start, market, "known_pt15m", 15)
                pt15_count += 1
        self.pt15m_count = pt15_count
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
                if q_start in known:
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

        timeline = [
            merged[t]
            for t in sorted(merged)
            if current_quarter <= dt_util.as_local(t) < end
        ][:FORECAST_SLOTS]

        point = self._find_current_point(timeline)
        self.current_source = point.kind if point is not None else "missing"
        return timeline

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
                "variable_addon_source": GAS_VARIABLE_ADDON_ENTITY,
                "configured_supplier_component_incl_vat": self._num(CONF_GAS_SUPPLIER),
                "configured_energy_tax_incl_vat": self._num(CONF_GAS_TAX),
                "tariff_profile_id": tariff.get("profile_id"),
                "tariff_valid_from": tariff.get("valid_from"),
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
            "known_slots": self.known_count,
            "forecast_slots": self.forecast_count,
            "timeline_slots": len(self.points),
            "resolution_minutes": QUARTER_MINUTES,
            "current_price_source": self.current_source,
            "actual_source": "stroomvoorspeller_prices_15m_with_hourly_gap_fallback" if self.has_pt15m else "stroomvoorspeller_prices_hourly_fallback",
            "forecast_source": "stroomvoorspeller_forecast",
            "attribution": SOURCE_ATTRIBUTION,
            "error": self.error,
            "tariff_snapshot": self.tariff_snapshot,
        }
