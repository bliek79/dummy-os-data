"""Apply reviewed adapter changes to Alpha34; temporary build helper."""
from pathlib import Path
import ast
import json
import re
C=Path('custom_components/dummy_os_data')
assert json.loads((C/'manifest.json').read_text())['version']=='0.2.0-alpha.34'

def change(name,old,new,count=1):
    p=C/name; s=p.read_text()
    assert s.count(old)==count,(name,old[:100],s.count(old))
    p.write_text(s.replace(old,new))

def replace_def(name,target,body,cls=None):
    p=C/name; s=p.read_text(); nodes=ast.parse(s).body
    if cls: nodes=next(n for n in nodes if isinstance(n,ast.ClassDef) and n.name==cls).body
    n=next(n for n in nodes if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==target)
    lines=s.splitlines(keepends=True); lines[n.lineno-1:n.end_lineno]=[body.rstrip()+'\n']; p.write_text(''.join(lines))

def wrap(name,target,body):
    p=C/name; s=p.read_text(); old='def '+target+'('
    assert s.count(old)==1
    p.write_text(s.replace(old,'def _legacy_'+target+'(',1)+'\n\n'+body.rstrip()+'\n')

change('forecast.py','        slot_count: int = FORECAST_SLOTS,','        slot_count: int = FORECAST_SLOTS,\n        window_start: datetime | None = None,')
change('forecast.py','from .const import FORECAST_SLOTS, PROFILE_LEARNING_OPTIONS, QUARTER_MINUTES','from .const import FORECAST_SLOTS, PROFILE_LEARNING_OPTIONS, QUARTER_MINUTES\nfrom .planner_time_contract import ceil_quarter, floor_quarter, utc')
change('forecast.py','''        now_local = dt_util.as_local(now_utc)
        minute = (now_local.minute // QUARTER_MINUTES) * QUARTER_MINUTES
        next_local = now_local.replace(minute=minute, second=0, microsecond=0) + timedelta(
            minutes=QUARTER_MINUTES
        )
        start_utc = dt_util.as_utc(next_local)''','''        start_utc = utc(window_start) if window_start is not None else ceil_quarter(now_utc)
        if start_utc != floor_quarter(start_utc):
            raise ValueError("forecast window start must be quarter-aligned")''')
change('prices.py','_LOGGER = logging.getLogger(__name__)','from .planner_time_contract import build_time_contract, select_points, utc\n\n_LOGGER = logging.getLogger(__name__)')
change('prices.py','planner_start = self._next_complete_local_hour(current_quarter)','planner_start = utc(build_time_contract(dt_util.utcnow())["window_start"])')
replace_def('prices.py','planner_points','''    def planner_points(self) -> list[PricePoint]:
        """Compatibility view; production supplies one captured time contract."""
        return self.planner_points_for_window(build_time_contract(dt_util.utcnow()))

    def planner_points_for_window(self, contract: dict[str, Any], *, include_neighbours: bool = False) -> list[PricePoint]:
        """Select the caller's exact window without an independent clock read."""
        start = utc(contract["window_start"])
        selected, missing = _select_exact_price_window(self._price_buffer_by_start, start=start, slot_count=PLANNER_PRICE_SLOT_COUNT)
        self._planner_points = selected
        self.planner_price_missing_starts = missing
        self.planner_window_start = start
        self.planner_window_end = utc(contract["window_end"])
        self.planner_price_valid_slots = len(selected)
        self.planner_price_missing_slots = len(missing)
        self._planner_time_contract = dict(contract)
        return select_points(self._price_buffer_by_start.values(), contract, neighbours=include_neighbours)''',cls='DummyOSPricesCoordinator')
change('prices.py','            "planner_price_expected_slots": PLANNER_PRICE_SLOT_COUNT,','            "planner_time_contract": getattr(self, "_planner_time_contract", None),\n            "planner_price_expected_slots": PLANNER_PRICE_SLOT_COUNT,')
change('solar.py','    @property\n    def source_point_count','''    def planner_points_for_window(self, contract: dict[str, Any]) -> list[SolarPoint]:
        """Select the supplied window from the retained source buffer."""
        from .planner_time_contract import select_points
        return select_points(self._source_points, contract)

    @property
    def source_point_count''')
