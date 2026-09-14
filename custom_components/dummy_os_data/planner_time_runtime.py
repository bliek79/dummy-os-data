"""Main-thread snapshot helpers; no IO or physical control."""
from __future__ import annotations
from typing import Any
from .planner_time_contract import finite,utc
from .planner_soc_bridge import project_soc_to_window


def read_soc_bridge(coordinator:Any,snapshot:dict[str,Any],soc_contract:dict[str,Any]) -> dict[str,Any]:
    from .const import CONF_BATTERY_CHARGE_POWER_ENTITY,CONF_BATTERY_DISCHARGE_POWER_ENTITY
    powers=[]; provenance=[]
    for option,fallback in ((CONF_BATTERY_CHARGE_POWER_ENTITY,"sensor.do_source_battery_charge_power"),
                            (CONF_BATTERY_DISCHARGE_POWER_ENTITY,"sensor.do_source_battery_discharge_power")):
        entry=coordinator.entry
        entity_id=entry.options.get(option,entry.data.get(option)) or fallback
        state=coordinator.hass.states.get(entity_id)
        value=finite(state.state) if state else None
        unit=state.attributes.get("unit_of_measurement") if state else None
        if unit=="kW" and value is not None:
            value*=1000.0
        elif unit not in {"W","kW"}:
            value=None
        powers.append(value)
        provenance.append({"entity_id":entity_id,"unit":unit,
                           "last_updated":state.last_updated.isoformat() if state else None,
                           "last_reported":getattr(state,"last_reported",state.last_updated).isoformat() if state else None})
    result=project_soc_to_window(contract=snapshot["time_contract"],
        soc=soc_contract.get("soc_percent") if soc_contract.get("valid") is True else None,
        charge_power_w=powers[0],discharge_power_w=powers[1])
    result.update(soc_source_entity=soc_contract.get("source_entity"),
                  soc_source_last_updated=soc_contract.get("source_last_updated"),power_sources=provenance,
                  telemetry_caveat="State observed at reference; source report times retained, not assumed measurement time.")
    return result


def aligned_reference(input_result:dict[str,Any],fallback:Any) -> Any:
    contract=input_result.get("time_contract")
    return utc(contract["reference_utc"]) if isinstance(contract,dict) else fallback


def subscribe_upstream(entity:Any,unique_ids:list[str]) -> Any:
    from homeassistant.core import callback
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.event import async_track_state_change_event
    from .const import DOMAIN
    registry=er.async_get(entity.hass)
    ids=[registry.async_get_entity_id("sensor",DOMAIN,uid) for uid in unique_ids]
    ids=[i for i in ids if i]
    if not ids:
        return lambda:None

    # Home Assistant dispatches an undecorated synchronous event listener in an
    # executor thread.  _schedule_refresh() creates an asyncio task and therefore
    # must run on the HA event loop.  Mark the wrapper as a HA callback so the
    # event helper keeps this handoff on the event-loop thread.
    @callback
    def changed(_event:Any) -> None:
        entity._schedule_refresh()

    return async_track_state_change_event(entity.hass,ids,changed)


def subscribe_bridge_recovery(entity:Any) -> Any:
    """Retry missing bridge telemetry on recovery, not on every power sample."""
    from homeassistant.core import callback
    from homeassistant.helpers.event import async_track_state_change_event
    from .const import CONF_BATTERY_CHARGE_POWER_ENTITY,CONF_BATTERY_DISCHARGE_POWER_ENTITY
    entry=entity.coordinator.entry
    ids=[entry.options.get(k,entry.data.get(k)) or fallback for k,fallback in (
        (CONF_BATTERY_CHARGE_POWER_ENTITY,"sensor.do_source_battery_charge_power"),
        (CONF_BATTERY_DISCHARGE_POWER_ENTITY,"sensor.do_source_battery_discharge_power"))]

    @callback
    def changed(_event:Any) -> None:
        if getattr(entity,"_last_soc_bridge_valid",True) is False:
            entity._schedule_refresh()

    return async_track_state_change_event(entity.hass,ids,changed)
