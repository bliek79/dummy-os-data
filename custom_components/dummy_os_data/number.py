"""Number controls for Dummy OS Energy."""
from __future__ import annotations

from .ems_alpha76_surface import build_alpha76_plan_number_entities


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Expose the current DO identities backed by the exact alpha76 Plan Store."""
    coordinator = entry.runtime_data
    async_add_entities(build_alpha76_plan_number_entities(coordinator))