change('solar.py','"timezone": OPEN_METEO_SOLAR_TIMEZONE,','"timezone": "UTC",')
change('solar.py','timezone = ZoneInfo(OPEN_METEO_SOLAR_TIMEZONE)','timezone = ZoneInfo(str(payload.get("timezone") or OPEN_METEO_SOLAR_TIMEZONE))')
change('solar_model.py','from datetime import datetime, timedelta','from datetime import datetime, timedelta, timezone')
replace_def('solar_model.py','next_complete_slot','''def next_complete_slot(timestamp: datetime, resolution_minutes: int = 15) -> datetime:
    """Elapsed-time UTC arithmetic, preserving local offset only for presentation."""
    if timestamp.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    reference = timestamp.astimezone(timezone.utc)
    floor = floor_slot_start(reference, resolution_minutes)
    result = floor if reference == floor else floor + timedelta(minutes=resolution_minutes)
    return result.astimezone(timestamp.tzinfo)''')
change('sensor.py','from .forecast import HomeBaselineForecast','from .forecast import HomeBaselineForecast\nfrom .planner_time_contract import build_time_contract, utc\nfrom .planner_time_views import forecast_transport\nfrom .planner_time_runtime import read_soc_bridge, subscribe_bridge_recovery')
replace_def('sensor.py','_planner_runtime_snapshot','''def _planner_runtime_snapshot(
    coordinator: DummyOSHomeDataCoordinator,
    *,
    now: datetime | None = None,
    soc_percent: float | None = None,
) -> dict[str, Any]:
    """Capture time once before selecting all planner sources on the HA thread."""
    reference = utc(now or dt_util.utcnow())
    contract = build_time_contract(reference)
    return {
        "records": list(coordinator.records),
        "evaluations": list(coordinator.evaluations),
        "horizon_daily_stats": dict(coordinator.horizon_daily_stats),
        "profile": coordinator.profile,
        "source_available": coordinator.source_available,
        "solar_points": list(coordinator.solar.planner_points_for_window(contract)),
        "price_points": list(coordinator.prices.planner_points_for_window(contract, include_neighbours=True)),
        "solar_status": coordinator.solar.source_status,
        "prices_status": coordinator.prices.status,
        "prices_freshness": coordinator.prices.freshness,
        "now": reference,
        "soc_percent": soc_percent,
        "time_contract": contract,
    }''')
replace_def('sensor.py','_build_planner_hours_from_snapshot','''def _build_planner_hours_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    reference = snapshot["now"]
    contract = snapshot.get("time_contract") or build_time_contract(reference)
    profile = snapshot["profile"]
    slots = HomeBaselineForecast(snapshot["records"]).build(
        profile, now=reference, slot_count=FORECAST_SLOTS, window_start=utc(contract["window_start"])
    )
    result = forecast_transport(slots, profile=profile, contract=contract)
    if profile not in PROFILE_LEARNING_OPTIONS:
        result["status"] = "profile_unclassified"
    return result''')
replace_def('sensor.py','_forecast','''    def _forecast(self):
        reference = dt_util.utcnow()
        contract = build_time_contract(reference)
        key = (self.coordinator.profile, len(self.coordinator.records), contract["window_id"])
        if key != self._forecast_cache_key:
            self._forecast_cache = HomeBaselineForecast(self.coordinator.records).build(
                self.coordinator.profile, now=reference, window_start=utc(contract["window_start"])
            )
            self._forecast_cache_key = key
        return self._forecast_cache or []''',cls='DummyOSBaseSensor')
replace_def('sensor.py','_snapshot','''    def _snapshot(self) -> dict[str, Any]:
        reference = dt_util.utcnow()
        contract = get_do_plan_soc_contract_runtime(self.coordinator).result(now=reference)
        snapshot = _planner_runtime_snapshot(self.coordinator, now=reference, soc_percent=contract.get("soc_percent"))
        bridge = read_soc_bridge(self.coordinator, snapshot, contract)
        self._last_soc_bridge_valid = bridge["valid"]
        snapshot["soc_bridge"] = bridge
        snapshot["soc_percent"] = bridge.get("planner_start_soc_percent") if bridge["valid"] else None
        snapshot["soc_source_entity"] = "runtime:do_plan_soc_contract_v1"
        snapshot["soc_contract_entity"] = self.SOC_ENTITY
        snapshot["soc_contract_status"] = contract.get("status")
        snapshot["soc_contract_valid"] = contract.get("valid")
        snapshot["soc_raw_source_entity"] = contract.get("source_entity")
        return snapshot''',cls='DummyOSPlanEnergyNeedSensor')
