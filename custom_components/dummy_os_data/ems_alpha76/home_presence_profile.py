from __future__ import annotations

from typing import Any

NORMAL_MODE = "normal"
ABSENCE_MODE = "absence"
UNKNOWN_MODE = "unknown"

_ABSENCE_VALUES = {
    "absence",
    "afwezig",
    "afwezigheid",
    "away",
    "vacation",
    "vakantie",
    "on",
    "true",
    "1",
}

_NORMAL_VALUES = {
    "normal",
    "normaal",
    "home",
    "thuis",
    "off",
    "false",
    "0",
}


def normalize_presence_mode(value: Any) -> str:
    """Normalize a future presence-mode source to the EMS profile contract."""
    if isinstance(value, bool):
        return ABSENCE_MODE if value else NORMAL_MODE
    text = str(value or "").strip().lower()
    if text in _ABSENCE_VALUES:
        return ABSENCE_MODE
    if text in _NORMAL_VALUES:
        return NORMAL_MODE
    return UNKNOWN_MODE


def profile_decision(*, source_value: Any, source_configured: bool) -> dict[str, Any]:
    """Return a fail-safe learning-profile decision.

    Until the real EMS absence-mode entity is explicitly contracted and wired,
    history stays in the normal profile and diagnostics state that the source
    is not configured. This avoids inventing an entity ID or contaminating
    future absence history with guessed state.
    """
    if not source_configured:
        return {
            "mode": NORMAL_MODE,
            "source_status": "not_configured",
            "source_value": None,
            "profile_separation_ready": False,
        }

    mode = normalize_presence_mode(source_value)
    if mode == UNKNOWN_MODE:
        return {
            "mode": NORMAL_MODE,
            "source_status": "unknown_fallback_normal",
            "source_value": source_value,
            "profile_separation_ready": False,
        }
    return {
        "mode": mode,
        "source_status": "ready",
        "source_value": source_value,
        "profile_separation_ready": True,
    }
