"""Shadow-only lifecycle handoff buttons for Dummy OS Energy.

These buttons expose only the pre-execution part of the original EMS alpha76
``start_plan_now`` path: execution_mode -> direct, lifecycle -> pending,
then a runtime refresh. They deliberately stop before any Execution Controller
call and therefore cannot actuate the battery.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, NAME, VERSION
from .ems_alpha76.const import PLAN_SLOT_COUNT
from .ems_alpha76_runtime import get_ems_alpha76_runtime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = get_ems_alpha76_runtime(entry.runtime_data)
    if runtime is None:
        raise RuntimeError("Dummy OS EMS alpha76 shadow runtime is not initialized")
    async_add_entities(
        DummyOSAlpha76ShadowStartReadyButton(runtime, slot)
        for slot in range(1, PLAN_SLOT_COUNT + 1)
    )


class DummyOSAlpha76ShadowStartReadyButton(ButtonEntity):
    """Move one manual plan to alpha76 start-ready evaluation, shadow-only."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, runtime, slot: int) -> None:
        self.runtime = runtime
        self.slot = slot
        self._attr_name = f"DO Plan {slot} Shadow Start Ready"
        self._attr_unique_id = f"do_plan_{slot}_shadow_start_ready"
        self._attr_suggested_object_id = self._attr_unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "main")},
            name=NAME,
            manufacturer="Dummy OS",
            model="Energy Platform",
            sw_version=VERSION,
        )

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "ems_authority": "alpha76_plan_store",
            "alpha76_source_tag": "0.0.1-alpha.76",
            "shadow_only": True,
            "simulation_mode": True,
            "physical_execution_authority": False,
            "alpha76_physical_autostart_wired": False,
            "handoff_scope": "execution_mode_direct_then_lifecycle_pending_then_refresh",
            "execution_controller_called": False,
        }

    async def async_press(self) -> None:
        plan = self.runtime.plan_store.get_plan(self.slot)
        if plan.get("action") == "geen":
            raise HomeAssistantError(f"Plan {self.slot} heeft nog geen actie")

        # Exact pre-execution lifecycle of alpha76 start_plan_now.  Intentionally
        # stop before ``execution.async_execute_selected_plan()``.
        await self.runtime.plan_store.async_set_value(
            self.slot, "execution_mode", "direct"
        )
        await self.runtime.plan_store.async_mark_lifecycle(
            self.slot, "pending", "shadow_start_ready_validation"
        )
        await self.runtime.async_request_refresh()
