"""Safety deadlines must use storage after previous consumption, not start-SOC."""
from datetime import datetime, timedelta, timezone
import pytest
from custom_components.dummy_os_data.do_plan_72h import build_do_plan_72h


def native_case(start_soc=94.0):
    """Deterministic three-day regression, not the user's incomplete live dump."""
    start = datetime(2026, 9, 13, 18, tzinfo=timezone.utc)
    rows = []
    for h in range(72):
        hs = start + timedelta(hours=h)
        home = []; solar = []; prices = []
        for q in range(4):
            t = hs + timedelta(minutes=15*q)
            home.append({'start':t.isoformat(), 'end':(t+timedelta(minutes=15)).isoformat(), 'kwh':0.10})
            solar.append({'start':t.isoformat(), 'kwh':0.12 if 12 <= h % 24 < 16 else 0.0})
            prices.append({'start':t.isoformat(), 'import_price':0.2 + (h % 24)*0.001, 'export_price':0.05, 'kind':'known_pt15m', 'source_resolution_minutes':15})
        rows.append({'index':h, 'start':hs.isoformat(), 'end':(hs+timedelta(hours=1)).isoformat(), 'fully_valid':True, 'home_quarters_valid':True, 'home_quarters':home, 'solar_quarters':solar, 'price_quarters':prices, 'home_kwh':sum(v['kwh'] for v in home), 'solar_kwh':sum(v['kwh'] for v in solar), 'import_price':prices[0]['import_price'], 'export_price':0.05})
    inp = {'status':'ready', 'fully_valid_hours':72, 'effective_horizon_hours':72, 'rows_signature':'alpha34', 'valid_through':rows[-1]['end'], 'rows':rows}
    reserve = {'status':'ready','valid':True,'input_rows_signature':'alpha34','soc_percent':start_soc,'reserve_soc_target_percent':100.0}
    preview = {'status':'ready','valid':True,'input_rows_signature':'alpha34','safety_charge_hours':[],'minimum_trade_margin':0.1}
    return inp, reserve, preview


def test_second_and_third_reserve_peaks_are_actually_reachable():
    inp, reserve, preview = native_case()
    out = build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    assert out['slot_count'] == 288 and out['hour_count'] == 72
    assert out['valid'] is True, (out['status'], out['minimum_execution_headroom_soc_percent'])
    assert out['candidate']['reserve_breach_slots'] == 0
    assert out['candidate']['execution_buffer_breach_slots'] == 0
    assert min(s['execution_headroom_soc_percent'] for s in out['slots']) >= -0.002
    assert sum(s['grid_to_battery_safety_kwh'] for s in out['slots'][96:]) > 0.1

from custom_components.dummy_os_data.do_plan_native_common import _expand_native_slots, _dynamic_reserve_profile
from custom_components.dummy_os_data.do_plan_native_safety import build_native_safety_plan
from custom_components.dummy_os_data.do_plan_native_simulation import _simulate
from custom_components.dummy_os_data.do_plan_grid_support import build_do_plan_grid_support


def controlled_case(count=12, deadline=5, target=5.0, start_soc=20.0):
    inp, _, _ = native_case(start_soc)
    slots, errors, _ = _expand_native_slots(inp['rows'], 72)
    assert not errors
    slots = slots[:count]
    for index, slot in enumerate(slots):
        slot['home_kwh'] = 0.1
        slot['solar_kwh'] = 0.0
        slot['import_price'] = 0.3
    profile = [{'execution_floor_kwh':target if i == deadline else 1.008,
                'dynamic_floor_kwh':target-0.144 if i == deadline else 0.864,
                'need_until_solar_kwh':0.0,'next_usable_solar':slots[-1]['start'],
                'solar_horizon_complete':True} for i in range(count+1)]
    return slots, profile


def test_reachability_preserves_existing_energy_before_power_limited_deadline():
    slots, profile = controlled_case()
    # Feasible: 1.44 initial + 5*0.736 = 5.12 kWh > 5.0 kWh target.
    # Spending 0.44 kWh first would make this falsely infeasible.
    out = build_native_safety_plan(slots=slots,reserve_profile=profile,start_soc=20.0,charge_eff=0.92,discharge_eff=0.92)
    assert out['fully_allocated'] is True
    assert out['simulation']['slots'][4]['end_stored_kwh'] >= 5.0-1e-6


