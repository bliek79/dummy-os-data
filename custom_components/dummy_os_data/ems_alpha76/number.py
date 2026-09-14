from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NAME, PLAN_SLOT_COUNT
from .coordinator import AnkerEmsCoordinator


@dataclass(frozen=True)
class PlanNumberDefinition:
    field: str
    label: str
    minimum: float
    maximum: float
    step: float
    unit: str | None = None


DEFINITIONS = (
    PlanNumberDefinition("power_w", "Power", 100, 3500, 100, UnitOfPower.WATT),
    PlanNumberDefinition("target_soc", "Target SOC", 5, 100, 1, PERCENTAGE),
    PlanNumberDefinition("max_runtime_h", "Maximum Runtime", 0.25, 12, 0.25, UnitOfTime.HOURS),
    PlanNumberDefinition("max_start_delay_min", "Maximum Start Delay", 1, 120, 1, UnitOfTime.MINUTES),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AnkerEmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AnkerEmsPlanNumber(coordinator, entry, slot, definition)
        for slot in range(1, PLAN_SLOT_COUNT + 1)
        for definition in DEFINITIONS
    )


class AnkerEmsPlanNumber(NumberEntity):
    _attr_has_entity_name = False
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: AnkerEmsCoordinator,
        entry: ConfigEntry,
        slot: int,
        definition: PlanNumberDefinition,
    ) -> None:
        self.coordinator = coordinator
        self.plan_store = coordinator.plan_store
        self.slot = slot
        self.definition = definition
        self._attr_name = f"Dummy OS EMS Plan {slot} {definition.label}"
        self._attr_unique_id = f"{entry.entry_id}_plan_{slot}_{definition.field}"
        self._attr_native_min_value = definition.minimum
        self._attr_native_max_value = (
            max(coordinator.max_charge_power_w, coordinator.max_discharge_power_w)
            if definition.field == "power_w"
            else definition.maximum
        )
        self._attr_native_step = definition.step
        self._attr_native_unit_of_measurement = definition.unit
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Dummy OS",
            model="EMS",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.plan_store.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> float:
        return float(self.plan_store.get_value(self.slot, self.definition.field))

    async def async_set_native_value(self, value: float) -> None:
        max_value = self.native_max_value
        if self.definition.field == "power_w":
            action = self.plan_store.get_value(self.slot, "action")
            max_value = self.coordinator.max_discharge_power_w if action == "ontladen" else self.coordinator.max_charge_power_w
        value = max(self.native_min_value, min(max_value, value))
        steps = round((value - self.native_min_value) / self.native_step)
        value = self.native_min_value + steps * self.native_step
        await self.plan_store.async_set_value(self.slot, self.definition.field, value)
