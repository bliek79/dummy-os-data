"""Baseline Home Forecast model for Dummy OS Data."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from homeassistant.util import dt as dt_util

from .const import FORECAST_SLOTS, PROFILE_OPTIONS, QUARTER_MINUTES


@dataclass(slots=True)
class ForecastSlot:
    """One 15-minute forecast slot."""

    start: datetime
    end: datetime
    energy_kwh: float | None
    sample_count: int
    source: str
    confidence: float


class HomeBaselineForecast:
    """Build historical profiles and a rolling 72-hour baseline forecast."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records

    @staticmethod
    def _quarter_index(local_dt: datetime) -> int:
        return local_dt.hour * 4 + local_dt.minute // QUARTER_MINUTES

    def _history(self, profile: str) -> tuple[dict[tuple[int, int], list[float]], dict[int, list[float]], list[float]]:
        exact: dict[tuple[int, int], list[float]] = defaultdict(list)
        quarter: dict[int, list[float]] = defaultdict(list)
        all_values: list[float] = []

        for record in self.records:
            if not record.get("valid") or record.get("profile") != profile:
                continue
            value = record.get("energy_kwh")
            if value is None:
                continue
            try:
                start = datetime.fromisoformat(record["start"])
                energy = float(value)
            except (KeyError, TypeError, ValueError):
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=dt_util.UTC)
            local = dt_util.as_local(start)
            qidx = self._quarter_index(local)
            exact[(local.weekday(), qidx)].append(energy)
            quarter[qidx].append(energy)
            all_values.append(energy)

        return exact, quarter, all_values

    def profile_statistics(self, profile: str) -> dict[str, Any]:
        """Return compact historical statistics for one profile."""
        exact, quarter, all_values = self._history(profile)
        exact_cells = len(exact)
        quarter_cells = len(quarter)
        return {
            "profile": profile,
            "valid_samples": len(all_values),
            "weekday_quarter_cells": exact_cells,
            "weekday_quarter_coverage": round(exact_cells / (7 * 96), 4),
            "quarter_cells": quarter_cells,
            "quarter_coverage": round(quarter_cells / 96, 4),
            "mean_quarter_kwh": round(mean(all_values), 6) if all_values else None,
        }

    def all_profile_statistics(self) -> dict[str, dict[str, Any]]:
        """Return statistics for all supported profiles."""
        return {profile: self.profile_statistics(profile) for profile in PROFILE_OPTIONS}

    def build(self, profile: str, now: datetime | None = None) -> list[ForecastSlot]:
        """Build 288 native 15-minute forecast slots from historical data."""
        exact, quarter, all_values = self._history(profile)
        now_local = dt_util.as_local(now or dt_util.utcnow())
        minute = (now_local.minute // QUARTER_MINUTES) * QUARTER_MINUTES
        next_local = now_local.replace(minute=minute, second=0, microsecond=0) + timedelta(minutes=QUARTER_MINUTES)
        start_utc = dt_util.as_utc(next_local)

        result: list[ForecastSlot] = []
        for offset in range(FORECAST_SLOTS):
            slot_start_utc = start_utc + timedelta(minutes=offset * QUARTER_MINUTES)
            slot_end_utc = slot_start_utc + timedelta(minutes=QUARTER_MINUTES)
            slot_start_local = dt_util.as_local(slot_start_utc)
            qidx = self._quarter_index(slot_start_local)
            exact_values = exact.get((slot_start_local.weekday(), qidx), [])
            quarter_values = quarter.get(qidx, [])

            if exact_values:
                value = mean(exact_values)
                samples = len(exact_values)
                source = "weekday_quarter"
                confidence = min(1.0, 0.55 + 0.09 * min(samples, 5))
            elif quarter_values:
                value = mean(quarter_values)
                samples = len(quarter_values)
                source = "quarter_of_day"
                confidence = min(0.55, 0.25 + 0.06 * min(samples, 5))
            elif all_values:
                value = mean(all_values)
                samples = len(all_values)
                source = "profile_mean"
                confidence = min(0.25, 0.10 + 0.01 * min(samples, 15))
            else:
                value = None
                samples = 0
                source = "unavailable"
                confidence = 0.0

            result.append(
                ForecastSlot(
                    start=slot_start_utc,
                    end=slot_end_utc,
                    energy_kwh=round(value, 6) if value is not None else None,
                    sample_count=samples,
                    source=source,
                    confidence=round(confidence, 3),
                )
            )
        return result

    @staticmethod
    def serialize(slots: list[ForecastSlot]) -> list[dict[str, Any]]:
        """Serialize forecast slots for Home Assistant attributes."""
        return [
            {
                "start": slot.start.isoformat(),
                "end": slot.end.isoformat(),
                "energy_kwh": slot.energy_kwh,
                "sample_count": slot.sample_count,
                "source": slot.source,
                "confidence": slot.confidence,
            }
            for slot in slots
        ]