def test_impossible_deadline_is_not_relabelled_green_and_keeps_data():
    slots, profile = controlled_case(deadline=1,target=7.2)
    out = build_native_safety_plan(slots=slots,reserve_profile=profile,start_soc=20.0,charge_eff=0.92,discharge_eff=0.92)
    assert out['fully_allocated'] is False
    assert out['breaches'][0]['index'] == 0
    assert out['breaches'][0]['shortfall_battery_kwh'] > 5
    assert len(out['simulation']['slots']) == len(slots)
    assert out['simulation']['slots'][0]['end_stored_kwh'] <= 1.44+0.736+1e-6


def test_cheapest_early_charge_survives_until_its_deadline():
    slots, profile = controlled_case(count=16,deadline=12,target=5.0,start_soc=30)
    for index, slot in enumerate(slots):
        slot['import_price'] = 0.1 if 2 <= index < 8 else 0.5
    out = build_native_safety_plan(slots=slots,reserve_profile=profile,start_soc=30.0,charge_eff=0.92,discharge_eff=0.92)
    assert out['fully_allocated']
    assert out['selected_charge_slots']
    assert all(row['import_price_all_in'] == 0.1 for row in out['selected_charge_slots'])
    assert all(row['end'] <= slots[11]['end'] for row in out['selected_charge_slots'])
    assert out['simulation']['slots'][9]['safety_reserved_kwh'] > 0


def test_native_energy_conservation_and_all_288_power_limits():
    inp, reserve, preview = native_case()
    result = build_do_plan_72h(input_result=inp,reserve_result=reserve,preview_result=preview)
    previous_stored = reserve['soc_percent']/100*7.2
    for s in result['slots']:
        assert s['home_kwh'] == pytest.approx(s['solar_to_home_kwh']+s['battery_to_home_kwh']+s['grid_to_home_kwh'],abs=2e-6)
        assert s['solar_kwh'] == pytest.approx(s['solar_to_home_kwh']+s['solar_to_battery_kwh']/0.92+s['solar_to_grid_kwh'],abs=2e-6)
        assert s['solar_to_battery_kwh']/0.92+s['grid_to_battery_kwh'] <= 0.800002
        assert s['battery_to_home_kwh']+s['battery_to_grid_kwh'] <= 0.800002
        expected=previous_stored+s['solar_to_battery_kwh']+s['grid_to_battery_kwh']*0.92-(s['battery_to_home_kwh']+s['battery_to_grid_kwh'])/0.92
        assert s['end_stored_kwh'] == pytest.approx(expected,abs=3e-6)
        assert 0.36-1e-6 <= s['end_stored_kwh'] <= 7.2+1e-6
        previous_stored=s['end_stored_kwh']
    for hour in result['hours']:
        group=result['slots'][hour['index']*4:hour['index']*4+4]
        for k in ('home_kwh','solar_kwh','grid_to_battery_safety_kwh','grid_to_battery_trade_kwh','battery_to_home_kwh','battery_to_grid_kwh'):
            assert hour[k] == round(sum(s[k] for s in group),3)
        assert hour['end_soc_percent'] == group[-1]['end_soc_percent']
        assert hour['dynamic_reserve_end_soc_percent'] == group[-1]['dynamic_reserve_end_soc_percent']


def test_grid_support_caps_last_quarter_to_0790_kwh_not_two_full_slots():
    inp, reserve, _ = native_case()
    reserve.update({'grid_support_required':True,'grid_support_deficit_kwh':0.79,'reserve_deficit_kwh':0.79,'first_usable_solar':inp['rows'][12]['start']})
    result=build_do_plan_grid_support(input_result=inp,reserve_result=reserve)
    assert result['valid'] is True
    assert result['selected_charge_stored_kwh_total'] == pytest.approx(0.79,abs=0.001)
    assert sum(s['stored_battery_kwh'] for s in result['selected_charge_slots']) == pytest.approx(0.79,abs=2e-6)
    assert result['selected_charge_input_kwh_total'] == pytest.approx(0.859,abs=0.001)

