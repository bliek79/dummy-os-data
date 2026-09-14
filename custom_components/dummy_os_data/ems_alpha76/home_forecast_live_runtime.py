from __future__ import annotations

from typing import Any


def install_live_diagnostic_sensor_contract() -> None:
    """No-op compatibility hook for the removed alpha72 diagnostics.

    Alpha73 removes the legacy EMS-owned Home Forecast comparison/evaluation/
    transition sensor contract. Existing entity-registry entries will therefore
    no longer be registered by this integration after restart.
    """
    return None


class AnkerEmsHomeForecastLiveRuntime:
    """No-op compatibility shell for the removed legacy diagnostics runtime."""

    def __init__(self, coordinator: Any) -> None:
        self.coordinator = coordinator

    async def async_attach(self) -> None:
        return None
