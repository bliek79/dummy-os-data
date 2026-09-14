from __future__ import annotations

from typing import Any


class AnkerEmsActionController:
    """Prepare a semantic battery command without executing it.

    Alpha 10 keeps the controller/safety decision chain in simulation. It intentionally does
    not call Home Assistant services. Device-specific command mapping and
    physical writes are reserved for a later alpha after explicit validation.
    """

    def evaluate(self, data: dict[str, Any]) -> dict[str, Any]:
        slot = data.get("scheduler_selected_slot")
        slots = data.get("scheduler_slots", {}) or {}
        detail = slots.get(slot) or slots.get(str(slot)) or {}
        safe = bool(data.get("safety_safe"))

        if slot is None or not data.get("scheduler_ready"):
            return {
                "controller_status": "idle",
                "controller_ready": False,
                "controller_selected_slot": None,
                "controller_action": None,
                "controller_power_w": None,
                "controller_target_soc": None,
                "controller_max_runtime_h": None,
                "controller_execution_mode": None,
                "controller_reason": "Geen startklaar plan",
                "controller_physical_control": False,
            }

        if not safe:
            return {
                "controller_status": "geblokkeerd",
                "controller_ready": False,
                "controller_selected_slot": slot,
                "controller_action": detail.get("action"),
                "controller_power_w": detail.get("power_w"),
                "controller_target_soc": detail.get("target_soc"),
                "controller_max_runtime_h": detail.get("max_runtime_h"),
                "controller_execution_mode": detail.get("execution_mode"),
                "controller_reason": data.get("safety_reason"),
                "controller_physical_control": False,
            }

        simulation = bool(data.get("simulation_mode"))
        return {
            "controller_status": "voorbereid_simulatie" if simulation else "voorbereid_observe",
            "controller_ready": True,
            "controller_selected_slot": slot,
            "controller_action": detail.get("action"),
            "controller_power_w": detail.get("power_w"),
            "controller_target_soc": detail.get("target_soc"),
            "controller_max_runtime_h": detail.get("max_runtime_h"),
            "controller_execution_mode": detail.get("execution_mode"),
            "controller_reason": (
                "Commando veilig voorbereid; simulatiemodus voorkomt fysieke uitvoering"
                if simulation
                else "Commando veilig voorbereid; automatische fysieke uitvoering blijft afhankelijk van de centrale arm- en safety-gates"
            ),
            "controller_desired_mode": "third_party_control",
            "controller_desired_direction": detail.get("action"),
            "controller_desired_power_w": detail.get("power_w"),
            "controller_physical_control": False,
        }
