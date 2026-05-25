"""Coordinator for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_DEFAULT_PRESET,
    CONF_ENTITY_ID,
    CONF_PRIORITY,
    DEFAULT_COOL_TEMP,
    DEFAULT_HEAT_TEMP,
    DEFAULT_PRIORITY,
    PRESET_COMFORT,
    PRESETS,
    AUTOMATIC_MODE_COOLDOWN,
    TEMPERATURE_TOLERANCE,
)

_LOGGER = logging.getLogger(__name__)


class MiniSplitThermostatCoordinator:
    """Coordinator for managing state across multiple mini-split zones.

    Preset temperature configurations (heat_temp/cool_temp per preset) are
    shared across all zones. Each zone tracks which preset is currently
    active independently.

    The coordinator automatically determines whether to be in HEAT or COOL
    mode based on zone temperatures. If any zone is outside its comfort
    band (target ± tolerance), the mode is set to meet that need. When
    zones conflict, the highest priority zone wins.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        zone_configs: list[dict[str, Any]],
        preset_configs: dict[str, dict[str, float]],
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry_id = entry.entry_id
        # Get name from config data, entry title, or fallback
        name = entry.data.get(CONF_NAME)
        if not name:
            name = entry.title
        if not name:
            name = "Multi-Zone Thermostat"
        self._entry_name = name
        # Restore mode from options, or determine on startup
        stored_mode = entry.options.get("mode")
        if stored_mode:
            self._hvac_mode = HVACMode(stored_mode)
        else:
            self._hvac_mode = None
        self.zone_configs = zone_configs
        self._preset_configs: dict[str, dict[str, float]] = preset_configs
        self._zone_presets: dict[str, str] = {}
        self._auto_mode: bool = False
        self._select_entities: list = []
        self._number_entities: list = []
        self._remove_trackers: list = []
        self._last_auto_mode_change: float = 0.0

        for zone_config in zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            self._zone_presets[entity_id] = zone_config.get(
                CONF_DEFAULT_PRESET, PRESET_COMFORT
            )

    @property
    def entity_presets(self) -> dict[str, str]:
        """Return the current preset for each zone."""
        return dict(self._zone_presets)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the shared HVAC mode."""
        return self._hvac_mode

    @property
    def entry_name(self) -> str:
        """Return the thermostat name."""
        return self._entry_name

    def add_select_entity(self, entity: Any) -> None:
        """Register a select entity for state update callbacks."""
        self._select_entities.append(entity)

    def add_number_entity(self, entity: Any) -> None:
        """Register a number entity for state update callbacks."""
        self._number_entities.append(entity)

    def get_preset_temp(self, preset: str, mode: str) -> float:
        """Get the target temperature for a preset and mode (heat/cool)."""
        preset_config = self._preset_configs.get(preset, {})
        if mode == "heat":
            return preset_config.get("heat_temp", DEFAULT_HEAT_TEMP)
        return preset_config.get("cool_temp", DEFAULT_COOL_TEMP)

    async def async_set_preset_temp(self, preset: str, mode: str, value: float) -> None:
        """Set the target temperature for a preset and mode."""
        if preset not in self._preset_configs:
            self._preset_configs[preset] = {}
        key = "heat_temp" if mode == "heat" else "cool_temp"
        self._preset_configs[preset][key] = value
        self._notify_state_changed()

    async def _persist_mode(self) -> None:
        """Persist the current mode to config entry options."""
        mode_value = self._hvac_mode.value if self._hvac_mode else None
        current_options = dict(self.hass.config_entries.async_get_entry(self.entry_id).options)
        if current_options.get("mode") != mode_value:
            new_options = {**current_options, "mode": mode_value}
            self.hass.config_entries.async_update_entry(
                self.hass.config_entries.async_get_entry(self.entry_id),
                options=new_options,
            )

    def _notify_state_changed(self) -> None:
        """Notify all registered entities that state has changed."""
        for select_entity in self._select_entities:
            select_entity.async_write_ha_state()
        for number_entity in self._number_entities:
            number_entity.async_write_ha_state()

    async def async_request_ha_state_update(self) -> None:
        """Request all registered entities to update their HA state."""
        self._notify_state_changed()

    def set_entity_preset(self, entity_id: str, preset: str) -> None:
        """Set the preset for a specific zone."""
        if entity_id not in self._zone_presets:
            _LOGGER.warning("Zone %s not managed by this thermostat", entity_id)
            return
        if preset not in PRESETS:
            _LOGGER.warning("Invalid preset: %s", preset)
            return
        self._zone_presets[entity_id] = preset

    async def async_set_hvac_mode(self, mode: HVACMode) -> None:
        """Set the HVAC mode for all underlying zones."""
        if mode not in (HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF):
            _LOGGER.warning("Unsupported HVAC mode: %s", mode)
            return
        self._hvac_mode = mode
        if mode == HVACMode.OFF:
            self._auto_mode = False
        self._last_auto_mode_change = time.time()
        self._notify_state_changed()
        await self._persist_mode()

    def _get_heat_target(self, entity_id: str) -> float:
        """Get the heating target temperature for a zone based on its preset."""
        preset = self._zone_presets.get(entity_id, PRESET_COMFORT)
        preset_config = self._preset_configs.get(preset, {})
        return preset_config.get("heat_temp", DEFAULT_HEAT_TEMP)

    def _get_cool_target(self, entity_id: str) -> float:
        """Get the cooling target temperature for a zone based on its preset."""
        preset = self._zone_presets.get(entity_id, PRESET_COMFORT)
        preset_config = self._preset_configs.get(preset, {})
        return preset_config.get("cool_temp", DEFAULT_COOL_TEMP)

    def get_target_temp(self, entity_id: str) -> float:
        """Get the target temperature for a zone based on its preset and current mode."""
        if self._hvac_mode == HVACMode.HEAT:
            return self._get_heat_target(entity_id)
        else:
            return self._get_cool_target(entity_id)

    def get_all_target_temps(self) -> dict[str, float]:
        """Get target temperatures for all zones."""
        return {
            entity_id: self.get_target_temp(entity_id)
            for entity_id in self._zone_presets
        }

    def get_zone_state(self, entity_id: str) -> dict[str, Any] | None:
        """Get the current state dict for an underlying zone."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return {
            "state": state.state,
            "temperature": state.attributes.get("temperature"),
            "current_temperature": state.attributes.get("current_temperature"),
            "preset_mode": state.attributes.get("preset_mode"),
            "hvac_action": state.attributes.get("hvac_action"),
        }

    def determine_hvac_mode(self) -> HVACMode | None:
        """Determine the appropriate HVAC mode based on zone temperatures.

        Returns the mode that should be set, or None if no change is needed.
        If zones conflict, the highest priority zone wins.
        """
        if not self._auto_mode:
            return None

        heat_zones: list[tuple[int, str]] = []
        cool_zones: list[tuple[int, str]] = []

        for zone_config in self.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            priority = zone_config.get(CONF_PRIORITY, DEFAULT_PRIORITY)

            zone_state = self.get_zone_state(entity_id)
            if zone_state is None:
                continue

            current_temp = zone_state.get("current_temperature")
            if current_temp is None:
                continue

            try:
                current_temp = float(current_temp)
            except (ValueError, TypeError):
                continue

            heat_target = self._get_heat_target(entity_id)
            cool_target = self._get_cool_target(entity_id)

            if current_temp < heat_target - TEMPERATURE_TOLERANCE:
                heat_zones.append((priority, entity_id))
            elif current_temp > cool_target + TEMPERATURE_TOLERANCE:
                cool_zones.append((priority, entity_id))

        if heat_zones and cool_zones:
            max_heat_priority = max(heat_zones, key=lambda x: x[0])
            max_cool_priority = max(cool_zones, key=lambda x: x[0])
            if max_heat_priority[0] >= max_cool_priority[0]:
                return HVACMode.HEAT
            return HVACMode.COOL

        if heat_zones:
            return HVACMode.HEAT
        if cool_zones:
            return HVACMode.COOL

        return None

    async def async_check_and_update_mode(self) -> None:
        """Check if HVAC mode needs to change and apply it if so."""
        elapsed = time.time() - self._last_auto_mode_change
        if elapsed < AUTOMATIC_MODE_COOLDOWN:
            return

        determined_mode = self.determine_hvac_mode()
        if determined_mode is None or determined_mode == self._hvac_mode:
            return

        _LOGGER.info(
            "Auto-switching HVAC mode from %s to %s",
            self._hvac_mode,
            determined_mode,
        )
        self._hvac_mode = determined_mode

        for zone_config in self.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": determined_mode},
            )
            target_temp = self.get_target_temp(entity_id)
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": entity_id, "temperature": target_temp},
            )

        self._last_auto_mode_change = time.time()
        self._notify_state_changed()
        await self._persist_mode()

    def setup_state_listeners(self) -> None:
        """Set up state change listeners for underlying zones."""
        entity_ids = [z[CONF_ENTITY_ID] for z in self.zone_configs]

        @callback
        def _async_state_changed(event: Any) -> None:
            self.hass.async_create_task(self.async_check_and_update_mode())
            self._notify_state_changed()

        tracker = async_track_state_change_event(
            self.hass, entity_ids, _async_state_changed
        )
        self._remove_trackers.append(tracker)

    def cleanup(self) -> None:
        """Remove all state change listeners."""
        for remove_tracker in self._remove_trackers:
            remove_tracker()
        self._remove_trackers.clear()