change('sensor.py','    result["soc_source_entity"] = snapshot.get("soc_source_entity", "sensor.do_plan_soc_contract")','''    result["soc_bridge"] = snapshot.get("soc_bridge")
    if snapshot.get("soc_bridge") is not None:
        result["measured_soc_percent"] = snapshot["soc_bridge"].get("measured_soc_percent")
        result["planner_start_soc_percent"] = snapshot["soc_bridge"].get("planner_start_soc_percent")
        result["soc_time_basis"] = "planner_window_start_estimate"
    result["soc_source_entity"] = snapshot.get("soc_source_entity", "sensor.do_plan_soc_contract")''')
change('sensor.py','        self._remove_soc_listener = None','        self._remove_soc_listener = None\n        self._remove_bridge_recovery = None')
change('sensor.py','        self._remove_soc_listener = async_track_state_change_event(','        self._remove_bridge_recovery = subscribe_bridge_recovery(self)\n        self._remove_soc_listener = async_track_state_change_event(')
change('sensor.py','        if self._remove_soc_listener is not None:','        if self._remove_bridge_recovery is not None:\n            self._remove_bridge_recovery()\n        if self._remove_soc_listener is not None:')
change('sensor.py','''            self._cached_result = result
            self.async_write_ha_state()
            if not self._refresh_pending:
                return

    def _snapshot(self)''','''            contract = result.get("time_contract")
            if contract and contract["window_id"] != build_time_contract(dt_util.utcnow())["window_id"]:
                result = {**result, "status": "stale", "valid": False,
                          "reason": "planner_window_elapsed", "blockers": ["planner_window_elapsed"],
                          "time_alignment_current": False}
                if snapshot.get("time_contract") is not None:
                    self._refresh_pending = True
            else:
                result["time_alignment_current"] = True
            self._cached_result = result
            self.async_write_ha_state()
            if not self._refresh_pending:
                return

    def _snapshot(self)''')
change('sensor.py','_unrecorded_attributes = frozenset({"rows"})','_unrecorded_attributes = frozenset({"rows", "slots", "source_time_audit"})')
change('forecast_planner_contract.py','''    for field in _READINESS_FIELDS:
        result[field] = model_health.get(field)
    return result''','''    for field in _READINESS_FIELDS:
        result[field] = model_health.get(field)
    if planner_hours.get("time_contract") is not None:
        from custom_components.dummy_os_data.planner_time_contract import time_fields
        result.update(time_fields(planner_hours["time_contract"]))
        result["planner_resolution_minutes"] = 15
        result["transport_resolution_minutes"] = 60
        result["hour_grouping"] = "window_relative_transport_not_apex"
    return result''')
change('do_plan_input.py','if contract.get("planner_resolution_minutes") != PLANNER_RESOLUTION_MINUTES:','if contract.get("planner_resolution_minutes") != (15 if contract.get("time_contract") is not None else PLANNER_RESOLUTION_MINUTES):')
wrap('do_plan_input.py','build_do_plan_input_72h','''def build_do_plan_input_72h(**kwargs: Any) -> dict[str, Any]:
    from custom_components.dummy_os_data.planner_time_contract import validate_time_contract
    from custom_components.dummy_os_data.planner_time_input import normalize_source, finalize_time_input
    time_contract = kwargs.get("contract", {}).get("time_contract")
    if time_contract is None:
        return _legacy_build_do_plan_input_72h(**kwargs)
    errors = validate_time_contract(time_contract)
    if errors:
        return {"status": "blocked", "valid": False, "blockers": errors, "rows": [], "slots": []}
    solar, solar_audit = normalize_source(list(kwargs["solar_points"]), price=False)
    prices, price_audit = normalize_source(list(kwargs["price_points"]), price=True)
    result = _legacy_build_do_plan_input_72h(**{**kwargs, "solar_points": solar, "price_points": prices})
    return finalize_time_input(result, time_contract, {"solar": solar_audit, "prices": price_audit})''')
change('do_plan_energy_need.py','    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)','''    if input_result.get("time_contract") is not None:
        from custom_components.dummy_os_data.planner_native_need import build_native_energy_need
        return build_native_energy_need(input_result=input_result, base=base, soc=soc, capacity=capacity,
                                        min_soc=min_soc, reserve_percent=reserve_percent)
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)''')
wrap('do_plan_energy_need.py','build_do_plan_energy_need','''def build_do_plan_energy_need(**kwargs: Any) -> dict[str, Any]:
    from custom_components.dummy_os_data.planner_time_contract import propagate_time
    return propagate_time(_legacy_build_do_plan_energy_need(**kwargs), kwargs["input_result"])''')
