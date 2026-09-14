from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import DEFAULT_BATTERY_CAPACITY_KWH, MIN_SOC_PERCENT


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


def build_energy_need_analysis(
    forecast: list[dict[str, Any]],
    soc: float | None,
    safety_reserve_percent: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build an observational energy balance until usable solar returns.

    Usable solar is deliberately conservative in this first observational
    version: the first hour of two consecutive forecast hours where solar
    production is at least equal to the forecast home consumption.
    """
    now_utc = (now or dt_util.utcnow()).astimezone(dt_util.UTC)
    reserve_percent = max(0.0, min(30.0, float(safety_reserve_percent)))
    reserve_kwh = DEFAULT_BATTERY_CAPACITY_KWH * reserve_percent / 100.0

    rows: list[dict[str, Any]] = []
    for raw in forecast:
        hour = _parse_time(raw.get("time"))
        home = _as_float(raw.get("home_consumption_kwh"))
        solar = _as_float(raw.get("solar_kwh"))
        if hour is None:
            continue
        rows.append({"time": hour, "home": home, "solar": solar})
    rows.sort(key=lambda item: item["time"])

    usable_index: int | None = None
    for index in range(len(rows) - 1):
        current = rows[index]
        following = rows[index + 1]
        if current["time"] < now_utc.replace(minute=0, second=0, microsecond=0):
            continue
        current_usable = (
            current["home"] is not None
            and current["solar"] is not None
            and current["solar"] >= current["home"]
            and current["solar"] > 0
        )
        following_usable = (
            following["home"] is not None
            and following["solar"] is not None
            and following["solar"] >= following["home"]
            and following["solar"] > 0
        )
        if current_usable and following_usable:
            usable_index = index
            break

    missing_home = False
    missing_solar = False
    net_need_kwh = 0.0
    contributing_hours = 0.0
    first_usable = rows[usable_index]["time"] if usable_index is not None else None

    for index, row in enumerate(rows):
        if row["time"] < now_utc.replace(minute=0, second=0, microsecond=0):
            continue
        if usable_index is not None and index >= usable_index:
            break

        home = row["home"]
        solar = row["solar"]
        if home is None:
            missing_home = True
            continue
        if solar is None:
            missing_solar = True
            solar = 0.0

        fraction = 1.0
        if row["time"] == now_utc.replace(minute=0, second=0, microsecond=0):
            elapsed = now_utc.minute / 60.0 + now_utc.second / 3600.0
            fraction = max(0.0, min(1.0, 1.0 - elapsed))

        net_need_kwh += max(home - solar, 0.0) * fraction
        contributing_hours += fraction

    available_battery_kwh: float | None = None
    if soc is not None:
        usable_soc = max(0.0, min(100.0, float(soc)) - MIN_SOC_PERCENT)
        available_battery_kwh = DEFAULT_BATTERY_CAPACITY_KWH * usable_soc / 100.0

    required_including_reserve = net_need_kwh + reserve_kwh
    additional_grid_charge_kwh: float | None = None
    tradable_battery_kwh: float | None = None
    if available_battery_kwh is not None:
        additional_grid_charge_kwh = max(
            required_including_reserve - available_battery_kwh, 0.0
        )
        tradable_battery_kwh = max(
            available_battery_kwh - required_including_reserve, 0.0
        )

    valid = (
        first_usable is not None
        and not missing_home
        and not missing_solar
        and available_battery_kwh is not None
    )

    if first_usable is None:
        reason = "Geen twee opeenvolgende bruikbare zonne-uren gevonden binnen de forecast"
    elif available_battery_kwh is None:
        reason = "SOC niet beschikbaar; batterij-energiebalans kan niet worden bepaald"
    elif missing_home or missing_solar:
        reason = "Forecast bevat ontbrekende woning- of solarwaarden voor de benodigde periode"
    elif additional_grid_charge_kwh is not None and additional_grid_charge_kwh > 0.01:
        reason = "Aanvullende energie nodig om behoefte plus veiligheidsreserve te dekken"
    else:
        reason = "Beschikbare batterij-energie dekt behoefte plus veiligheidsreserve"

    return {
        "energy_need_status": "ready" if valid else "waiting_for_complete_forecast",
        "energy_need_valid": valid,
        "energy_need_reason": reason,
        "energy_need_until_solar_kwh": round(net_need_kwh, 3),
        "energy_need_first_usable_solar": first_usable.isoformat() if first_usable else None,
        "energy_need_available_battery_kwh": (
            round(available_battery_kwh, 3) if available_battery_kwh is not None else None
        ),
        "energy_need_safety_reserve_percent": round(reserve_percent, 1),
        "energy_need_safety_reserve_kwh": round(reserve_kwh, 3),
        "energy_need_required_including_reserve_kwh": round(required_including_reserve, 3),
        "energy_need_additional_grid_charge_kwh": (
            round(additional_grid_charge_kwh, 3)
            if additional_grid_charge_kwh is not None
            else None
        ),
        "energy_need_tradable_battery_kwh": (
            round(tradable_battery_kwh, 3)
            if tradable_battery_kwh is not None
            else None
        ),
        "energy_need_contributing_hours": round(contributing_hours, 2),
        "energy_need_battery_capacity_kwh": DEFAULT_BATTERY_CAPACITY_KWH,
        "energy_need_min_soc_percent": MIN_SOC_PERCENT,
        "energy_need_usable_solar_rule": (
            "eerste van twee opeenvolgende forecasturen waarin solar >= woningverbruik"
        ),
        "energy_need_observational_only": True,
    }
