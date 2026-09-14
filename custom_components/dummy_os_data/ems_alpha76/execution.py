from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_CHARGE_EFFICIENCY_PERCENT,
    DEFAULT_DISCHARGE_EFFICIENCY_PERCENT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
_STORAGE_VERSION = 1
_EXTERNAL_MODE = "third_party_control"
_SELF_MODE = "self_consumption"
_MODE_WAIT_SECONDS = 20
_MONITOR_INTERVAL_SECONDS = 5
_CONTROL_PATH_STABLE_SECONDS = 60
_RUN_HISTORY_LIMIT = 10
_TRACE_LIMIT = 40


class AnkerEmsExecutionController:
    """Execute a scheduler-selected plan with an explicit user confirmation.

    Alpha 12 introduces the real execution state machine and automatic mode
    transition. It does not yet auto-trigger from the scheduler: a user/service
    call must explicitly start the selected plan. Charging is physically
    enabled; discharging remains blocked until a separate controlled discharge
    test has been validated.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store: Store[dict[str, Any]] = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}.{entry_id}.execution"
        )
        self._coordinator = None
        self._stop_task: asyncio.Task[None] | None = None
        self._cancel_monitor: Callable[[], None] | None = None
        self._stop_lock = asyncio.Lock()
        self._state: dict[str, Any] = {
            "active": False,
            "status": "idle",
            "reason": "Geen EMS-uitvoering actief",
            "slot": None,
            "origin": None,
            "action": None,
            "power_w": None,
            "target_soc": None,
            "max_runtime_h": None,
            "planned_energy_kwh": None,
            "planned_end_time": None,
            "started_at": None,
            "stop_at": None,
            "last_result": None,
            "auto_mode_switch_active": False,
            "auto_mode_switch_status": "idle",
            "auto_mode_switch_reason": "Geen automatische mode-switch actief",
            "auto_mode_switch_identity": None,
            "auto_mode_switch_started_at": None,
            "auto_mode_switch_completed_at": None,
            "auto_mode_switch_last_identity": None,
            "auto_mode_switch_last_result": None,
            "control_path_ready": False,
            "control_path_ready_reason": "Nog niet gecontroleerd",
            "control_path_stable_seconds": 0,
            "control_path_required_stable_seconds": _CONTROL_PATH_STABLE_SECONDS,
            # Alpha55 observability: compact persistent audit trail for automatic
            # physical runs. Long high-frequency telemetry is intentionally not
            # stored; only stage transitions and final run summaries are kept.
            "automatic_run_count": 0,
            "automatic_success_count": 0,
            "automatic_failure_count": 0,
            "automatic_last_identity": None,
            "automatic_last_slot": None,
            "automatic_last_action": None,
            "automatic_last_requested_power_w": None,
            "automatic_last_target_soc": None,
            "automatic_last_planned_start_time": None,
            "automatic_last_planned_end_time": None,
            "automatic_last_planned_duration_s": None,
            "automatic_last_planned_energy_kwh": None,
            "automatic_last_started_at": None,
            "automatic_last_actual_started_at": None,
            "automatic_last_finished_at": None,
            "automatic_last_duration_s": None,
            "automatic_last_duration_delta_s": None,
            "automatic_last_start_soc": None,
            "automatic_last_end_soc": None,
            "automatic_last_soc_delta": None,
            "automatic_last_target_error_soc": None,
            "automatic_last_average_actual_power_w": None,
            "automatic_last_actual_energy_kwh": None,
            "automatic_last_energy_delta_kwh": None,
            "automatic_last_result": None,
            "automatic_last_reason": None,
            "automatic_current_trace": [],
            "automatic_last_trace": [],
            "automatic_run_history": [],
            "automatic_sample_count": 0,
            "automatic_actual_power_sum_w": 0.0,
            "automatic_actual_energy_wh": 0.0,
            "automatic_previous_sample_power_w": None,
            "automatic_previous_sample_at": None,
            "automatic_last_actual_energy_source": None,
        }

    def attach_coordinator(self, coordinator: Any) -> None:
        self._coordinator = coordinator

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            for key in self._state:
                if key in stored:
                    self._state[key] = stored[key]

    @property
    def data(self) -> dict[str, Any]:
        result = dict(self._state)
        result["remaining_s"] = self.remaining_seconds
        return result

    @property
    def remaining_seconds(self) -> int | None:
        if not self._state.get("active") or not self._state.get("stop_at"):
            return None
        stop_at = dt_util.parse_datetime(str(self._state["stop_at"]))
        if stop_at is None:
            return None
        if stop_at.tzinfo is None:
            stop_at = stop_at.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return max(0, int((stop_at - dt_util.now()).total_seconds()))

    async def _async_save(self) -> None:
        await self._store.async_save(dict(self._state))

    def _trace_automatic(self, stage: str, detail: str | None = None) -> None:
        """Append one compact automatic-execution trace event in memory."""
        trace = list(self._state.get("automatic_current_trace") or [])
        event: dict[str, Any] = {"time": dt_util.now().isoformat(), "stage": stage}
        if detail:
            event["detail"] = str(detail)[:240]
        trace.append(event)
        self._state["automatic_current_trace"] = trace[-_TRACE_LIMIT:]

    def _begin_automatic_audit(
        self, *, identity: str, slot: int | str, action: str, power_w: int,
        target_soc: float, max_runtime_h: float, start_soc: Any,
        planned_start_time: Any = None, planned_energy_kwh: Any = None,
        planned_end_time: Any = None,
    ) -> None:
        """Start an automatic run audit before the first physical mode action."""
        try:
            start_soc_value = None if start_soc is None else round(float(start_soc), 2)
        except (TypeError, ValueError):
            start_soc_value = None
        planned_duration_s = max(0, int(round(float(max_runtime_h) * 3600)))
        try:
            explicit_planned_energy_kwh = max(0.0, float(planned_energy_kwh))
        except (TypeError, ValueError):
            explicit_planned_energy_kwh = (float(power_w) * float(max_runtime_h)) / 1000.0
        planned_energy_kwh = round(explicit_planned_energy_kwh, 3)
        planned_start = str(planned_start_time) if planned_start_time else dt_util.now().isoformat()
        planned_start_dt = dt_util.parse_datetime(planned_start)
        planned_end = None
        if planned_start_dt is not None:
            if planned_start_dt.tzinfo is None:
                planned_start_dt = planned_start_dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            planned_end = (planned_start_dt + timedelta(seconds=planned_duration_s)).isoformat()
        self._state.update({
            "automatic_last_identity": identity,
            "automatic_last_slot": slot,
            "automatic_last_action": action,
            "automatic_last_requested_power_w": power_w,
            "automatic_last_target_soc": target_soc,
            "automatic_last_planned_start_time": planned_start,
            "automatic_last_planned_end_time": str(planned_end_time) if planned_end_time else planned_end,
            "automatic_last_planned_duration_s": planned_duration_s,
            "automatic_last_planned_energy_kwh": planned_energy_kwh,
            "automatic_last_started_at": dt_util.now().isoformat(),
            "automatic_last_actual_started_at": None,
            "automatic_last_finished_at": None,
            "automatic_last_duration_s": None,
            "automatic_last_start_soc": start_soc_value,
            "automatic_last_end_soc": None,
            "automatic_last_average_actual_power_w": None,
            "automatic_last_result": "arming",
            "automatic_last_reason": "automatic_execution_arming",
            "automatic_current_trace": [],
            "automatic_sample_count": 0,
            "automatic_actual_power_sum_w": 0.0,
            "automatic_actual_energy_wh": 0.0,
            "automatic_previous_sample_power_w": None,
            "automatic_previous_sample_at": None,
            "automatic_last_actual_energy_source": None,
        })
        self._trace_automatic("selected", f"slot={slot}; action={action}; requested={power_w}W; target={target_soc}%")

    def _sample_automatic_actual_power(self, data: dict[str, Any]) -> None:
        """Aggregate measured power and integrate transferred energy while running."""
        if self._state.get("origin") != "automatic_72h_planner":
            return
        action = self._state.get("action")
        raw = data.get("charge_power_w") if action == "laden" else data.get("discharge_power_w")
        try:
            value = max(0.0, float(raw))
        except (TypeError, ValueError):
            return

        now = dt_util.now()
        previous_at = dt_util.parse_datetime(str(self._state.get("automatic_previous_sample_at") or ""))
        previous_power = self._state.get("automatic_previous_sample_power_w")
        if previous_at is not None and previous_power is not None:
            if previous_at.tzinfo is None:
                previous_at = previous_at.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            elapsed_s = max(0.0, min(60.0, (now - previous_at).total_seconds()))
            interval_wh = ((float(previous_power) + value) / 2.0) * elapsed_s / 3600.0
            self._state["automatic_actual_energy_wh"] = float(
                self._state.get("automatic_actual_energy_wh") or 0.0
            ) + interval_wh

        self._state["automatic_sample_count"] = int(self._state.get("automatic_sample_count") or 0) + 1
        self._state["automatic_actual_power_sum_w"] = float(self._state.get("automatic_actual_power_sum_w") or 0.0) + value
        self._state["automatic_previous_sample_power_w"] = value
        self._state["automatic_previous_sample_at"] = now.isoformat()

    def _finish_automatic_audit(self, result: str, reason: str, data: dict[str, Any] | None = None) -> None:
        """Finalize and persist a compact run summary."""
        if not self._state.get("automatic_last_identity"):
            return
        finished = dt_util.now()
        started = dt_util.parse_datetime(str(
            self._state.get("automatic_last_actual_started_at")
            or self._state.get("automatic_last_started_at")
            or ""
        ))
        duration_s = None
        if started is not None:
            if started.tzinfo is None:
                started = started.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            duration_s = max(0, int((finished - started).total_seconds()))
        end_soc = None
        if data is not None:
            try:
                end_soc = round(float(data.get("soc")), 2)
            except (TypeError, ValueError):
                end_soc = None
        samples = int(self._state.get("automatic_sample_count") or 0)
        avg_power = None
        if samples > 0:
            avg_power = round(float(self._state.get("automatic_actual_power_sum_w") or 0.0) / samples, 1)
        self._trace_automatic("finished", f"result={result}; reason={reason}")
        trace = list(self._state.get("automatic_current_trace") or [])
        planned_duration_s = self._state.get("automatic_last_planned_duration_s")
        planned_energy_kwh = self._state.get("automatic_last_planned_energy_kwh")

        # Primary measurement: integrate the 5-second live power samples.
        integrated_kwh = max(0.0, float(self._state.get("automatic_actual_energy_wh") or 0.0) / 1000.0)
        actual_energy_kwh = round(integrated_kwh, 3) if samples > 1 else None
        actual_energy_source = "power_samples" if samples > 1 else "unavailable"

        soc_delta = None
        start_soc = self._state.get("automatic_last_start_soc")
        if start_soc is not None and end_soc is not None:
            soc_delta = round(float(end_soc) - float(start_soc), 2)

        # Live alpha57 runs showed a valid SOC change while the measured power
        # aggregate could remain 0 W. In that specific case, use SOC delta as a
        # transparent fallback estimate rather than storing a false 0.000 kWh.
        if (actual_energy_kwh is None or actual_energy_kwh <= 0.005) and soc_delta is not None and abs(soc_delta) >= 0.5:
            try:
                capacity_kwh = max(0.1, float((data or {}).get("battery_capacity_kwh") or DEFAULT_BATTERY_CAPACITY_KWH))
                charge_eff = max(0.50, min(1.00, float((data or {}).get("charge_efficiency_percent") or DEFAULT_CHARGE_EFFICIENCY_PERCENT) / 100.0))
                discharge_eff = max(0.50, min(1.00, float((data or {}).get("discharge_efficiency_percent") or DEFAULT_DISCHARGE_EFFICIENCY_PERCENT) / 100.0))
                action = self._state.get("automatic_last_action")
                if action == "laden" and soc_delta > 0:
                    stored_delta_kwh = capacity_kwh * soc_delta / 100.0
                    actual_energy_kwh = round(stored_delta_kwh / charge_eff, 3)
                    actual_energy_source = "soc_delta_fallback"
                elif action == "ontladen" and soc_delta < 0:
                    stored_delta_kwh = capacity_kwh * abs(soc_delta) / 100.0
                    actual_energy_kwh = round(stored_delta_kwh * discharge_eff, 3)
                    actual_energy_source = "soc_delta_fallback"
            except (TypeError, ValueError):
                pass

        if actual_energy_kwh is not None and duration_s and actual_energy_source == "soc_delta_fallback":
            avg_power = round(actual_energy_kwh * 3600000.0 / float(duration_s), 1)

        energy_delta_kwh = None
        if actual_energy_kwh is not None and planned_energy_kwh is not None:
            energy_delta_kwh = round(actual_energy_kwh - float(planned_energy_kwh), 3)
        duration_delta_s = None
        if duration_s is not None and planned_duration_s is not None:
            duration_delta_s = int(duration_s) - int(planned_duration_s)
        target_error_soc = None
        target_soc = self._state.get("automatic_last_target_soc")
        if end_soc is not None and target_soc is not None:
            target_error_soc = round(float(end_soc) - float(target_soc), 2)
        summary = {
            "identity": self._state.get("automatic_last_identity"),
            "slot": self._state.get("automatic_last_slot"),
            "action": self._state.get("automatic_last_action"),
            "requested_power_w": self._state.get("automatic_last_requested_power_w"),
            "average_actual_power_w": avg_power,
            "planned_start_time": self._state.get("automatic_last_planned_start_time"),
            "planned_end_time": self._state.get("automatic_last_planned_end_time"),
            "planned_duration_s": planned_duration_s,
            "actual_started_at": self._state.get("automatic_last_actual_started_at") or self._state.get("automatic_last_started_at"),
            "actual_finished_at": finished.isoformat(),
            "actual_duration_s": duration_s,
            "duration_delta_s": duration_delta_s,
            "planned_energy_kwh": planned_energy_kwh,
            "actual_energy_kwh": actual_energy_kwh,
            "actual_energy_source": actual_energy_source,
            "power_sample_count": samples,
            "energy_delta_kwh": energy_delta_kwh,
            "target_soc": target_soc,
            "start_soc": start_soc,
            "end_soc": end_soc,
            "soc_delta": soc_delta,
            "target_error_soc": target_error_soc,
            "result": result,
            "reason": reason,
        }
        history = list(self._state.get("automatic_run_history") or [])
        history.append(summary)
        success = result == "completed"
        self._state.update({
            "automatic_run_count": int(self._state.get("automatic_run_count") or 0) + 1,
            "automatic_success_count": int(self._state.get("automatic_success_count") or 0) + (1 if success else 0),
            "automatic_failure_count": int(self._state.get("automatic_failure_count") or 0) + (0 if success else 1),
            "automatic_last_finished_at": finished.isoformat(),
            "automatic_last_duration_s": duration_s,
            "automatic_last_end_soc": end_soc,
            "automatic_last_average_actual_power_w": avg_power,
            "automatic_last_actual_energy_kwh": actual_energy_kwh,
            "automatic_last_actual_energy_source": actual_energy_source,
            "automatic_last_energy_delta_kwh": energy_delta_kwh,
            "automatic_last_duration_delta_s": duration_delta_s,
            "automatic_last_soc_delta": soc_delta,
            "automatic_last_target_error_soc": target_error_soc,
            "automatic_last_result": result,
            "automatic_last_reason": reason,
            "automatic_last_trace": trace[-_TRACE_LIMIT:],
            "automatic_run_history": history[-_RUN_HISTORY_LIMIT:],
            "automatic_current_trace": [],
        })

    def _entity_ids(self) -> tuple[str, str, str]:
        if self._coordinator is None:
            raise HomeAssistantError("Dummy OS EMS coordinator is niet beschikbaar")
        ids = self._coordinator.control_entity_ids
        mode = ids.get("operating_mode")
        direction = ids.get("action_direction")
        power = ids.get("power_setpoint")
        if not mode or not direction or not power:
            raise HomeAssistantError("Niet alle besturingsentiteiten zijn geconfigureerd")
        if not mode.startswith("select."):
            raise HomeAssistantError("Bedrijfsmodus moet een select-entiteit zijn")
        if not direction.startswith("select."):
            raise HomeAssistantError("Laad/ontlaadrichting moet een select-entiteit zijn")
        if not power.startswith("number."):
            raise HomeAssistantError("Vermogenssetpoint moet een number-entiteit zijn")
        return mode, direction, power

    def control_path_readiness(self) -> dict[str, Any]:
        """Return two-stage readiness for the configured Anker control path.

        Alpha52 removes the circular readiness dependency discovered on the live
        Solarbank Max AC: while the battery is in ``self_consumption`` the Anker
        integration can intentionally expose direction and power-setpoint as
        unavailable. Those controls are therefore post-mode requirements.

        Stage 1 (pre-mode) requires only a configured, available and stable
        operating-mode select. Stage 2 (post-mode) is evaluated only while the
        device is actually in ``third_party_control`` and then requires direction
        and power-setpoint to be available and stable for 60 seconds.

        ``ready`` intentionally means "safe to reach the mode-switch boundary"
        while still in self-consumption. It does not permit physical execution.
        """
        try:
            mode_entity, direction_entity, power_entity = self._entity_ids()
        except HomeAssistantError as err:
            return {
                "ready": False,
                "reason": str(err),
                "stable_seconds": 0,
                "required_stable_seconds": _CONTROL_PATH_STABLE_SECONDS,
                "pre_mode_ready": False,
                "pre_mode_reason": str(err),
                "pre_mode_stable_seconds": 0,
                "post_mode_ready": False,
                "post_mode_reason": "control_path_not_configured",
                "post_mode_stable_seconds": 0,
                "post_mode_required": False,
                "entities": {},
            }

        now = dt_util.now()
        details: dict[str, Any] = {}

        def entity_detail(key: str, entity_id: str) -> dict[str, Any]:
            state = self.hass.states.get(entity_id)
            available = state is not None and state.state not in {"unknown", "unavailable"}
            stable_s = 0.0
            if available and state is not None:
                stable_s = max(0.0, (now - state.last_changed).total_seconds())
            result = {
                "entity_id": entity_id,
                "available": available,
                "state": None if state is None else state.state,
                "stable_seconds": round(stable_s, 1),
            }
            details[key] = result
            return result

        mode = entity_detail("operating_mode", mode_entity)
        direction = entity_detail("action_direction", direction_entity)
        power = entity_detail("power_setpoint", power_entity)

        pre_blockers: list[str] = []
        if not mode["available"]:
            pre_blockers.append("operating_mode_unavailable")
        elif mode["stable_seconds"] < _CONTROL_PATH_STABLE_SECONDS:
            pre_blockers.append("operating_mode_not_stable")
        pre_mode_ready = not pre_blockers
        pre_mode_reason = "pre_mode_ready" if pre_mode_ready else ",".join(pre_blockers)
        pre_mode_stable = mode["stable_seconds"] if mode["available"] else 0.0

        external_active = mode["available"] and mode["state"] == _EXTERNAL_MODE
        post_blockers: list[str] = []
        if not external_active:
            post_mode_ready = False
            post_mode_reason = "awaiting_third_party_control"
            post_mode_stable = 0.0
        else:
            for key, item in (("action_direction", direction), ("power_setpoint", power)):
                if not item["available"]:
                    post_blockers.append(f"{key}_unavailable")
                elif item["stable_seconds"] < _CONTROL_PATH_STABLE_SECONDS:
                    post_blockers.append(f"{key}_not_stable")
            post_mode_ready = not post_blockers
            post_mode_reason = "post_mode_ready" if post_mode_ready else ",".join(post_blockers)
            post_mode_stable = (
                min(direction["stable_seconds"], power["stable_seconds"])
                if direction["available"] and power["available"]
                else 0.0
            )

        ready = pre_mode_ready and (post_mode_ready if external_active else True)
        reason = (
            "control_path_ready"
            if ready
            else (post_mode_reason if external_active else pre_mode_reason)
        )
        stable_seconds = post_mode_stable if external_active else pre_mode_stable
        return {
            "ready": ready,
            "reason": reason,
            "stable_seconds": round(stable_seconds, 1),
            "required_stable_seconds": _CONTROL_PATH_STABLE_SECONDS,
            "pre_mode_ready": pre_mode_ready,
            "pre_mode_reason": pre_mode_reason,
            "pre_mode_stable_seconds": round(pre_mode_stable, 1),
            "post_mode_ready": post_mode_ready,
            "post_mode_reason": post_mode_reason,
            "post_mode_stable_seconds": round(post_mode_stable, 1),
            "post_mode_required": external_active,
            "entities": details,
        }

    async def _wait_for_external_controls(self) -> None:
        """Wait until external mode and its dependent control entities are live."""
        if self._coordinator is None:
            raise HomeAssistantError("Dummy OS EMS coordinator is niet beschikbaar")
        deadline = dt_util.now() + timedelta(seconds=_MODE_WAIT_SECONDS)
        while dt_util.now() < deadline:
            await self._coordinator.async_refresh()
            data = self._coordinator.data
            if (
                data.get("operating_mode") == _EXTERNAL_MODE
                and data.get("action_direction") is not None
                and data.get("power_setpoint_w") is not None
            ):
                return
            await asyncio.sleep(1)
        raise HomeAssistantError(
            "Externe modus werd niet tijdig beschikbaar of besturingsbronnen bleven unavailable"
        )

    async def async_recover_if_needed(self) -> None:
        if self._state.get("active"):
            _LOGGER.warning("Recovering interrupted Dummy OS EMS execution")
            await self.async_stop("restart_recovery", emergency=True)
            return
        if self._state.get("auto_mode_switch_active"):
            _LOGGER.warning("Recovering interrupted Dummy OS EMS automatic arming")
            await self.async_abort_automatic_arming("restart_recovery")

    async def async_abort_automatic_arming(self, reason: str) -> None:
        """Fail-safe an in-progress automatic mode transition before power handoff."""
        if not self._state.get("auto_mode_switch_active"):
            return
        mode_entity = power_entity = None
        try:
            mode_entity, _direction_entity, power_entity = self._entity_ids()
        except HomeAssistantError:
            pass
        errors: list[str] = []
        if power_entity:
            state = self.hass.states.get(power_entity)
            if state is not None and state.state not in {"unknown", "unavailable"}:
                try:
                    await self.hass.services.async_call(
                        "number", "set_value", {"value": 0},
                        target={"entity_id": power_entity}, blocking=True,
                    )
                except Exception as err:
                    errors.append(f"power_zero_failed: {err}")
        if mode_entity:
            state = self.hass.states.get(mode_entity)
            if state is not None and state.state not in {"unknown", "unavailable", _SELF_MODE}:
                try:
                    await self.hass.services.async_call(
                        "select", "select_option", {"option": _SELF_MODE},
                        target={"entity_id": mode_entity}, blocking=True,
                    )
                except Exception as err:
                    errors.append(f"self_consumption_failed: {err}")
        result_reason = reason if not errors else f"{reason}; {'; '.join(errors)}"
        self._state.update({
            "auto_mode_switch_active": False,
            "auto_mode_switch_status": "aborted" if not errors else "abort_error",
            "auto_mode_switch_reason": result_reason,
            "auto_mode_switch_completed_at": dt_util.now().isoformat(),
            "auto_mode_switch_last_result": "aborted" if not errors else "abort_error",
        })
        await self._async_save()
        if self._coordinator is not None:
            await self._coordinator.async_refresh()

    def evaluate_automatic_handoff(self, data: dict[str, Any]) -> dict[str, Any]:
        """Evaluate Safety Guard -> Execution Controller handoff without actuating.

        The observer handoff deliberately stops before any Home Assistant service call. The
        method mirrors the final prerequisites the Execution Controller will
        require later, so the complete automatic chain can be observed before
        physical execution is enabled.
        """
        slot = data.get("auto_safety_handoff_selected_slot")
        slots = data.get("scheduler_slots", {}) or {}
        detail = slots.get(slot) or slots.get(str(slot)) or {}
        origin = str(detail.get("origin") or "manual")

        base = {
            "auto_execution_handoff_enabled": True,
            "auto_execution_handoff_required": False,
            "auto_execution_handoff_ready": False,
            "auto_execution_handoff_status": "not_required",
            "auto_execution_handoff_reason": "Geen door Safety Guard goedgekeurde automatische actie",
            "auto_execution_handoff_reasons": [],
            "auto_execution_handoff_warnings": [],
            "auto_execution_handoff_selected_slot": None,
            "auto_execution_handoff_planner_identity": None,
            "auto_execution_handoff_action": None,
            "auto_execution_handoff_power_w": None,
            "auto_execution_handoff_target_soc": None,
            "auto_execution_handoff_max_runtime_h": None,
            "auto_execution_handoff_safety_safe": bool(data.get("auto_safety_handoff_safe")),
            "auto_execution_handoff_control_path_configured": bool(data.get("control_path_configured")),
            "auto_execution_handoff_controller_idle": not bool(data.get("execution_active")),
            "auto_execution_handoff_physical_test_idle": not bool(data.get("physical_test_active")),
            "auto_execution_handoff_final_revalidation_required": True,
            "auto_execution_handoff_execution_permitted": False,
            "auto_execution_handoff_physical_control": False,
        }

        if (
            slot is None
            or data.get("auto_safety_handoff_required") is not True
            or origin != "automatic_72h_planner"
        ):
            return base

        reasons: list[str] = []
        warnings: list[str] = []
        action = detail.get("action")
        try:
            power_w = int(float(detail.get("power_w") or 0))
        except (TypeError, ValueError):
            power_w = 0
        try:
            target_soc = float(detail.get("target_soc") or 0)
        except (TypeError, ValueError):
            target_soc = 0.0
        try:
            max_runtime_h = float(detail.get("max_runtime_h") or 0)
        except (TypeError, ValueError):
            max_runtime_h = 0.0
        planner_identity = detail.get("planner_identity")

        if data.get("auto_safety_handoff_safe") is not True:
            reasons.append("safety_handoff_not_safe")
        if data.get("auto_prestart_safe") is not True:
            reasons.append("prestart_not_safe")
        if data.get("auto_prestart_current_identity_match") is not True:
            reasons.append("planner_identity_mismatch")
        if not planner_identity:
            reasons.append("planner_identity_missing")
        if action not in {"laden", "ontladen"}:
            reasons.append("invalid_action")

        max_power = int(data.get("max_discharge_power_w") or 800) if action == "ontladen" else int(data.get("max_charge_power_w") or 800)
        if not 100 <= power_w <= max_power:
            reasons.append("invalid_power")
        if not 5 <= target_soc <= 100:
            reasons.append("invalid_target_soc")
        if not 0.25 <= max_runtime_h <= 12:
            reasons.append("invalid_runtime")
        if not data.get("control_path_configured"):
            reasons.append("control_path_not_configured")
        if data.get("physical_test_active"):
            reasons.append("physical_test_active")
        if data.get("execution_active"):
            reasons.append("execution_already_active")

        # The actual mode switch and final post-mode revalidation remain future
        # execution-stage responsibilities. They are warnings here, not blockers.
        if data.get("operating_mode") != _EXTERNAL_MODE:
            warnings.append("external_mode_switch_required")
        if data.get("auto_prestart_current_signature_match") is not True:
            warnings.append("planner_revision_changed")

        ready = len(reasons) == 0
        return {
            "auto_execution_handoff_enabled": True,
            "auto_execution_handoff_required": True,
            "auto_execution_handoff_ready": ready,
            "auto_execution_handoff_status": "ready_observe" if ready else "blocked",
            "auto_execution_handoff_reason": (
                "Execution Controller handoff is gereed voor finale live revalidatie; fysieke uitvoering vereist de Automatic Execution-arm"
                if ready
                else ", ".join(reasons)
            ),
            "auto_execution_handoff_reasons": reasons,
            "auto_execution_handoff_warnings": warnings,
            "auto_execution_handoff_selected_slot": slot,
            "auto_execution_handoff_planner_identity": planner_identity,
            "auto_execution_handoff_action": action,
            "auto_execution_handoff_power_w": power_w,
            "auto_execution_handoff_target_soc": target_soc,
            "auto_execution_handoff_max_runtime_h": max_runtime_h,
            "auto_execution_handoff_safety_safe": bool(data.get("auto_safety_handoff_safe")),
            "auto_execution_handoff_control_path_configured": bool(data.get("control_path_configured")),
            "auto_execution_handoff_controller_idle": not bool(data.get("execution_active")),
            "auto_execution_handoff_physical_test_idle": not bool(data.get("physical_test_active")),
            "auto_execution_handoff_final_revalidation_required": True,
            "auto_execution_handoff_execution_permitted": False,
            "auto_execution_handoff_physical_control": False,
        }

    def evaluate_final_revalidation(self, data: dict[str, Any]) -> dict[str, Any]:
        """Perform the last non-actuating live validation before a future mode switch.

        Alpha38 keeps physical execution disabled. This gate mirrors the exact
        conditions that must still be true immediately before the Execution
        Controller may switch the battery to external control in a later
        release. It is intentionally evaluated from the latest coordinator
        snapshot and never calls Home Assistant services.
        """
        slot = data.get("auto_execution_handoff_selected_slot")
        slots = data.get("scheduler_slots", {}) or {}
        detail = slots.get(slot) or slots.get(str(slot)) or {}
        origin = str(detail.get("origin") or "manual")

        base = {
            "auto_final_revalidation_enabled": True,
            "auto_final_revalidation_required": False,
            "auto_final_revalidation_safe": False,
            "auto_final_revalidation_status": "not_required",
            "auto_final_revalidation_reason": "Geen Execution Controller handoff gereed voor finale live validatie",
            "auto_final_revalidation_reasons": [],
            "auto_final_revalidation_warnings": [],
            "auto_final_revalidation_checks": [],
            "auto_final_revalidation_selected_slot": None,
            "auto_final_revalidation_planner_identity": None,
            "auto_final_revalidation_planner_signature": None,
            "auto_final_revalidation_checked_at": dt_util.now().isoformat(),
            "auto_final_revalidation_action": None,
            "auto_final_revalidation_power_w": None,
            "auto_final_revalidation_target_soc": None,
            "auto_final_revalidation_current_soc": self._number_value(data.get("soc")),
            "auto_final_revalidation_execution_reserve_soc": data.get("auto_prestart_execution_reserve_soc"),
            "auto_final_revalidation_control_path_configured": bool(data.get("control_path_configured")),
            "auto_final_revalidation_controller_idle": not bool(data.get("execution_active")),
            "auto_final_revalidation_physical_test_idle": not bool(data.get("physical_test_active")),
            "auto_final_revalidation_mode_switch_required": data.get("operating_mode") != _EXTERNAL_MODE,
            "auto_final_revalidation_execution_permitted": False,
            "auto_final_revalidation_physical_control": False,
        }

        if (
            slot is None
            or data.get("auto_execution_handoff_required") is not True
            or data.get("auto_execution_handoff_ready") is not True
            or origin != "automatic_72h_planner"
        ):
            return base

        reasons: list[str] = []
        warnings: list[str] = []
        checks: list[dict[str, Any]] = []

        def add_check(name: str, passed: bool, detail_text: str, *, warning_only: bool = False) -> None:
            severity = "ok" if passed else ("warning" if warning_only else "blocker")
            checks.append({"check": name, "passed": passed, "severity": severity, "detail": detail_text})
            if not passed:
                (warnings if warning_only else reasons).append(name)

        action = detail.get("action")
        power_w = self._number_value(detail.get("power_w"))
        target_soc = self._number_value(detail.get("target_soc"))
        soc = self._number_value(data.get("soc"))
        charge_power = self._number_value(data.get("charge_power_w"))
        discharge_power = self._number_value(data.get("discharge_power_w"))
        planner_identity = detail.get("planner_identity")
        planner_signature = detail.get("planner_signature")
        reserve_soc = self._number_value(data.get("auto_prestart_execution_reserve_soc"))

        add_check("scheduler_ready", bool(data.get("scheduler_ready")), "Scheduler still has a start-ready plan")
        add_check("selected_slot_match", data.get("scheduler_selected_slot") == slot, f"Selected slot: {data.get('scheduler_selected_slot')}; expected: {slot}")
        add_check("automatic_origin", origin == "automatic_72h_planner", f"Origin: {origin}")
        add_check("prestart_safe", data.get("auto_prestart_safe") is True, "Authoritative pre-start gate safe")
        add_check("safety_handoff_safe", data.get("auto_safety_handoff_safe") is True, "Safety Guard handoff safe")
        add_check("execution_handoff_ready", data.get("auto_execution_handoff_ready") is True, "Execution handoff ready")
        add_check("planner_identity_match", data.get("auto_prestart_current_identity_match") is True and planner_identity == data.get("auto_execution_handoff_planner_identity"), "Planner identity unchanged")
        add_check("planner_signature_match", data.get("auto_prestart_current_signature_match") is True, "Planner revision unchanged", warning_only=True)
        add_check("forecast_ready", data.get("forecast_ready") is True, "Forecast sources ready")
        purpose = str(detail.get("purpose") or "")
        safety_recovery_action = bool(
            action == "laden"
            and purpose in {"veiligheidsladen", "veiligheidsladen+handelsladen"}
        )
        execution_buffer_safe = data.get("auto_plan_72h_execution_buffer_safe") is True
        add_check(
            "execution_buffer_safe",
            execution_buffer_safe or safety_recovery_action,
            (
                "Execution buffer safe"
                if execution_buffer_safe
                else "Execution buffer unsafe; safety charge is allowed to restore it"
            ),
        )
        add_check("control_path_configured", bool(data.get("control_path_configured")), "Control path configured")
        add_check("controller_idle", not bool(data.get("execution_active")), "Execution Controller idle")
        add_check("physical_test_idle", not bool(data.get("physical_test_active")), "Physical test idle")
        add_check("action_valid", action in {"laden", "ontladen"}, f"Action: {action}")

        max_power = int(data.get("max_discharge_power_w") or 800) if action == "ontladen" else int(data.get("max_charge_power_w") or 800)
        add_check("power_valid", power_w is not None and 100 <= power_w <= max_power, f"Power: {power_w} W; allowed 100-{max_power} W")
        add_check("soc_valid", soc is not None and 0 <= soc <= 100, f"Current SOC: {soc}%")
        add_check("target_soc_valid", target_soc is not None and 5 <= target_soc <= 100, f"Target SOC: {target_soc}%")

        direction_ok = False
        if soc is not None and target_soc is not None:
            if action == "laden":
                direction_ok = soc < target_soc
            elif action == "ontladen":
                direction_ok = soc > target_soc
        add_check("target_direction_valid", direction_ok, "Current SOC still requires the planned action")

        reserve_ok = True
        if action == "ontladen":
            reserve_ok = soc is not None and reserve_soc is not None and soc > reserve_soc
        add_check("execution_reserve_available", reserve_ok, f"Execution reserve: {reserve_soc}%")

        conflicting_power = (
            charge_power is not None
            and discharge_power is not None
            and charge_power > 100
            and discharge_power > 100
        )
        add_check("no_conflicting_battery_power", not conflicting_power, f"Charge: {charge_power} W; discharge: {discharge_power} W")

        if data.get("operating_mode") != _EXTERNAL_MODE:
            warnings.append("external_mode_switch_required")
            checks.append({
                "check": "external_mode_ready",
                "passed": False,
                "severity": "warning",
                "detail": "Battery is not yet in third_party_control; the Execution Controller switches mode after this gate when automatic execution is armed",
            })
        else:
            checks.append({
                "check": "external_mode_ready",
                "passed": True,
                "severity": "ok",
                "detail": "Battery already in third_party_control",
            })

        safe = not reasons
        return {
            **base,
            "auto_final_revalidation_required": True,
            "auto_final_revalidation_safe": safe,
            "auto_final_revalidation_status": "ready_observe" if safe else "blocked",
            "auto_final_revalidation_reason": (
                "Finale live revalidatie akkoord; toekomstige mode-switch mag pas in een latere release worden vrijgegeven"
                if safe
                else ", ".join(reasons)
            ),
            "auto_final_revalidation_reasons": reasons,
            "auto_final_revalidation_warnings": warnings,
            "auto_final_revalidation_checks": checks,
            "auto_final_revalidation_selected_slot": slot,
            "auto_final_revalidation_planner_identity": planner_identity,
            "auto_final_revalidation_planner_signature": planner_signature,
            "auto_final_revalidation_checked_at": dt_util.now().isoformat(),
            "auto_final_revalidation_action": action,
            "auto_final_revalidation_power_w": int(power_w) if power_w is not None else None,
            "auto_final_revalidation_target_soc": target_soc,
            "auto_final_revalidation_current_soc": soc,
            "auto_final_revalidation_execution_reserve_soc": reserve_soc,
            "auto_final_revalidation_control_path_configured": bool(data.get("control_path_configured")),
            "auto_final_revalidation_controller_idle": not bool(data.get("execution_active")),
            "auto_final_revalidation_physical_test_idle": not bool(data.get("physical_test_active")),
            "auto_final_revalidation_mode_switch_required": data.get("operating_mode") != _EXTERNAL_MODE,
            "auto_final_revalidation_execution_permitted": False,
            "auto_final_revalidation_physical_control": False,
        }

    def evaluate_mode_switch_transaction(self, data: dict[str, Any]) -> dict[str, Any]:
        """Preview the guarded external-mode transaction without actuating.

        Alpha39 turns the final revalidation result into an explicit transaction
        plan for the guarded physical mode switch. This evaluator itself calls no Home Assistant service.
        called here. The preview requires a zero-power safety step, the mode
        transition, control-source availability recheck and a final safe-return
        path before direction/power execution may ever be enabled.
        """
        required = bool(data.get("auto_final_revalidation_required"))
        safe = bool(data.get("auto_final_revalidation_safe"))
        mode = data.get("operating_mode")
        control_ok = bool(data.get("control_path_configured"))
        controller_idle = not bool(data.get("execution_active"))
        test_idle = not bool(data.get("physical_test_active"))
        power = self._number_value(data.get("power_setpoint_w"))

        blockers: list[str] = []
        if required and not safe:
            blockers.append("final_revalidation_not_safe")
        if required and not control_ok:
            blockers.append("control_path_not_configured")
        if required and not controller_idle:
            blockers.append("execution_controller_busy")
        if required and not test_idle:
            blockers.append("physical_test_active")

        ready = required and safe and not blockers
        steps = [
            {"step": 1, "action": "zero_power_guard", "required": True, "physical": False},
            {"step": 2, "action": "switch_third_party_control", "required": mode != _EXTERNAL_MODE, "physical": False},
            {"step": 3, "action": "wait_external_controls", "required": True, "physical": False},
            {"step": 4, "action": "post_mode_revalidation", "required": True, "physical": False},
            {"step": 5, "action": "direction_and_power_handoff", "required": True, "physical": False, "enabled": False},
            {"step": 6, "action": "safe_return_self_consumption", "required": True, "physical": False},
        ]
        return {
            "auto_mode_switch_preview_enabled": True,
            "auto_mode_switch_preview_required": required,
            "auto_mode_switch_preview_ready": ready,
            "auto_mode_switch_preview_status": "ready_observe" if ready else ("blocked" if required else "not_required"),
            "auto_mode_switch_preview_reason": (
                "Mode-switch transaction is gereed; fysieke uitvoering blijft afhankelijk van de Automatic Execution-arm en finale revalidatie"
                if ready else (", ".join(blockers) if blockers else "Geen finale revalidatie actief")
            ),
            "auto_mode_switch_preview_blockers": blockers,
            "auto_mode_switch_preview_steps": steps,
            "auto_mode_switch_preview_current_mode": mode,
            "auto_mode_switch_preview_power_setpoint_w": power,
            "auto_mode_switch_preview_zero_power_guard_required": power is None or abs(power) > 1,
            "auto_mode_switch_preview_post_mode_revalidation_required": True,
            "auto_mode_switch_preview_safe_return_required": True,
            "auto_mode_switch_preview_execution_permitted": False,
            "auto_mode_switch_preview_physical_control": False,
        }

    async def async_run_automatic_mode_switch_only(self) -> bool:
        """Physically validate only the guarded external-mode transaction.

        Alpha40 is intentionally limited: it may set the configured power setpoint
        to 0 W, switch to third_party_control, wait for the external controls,
        revalidate the complete automatic safety chain, and immediately return to
        self_consumption. It never selects charge/discharge direction and never
        applies a non-zero power setpoint. A planner identity is handled at most
        once, including across Home Assistant restarts.
        """
        if self._coordinator is None:
            raise HomeAssistantError("Dummy OS EMS coordinator is niet beschikbaar")
        if self._state.get("active") or self._state.get("auto_mode_switch_active"):
            raise HomeAssistantError("Execution Controller is al bezig")
        if self._coordinator.physical_test.data.get("active"):
            raise HomeAssistantError("Er is nog een fysieke test actief")

        await self._coordinator.async_refresh()
        data = self._coordinator.data
        if data.get("auto_mode_switch_preview_ready") is not True:
            raise HomeAssistantError("Mode-switch preview is niet gereed")
        if data.get("auto_final_revalidation_safe") is not True:
            raise HomeAssistantError("Finale live revalidatie is niet veilig")

        slot = data.get("auto_final_revalidation_selected_slot")
        detail = ((data.get("scheduler_slots", {}) or {}).get(slot) or
                  (data.get("scheduler_slots", {}) or {}).get(str(slot)) or {})
        identity = detail.get("planner_identity")
        if not identity or detail.get("origin") != "automatic_72h_planner":
            raise HomeAssistantError("Geen geldige automatische planner identity geselecteerd")
        if identity == self._state.get("auto_mode_switch_last_identity"):
            return False

        readiness = self.control_path_readiness()
        self._state.update({
            "control_path_ready": bool(readiness.get("ready")),
            "control_path_ready_reason": readiness.get("reason"),
            "control_path_stable_seconds": readiness.get("stable_seconds", 0),
            "control_path_required_stable_seconds": readiness.get("required_stable_seconds", _CONTROL_PATH_STABLE_SECONDS),
        })
        await self._async_save()
        if not readiness.get("ready"):
            # Normal startup condition: do not touch the battery and do not mark
            # the planner identity as failed/handled. A later coordinator update
            # may retry after the Anker control path has become stable.
            return False

        mode_entity, _direction_entity, power_entity = self._entity_ids()
        now = dt_util.now()
        self._state.update({
            "auto_mode_switch_active": True,
            "auto_mode_switch_status": "zero_power_guard",
            "auto_mode_switch_reason": "Automatische mode-switch validatie gestart",
            "auto_mode_switch_identity": identity,
            "auto_mode_switch_started_at": now.isoformat(),
            "auto_mode_switch_completed_at": None,
            "auto_mode_switch_last_result": None,
        })
        await self._async_save()

        try:
            # Step 1: zero-power guard. Never issue a non-zero setpoint in alpha40.
            await self.hass.services.async_call(
                "number", "set_value", {"value": 0},
                target={"entity_id": power_entity}, blocking=True,
            )

            self._state.update({
                "auto_mode_switch_status": "switching_external_mode",
                "auto_mode_switch_reason": "Zero-power guard actief; third_party_control wordt getest",
            })
            await self._async_save()

            if data.get("operating_mode") != _EXTERNAL_MODE:
                await self.hass.services.async_call(
                    "select", "select_option", {"option": _EXTERNAL_MODE},
                    target={"entity_id": mode_entity}, blocking=True,
                )
            await self._wait_for_external_controls()

            self._state.update({
                "auto_mode_switch_status": "post_mode_revalidation",
                "auto_mode_switch_reason": "Externe modus actief; finale veiligheidsketen wordt opnieuw gevalideerd",
            })
            await self._async_save()

            await self._coordinator.async_refresh()
            armed = self._coordinator.data
            armed_slot = armed.get("auto_final_revalidation_selected_slot")
            armed_detail = ((armed.get("scheduler_slots", {}) or {}).get(armed_slot) or
                            (armed.get("scheduler_slots", {}) or {}).get(str(armed_slot)) or {})
            blockers=[]
            if armed.get("operating_mode") != _EXTERNAL_MODE:
                blockers.append("not_in_external_mode")
            if armed.get("auto_final_revalidation_safe") is not True:
                blockers.append("final_revalidation_not_safe")
            if armed.get("auto_mode_switch_preview_ready") is not True:
                blockers.append("mode_switch_preview_not_ready")
            if armed_detail.get("planner_identity") != identity:
                blockers.append("planner_identity_changed")
            if armed.get("physical_test_active"):
                blockers.append("physical_test_active")
            if blockers:
                raise HomeAssistantError(", ".join(blockers))

            # Alpha40 deliberately stops here: no direction and no non-zero power.
            self._state.update({
                "auto_mode_switch_status": "safe_return",
                "auto_mode_switch_reason": "Mode-switch gevalideerd; veilige terugkeer naar self_consumption",
            })
            await self._async_save()
            await self.hass.services.async_call(
                "number", "set_value", {"value": 0},
                target={"entity_id": power_entity}, blocking=True,
            )
            await self.hass.services.async_call(
                "select", "select_option", {"option": _SELF_MODE},
                target={"entity_id": mode_entity}, blocking=True,
            )

            completed = dt_util.now().isoformat()
            self._state.update({
                "auto_mode_switch_active": False,
                "auto_mode_switch_status": "completed",
                "auto_mode_switch_reason": "Fysieke mode-switch en veilige terugkeer succesvol gevalideerd",
                "auto_mode_switch_completed_at": completed,
                "auto_mode_switch_last_identity": identity,
                "auto_mode_switch_last_result": "success",
            })
            await self._async_save()
            await self._coordinator.async_refresh()
            return True
        except Exception as err:
            _LOGGER.exception("Automatic Dummy OS EMS mode-switch validation failed")
            # Fail safe: zero power first, then self_consumption.
            try:
                await self.hass.services.async_call(
                    "number", "set_value", {"value": 0},
                    target={"entity_id": power_entity}, blocking=True,
                )
            except Exception:
                _LOGGER.exception("Failed to apply zero-power guard during mode-switch abort")
            try:
                await self.hass.services.async_call(
                    "select", "select_option", {"option": _SELF_MODE},
                    target={"entity_id": mode_entity}, blocking=True,
                )
            except Exception:
                _LOGGER.exception("Failed to return to self_consumption during mode-switch abort")
            self._state.update({
                "auto_mode_switch_active": False,
                "auto_mode_switch_status": "failed",
                "auto_mode_switch_reason": f"Mode-switch validatie mislukt: {err}",
                "auto_mode_switch_completed_at": dt_util.now().isoformat(),
                "auto_mode_switch_last_identity": identity,
                "auto_mode_switch_last_result": f"failed: {err}",
            })
            await self._async_save()
            await self._coordinator.async_refresh()
            raise HomeAssistantError(f"Automatische mode-switch validatie mislukt: {err}") from err

    @staticmethod
    def _number_value(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    async def async_execute_selected_plan(self) -> None:
        if self._coordinator is None:
            raise HomeAssistantError("Dummy OS EMS coordinator is niet beschikbaar")
        if self._state.get("active"):
            raise HomeAssistantError("Er is al een EMS-uitvoering actief")
        if self._state.get("auto_mode_switch_active"):
            raise HomeAssistantError("Automatische mode-switch validatie is actief")
        if self._coordinator.physical_test.data.get("active"):
            raise HomeAssistantError("Er is nog een fysieke test actief")

        await self._coordinator.async_refresh()
        data = self._coordinator.data
        if not data.get("simulation_mode"):
            raise HomeAssistantError(
                "Alpha 12 verwacht dat de normale automatische planner nog in simulation staat"
            )
        if not data.get("scheduler_ready"):
            raise HomeAssistantError("Scheduler heeft geen startklaar plan")

        slot = data.get("scheduler_selected_slot")
        slots = data.get("scheduler_slots", {}) or {}
        detail = slots.get(slot) or slots.get(str(slot)) or {}
        action = detail.get("action")
        power_w = int(float(detail.get("power_w") or 0))
        target_soc = float(detail.get("target_soc") or 0)
        max_runtime_h = float(detail.get("max_runtime_h") or 0)
        soc = data.get("soc")

        if action not in {"laden", "ontladen"}:
            raise HomeAssistantError("Geselecteerd plan bevat geen ondersteunde batterijactie")
        max_power_w = int(data.get("max_discharge_power_w") or 800) if action == "ontladen" else int(data.get("max_charge_power_w") or 800)
        if not 100 <= power_w <= max_power_w:
            raise HomeAssistantError(
                f"Planvermogen valt buiten 100-{max_power_w} W voor {action}"
            )
        if not 5 <= target_soc <= 100:
            raise HomeAssistantError("Doel-SOC valt buiten 5-100%")
        if not 0.25 <= max_runtime_h <= 12:
            raise HomeAssistantError("Maximale looptijd valt buiten 0,25-12 uur")
        if soc is None:
            raise HomeAssistantError("SOC is niet beschikbaar")
        try:
            soc_value = float(soc)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("SOC is ongeldig") from err
        if action == "laden":
            if soc_value >= target_soc:
                raise HomeAssistantError("Laaddoel-SOC is al bereikt")
            if (data.get("discharge_power_w") or 0) > 100:
                raise HomeAssistantError("Batterij ontlaadt momenteel; laden wordt niet gestart")
        else:
            if soc_value <= 5:
                raise HomeAssistantError("Minimale SOC van 5% is bereikt")
            if soc_value <= target_soc:
                raise HomeAssistantError("Ontlaaddoel-SOC is al bereikt")
            if (data.get("charge_power_w") or 0) > 100:
                raise HomeAssistantError("Batterij laadt momenteel; ontladen wordt niet gestart")

        mode_entity, direction_entity, power_entity = self._entity_ids()
        now = dt_util.now()
        stop_at = now + timedelta(hours=max_runtime_h)
        self._state.update(
            {
                "active": True,
                "status": "arming_external_mode",
                "reason": "Externe modus wordt automatisch geactiveerd",
                "slot": slot,
                "origin": detail.get("origin", "manual"),
                "action": action,
                "power_w": power_w,
                "target_soc": target_soc,
                "max_runtime_h": max_runtime_h,
                "started_at": now.isoformat(),
                "stop_at": stop_at.isoformat(),
                "last_result": None,
            }
        )
        await self._async_save()
        await self._coordinator.async_refresh()

        try:
            if data.get("operating_mode") != _EXTERNAL_MODE:
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {"option": _EXTERNAL_MODE},
                    target={"entity_id": mode_entity},
                    blocking=True,
                )
            await self._wait_for_external_controls()

            # Re-evaluate the full safety/controller chain after the mode switch.
            await self._coordinator.async_refresh()
            armed = self._coordinator.data
            if not armed.get("safety_safe"):
                raise HomeAssistantError(
                    f"Safety Guard blokkeert uitvoering: {armed.get('safety_reason') or 'onbekende reden'}"
                )
            if not armed.get("controller_ready"):
                raise HomeAssistantError(
                    f"Action Controller niet gereed: {armed.get('controller_reason') or 'onbekende reden'}"
                )
            if armed.get("controller_action") != action:
                raise HomeAssistantError("Geselecteerde actie wijzigde tijdens het inschakelen")

            self._state.update(
                {
                    "status": "starting",
                    "reason": f"Plan {slot} wordt gestart: {power_w} W {action} tot {target_soc:.0f}%",
                }
            )
            await self._async_save()
            await self._coordinator.async_refresh()

            await self.hass.services.async_call(
                "select",
                "select_option",
                {"option": "charge" if action == "laden" else "discharge"},
                target={"entity_id": direction_entity},
                blocking=True,
            )
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"value": power_w},
                target={"entity_id": power_entity},
                blocking=True,
            )
        except Exception as err:
            _LOGGER.exception("Failed to start Dummy OS EMS execution")
            await self.async_stop(f"start_failed: {err}", emergency=True)
            raise HomeAssistantError(f"EMS-uitvoering starten mislukt: {err}") from err

        self._state.update(
            {
                "status": "running",
                "reason": f"Plan {slot} actief: {action} met {power_w} W tot {target_soc:.0f}% of max {max_runtime_h:g} uur",
            }
        )
        await self._async_save()
        # The plan lifecycle is separate from the execution controller state.
        # Mark it active only after the physical command has been accepted, so
        # the scheduler can no longer select it a second time while it runs.
        await self._coordinator.plan_store.async_mark_lifecycle(
            int(slot), "actief", "execution_running"
        )
        self._schedule_stop(stop_at)
        self._schedule_monitor()
        await self._coordinator.async_refresh()

    async def async_execute_automatic_plan(self, expected_identity: str | None = None) -> bool:
        """Execute one Scheduler-selected automatic planner action physically.

        Alpha54 is the first live automatic execution path. It only starts when
        the complete observer chain is green *and* the user arm switch is on.
        The transaction is deliberately staged:

        1. capture and validate the selected planner identity;
        2. switch to ``third_party_control``;
        3. force a 0 W guard as soon as the external setpoint is available;
        4. wait until post-mode controls have been stable for 60 seconds;
        5. re-run the complete final safety/identity validation;
        6. select direction and only then apply the non-zero setpoint;
        7. monitor continuously and fail-safe back to 0 W/self-consumption.
        """
        if self._coordinator is None:
            raise HomeAssistantError("Dummy OS EMS coordinator is niet beschikbaar")
        if self._state.get("active") or self._state.get("auto_mode_switch_active"):
            return False
        if self._coordinator.physical_test.data.get("active"):
            return False

        await self._coordinator.async_refresh()
        data = self._coordinator.data
        if data.get("auto_shadow_execution_permitted") is not True:
            return False
        if data.get("auto_final_revalidation_safe") is not True:
            return False
        if data.get("auto_mode_switch_preview_ready") is not True:
            return False

        slot = data.get("auto_final_revalidation_selected_slot")
        slots = data.get("scheduler_slots", {}) or {}
        detail = slots.get(slot) or slots.get(str(slot)) or {}
        identity = detail.get("planner_identity")
        if not identity or detail.get("origin") != "automatic_72h_planner":
            return False
        if expected_identity is not None and identity != expected_identity:
            return False

        action = detail.get("action")
        try:
            power_w = int(float(detail.get("power_w") or 0))
            target_soc = float(detail.get("target_soc") or 0)
            max_runtime_h = float(detail.get("max_runtime_h") or 0)
        except (TypeError, ValueError):
            return False
        if action not in {"laden", "ontladen"}:
            return False
        max_power = int(data.get("max_discharge_power_w") or 800) if action == "ontladen" else int(data.get("max_charge_power_w") or 800)
        if not 100 <= power_w <= max_power:
            return False
        if not 5 <= target_soc <= 100 or not 0.25 <= max_runtime_h <= 12:
            return False

        mode_entity, direction_entity, power_entity = self._entity_ids()
        self._begin_automatic_audit(
            identity=identity, slot=slot, action=action, power_w=power_w,
            target_soc=target_soc, max_runtime_h=max_runtime_h, start_soc=data.get("soc"),
            planned_start_time=detail.get("start_time"),
            planned_energy_kwh=detail.get("planned_energy_kwh"),
            planned_end_time=detail.get("planned_end_time"),
        )
        now = dt_util.now()
        self._state.update({
            "auto_mode_switch_active": True,
            "auto_mode_switch_status": "automatic_execution_arming",
            "auto_mode_switch_reason": "Automatische fysieke uitvoering wordt veilig voorbereid",
            "auto_mode_switch_identity": identity,
            "auto_mode_switch_started_at": now.isoformat(),
            "auto_mode_switch_completed_at": None,
            "auto_mode_switch_last_result": None,
        })
        self._trace_automatic("arming", "pre-mode gates passed")
        await self._async_save()

        try:
            # If the setpoint is already available, zero it before the mode
            # transition. On the live Solarbank it can legitimately be
            # unavailable in self_consumption, so this step is best-effort.
            power_state = self.hass.states.get(power_entity)
            if power_state is not None and power_state.state not in {"unknown", "unavailable"}:
                await self.hass.services.async_call(
                    "number", "set_value", {"value": 0},
                    target={"entity_id": power_entity}, blocking=True,
                )

            if data.get("operating_mode") != _EXTERNAL_MODE:
                self._state.update({
                    "auto_mode_switch_status": "switching_external_mode",
                    "auto_mode_switch_reason": "Omschakelen naar third_party_control",
                })
                await self._async_save()
                await self.hass.services.async_call(
                    "select", "select_option", {"option": _EXTERNAL_MODE},
                    target={"entity_id": mode_entity}, blocking=True,
                )
                self._trace_automatic("third_party_control_requested")

            # Wait for the external controls to appear, then immediately pin
            # the setpoint to zero before waiting for the 60 s stability gate.
            await self._wait_for_external_controls()
            await self.hass.services.async_call(
                "number", "set_value", {"value": 0},
                target={"entity_id": power_entity}, blocking=True,
            )
            self._trace_automatic("zero_power_guard", "external controls available")

            self._state.update({
                "auto_mode_switch_status": "post_mode_stability",
                "auto_mode_switch_reason": "Externe besturing actief; 60 s stabiliteit en finale revalidatie vereist",
            })
            await self._async_save()

            deadline = dt_util.now() + timedelta(seconds=_CONTROL_PATH_STABLE_SECONDS + 30)
            while dt_util.now() < deadline:
                await self._coordinator.async_refresh()
                readiness = self.control_path_readiness()
                if readiness.get("post_mode_ready") is True:
                    self._trace_automatic("post_mode_ready", f"stable={readiness.get('post_mode_stable_seconds', 0)}s")
                    break
                if self._coordinator.data.get("operating_mode") != _EXTERNAL_MODE:
                    raise HomeAssistantError("third_party_control viel weg tijdens post-mode stabilisatie")
                await asyncio.sleep(2)
            else:
                raise HomeAssistantError("Post-mode besturingspad werd niet 60 seconden stabiel")

            await self._coordinator.async_refresh()
            armed = self._coordinator.data
            armed_slot = armed.get("auto_final_revalidation_selected_slot")
            armed_detail = ((armed.get("scheduler_slots", {}) or {}).get(armed_slot) or
                            (armed.get("scheduler_slots", {}) or {}).get(str(armed_slot)) or {})
            blockers: list[str] = []
            if armed.get("auto_shadow_armed") is not True:
                blockers.append("automatic_execution_disarmed")
            if armed.get("operating_mode") != _EXTERNAL_MODE:
                blockers.append("not_in_external_mode")
            if armed.get("auto_final_revalidation_safe") is not True:
                blockers.append("final_revalidation_not_safe")
            if armed.get("auto_mode_switch_preview_ready") is not True:
                blockers.append("mode_switch_preview_not_ready")
            if armed_detail.get("planner_identity") != identity:
                blockers.append("planner_identity_changed")
            if armed_slot != slot:
                blockers.append("selected_slot_changed")
            readiness = self.control_path_readiness()
            if readiness.get("post_mode_ready") is not True:
                blockers.append("post_mode_not_ready")
            if blockers:
                raise HomeAssistantError(", ".join(blockers))
            self._trace_automatic("final_revalidation_passed")

            execution_started_at = dt_util.now()
            stop_at = execution_started_at + timedelta(hours=max_runtime_h)
            planned_end_time = detail.get("planned_end_time")
            planned_end_dt = dt_util.parse_datetime(str(planned_end_time)) if planned_end_time else None
            if planned_end_dt is not None:
                if planned_end_dt.tzinfo is None:
                    planned_end_dt = planned_end_dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                # Alpha62: an automatic price-window action must not continue
                # into the next (potentially more expensive) planner hour.
                stop_at = min(stop_at, planned_end_dt)
            self._state.update({
                "automatic_last_actual_started_at": execution_started_at.isoformat(),
                "active": True,
                "status": "starting_automatic",
                "reason": f"Automatisch plan {slot}: {power_w} W {action} tot {target_soc:.0f}%",
                "slot": slot,
                "origin": "automatic_72h_planner",
                "action": action,
                "power_w": power_w,
                "target_soc": target_soc,
                "max_runtime_h": max_runtime_h,
                "planned_energy_kwh": detail.get("planned_energy_kwh"),
                "planned_end_time": detail.get("planned_end_time"),
                "started_at": execution_started_at.isoformat(),
                "stop_at": stop_at.isoformat(),
                "last_result": None,
                "auto_mode_switch_active": False,
                "auto_mode_switch_status": "automatic_handoff",
                "auto_mode_switch_reason": "Post-mode validatie akkoord; richting en vermogen worden overgedragen",
            })
            await self._async_save()

            await self.hass.services.async_call(
                "select", "select_option",
                {"option": "charge" if action == "laden" else "discharge"},
                target={"entity_id": direction_entity}, blocking=True,
            )
            await self.hass.services.async_call(
                "number", "set_value", {"value": power_w},
                target={"entity_id": power_entity}, blocking=True,
            )
            self._trace_automatic("power_handoff", f"direction={action}; requested={power_w}W")

            self._state.update({
                "status": "running",
                "reason": f"Automatisch plan {slot} actief: {action} {power_w} W tot {target_soc:.0f}% of max {max_runtime_h:g} uur",
                "auto_mode_switch_completed_at": dt_util.now().isoformat(),
                "auto_mode_switch_last_identity": identity,
                "auto_mode_switch_last_result": "automatic_execution_started",
            })
            await self._async_save()
            await self._coordinator.plan_store.async_mark_lifecycle(
                int(slot), "actief", "automatic_execution_running"
            )
            self._schedule_stop(stop_at)
            self._schedule_monitor()
            await self._coordinator.async_refresh()
            return True
        except Exception as err:
            _LOGGER.exception("Automatic Dummy OS EMS physical execution failed to start")
            # When active was already set, use the normal safe-stop path so the
            # plan lifecycle is also marked. Otherwise perform the same physical
            # fail-safe directly and leave the pending plan available for the
            # scheduler only if its start window remains valid.
            if self._state.get("active"):
                await self.async_stop(f"automatic_start_failed: {err}", emergency=True)
            else:
                try:
                    state = self.hass.states.get(power_entity)
                    if state is not None and state.state not in {"unknown", "unavailable"}:
                        await self.hass.services.async_call(
                            "number", "set_value", {"value": 0},
                            target={"entity_id": power_entity}, blocking=True,
                        )
                except Exception:
                    _LOGGER.exception("Failed to apply automatic execution zero-power abort")
                try:
                    await self.hass.services.async_call(
                        "select", "select_option", {"option": _SELF_MODE},
                        target={"entity_id": mode_entity}, blocking=True,
                    )
                except Exception:
                    _LOGGER.exception("Failed to return automatic execution to self_consumption")
                self._state.update({
                    "auto_mode_switch_active": False,
                    "auto_mode_switch_status": "failed",
                    "auto_mode_switch_reason": f"Automatische uitvoering afgebroken: {err}",
                    "auto_mode_switch_completed_at": dt_util.now().isoformat(),
                    "auto_mode_switch_last_identity": identity,
                    "auto_mode_switch_last_result": f"failed: {err}",
                })
                self._finish_automatic_audit("start_failed", str(err), self._coordinator.data if self._coordinator else None)
                await self._async_save()
                await self._coordinator.async_refresh()
            raise HomeAssistantError(f"Automatische EMS-uitvoering starten mislukt: {err}") from err

    def _schedule_stop(self, stop_at: datetime) -> None:
        if self._stop_task is not None and not self._stop_task.done():
            self._stop_task.cancel()
        self._stop_task = self.hass.async_create_task(
            self._async_auto_stop_at(stop_at),
            "Dummy OS EMS execution max-runtime stop",
        )

    async def _async_auto_stop_at(self, stop_at: datetime) -> None:
        try:
            delay = max(0.0, (stop_at - dt_util.now()).total_seconds())
            await asyncio.sleep(delay)
            if self._state.get("active"):
                reason = "max_runtime_reached"
                planned_end_raw = self._state.get("planned_end_time")
                planned_end = dt_util.parse_datetime(str(planned_end_raw)) if planned_end_raw else None
                if planned_end is not None:
                    if planned_end.tzinfo is None:
                        planned_end = planned_end.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                    if abs((stop_at - planned_end).total_seconds()) < 2.0:
                        reason = "planned_window_ended"
                await self.async_stop(reason, emergency=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Automatic EMS execution stop failed")
            self._state.update(
                {
                    "status": "stop_error",
                    "reason": "Automatische safe-stop kon niet worden uitgevoerd",
                    "last_result": "stop_error",
                }
            )
            await self._async_save()
            if self._coordinator is not None:
                await self._coordinator.async_refresh()

    def _schedule_monitor(self) -> None:
        if self._cancel_monitor is not None:
            self._cancel_monitor()
        self._cancel_monitor = async_call_later(
            self.hass,
            _MONITOR_INTERVAL_SECONDS,
            self._async_monitor_callback,
        )

    @callback
    def _async_monitor_callback(self, _now: datetime) -> None:
        """Schedule the execution monitor from the Home Assistant event loop."""
        self.hass.async_create_task(
            self._async_monitor_once(),
            "Dummy OS EMS execution monitor",
        )

    async def _async_monitor_once(self) -> None:
        if not self._state.get("active") or self._coordinator is None:
            return
        await self._coordinator.async_refresh()
        data = self._coordinator.data
        self._sample_automatic_actual_power(data)

        if data.get("operating_mode") != _EXTERNAL_MODE:
            await self.async_stop("operating_mode_changed", emergency=True)
            return

        action = self._state.get("action")
        expected_direction = "charge" if action == "laden" else "discharge"
        if data.get("action_direction") != expected_direction:
            await self.async_stop("direction_changed", emergency=True)
            return
        if data.get("power_setpoint_w") is None:
            await self.async_stop("power_setpoint_unavailable", emergency=True)
            return
        expected_power = self._number_value(self._state.get("power_w"))
        actual_setpoint = self._number_value(data.get("power_setpoint_w"))
        if (
            expected_power is None
            or actual_setpoint is None
            or abs(actual_setpoint - expected_power) > 10
        ):
            await self.async_stop("power_setpoint_changed", emergency=True)
            return
        if action == "laden" and (data.get("discharge_power_w") or 0) > 100:
            await self.async_stop("unexpected_discharge_detected", emergency=True)
            return
        if action == "ontladen" and (data.get("charge_power_w") or 0) > 100:
            await self.async_stop("unexpected_charge_detected", emergency=True)
            return

        # Reaching the planned target is a normal completion condition.
        soc = data.get("soc")
        target_soc = self._state.get("target_soc")
        if soc is None:
            await self.async_stop("soc_unavailable", emergency=True)
            return
        try:
            soc_value = float(soc)
        except (TypeError, ValueError):
            await self.async_stop("invalid_soc", emergency=True)
            return
        if not 0 <= soc_value <= 100:
            await self.async_stop("invalid_soc", emergency=True)
            return
        if data.get("device_status") is None:
            await self.async_stop("device_status_unavailable", emergency=True)
            return
        if data.get("charge_power_w") is None or data.get("discharge_power_w") is None:
            await self.async_stop("battery_power_source_unavailable", emergency=True)
            return
        if action == "laden" and target_soc is not None and soc_value >= float(target_soc):
            await self.async_stop("target_soc_reached", emergency=False)
            return
        if action == "ontladen":
            if soc_value <= 5:
                await self.async_stop("minimum_soc_reached", emergency=False)
                return
            if target_soc is not None and soc_value <= float(target_soc):
                await self.async_stop("target_soc_reached", emergency=False)
                return

        # Alpha62: for automatic planner actions the exact explicit Plan72
        # energy is the primary normal completion condition. This prevents a
        # total-hour ``soc_end`` projection from keeping grid charging active
        # beyond the economically selected amount.
        if self._state.get("origin") == "automatic_72h_planner":
            try:
                planned_energy = float(self._state.get("planned_energy_kwh") or 0.0)
                delivered_energy = float(self._state.get("automatic_actual_energy_wh") or 0.0) / 1000.0
            except (TypeError, ValueError):
                planned_energy = 0.0
                delivered_energy = 0.0
            if planned_energy > 0 and delivered_energy + 0.002 >= planned_energy:
                await self.async_stop("planned_energy_reached", emergency=False)
                return

        # Do not reuse the pre-start Safety Guard while a plan is active.
        # The Safety Guard intentionally requires a scheduler-selected
        # start-ready plan; an active lifecycle plan is deliberately removed
        # from scheduler selection to prevent duplicate execution. Runtime
        # safety is therefore enforced here directly against the live sources.
        if self.remaining_seconds == 0:
            await self.async_stop("max_runtime_reached", emergency=False)
            return

        self._schedule_monitor()

    async def async_stop(self, reason: str, *, emergency: bool = False) -> None:
        async with self._stop_lock:
            slot = self._state.get("slot")
            if not self._state.get("active") and self._state.get("status") not in {
                "arming_external_mode",
                "starting",
                "running",
                "stopping",
            }:
                return

            current_task = asyncio.current_task()
            if (
                self._stop_task is not None
                and self._stop_task is not current_task
                and not self._stop_task.done()
            ):
                self._stop_task.cancel()
            if self._stop_task is not current_task:
                self._stop_task = None
            if self._cancel_monitor is not None:
                self._cancel_monitor()
                self._cancel_monitor = None

            self._state.update(
                {"status": "stopping", "reason": f"Safe-stop actief: {reason}"}
            )
            await self._async_save()
            if self._coordinator is not None:
                await self._coordinator.async_refresh()

            mode_entity = direction_entity = power_entity = None
            try:
                mode_entity, direction_entity, power_entity = self._entity_ids()
            except HomeAssistantError:
                pass

            errors: list[str] = []
            if power_entity:
                try:
                    await self.hass.services.async_call(
                        "number",
                        "set_value",
                        {"value": 0},
                        target={"entity_id": power_entity},
                        blocking=True,
                    )
                except Exception as err:
                    errors.append(f"power_zero_failed: {err}")

            await asyncio.sleep(1)
            if mode_entity:
                try:
                    await self.hass.services.async_call(
                        "select",
                        "select_option",
                        {"option": _SELF_MODE},
                        target={"entity_id": mode_entity},
                        blocking=True,
                    )
                except Exception as err:
                    errors.append(f"self_consumption_failed: {err}")

            result = "emergency_stopped" if emergency else "completed"
            if errors:
                result = "stop_error"
                reason = f"{reason}; {'; '.join(errors)}"
            if self._state.get("origin") == "automatic_72h_planner":
                live = self._coordinator.data if self._coordinator is not None else None
                self._finish_automatic_audit(result, reason, live)
            self._state.update(
                {
                    "active": False,
                    "status": result,
                    "reason": reason,
                    "last_result": result,
                    "stop_at": dt_util.now().isoformat(),
                }
            )
            await self._async_save()

            if self._coordinator is not None and slot is not None:
                if result == "completed":
                    lifecycle = (
                        "geannuleerd"
                        if reason in {"manual_stop", "automatic_execution_disarmed"}
                        else "voltooid"
                    )
                else:
                    lifecycle = "fout"
                await self._coordinator.plan_store.async_mark_lifecycle(
                    int(slot), lifecycle, reason
                )

            if self._coordinator is not None:
                await self._coordinator.async_refresh()
            if self._stop_task is current_task:
                self._stop_task = None

    async def async_shutdown_stop(self) -> None:
        if self._state.get("active"):
            try:
                await self.async_stop("home_assistant_stop", emergency=True)
            except Exception:
                _LOGGER.exception("Could not stop EMS execution during Home Assistant shutdown")
