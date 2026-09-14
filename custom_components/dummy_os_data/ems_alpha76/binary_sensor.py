from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import AnkerEmsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AnkerEmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AnkerEmsSourcesAvailable(coordinator, entry),
            AnkerEmsControlAvailable(coordinator, entry),
            AnkerEmsForecastSourcesAvailable(coordinator, entry),
            AnkerEmsSchedulerReady(coordinator, entry),
            AnkerEmsSafetySafe(coordinator, entry),
            AnkerEmsControllerReady(coordinator, entry),
            AnkerEmsPhysicalTestActive(coordinator, entry),
            AnkerEmsExecutionActive(coordinator, entry),
            AnkerEmsPlannerSafetyChargeNeeded(coordinator, entry),
            AnkerEmsPlannerTradeChargeCandidate(coordinator, entry),
            AnkerEmsPlannerDischargePossible(coordinator, entry),
            AnkerEmsPlannerSolarChargeDelay(coordinator, entry),
            AnkerEmsPlannerTradeProfitable(coordinator, entry),
            AnkerEmsAutoPlan72hValid(coordinator, entry),
            AnkerEmsAutoPlan72hExecutionBufferSafe(coordinator, entry),
            AnkerEmsAutoBridgeValid(coordinator, entry),
            AnkerEmsAutomaticExecutionReady(coordinator, entry),
        ]
    )


class _AnkerEmsBinarySensorBase(
    CoordinatorEntity[AnkerEmsCoordinator],
    BinarySensorEntity,
):
    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Dummy OS",
            model="EMS",
        )


