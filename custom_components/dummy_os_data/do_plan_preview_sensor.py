"""Home Assistant sensor adapter for observer-only DO Plan Preview."""

from __future__ import annotations

from typing import Any
from .planner_time_runtime import aligned_reference, subscribe_upstream

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .do_plan_preview import build_do_plan_preview

INPUT_UNIQUE_ID = "do_plan_input_72h"
RESERVE_UNIQUE_ID = "do_plan_reserve_soc"


def _state_contract(hass: Any, unique_id: str) -> tuple[str | None, dict[str, Any]]:
    """Copy one already-published upstream contract on the HA main thread."""
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id)
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in {"unknown", "unavailable", "none", "None", ""}:
        return entity_id, {"status": "unavailable", "valid": False, "blockers": [f"{unique_id}_unavailable"]}
    result = dict(state.attributes)
    result["status"] = state.state
    return entity_id, result


def build_do_plan_preview_sensors(coordinator: Any) -> list[Any]:
    """Build Step-4 preview from existing Step-1 and Step-3 contracts.

    Preview must not rebuild Forecast -> Planner -> Model Health. The upstream
    entities already own those calculations and publish the validated contract.
    """
    from .sensor import DummyOSPlanReserveSOCSensor

    class DummyOSPlanPreviewSensor(DummyOSPlanReserveSOCSensor):
        async def async_added_to_hass(self) -> None:
            await super().async_added_to_hass()
            self._remove_aligned_upstream = subscribe_upstream(self, ['do_plan_input_72h', 'do_plan_reserve_soc'])

        async def async_will_remove_from_hass(self) -> None:
            remove = getattr(self, "_remove_aligned_upstream", None)
            if remove is not None:
                remove()
            await super().async_will_remove_from_hass()

        _attr_name = "DO Plan Preview"
        _attr_unique_id = "do_plan_preview"
        _attr_suggested_object_id = "do_plan_preview"
        _attr_icon = "mdi:clipboard-text-clock-outline"
        _unrecorded_attributes = frozenset({"safety_charge_hours", "best_import_avoidance", "best_export_trade"})

        CHARGE_EFFICIENCY_PERCENT = 92.0
        DISCHARGE_EFFICIENCY_PERCENT = 92.0
        MINIMUM_TRADE_MARGIN = 0.10
        MAX_CHARGE_POWER_W = 3200
        MAX_DISCHARGE_POWER_W = 3200

        def _snapshot(self) -> dict[str, Any]:
            input_entity, input_result = _state_contract(self.hass, INPUT_UNIQUE_ID)
            reserve_entity, reserve_result = _state_contract(self.hass, RESERVE_UNIQUE_ID)
            return {"now": aligned_reference(input_result, dt_util.utcnow()), "input_entity": input_entity, "reserve_entity": reserve_entity, "input_result": input_result, "reserve_result": reserve_result}

        def _calculate_result(self, snapshot: dict[str, Any]) -> dict[str, Any]:
            input_result = snapshot["input_result"]
            reserve_result = snapshot["reserve_result"]
            result = build_do_plan_preview(input_result=input_result, reserve_result=reserve_result, now=snapshot["now"], charge_efficiency_percent=self.CHARGE_EFFICIENCY_PERCENT, discharge_efficiency_percent=self.DISCHARGE_EFFICIENCY_PERCENT, minimum_trade_margin=self.MINIMUM_TRADE_MARGIN, max_charge_power_w=self.MAX_CHARGE_POWER_W, max_discharge_power_w=self.MAX_DISCHARGE_POWER_W)
            result["input_entity"] = snapshot["input_entity"]
            result["reserve_entity"] = snapshot["reserve_entity"]
            result["soc_source_entity"] = reserve_result.get("soc_source_entity")
            result["source_layer_status"] = reserve_result.get("source_layer_status")
            result["dependency_mode"] = "published_upstream_contracts"
            return result

    return [DummyOSPlanPreviewSensor(coordinator)]
