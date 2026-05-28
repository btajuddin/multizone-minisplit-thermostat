"""Offset learner for Multi-Zone Mini-Split Thermostat integration.

Implements simple linear regression to learn the temperature offset between
zone thermostats and mini-splits, using outside temperature as a predictor.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    OFFSET_LEARNING_WINDOW,
    OFFSET_MAX_VALUE,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "multizone_minisplit_thermostat"
STORAGE_KEY = f"{DOMAIN}_offset_data"
STORAGE_VERSION_MAJOR = 1
STORAGE_VERSION_MINOR = 0


class OffsetLearner:
    """Learn temperature offset using simple linear regression.

    Model: offset = a * outside_temp + b
    where offset = minisplit_temp - zone_temp
    """

    def __init__(
        self,
        hass: HomeAssistant,
        zone_entity_id: str,
        storage: Any | None = None,
    ) -> None:
        """Initialize the offset learner.

        Args:
            hass: Home Assistant instance
            zone_entity_id: The zone entity ID this learner is for
            storage: Optional storage helper for persistence
        """
        self.hass = hass
        self.zone_entity_id = zone_entity_id
        self._storage = storage
        self._data_points: list[dict[str, float]] = []
        self._slope: float = 0.0  # 'a' in y = a*x + b
        self._intercept: float = 0.0  # 'b' in y = a*x + b
        self._has_model: bool = False
        self._last_calculation: float = 0.0

    async def async_load(self) -> None:
        """Load persisted data points from storage."""
        if self._storage is None:
            return
        try:
            stored = await self._storage.async_load()
            if stored and isinstance(stored, dict):
                zone_data = stored.get(self.zone_entity_id, {})
                raw_points = zone_data.get("data_points", [])
                self._data_points = [
                    {
                        "outside_temp": float(p["outside_temp"]),
                        "zone_temp": float(p["zone_temp"]),
                        "minisplit_temp": float(p["minisplit_temp"]),
                        "timestamp": float(p["timestamp"]),
                    }
                    for p in raw_points
                    if all(k in p for k in ("outside_temp", "zone_temp", "minisplit_temp", "timestamp"))
                ]
                model = zone_data.get("model", {})
                if "slope" in model and "intercept" in model:
                    self._slope = float(model["slope"])
                    self._intercept = float(model["intercept"])
                    self._has_model = True
                _LOGGER.debug(
                    "Loaded %d data points for %s", len(self._data_points), self.zone_entity_id
                )
        except Exception:
            _LOGGER.exception("Failed to load offset data for %s", self.zone_entity_id)
            self._data_points = []

    async def async_persist(self) -> None:
        """Persist data points and model to storage."""
        if self._storage is None:
            return
        try:
            stored = await self._storage.async_load() or {}
            stored[self.zone_entity_id] = {
                "data_points": self._data_points,
                "model": {
                    "slope": self._slope,
                    "intercept": self._intercept,
                },
            }
            await self._storage.async_save(stored)
        except Exception:
            _LOGGER.exception("Failed to persist offset data for %s", self.zone_entity_id)

    def add_data_point(
        self,
        outside_temp: float,
        zone_temp: float,
        minisplit_temp: float,
        timestamp: float | None = None,
    ) -> None:
        """Record a new data point.

        Args:
            outside_temp: Current outside temperature
            zone_temp: Current zone thermostat temperature
            minisplit_temp: Current mini-split temperature
            timestamp: Optional timestamp (defaults to current time)
        """
        ts = timestamp or time.time()
        self._data_points.append({
            "outside_temp": outside_temp,
            "zone_temp": zone_temp,
            "minisplit_temp": minisplit_temp,
            "timestamp": ts,
        })
        self._prune_old_data(ts)
        self._fit_model()

    def get_predicted_offset(self, outside_temp: float) -> float:
        """Get the predicted offset for a given outside temperature.

        Args:
            outside_temp: Outside temperature to predict for

        Returns:
            Predicted offset, clamped to ±OFFSET_MAX_VALUE
        """
        if not self._has_model:
            return 0.0
        offset = self._slope * outside_temp + self._intercept
        return max(-OFFSET_MAX_VALUE, min(OFFSET_MAX_VALUE, offset))

    def get_sample_count(self) -> int:
        """Return the number of data points in the learning window."""
        return len(self._data_points)

    def get_model_info(self) -> dict[str, Any]:
        """Return current model coefficients and metadata."""
        return {
            "slope": self._slope,
            "intercept": self._intercept,
            "has_model": self._has_model,
            "sample_count": len(self._data_points),
            "last_calculation": self._last_calculation,
        }

    def clear_history(self) -> None:
        """Clear all data points and reset model."""
        self._data_points = []
        self._slope = 0.0
        self._intercept = 0.0
        self._has_model = False
        self._last_calculation = 0.0

    def _prune_old_data(self, current_time: float | None = None) -> None:
        """Remove data points outside the learning window."""
        ts = current_time or time.time()
        cutoff = ts - OFFSET_LEARNING_WINDOW
        before = len(self._data_points)
        self._data_points = [p for p in self._data_points if p["timestamp"] >= cutoff]
        if len(self._data_points) < before:
            _LOGGER.debug(
                "Pruned %d old data points for %s",
                before - len(self._data_points),
                self.zone_entity_id,
            )

    def _fit_model(self) -> None:
        """Recalculate regression coefficients from stored data.

        Simple linear regression: y = a*x + b
        where y = offset (minisplit_temp - zone_temp), x = outside_temp

        a = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
        b = (Σy - a*Σx) / n
        """
        points = self._data_points
        n = len(points)
        if n < 2:
            # Need at least 2 points for regression
            self._has_model = False
            return

        # Calculate offset for each point
        offsets = [p["minisplit_temp"] - p["zone_temp"] for p in points]
        outside_temps = [p["outside_temp"] for p in points]

        sum_x = sum(outside_temps)
        sum_y = sum(offsets)
        sum_xy = sum(x * y for x, y in zip(outside_temps, offsets))
        sum_x2 = sum(x * x for x in outside_temps)

        denominator = n * sum_x2 - sum_x * sum_x
        if abs(denominator) < 1e-10:
            # All outside temps are the same, can't do regression
            # Use mean offset instead
            self._slope = 0.0
            self._intercept = sum_y / n
            self._has_model = True
            self._last_calculation = time.time()
            _LOGGER.debug(
                "Flat regression for %s: offset=%.3f (all same outside temp)",
                self.zone_entity_id,
                self._intercept,
            )
            return

        self._slope = (n * sum_xy - sum_x * sum_y) / denominator
        self._intercept = (sum_y - self._slope * sum_x) / n
        self._has_model = True
        self._last_calculation = time.time()

        _LOGGER.debug(
            "Updated model for %s: offset = %.4f * outside_temp + %.4f (%d points)",
            self.zone_entity_id,
            self._slope,
            self._intercept,
            n,
        )
