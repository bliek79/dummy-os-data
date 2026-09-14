from __future__ import annotations

from typing import Any

from .const import MAX_SOC_PERCENT, MIN_SOC_PERCENT


class AnkerEmsSafetyGuard:
    """Evaluate whether a scheduler-selected action is safe to prepare.

    Alpha 10 keeps the normal EMS controller non-actuating. The guard validates the current
    Home Assistant source state and the selected persistent plan, but never
    calls services or writes to the physical battery.
    """

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def evaluate(self, data: dict[str, Any]) -> dict[str, Any]:
        slot = data.get("scheduler_selected_slot")
        slots = data.get("scheduler_slots", {}) or {}
        detail = slots.get(slot) or slots.get(str(slot)) or {}

        reasons: list[str] = []
        warnings: list[str] = []

        if slot is None or not data.get("scheduler_ready"):
            return {
                "safety_safe": False,
                "safety_status": "geen_actie",
                "safety_reason": "Geen startklaar plan geselecteerd",
                "safety_reasons": ["no_selected_plan"],
                "safety_warnings": [],
                "safety_selected_slot": None,
                "safety_physical_control": False,
            }

        action = detail.get("action")
        power = self._number(detail.get("power_w"))
        target_soc = self._number(detail.get("target_soc"))
        soc = self._number(data.get("soc"))
        charge_power = self._number(data.get("charge_power_w"))
        discharge_power = self._number(data.get("discharge_power_w"))

        observation_values = (
            data.get("soc"),
            data.get("device_status"),
            data.get("charge_power_w"),
            data.get("discharge_power_w"),
            data.get("operating_mode"),
        )
        if any(value is None for value in observation_values):
            reasons.append("observation_sources_missing")

        if data.get("operating_mode") != "third_party_control":
            reasons.append("not_in_external_mode")
        else:
            control_values = (
                data.get("action_direction"),
                data.get("power_setpoint_w"),
            )
            if any(value is None for value in control_values):
                reasons.append("control_sources_missing")

        if action not in {"laden", "ontladen"}:
            reasons.append("invalid_action")

        max_power = int(data.get("max_discharge_power_w") or 800) if action == "ontladen" else int(data.get("max_charge_power_w") or 800)
        if power is None or not 100 <= power <= max_power:
            reasons.append("invalid_power")

        if soc is None or not 0 <= soc <= MAX_SOC_PERCENT:
            reasons.append("invalid_soc")

        if target_soc is None or not MIN_SOC_PERCENT <= target_soc <= MAX_SOC_PERCENT:
            reasons.append("invalid_target_soc")

        if soc is not None and target_soc is not None:
            if action == "laden" and soc >= target_soc:
                reasons.append("charge_target_already_reached")
            if action == "ontladen" and soc <= target_soc:
                reasons.append("discharge_target_already_reached")
            if action == "ontladen" and soc <= MIN_SOC_PERCENT:
                reasons.append("minimum_soc_reached")

        if (
            charge_power is not None
            and discharge_power is not None
            and charge_power > 100
            and discharge_power > 100
        ):
            reasons.append("conflicting_battery_power")

        if data.get("forecast_ready") is not True:
            warnings.append("forecast_not_ready")

        safe = len(reasons) == 0
        if safe and data.get("simulation_mode"):
            status = "veilig_simulatie"
            reason_text = "Veiligheidscontrole akkoord; fysieke uitvoering geblokkeerd door simulatiemodus"
        elif safe:
            status = "veilig_observe"
            reason_text = "Veiligheidscontrole akkoord; normale EMS-controller voert nog geen fysieke commando's uit"
        else:
            status = "geblokkeerd"
            reason_text = ", ".join(reasons)

        return {
            "safety_safe": safe,
            "safety_status": status,
            "safety_reason": reason_text,
            "safety_reasons": reasons,
            "safety_warnings": warnings,
            "safety_selected_slot": slot,
            "safety_physical_control": False,
        }

    def evaluate_automatic_handoff(self, data: dict[str, Any]) -> dict[str, Any]:
        """Evaluate Scheduler -> Safety Guard handoff for automatic plans.

        Alpha35 is deliberately non-actuating. This gate is evaluated only for
        an automatic Scheduler-ready plan after the authoritative pre-start
        validator has approved it. It validates the plan and the availability
        of the future control path, but it does not require the battery to be in
        third_party_control yet and never calls Home Assistant services.
        """
        slot = data.get("scheduler_selected_slot")
        slots = data.get("scheduler_slots", {}) or {}
        detail = slots.get(slot) or slots.get(str(slot)) or {}
        origin = str(detail.get("origin") or "manual")

        base = {
            "auto_safety_handoff_enabled": True,
            "auto_safety_handoff_required": False,
            "auto_safety_handoff_safe": False,
            "auto_safety_handoff_status": "not_required",
            "auto_safety_handoff_reason": "Geen automatische startklare planneractie geselecteerd",
            "auto_safety_handoff_reasons": [],
            "auto_safety_handoff_warnings": [],
            "auto_safety_handoff_selected_slot": None,
            "auto_safety_handoff_planner_identity": None,
            "auto_safety_handoff_prestart_safe": bool(data.get("auto_prestart_safe")),
            "auto_safety_handoff_control_path_configured": bool(data.get("control_path_configured")),
            "auto_safety_handoff_execution_permitted": False,
            "auto_safety_handoff_physical_control": False,
            "auto_safety_handoff_max_charge_power_w": int(data.get("max_charge_power_w") or 800),
            "auto_safety_handoff_max_discharge_power_w": int(data.get("max_discharge_power_w") or 800),
        }

        if slot is None or not data.get("scheduler_ready") or origin != "automatic_72h_planner":
            return base

        reasons: list[str] = []
        warnings: list[str] = []
        action = detail.get("action")
        power = self._number(detail.get("power_w"))
        target_soc = self._number(detail.get("target_soc"))
        soc = self._number(data.get("soc"))
        charge_power = self._number(data.get("charge_power_w"))
        discharge_power = self._number(data.get("discharge_power_w"))
        planner_identity = detail.get("planner_identity")

        if data.get("auto_prestart_required") is not True:
            reasons.append("prestart_not_required_for_selected_plan")
        if data.get("auto_prestart_safe") is not True:
            reasons.append("prestart_not_safe")
        if data.get("auto_prestart_current_identity_match") is not True:
            reasons.append("planner_identity_mismatch")
        if data.get("auto_bridge_valid") is not True:
            reasons.append("bridge_invalid")
        if data.get("forecast_ready") is not True:
            reasons.append("forecast_not_ready")
        purpose = str(detail.get("purpose") or "")
        safety_recovery_action = bool(
            action == "laden"
            and purpose in {"veiligheidsladen", "veiligheidsladen+handelsladen"}
        )
        if (
            data.get("auto_plan_72h_execution_buffer_safe") is not True
            and not safety_recovery_action
        ):
            reasons.append("execution_buffer_unsafe")
        if not data.get("control_path_configured"):
            reasons.append("control_path_not_configured")
        if data.get("physical_test_active"):
            reasons.append("physical_test_active")
        if data.get("execution_active"):
            reasons.append("execution_already_active")

        if action not in {"laden", "ontladen"}:
            reasons.append("invalid_action")
        max_power = int(data.get("max_discharge_power_w") or 800) if action == "ontladen" else int(data.get("max_charge_power_w") or 800)
        if power is None or not 100 <= power <= max_power:
            reasons.append("invalid_power")
        if soc is None or not MIN_SOC_PERCENT <= soc <= MAX_SOC_PERCENT:
            reasons.append("invalid_soc")
        if target_soc is None or not MIN_SOC_PERCENT <= target_soc <= MAX_SOC_PERCENT:
            reasons.append("invalid_target_soc")

        if soc is not None and target_soc is not None:
            if action == "laden" and soc >= target_soc:
                reasons.append("charge_target_already_reached")
            elif action == "ontladen" and soc <= target_soc:
                reasons.append("discharge_target_already_reached")

        if (
            charge_power is not None
            and discharge_power is not None
            and charge_power > 100
            and discharge_power > 100
        ):
            reasons.append("conflicting_battery_power")

        if data.get("auto_prestart_current_signature_match") is not True:
            warnings.append("planner_revision_changed")

        safe = not reasons
        status = "safe_observe" if safe else "blocked"
        reason = (
            "Scheduler-ready automatisch plan is door Safety Guard goedgekeurd; fysieke uitvoering vereist nog de centrale arm- en finale revalidatiegates"
            if safe
            else ", ".join(reasons)
        )

        return {
            **base,
            "auto_safety_handoff_required": True,
            "auto_safety_handoff_safe": safe,
            "auto_safety_handoff_status": status,
            "auto_safety_handoff_reason": reason,
            "auto_safety_handoff_reasons": reasons,
            "auto_safety_handoff_warnings": warnings,
            "auto_safety_handoff_selected_slot": slot,
            "auto_safety_handoff_planner_identity": planner_identity,
            "auto_safety_handoff_prestart_safe": bool(data.get("auto_prestart_safe")),
            "auto_safety_handoff_control_path_configured": bool(data.get("control_path_configured")),
            "auto_safety_handoff_execution_permitted": False,
            "auto_safety_handoff_physical_control": False,
            "auto_safety_handoff_max_charge_power_w": int(data.get("max_charge_power_w") or 800),
            "auto_safety_handoff_max_discharge_power_w": int(data.get("max_discharge_power_w") or 800),
        }