from custom_components.dummy_os_data.do_plan_store_bridge import build_do_plan_store_bridge


def test_conflicting_advice_does_not_change_authoritative_native_schedule():
    inp, reserve, preview = native_case()
    base=build_do_plan_72h(input_result=inp,reserve_result=reserve,preview_result=preview)
    preview['safety_charge_hours']=[{'start':inp['rows'][5]['start'],'candidate_battery_energy_kwh':5.0}]
    grid={'status':'ready','valid':True,'selected_charge_slots':[{'start':inp['rows'][6]['start'],'stored_battery_kwh':5.0}]}
    other=build_do_plan_72h(input_result=inp,reserve_result=reserve,preview_result=preview,grid_support_result=grid)
    assert base['slots'] == other['slots']
    assert other['safety_plan_authority'] == 'plan72_native'
    assert other['upstream_safety_advice_only'] is True


def test_bridge_uses_exact_native_charge_timing_and_not_advisory_grid_plan():
    inp, _, _ = native_case()
    start=inp['rows'][2]['price_quarters'][1]['start']; end=inp['rows'][2]['price_quarters'][2]['start']
    slot={'start':start,'end':end,'grid_to_battery_kwh':0.3,'grid_to_battery_safety_kwh':0.3,'battery_to_grid_kwh':0.0,'start_soc_percent':50,'end_soc_percent':53.833}
    plan={'status':'ready','valid':True,'safety_plan_authority':'plan72_native','slots':[slot], 'hours':[dict(slot,start=inp['rows'][2]['start'],end=inp['rows'][2]['end'])]}
    grid={'status':'ready','valid':True,'grid_charge_triggered':True,'selected_charge_slots':[{'start':inp['rows'][1]['start'],'end':inp['rows'][1]['price_quarters'][1]['start'],'allocated_charge_input_kwh':0.5}]}
    out=build_do_plan_store_bridge(plan72_result=plan,grid_support_result=grid,now=datetime.fromisoformat(inp['rows'][0]['start']))
    assert out['candidate_count'] == 1
    assert out['candidate_authority'] == 'plan72_native'
    assert out['candidates'][0]['start_time'] == start
    assert out['candidates'][0]['planned_end_time'] == end
    assert out['candidates'][0]['planned_energy_kwh'] == 0.3
    assert out['candidates'][0]['power_w'] == 1200
    assert out['candidates'][0]['target_soc_percent'] == 53.833
    assert out['suppressed_candidates'][0]['reason'] == 'advisory_only_native_plan_authoritative'
    plan.update(status='infeasible',valid=False)
    blocked=build_do_plan_store_bridge(plan72_result=plan,grid_support_result=grid,now=datetime.fromisoformat(inp['rows'][0]['start']))
    assert blocked['candidates'] == []


def test_degraded_prefix_is_still_simulated_without_padding():
    inp, reserve, preview = native_case()
    inp.update(status='degraded',effective_horizon_hours=71,fully_valid_hours=71,valid_through=inp['rows'][70]['end'])
    inp['rows'][71]['fully_valid']=False
    out=build_do_plan_72h(input_result=inp,reserve_result=reserve,preview_result=preview)
    assert out['status'] == 'degraded' and out['valid']
    assert out['slot_count'] == 284 and out['hour_count'] == 71
    assert out['slots'][-1]['end'] == inp['valid_through']
    assert out['missing_as_zero_used'] is False
    assert out['physical_execution_authority'] is False


def test_solar_has_first_priority_in_shared_charge_power():
    slots, profile=controlled_case(count=8,deadline=4,target=4.0)
    slots[1]['solar_kwh']=0.8
    out=build_native_safety_plan(slots=slots,reserve_profile=profile,start_soc=30.0,charge_eff=0.92,discharge_eff=0.92)
    assert out['fully_allocated']
    row=out['simulation']['slots'][1]
    assert row['solar_to_battery_kwh'] == pytest.approx(0.7*0.92,abs=1e-6)
    assert row['grid_to_battery_safety_kwh'] <= 0.100001