class AnkerEmsSourcesAvailable(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Sources Available"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_sources_available"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        required_observation_sources = (
            data.get("soc"),
            data.get("device_status"),
            data.get("charge_power_w"),
            data.get("discharge_power_w"),
            data.get("operating_mode"),
        )
        return all(value is not None for value in required_observation_sources)


class AnkerEmsControlAvailable(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Control Available"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_control_available"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        required_control_sources = (
            data.get("operating_mode"),
            data.get("action_direction"),
            data.get("power_setpoint_w"),
        )
        return all(value is not None for value in required_control_sources)


class AnkerEmsForecastSourcesAvailable(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Forecast Sources Available"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_forecast_sources_available"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("forecast_ready"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "price_hours": data.get("forecast_price_hours"),
            "home_hours": data.get("forecast_home_hours"),
            "solar_hours": data.get("forecast_solar_hours"),
            "complete_hours": data.get("forecast_complete_hours"),
            "missing_sources": data.get("forecast_missing_sources", []),
        }


class AnkerEmsSchedulerReady(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Scheduler Ready"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_scheduler_ready"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("scheduler_ready"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "selected_slot": data.get("scheduler_selected_slot"),
            "selected_action": data.get("scheduler_selected_action"),
            "selected_execution_mode": data.get("scheduler_selected_execution_mode"),
            "selected_start_time": data.get("scheduler_selected_start_time"),
            "physical_control": False,
        }


class AnkerEmsSafetySafe(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Safety Safe"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_safety_safe"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("safety_safe"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "status": data.get("safety_status"),
            "reason": data.get("safety_reason"),
            "reasons": data.get("safety_reasons", []),
            "warnings": data.get("safety_warnings", []),
            "selected_slot": data.get("safety_selected_slot"),
            "physical_control": False,
        }


class AnkerEmsControllerReady(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Controller Ready"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_controller_ready"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("controller_ready"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "status": data.get("controller_status"),
            "selected_slot": data.get("controller_selected_slot"),
            "action": data.get("controller_action"),
            "power_w": data.get("controller_power_w"),
            "target_soc": data.get("controller_target_soc"),
            "reason": data.get("controller_reason"),
            "physical_control": False,
        }


class AnkerEmsPhysicalTestActive(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Physical Test Active"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_physical_test_active"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("physical_test_active"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "status": data.get("physical_test_status"),
            "reason": data.get("physical_test_reason"),
            "power_w": data.get("physical_test_power_w"),
            "duration_s": data.get("physical_test_duration_s"),
            "remaining_s": data.get("physical_test_remaining_s"),
            "started_at": data.get("physical_test_started_at"),
            "stop_at": data.get("physical_test_stop_at"),
            "last_result": data.get("physical_test_last_result"),
        }


class AnkerEmsExecutionActive(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Execution Active"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_execution_active"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("execution_active"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "status": data.get("execution_status"),
            "reason": data.get("execution_reason"),
            "slot": data.get("execution_slot"),
            "action": data.get("execution_action"),
            "power_w": data.get("execution_power_w"),
            "target_soc": data.get("execution_target_soc"),
            "remaining_s": data.get("execution_remaining_s"),
            "last_result": data.get("execution_last_result"),
        }


class _AnkerEmsPlannerBinaryBase(_AnkerEmsBinarySensorBase):
    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "planner_status": data.get("planner_preview_status"),
            "planner_decision": data.get("planner_preview_decision"),
            "planner_reason": data.get("planner_preview_reason"),
            "observational_only": data.get("planner_preview_observational_only", True),
            "trading_execution_enabled": data.get("planner_preview_trading_execution_enabled", False),
        }


class AnkerEmsPlannerSafetyChargeNeeded(_AnkerEmsPlannerBinaryBase):
    _attr_name = "Dummy OS EMS Safety Charge Needed"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_planner_safety_charge_needed"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("planner_preview_safety_charge_needed"))


class AnkerEmsPlannerTradeChargeCandidate(_AnkerEmsPlannerBinaryBase):
    _attr_name = "Dummy OS EMS Trade Charge Candidate"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_planner_trade_charge_candidate"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("planner_preview_trade_charge_candidate"))


class AnkerEmsPlannerDischargePossible(_AnkerEmsPlannerBinaryBase):
    _attr_name = "Dummy OS EMS Discharge Possible"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_planner_discharge_possible"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("planner_preview_discharge_possible"))


class AnkerEmsPlannerSolarChargeDelay(_AnkerEmsPlannerBinaryBase):
    _attr_name = "Dummy OS EMS Solar Charge Delay"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_planner_solar_charge_delay"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("planner_preview_solar_charge_delay"))


class AnkerEmsPlannerTradeProfitable(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Trade Profitable"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_planner_trade_profitable"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("planner_preview_trade_profitable"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "best_charge_time": data.get("planner_preview_best_charge_time"),
            "best_charge_price": data.get("planner_preview_best_charge_price"),
            "best_discharge_time": data.get("planner_preview_best_discharge_time"),
            "best_discharge_price": data.get("planner_preview_best_discharge_price"),
            "effective_charge_cost": data.get("planner_preview_effective_charge_cost"),
            "expected_trade_margin": data.get("planner_preview_expected_trade_margin"),
            "minimum_trade_margin": data.get("planner_preview_minimum_trade_margin"),
            "roundtrip_efficiency_percent": data.get("planner_preview_roundtrip_efficiency_percent"),
            "observational_only": True,
        }


class AnkerEmsAutoPlan72hValid(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Plan72 Valid"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_auto_plan_72h_valid"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("auto_plan_72h_valid"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "status": data.get("auto_plan_72h_status"),
            "reason": data.get("auto_plan_72h_reason"),
            "hours": data.get("auto_plan_72h_count"),
            "start": data.get("auto_plan_72h_start"),
            "end": data.get("auto_plan_72h_end"),
            "observational_only": data.get("auto_plan_72h_observational_only", True),
            "execution_enabled": data.get("auto_plan_72h_execution_enabled", False),
        }


class AnkerEmsAutoPlan72hExecutionBufferSafe(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Plan72 Execution Buffer Safe"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_auto_plan_72h_execution_buffer_safe"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("auto_plan_72h_execution_buffer_safe"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "buffer_percent": data.get("auto_plan_72h_execution_buffer_percent"),
            "execution_reserve_floor_soc": data.get("auto_plan_72h_execution_reserve_floor_soc"),
            "minimum_headroom_soc": data.get("auto_plan_72h_min_execution_headroom_soc"),
            "breach_hours": data.get("auto_plan_72h_execution_buffer_breach_hours"),
            "observational_only": data.get("auto_plan_72h_observational_only", True),
            "execution_enabled": data.get("auto_plan_72h_execution_enabled", False),
        }


class AnkerEmsAutoBridgeValid(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Action Bridge Valid"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_auto_bridge_valid"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("auto_bridge_valid"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "status": data.get("auto_bridge_status"),
            "reason": data.get("auto_bridge_reason"),
            "candidate_count": data.get("auto_bridge_candidate_count"),
            "slot_preview_count": data.get("auto_bridge_slot_preview_count"),
            "overflow_count": data.get("auto_bridge_overflow_count"),
            "manual_slot_conflict": data.get("auto_bridge_manual_slot_conflict", False),
            "plan_store_write_enabled": data.get("auto_bridge_plan_store_write_enabled", False),
            "plan_store_write_gate_open": data.get("auto_bridge_plan_store_write_gate_open", False),
            "plan_store_write_changed": data.get("auto_bridge_plan_store_write_changed", False),
            "plan_store_written_slots": data.get("auto_bridge_plan_store_written_slots", []),
            "plan_store_cleared_slots": data.get("auto_bridge_plan_store_cleared_slots", []),
            "plan_store_skipped_slots": data.get("auto_bridge_plan_store_skipped_slots", []),
            "expired_release_changed": data.get("auto_expired_release_changed", False),
            "expired_released_slots": data.get("auto_expired_released_slots", []),
            "scheduler_expired_slots": data.get("auto_expired_scheduler_slots", []),
            "scheduler_handoff_enabled": data.get("auto_bridge_scheduler_handoff_enabled", False),
            "scheduler_handoff_gate_open": data.get("auto_bridge_scheduler_handoff_gate_open", False),
            "scheduler_handoff_changed": data.get("auto_bridge_scheduler_handoff_changed", False),
            "scheduler_handoff_slots": data.get("auto_bridge_scheduler_handoff_slots", []),
            "scheduler_handoff_skipped_slots": data.get("auto_bridge_scheduler_handoff_skipped_slots", []),
            "prestart_enabled": data.get("auto_prestart_enabled", False),
            "prestart_required": data.get("auto_prestart_required", False),
            "prestart_safe": data.get("auto_prestart_safe", False),
            "prestart_status": data.get("auto_prestart_status"),
            "prestart_reason": data.get("auto_prestart_reason"),
            "prestart_reasons": data.get("auto_prestart_reasons", []),
            "prestart_warnings": data.get("auto_prestart_warnings", []),
            "prestart_selected_slot": data.get("auto_prestart_selected_slot"),
            "prestart_identity_match": data.get("auto_prestart_current_identity_match", False),
            "prestart_signature_match": data.get("auto_prestart_current_signature_match", False),
            "execution_enabled": data.get("auto_bridge_execution_enabled", False),
            "observational_only": data.get("auto_bridge_observational_only", True),
        }


class AnkerEmsAutomaticExecutionReady(_AnkerEmsBinarySensorBase):
    _attr_name = "Dummy OS EMS Automatic Execution Ready"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_automatic_execution_ready"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("auto_shadow_technical_ready"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "armed": data.get("auto_shadow_armed", False),
            "status": data.get("auto_shadow_status"),
            "blockers": data.get("auto_shadow_blockers", []),
            "warnings": data.get("auto_shadow_warnings", []),
            "selected_slot": data.get("auto_shadow_selected_slot"),
            "action": data.get("auto_shadow_action"),
            "purpose": data.get("auto_shadow_purpose"),
            "power_w": data.get("auto_shadow_power_w"),
            "target_soc": data.get("auto_shadow_target_soc"),
            "pre_mode_ready": data.get("auto_shadow_pre_mode_ready", False),
            "pre_mode_reason": data.get("auto_shadow_pre_mode_reason"),
            "post_mode_ready": data.get("auto_shadow_post_mode_ready", False),
            "post_mode_reason": data.get("auto_shadow_post_mode_reason"),
            "post_mode_required": data.get("auto_shadow_post_mode_required", False),
            "physical_execution_enabled": False,
        }