wrap('do_plan_reserve_soc.py','build_do_plan_reserve_soc','''def build_do_plan_reserve_soc(**kwargs: Any) -> dict[str, Any]:
    from custom_components.dummy_os_data.planner_time_contract import propagate_time
    need = kwargs["energy_need_result"]
    result = propagate_time(_legacy_build_do_plan_reserve_soc(**kwargs), need)
    for key in ("soc_bridge", "measured_soc_percent", "planner_start_soc_percent", "soc_time_basis"):
        if key in need:
            result[key] = need[key]
    return result''')
wrap('do_plan_preview.py','build_do_plan_preview','''def build_do_plan_preview(**kwargs: Any) -> dict[str, Any]:
    from custom_components.dummy_os_data.planner_time_contract import propagate_time, window_errors
    sources = (kwargs["input_result"], kwargs["reserve_result"])
    errors = window_errors(*sources)
    result = {"status": "blocked", "valid": False, "blockers": errors} if errors else _legacy_build_do_plan_preview(**kwargs)
    return propagate_time(result, *sources)''')
wrap('do_plan_grid_support.py','build_do_plan_grid_support','''def build_do_plan_grid_support(**kwargs: Any) -> dict[str, Any]:
    from custom_components.dummy_os_data.planner_time_contract import propagate_time, window_errors
    sources = [kwargs["input_result"]]
    for key in ("energy_need_result", "reserve_result"):
        if kwargs.get(key) is not None:
            sources.append(kwargs[key])
    errors = window_errors(*sources)
    result = {"status": "blocked", "valid": False, "blockers": errors, "selected_charge_slots": []} if errors else _legacy_build_do_plan_grid_support(**kwargs)
    return propagate_time(result, *sources)''')
wrap('do_plan_72h.py','build_do_plan_72h','''def build_do_plan_72h(**kwargs: Any) -> dict[str, Any]:
    from custom_components.dummy_os_data.planner_time_contract import propagate_time, window_errors, finite
    from custom_components.dummy_os_data.planner_time_views import aggregate_clock_hours
    sources = (kwargs["input_result"], kwargs["reserve_result"], kwargs["preview_result"])
    errors = window_errors(*sources)
    contract = sources[0].get("time_contract")
    bridge = sources[1].get("soc_bridge")
    if contract is not None and (not isinstance(bridge, dict) or bridge.get("valid") is not True
                                 or bridge.get("projected_at") != contract.get("window_start")
                                 or finite(bridge.get("planner_start_soc_percent")) is None):
        errors.append("planner_start_soc_not_aligned")
    if errors:
        return propagate_time({"status": "blocked", "valid": False, "reason": errors[0], "blockers": errors,
                               "slots": [], "hours": [], "slot_count": 0, "hour_count": 0,
                               "shadow_only": True, "physical_execution_authority": False,
                               "active_use_permitted": False}, *sources)
    if contract is not None:
        kwargs = {**kwargs, "reserve_result": {**sources[1], "soc_percent": bridge["planner_start_soc_percent"]}}
    result = propagate_time(_legacy_build_do_plan_72h(**kwargs), *sources)
    if contract is not None:
        result["soc_bridge"] = bridge
        result["measured_soc_percent"] = sources[1].get("measured_soc_percent")
        result["planner_start_soc_percent"] = bridge["planner_start_soc_percent"]
        result["soc_time_basis"] = "planner_window_start_estimate"
        result["transport_hour_count"] = len(result.get("hours") or [])
        result["hours"] = aggregate_clock_hours(result.get("slots") or [])
        result["hour_count"] = result["dashboard_hour_count"] = len(result["hours"])
        result["simulated_hour_count"] = len(result.get("slots") or []) / 4
        result["apex_contract"] = "utc_clock_hour_aggregation_with_explicit_partial_edges"
        result["dashboard_start"] = contract["window_start"]
        result["dashboard_end"] = contract["window_end"]
        result["baseline_hours_grouping"] = "window_relative_transport_not_apex"
    return result''')
wrap('do_plan_store_bridge.py','build_do_plan_store_bridge','''def build_do_plan_store_bridge(**kwargs: Any) -> dict[str, Any]:
    from custom_components.dummy_os_data.planner_time_contract import propagate_time
    return propagate_time(_legacy_build_do_plan_store_bridge(**kwargs), kwargs["plan72_result"])''')