def test_small_home_flows_are_not_phantom_energy():
    slots, profile=controlled_case(count=4,deadline=4,target=1.008)
    for slot in slots: slot['home_kwh']=0.005
    out=_simulate(slots=slots,start_soc=50.0,reserve_profile=profile,safety_slots={},trade=None,charge_eff=0.92,discharge_eff=0.92)
    assert out['slots'][-1]['end_stored_kwh'] == pytest.approx(3.6-0.020/0.92,abs=1e-9)
    assert all(s['grid_to_home_kwh'] == 0.0 for s in out['slots'])


def test_unsafe_trade_does_not_destroy_safe_baseline():
    # A real sequential replay where trading displaces previously accepted safety
    # storage; no mocked simulation and no false claim to be the live user dump.
    import random
    rnd = random.Random(6)
    inp, reserve, preview = native_case()
    for h, row in enumerate(inp['rows']):
        for q in range(4):
            row['home_quarters'][q]['kwh'] = rnd.uniform(0.03, 0.16)
            row['solar_quarters'][q]['kwh'] = rnd.uniform(0.12, 0.8) if 12 <= h % 24 < 16 else 0.0
            row['price_quarters'][q].update(import_price=rnd.uniform(0.1, 0.65), export_price=rnd.uniform(0.1, 0.65))
    result = build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    assert result['baseline']['execution_buffer_breach_slots'] == 0
    assert result['trade_candidate'] is not None
    assert result['trade_rejected_for_safety'] is True
    assert result['valid'] is True
    assert result['hours'] == result['baseline']['hours']
    assert result['rejected_trade_candidate']['execution_buffer_breach_slots'] > 0


def test_published_safety_diagnostics_are_accepted_energy_in_published_slots():
    inp, reserve, preview = native_case()
    for row in inp['rows']:
        for price in row['price_quarters']:
            price['export_price'] = price['import_price'] + 0.25
    result = build_do_plan_72h(input_result=inp, reserve_result=reserve, preview_result=preview)
    by_start = {s['start']: s for s in result['slots']}
    safety = result['safety_plan']
    assert safety['valid'] == result['valid']
    for selected in safety['selected_charge_slots']:
        slot = by_start[selected['start']]
        assert selected['allocated_charge_input_kwh'] == slot['grid_to_battery_safety_kwh']
        assert selected['stored_battery_kwh'] == round(slot['accepted_safety_stored_kwh'], 6)
        assert selected['projected_soc_after_percent'] == slot['end_soc_percent']
    accepted = sum(slot['grid_to_battery_safety_kwh'] for slot in result['slots'])
    assert safety['accepted_grid_input_kwh'] == pytest.approx(accepted, abs=1e-6)
    assert result['grid_to_battery_safety_kwh'] == pytest.approx(accepted, abs=0.0006)


@pytest.mark.parametrize('seed',range(12))
def test_feasible_changing_deadlines_never_lose_energy_or_go_false_infeasible(seed):
    import random
    rnd=random.Random(seed)
    slots,profile=controlled_case(count=32)
    initial=2.16
    reachable=initial
    for i,slot in enumerate(slots):
        slot['home_kwh']=rnd.uniform(0.01,0.5)
        slot['solar_kwh']=rnd.uniform(0,0.8) if i%6<3 else 0.0
        slot['import_price']=rnd.uniform(-0.05,0.6)
        reachable=min(7.2,reachable+0.8*0.92)
        target=rnd.uniform(1.008,reachable)
        profile[i+1].update(execution_floor_kwh=target,dynamic_floor_kwh=max(0.864,target-0.144))
    result=build_native_safety_plan(slots=slots,reserve_profile=profile,start_soc=30.0,charge_eff=0.92,discharge_eff=0.92)
    assert result['fully_allocated'], result['breaches']
    previous=initial
    for s in result['simulation']['slots']:
        expected=previous+s['solar_to_battery_kwh']+s['grid_to_battery_kwh']*0.92-(s['battery_to_home_kwh']+s['battery_to_grid_kwh'])/0.92
        assert s['end_stored_kwh'] == pytest.approx(expected,abs=3e-6)
        previous=s['end_stored_kwh']
