from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import DEFAULT_BATTERY_CAPACITY_KWH, MIN_SOC_PERCENT

_MIN_ENERGY_KWH = 0.01


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return parsed.astimezone(dt_util.UTC)


def build_planner_preview(
    forecast: list[dict[str, Any]],
    energy_need: dict[str, Any],
    soc: float | None,
    charge_efficiency_percent: float,
    discharge_efficiency_percent: float,
    minimum_trade_margin: float,
    max_charge_power_w: int = 3500,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build an observational planner and financial trade preview.

    Alpha23 still creates no plans and performs no physical trading action.
    """
    now_utc = (now or dt_util.utcnow()).astimezone(dt_util.UTC)
    current_hour = now_utc.replace(minute=0, second=0, microsecond=0)

    charge_eff = max(0.50, min(1.00, float(charge_efficiency_percent) / 100.0))
    discharge_eff = max(0.50, min(1.00, float(discharge_efficiency_percent) / 100.0))
    roundtrip_eff = charge_eff * discharge_eff
    min_margin = max(0.0, float(minimum_trade_margin))

    valid = bool(energy_need.get("energy_need_valid"))
    need_kwh = _as_float(energy_need.get("energy_need_until_solar_kwh")) or 0.0
    reserve_kwh = _as_float(energy_need.get("energy_need_safety_reserve_kwh")) or 0.0
    additional_kwh = _as_float(energy_need.get("energy_need_additional_grid_charge_kwh"))
    tradable_kwh = _as_float(energy_need.get("energy_need_tradable_battery_kwh"))
    first_usable = _parse_time(energy_need.get("energy_need_first_usable_solar"))

    required_min_soc = MIN_SOC_PERCENT + (
        (need_kwh + reserve_kwh) / DEFAULT_BATTERY_CAPACITY_KWH * 100.0
    )
    required_min_soc = max(float(MIN_SOC_PERCENT), min(100.0, required_min_soc))

    price_rows: list[dict[str, Any]] = []
    for raw in forecast:
        hour = _parse_time(raw.get("time"))
        import_price = _as_float(raw.get("import_price"))
        if import_price is None:
            import_price = _as_float(raw.get("price"))
        export_price = _as_float(raw.get("export_price"))
        if export_price is None:
            export_price = import_price
        if hour is None or import_price is None or export_price is None or hour < current_hour:
            continue
        price_rows.append(
            {
                "time": hour,
                "price": import_price,
                "import_price": import_price,
                "export_price": export_price,
                "price_source": raw.get("price_source"),
                "import_price_source": raw.get("import_price_source") or raw.get("price_source"),
                "export_price_source": raw.get("export_price_source") or raw.get("price_source"),
                "solar_kwh": _as_float(raw.get("solar_kwh")),
                "home_consumption_kwh": _as_float(raw.get("home_consumption_kwh")),
            }
        )
    price_rows.sort(key=lambda item: item["time"])

    prices = [row["import_price"] for row in price_rows]
    price_min = min(prices) if prices else None
    price_max = max(prices) if prices else None
    price_spread = (
        price_max - price_min if price_min is not None and price_max is not None else None
    )

    safety_candidates = [
        row for row in price_rows if first_usable is None or row["time"] < first_usable
    ]
    safety_candidates.sort(key=lambda item: (item["import_price"], item["time"]))

    remaining = max(additional_kwh or 0.0, 0.0)
    selected_hours: list[dict[str, Any]] = []
    for row in safety_candidates:
        if remaining <= _MIN_ENERGY_KWH:
            break
        fraction = 1.0
        if row["time"] == current_hour:
            elapsed = now_utc.minute / 60.0 + now_utc.second / 3600.0
            fraction = max(0.0, min(1.0, 1.0 - elapsed))
        capacity_kwh = max_charge_power_w / 1000.0 * fraction * charge_eff
        if capacity_kwh <= 0:
            continue
        allocated = min(remaining, capacity_kwh)
        selected_hours.append(
            {
                "time": row["time"].isoformat(),
                "price": row["import_price"],
                "import_price": row["import_price"],
                "export_price": row["export_price"],
                "price_source": row["price_source"],
                "max_battery_energy_kwh": round(capacity_kwh, 3),
                "candidate_battery_energy_kwh": round(allocated, 3),
            }
        )
        remaining -= allocated

    safety_charge_needed = bool(
        valid and additional_kwh is not None and additional_kwh > _MIN_ENERGY_KWH
    )
    safety_schedule_sufficient = bool(
        not safety_charge_needed or remaining <= _MIN_ENERGY_KWH
    )

    discharge_possible = bool(
        valid
        and tradable_kwh is not None
        and tradable_kwh > _MIN_ENERGY_KWH
        and soc is not None
        and float(soc) > required_min_soc
    )

    solar_charge_delay = bool(
        valid
        and not safety_charge_needed
        and first_usable is not None
        and first_usable > now_utc
    )

    free_capacity_kwh = None
    if soc is not None:
        free_capacity_kwh = (
            DEFAULT_BATTERY_CAPACITY_KWH * max(0.0, 100.0 - float(soc)) / 100.0
        )

    # Financial pair search: buy in an earlier hour, use/sell in a later
    # more expensive hour. Cost is expressed per delivered kWh after both
    # charge and discharge losses.
    best_trade: dict[str, Any] | None = None
    for i, charge_row in enumerate(price_rows):
        effective_charge_cost = charge_row["import_price"] / roundtrip_eff
        for discharge_row in price_rows[i + 1:]:
            net_margin = discharge_row["export_price"] - effective_charge_cost
            if best_trade is None or net_margin > best_trade["net_margin"]:
                best_trade = {
                    "charge_time": charge_row["time"],
                    "charge_price": charge_row["import_price"],
                    "discharge_time": discharge_row["time"],
                    "discharge_price": discharge_row["export_price"],
                    "effective_charge_cost": effective_charge_cost,
                    "net_margin": net_margin,
                }

    trade_profitable = bool(
        best_trade is not None
        and best_trade["net_margin"] >= min_margin
    )

    current_is_best_charge = bool(
        best_trade is not None and best_trade["charge_time"] == current_hour
    )
    current_is_best_discharge = bool(
        best_trade is not None and best_trade["discharge_time"] == current_hour
    )

    trade_charge_candidate = bool(
        valid
        and not safety_charge_needed
        and free_capacity_kwh is not None
        and free_capacity_kwh > _MIN_ENERGY_KWH
        and trade_profitable
    )

    if not valid:
        decision = "wachten"
        reason = "Energiebalans is nog niet volledig geldig"
    elif safety_charge_needed:
        decision = "veiligheidsladen"
        if safety_schedule_sufficient:
            reason = (
                "Batterij-energie is onvoldoende voor behoefte plus reserve; "
                "goedkoopste benodigde laaduren zijn geselecteerd"
            )
        else:
            reason = (
                "Batterij-energie is onvoldoende en beschikbare laaduren vóór "
                "bruikbare zon lijken niet genoeg om het tekort volledig te laden"
            )
    elif current_is_best_discharge and discharge_possible and trade_profitable:
        decision = "ontladen"
        reason = (
            "Huidig uur is financieel beste ontlaaduur en energie boven reserve "
            "is beschikbaar"
        )
    elif current_is_best_charge and trade_charge_candidate and not solar_charge_delay:
        decision = "handelsladen"
        reason = (
            "Huidig uur is financieel beste laaduur en verwachte netto marge "
            "overschrijdt de ingestelde minimum handelsmarge"
        )
    elif solar_charge_delay:
        decision = "wachten"
        reason = (
            "Voldoende batterijreserve tot bruikbare zon; netladen nu uitstellen"
        )
    elif trade_profitable:
        decision = "wachten"
        reason = (
            "Financieel rendabele handelscombinatie gevonden; beste laad- of "
            "ontlaaduur ligt later"
        )
    else:
        decision = "geen_actie"
        reason = (
            "Geen veiligheidslading nodig en geen handelscombinatie voldoet aan "
            "de ingestelde netto handelsmarge"
        )

    cheapest_preview = sorted(price_rows, key=lambda item: (item["import_price"], item["time"]))[:6]
    cheapest_preview = [
        {
            "time": row["time"].isoformat(),
            "price": row["import_price"],
            "import_price": row["import_price"],
            "export_price": row["export_price"],
            "price_source": row["price_source"],
        }
        for row in cheapest_preview
    ]

    return {
        "planner_preview_status": "ready" if valid else "waiting_for_energy_balance",
        "planner_preview_decision": decision,
        "planner_preview_reason": reason,
        "planner_preview_required_min_soc": round(required_min_soc, 1),
        "planner_preview_energy_above_reserve_kwh": (
            round(tradable_kwh, 3) if tradable_kwh is not None else None
        ),
        "planner_preview_safety_charge_needed": safety_charge_needed,
        "planner_preview_safety_charge_kwh": (
            round(additional_kwh, 3) if additional_kwh is not None else None
        ),
        "planner_preview_safety_charge_hours": selected_hours,
        "planner_preview_safety_charge_hour_count": len(selected_hours),
        "planner_preview_safety_schedule_sufficient": safety_schedule_sufficient,
        "planner_preview_trade_charge_candidate": trade_charge_candidate,
        "planner_preview_discharge_possible": discharge_possible,
        "planner_preview_solar_charge_delay": solar_charge_delay,
        "planner_preview_first_usable_solar": (
            first_usable.isoformat() if first_usable is not None else None
        ),
        "planner_preview_price_min": price_min,
        "planner_preview_price_max": price_max,
        "planner_preview_price_spread": (
            round(price_spread, 6) if price_spread is not None else None
        ),
        "planner_preview_cheapest_hours": cheapest_preview,
        "planner_preview_free_capacity_kwh": (
            round(free_capacity_kwh, 3) if free_capacity_kwh is not None else None
        ),
        "planner_preview_charge_efficiency_percent": round(charge_eff * 100.0, 1),
        "planner_preview_discharge_efficiency_percent": round(discharge_eff * 100.0, 1),
        "planner_preview_roundtrip_efficiency_percent": round(roundtrip_eff * 100.0, 1),
        "planner_preview_minimum_trade_margin": round(min_margin, 4),
        "planner_preview_trade_profitable": trade_profitable,
        "planner_preview_best_charge_time": (
            best_trade["charge_time"].isoformat() if best_trade else None
        ),
        "planner_preview_best_charge_price": (
            round(best_trade["charge_price"], 6) if best_trade else None
        ),
        "planner_preview_best_discharge_time": (
            best_trade["discharge_time"].isoformat() if best_trade else None
        ),
        "planner_preview_best_discharge_price": (
            round(best_trade["discharge_price"], 6) if best_trade else None
        ),
        "planner_preview_effective_charge_cost": (
            round(best_trade["effective_charge_cost"], 6) if best_trade else None
        ),
        "planner_preview_expected_trade_margin": (
            round(best_trade["net_margin"], 6) if best_trade else None
        ),
        "planner_preview_replan_reason": "periodieke_observatieve_herberekening",
        "planner_preview_observational_only": True,
        "planner_preview_trading_execution_enabled": False,
        "planner_preview_losses_included": True,
        "planner_preview_assumed_max_charge_power_w": int(max_charge_power_w),
        "planner_preview_note": (
            "Alpha23 rekent handelsrendement observerend door met laad- en "
            "ontlaadrendement en minimum handelsmarge. Er worden nog geen "
            "automatische plannen aangemaakt."
        ),
    }