change('do_plan_native_common.py','''    remainder = first_candidate % SLOTS_PER_HOUR
    if remainder:
        first_candidate += SLOTS_PER_HOUR - remainder
    for candidate in range(first_candidate, last_candidate + 1, SLOTS_PER_HOUR):
        if _is_usable_solar_window(slots, candidate)''','''    for candidate in range(first_candidate, last_candidate + 1):
        candidate_start = _utc(slots[candidate]["start"])
        if candidate_start is None or candidate_start.minute != 0:
            continue
        if _is_usable_solar_window(slots, candidate)''')
for name,cname,ids in [('do_plan_preview_sensor.py','DummyOSPlanPreviewSensor',['do_plan_input_72h','do_plan_reserve_soc']),('do_plan_grid_support_sensor.py','DummyOSPlanGridSupportSensor',['do_plan_input_72h','do_plan_energy_need','do_plan_reserve_soc'])]:
    p=C/name; s=p.read_text()
    s=s.replace('from typing import Any','from typing import Any\nfrom .planner_time_runtime import aligned_reference, subscribe_upstream',1)
    pos=s.index('\n',s.index('    class '+cname))+1
    methods=f'''        async def async_added_to_hass(self) -> None:
            await super().async_added_to_hass()
            self._remove_aligned_upstream = subscribe_upstream(self, {ids!r})

        async def async_will_remove_from_hass(self) -> None:
            remove = getattr(self, "_remove_aligned_upstream", None)
            if remove is not None:
                remove()
            await super().async_will_remove_from_hass()

'''
    s=s[:pos]+methods+s[pos:]
    s=s.replace('"now": dt_util.utcnow(), "input_entity"','"now": aligned_reference(input_result, dt_util.utcnow()), "input_entity"')
    s=s.replace('"now":dt_util.utcnow(),"input_entity"','"now":aligned_reference(input_result, dt_util.utcnow()),"input_entity"')
    p.write_text(s)
change('do_plan_grid_support_sensor.py','material={"quarter":quarter,','material={"window_id": (snapshot.get("time_contract") or {}).get("window_id"),"soc_bridge":snapshot.get("soc_bridge"),"quarter":quarter,')
change('do_plan_grid_support_sensor.py','from .const import DOMAIN','from .const import DOMAIN\nfrom .planner_time_contract import build_time_contract')
change('do_plan_grid_support_sensor.py','result=await self.hass.async_add_executor_job(self._calculate_result,snapshot); await runtime.async_ensure_loaded(); candidates=result.get("candidates") if result.get("status")=="ready" else []','''result=await self.hass.async_add_executor_job(self._calculate_result,snapshot)
                await runtime.async_ensure_loaded()
                if result.get("window_id") and result["window_id"] != build_time_contract(dt_util.utcnow())["window_id"]:
                    self._cached_result = {**result, "status": "stale", "valid": False,
                                           "blockers": ["planner_window_elapsed"],
                                           "reason": "planner_window_elapsed", "store_changed": False}
                    self.async_write_ha_state()
                    continue
                candidates=result.get("candidates") if result.get("status")=="ready" else []''')
p=C/'do_plan_72h_sensor.py'; s=p.read_text(); s=s.replace('"hours", "slots", "baseline", "candidate"','"hours", "slots", "baseline", "candidate", "soc_bridge"'); p.write_text(s)
# Update obsolete literal API assertions, preserving isolation/Recorder checks.
p=Path('tests/test_pre_step5_planner_main_thread_fix.py');s=p.read_text().replace('"solar_points": list(coordinator.solar.planner_points)','"solar_points": list(coordinator.solar.planner_points_for_window(contract))').replace('"price_points": list(coordinator.prices.planner_points)','"price_points": list(coordinator.prices.planner_points_for_window(contract, include_neighbours=True))');p.write_text(s)
p=Path('tests/test_do_plan_sensor_contract.py');s=p.read_text().replace('frozenset({"rows"})','frozenset({"rows", "slots", "source_time_audit"})');p.write_text(s)
p=Path('tests/test_release_consistency.py');s=re.sub(r'_CORE.VERSION = "0.2.0-alpha.\d+"','_CORE.VERSION = "0.2.0-alpha.35"',p.read_text());p.write_text(s)
change('const.py','VERSION = "0.2.0-alpha.34"','VERSION = "0.2.0-alpha.35"')
p=C/'manifest.json';v=json.loads(p.read_text());v['version']='0.2.0-alpha.35';p.write_text(json.dumps(v,indent=2)+'\n')
print('Alpha35 adapter changes applied to Alpha34')
