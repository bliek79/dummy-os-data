from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NAME, PLAN_SLOT_COUNT
from .coordinator import AnkerEmsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AnkerEmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AnkerEmsPlanStartTime(coordinator, entry, slot)
        for slot in range(1, PLAN_SLOT_COUNT + 1)
    )


class AnkerEmsPlanStartTime(DateTimeEntity):
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: AnkerEmsCoordinator,
        entry: ConfigEntry,
        slot: int,
    ) -> None:
        self.coordinator = coordinator
        self.plan_store = coordinator.plan_store
        self.slot = slot
        self._attr_name = f"Dummy OS EMS Plan {slot} Start"
        self._attr_unique_id = f"{entry.entry_id}_plan_{slot}_start_time"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Dummy OS",
            model="EMS",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.plan_store.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> datetime | None:
        value = self.plan_store.get_value(self.slot, "start_time")
        if not value:
            return None
        parsed = dt_util.parse_datetime(str(value))
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return parsed

    async def async_set_value(self, value: datetime) -> None:
        await self.plan_store.async_set_value(self.slot, "start_time", value)
