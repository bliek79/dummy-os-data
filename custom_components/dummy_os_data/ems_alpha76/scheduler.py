from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .const import PLAN_SLOT_COUNT
from .plan_store import AnkerEmsPlanStore


@dataclass(frozen=True)
class SchedulerCandidate:
    slot: int
    action: str
    execution_mode: str
    start_time: datetime | None
    ready_since: datetime


class AnkerEmsScheduler:
    """Evaluate persistent plan slots without executing physical actions."""

    def __init__(self, plan_store: AnkerEmsPlanStore) -> None:
        self.plan_store = plan_store

    @staticmethod
    def _parse_start(value: Any) -> datetime | None:
        if not value:
            return None
        parsed = dt_util.parse_datetime(str(value))
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return parsed

    @staticmethod
    def _base_valid(plan: dict[str, Any], max_charge_power_w: int, max_discharge_power_w: int) -> bool:
        action = plan.get("action")
        execution_mode = plan.get("execution_mode")
        power = plan.get("power_w")
        target_soc = plan.get("target_soc")
        runtime = plan.get("max_runtime_h")
        delay = plan.get("max_start_delay_min")

        if action == "geen":
            return True
        if action not in {"laden", "ontladen"}:
            return False
        if execution_mode not in {"direct", "gepland"}:
            return False
        max_power_w = max_charge_power_w if action == "laden" else max_discharge_power_w
        if not isinstance(power, (int, float)) or not 100 <= float(power) <= max_power_w:
            return False
        if not isinstance(target_soc, (int, float)) or not 5 <= float(target_soc) <= 100:
            return False
        if not isinstance(runtime, (int, float)) or not 0.25 <= float(runtime) <= 12:
            return False
        if not isinstance(delay, (int, float)) or not 1 <= float(delay) <= 120:
            return False
        return True

    def evaluate(self, max_charge_power_w: int = 3500, max_discharge_power_w: int = 3500, now: datetime | None = None) -> dict[str, Any]:
        """Return deterministic scheduler state for all three slots.

        The Scheduler determines which plan is allowed to start and exposes the
        user-configured start window. Physical execution is handled separately.
        """
        local_now = now or dt_util.now()
        if local_now.tzinfo is None:
            local_now = local_now.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

        slot_details: dict[int, dict[str, Any]] = {}
        candidates: list[SchedulerCandidate] = []
        future_starts: list[tuple[datetime, int]] = []

        for slot in range(1, PLAN_SLOT_COUNT + 1):
            plan = self.plan_store.get_plan(slot)
            action = plan.get("action")
            execution_mode = plan.get("execution_mode")
            lifecycle_status = str(plan.get("lifecycle_status", "pending"))
            parsed_start = self._parse_start(plan.get("start_time"))
            delay_min = float(plan.get("max_start_delay_min", 0) or 0)
            window_end = (
                parsed_start + timedelta(minutes=delay_min)
                if parsed_start is not None
                else None
            )

            detail: dict[str, Any] = {
                "slot": slot,
                "action": action,
                "execution_mode": execution_mode,
                "start_time": parsed_start.isoformat() if parsed_start else None,
                "start_window_end": window_end.isoformat() if window_end else None,
                "power_w": plan.get("power_w"),
                "target_soc": plan.get("target_soc"),
                "max_runtime_h": plan.get("max_runtime_h"),
                "max_start_delay_min": plan.get("max_start_delay_min"),
                "planned_energy_kwh": plan.get("planned_energy_kwh"),
                "planned_end_time": plan.get("planned_end_time"),
                "lifecycle_status": lifecycle_status,
                "lifecycle_reason": plan.get("lifecycle_reason"),
                "lifecycle_updated_at": plan.get("lifecycle_updated_at"),
                "origin": plan.get("origin", "manual"),
                "purpose": plan.get("purpose"),
                "planner_generated_at": plan.get("planner_generated_at"),
                "planner_identity": plan.get("planner_identity"),
                "planner_signature": plan.get("planner_signature"),
                "selected": False,
                "physical_control": False,
            }

            if lifecycle_status in {"actief", "voltooid", "geannuleerd", "fout"}:
                detail["status"] = lifecycle_status
            elif action == "geen":
                detail["status"] = "leeg"
            elif lifecycle_status == "concept":
                detail["status"] = "concept"
            elif not self._base_valid(plan, max_charge_power_w, max_discharge_power_w):
                detail["status"] = "ongeldig"
            elif execution_mode == "direct":
                detail["status"] = "kandidaat"
                candidates.append(
                    SchedulerCandidate(
                        slot=slot,
                        action=str(action),
                        execution_mode="direct",
                        start_time=None,
                        ready_since=local_now,
                    )
                )
            elif parsed_start is None:
                detail["status"] = "wacht_op_starttijd"
            elif local_now < parsed_start:
                detail["status"] = "wachtend"
                future_starts.append((parsed_start, slot))
            elif window_end is not None and local_now <= window_end:
                detail["status"] = "kandidaat"
                candidates.append(
                    SchedulerCandidate(
                        slot=slot,
                        action=str(action),
                        execution_mode="gepland",
                        start_time=parsed_start,
                        ready_since=parsed_start,
                    )
                )
            else:
                detail["status"] = "verlopen"

            slot_details[slot] = detail

        # Scheduled candidates are preferred by oldest due start time; direct
        # plans follow in slot order. This prevents two simulated starts from
        # being selected at the same time and makes conflicts deterministic.
        candidates.sort(
            key=lambda item: (
                0 if item.execution_mode == "gepland" else 1,
                item.ready_since,
                item.slot,
            )
        )

        selected: SchedulerCandidate | None = candidates[0] if candidates else None
        if selected is not None:
            for candidate in candidates:
                detail = slot_details[candidate.slot]
                if candidate.slot == selected.slot:
                    detail["status"] = "startklaar"
                    detail["selected"] = True
                else:
                    detail["status"] = "geblokkeerd"

        future_starts.sort(key=lambda item: (item[0], item[1]))
        next_future = future_starts[0] if future_starts else None

        if selected is not None:
            scheduler_status = "startklaar"
        elif any(detail["status"] == "actief" for detail in slot_details.values()):
            scheduler_status = "actief"
        elif any(detail["status"] == "wachtend" for detail in slot_details.values()):
            scheduler_status = "wachtend"
        elif any(
            detail["status"] in {"ongeldig", "wacht_op_starttijd", "verlopen"}
            for detail in slot_details.values()
        ):
            scheduler_status = "aandacht"
        else:
            scheduler_status = "idle"

        return {
            "scheduler_status": scheduler_status,
            "scheduler_selected_slot": selected.slot if selected else None,
            "scheduler_selected_action": selected.action if selected else None,
            "scheduler_selected_execution_mode": (
                selected.execution_mode if selected else None
            ),
            "scheduler_selected_start_time": (
                selected.start_time.isoformat() if selected and selected.start_time else None
            ),
            "scheduler_next_future_slot": next_future[1] if next_future else None,
            "scheduler_next_future_start": (
                next_future[0].isoformat() if next_future else None
            ),
            "scheduler_ready": selected is not None,
            "scheduler_slots": slot_details,
            "scheduler_physical_control": False,
        }

    def slot_status(self, slot: int, now: datetime | None = None) -> str:
        snapshot = self.evaluate(now)
        detail = snapshot["scheduler_slots"].get(slot, {})
        return str(detail.get("status", "ongeldig"))
