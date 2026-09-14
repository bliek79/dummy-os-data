from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import AnkerEmsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AnkerEmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AnkerEmsAutomaticExecutionArm(coordinator, entry)])


class AnkerEmsAutomaticExecutionArm(
    CoordinatorEntity[AnkerEmsCoordinator], RestoreEntity, SwitchEntity
):
    """Fail-safe arm switch for automatic physical execution.

    Alpha54: ON explicitly permits a fully validated automatic planner action
    to reach the physical Execution Controller. OFF closes the gate and also
    safe-stops a currently running automatic planner execution.
    """

    _attr_name = "Dummy OS EMS Automatic Execution"
    _attr_icon = "mdi:robot"

    def __init__(self, coordinator: AnkerEmsCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_unique_id = f"{entry.entry_id}_automatic_execution_arm"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Dummy OS",
            model="EMS",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.auto_execution_armed

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        previous = await self.async_get_last_state()
        # Fail-safe migration from the former shadow-only arm: an ON state from
        # alpha51-alpha53 must never silently become a physical-live arm after
        # upgrading. Only a state previously saved by the live_guarded switch
        # itself is restored as ON. The first alpha54 start therefore requires
        # one explicit user re-arm.
        armed = bool(
            previous is not None
            and previous.state == "on"
            and previous.attributes.get("mode") == "live_guarded"
        )
        await self.coordinator.async_set_auto_execution_armed(armed)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_auto_execution_armed(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_auto_execution_armed(False)
        execution = self.coordinator.execution.data
        if (
            execution.get("active")
            and execution.get("origin") == "automatic_72h_planner"
        ):
            await self.coordinator.execution.async_stop(
                "automatic_execution_disarmed", emergency=False
            )
        elif execution.get("auto_mode_switch_active"):
            await self.coordinator.execution.async_abort_automatic_arming(
                "automatic_execution_disarmed"
            )

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data or {}
        return {
            "mode": "live_guarded",
            "technical_ready": data.get("auto_shadow_technical_ready", False),
            "execution_status": data.get("auto_shadow_status"),
            "blockers": data.get("auto_shadow_blockers", []),
            "physical_execution_enabled": True,
            "execution_permitted": data.get("auto_shadow_execution_permitted", False),
        }
