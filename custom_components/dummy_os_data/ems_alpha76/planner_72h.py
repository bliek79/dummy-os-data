from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_AUTO_EXECUTION_BUFFER_PERCENT,
    DEFAULT_BATTERY_CAPACITY_KWH,
    MIN_SOC_PERCENT,
)

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


def _hour_fraction(hour: datetime, now_utc: datetime) -> float:
    current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
    if hour != current_hour:
        return 1.0
    elapsed = now_utc.minute / 60.0 + now_utc.second / 3600.0
    return max(0.0, min(1.0, 1.0 - elapsed))


def build_72h_plan_preview(
    forecast: list[dict[str, Any]],
    energy_need: dict[str, Any],
    planner_preview: dict[str, Any],
    soc: float | None,
    charge_efficiency_percent: float,
    discharge_efficiency_percent: float,
    execution_buffer_percent: float = DEFAULT_AUTO_EXECUTION_BUFFER_PERCENT,
    max_charge_power_w: int = 3500,
    max_discharge_power_w: int = 3500,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a sequential 72-hour battery plan preview.

    Alpha27 keeps the 72-hour planner observational only:
    - no plans are written to the three manual slots;
    - no Scheduler call is made;
    - no physical battery command is executed.
    """
    now_utc = (now or dt_util.utcnow()).astimezone(dt_util.UTC)
    current_hour = now_utc.replace(minute=0, second=0, microsecond=0)

    charge_eff = max(0.50, min(1.00, float(charge_efficiency_percent) / 100.0))
    discharge_eff = max(0.50, min(1.00, float(discharge_efficiency_percent) / 100.0))
    execution_buffer_percent = max(0.0, min(10.0, float(execution_buffer_percent)))

    if soc is None:
        return {
            "auto_plan_72h_status": "waiting_for_soc",
            "auto_plan_72h_valid": False,
            "auto_plan_72h_reason": "Geen geldige SOC beschikbaar",
            "auto_plan_72h_plan": [],
            "auto_plan_72h_count": 0,
            "auto_plan_72h_observational_only": True,
        }

    rows: list[dict[str, Any]] = []
    for raw in forecast:
        hour = _parse_time(raw.get("time"))
        if hour is None or hour < current_hour:
            continue
        rows.append(
            {
                "time": hour,
                "price": _as_float(raw.get("import_price")) if _as_float(raw.get("import_price")) is not None else _as_float(raw.get("price")),
                "import_price": _as_float(raw.get("import_price")) if _as_float(raw.get("import_price")) is not None else _as_float(raw.get("price")),
                "export_price": _as_float(raw.get("export_price")) if _as_float(raw.get("export_price")) is not None else (_as_float(raw.get("import_price")) if _as_float(raw.get("import_price")) is not None else _as_float(raw.get("price"))),
                "price_source": raw.get("price_source"),
                "import_price_source": raw.get("import_price_source") or raw.get("price_source"),
                "export_price_source": raw.get("export_price_source") or raw.get("price_source"),
                "solar_kwh": max(0.0, _as_float(raw.get("solar_kwh")) or 0.0),
                "home_kwh": max(0.0, _as_float(raw.get("home_consumption_kwh")) or 0.0),
            }
        )
    rows.sort(key=lambda item: item["time"])
    rows = rows[:72]

    if not rows:
        return {
            "auto_plan_72h_status": "waiting_for_forecast",
            "auto_plan_72h_valid": False,
            "auto_plan_72h_reason": "Geen bruikbare forecasturen beschikbaar",
            "auto_plan_72h_plan": [],
            "auto_plan_72h_count": 0,
            "auto_plan_72h_observational_only": True,
        }

    capacity = DEFAULT_BATTERY_CAPACITY_KWH
    start_soc = max(float(MIN_SOC_PERCENT), min(100.0, float(soc)))
    stored_kwh = capacity * start_soc / 100.0

    reserve_kwh = _as_float(energy_need.get("energy_need_safety_reserve_kwh")) or 0.0
    minimum_stored_kwh = capacity * float(MIN_SOC_PERCENT) / 100.0
    base_reserve_floor_kwh = minimum_stored_kwh + reserve_kwh
    base_reserve_floor_kwh = min(
        capacity,
        max(minimum_stored_kwh, base_reserve_floor_kwh),
    )
    execution_buffer_kwh = capacity * execution_buffer_percent / 100.0


    def _is_usable_solar(index: int) -> bool:
        if index < 0 or index >= len(rows):
            return False
        row = rows[index]
        return row["solar_kwh"] > 0 and row["solar_kwh"] >= row["home_kwh"]

    def _dynamic_reserve(index: int) -> tuple[float, float, datetime | None]:
        """Required stored energy from this hour until the next usable solar block.

        The usable-solar rule stays aligned with alpha21: the first of two
        consecutive hours where solar >= forecast home consumption.

        Home deficits are converted to required stored battery energy using the
        configured discharge efficiency. The fixed software safety reserve and
        5% hardware floor are then added.
        """
        if index >= len(rows):
            return base_reserve_floor_kwh, 0.0, None

        usable_index: int | None = None
        for candidate in range(index, len(rows) - 1):
            if _is_usable_solar(candidate) and _is_usable_solar(candidate + 1):
                usable_index = candidate
                break

        if usable_index is None:
            # The end of the available forecast is not proof that there will be
            # no usable solar later. Do not reserve the complete remainder of the
            # 72-hour horizon. Fall back to the normal hardware + software reserve
            # and mark the solar horizon as incomplete through first_usable=None.
            return base_reserve_floor_kwh, 0.0, None

        stop_index = usable_index
        net_home_need_kwh = 0.0

        for need_index in range(index, stop_index):
            need_row = rows[need_index]
            fraction = _hour_fraction(need_row["time"], now_utc)
            net_home_need_kwh += max(
                0.0,
                need_row["home_kwh"] - need_row["solar_kwh"],
            ) * fraction

        stored_need_kwh = net_home_need_kwh / discharge_eff
        floor_kwh = min(
            capacity,
            max(
                minimum_stored_kwh,
                base_reserve_floor_kwh + stored_need_kwh,
            ),
        )
        first_usable = rows[usable_index]["time"]
        return floor_kwh, net_home_need_kwh, first_usable

    def _execution_reserve(index: int) -> tuple[float, float, float, datetime | None]:
        """Return calculated reserve plus the alpha25 execution headroom."""
        floor_kwh, need_kwh, first_usable = _dynamic_reserve(index)
        execution_floor_kwh = min(capacity, floor_kwh + execution_buffer_kwh)
        return execution_floor_kwh, floor_kwh, need_kwh, first_usable

    safety_hours_raw = planner_preview.get("planner_preview_safety_charge_hours") or []
    safety_by_time: dict[str, float] = {}
    for item in safety_hours_raw:
        if not isinstance(item, dict):
            continue
        t = _parse_time(item.get("time"))
        if t is None:
            continue
        wanted = _as_float(item.get("candidate_battery_energy_kwh"))
        if wanted is None:
            wanted = _as_float(item.get("candidate_energy_kwh"))
        if wanted is not None and wanted > 0:
            safety_by_time[t.isoformat()] = wanted

    trade_profitable = bool(planner_preview.get("planner_preview_trade_profitable"))
    best_charge_time = _parse_time(planner_preview.get("planner_preview_best_charge_time"))
    best_discharge_time = _parse_time(planner_preview.get("planner_preview_best_discharge_time"))

    plan: list[dict[str, Any]] = []
    total_solar_charge = 0.0
    total_grid_safety_charge = 0.0
    total_grid_trade_charge = 0.0
    total_home_discharge = 0.0
    total_grid_trade_discharge = 0.0
    total_grid_import_for_home = 0.0
    total_solar_export = 0.0
    min_soc_seen = start_soc
    max_soc_seen = start_soc
    dynamic_reserve_min_soc = 100.0
    dynamic_reserve_max_soc = 0.0
    execution_reserve_min_soc = 100.0
    execution_reserve_max_soc = 0.0
    minimum_execution_headroom_soc = 100.0
    execution_buffer_breach_hours = 0

    # Reserve a future high-value discharge opportunity. This prevents battery
    # energy from being consumed too early by low-value home deficits.
    best_discharge_price = _as_float(planner_preview.get("planner_preview_best_discharge_price"))
    best_charge_price = _as_float(planner_preview.get("planner_preview_best_charge_price"))
    minimum_trade_margin = _as_float(planner_preview.get("planner_preview_minimum_trade_margin")) or 0.0

    # Estimate how much future solar surplus can still charge the battery
    # between a candidate charge hour and the selected trade discharge hour.
    def future_solar_charge_potential(from_index: int, until_time: datetime | None) -> float:
        potential_input = 0.0
        for future in rows[from_index + 1:]:
            if until_time is not None and future["time"] > until_time:
                break
            future_solar = future["solar_kwh"]
            future_home = future["home_kwh"]
            potential_input += max(0.0, future_solar - future_home)
        return potential_input * charge_eff

    # Estimate the future home deficit before the best trade discharge hour.
    # Only deficits in more expensive hours than the candidate charge price
    # are allowed to use trade-reserved energy.
    def future_high_value_home_need(from_index: int, until_time: datetime | None, reference_price: float | None) -> float:
        need_output = 0.0
        for future in rows[from_index + 1:]:
            if until_time is not None and future["time"] > until_time:
                break
            future_price = future["import_price"]
            if reference_price is not None and future_price is not None and future_price <= reference_price:
                continue
            need_output += max(0.0, future["home_kwh"] - future["solar_kwh"])
        return need_output

    trade_energy_reserved_kwh = 0.0

    def _planned_dynamic_safety_charge_by_hour() -> dict[str, float]:
        """Pre-plan safety energy before each future execution-reserve deadline.

        Alpha27 fixes the timing edge found in alpha26: the reserve that applies
        *after* an hour must already be achievable by the end of that same hour.
        The previous implementation looked at the reserve at the start of the
        following hour, which could make a sharp reserve increase arrive one
        hour too late.

        For every local end-of-hour reserve peak we estimate how much stored
        energy will be available from the starting SOC and free solar. Only the
        remaining deficit is bought from the grid, allocated to the cheapest
        technically feasible hour(s) at or before the deadline.
        """
        planned: dict[str, float] = {}
        if not rows:
            return planned

        # A row's execution_floor_end is the requirement that must be met when
        # that row finishes. Therefore requirement index N uses reserve(N + 1),
        # but its charging deadline remains row N. This is the core alpha27 fix.
        reserve_requirements: list[tuple[int, float, datetime | None]] = []
        for idx, _row in enumerate(rows):
            execution_floor_end_kwh, _, _, next_solar = _execution_reserve(idx + 1)
            reserve_requirements.append((idx, execution_floor_end_kwh, next_solar))

        # Detect local end-of-hour reserve peaks tied to a demonstrable future
        # usable-solar block. Horizon-fallback hours deliberately do not create
        # artificial precharge demand.
        peaks: list[tuple[int, float, datetime]] = []
        for idx, floor_kwh, next_solar in reserve_requirements:
            if next_solar is None:
                continue
            prev_floor = reserve_requirements[idx - 1][1] if idx > 0 else base_reserve_floor_kwh
            next_floor = (
                reserve_requirements[idx + 1][1]
                if idx + 1 < len(reserve_requirements)
                else base_reserve_floor_kwh
            )
            if floor_kwh > prev_floor + _MIN_ENERGY_KWH and floor_kwh >= next_floor - _MIN_ENERGY_KWH:
                peaks.append((idx, floor_kwh, next_solar))

        for deadline_idx, required_floor_kwh, _next_solar in peaks:
            # Estimate stored energy available at the end of the deadline hour
            # from initial SOC + solar surplus + safety energy already allocated
            # for an earlier reserve peak. Discretionary discharge is ignored
            # here; the sequential planner later prevents discharge below the
            # execution reserve itself.
            estimated_stored = capacity * start_soc / 100.0
            for sim_idx in range(0, deadline_idx + 1):
                sim_row = rows[sim_idx]
                frac = _hour_fraction(sim_row["time"], now_utc)
                solar_surplus = max(
                    0.0,
                    (sim_row["solar_kwh"] - sim_row["home_kwh"]) * frac,
                )
                estimated_stored = min(
                    capacity,
                    estimated_stored + solar_surplus * charge_eff,
                )
                key = sim_row["time"].isoformat()
                if key in planned:
                    estimated_stored = min(capacity, estimated_stored + planned[key])

            deficit_stored = max(0.0, required_floor_kwh - estimated_stored)
            if deficit_stored <= _MIN_ENERGY_KWH:
                continue

            # Choose only hours that can physically contribute before the
            # deadline, ordered by price and then time. Planned values are stored
            # battery energy (after charge efficiency), matching the rest of the
            # planner's safety-allocation model.
            candidates: list[tuple[float, datetime, float]] = []
            for cand_idx in range(0, deadline_idx + 1):
                cand = rows[cand_idx]
                price = cand["import_price"]
                if price is None:
                    continue
                fraction = _hour_fraction(cand["time"], now_utc)

                # Safety precharge and solar charging share the same physical
                # charge-input ceiling.  The earlier alpha52 pre-planner used
                # the complete inverter charge limit for grid safety charging
                # and then the sequential planner correctly gave solar first
                # priority.  During a partially elapsed hour this could make the
                # pre-planner overestimate how much grid energy would actually
                # fit, leaving the final SOC just below the execution reserve.
                # Reserve only the grid-input headroom that remains after the
                # forecast solar surplus for this hour has taken its share.
                charge_input_limit = max_charge_power_w / 1000.0 * fraction
                solar_surplus_input = max(
                    0.0,
                    (cand["solar_kwh"] - cand["home_kwh"]) * fraction,
                )
                available_grid_input = max(0.0, charge_input_limit - solar_surplus_input)
                max_stored = available_grid_input * charge_eff
                if max_stored <= _MIN_ENERGY_KWH:
                    continue
                candidates.append((price, cand["time"], max_stored))

            candidates.sort(key=lambda item: (item[0], item[1]))
            remaining = deficit_stored
            for _price, cand_time, max_stored in candidates:
                if remaining <= _MIN_ENERGY_KWH:
                    break
                key = cand_time.isoformat()
                already = planned.get(key, 0.0)
                available = max(0.0, max_stored - already)
                if available <= _MIN_ENERGY_KWH:
                    continue
                add = min(available, remaining)
                planned[key] = already + add
                remaining -= add

        return planned

    dynamic_safety_by_time = _planned_dynamic_safety_charge_by_hour()

    for index, row in enumerate(rows):
        hour = row["time"]
        fraction = _hour_fraction(hour, now_utc)

        execution_floor_start_kwh, reserve_floor_start_kwh, reserve_need_start_kwh, next_usable_solar = _execution_reserve(index)
        execution_floor_end_kwh, reserve_floor_end_kwh, reserve_need_end_kwh, _ = _execution_reserve(index + 1)
        reserve_floor_start_soc = reserve_floor_start_kwh / capacity * 100.0
        reserve_floor_end_soc = reserve_floor_end_kwh / capacity * 100.0
        execution_floor_start_soc = execution_floor_start_kwh / capacity * 100.0
        execution_floor_end_soc = execution_floor_end_kwh / capacity * 100.0
        dynamic_reserve_min_soc = min(dynamic_reserve_min_soc, reserve_floor_end_soc)
        dynamic_reserve_max_soc = max(dynamic_reserve_max_soc, reserve_floor_start_soc)
        execution_reserve_min_soc = min(execution_reserve_min_soc, execution_floor_end_soc)
        execution_reserve_max_soc = max(execution_reserve_max_soc, execution_floor_start_soc)
        charge_input_limit = max_charge_power_w / 1000.0 * fraction
        discharge_output_limit = max_discharge_power_w / 1000.0 * fraction

        solar = row["solar_kwh"] * fraction
        home = row["home_kwh"] * fraction

        solar_to_home = min(solar, home)
        solar_surplus = max(0.0, solar - solar_to_home)
        home_deficit = max(0.0, home - solar_to_home)

        solar_charge_input = 0.0
        grid_safety_input = 0.0
        grid_trade_input = 0.0
        discharge_to_home = 0.0
        discharge_to_grid = 0.0
        grid_home = 0.0
        solar_export = 0.0

        available_charge_input = charge_input_limit

        # 1) Solar surplus charges first.
        if solar_surplus > _MIN_ENERGY_KWH and stored_kwh < capacity - _MIN_ENERGY_KWH:
            max_input_by_capacity = (capacity - stored_kwh) / charge_eff
            solar_charge_input = min(solar_surplus, available_charge_input, max_input_by_capacity)
            stored_added = solar_charge_input * charge_eff
            stored_kwh += stored_added
            available_charge_input -= solar_charge_input
            solar_surplus -= solar_charge_input

        solar_export = max(0.0, solar_surplus)

        # 2) Safety grid charge always has priority.
        # Alpha21/22 can already nominate a safety-charge hour. Alpha24.3 adds
        # a live 72-hour check: after solar charging, stored energy must be
        # sufficient for the dynamically calculated requirement from this hour
        # until the next usable solar block.
        planned_safety_target_stored = safety_by_time.get(hour.isoformat(), 0.0)
        dynamic_safety_target_stored = dynamic_safety_by_time.get(hour.isoformat(), 0.0)
        safety_target_stored = max(
            planned_safety_target_stored,
            dynamic_safety_target_stored,
        )

        if safety_target_stored > _MIN_ENERGY_KWH and stored_kwh < capacity - _MIN_ENERGY_KWH:
            max_input_by_capacity = (capacity - stored_kwh) / charge_eff
            requested_input = safety_target_stored / charge_eff
            grid_safety_input = min(
                requested_input,
                available_charge_input,
                max_input_by_capacity,
            )
            stored_kwh += grid_safety_input * charge_eff
            available_charge_input -= grid_safety_input

        # 3) Trade charging is blocked when expected solar can fill the same
        # free capacity before the selected sell hour (Solar Charge Delay).
        if (
            trade_profitable
            and best_charge_time is not None
            and hour == best_charge_time
            and available_charge_input > _MIN_ENERGY_KWH
            and stored_kwh < capacity - _MIN_ENERGY_KWH
        ):
            free_capacity_stored = max(0.0, capacity - stored_kwh)
            solar_fill_stored = future_solar_charge_potential(index, best_discharge_time)
            solar_charge_delay_active = solar_fill_stored >= max(0.0, free_capacity_stored - _MIN_ENERGY_KWH)

            if not solar_charge_delay_active:
                # Only buy the capacity that is not expected to be filled by
                # free solar before the sell hour.
                required_trade_stored = max(0.0, free_capacity_stored - solar_fill_stored)

                # Keep trade charging economically meaningful. If the expected
                # sell price no longer clears the required margin, do not charge.
                effective_charge_cost = (
                    row["import_price"] / (charge_eff * discharge_eff)
                    if row["import_price"] is not None
                    else None
                )
                expected_margin = (
                    best_discharge_price - effective_charge_cost
                    if best_discharge_price is not None and effective_charge_cost is not None
                    else None
                )
                trade_allowed = expected_margin is not None and expected_margin >= minimum_trade_margin

                if trade_allowed and required_trade_stored > _MIN_ENERGY_KWH:
                    max_input_by_capacity = free_capacity_stored / charge_eff
                    requested_input = required_trade_stored / charge_eff
                    grid_trade_input = min(
                        available_charge_input,
                        max_input_by_capacity,
                        requested_input,
                    )
                    stored_added = grid_trade_input * charge_eff
                    stored_kwh += stored_added
                    trade_energy_reserved_kwh += stored_added

        # 4) Home deficit uses battery only when doing so does not consume
        # energy reserved for a later, more valuable trade discharge.
        operational_floor = execution_floor_end_kwh + trade_energy_reserved_kwh
        operational_floor = min(
            capacity,
            max(execution_floor_end_kwh, operational_floor),
        )

        available_stored_above_floor = max(0.0, stored_kwh - operational_floor)
        max_output_from_storage = available_stored_above_floor * discharge_eff

        # Prefer battery for home use when the current price is at least as high
        # as the best buy price plus the requested trade margin, or when there is
        # no active future trade reservation.
        current_price = row["import_price"]
        threshold_price = None
        if best_charge_price is not None:
            threshold_price = best_charge_price / (charge_eff * discharge_eff) + minimum_trade_margin

        allow_home_discharge = trade_energy_reserved_kwh <= _MIN_ENERGY_KWH
        if (
            current_price is not None
            and threshold_price is not None
            and current_price >= threshold_price
        ):
            allow_home_discharge = True

        if allow_home_discharge:
            discharge_to_home = min(
                home_deficit,
                discharge_output_limit,
                max_output_from_storage,
            )
            if discharge_to_home > _MIN_ENERGY_KWH:
                stored_used = discharge_to_home / discharge_eff
                stored_kwh -= stored_used
                home_deficit -= discharge_to_home

                # If high-value home use happens before the selected trade hour,
                # it can consume part of the trade reservation because it creates
                # equal or better economic value than later grid export.
                if trade_energy_reserved_kwh > _MIN_ENERGY_KWH and current_price is not None:
                    trade_energy_reserved_kwh = max(
                        0.0,
                        trade_energy_reserved_kwh - stored_used,
                    )

        grid_home = max(0.0, home_deficit)

        # 5) At the selected best sell hour, discharge only energy above the
        # operational reserve. Home has priority, remainder may go to the grid.
        if (
            trade_profitable
            and best_discharge_time is not None
            and hour == best_discharge_time
        ):
            remaining_output_limit = max(0.0, discharge_output_limit - discharge_to_home)
            available_stored_above_reserve = max(
                0.0,
                stored_kwh - execution_floor_end_kwh,
            )
            max_trade_output = available_stored_above_reserve * discharge_eff
            discharge_to_grid = min(remaining_output_limit, max_trade_output)
            if discharge_to_grid > _MIN_ENERGY_KWH:
                stored_used = discharge_to_grid / discharge_eff
                stored_kwh -= stored_used
                trade_energy_reserved_kwh = max(
                    0.0,
                    trade_energy_reserved_kwh - stored_used,
                )

        stored_kwh = max(
            capacity * float(MIN_SOC_PERCENT) / 100.0,
            min(capacity, stored_kwh),
        )
        soc_start = plan[-1]["soc_end"] if plan else start_soc
        soc_end = stored_kwh / capacity * 100.0
        min_soc_seen = min(min_soc_seen, soc_end)
        max_soc_seen = max(max_soc_seen, soc_end)
        execution_headroom_soc = soc_end - execution_floor_end_soc
        minimum_execution_headroom_soc = min(minimum_execution_headroom_soc, execution_headroom_soc)
        if execution_headroom_soc < -0.05:
            execution_buffer_breach_hours += 1

        action_parts: list[str] = []
        if grid_safety_input > _MIN_ENERGY_KWH:
            action_parts.append("veiligheidsladen")
        if grid_trade_input > _MIN_ENERGY_KWH:
            action_parts.append("handelsladen")
        if solar_charge_input > _MIN_ENERGY_KWH:
            action_parts.append("zonneladen")
        if discharge_to_home > _MIN_ENERGY_KWH:
            action_parts.append("woning_ontladen")
        if discharge_to_grid > _MIN_ENERGY_KWH:
            action_parts.append("handel_ontladen")
        if not action_parts:
            action_parts.append("geen_actie")

        total_solar_charge += solar_charge_input
        total_grid_safety_charge += grid_safety_input
        total_grid_trade_charge += grid_trade_input
        total_home_discharge += discharge_to_home
        total_grid_trade_discharge += discharge_to_grid
        total_grid_import_for_home += grid_home
        total_solar_export += solar_export

        plan.append(
            {
                "time": hour.isoformat(),
                "price": row["import_price"],
                "import_price": row["import_price"],
                "export_price": row["export_price"],
                "price_source": row["price_source"],
                "import_price_source": row["import_price_source"],
                "export_price_source": row["export_price_source"],
                "solar_kwh": round(solar, 3),
                "home_consumption_kwh": round(home, 3),
                "solar_to_home_kwh": round(solar_to_home, 3),
                "charge_from_solar_kwh": round(solar_charge_input, 3),
                "charge_from_grid_safety_kwh": round(grid_safety_input, 3),
                "charge_from_grid_trade_kwh": round(grid_trade_input, 3),
                "charge_from_grid_kwh": round(grid_safety_input + grid_trade_input, 3),
                "discharge_to_home_kwh": round(discharge_to_home, 3),
                "discharge_to_grid_kwh": round(discharge_to_grid, 3),
                "grid_import_for_home_kwh": round(grid_home, 3),
                "solar_export_kwh": round(solar_export, 3),
                "soc_start": round(float(soc_start), 1),
                "soc_end": round(soc_end, 1),
                "reserve_floor_soc": round(reserve_floor_end_soc, 1),
                "reserve_floor_start_soc": round(reserve_floor_start_soc, 1),
                "execution_reserve_floor_soc": round(execution_floor_end_soc, 1),
                "execution_reserve_floor_start_soc": round(execution_floor_start_soc, 1),
                "execution_buffer_percent": round(execution_buffer_percent, 1),
                "execution_headroom_soc": round(execution_headroom_soc, 1),
                "dynamic_need_until_solar_kwh": round(reserve_need_start_kwh, 3),
                "dynamic_need_after_hour_kwh": round(reserve_need_end_kwh, 3),
                "next_usable_solar": (
                    next_usable_solar.isoformat()
                    if next_usable_solar is not None
                    else None
                ),
                "solar_horizon_complete": next_usable_solar is not None,
                "trade_reserved_kwh": round(trade_energy_reserved_kwh, 3),
                "action": "+".join(action_parts),
                "observational_only": True,
            }
        )

    end_soc = plan[-1]["soc_end"] if plan else start_soc

    return {
        "auto_plan_72h_status": "ready",
        "auto_plan_72h_valid": True,
        "auto_plan_72h_reason": (
            "72-uurs planpreview berekend; veiligheidslading heeft voorrang, "
            "daarna solar, woningdekking en observerende handel"
        ),
        "auto_plan_72h_plan": plan,
        "auto_plan_72h_count": len(plan),
        "auto_plan_72h_start": plan[0]["time"] if plan else None,
        "auto_plan_72h_end": plan[-1]["time"] if plan else None,
        "auto_plan_72h_start_soc": round(start_soc, 1),
        "auto_plan_72h_end_soc": round(float(end_soc), 1),
        "auto_plan_72h_min_soc": round(min_soc_seen, 1),
        "auto_plan_72h_max_soc": round(max_soc_seen, 1),
        "auto_plan_72h_reserve_floor_soc": (
            round(plan[0]["reserve_floor_start_soc"], 1) if plan else None
        ),
        "auto_plan_72h_dynamic_reserve_min_soc": round(dynamic_reserve_min_soc, 1),
        "auto_plan_72h_dynamic_reserve_max_soc": round(dynamic_reserve_max_soc, 1),
        "auto_plan_72h_execution_buffer_percent": round(execution_buffer_percent, 1),
        "auto_plan_72h_max_charge_power_w": int(max_charge_power_w),
        "auto_plan_72h_max_discharge_power_w": int(max_discharge_power_w),
        "auto_plan_72h_execution_reserve_floor_soc": (
            round(plan[0]["execution_reserve_floor_start_soc"], 1) if plan else None
        ),
        "auto_plan_72h_execution_reserve_min_soc": round(execution_reserve_min_soc, 1),
        "auto_plan_72h_execution_reserve_max_soc": round(execution_reserve_max_soc, 1),
        "auto_plan_72h_min_execution_headroom_soc": round(minimum_execution_headroom_soc, 1),
        "auto_plan_72h_execution_buffer_breach_hours": execution_buffer_breach_hours,
        "auto_plan_72h_execution_buffer_safe": execution_buffer_breach_hours == 0,
        "auto_plan_72h_solar_horizon_complete": all(
            item.get("solar_horizon_complete", False) for item in plan
        ),
        "auto_plan_72h_solar_horizon_incomplete_hours": sum(
            1 for item in plan if not item.get("solar_horizon_complete", False)
        ),
        "auto_plan_72h_solar_charge_kwh": round(total_solar_charge, 3),
        "auto_plan_72h_grid_safety_charge_kwh": round(total_grid_safety_charge, 3),
        "auto_plan_72h_grid_trade_charge_kwh": round(total_grid_trade_charge, 3),
        "auto_plan_72h_home_discharge_kwh": round(total_home_discharge, 3),
        "auto_plan_72h_grid_trade_discharge_kwh": round(total_grid_trade_discharge, 3),
        "auto_plan_72h_grid_import_for_home_kwh": round(total_grid_import_for_home, 3),
        "auto_plan_72h_solar_export_kwh": round(total_solar_export, 3),
        "auto_plan_72h_trade_charge_stored_kwh": round(total_grid_trade_charge * charge_eff, 3),
        "auto_plan_72h_charge_efficiency_percent": round(charge_eff * 100.0, 1),
        "auto_plan_72h_discharge_efficiency_percent": round(discharge_eff * 100.0, 1),
        "auto_plan_72h_observational_only": True,
        "auto_plan_72h_execution_enabled": False,
        "auto_plan_72h_note": (
            "Dummy OS EMS Plan72 gebruikt de 2 procentpunt uitvoeringsbuffer, "
            "dynamische reserve en vooruitkijkende reserveplanning. Automatische "
            "laad/ontlaaduitvoering blijft buiten de huidige fysieke alpha-scope."
        ),
    }
