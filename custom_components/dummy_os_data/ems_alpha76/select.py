from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NAME, PLAN_SLOT_COUNT
from .coordinator import AnkerEmsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AnkerEmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = []
    for slot in range(1, PLAN_SLOT_COUNT + 1):
        entities.extend(
            [
                AnkerEmsPlanSelect(
                    coordinator,
                    entry,
                    slot,
                    "action",
                    "Action",
                    ["geen", "laden", "ontladen"],
                ),
                AnkerEmsPlanSelect(
                    coordinator,
                    entry,
                    slot,
                    "execution_mode",
                    "Mode",
                    ["direct", "gepland"],
                ),
            ]
        )
    async_add_entities(entities)


class AnkerEmsPlanSelect(SelectEntity):
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: AnkerEmsCoordinator,
        entry: ConfigEntry,
        slot: int,
        field: str,
        label: str,
        options: list[str],
    ) -> None:
        self.coordinator = coordinator
        self.plan_store = coordinator.plan_store
        self.slot = slot
        self.field = field
        self._attr_name = f"Dummy OS EMS Plan {slot} {label}"
        self._attr_unique_id = f"{entry.entry_id}_plan_{slot}_{field}"
        self._attr_options = options
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Dummy OS",
            model="EMS",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.plan_store.add_listener(self.async_write_ha_state))

    @property
    def current_option(self) -> str | None:
        value = self.plan_store.get_value(self.slot, self.field)
        return value if value in self.options else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError(f"Unsupported option: {option}")
        await self.plan_store.async_set_value(self.slot, self.field, option)
