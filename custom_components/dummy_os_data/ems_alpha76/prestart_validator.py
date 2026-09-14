from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import MAX_SOC_PERCENT, MIN_SOC_PERCENT


class AnkerEmsPreStartValidator:
    """Validate and diagnose automatic plans immediately before execution.

    Physical automatic execution remains disabled. This validator separates the
    continuous early diagnostic from the authoritative Scheduler-ready pre-start
    gate. Live-SOC direction and execution-reserve checks are informative while
    a plan is still far away and become hard blockers only close to start.
    """

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
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

    def _find_current_candidate(
        self, data: dict[str, Any], planner_identity: str | None
    ) -> dict[str, Any] | None:
        if not planner_identity:
            return None
        for candidate in data.get("auto_bridge_candidates") or []:
            if candidate.get("planner_identity") == planner_identity:
                return candidate
        for proposal in data.get("auto_bridge_slot_preview") or []:
            if proposal.get("planner_identity") == planner_identity:
                return proposal
        return None

    def _checks(
        self,
        data: dict[str, Any],
        detail: dict[str, Any],
        *,
        require_identity: bool = True,
        enforce_live_soc: bool = True,
    ) -> dict[str, Any]:
        reasons: list[str] = []
        warnings: list[str] = []
        checks: list[dict[str, Any]] = []

        def add_check(name: str, passed: bool, detail_text: str, blocker: str | None = None) -> None:
            checks.append(
                {
                    "check": name,
                    "passed": bool(passed),
                    "severity": "ok" if passed else "blocker",
                    "detail": detail_text,
                }
            )
            if not passed and blocker:
                reasons.append(blocker)

        planner_valid = data.get("auto_plan_72h_valid") is True
        add_check("planner_valid", planner_valid, "72-hour planner valid", "planner_invalid")

        forecast_ready = data.get("forecast_ready") is True
        add_check("forecast_ready", forecast_ready, "Forecast sources ready", "forecast_not_ready")

        purpose = str(detail.get("purpose") or "")
        action = str(detail.get("action") or "")
        safety_recovery_action = bool(
            action == "laden"
            and purpose in {"veiligheidsladen", "veiligheidsladen+handelsladen"}
        )
        buffer_safe = data.get("auto_plan_72h_execution_buffer_safe") is True
        buffer_allows_action = buffer_safe or safety_recovery_action
        add_check(
            "execution_buffer_safe",
            buffer_allows_action,
            (
                "Execution buffer safe"
                if buffer_safe
                else "Execution buffer unsafe; safety charge is allowed to restore it"
            ),
            "execution_buffer_unsafe",
        )

        invalid_candidates = int(data.get("auto_bridge_invalid_candidate_count") or 0)
        add_check(
            "bridge_candidates_valid",
            invalid_candidates == 0,
            f"Invalid bridge candidates: {invalid_candidates}",
            "invalid_bridge_candidates",
        )

        bridge_valid = data.get("auto_bridge_valid") is True
        add_check("bridge_valid", bridge_valid, "Action Bridge valid", "bridge_invalid")

        planner_identity = detail.get("planner_identity")
        current = self._find_current_candidate(data, planner_identity)
        identity_match = current is not None
        if require_identity:
            add_check(
                "planner_identity_match",
                identity_match,
                "Stored plan identity exists in current planner preview",
                "planner_identity_missing",
            )

        stored_signature = detail.get("planner_signature")
        current_signature = current.get("planner_signature") if current else None
        signature_match = bool(
            stored_signature and current_signature and stored_signature == current_signature
        )
        checks.append(
            {
                "check": "planner_signature_match",
                "passed": signature_match,
                "severity": "ok" if signature_match else "warning",
                "detail": "Current planner revision matches stored plan" if signature_match else "Planner revision changed; stable identity remains authoritative",
            }
        )
        if identity_match and not signature_match:
            warnings.append("planner_revision_changed_after_due")

        action = detail.get("action")
        power = self._number(detail.get("power_w"))
        target_soc = self._number(detail.get("target_soc"))
        soc = self._number(data.get("soc"))

        valid_action = action in {"laden", "ontladen"}
        add_check("action_valid", valid_action, f"Action: {action}", "invalid_action")

        max_power = int(data.get("max_discharge_power_w") or 800) if action == "ontladen" else int(data.get("max_charge_power_w") or 800)
        power_valid = power is not None and 100 <= power <= max_power
        add_check("power_valid", power_valid, f"Power: {power} W; allowed 100-{max_power} W", "invalid_power")

        soc_valid = soc is not None and MIN_SOC_PERCENT <= soc <= MAX_SOC_PERCENT
        add_check("soc_valid", soc_valid, f"Current SOC: {soc}%", "invalid_soc")

        target_valid = target_soc is not None and MIN_SOC_PERCENT <= target_soc <= MAX_SOC_PERCENT
        add_check("target_soc_valid", target_valid, f"Target SOC: {target_soc}%", "invalid_target_soc")

        target_direction_ok = True
        target_blocker = None
        if soc is not None and target_soc is not None:
            if action == "laden" and soc >= target_soc:
                target_direction_ok = False
                target_blocker = "charge_target_already_reached"
            elif action == "ontladen" and soc <= target_soc:
                target_direction_ok = False
                target_blocker = "discharge_target_already_reached"
        if target_direction_ok:
            checks.append({
                "check": "target_direction_valid",
                "passed": True,
                "severity": "ok",
                "detail": "Current SOC still requires the planned action",
            })
        elif enforce_live_soc:
            checks.append({
                "check": "target_direction_valid",
                "passed": False,
                "severity": "blocker",
                "detail": "Target SOC already reached/passed",
            })
            if target_blocker:
                reasons.append(target_blocker)
        else:
            checks.append({
                "check": "target_direction_valid",
                "passed": False,
                "severity": "warning",
                "detail": "Current SOC would block this action now, but the plan is still outside the live pre-start decision window",
            })
            if target_blocker:
                warnings.append(target_blocker)

        reserve_soc = self._number(current.get("execution_reserve_start_soc")) if current else None
        reserve_ok = True
        reserve_blocker = None
        if action == "ontladen":
            reserve_ok = soc is not None and reserve_soc is not None and soc > reserve_soc
            if not reserve_ok:
                reserve_blocker = "execution_reserve_reached"
        checks.append(
            {
                "check": "execution_reserve_available",
                "passed": reserve_ok,
                "severity": "ok" if reserve_ok else ("blocker" if enforce_live_soc else "warning"),
                "detail": (
                    f"Execution reserve: {reserve_soc}%"
                    if reserve_ok or enforce_live_soc
                    else f"Execution reserve: {reserve_soc}%; current SOC is informational until the live pre-start window"
                ) if action == "ontladen" else "Not applicable to charge action",
            }
        )
        if not reserve_ok and reserve_blocker:
            (reasons if enforce_live_soc else warnings).append(reserve_blocker)

        return {
            "safe": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "checks": checks,
            "current": current,
            "identity_match": identity_match,
            "signature_match": signature_match,
            "soc": soc,
            "target_soc": target_soc,
            "reserve_soc": reserve_soc,
            "power_w": power,
            "action": action,
        }

    def _nearest_automatic_pending(self, data: dict[str, Any]) -> tuple[int | None, dict[str, Any]]:
        slots = data.get("scheduler_slots", {}) or {}
        now = dt_util.utcnow()
        choices: list[tuple[datetime, int, dict[str, Any]]] = []
        for raw_slot, raw_detail in slots.items():
            detail = raw_detail or {}
            if str(detail.get("origin") or "manual") != "automatic_72h_planner":
                continue
            if str(detail.get("lifecycle_status") or "").lower() != "pending":
                continue
            if not detail.get("planner_identity"):
                continue
            start = self._parse_datetime(detail.get("start_time"))
            if start is None:
                continue
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError):
                continue
            # Due plans are also useful for diagnostics; sort them first.
            sort_start = start if start >= now else now
            choices.append((sort_start, slot, detail))
        if not choices:
            return None, {}
        choices.sort(key=lambda item: (item[0], item[1]))
        _, slot, detail = choices[0]
        return slot, detail

    def _diagnose(self, data: dict[str, Any]) -> dict[str, Any]:
        slot, detail = self._nearest_automatic_pending(data)
        base: dict[str, Any] = {
            "auto_prestart_diagnostic_enabled": True,
            "auto_prestart_diagnostic_status": "no_plan",
            "auto_prestart_diagnostic_safe": False,
            "auto_prestart_diagnostic_slot": None,
            "auto_prestart_diagnostic_planner_identity": None,
            "auto_prestart_diagnostic_start_time": None,
            "auto_prestart_diagnostic_minutes_to_start": None,
            "auto_prestart_diagnostic_phase": "no_plan",
            "auto_prestart_diagnostic_authoritative": False,
            "auto_prestart_diagnostic_live_soc_enforced": False,
            "auto_prestart_diagnostic_decision_window_min": None,
            "auto_prestart_diagnostic_action": None,
            "auto_prestart_diagnostic_power_w": None,
            "auto_prestart_diagnostic_current_soc": self._number(data.get("soc")),
            "auto_prestart_diagnostic_target_soc": None,
            "auto_prestart_diagnostic_execution_reserve_soc": None,
            "auto_prestart_diagnostic_identity_match": False,
            "auto_prestart_diagnostic_signature_match": False,
            "auto_prestart_diagnostic_blockers": [],
            "auto_prestart_diagnostic_warnings": [],
            "auto_prestart_diagnostic_checks": [],
            "auto_prestart_test_matrix": [],
        }
        if slot is None:
            return base

        start = self._parse_datetime(detail.get("start_time"))
        minutes = None
        if start is not None:
            minutes = round((start - dt_util.utcnow()).total_seconds() / 60.0, 1)

        # Early diagnostics are intentionally non-authoritative. Current SOC can
        # change substantially before the plan starts, so SOC direction/reserve
        # become hard blockers only inside a small live decision window.
        start_delay = self._number(detail.get("max_start_delay_min")) or 10.0
        decision_window_min = max(15.0, start_delay)
        live_soc_enforced = minutes is not None and minutes <= decision_window_min
        phase = (
            "due" if minutes is not None and minutes <= 0
            else "near_start" if live_soc_enforced
            else "early"
        )
        result = self._checks(data, detail, enforce_live_soc=live_soc_enforced)

        # Dry-run matrix proves that the gate can distinguish common hard blockers.
        # It uses the same time relevance as the live diagnostic. 
        # These are pure in-memory evaluations and never alter Home Assistant state.
        matrix: list[dict[str, Any]] = []
        for name, overrides in (
            ("current_conditions", {}),
            ("forecast_not_ready", {"forecast_ready": False}),
            ("execution_buffer_unsafe", {"auto_plan_72h_execution_buffer_safe": False}),
            ("planner_invalid", {"auto_plan_72h_valid": False}),
        ):
            test_data = dict(data)
            test_data.update(overrides)
            test_result = self._checks(test_data, detail, enforce_live_soc=live_soc_enforced)
            matrix.append(
                {
                    "case": name,
                    "safe": test_result["safe"],
                    "blockers": test_result["reasons"],
                }
            )

        base.update(
            {
                "auto_prestart_diagnostic_status": (
                    f"{phase}_pass" if result["safe"] else f"{phase}_blocked"
                ),
                "auto_prestart_diagnostic_safe": result["safe"],
                "auto_prestart_diagnostic_slot": slot,
                "auto_prestart_diagnostic_planner_identity": detail.get("planner_identity"),
                "auto_prestart_diagnostic_start_time": start.isoformat() if start else None,
                "auto_prestart_diagnostic_minutes_to_start": minutes,
                "auto_prestart_diagnostic_phase": phase,
                "auto_prestart_diagnostic_authoritative": False,
                "auto_prestart_diagnostic_live_soc_enforced": live_soc_enforced,
                "auto_prestart_diagnostic_decision_window_min": decision_window_min,
                "auto_prestart_diagnostic_action": result["action"],
                "auto_prestart_diagnostic_power_w": result["power_w"],
                "auto_prestart_diagnostic_current_soc": result["soc"],
                "auto_prestart_diagnostic_target_soc": result["target_soc"],
                "auto_prestart_diagnostic_execution_reserve_soc": result["reserve_soc"],
                "auto_prestart_diagnostic_identity_match": result["identity_match"],
                "auto_prestart_diagnostic_signature_match": result["signature_match"],
                "auto_prestart_diagnostic_blockers": result["reasons"],
                "auto_prestart_diagnostic_warnings": result["warnings"],
                "auto_prestart_diagnostic_checks": result["checks"],
                "auto_prestart_test_matrix": matrix,
            }
        )
        return base

    def evaluate(self, data: dict[str, Any]) -> dict[str, Any]:
        slot = data.get("scheduler_selected_slot")
        slots = data.get("scheduler_slots", {}) or {}
        detail = slots.get(slot) or slots.get(str(slot)) or {}

        result: dict[str, Any] = {
            "auto_prestart_enabled": True,
            "auto_prestart_required": False,
            "auto_prestart_safe": False,
            "auto_prestart_status": "not_required",
            "auto_prestart_reason": "Geen automatische startklare planneractie geselecteerd",
            "auto_prestart_reasons": [],
            "auto_prestart_warnings": [],
            "auto_prestart_selected_slot": None,
            "auto_prestart_planner_identity": None,
            "auto_prestart_current_identity_match": False,
            "auto_prestart_current_signature_match": False,
            "auto_prestart_current_soc": self._number(data.get("soc")),
            "auto_prestart_target_soc": None,
            "auto_prestart_execution_reserve_soc": None,
            "auto_prestart_execution_enabled": False,
            "auto_prestart_physical_control": False,
        }
        result.update(self._diagnose(data))

        if slot is None or not data.get("scheduler_ready"):
            return result

        origin = str(detail.get("origin") or "manual")
        planner_identity = detail.get("planner_identity")
        if origin != "automatic_72h_planner" or not planner_identity:
            result.update(
                {
                    "auto_prestart_status": "manual_plan",
                    "auto_prestart_reason": "Geselecteerd plan is handmatig; automatische pre-start validatie is niet van toepassing",
                    "auto_prestart_selected_slot": slot,
                }
            )
            return result

        result["auto_prestart_required"] = True
        result["auto_prestart_selected_slot"] = slot
        result["auto_prestart_planner_identity"] = planner_identity

        checked = self._checks(data, detail)
        result.update(
            {
                "auto_prestart_safe": checked["safe"],
                "auto_prestart_status": "safe_observe" if checked["safe"] else "blocked",
                "auto_prestart_reason": (
                    "Pre-start veiligheidscontrole akkoord; fysieke uitvoering vereist nog de Automatic Execution-arm en volgende safety-gates"
                    if checked["safe"]
                    else ", ".join(checked["reasons"])
                ),
                "auto_prestart_reasons": checked["reasons"],
                "auto_prestart_warnings": checked["warnings"],
                "auto_prestart_current_identity_match": checked["identity_match"],
                "auto_prestart_current_signature_match": checked["signature_match"],
                "auto_prestart_current_soc": checked["soc"],
                "auto_prestart_target_soc": checked["target_soc"],
                "auto_prestart_execution_reserve_soc": checked["reserve_soc"],
            }
        )
        return result
