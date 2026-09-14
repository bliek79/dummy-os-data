from __future__ import annotations

from datetime import datetime, timedelta
import time
import hashlib
import json
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_STORAGE_VERSION = 1
_STORAGE_KEY = "anker_ems_source_monitor"
_RETENTION_DAYS = 7
_MAX_EVENTS = 2000


class AnkerEmsSourceMonitor:
    """Observe source report/update moments without triggering planner logic yet."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store(
            hass,
            _STORAGE_VERSION,
            f"{_STORAGE_KEY}_{entry_id}",
        )
        self._last_save_monotonic = 0.0
        self._data: dict[str, Any] = {
            "sources": {},
            "events": [],
        }

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._data.update(stored)
        self._prune()

    def _prune(self) -> None:
        cutoff = dt_util.utcnow() - timedelta(days=_RETENTION_DAYS)
        kept: list[dict[str, Any]] = []
        for event in self._data.get("events", []):
            if not isinstance(event, dict):
                continue
            parsed = dt_util.parse_datetime(str(event.get("time", "")))
            if parsed is None:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt_util.UTC)
            if parsed.astimezone(dt_util.UTC) >= cutoff:
                kept.append(event)
        self._data["events"] = kept[-_MAX_EVENTS:]

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(dt_util.UTC).isoformat()

    @staticmethod
    def _canonical_digest(content: Any) -> str:
        raw = json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _state_payload(state: State | None, preferred_attributes: tuple[str, ...]) -> Any:
        if state is None:
            return None
        payload: dict[str, Any] = {"state": state.state}
        for attr in preferred_attributes:
            if attr in state.attributes:
                payload[attr] = state.attributes.get(attr)
        if len(payload) == 1:
            payload["attributes"] = dict(state.attributes)
        return payload

    def _append_event(
        self,
        source: str,
        kind: str,
        entity_ids: list[str],
        reported_at: str | None,
    ) -> None:
        self._data.setdefault("events", []).append(
            {
                "time": dt_util.utcnow().isoformat(),
                "source": source,
                "kind": kind,
                "entities": entity_ids,
                "reported_at": reported_at,
            }
        )
        self._data["events"] = self._data["events"][-_MAX_EVENTS:]

    async def async_observe(self, specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        changed = False
        sources = self._data.setdefault("sources", {})

        for source_name, spec in specs.items():
            entity_ids = [str(eid) for eid in spec.get("entity_ids", []) if eid]
            states = [self.hass.states.get(entity_id) for entity_id in entity_ids]
            present_states = [state for state in states if state is not None]

            latest_reported = None
            if present_states:
                latest_reported = max(
                    (getattr(state, "last_reported", state.last_updated) for state in present_states),
                    default=None,
                )
            latest_reported_iso = self._iso(latest_reported)

            content = spec.get("content")
            digest = self._canonical_digest(content)
            previous = sources.get(source_name)

            if not isinstance(previous, dict):
                sources[source_name] = {
                    "entity_ids": entity_ids,
                    "available": bool(present_states),
                    "last_reported": latest_reported_iso,
                    "last_content_change": dt_util.utcnow().isoformat(),
                    "digest": digest,
                    "baseline_at": dt_util.utcnow().isoformat(),
                }
                self._append_event(source_name, "baseline", entity_ids, latest_reported_iso)
                changed = True
                continue

            previous["entity_ids"] = entity_ids
            previous["available"] = bool(present_states)

            if latest_reported_iso and latest_reported_iso != previous.get("last_reported"):
                previous["last_reported"] = latest_reported_iso
                self._append_event(source_name, "reported", entity_ids, latest_reported_iso)
                changed = True

            if digest != previous.get("digest"):
                previous["digest"] = digest
                previous["last_content_change"] = dt_util.utcnow().isoformat()
                self._append_event(source_name, "content_changed", entity_ids, latest_reported_iso)
                changed = True

        self._prune()
        if changed and (time.monotonic() - self._last_save_monotonic >= 60):
            await self._store.async_save(self._data)
            self._last_save_monotonic = time.monotonic()
        return self.summary()

    def summary(self) -> dict[str, Any]:
        today = dt_util.now().date()
        events = [e for e in self._data.get("events", []) if isinstance(e, dict)]
        sources_out: dict[str, Any] = {}

        for source_name, source in self._data.get("sources", {}).items():
            source_events_today: list[dict[str, Any]] = []
            for event in events:
                if event.get("source") != source_name:
                    continue
                parsed = dt_util.parse_datetime(str(event.get("time", "")))
                if parsed is None:
                    continue
                if dt_util.as_local(parsed).date() == today:
                    source_events_today.append(event)

            sources_out[source_name] = {
                "entity_ids": source.get("entity_ids", []),
                "available": source.get("available", False),
                "last_reported": source.get("last_reported"),
                "last_content_change": source.get("last_content_change"),
                "reports_today": sum(1 for e in source_events_today if e.get("kind") == "reported"),
                "content_changes_today": sum(
                    1 for e in source_events_today if e.get("kind") == "content_changed"
                ),
            }

        recent = events[-60:]
        candidate_sources = {
            "solcast_forecast",
            "stroomvoorspeller",
            "energyzero_prices",
            "price_forecast",
        }
        recalc_candidates_today = 0
        for event in events:
            if event.get("kind") != "content_changed" or event.get("source") not in candidate_sources:
                continue
            parsed = dt_util.parse_datetime(str(event.get("time", "")))
            if parsed is not None and dt_util.as_local(parsed).date() == today:
                recalc_candidates_today += 1

        last_change_events = [e for e in events if e.get("kind") == "content_changed"]
        return {
            "source_monitor_status": "recording",
            "source_monitor_sources": sources_out,
            "source_monitor_recent_events": recent,
            "source_monitor_recalc_candidates_today": recalc_candidates_today,
            "source_monitor_last_content_change": (
                last_change_events[-1].get("time") if last_change_events else None
            ),
            "source_monitor_retention_days": _RETENTION_DAYS,
        }
