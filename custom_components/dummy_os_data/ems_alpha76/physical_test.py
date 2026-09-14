from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    TEST_DEFAULT_DURATION_S,
    TEST_DEFAULT_POWER_W,
    TEST_MAX_DURATION_S,
    TEST_MAX_POWER_W,
    TEST_MIN_DURATION_S,
    TEST_MIN_POWER_W,
)

_LOGGER = logging.getLogger(__name__)
_STORAGE_VERSION = 1


class AnkerEmsPhysicalTestController:
    """Run tightly bounded physical charge/discharge validation tests.

    This controller is intentionally separate from the normal Action Controller.
    Tests can only be started through explicit service actions and always attempt
    to return the battery to self_consumption when they stop.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store: Store[dict[str, Any]] = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}.{entry_id}.physical_test"
        )
        self._coordinator = None
        self._stop_task: asyncio.Task[None] | None = None
        self._cancel_monitor: Callable[[], None] | None = None
        self._stop_lock = asyncio.Lock()
        self._state: dict[str, Any] = {
            "active": False,
            "status": "idle",
            "reason": "Geen fysieke test actief",
            "action": None,
            "power_w": None,
            "duration_s": None,
            "started_at": None,
            "stop_at": None,
            "last_result": None,
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

    async def async_recover_if_needed(self) -> None:
        """Fail safe after a Home Assistant restart during an active test."""
        if not self._state.get("active"):
            return
        _LOGGER.warning("Recovering interrupted Dummy OS EMS physical test")
        await self.async_stop("restart_recovery", emergency=True)

    async def _async_validate_common_test(self, power_w: int, duration_s: int) -> dict[str, Any]:
        if self._coordinator is None:
            raise HomeAssistantError("Dummy OS EMS coordinator is niet beschikbaar")
        if self._state.get("active"):
            raise HomeAssistantError("Er is al een fysieke test actief")
        if (
            getattr(self._coordinator, "execution", None) is not None
            and (
                self._coordinator.execution.data.get("active")
                or self._coordinator.execution.data.get("auto_mode_switch_active")
            )
        ):
            raise HomeAssistantError("Er is al een EMS-uitvoering of mode-switch validatie actief")
        if not TEST_MIN_POWER_W <= power_w <= TEST_MAX_POWER_W:
            raise HomeAssistantError(
                f"Testvermogen moet tussen {TEST_MIN_POWER_W} en {TEST_MAX_POWER_W} W liggen"
            )
        if not TEST_MIN_DURATION_S <= duration_s <= TEST_MAX_DURATION_S:
            raise HomeAssistantError(
                f"Testduur moet tussen {TEST_MIN_DURATION_S} en {TEST_MAX_DURATION_S} seconden liggen"
            )

        await self._coordinator.async_refresh()
        data = self._coordinator.data
        if not data.get("simulation_mode"):
            raise HomeAssistantError("Fysieke test is alleen toegestaan terwijl EMS op simulation staat")
        if not data.get("scheduler_ready"):
            raise HomeAssistantError("Scheduler heeft geen startklaar plan")
        if data.get("operating_mode") != "third_party_control":
            raise HomeAssistantError("Zet de batterij eerst op third_party_control")
        if data.get("action_direction") is None or data.get("power_setpoint_w") is None:
            raise HomeAssistantError("Besturingsbronnen zijn niet beschikbaar")
        return data

    async def async_start_discharge_test(
        self,
        *,
        power_w: int = TEST_DEFAULT_POWER_W,
        duration_s: int = TEST_DEFAULT_DURATION_S,
    ) -> None:
        """Run an explicit, bounded physical discharge validation test."""
        data = await self._async_validate_common_test(power_w, duration_s)

        if data.get("controller_action") != "ontladen":
            raise HomeAssistantError("Voor de ontlaadtest moet een ontlaadplan startklaar staan")
        if not data.get("safety_safe"):
            raise HomeAssistantError(
                f"Safety Guard blokkeert de test: {data.get('safety_reason') or 'onbekende reden'}"
            )
        if (data.get("charge_power_w") or 0) > 100:
            raise HomeAssistantError("Laadvermogen is actief; ontlaadtest wordt niet gestart")

        soc = data.get("soc")
        target_soc = data.get("controller_target_soc")
        if soc is None:
            raise HomeAssistantError("SOC is niet beschikbaar")
        try:
            soc_value = float(soc)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("SOC is ongeldig") from err
        if soc_value <= 5:
            raise HomeAssistantError("Ontlaadtest geblokkeerd: minimale SOC van 5% bereikt")
        if target_soc is not None and soc_value <= float(target_soc):
            raise HomeAssistantError("Ontlaaddoel is al bereikt")

        mode_entity, direction_entity, power_entity = self._entity_ids()
        now = dt_util.now()
        stop_at = now + timedelta(seconds=duration_s)
        self._state.update(
            {
                "active": True,
                "status": "starting",
                "reason": "Fysieke ontlaadtest wordt gestart",
                "action": "ontladen",
                "power_w": power_w,
                "duration_s": duration_s,
                "started_at": now.isoformat(),
                "stop_at": stop_at.isoformat(),
                "last_result": None,
            }
        )
        await self._async_save()

        try:
            await self.hass.services.async_call(
                "select",
                "select_option",
                {"option": "discharge"},
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
            _LOGGER.exception("Failed to start physical discharge test")
            await self.async_stop(f"start_failed: {err}", emergency=True)
            raise HomeAssistantError(f"Start fysieke ontlaadtest mislukt: {err}") from err

        self._state.update(
            {
                "status": "running",
                "reason": f"Ontlaadtest actief: {power_w} W gedurende maximaal {duration_s} s",
            }
        )
        await self._async_save()
        self._schedule_stop(stop_at)
        self._schedule_monitor()
        await self._coordinator.async_refresh()

    async def async_start_charge_test(
        self,
        *,
        power_w: int = TEST_DEFAULT_POWER_W,
        duration_s: int = TEST_DEFAULT_DURATION_S,
    ) -> None:
        data = await self._async_validate_common_test(power_w, duration_s)

        if data.get("controller_action") != "laden":
            raise HomeAssistantError("Voor de laadtest moet een laadplan startklaar staan")
        if not data.get("safety_safe"):
            raise HomeAssistantError(
                f"Safety Guard blokkeert de test: {data.get('safety_reason') or 'onbekende reden'}"
            )
        if (data.get("discharge_power_w") or 0) > 100:
            raise HomeAssistantError("Ontlaadvermogen is actief; test wordt niet gestart")

        mode_entity, direction_entity, power_entity = self._entity_ids()
        now = dt_util.now()
        stop_at = now + timedelta(seconds=duration_s)
        self._state.update(
            {
                "active": True,
                "status": "starting",
                "reason": "Fysieke laadtest wordt gestart",
                "action": "laden",
                "power_w": power_w,
                "duration_s": duration_s,
                "started_at": now.isoformat(),
                "stop_at": stop_at.isoformat(),
                "last_result": None,
            }
        )
        await self._async_save()

        try:
            # Direction first, power second. Operating mode is deliberately not
            # switched automatically in alpha 10; the user must arm it manually.
            await self.hass.services.async_call(
                "select",
                "select_option",
                {"option": "charge"},
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
            _LOGGER.exception("Failed to start physical charge test")
            await self.async_stop(f"start_failed: {err}", emergency=True)
            raise HomeAssistantError(f"Start fysieke test mislukt: {err}") from err

        self._state.update(
            {
                "status": "running",
                "reason": f"Laadtest actief: {power_w} W gedurende maximaal {duration_s} s",
            }
        )
        await self._async_save()
        self._schedule_stop(stop_at)
        self._schedule_monitor()
        await self._coordinator.async_refresh()

    def _schedule_stop(self, stop_at: datetime) -> None:
        """Schedule a dedicated fail-safe task for the absolute stop time.

        Alpha 10 used ``async_call_later`` for the primary stop callback. During
        the first physical test the countdown reached zero while that callback
        did not complete the safe-stop path. A dedicated task is easier to
        supervise and, importantly, cannot accidentally cancel its own callback
        while ``async_stop`` is running.
        """
        if self._stop_task is not None and not self._stop_task.done():
            self._stop_task.cancel()
        self._stop_task = self.hass.async_create_task(
            self._async_auto_stop_at(stop_at),
            "Dummy OS EMS physical test auto-stop",
        )

    async def _async_auto_stop_at(self, stop_at: datetime) -> None:
        try:
            delay = max(0.0, (stop_at - dt_util.now()).total_seconds())
            await asyncio.sleep(delay)
            if self._state.get("active"):
                _LOGGER.info("Dummy OS EMS physical test duration reached; executing safe stop")
                await self.async_stop("test_duration_reached", emergency=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Automatic safe stop for physical test failed")
            # Keep the test marked active so restart recovery/manual stop can
            # still see that intervention is required.
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
            5,
            self._async_monitor_callback,
        )

    @callback
    def _async_monitor_callback(self, _now: datetime) -> None:
        """Schedule the physical-test monitor from the Home Assistant event loop."""
        self.hass.async_create_task(
            self._async_monitor_once(),
            "Dummy OS EMS physical test monitor",
        )

    async def _async_monitor_once(self) -> None:
        if not self._state.get("active") or self._coordinator is None:
            return
        await self._coordinator.async_refresh()
        data = self._coordinator.data

        if data.get("operating_mode") != "third_party_control":
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

        if action == "laden" and (data.get("discharge_power_w") or 0) > 100:
            await self.async_stop("unexpected_discharge_detected", emergency=True)
            return
        if action == "ontladen" and (data.get("charge_power_w") or 0) > 100:
            await self.async_stop("unexpected_charge_detected", emergency=True)
            return

        target_soc = data.get("controller_target_soc")
        soc = data.get("soc")
        if soc is None:
            await self.async_stop("soc_unavailable", emergency=True)
            return
        try:
            soc_value = float(soc)
        except (TypeError, ValueError):
            await self.async_stop("invalid_soc", emergency=True)
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

        if self.remaining_seconds == 0:
            await self.async_stop("test_duration_reached", emergency=False)
            return

        self._schedule_monitor()

    async def async_stop(self, reason: str, *, emergency: bool = False) -> None:
        """Stop the test and return the battery to self consumption."""
        async with self._stop_lock:
            # A second stop request may arrive while the first one is completing
            # (for example watchdog + manual stop). Treat it as idempotent.
            if not self._state.get("active") and self._state.get("status") not in {
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
                {
                    "status": "stopping",
                    "reason": f"Safe-stop actief: {reason}",
                }
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

            # Give the device a brief moment to accept the zero setpoint before
            # handing control back to its own self-consumption logic.
            await asyncio.sleep(1)

            if mode_entity:
                try:
                    await self.hass.services.async_call(
                        "select",
                        "select_option",
                        {"option": "self_consumption"},
                        target={"entity_id": mode_entity},
                        blocking=True,
                    )
                except Exception as err:
                    errors.append(f"self_consumption_failed: {err}")

            result = "emergency_stopped" if emergency else "completed"
            if errors:
                result = "stop_error"
                reason = f"{reason}; {'; '.join(errors)}"

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
            if self._coordinator is not None:
                await self._coordinator.async_refresh()

            if self._stop_task is current_task:
                self._stop_task = None

    async def async_shutdown_stop(self) -> None:
        if self._state.get("active"):
            try:
                await self.async_stop("home_assistant_stop", emergency=True)
            except Exception:
                _LOGGER.exception("Could not stop physical test during Home Assistant shutdown")
