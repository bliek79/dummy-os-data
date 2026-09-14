"""Home Assistant sensor adapter for observer-only Planner Step 5."""

from __future__ import annotations
from typing import Any

from .do_plan_72h import build_do_plan_72h
from .do_plan_preview import build_do_plan_preview
from .do_plan_grid_support import build_do_plan_grid_support


def build_do_plan_72h_sensors(coordinator: Any) -> list[Any]:
    from homeassistant.components.sensor import SensorEntity
    from homeassistant.core import callback
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
    from homeassistant.util import dt as dt_util

    from .const import DOMAIN
    from .planner_time_runtime import subscribe_bridge_recovery
    from .sensor import (
        DummyOSPlanReserveSOCSensor,
        _build_energy_need_from_snapshot,
        _build_plan_input_from_snapshot,
        _build_reserve_from_snapshot,
    )

    class DummyOSPlan72hSensor(DummyOSPlanReserveSOCSensor):
        """Heavy alpha76-backed Plan72 view with bounded HA refresh triggers."""

        _attr_name = "DO Plan 72h"
        _attr_unique_id = "do_plan_72h"
        _attr_suggested_object_id = "do_plan_72h"
        _attr_icon = "mdi:timeline-clock-outline"
        _unrecorded_attributes = frozenset(
            {
                "hours",
                "slots",
                "baseline",
                "candidate",
                "soc_bridge",
                "safety_plan",
                "rejected_trade_candidate",
                "alpha76_plan72",
            }
        )

        def __init__(self, coordinator: Any) -> None:
            super().__init__(coordinator)
            self._remove_profile_listener = None
            self._remove_periodic_refresh = None
            self._remove_soc_recovery_listener = None
            self._last_profile = coordinator.profile
            self._last_solar_source_signature = self._solar_source_signature()
            self._last_price_source_signature = self._price_source_signature()

        @staticmethod
        def _stamp(value: Any) -> str | None:
            return value.isoformat() if value is not None else None

        def _solar_source_signature(self) -> tuple[Any, ...]:
            solar = self.coordinator.solar
            return (
                self._stamp(solar.last_successful_update),
                solar.last_error,
                solar.source_point_count,
            )

        def _price_source_signature(self) -> tuple[Any, ...]:
            prices = self.coordinator.prices
            return (
                prices.source_generated_at,
                prices.forecast_generated_at,
                prices.status,
                prices.error,
            )

        async def async_added_to_hass(self) -> None:
            """Subscribe only to meaningful heavy-planner refresh triggers."""
            # Deliberately bypass the generic planner parent subscriptions here.
            # Those parents listen to raw SOC and every Solar/Prices notify, while
            # Solar notify also fires on actual PV telemetry. That made Plan72 run
            # dozens of times per minute in the alpha36 live test.
            await SensorEntity.async_added_to_hass(self)

            self._remove_profile_listener = self.coordinator.async_add_listener(
                self._handle_profile_update
            )
            self._remove_solar_listener = self.coordinator.solar.async_add_listener(
                self._handle_solar_source_update
            )
            self._remove_prices_listener = self.coordinator.prices.async_add_listener(
                self._handle_price_source_update
            )
            self._remove_bridge_recovery = subscribe_bridge_recovery(self)

            registry = er.async_get(self.hass)
            soc_contract_entity_id = registry.async_get_entity_id(
                "sensor", DOMAIN, "do_plan_soc_contract"
            )
            if soc_contract_entity_id:
                self._remove_soc_recovery_listener = async_track_state_change_event(
                    self.hass,
                    [soc_contract_entity_id],
                    self._handle_soc_contract_recovery,
                )

            self._remove_periodic_refresh = async_track_time_change(
                self.hass,
                self._handle_periodic_refresh,
                minute=5,
                second=0,
            )
            self._schedule_refresh()

        async def async_will_remove_from_hass(self) -> None:
            for attr in (
                "_remove_profile_listener",
                "_remove_solar_listener",
                "_remove_prices_listener",
                "_remove_bridge_recovery",
                "_remove_soc_recovery_listener",
                "_remove_periodic_refresh",
            ):
                remove = getattr(self, attr, None)
                if remove is not None:
                    remove()
                    setattr(self, attr, None)
            if self._refresh_task is not None and not self._refresh_task.done():
                self._refresh_task.cancel()
            await SensorEntity.async_will_remove_from_hass(self)

        @callback
        def _handle_profile_update(self) -> None:
            profile = self.coordinator.profile
            if profile == self._last_profile:
                return
            self._last_profile = profile
            self._schedule_refresh()

        @callback
        def _handle_solar_source_update(self) -> None:
            signature = self._solar_source_signature()
            if signature == self._last_solar_source_signature:
                return
            self._last_solar_source_signature = signature
            self._schedule_refresh()

        @callback
        def _handle_price_source_update(self) -> None:
            signature = self._price_source_signature()
            if signature == self._last_price_source_signature:
                return
            self._last_price_source_signature = signature
            self._schedule_refresh()

        @callback
        def _handle_soc_contract_recovery(self, event: Any) -> None:
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")
            if new_state is None or new_state.state != "ready":
                return
            if old_state is not None and old_state.state == "ready":
                return
            if getattr(self, "_last_soc_bridge_valid", True) is False:
                self._schedule_refresh()

        @callback
        def _handle_periodic_refresh(self, now: Any) -> None:
            local = dt_util.as_local(now)
            if 5 <= local.hour < 22:
                self._schedule_refresh()

        def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
            input_result = _build_plan_input_from_snapshot(snapshot)
            energy_need_result = _build_energy_need_from_snapshot(snapshot)
            reserve_result = _build_reserve_from_snapshot(snapshot)
            preview_result = build_do_plan_preview(
                input_result=input_result,
                reserve_result=reserve_result,
                now=snapshot["now"],
                charge_efficiency_percent=92.0,
                discharge_efficiency_percent=92.0,
                minimum_trade_margin=0.10,
                max_charge_power_w=3200,
                max_discharge_power_w=3200,
            )
            grid_support_result = build_do_plan_grid_support(
                input_result=input_result,
                energy_need_result=energy_need_result,
                reserve_result=reserve_result,
                trigger_kwh=0.25,
            )
            result = build_do_plan_72h(
                input_result=input_result,
                reserve_result=reserve_result,
                preview_result=preview_result,
                grid_support_result=grid_support_result,
            )
            result["input_entity"] = "sensor.do_plan_input_72h"
            result["reserve_entity"] = "sensor.do_plan_reserve_soc"
            result["preview_entity"] = "sensor.do_plan_preview"
            result["grid_support_entity"] = "sensor.do_plan_grid_support"
            result["soc_source_entity"] = reserve_result.get("soc_source_entity")
            result["source_layer_status"] = reserve_result.get("source_layer_status")
            return result

        def _initial_result(self) -> dict[str, Any]:
            return {
                "status": "initializing",
                "valid": False,
                "slot_count": 0,
                "hour_count": 0,
                "slots": [],
                "hours": [],
                "shadow_only": True,
                "active_use_permitted": False,
                "physical_execution_authority": False,
                "plan_store_write": False,
                "scheduler_invoked": False,
                "safety_chain_invoked": False,
                "service_calls_performed": False,
                "blockers": ["planner_calculation_pending"],
            }

        @property
        def native_value(self) -> str:
            return str(self._result().get("status", "initializing"))

        @property
        def extra_state_attributes(self) -> dict[str, Any]:
            result = dict(self._result())
            # Keep the exact alpha76 raw planner output internal for parity and
            # diagnostics, but never publish this large duplicate into HA state.
            result.pop("alpha76_plan72", None)
            return result

    return [DummyOSPlan72hSensor(coordinator)]
