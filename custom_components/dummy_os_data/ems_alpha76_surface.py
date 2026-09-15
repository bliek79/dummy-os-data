"""Home Assistant entity surface for the copied alpha76 EMS runtime.

This module contains no EMS policy. It only binds the current Dummy OS Energy
platforms to the exact vendored alpha76 Plan Store and read-only runtime state.
Physical execution remains disabled by ``ems_alpha76_runtime``.
"""
from __future__ import annotations

from typing import Any

from .ems_alpha76.binary_sensor import (
    AnkerEmsAutomaticExecutionReady,
    AnkerEmsAutoBridgeValid,
    AnkerEmsAutoPlan72hExecutionBufferSafe,
    AnkerEmsAutoPlan72hValid,
    AnkerEmsControllerReady,
    AnkerEmsControlAvailable,
    AnkerEmsExecutionActive,
    AnkerEmsForecastSourcesAvailable,
    AnkerEmsPhysicalTestActive,
    AnkerEmsPlannerDischargePossible,
    AnkerEmsPlannerSafetyChargeNeeded,
    AnkerEmsPlannerSolarChargeDelay,
    AnkerEmsPlannerTradeChargeCandidate,
    AnkerEmsPlannerTradeProfitable,
    AnkerEmsSafetySafe,
    AnkerEmsSchedulerReady,
    AnkerEmsSourcesAvailable,
)
from .ems_alpha76.const import PLAN_SLOT_COUNT
from .ems_alpha76.datetime import AnkerEmsPlanStartTime
from .ems_alpha76.number import AnkerEmsPlanNumber, DEFINITIONS as PLAN_NUMBER_DEFINITIONS
from .ems_alpha76.select import AnkerEmsPlanSelect
from .ems_alpha76_runtime import DummyOSEmsAlpha76Runtime, get_ems_alpha76_runtime


def _require_runtime(coordinator: Any) -> DummyOSEmsAlpha76Runtime:
    """Return the initialized alpha76 runtime or fail platform setup explicitly."""
    runtime = get_ems_alpha76_runtime(coordinator)
    if runtime is None:
        raise RuntimeError("Dummy OS EMS alpha76 shadow runtime is not initialized")
    return runtime


def build_alpha76_plan_number_entities(coordinator: Any, entry: Any) -> list[Any]:
    """Build the exact alpha76 numeric controls against the alpha76 Plan Store."""
    runtime = _require_runtime(coordinator)
    return [
        AnkerEmsPlanNumber(runtime, entry, slot, definition)
        for slot in range(1, PLAN_SLOT_COUNT + 1)
        for definition in PLAN_NUMBER_DEFINITIONS
    ]


def build_alpha76_plan_datetime_entities(coordinator: Any, entry: Any) -> list[Any]:
    """Build the exact alpha76 start-time controls."""
    runtime = _require_runtime(coordinator)
    return [
        AnkerEmsPlanStartTime(runtime, entry, slot)
        for slot in range(1, PLAN_SLOT_COUNT + 1)
    ]


def build_alpha76_plan_select_entities(coordinator: Any, entry: Any) -> list[Any]:
    """Build the exact alpha76 action and execution-mode controls."""
    runtime = _require_runtime(coordinator)
    entities: list[Any] = []
    for slot in range(1, PLAN_SLOT_COUNT + 1):
        entities.extend(
            [
                AnkerEmsPlanSelect(
                    runtime,
                    entry,
                    slot,
                    "action",
                    "Action",
                    ["geen", "laden", "ontladen"],
                ),
                AnkerEmsPlanSelect(
                    runtime,
                    entry,
                    slot,
                    "execution_mode",
                    "Mode",
                    ["direct", "gepland"],
                ),
            ]
        )
    return entities


def build_alpha76_binary_sensors(coordinator: Any, entry: Any) -> list[Any]:
    """Expose the exact alpha76 scheduler/safety/controller state read-only."""
    runtime = _require_runtime(coordinator)
    return [
        AnkerEmsSourcesAvailable(runtime, entry),
        AnkerEmsControlAvailable(runtime, entry),
        AnkerEmsForecastSourcesAvailable(runtime, entry),
        AnkerEmsSchedulerReady(runtime, entry),
        AnkerEmsSafetySafe(runtime, entry),
        AnkerEmsControllerReady(runtime, entry),
        AnkerEmsPhysicalTestActive(runtime, entry),
        AnkerEmsExecutionActive(runtime, entry),
        AnkerEmsPlannerSafetyChargeNeeded(runtime, entry),
        AnkerEmsPlannerTradeChargeCandidate(runtime, entry),
        AnkerEmsPlannerDischargePossible(runtime, entry),
        AnkerEmsPlannerSolarChargeDelay(runtime, entry),
        AnkerEmsPlannerTradeProfitable(runtime, entry),
        AnkerEmsAutoPlan72hValid(runtime, entry),
        AnkerEmsAutoPlan72hExecutionBufferSafe(runtime, entry),
        AnkerEmsAutoBridgeValid(runtime, entry),
        AnkerEmsAutomaticExecutionReady(runtime, entry),
    ]
