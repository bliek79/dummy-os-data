"""Parity coverage beyond Plan72: bridge, store, scheduler, gates and execution."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.dummy_os_data.ems_alpha76.action_controller import AnkerEmsActionController
from custom_components.dummy_os_data.ems_alpha76.const import DEFAULT_PLAN if False else PLAN_SLOT_COUNT
from custom_components.dummy_os_data.ems_alpha76.execution import AnkerEmsExecutionController
from custom_components.dummy_os_data.ems_alpha76.plan_store import AnkerEmsPlanStore, DEFAULT_PLAN
from custom_components.dummy_os_data.ems_alpha76.planner_action_bridge import build_planner_action_bridge
from custom_components.dummy_os_data.ems_alpha76.prestart_validator import AnkerEmsPreStartValidator
from custom_components.dummy_os_data.ems_alpha76.safety_guard import AnkerEmsSafetyGuard
from custom_components.dummy_os_data.ems_alpha76.scheduler import AnkerEmsScheduler

BASE = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)


class MemoryPlanStore:
    def __init__(self):
        self.plans={slot:deepcopy(DEFAULT_PLAN) for slot in range(1,4)}
        self.lifecycle=[]
    def get_plan(self,slot): return deepcopy(self.plans[slot])
    async def async_mark_lifecycle(self,slot,status,reason):
        self.plans[slot]["lifecycle_status"]=status
        self.plans[slot]["lifecycle_reason"]=reason
        self.lifecycle.append((slot,status,reason))


def automatic_plan(*, start=BASE, action="laden", purpose="veiligheidsladen", power=800, target=60.0):
    return {
        "action":action,"execution_mode":"gepland","start_time":start.isoformat(),
        "power_w":power,"target_soc":target,"max_runtime_h":1.0,
        "max_start_delay_min":10,"planned_energy_kwh":0.8,
        "planned_end_time":(start+timedelta(hours=1)).isoformat(),
        "lifecycle_status":"pending","lifecycle_reason":"test",
        "origin":"automatic_72h_planner","purpose":purpose,
        "planner_identity":"identity-1","planner_signature":"signature-1",
        "price_sources":["known"],"all_prices_known":True,
    }


def test_scheduler_exact_alpha76_priority_and_statuses():
    store=MemoryPlanStore()
    store.plans[1]=automatic_plan(start=BASE+timedelta(minutes=3))
    store.plans[2]=automatic_plan(start=BASE-timedelta(minutes=1),action="ontladen",purpose="handel_ontladen",target=40.0)
    store.plans[3]=deepcopy(DEFAULT_PLAN)
    scheduler=AnkerEmsScheduler(store)
    result=scheduler.evaluate(3200,3200,now=BASE)
    assert result["scheduler_status"]=="startklaar"
    assert result["scheduler_selected_slot"]==2
    assert result["scheduler_slots"][2]["status"]=="startklaar"
    assert result["scheduler_slots"][1]["status"]=="wachtend"
    assert result["scheduler_slots"][3]["status"]=="leeg"


def test_action_bridge_keeps_manual_slot_and_uses_alpha76_safety_threshold():
    manual=automatic_plan(start=BASE+timedelta(hours=4))
    manual.update({"origin":"manual","lifecycle_status":"pending","planner_identity":None,"planner_signature":None})
    scheduler_slots={
        1:{**manual,"status":"wachtend"},
        2:{**deepcopy(DEFAULT_PLAN),"status":"leeg"},
        3:{**deepcopy(DEFAULT_PLAN),"status":"leeg"},
    }
    plan=[{
        "time":BASE.isoformat(),"charge_from_grid_safety_kwh":0.099,
        "charge_from_grid_trade_kwh":0.0,"discharge_to_grid_kwh":0.0,
        "soc_start":20.0,"soc_end":21.0,"execution_reserve_floor_start_soc":12.0,
        "execution_reserve_floor_soc":12.0,"price":0.1,"price_source":"known",
    },{
        "time":(BASE+timedelta(hours=1)).isoformat(),"charge_from_grid_safety_kwh":0.2,
        "charge_from_grid_trade_kwh":0.0,"discharge_to_grid_kwh":0.0,
        "soc_start":21.0,"soc_end":23.5,"execution_reserve_floor_start_soc":12.0,
        "execution_reserve_floor_soc":12.0,"price":0.11,"price_source":"known",
    }]
    data={
        "auto_plan_72h_plan":plan,"auto_plan_72h_valid":True,
        "auto_plan_72h_execution_buffer_safe":True,"forecast_ready":True,
        "max_charge_power_w":3200,"max_discharge_power_w":3200,
        "battery_capacity_kwh":7.2,"charge_efficiency_percent":92.0,
        "discharge_efficiency_percent":92.0,"scheduler_slots":scheduler_slots,
    }
    result=build_planner_action_bridge(data,now=BASE-timedelta(minutes=1))
    assert result["auto_bridge_valid"] is True
    assert result["auto_bridge_suppressed_safety_charge_kwh"]==pytest.approx(0.099)
    assert result["auto_bridge_candidate_count"]==1
    proposal=result["auto_bridge_slot_preview"][0]
    assert proposal["purpose"]=="veiligheidsladen"
    assert proposal["suggested_slot"]==2
    assert proposal["plan_store_write_permitted"] is True


def gate_data(*, soc=50.0, action="laden", target=60.0):
    detail=automatic_plan(action=action,target=target,start=BASE)
    return {
        "scheduler_selected_slot":1,"scheduler_ready":True,"scheduler_slots":{1:detail},
        "auto_plan_72h_valid":True,"forecast_ready":True,
        "auto_plan_72h_execution_buffer_safe":True,"auto_bridge_invalid_candidate_count":0,
        "auto_bridge_valid":True,"auto_bridge_candidates":[{
            "planner_identity":"identity-1","planner_signature":"signature-1",
            "execution_reserve_start_soc":12.0,
        }],
        "auto_bridge_slot_preview":[],"soc":soc,"max_charge_power_w":3200,
        "max_discharge_power_w":3200,"control_path_configured":True,
        "physical_test_active":False,"execution_active":False,
        "operating_mode":"third_party_control","action_direction":"charge",
        "power_setpoint_w":0,"charge_power_w":0,"discharge_power_w":0,
    }


def test_prestart_safety_and_action_controller_preserve_alpha76_gates():
    data=gate_data()
    pre=AnkerEmsPreStartValidator().evaluate(data)
    data.update(pre)
    assert data["auto_prestart_required"] is True
    assert data["auto_prestart_safe"] is True
    safety=AnkerEmsSafetyGuard().evaluate_automatic_handoff(data)
    data.update(safety)
    assert data["auto_safety_handoff_safe"] is True
    # Legacy manual safety/controller path is also preserved.
    manual_safety=AnkerEmsSafetyGuard().evaluate(data)
    data.update(manual_safety)
    controller=AnkerEmsActionController().evaluate(data)
    assert controller["controller_ready"] is True
    assert controller["controller_action"]=="laden"
    assert controller["controller_power_w"]==800
    assert controller["controller_target_soc"]==60.0


def test_prestart_blocks_same_live_soc_direction_as_alpha76():
    data=gate_data(soc=65.0,action="laden",target=60.0)
    result=AnkerEmsPreStartValidator().evaluate(data)
    assert result["auto_prestart_safe"] is False
    assert "charge_target_already_reached" in result["auto_prestart_reasons"]


class FakeState:
    def __init__(self,state,last_changed):
        self.state=str(state); self.last_changed=last_changed; self.last_updated=last_changed
        self.attributes={}

class FakeStates:
    def __init__(self,values): self.values=values
    def get(self,eid): return self.values.get(eid)

class FakeServices:
    def __init__(self,hass,coordinator): self.calls=[]; self.hass=hass; self.coordinator=coordinator
    async def async_call(self,domain,service,data,target=None,blocking=True):
        eid=(target or {}).get("entity_id"); self.calls.append((domain,service,eid,dict(data)))
        now=BASE-timedelta(seconds=120)
        if domain=="select" and eid=="select.mode":
            option=data["option"]; self.hass.states.values[eid]=FakeState(option,now); self.coordinator.data["operating_mode"]=option
        elif domain=="select" and eid=="select.direction":
            option=data["option"]; self.hass.states.values[eid]=FakeState(option,now); self.coordinator.data["action_direction"]=option
        elif domain=="number" and eid=="number.power":
            value=data["value"]; self.hass.states.values[eid]=FakeState(value,now); self.coordinator.data["power_setpoint_w"]=value

class FakeHass:
    def __init__(self,states): self.states=FakeStates(states); self.services=None
    def async_create_task(self,coro,*args): return asyncio.create_task(coro)

class FakePhysical:
    data={"active":False}

class FakeCoordinator:
    def __init__(self,data,store):
        self.data=data; self.plan_store=store; self.physical_test=FakePhysical()
        self.control_entity_ids={"operating_mode":"select.mode","action_direction":"select.direction","power_setpoint":"number.power"}
    async def async_refresh(self): return None


@pytest.mark.asyncio
async def test_automatic_execution_exact_safe_order_and_safe_stop(monkeypatch):
    import custom_components.dummy_os_data.ems_alpha76.execution as execution_module
    async def no_sleep(_seconds): return None
    monkeypatch.setattr(execution_module.asyncio,"sleep",no_sleep)

    old=BASE-timedelta(seconds=120)
    states={
        "select.mode":FakeState("self_consumption",old),
        "select.direction":FakeState("charge",old),
        "number.power":FakeState(0,old),
    }
    store=MemoryPlanStore(); store.plans[1]=automatic_plan(start=BASE)
    data=gate_data(); data.update({
        "auto_shadow_execution_permitted":True,"auto_shadow_armed":True,
        "auto_final_revalidation_safe":True,"auto_mode_switch_preview_ready":True,
        "auto_final_revalidation_selected_slot":1,"execution_active":False,
        "physical_test_active":False,"operating_mode":"self_consumption",
        "battery_capacity_kwh":7.2,"charge_efficiency_percent":92.0,
        "discharge_efficiency_percent":92.0,
    })
    hass=FakeHass(states); coordinator=FakeCoordinator(data,store)
    hass.services=FakeServices(hass,coordinator)
    execution=AnkerEmsExecutionController(hass,"test")
    execution.attach_coordinator(coordinator)

    started=await execution.async_execute_automatic_plan("identity-1")
    assert started is True
    calls=hass.services.calls
    # If power was available in self_consumption the original code first pins 0 W,
    # then changes mode, pins 0 W again, chooses direction and finally applies power.
    assert calls[:5]==[
        ("number","set_value","number.power",{"value":0}),
        ("select","select_option","select.mode",{"option":"third_party_control"}),
        ("number","set_value","number.power",{"value":0}),
        ("select","select_option","select.direction",{"option":"charge"}),
        ("number","set_value","number.power",{"value":800}),
    ]
    assert store.lifecycle[-1]==(1,"actief","automatic_execution_running")

    await execution.async_stop("manual_stop",emergency=False)
    assert hass.services.calls[-2:]==[
        ("number","set_value","number.power",{"value":0}),
        ("select","select_option","select.mode",{"option":"self_consumption"}),
    ]
    assert store.lifecycle[-1]==(1,"geannuleerd","manual_stop")


@pytest.mark.asyncio
async def test_execution_monitor_emergency_stops_on_direction_change(monkeypatch):
    import custom_components.dummy_os_data.ems_alpha76.execution as execution_module
    async def no_sleep(_seconds): return None
    monkeypatch.setattr(execution_module.asyncio,"sleep",no_sleep)
    old=BASE-timedelta(seconds=120)
    states={"select.mode":FakeState("third_party_control",old),"select.direction":FakeState("discharge",old),"number.power":FakeState(800,old)}
    store=MemoryPlanStore(); store.plans[1]=automatic_plan(start=BASE)
    data=gate_data(); data.update({"operating_mode":"third_party_control","action_direction":"discharge","power_setpoint_w":800,"device_status":"ok","soc":50.0,"charge_power_w":0,"discharge_power_w":0})
    hass=FakeHass(states); coordinator=FakeCoordinator(data,store); hass.services=FakeServices(hass,coordinator)
    execution=AnkerEmsExecutionController(hass,"test"); execution.attach_coordinator(coordinator)
    execution._state.update({"active":True,"status":"running","slot":1,"origin":"automatic_72h_planner","action":"laden","power_w":800,"target_soc":60.0,"max_runtime_h":1.0,"stop_at":(BASE+timedelta(hours=1)).isoformat()})
    await execution._async_monitor_once()
    assert execution.data["active"] is False
    assert execution.data["last_result"]=="emergency_stopped"
    assert execution.data["reason"]=="direction_changed"
    assert hass.services.calls[-2:]==[
        ("number","set_value","number.power",{"value":0}),
        ("select","select_option","select.mode",{"option":"self_consumption"}),
    ]
