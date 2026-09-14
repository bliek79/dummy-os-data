from __future__ import annotations

from datetime import datetime, timedelta
from copy import deepcopy
import logging
from typing import Any, Iterable

from aiohttp import ClientError, ClientTimeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .plan_store import AnkerEmsPlanStore
from .scheduler import AnkerEmsScheduler
from .safety_guard import AnkerEmsSafetyGuard
from .prestart_validator import AnkerEmsPreStartValidator
from .action_controller import AnkerEmsActionController
from .physical_test import AnkerEmsPhysicalTestController
from .execution import AnkerEmsExecutionController
from .source_monitor import AnkerEmsSourceMonitor
from .home_history import AnkerEmsHomeHistory
from .home_forecast import build_internal_home_forecast
from .energy_need import build_energy_need_analysis
from .planner_preview import build_planner_preview
from .planner_72h import build_72h_plan_preview
from .planner_action_bridge import build_planner_action_bridge

from .const import (
    NAME,
    CONF_SIMULATION_MODE,
    CONF_ELECTRICAL_PROFILE,
    CONF_MAX_CHARGE_POWER_W,
    CONF_MAX_DISCHARGE_POWER_W,
    DEFAULT_ELECTRICAL_PROFILE,
    DEFAULT_SHARED_MAX_POWER_W,
    ELECTRICAL_PROFILE_SHARED,
    ABSOLUTE_MAX_CHARGE_POWER_W,
    ABSOLUTE_MAX_DISCHARGE_POWER_W,
    CONF_SOC_ENTITY,
    CONF_DEVICE_STATUS_ENTITY,
    CONF_CHARGE_POWER_ENTITY,
    CONF_DISCHARGE_POWER_ENTITY,
    CONF_GRID_IMPORT_POWER_ENTITY,
    CONF_GRID_EXPORT_POWER_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
    CONF_OPERATING_MODE_ENTITY,
    CONF_ACTION_DIRECTION_ENTITY,
    CONF_POWER_SETPOINT_ENTITY,
    CONF_MARKET_PRICE_ARCHITECTURE_ENABLED,
    CONF_MARKET_PRICE_ENTITY,
    CONF_IMPORT_MARKUP_PER_KWH,
    CONF_EXPORT_MARKUP_PER_KWH,
    CONF_TARIFF_RESOLUTION,
    TARIFF_RESOLUTION_HOURLY,
    TARIFF_RESOLUTION_QUARTER_HOURLY,
    DEFAULT_TARIFF_RESOLUTION,
    DEFAULT_MARKET_PRICE_ENTITY,
    DEFAULT_IMPORT_MARKUP_PER_KWH,
    DEFAULT_EXPORT_MARKUP_PER_KWH,
    CONF_KNOWN_PRICE_ENTITY,
    CONF_FORECAST_PRICE_ENTITY,
    CONF_HOME_FORECAST_ENTITY,
    CONF_SOLAR_TODAY_ENTITY,
    CONF_SOLAR_TOMORROW_ENTITY,
    CONF_SOLAR_DAY3_ENTITY,
    DEFAULT_KNOWN_PRICE_ENTITY,
    DEFAULT_FORECAST_PRICE_ENTITY,
    DEFAULT_HOME_FORECAST_ENTITY,
    DEFAULT_SOLAR_TODAY_ENTITY,
    DEFAULT_SOLAR_TOMORROW_ENTITY,
    DEFAULT_SOLAR_DAY3_ENTITY,
    CONF_MONITOR_ENERGYZERO_ENTITY,
    CONF_MONITOR_STROOMVOORSPELLER_ENTITY,
    CONF_MONITOR_SOLCAST_API_ENTITY,
    DEFAULT_MONITOR_ENERGYZERO_ENTITY,
    DEFAULT_MONITOR_STROOMVOORSPELLER_ENTITY,
    DEFAULT_MONITOR_SOLCAST_API_ENTITY,
    FORECAST_HORIZON_HOURS,
    DEFAULT_BATTERY_CAPACITY_KWH,
    CONF_SOFTWARE_RESERVE_PERCENT,
    DEFAULT_SOFTWARE_RESERVE_PERCENT,
    CONF_CHARGE_EFFICIENCY_PERCENT,
    CONF_DISCHARGE_EFFICIENCY_PERCENT,
    CONF_MINIMUM_TRADE_MARGIN,
    DEFAULT_CHARGE_EFFICIENCY_PERCENT,
    DEFAULT_DISCHARGE_EFFICIENCY_PERCENT,
    DEFAULT_MINIMUM_TRADE_MARGIN,
)

_LOGGER = logging.getLogger(__name__)

_INVALID_STATES = {None, "unknown", "unavailable", "none", ""}


def _as_float(value: Any) -> float | None:
    if value in _INVALID_STATES:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return parsed.astimezone(dt_util.UTC)


def _hour_key(value: Any) -> datetime | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.replace(minute=0, second=0, microsecond=0)


class AnkerEmsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        plan_store: AnkerEmsPlanStore,
        scheduler: AnkerEmsScheduler,
        safety_guard: AnkerEmsSafetyGuard,
        action_controller: AnkerEmsActionController,
        physical_test: AnkerEmsPhysicalTestController,
        execution: AnkerEmsExecutionController,
        source_monitor: AnkerEmsSourceMonitor,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=NAME,
            update_interval=timedelta(seconds=10),
            config_entry=entry,
        )
        self.entry = entry
        self.plan_store = plan_store
        self.scheduler = scheduler
        self.safety_guard = safety_guard
        self.action_controller = action_controller
        self.physical_test = physical_test
        self.execution = execution
        self.source_monitor = source_monitor
        self.home_history = AnkerEmsHomeHistory(hass, entry.entry_id)
        self._cached_internal_home_forecast: dict[str, Any] | None = None
        self._internal_home_forecast_history_points = -1
        self._cached_72h_plan: dict[str, Any] | None = None
        self._last_plan_source_token: str | None = None
        self._last_plan_refresh_at: datetime | None = None
        self._last_plan_refresh_reason: str | None = None
        self._last_plan_periodic_bucket: str | None = None
        self._last_plan_start_critical_key: str | None = None
        self._last_forecast_ready: bool | None = None
        self._plan_refresh_count_date = dt_util.now().date()
        self._plan_refresh_count_today = 0
        self._direct_price_forecast_payload: dict[str, Any] | None = None
        self._direct_price_forecast_last_fetch_at: datetime | None = None
        self._direct_price_forecast_last_success_at: datetime | None = None
        self._direct_price_forecast_error: str | None = None
        # Alpha51: explicit user arm. Default is fail-safe OFF on every fresh install.
        # The switch platform restores the user's last state after startup.
        self._auto_execution_armed = False

    @property
    def auto_execution_armed(self) -> bool:
        return self._auto_execution_armed

    async def async_set_auto_execution_armed(self, armed: bool) -> None:
        self._auto_execution_armed = bool(armed)
        await self.async_request_refresh()

    def _automatic_execution_shadow(self, data: dict[str, Any]) -> dict[str, Any]:
        """Build the final non-actuating command that alpha52 would execute.

        This is the authoritative shadow gate used to prove the whole automatic
        chain before any non-zero automatic battery command is enabled.
        """
        slot = data.get("scheduler_selected_slot")
        slots = data.get("scheduler_slots", {}) or {}
        detail = slots.get(slot) or slots.get(str(slot)) or {}
        origin = str(detail.get("origin") or "manual")
        purpose = str(detail.get("purpose") or "")
        blockers: list[str] = []
        warnings: list[str] = []

        automatic_selected = bool(
            slot is not None
            and data.get("scheduler_ready")
            and origin == "automatic_72h_planner"
        )
        if not automatic_selected:
            blockers.append("no_automatic_action_selected")
        if data.get("auto_prestart_safe") is not True:
            blockers.append("prestart_not_safe")
        if data.get("auto_safety_handoff_safe") is not True:
            blockers.append("safety_handoff_not_safe")
        if data.get("auto_execution_handoff_ready") is not True:
            blockers.append("execution_handoff_not_ready")
        if data.get("auto_final_revalidation_safe") is not True:
            blockers.append("final_revalidation_not_safe")
        if data.get("auto_mode_switch_preview_ready") is not True:
            blockers.append("mode_switch_preview_not_ready")
        selected_action = str(detail.get("action") or "")
        safety_recovery_action = bool(
            selected_action == "laden"
            and purpose in {"veiligheidsladen", "veiligheidsladen+handelsladen"}
        )
        if (
            data.get("auto_plan_72h_execution_buffer_safe") is not True
            and not safety_recovery_action
        ):
            blockers.append("execution_buffer_unsafe")
        if data.get("forecast_ready") is not True:
            blockers.append("forecast_not_ready")
        if not data.get("control_path_configured"):
            blockers.append("control_path_not_configured")
        if data.get("physical_test_active"):
            blockers.append("physical_test_active")
        if data.get("execution_active"):
            blockers.append("execution_already_active")

        # Manual actions always win. A selected manual plan, or a running manual
        # execution, must keep automatic execution out of the control path.
        manual_override = bool(
            (slot is not None and data.get("scheduler_ready") and origin != "automatic_72h_planner")
            or (
                data.get("execution_active")
                and str(data.get("execution_origin") or "manual") != "automatic_72h_planner"
            )
        )
        if manual_override:
            blockers.append("manual_override_active")

        # Trading may be planned using forecast prices, but physical price-trade
        # execution is allowed only when every source hour has a known day-ahead price.
        is_trade = purpose in {"handelsladen", "veiligheidsladen+handelsladen", "handel_ontladen"}
        all_prices_known = bool(detail.get("all_prices_known"))
        if is_trade and not all_prices_known:
            blockers.append("trade_requires_known_prices")
        elif not all_prices_known:
            warnings.append("forecast_price_used_for_non_trade_planning")

        readiness = self.execution.control_path_readiness()
        if readiness.get("ready") is not True:
            blockers.append("control_path_not_stable")

        # De-duplicate while preserving the first, most useful order.
        blockers = list(dict.fromkeys(blockers))
        warnings = list(dict.fromkeys(warnings))
        technical_ready = not blockers
        armed = bool(self._auto_execution_armed)
        execution_permitted = bool(automatic_selected and technical_ready and armed)
        if not automatic_selected:
            status = "idle"
        elif not technical_ready:
            status = "blocked"
        elif not armed:
            status = "ready_disarmed"
        else:
            status = "armed_live_ready"

        return {
            "auto_shadow_enabled": True,
            "auto_shadow_status": status,
            "auto_shadow_technical_ready": technical_ready,
            "auto_shadow_armed": armed,
            "auto_shadow_execution_permitted": execution_permitted,
            "auto_shadow_physical_control": execution_permitted,
            "auto_shadow_selected_slot": slot if automatic_selected else None,
            "auto_shadow_planner_identity": detail.get("planner_identity") if automatic_selected else None,
            "auto_shadow_action": detail.get("action") if automatic_selected else None,
            "auto_shadow_purpose": purpose or None,
            "auto_shadow_power_w": detail.get("power_w") if automatic_selected else None,
            "auto_shadow_target_soc": detail.get("target_soc") if automatic_selected else None,
            "auto_shadow_max_runtime_h": detail.get("max_runtime_h") if automatic_selected else None,
            "auto_shadow_start_time": detail.get("start_time") if automatic_selected else None,
            "auto_shadow_price_sources": list(detail.get("price_sources") or []),
            "auto_shadow_all_prices_known": all_prices_known,
            "auto_shadow_manual_override_active": manual_override,
            "auto_shadow_blockers": blockers,
            "auto_shadow_warnings": warnings,
            "auto_shadow_control_path_ready": bool(readiness.get("ready")),
            "auto_shadow_control_path_reason": readiness.get("reason"),
            "auto_shadow_control_path_stable_seconds": readiness.get("stable_seconds", 0),
            "auto_shadow_pre_mode_ready": bool(readiness.get("pre_mode_ready")),
            "auto_shadow_pre_mode_reason": readiness.get("pre_mode_reason"),
            "auto_shadow_pre_mode_stable_seconds": readiness.get("pre_mode_stable_seconds", 0),
            "auto_shadow_post_mode_ready": bool(readiness.get("post_mode_ready")),
            "auto_shadow_post_mode_reason": readiness.get("post_mode_reason"),
            "auto_shadow_post_mode_stable_seconds": readiness.get("post_mode_stable_seconds", 0),
            "auto_shadow_post_mode_required": bool(readiness.get("post_mode_required")),
            "auto_shadow_control_entities": readiness.get("entities", {}),
            "auto_shadow_note": (
                "Alpha54: een gewapende, volledig veilige automatische planneractie mag fysiek worden uitgevoerd. "
                "Two-stage control-path readiness, post-mode revalidatie en fail-safe stop blijven verplicht."
            ),
        }

    @staticmethod
    def _planner_source_token(data: dict[str, Any]) -> str:
        """Return a stable token for content changes relevant to the 72h planner."""
        sources = data.get("source_monitor_sources") or {}
        relevant = (
            ("solcast_forecast", "stroomvoorspeller", "home_forecast")
            if data.get("price_architecture_enabled")
            else ("solcast_forecast", "stroomvoorspeller", "energyzero_prices", "price_forecast", "home_forecast")
        )
        base = "|".join(
            f"{name}:{(sources.get(name) or {}).get('last_content_change') or ''}"
            for name in relevant
        )
        direct_generated = data.get("price_architecture_direct_forecast_generated_at") or ""
        direct_hours = data.get("price_architecture_direct_forecast_hours") or 0
        return f"{base}|direct_stroomvoorspeller:{direct_generated}:{direct_hours}"

    def _planner_start_critical_key(self, scheduler_data: dict[str, Any]) -> str | None:
        """Return a one-shot key when an automatic plan enters a start-critical phase."""
        slots = scheduler_data.get("scheduler_slots") or {}
        selected_slot = scheduler_data.get("scheduler_selected_slot")
        if isinstance(selected_slot, int):
            detail = slots.get(selected_slot) or slots.get(str(selected_slot)) or {}
            if detail.get("origin") == "automatic_72h_planner":
                identity = detail.get("planner_identity") or f"slot_{selected_slot}"
                return f"due:{identity}"

        next_slot = scheduler_data.get("scheduler_next_future_slot")
        next_start_raw = scheduler_data.get("scheduler_next_future_start")
        if not isinstance(next_slot, int) or not next_start_raw:
            return None
        detail = slots.get(next_slot) or slots.get(str(next_slot)) or {}
        if detail.get("origin") != "automatic_72h_planner":
            return None
        next_start = _parse_datetime(next_start_raw)
        if next_start is None:
            return None
        now_utc = dt_util.utcnow().astimezone(dt_util.UTC)
        minutes = (next_start - now_utc).total_seconds() / 60.0
        if 0.0 < minutes <= 15.0:
            identity = detail.get("planner_identity") or f"slot_{next_slot}"
            return f"near:{identity}"
        return None

    def _should_refresh_72h_plan(
        self,
        data: dict[str, Any],
        scheduler_data: dict[str, Any],
    ) -> tuple[bool, str, str, str | None]:
        """Apply alpha40.2 planner refresh policy.

        The coordinator itself remains fast for live safety/execution state, while
        the expensive 72-hour planner is refreshed at most once per local hour
        between 05:00 and 22:00, plus immediate event-driven exceptions.
        """
        now_local = dt_util.now()
        if self._plan_refresh_count_date != now_local.date():
            self._plan_refresh_count_date = now_local.date()
            self._plan_refresh_count_today = 0
        # Direct Stroomvoorspeller cache belongs to the coordinator lifetime.
        # Do not reset it during every Plan72 refresh decision: doing so bypassed
        # the 30-minute fetch guard and caused a request storm when the provider
        # returned HTTP 403.

        source_token = self._planner_source_token(data)
        hour_bucket = now_local.strftime("%Y-%m-%dT%H")
        start_key = self._planner_start_critical_key(scheduler_data)
        forecast_ready = bool(data.get("forecast_ready"))

        # Alpha64: make SOC recovery part of the coordinator refresh policy itself.
        # The first startup pass can cache waiting_for_soc before the configured
        # SOC entity has restored. As soon as a later coordinator cycle sees a
        # numeric SOC, force exactly the Plan72 rebuild that the cached state needs.
        # The direct Stroomvoorspeller cache remains untouched.
        cached_plan = self._cached_72h_plan or {}
        cached_waiting_for_soc = bool(
            str(cached_plan.get("auto_plan_72h_status") or "") == "waiting_for_soc"
            or (
                cached_plan.get("auto_plan_72h_valid") is not True
                and int(cached_plan.get("auto_plan_72h_count") or 0) == 0
                and str(cached_plan.get("auto_plan_72h_reason") or "") == "Geen geldige SOC beschikbaar"
            )
        )
        if cached_waiting_for_soc and _as_float(data.get("soc")) is not None:
            return True, "soc_recovered_after_startup", source_token, start_key

        if self._cached_72h_plan is None:
            return True, "startup", source_token, start_key

        if source_token != self._last_plan_source_token:
            return True, "source_content_changed", source_token, start_key

        if self._last_forecast_ready is False and forecast_ready:
            return True, "forecast_recovered", source_token, start_key

        if start_key is not None and start_key != self._last_plan_start_critical_key:
            return True, "start_critical", source_token, start_key

        if 5 <= now_local.hour <= 22 and hour_bucket != self._last_plan_periodic_bucket:
            return True, "hourly_window", source_token, start_key

        return False, "cached", source_token, start_key

    def _planner_refresh_metadata(self, reason: str) -> dict[str, Any]:
        return {
            "auto_plan_72h_refresh_policy": "hourly_05_22_plus_events",
            "auto_plan_72h_refresh_cached": reason == "cached",
            "auto_plan_72h_refresh_reason": reason,
            "auto_plan_72h_last_refreshed_at": (
                self._last_plan_refresh_at.isoformat()
                if self._last_plan_refresh_at is not None
                else None
            ),
            "auto_plan_72h_refresh_count_today": self._plan_refresh_count_today,
            "auto_plan_72h_periodic_window": "05:00-22:00",
            "auto_plan_72h_periodic_max_per_hour": 1,
            "auto_plan_72h_event_refresh_enabled": True,
        }

    @property
    def simulation_mode(self) -> bool:
        return bool(self.entry.data.get(CONF_SIMULATION_MODE, True))

    @property
    def electrical_profile(self) -> str:
        return str(self.entry.options.get(CONF_ELECTRICAL_PROFILE, self.entry.data.get(CONF_ELECTRICAL_PROFILE, DEFAULT_ELECTRICAL_PROFILE)))

    @property
    def max_charge_power_w(self) -> int:
        fallback = DEFAULT_SHARED_MAX_POWER_W if self.electrical_profile == ELECTRICAL_PROFILE_SHARED else ABSOLUTE_MAX_CHARGE_POWER_W
        raw = self.entry.options.get(CONF_MAX_CHARGE_POWER_W, self.entry.data.get(CONF_MAX_CHARGE_POWER_W, fallback))
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            value = fallback
        profile_cap = DEFAULT_SHARED_MAX_POWER_W if self.electrical_profile == ELECTRICAL_PROFILE_SHARED else ABSOLUTE_MAX_CHARGE_POWER_W
        return max(100, min(profile_cap, value))

    @property
    def max_discharge_power_w(self) -> int:
        fallback = DEFAULT_SHARED_MAX_POWER_W if self.electrical_profile == ELECTRICAL_PROFILE_SHARED else ABSOLUTE_MAX_DISCHARGE_POWER_W
        raw = self.entry.options.get(CONF_MAX_DISCHARGE_POWER_W, self.entry.data.get(CONF_MAX_DISCHARGE_POWER_W, fallback))
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            value = fallback
        profile_cap = DEFAULT_SHARED_MAX_POWER_W if self.electrical_profile == ELECTRICAL_PROFILE_SHARED else ABSOLUTE_MAX_DISCHARGE_POWER_W
        return max(100, min(profile_cap, value))

    def _entity_id(self, key: str, default: str | None = None) -> str | None:
        return self.entry.options.get(key) or self.entry.data.get(key) or default


    @property
    def control_entity_ids(self) -> dict[str, str | None]:
        return {
            "operating_mode": self._entity_id(CONF_OPERATING_MODE_ENTITY),
            "action_direction": self._entity_id(CONF_ACTION_DIRECTION_ENTITY),
            "power_setpoint": self._entity_id(CONF_POWER_SETPOINT_ENTITY),
        }

    def _state_by_entity_id(self, entity_id: str | None) -> Any:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        return None if state is None else state.state

    def _state(self, key: str) -> Any:
        return self._state_by_entity_id(self._entity_id(key))

    def _number(self, key: str) -> float | None:
        return _as_float(self._state(key))

    def _home_power_snapshot(self) -> dict[str, Any]:
        """Build canonical home power from the five directional power sources.

        All configured source sensors are expected to expose positive power in W
        for their named direction. The EMS home load is therefore:
        solar + grid import + battery discharge - grid export - battery charge.
        The raw result is retained for diagnostics; the canonical load is clamped
        at zero to absorb tiny asynchronous meter timing differences.
        """
        source_keys = {
            "grid_import": CONF_GRID_IMPORT_POWER_ENTITY,
            "grid_export": CONF_GRID_EXPORT_POWER_ENTITY,
            "solar": CONF_SOLAR_POWER_ENTITY,
            "battery_charge": CONF_CHARGE_POWER_ENTITY,
            "battery_discharge": CONF_DISCHARGE_POWER_ENTITY,
        }
        entities = {name: self._entity_id(key) for name, key in source_keys.items()}
        values = {name: self._number(key) for name, key in source_keys.items()}
        missing = [name for name in source_keys if not entities.get(name) or values.get(name) is None]
        if missing:
            return {
                "home_power_valid": False,
                "home_power_status": "waiting_for_sources",
                "home_power_w": None,
                "home_power_raw_w": None,
                "home_power_missing_sources": missing,
                "home_power_source_entities": entities,
                "home_power_source_values_w": values,
                "home_power_formula": "solar + grid_import + battery_discharge - grid_export - battery_charge",
            }

        raw = (
            float(values["solar"])
            + float(values["grid_import"])
            + float(values["battery_discharge"])
            - float(values["grid_export"])
            - float(values["battery_charge"])
        )
        return {
            "home_power_valid": True,
            "home_power_status": "ready",
            "home_power_w": round(max(0.0, raw), 3),
            "home_power_raw_w": round(raw, 3),
            "home_power_missing_sources": [],
            "home_power_source_entities": entities,
            "home_power_source_values_w": values,
            "home_power_formula": "solar + grid_import + battery_discharge - grid_export - battery_charge",
        }

    def _attributes(self, entity_id: str | None) -> dict[str, Any]:
        if not entity_id:
            return {}
        state = self.hass.states.get(entity_id)
        return {} if state is None else dict(state.attributes)

    def _rows(self, entity_id: str | None, attribute: str) -> list[dict[str, Any]]:
        raw = self._attributes(entity_id).get(attribute, [])
        if not isinstance(raw, list):
            return []
        return [row for row in raw if isinstance(row, dict)]

    def _price_architecture_settings(self) -> dict[str, Any]:
        options = self.entry.options
        return {
            "enabled": bool(options.get(CONF_MARKET_PRICE_ARCHITECTURE_ENABLED, False)),
            "market_entity": self._entity_id(CONF_MARKET_PRICE_ENTITY, DEFAULT_MARKET_PRICE_ENTITY) or "",
            "import_markup": _as_float(options.get(CONF_IMPORT_MARKUP_PER_KWH, DEFAULT_IMPORT_MARKUP_PER_KWH)) or 0.0,
            "export_markup": _as_float(options.get(CONF_EXPORT_MARKUP_PER_KWH, DEFAULT_EXPORT_MARKUP_PER_KWH)) or 0.0,
            "resolution": str(options.get(CONF_TARIFF_RESOLUTION, DEFAULT_TARIFF_RESOLUTION)),
        }

    @staticmethod
    def _iter_market_rows(raw: Any, source_kind: str) -> list[dict[str, Any]]:
        """Flatten common Stroomvoorspeller today/tomorrow/forecast payload shapes."""
        rows: list[dict[str, Any]] = []
        time_keys = ("time", "timestamp", "datetime", "start", "period_start", "periodStart")
        price_keys = ("market", "market_price", "marketPrice", "market_predicted", "price", "value", "predicted")

        def walk(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return
            time_value = _first(value, time_keys)
            price_value = _as_float(_first(value, price_keys))
            if time_value is not None and price_value is not None:
                rows.append({"time": time_value, "market_price": price_value, "source_kind": source_kind})
            for key, item in value.items():
                if key in time_keys or key in price_keys:
                    continue
                if isinstance(item, (list, dict)):
                    walk(item)
                elif isinstance(item, (int, float, str)):
                    parsed_time = _parse_datetime(key)
                    parsed_price = _as_float(item)
                    if parsed_time is not None and parsed_price is not None:
                        rows.append({"time": key, "market_price": parsed_price, "source_kind": source_kind})

        walk(raw)
        return rows

    def _direct_price_forecast_rows(self) -> list[dict[str, Any]]:
        """Return direct hourly Stroomvoorspeller forecast rows in EUR/kWh."""
        payload = self._direct_price_forecast_payload or {}
        raw_rows = payload.get("forecasts")
        if not isinstance(raw_rows, list):
            return []

        source_unit = str(payload.get("unit") or payload.get("source_unit") or "EUR/MWh").lower()
        divisor = 1000.0 if "mwh" in source_unit else 1.0
        rows: list[dict[str, Any]] = []
        for item in raw_rows:
            if not isinstance(item, dict):
                continue
            time_value = item.get("time")
            predicted = _as_float(item.get("predicted"))
            if time_value is None or predicted is None:
                continue
            rows.append(
                {
                    "time": time_value,
                    "market_price": predicted / divisor,
                    "source_kind": "forecast",
                    "forecast_granularity": "direct_hourly",
                }
            )
        return rows

    async def _async_refresh_direct_price_forecast(self) -> None:
        """Fetch the native 7-day Stroomvoorspeller hourly forecast with a 30 min cache."""
        now_utc = dt_util.utcnow().astimezone(dt_util.UTC)
        if (
            self._direct_price_forecast_last_fetch_at is not None
            and (now_utc - self._direct_price_forecast_last_fetch_at) < timedelta(minutes=30)
        ):
            return

        self._direct_price_forecast_last_fetch_at = now_utc
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                "https://stroomvoorspeller.nl/data/forecast.json",
                timeout=ClientTimeout(total=20),
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
            if not isinstance(payload, dict) or not isinstance(payload.get("forecasts"), list):
                raise ValueError("Stroomvoorspeller forecast payload bevat geen forecasts-lijst")
            if not payload.get("forecasts"):
                raise ValueError("Stroomvoorspeller forecast payload is leeg")
            self._direct_price_forecast_payload = payload
            self._direct_price_forecast_last_success_at = now_utc
            self._direct_price_forecast_error = None
        except (ClientError, TimeoutError, ValueError, TypeError) as err:
            self._direct_price_forecast_error = str(err)
            _LOGGER.warning("Directe Stroomvoorspeller forecast ophalen mislukt: %s", err)

    def _stroomvoorspeller_market_rows(self, entity_id: str) -> list[dict[str, Any]]:
        """Return known Stroomvoorspeller prices plus its direct hourly forecast.

        Exact ``today``/``tomorrow`` rows from the Home Assistant Stroomvoorspeller
        entity remain authoritative. Future hours come directly from
        stroomvoorspeller.nl/data/forecast.json, so the integration no longer
        depends on package sensor ``sensor.forecast_prices_all_in_data``. The
        daily model average is retained only as a last-resort fallback when the
        direct hourly feed is temporarily unavailable.
        """
        attrs = self._attributes(entity_id)
        rows: list[dict[str, Any]] = []
        rows.extend(self._iter_market_rows(attrs.get("today"), "known"))
        rows.extend(self._iter_market_rows(attrs.get("tomorrow"), "known"))

        forecast = attrs.get("forecast")
        embedded_forecast_rows = self._iter_market_rows(forecast, "forecast")
        direct_forecast_rows = self._direct_price_forecast_rows()
        hourly_forecast_rows = direct_forecast_rows or embedded_forecast_rows
        rows.extend(hourly_forecast_rows)
        forecast_hours = {
            hour
            for row in hourly_forecast_rows
            if (hour := _hour_key(row.get("time"))) is not None
        }

        if isinstance(forecast, dict):
            days = forecast.get("days")
            if isinstance(days, list):
                for day in days:
                    if not isinstance(day, dict):
                        continue
                    date_value = day.get("date")
                    market_estimate = _as_float(
                        _first(
                            day,
                            (
                                "average_market_estimate",
                                "market_estimate",
                                "average_market",
                                "market",
                                "predicted",
                            ),
                        )
                    )
                    if not date_value or market_estimate is None:
                        continue
                    try:
                        local_midnight = datetime.fromisoformat(str(date_value)).replace(
                            tzinfo=dt_util.DEFAULT_TIME_ZONE
                        )
                    except ValueError:
                        continue
                    for hour_offset in range(24):
                        local_hour = local_midnight + timedelta(hours=hour_offset)
                        utc_hour = local_hour.astimezone(dt_util.UTC).replace(
                            minute=0, second=0, microsecond=0
                        )
                        if utc_hour in forecast_hours:
                            continue
                        rows.append(
                            {
                                "time": local_hour.isoformat(),
                                "market_price": market_estimate,
                                "source_kind": "forecast",
                                "forecast_granularity": "daily_fallback",
                            }
                        )

        return rows

    @staticmethod
    def _aggregate_home_rows_hourly(
        rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Aggregate home-consumption forecast energy to hourly planner slots.

        Forecast values are energy per source interval (kWh). Multiple sub-hourly
        points in the same hour therefore have to be summed, never overwritten
        and never averaged. Exact duplicate timestamps are de-duplicated first.
        A native hourly source remains unchanged because it contributes one point.
        """
        per_timestamp: dict[datetime, float] = {}
        for row in rows:
            stamp = _parse_datetime(_first(row, ("time", "timestamp", "datetime", "start")))
            value = _as_float(_first(row, ("predicted", "value", "consumption", "kwh")))
            if stamp is None or value is None:
                continue
            per_timestamp[stamp] = max(0.0, value)

        grouped: dict[datetime, list[tuple[datetime, float]]] = {}
        for stamp, value in per_timestamp.items():
            hour = stamp.replace(minute=0, second=0, microsecond=0)
            grouped.setdefault(hour, []).append((stamp, value))

        aggregated: list[dict[str, Any]] = []
        subhourly_hours = 0
        max_points_per_hour = 0
        for hour in sorted(grouped):
            points = sorted(grouped[hour], key=lambda item: item[0])
            point_count = len(points)
            max_points_per_hour = max(max_points_per_hour, point_count)
            if point_count > 1:
                subhourly_hours += 1
            aggregated.append(
                {
                    "time": hour.isoformat(),
                    "home_consumption_kwh": sum(value for _stamp, value in points),
                    "source_point_count": point_count,
                    "forecast_granularity": "subhourly_sum" if point_count > 1 else "hourly",
                }
            )

        return aggregated, {
            "raw_rows": len(rows),
            "unique_points": len(per_timestamp),
            "hourly_rows": len(aggregated),
            "subhourly_hours": subhourly_hours,
            "max_points_per_hour": max_points_per_hour,
        }

    @staticmethod
    def _aggregate_market_rows_hourly(
        rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Aggregate market-price rows to the hourly planner layer.

        The external market source may contain hourly or quarter-hourly values.
        The planner is still hourly, so quarter-hour values are combined into a
        single arithmetic mean per hour. Known prices always take precedence
        over forecast prices for the same hour.
        """
        grouped: dict[tuple[datetime, str], list[float]] = {}
        granularities: dict[tuple[datetime, str], set[str]] = {}
        for row in rows:
            hour = _hour_key(row.get("time"))
            price = _as_float(row.get("market_price"))
            if hour is None or price is None:
                continue
            source_kind = str(row.get("source_kind") or "forecast")
            key = (hour, source_kind)
            grouped.setdefault(key, []).append(price)
            granularity = str(row.get("forecast_granularity") or ("known" if source_kind == "known" else "hourly"))
            granularities.setdefault(key, set()).add(granularity)

        hours = sorted({hour for hour, _source in grouped})
        aggregated: list[dict[str, Any]] = []
        full_quarter_hours = 0
        partial_quarter_hours = 0
        max_points_per_hour = 0

        for hour in hours:
            source_kind = "known" if (hour, "known") in grouped else "forecast"
            values = grouped.get((hour, source_kind), [])
            if not values:
                continue
            point_count = len(values)
            max_points_per_hour = max(max_points_per_hour, point_count)
            if point_count >= 4:
                full_quarter_hours += 1
            elif point_count > 1:
                partial_quarter_hours += 1
            granularity_values = granularities.get((hour, source_kind), set())
            if "daily_fallback" in granularity_values:
                forecast_granularity = "daily_fallback"
            elif source_kind == "known":
                forecast_granularity = "known"
            else:
                forecast_granularity = "hourly"
            aggregated.append(
                {
                    "time": hour.isoformat(),
                    "market_price": sum(values) / point_count,
                    "source_kind": source_kind,
                    "source_point_count": point_count,
                    "forecast_granularity": forecast_granularity,
                }
            )

        diagnostics = {
            "raw_rows": len(rows),
            "hourly_rows": len(aggregated),
            "full_quarter_hours": full_quarter_hours,
            "partial_quarter_hours": partial_quarter_hours,
            "max_points_per_hour": max_points_per_hour,
        }
        return aggregated, diagnostics

    def _forecast_entity_ids(self) -> dict[str, str]:
        return {
            "market_price": self._entity_id(CONF_MARKET_PRICE_ENTITY, DEFAULT_MARKET_PRICE_ENTITY) or "",
            "known_price": self._entity_id(CONF_KNOWN_PRICE_ENTITY, DEFAULT_KNOWN_PRICE_ENTITY) or "",
            "forecast_price": self._entity_id(CONF_FORECAST_PRICE_ENTITY, DEFAULT_FORECAST_PRICE_ENTITY) or "",
            "home": self._entity_id(CONF_HOME_FORECAST_ENTITY, DEFAULT_HOME_FORECAST_ENTITY) or "",
            "solar_today": self._entity_id(CONF_SOLAR_TODAY_ENTITY, DEFAULT_SOLAR_TODAY_ENTITY) or "",
            "solar_tomorrow": self._entity_id(CONF_SOLAR_TOMORROW_ENTITY, DEFAULT_SOLAR_TOMORROW_ENTITY) or "",
            "solar_day3": self._entity_id(CONF_SOLAR_DAY3_ENTITY, DEFAULT_SOLAR_DAY3_ENTITY) or "",
        }

    def _build_forecast(self) -> dict[str, Any]:
        entity_ids = self._forecast_entity_ids()
        price_settings = self._price_architecture_settings()
        raw_market_rows = (
            self._stroomvoorspeller_market_rows(entity_ids["market_price"])
            if price_settings["enabled"]
            else []
        )
        market_rows, market_row_diagnostics = self._aggregate_market_rows_hourly(raw_market_rows)
        known_rows = self._rows(entity_ids["known_price"], "prices")
        price_rows = self._rows(entity_ids["forecast_price"], "forecasts")

        # Direct forecast integration is package-independent. Daily fallback is
        # deliberately not shaped from legacy package sensors; if the native
        # hourly feed is unavailable, the daily Stroomvoorspeller estimate is
        # used transparently as the degraded fallback.
        shaped_daily_fallback_hours = 0
        raw_daily_fallback_hours = sum(
            1 for market_row in market_rows
            if market_row.get("forecast_granularity") == "daily_fallback"
        )

        home_rows = self._rows(entity_ids["home"], "forecasts")
        home_hourly_rows, home_row_diagnostics = self._aggregate_home_rows_hourly(home_rows)
        solar_rows: list[dict[str, Any]] = []
        for key in ("solar_today", "solar_tomorrow", "solar_day3"):
            solar_rows.extend(self._rows(entity_ids[key], "detailedHourly"))

        now_hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        end_hour = now_hour + timedelta(hours=FORECAST_HORIZON_HOURS)
        slots: dict[datetime, dict[str, Any]] = {
            now_hour + timedelta(hours=index): {
                "time": (now_hour + timedelta(hours=index)).isoformat(),
                "price": None,
                "price_min": None,
                "price_max": None,
                "price_source": None,
                "market_price": None,
                "import_price": None,
                "export_price": None,
                "import_price_source": None,
                "export_price_source": None,
                "solar_kwh": None,
                "home_consumption_kwh": None,
            }
            for index in range(FORECAST_HORIZON_HOURS)
        }

        if price_settings["enabled"] and market_rows:
            import_markup = float(price_settings["import_markup"])
            export_markup = float(price_settings["export_markup"])
            # The planner remains hourly. If the market source contains
            # quarter-hour values they are averaged above into the matching
            # hourly planner slot, preventing the previous last-quarter-wins
            # behaviour.
            for row in market_rows:
                hour = _hour_key(row.get("time"))
                if hour not in slots:
                    continue
                market_price = _as_float(row.get("market_price"))
                if market_price is None:
                    continue
                source_kind = str(row.get("source_kind") or "forecast")
                if source_kind == "forecast" and slots[hour].get("price_source") == "known":
                    continue
                import_price = market_price + import_markup
                export_price = market_price + export_markup
                slots[hour]["market_price"] = market_price
                slots[hour]["import_price"] = import_price
                slots[hour]["export_price"] = export_price
                slots[hour]["price"] = import_price
                slots[hour]["price_min"] = import_price
                slots[hour]["price_max"] = import_price
                slots[hour]["price_source"] = source_kind
                slots[hour]["import_price_source"] = source_kind
                slots[hour]["export_price_source"] = source_kind

        if not (price_settings["enabled"] and market_rows):
            for row in price_rows:
                hour = _hour_key(_first(row, ("time", "timestamp", "datetime", "start")))
                if hour not in slots:
                    continue
                predicted = _as_float(_first(row, ("predicted", "all_in", "price", "value")))
                lower = _as_float(_first(row, ("lower", "price_min", "min", "lower_bound")))
                upper = _as_float(_first(row, ("upper", "price_max", "max", "upper_bound")))
                slots[hour]["price"] = predicted
                slots[hour]["import_price"] = predicted
                slots[hour]["export_price"] = predicted
                slots[hour]["price_min"] = lower if lower is not None else predicted
                slots[hour]["price_max"] = upper if upper is not None else predicted
                slots[hour]["price_source"] = "forecast" if predicted is not None else None
                slots[hour]["import_price_source"] = "forecast" if predicted is not None else None
                slots[hour]["export_price_source"] = "forecast" if predicted is not None else None

            for row in known_rows:
                hour = _hour_key(_first(row, ("timestamp", "time", "datetime", "start")))
                if hour not in slots:
                    continue
                price = _as_float(_first(row, ("price", "all_in", "predicted", "value")))
                if price is None:
                    continue
                slots[hour]["price"] = price
                slots[hour]["import_price"] = price
                slots[hour]["export_price"] = price
                slots[hour]["price_min"] = price
                slots[hour]["price_max"] = price
                slots[hour]["price_source"] = "known"
                slots[hour]["import_price_source"] = "known"
                slots[hour]["export_price_source"] = "known"

        for row in home_hourly_rows:
            hour = _hour_key(row.get("time"))
            if hour not in slots:
                continue
            slots[hour]["home_consumption_kwh"] = _as_float(row.get("home_consumption_kwh"))

        for row in solar_rows:
            hour = _hour_key(_first(row, ("period_start", "periodStart", "time", "timestamp")))
            if hour not in slots:
                continue
            value = _as_float(_first(row, ("pv_estimate", "pvEstimate", "predicted", "value")))
            if value is None:
                continue
            current = slots[hour]["solar_kwh"]
            slots[hour]["solar_kwh"] = value if current is None else max(current, value)

        forecast = list(slots.values())
        price_count = sum(1 for row in forecast if row["price"] is not None)
        home_count = sum(1 for row in forecast if row["home_consumption_kwh"] is not None)
        solar_count = sum(1 for row in forecast if row["solar_kwh"] is not None)
        complete_count = sum(
            1
            for row in forecast
            if row["price"] is not None
            and row["home_consumption_kwh"] is not None
            and row["solar_kwh"] is not None
        )

        missing_sources: list[str] = []
        if price_settings["enabled"]:
            if not market_rows:
                missing_sources.append("price")
        elif not known_rows and not price_rows:
            missing_sources.append("price")
        if not home_hourly_rows:
            missing_sources.append("home")
        if not solar_rows:
            missing_sources.append("solar")

        ready = price_count >= 24 and home_count >= 24 and solar_count >= 24
        return {
            "forecast_ready": ready,
            "forecast_status": "ready" if ready else "waiting_for_sources",
            "forecast_horizon_hours": FORECAST_HORIZON_HOURS,
            "forecast_price_hours": price_count,
            "forecast_home_hours": home_count,
            "forecast_home_raw_rows": home_row_diagnostics["raw_rows"],
            "forecast_home_unique_points": home_row_diagnostics["unique_points"],
            "forecast_home_hourly_rows": home_row_diagnostics["hourly_rows"],
            "forecast_home_subhourly_hours": home_row_diagnostics["subhourly_hours"],
            "forecast_home_max_points_per_hour": home_row_diagnostics["max_points_per_hour"],
            "forecast_home_aggregation": "sum_energy_per_hour",
            "forecast_solar_hours": solar_count,
            "forecast_complete_hours": complete_count,
            "forecast_missing_sources": missing_sources,
            "forecast_sources": entity_ids,
            "price_architecture_enabled": bool(price_settings["enabled"]),
            "price_architecture_source": entity_ids.get("market_price") if price_settings["enabled"] else "legacy_known_plus_forecast",
            "price_architecture_market_rows": len(market_rows),
            "price_architecture_raw_market_rows": market_row_diagnostics["raw_rows"],
            "price_architecture_hourly_market_rows": market_row_diagnostics["hourly_rows"],
            "price_architecture_full_quarter_hours": market_row_diagnostics["full_quarter_hours"],
            "price_architecture_partial_quarter_hours": market_row_diagnostics["partial_quarter_hours"],
            "price_architecture_max_points_per_hour": market_row_diagnostics["max_points_per_hour"],
            "price_architecture_shaped_daily_fallback_hours": shaped_daily_fallback_hours,
            "price_architecture_unshaped_daily_fallback_hours": max(0, raw_daily_fallback_hours - shaped_daily_fallback_hours),
            "price_architecture_direct_forecast_url": "https://stroomvoorspeller.nl/data/forecast.json",
            "price_architecture_direct_forecast_available": bool(self._direct_price_forecast_rows()),
            "price_architecture_direct_forecast_hours": len(self._direct_price_forecast_rows()),
            "price_architecture_direct_forecast_generated_at": (self._direct_price_forecast_payload or {}).get("generated_at"),
            "price_architecture_direct_forecast_last_success_at": (
                self._direct_price_forecast_last_success_at.isoformat()
                if self._direct_price_forecast_last_success_at is not None
                else None
            ),
            "price_architecture_direct_forecast_error": self._direct_price_forecast_error,
            "price_architecture_import_markup_per_kwh": price_settings["import_markup"],
            "price_architecture_export_markup_per_kwh": price_settings["export_markup"],
            "price_architecture_requested_resolution": price_settings["resolution"],
            "price_architecture_effective_resolution": TARIFF_RESOLUTION_HOURLY,
            "price_architecture_quarter_hour_ready": bool(
                price_settings["resolution"] == TARIFF_RESOLUTION_QUARTER_HOURLY
                and market_row_diagnostics["full_quarter_hours"] >= 24
            ),
            "price_architecture_resolution_note": (
                "quarter_hour_source_aggregated_to_hourly_planner"
                if price_settings["resolution"] == TARIFF_RESOLUTION_QUARTER_HOURLY
                else "hourly_planner"
            ),
            "forecast": forecast,
        }

    def _source_monitor_specs(self) -> dict[str, dict[str, Any]]:
        forecast_ids = self._forecast_entity_ids()
        energyzero_id = self._entity_id(
            CONF_MONITOR_ENERGYZERO_ENTITY, DEFAULT_MONITOR_ENERGYZERO_ENTITY
        ) or ""
        stroom_id = self._entity_id(
            CONF_MONITOR_STROOMVOORSPELLER_ENTITY, DEFAULT_MONITOR_STROOMVOORSPELLER_ENTITY
        ) or ""
        solcast_api_id = self._entity_id(
            CONF_MONITOR_SOLCAST_API_ENTITY, DEFAULT_MONITOR_SOLCAST_API_ENTITY
        ) or ""

        def state_payload(entity_id: str, attrs: tuple[str, ...]) -> Any:
            state = self.hass.states.get(entity_id) if entity_id else None
            if state is None:
                return None
            payload: dict[str, Any] = {"state": state.state}
            for attr in attrs:
                if attr in state.attributes:
                    payload[attr] = state.attributes.get(attr)
            return payload

        solar_ids = [
            forecast_ids["solar_today"],
            forecast_ids["solar_tomorrow"],
            forecast_ids["solar_day3"],
        ]
        solar_content = [state_payload(entity_id, ("detailedHourly",)) for entity_id in solar_ids]

        return {
            "solcast_api": {
                "entity_ids": [solcast_api_id],
                "content": state_payload(solcast_api_id, ()),
            },
            "solcast_forecast": {
                "entity_ids": solar_ids,
                "content": solar_content,
            },
            "energyzero_prices": {
                "entity_ids": [energyzero_id],
                "content": state_payload(energyzero_id, ("prices", "price_count", "available_until")),
            },
            "stroomvoorspeller": {
                "entity_ids": [stroom_id],
                "content": state_payload(stroom_id, ("today", "tomorrow", "forecast", "hours", "prices", "updated")),
            },
            "price_forecast": {
                "entity_ids": [forecast_ids["forecast_price"]],
                "content": state_payload(forecast_ids["forecast_price"], ("forecasts",)),
            },
            "home_forecast": {
                "entity_ids": [forecast_ids["home"]],
                "content": state_payload(forecast_ids["home"], ("forecasts",)),
            },
        }

    async def _async_update_data(self) -> dict[str, Any]:
        control_ids = self.control_entity_ids
        data = {
            "simulation_mode": self.simulation_mode,
            "electrical_profile": self.electrical_profile,
            "max_charge_power_w": self.max_charge_power_w,
            "max_discharge_power_w": self.max_discharge_power_w,
            "battery_capacity_kwh": DEFAULT_BATTERY_CAPACITY_KWH,
            "charge_efficiency_percent": self.entry.options.get(
                CONF_CHARGE_EFFICIENCY_PERCENT, DEFAULT_CHARGE_EFFICIENCY_PERCENT
            ),
            "discharge_efficiency_percent": self.entry.options.get(
                CONF_DISCHARGE_EFFICIENCY_PERCENT, DEFAULT_DISCHARGE_EFFICIENCY_PERCENT
            ),
            "control_path_configured": all(bool(control_ids.get(key)) for key in ("operating_mode", "action_direction", "power_setpoint")),
            "soc": self._number(CONF_SOC_ENTITY),
            "device_status": self._state(CONF_DEVICE_STATUS_ENTITY),
            "charge_power_w": self._number(CONF_CHARGE_POWER_ENTITY),
            "discharge_power_w": self._number(CONF_DISCHARGE_POWER_ENTITY),
            "grid_import_power_w": self._number(CONF_GRID_IMPORT_POWER_ENTITY),
            "grid_export_power_w": self._number(CONF_GRID_EXPORT_POWER_ENTITY),
            "solar_power_w": self._number(CONF_SOLAR_POWER_ENTITY),
            "operating_mode": self._state(CONF_OPERATING_MODE_ENTITY),
            "action_direction": self._state(CONF_ACTION_DIRECTION_ENTITY),
            "power_setpoint_w": self._number(CONF_POWER_SETPOINT_ENTITY),
        }
        data.update(self._home_power_snapshot())
        # Alpha70: build a persistent, EMS-owned 15-minute demand history from
        # the validated canonical Home Power. This remains parallel/shadow data
        # and does not feed the current Home Forecast or Plan72 yet.
        data.update(
            await self.home_history.async_observe(
                data.get("home_power_w") if data.get("home_power_valid") else None
            )
        )
        # Alpha71: rebuild only when a completed 15-minute history point changes.
        # The internal forecast remains shadow-only and is not used by Plan72.
        history_points = int(data.get("home_history_points") or 0)
        if (
            self._cached_internal_home_forecast is None
            or history_points != self._internal_home_forecast_history_points
        ):
            self._cached_internal_home_forecast = build_internal_home_forecast(
                self.home_history.history
            )
            self._internal_home_forecast_history_points = history_points
        data.update(deepcopy(self._cached_internal_home_forecast))
        if self._price_architecture_settings()["enabled"]:
            await self._async_refresh_direct_price_forecast()
        data.update(self._build_forecast())
        # Source Monitor remains fast and observes every coordinator cycle. It
        # supplies content-change timestamps used to trigger event-driven 72h
        # refreshes without polling the heavy planner every 10 seconds.
        data.update(await self.source_monitor.async_observe(self._source_monitor_specs()))

        reserve_percent = self.entry.options.get(
            CONF_SOFTWARE_RESERVE_PERCENT, DEFAULT_SOFTWARE_RESERVE_PERCENT
        )
        energy_need = build_energy_need_analysis(
            data.get("forecast", []), data.get("soc"), reserve_percent
        )
        data.update(energy_need)
        charge_efficiency_percent = self.entry.options.get(
            CONF_CHARGE_EFFICIENCY_PERCENT, DEFAULT_CHARGE_EFFICIENCY_PERCENT
        )
        discharge_efficiency_percent = self.entry.options.get(
            CONF_DISCHARGE_EFFICIENCY_PERCENT, DEFAULT_DISCHARGE_EFFICIENCY_PERCENT
        )
        minimum_trade_margin = self.entry.options.get(
            CONF_MINIMUM_TRADE_MARGIN, DEFAULT_MINIMUM_TRADE_MARGIN
        )
        planner_preview = build_planner_preview(
            data.get("forecast", []),
            energy_need,
            data.get("soc"),
            charge_efficiency_percent,
            discharge_efficiency_percent,
            minimum_trade_margin,
            max_charge_power_w=self.max_charge_power_w,
        )
        data.update(planner_preview)

        # Alpha53: use the Scheduler's own lifecycle decision as the primary
        # signal for releasing an expired automatic slot. This avoids keeping a
        # planner-owned pending plan locked when the Scheduler already reports
        # it as ``verlopen``. The Plan Store still performs its independent
        # timestamp check as a fallback, and manual plans remain untouched.
        pre_cleanup_scheduler = self.scheduler.evaluate(
            self.max_charge_power_w, self.max_discharge_power_w
        )
        scheduler_expired_slots = {
            int(slot)
            for slot, detail in (pre_cleanup_scheduler.get("scheduler_slots") or {}).items()
            if str((detail or {}).get("status") or "").lower() == "verlopen"
        }
        expired_release = await self.plan_store.async_release_expired_automatic_plans(
            scheduler_expired_slots
        )
        data["auto_expired_release_changed"] = expired_release.get("changed", False)
        data["auto_expired_released_slots"] = expired_release.get("released_slots", [])
        data["auto_expired_scheduler_slots"] = expired_release.get(
            "scheduler_expired_slots", []
        )

        # Re-evaluate after cleanup so Bridge/Scheduler see the newly free slot
        # in the same coordinator cycle rather than waiting for a later poll.
        # This also remains the exception trigger for a fresh Plan72 calculation
        # when an action approaches or enters its start window.
        scheduler_snapshot = self.scheduler.evaluate(
            self.max_charge_power_w, self.max_discharge_power_w
        )
        refresh, refresh_reason, source_token, start_key = self._should_refresh_72h_plan(
            data, scheduler_snapshot
        )
        if refresh:
            self._cached_72h_plan = build_72h_plan_preview(
                data.get("forecast", []),
                energy_need,
                planner_preview,
                data.get("soc"),
                charge_efficiency_percent,
                discharge_efficiency_percent,
                max_charge_power_w=self.max_charge_power_w,
                max_discharge_power_w=self.max_discharge_power_w,
            )
            now_local = dt_util.now()
            self._last_plan_refresh_at = now_local
            self._last_plan_refresh_reason = refresh_reason
            self._last_plan_source_token = source_token
            self._last_forecast_ready = bool(data.get("forecast_ready"))
            self._last_plan_start_critical_key = start_key
            self._plan_refresh_count_today += 1
            if 5 <= now_local.hour <= 22:
                # Any event-driven refresh during this hour also satisfies the
                # hourly periodic refresh, preventing a redundant second pass.
                self._last_plan_periodic_bucket = now_local.strftime("%Y-%m-%dT%H")
        else:
            self._last_forecast_ready = bool(data.get("forecast_ready"))

        if self._cached_72h_plan is not None:
            data.update(deepcopy(self._cached_72h_plan))
        data.update(self._planner_refresh_metadata(refresh_reason))
        data.update(scheduler_snapshot)
        bridge = build_planner_action_bridge(data)
        data.update(bridge)

        # Alpha30: controlled automatic Plan Store write followed by a separate
        # guarded Scheduler handoff. Physical execution remains disabled.
        desired_auto_plans: dict[int, dict[str, Any]] = {}
        write_gate_open = (
            bool(data.get("auto_bridge_valid"))
            and bool(data.get("forecast_ready"))
            and not int(data.get("auto_bridge_invalid_candidate_count") or 0)
        )
        if write_gate_open:
            for proposal in data.get("auto_bridge_slot_preview") or []:
                if not proposal.get("plan_store_write_permitted"):
                    continue
                slot = proposal.get("suggested_slot")
                if isinstance(slot, int):
                    desired_auto_plans[slot] = proposal

        # Alpha40.1: preserve existing planner-owned future plans while the
        # planner/forecast gate is temporarily unavailable. An empty desired
        # set is only authoritative when the write gate is open; otherwise
        # syncing with {} would incorrectly clear valid pending plans during
        # startup or a transient source outage.
        if write_gate_open:
            write_result = await self.plan_store.async_sync_automatic_plans(
                desired_auto_plans
            )
        else:
            write_result = {
                "changed": False,
                "changed_slots": [],
                "written_slots": [],
                "cleared_slots": [],
                "skipped_slots": [],
                "preserved_due_gate_closed": True,
            }
        # Promote only the exact planner proposals that are currently approved
        # by the bridge. Matching signatures protect against stale data and
        # concurrent/manual edits between write and handoff.
        handoff_gate_open = write_gate_open
        handoff_allowed: dict[int, str] = {}
        if handoff_gate_open:
            for proposal in data.get("auto_bridge_slot_preview") or []:
                if not proposal.get("scheduler_handoff_permitted"):
                    continue
                slot = proposal.get("suggested_slot")
                signature = proposal.get("planner_signature")
                if isinstance(slot, int) and isinstance(signature, str) and signature:
                    handoff_allowed[slot] = signature

        handoff_result = await self.plan_store.async_handoff_automatic_plans(
            handoff_allowed if handoff_gate_open else {}
        )

        data.update(
            {
                "auto_bridge_plan_store_write_enabled": True,
                "auto_bridge_plan_store_write_gate_open": write_gate_open,
                "auto_bridge_plan_store_preserved_due_gate_closed": write_result.get("preserved_due_gate_closed", False),
                "auto_bridge_plan_store_write_changed": write_result.get("changed", False),
                "auto_bridge_plan_store_written_slots": write_result.get("written_slots", []),
                "auto_bridge_plan_store_cleared_slots": write_result.get("cleared_slots", []),
                "auto_bridge_plan_store_skipped_slots": write_result.get("skipped_slots", []),
                "auto_bridge_scheduler_handoff_enabled": True,
                "auto_bridge_scheduler_handoff_gate_open": handoff_gate_open,
                "auto_bridge_scheduler_handoff_changed": handoff_result.get("changed", False),
                "auto_bridge_scheduler_handoff_slots": handoff_result.get("handed_off_slots", []),
                "auto_bridge_scheduler_handoff_skipped_slots": handoff_result.get("skipped_slots", []),
                "auto_bridge_execution_enabled": bool(self._auto_execution_armed),
                "auto_bridge_observational_only": False,
            }
        )

        # Refresh scheduler details from the just-synchronized and handed-off store.
        data.update(self.scheduler.evaluate(self.max_charge_power_w, self.max_discharge_power_w))
        refreshed_bridge = build_planner_action_bridge(data)
        # Keep writer result flags from above while refreshing candidate/slot data.
        for key, value in refreshed_bridge.items():
            if key not in {
                "auto_bridge_plan_store_write_enabled",
                "auto_bridge_scheduler_handoff_enabled",
                "auto_bridge_scheduler_handoff_gate_open",
                "auto_bridge_scheduler_handoff_changed",
                "auto_bridge_scheduler_handoff_slots",
                "auto_bridge_scheduler_handoff_skipped_slots",
                "auto_bridge_execution_enabled",
                "auto_bridge_observational_only",
            }:
                data[key] = value
        # Time-aware diagnostics + authoritative pre-start gate for automatic
        # Scheduler-ready plans. Alpha35 then hands the approved automatic plan
        # to a non-actuating Safety Guard stage. Physical execution remains off.
        data.update(AnkerEmsPreStartValidator().evaluate(data))
        data["physical_test_active"] = bool(self.physical_test.data.get("active"))
        data["execution_active"] = bool(self.execution.data.get("active"))
        data["execution_origin"] = self.execution.data.get("origin")
        data.update(self.safety_guard.evaluate_automatic_handoff(data))
        # Expose the automatic handoff into the Execution Controller as a
        # non-actuating preview, followed by Alpha38 final live revalidation.
        # No Home Assistant control service is called by either stage.
        data.update(self.execution.evaluate_automatic_handoff(data))
        data.update(self.execution.evaluate_final_revalidation(data))
        data.update(self.execution.evaluate_mode_switch_transaction(data))
        data.update(self._automatic_execution_shadow(data))

        # Legacy Safety Guard / Action Controller remain available for the
        # existing manual execution path. The automatic Alpha35 handoff stops
        # before the Execution Controller and does not call services.
        data.update(self.safety_guard.evaluate(data))
        data.update(self.action_controller.evaluate(data))
        test_data = self.physical_test.data
        data.update({f"physical_test_{key}": value for key, value in test_data.items()})

        execution_data = self.execution.data
        data.update({f"execution_{key}": value for key, value in execution_data.items()})
        return data
