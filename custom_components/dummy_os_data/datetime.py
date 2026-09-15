"""Datetime entities for Dummy OS Energy."""
from __future__ import annotations
from datetime import datetime
from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from .const import DOMAIN, NAME, VERSION
from .ems_alpha76_surface import build_alpha76_plan_datetime_entities
from .presence import parse_aware_datetime
from .presence_runtime import async_get_presence_runtime

async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry,async_add_entities:AddConfigEntryEntitiesCallback)->None:
    coordinator=entry.runtime_data
    presence_runtime=await async_get_presence_runtime(coordinator)
    async_add_entities([
        DummyOSPresenceAwayStart(presence_runtime),
        DummyOSPresenceAwayEnd(presence_runtime),
        *build_alpha76_plan_datetime_entities(coordinator),
    ])

class _PresenceDateTime(DateTimeEntity):
    _attr_should_poll=False; _attr_has_entity_name=False
    def __init__(self,runtime)->None: self.runtime=runtime; self._remove_listener=None
    @property
    def device_info(self)->DeviceInfo: return DeviceInfo(identifiers={(DOMAIN,"main")},name=NAME,manufacturer="Dummy OS",model="Energy Platform",sw_version=VERSION)
    async def async_added_to_hass(self)->None:
        await super().async_added_to_hass(); self.runtime.canonicalize_control_entity("datetime",self._attr_unique_id,self.entity_id); self._remove_listener=self.runtime.add_listener(self._handle_update)
    async def async_will_remove_from_hass(self)->None:
        if self._remove_listener is not None: self._remove_listener()
        await super().async_will_remove_from_hass()
    @callback
    def _handle_update(self)->None: self.async_write_ha_state()

class DummyOSPresenceAwayStart(_PresenceDateTime):
    _attr_name="DO Presence Away Start"; _attr_unique_id="do_presence_away_start"; _attr_suggested_object_id="do_presence_away_start"; _attr_icon="mdi:calendar-start"
    @property
    def native_value(self)->datetime|None:
        value=parse_aware_datetime(self.runtime.schedule_start); return dt_util.as_local(value) if value is not None else None
    async def async_set_value(self,value:datetime)->None: await self.runtime.async_set_start(value)

class DummyOSPresenceAwayEnd(_PresenceDateTime):
    _attr_name="DO Presence Away End"; _attr_unique_id="do_presence_away_end"; _attr_suggested_object_id="do_presence_away_end"; _attr_icon="mdi:calendar-end"
    @property
    def native_value(self)->datetime|None:
        value=parse_aware_datetime(self.runtime.schedule_end); return dt_util.as_local(value) if value is not None else None
    async def async_set_value(self,value:datetime)->None: await self.runtime.async_set_end(value)
