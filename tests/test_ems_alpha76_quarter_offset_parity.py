"""Prove the alpha76 adapter does not change decisions at :15/:30/:45 starts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.dummy_os_data.ems_alpha76.energy_need import build_energy_need_analysis
from custom_components.dummy_os_data.ems_alpha76.planner_preview import build_planner_preview
from custom_components.dummy_os_data.ems_alpha76.planner_72h import build_72h_plan_preview
from custom_components.dummy_os_data.ems_alpha76_adapter import (
    forecast_from_input,
    planner_reference,
    run_energy_need,
    run_preview,
    run_plan72,
)


def make_input(minute: int):
    base = datetime(2026, 9, 14, 10, minute, tzinfo=timezone.utc)
    rows=[]
    for i in range(72):
        start=base+timedelta(hours=i)
        home=0.22 + (i % 5) * 0.07
        solar=0.0 if not 6 <= i <= 12 else 0.35 + (i % 4) * 0.18
        imp=0.11 + (i % 7) * 0.025
        exp=0.07 + (i % 6) * 0.02
        rows.append({
            "start": start.isoformat(), "end": (start+timedelta(hours=1)).isoformat(),
            "home_kwh": round(home,6), "solar_kwh": round(solar,6),
            "import_price": round(imp,5), "export_price": round(exp,5),
            "price_source": "known", "fully_valid": True,
            "price_quarters": [
                {"start": (start+timedelta(minutes=15*q)).isoformat(), "kind":"known_pt15m"}
                for q in range(4)
            ],
        })
    return {
        "status":"ready", "valid":True, "rows":rows,
        "rows_signature":f"offset-{minute}",
        "time_contract":{
            "window_start":base.isoformat(),
            "window_end":(base+timedelta(hours=72)).isoformat(),
            "window_id":f"offset-{minute}",
        },
    }, base


@pytest.mark.parametrize("minute", [0,15,30,45])
def test_exact_alpha76_chain_matches_adapter_at_every_quarter_boundary(minute):
    inp, base=make_input(minute)
    forecast=forecast_from_input(inp)
    assert len(forecast)==72
    assert planner_reference(inp)==base
    assert forecast[0]["time"]==base.isoformat()
    assert forecast[-1]["time"]==(base+timedelta(hours=71)).isoformat()

    direct_need=build_energy_need_analysis(forecast, 43.25, 7.0, now=base)
    direct_preview=build_planner_preview(
        forecast,direct_need,43.25,92.0,92.0,0.10,max_charge_power_w=3200,now=base
    )
    direct_plan=build_72h_plan_preview(
        forecast,direct_need,direct_preview,43.25,92.0,92.0,
        execution_buffer_percent=2.0,max_charge_power_w=3200,max_discharge_power_w=3200,now=base
    )

    adapted_need=run_energy_need(input_result=inp,soc_percent=43.25,now=base)
    adapted_preview=run_preview(
        input_result=inp,energy_need=adapted_need,soc_percent=43.25,
        charge_efficiency_percent=92.0,discharge_efficiency_percent=92.0,
        minimum_trade_margin=0.10,max_charge_power_w=3200,now=base
    )
    adapted_plan=run_plan72(
        input_result=inp,energy_need=adapted_need,planner_preview=adapted_preview,
        soc_percent=43.25,charge_efficiency_percent=92.0,
        discharge_efficiency_percent=92.0,execution_buffer_percent=2.0,
        max_charge_power_w=3200,max_discharge_power_w=3200,now=base
    )
    assert adapted_need==direct_need
    assert adapted_preview==direct_preview
    assert adapted_plan==direct_plan


@pytest.mark.parametrize("minute", [15,30,45])
def test_offset_adapter_does_not_round_to_clock_hour(minute):
    inp, base=make_input(minute)
    forecast=forecast_from_input(inp)
    assert datetime.fromisoformat(forecast[0]["time"]).minute==minute
    assert planner_reference(inp).minute==minute
    total_home=sum(float(row["home_consumption_kwh"]) for row in forecast)
    total_source=sum(float(row["home_kwh"]) for row in inp["rows"])
    assert total_home==pytest.approx(total_source,abs=1e-12)
