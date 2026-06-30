"""Coordinator for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    ATTR_ZONE_PRESETS,
    AUTOMATIC_MODE_COOLDOWN,
    CONF_DEFAULT_PRESET,
    CONF_ENTITY_ID,
    CONF_MAX_ADJUSTMENT,
    CONF_PRESET_CONFIGS,
    CONF_PRIORITY,
    CONF_QUIET_MODE_ENTITY,
    CONF_TEMP_SENSOR_ENTITY_ID,
    CONF_ZONES,
    DEFAULT_COOL_TEMP,
    DEFAULT_DEBOUNCE_INTERVAL,
    DEFAULT_DEBOUNCE_THRESHOLD,
    DEFAULT_HEAT_TEMP,
    DEFAULT_MAX_ADJUSTMENT,
    DEFAULT_PRIORITY,
    PRESET_COMFORT,
    PRESETS,
    RECONCILE_INTERVAL,
    RECONCILE_TEMP_TOLERANCE,
    TEMPERATURE_TOLERANCE,
)

_LOGGER = logging.getLogger(__name__)


class MiniSplitThermostatCoordinator:
    """Coordinator for managing state across multiple mini-split zones."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        zone_configs: list[dict[str, Any]],
        preset_configs: dict[str, dict[str, float]],
        max_adjustment: float = DEFAULT_MAX_ADJUSTMENT,
        debounce_interval: int = DEFAULT_DEBOUNCE_INTERVAL,
        debounce_threshold: float = DEFAULT_DEBOUNCE_THRESHOLD,
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry_id = entry.entry_id
        name = entry.data.get(CONF_NAME) or entry.title or "Multi-Zone Thermostat"
        self._entry_name = name
        stored_mode = entry.options.get("mode")
        self._hvac_mode = HVACMode(stored_mode) if stored_mode else None
        self.zone_configs = zone_configs
        self._preset_configs: dict[str, dict[str, float]] = preset_configs
        stored_zone_presets: dict[str, str] = entry.options.get(ATTR_ZONE_PRESETS, {})
        self._zone_presets: dict[str, str] = dict(stored_zone_presets)
        self._auto_mode: bool = False
        self._select_entities: list[Any] = []
        self._number_entities: list[Any] = []
        self._sensor_entities: list[Any] = []
        self._remove_trackers: list[Any] = []
        self._remove_reconcile_tracker = None
        self._last_auto_mode_change: float = 0.0
        self._debounce_interval = debounce_interval
        self._debounce_threshold = debounce_threshold
        self._max_adjustment = max_adjustment
        self._last_temp_adjust_time: dict[str, float] = {}
        self._last_actual_setpoint: dict[str, float] = {}

        for zone_config in zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            if entity_id not in self._zone_presets:
                self._zone_presets[entity_id] = zone_config.get(
                    CONF_DEFAULT_PRESET, PRESET_COMFORT
                )
            self._last_temp_adjust_time[entity_id] = 0.0

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

    @property
    def max_adjustment(self) -> float:
        """Return the maximum setpoint adjustment."""
        return self._max_adjustment

    async def async_set_max_adjustment(self, value: float) -> None:
        """Update the maximum setpoint adjustment."""
        self._max_adjustment = value
        await self._persist_option(CONF_MAX_ADJUSTMENT, value)
        self._notify_state_changed()
        await self.async_push_temperatures()

    def add_select_entity(self, entity: Any) -> None:
        """Register a select entity for state update callbacks."""
        self._select_entities.append(entity)

    def add_number_entity(self, entity: Any) -> None:
        """Register a number entity for state update callbacks."""
        self._number_entities.append(entity)

    def add_sensor_entity(self, entity: Any) -> None:
        """Register a sensor entity for state update callbacks."""
        self._sensor_entities.append(entity)

    def get_preset_temp(self, preset: str, mode: str) -> float:
        """Get the target temperature for a preset and mode."""
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
        await self._persist_option(CONF_PRESET_CONFIGS, self._preset_configs)
        self._notify_state_changed()
        await self.async_push_temperatures()

    def is_quiet_mode_active(self, entity_id: str) -> bool:
        """Check if quiet mode is active for a zone."""
        zone_config = next(
            (zc for zc in self.zone_configs if zc[CONF_ENTITY_ID] == entity_id), None
        )
        if zone_config is None:
            return False
        quiet_entity = zone_config.get(CONF_QUIET_MODE_ENTITY)
        if quiet_entity is None:
            return False
        state = self.hass.states.get(quiet_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        return state.state.lower() == "on"

    def get_active_preset(self, entity_id: str) -> str:
        """Get the active preset for a zone."""
        return self._zone_presets.get(entity_id, PRESET_COMFORT)

    def get_desired_target(self, entity_id: str) -> float:
        """Get the desired target temperature for a zone."""
        if self._hvac_mode == HVACMode.HEAT:
            return self._get_heat_target(entity_id)
        return self._get_cool_target(entity_id)

    def get_target_temp(self, entity_id: str) -> float:
        """Get the desired target temperature for a zone."""
        return self.get_desired_target(entity_id)

    def get_actual_setpoint(self, entity_id: str) -> float:
        """Get the most recent actual setpoint for a zone."""
        return self._last_actual_setpoint.get(
            entity_id, self.get_desired_target(entity_id)
        )

    def compute_adjusted_setpoint(self, entity_id: str) -> float | None:
        """Compute the setpoint to push to an underlying thermostat."""
        desired = self.get_desired_target(entity_id)
        measured = self._get_zone_current_temperature(entity_id)
        if measured is None:
            return desired
        max_adjustment = max(0.0, self._max_adjustment)
        if self._hvac_mode == HVACMode.HEAT:
            adjustment = max(0.0, min(max_adjustment, desired - measured))
        elif self._hvac_mode == HVACMode.COOL:
            adjustment = -max(0.0, min(max_adjustment, measured - desired))
        else:
            return None
        return desired + adjustment

    def _should_push_actual_setpoint(
        self, entity_id: str, actual_setpoint: float
    ) -> bool:
        """Return whether a setpoint write passes debounce checks."""
        last_setpoint = self._last_actual_setpoint.get(entity_id)
        if last_setpoint is None:
            return True
        if abs(actual_setpoint - last_setpoint) < self._debounce_threshold:
            return False
        return (
            time.time() - self._last_temp_adjust_time.get(entity_id, 0.0)
            >= self._debounce_interval
        )

    async def _async_push_actual_setpoint(
        self, entity_id: str, force: bool = False
    ) -> None:
        """Push the computed actual setpoint to an underlying thermostat."""
        actual_setpoint = self.compute_adjusted_setpoint(entity_id)
        if actual_setpoint is None:
            return
        if self.is_quiet_mode_active(entity_id):
            _LOGGER.debug(
                "Skipping temperature push for %s (quiet mode active)", entity_id
            )
            return
        if not force and not self._should_push_actual_setpoint(
            entity_id, actual_setpoint
        ):
            return
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, "temperature": actual_setpoint},
        )
        self._last_actual_setpoint[entity_id] = actual_setpoint
        self._last_temp_adjust_time[entity_id] = time.time()
        self._notify_state_changed()

    async def async_push_temperatures(self) -> None:
        """Push the current adjusted temperatures to all underlying thermostats."""
        for zone_config in self.zone_configs:
            await self._async_push_actual_setpoint(zone_config[CONF_ENTITY_ID])

    async def async_sync_zones(self) -> None:
        """Synchronize all underlying thermostats with current mode and temperatures."""
        if self._hvac_mode is None:
            _LOGGER.debug("No HVAC mode set yet, skipping zone sync")
            return

        _LOGGER.info("Synchronizing all zones with mode %s", self._hvac_mode)

        for zone_config in self.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": self._hvac_mode.value},
            )
            await self._async_push_actual_setpoint(entity_id, force=True)

        self._last_auto_mode_change = time.time()

    async def async_reconcile_zones(self) -> None:
        """Reconcile underlying climate entities with expected state."""
        if self._hvac_mode is None:
            return

        for zone_config in self.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue

            expected_mode = self._hvac_mode.value
            if state.state != expected_mode:
                _LOGGER.info(
                    "Reconcile: %s mode is %s, expected %s — correcting",
                    entity_id,
                    state.state,
                    expected_mode,
                )
                await self.hass.services.async_call(
                    "climate",
                    "set_hvac_mode",
                    {"entity_id": entity_id, "hvac_mode": expected_mode},
                )

            if self.is_quiet_mode_active(entity_id):
                continue

            current_temp = state.attributes.get("temperature")
            expected_temp = self.compute_adjusted_setpoint(entity_id)
            if current_temp is None or expected_temp is None:
                continue

            try:
                current_temp = float(current_temp)
            except (ValueError, TypeError):
                continue

            if abs(current_temp - expected_temp) > RECONCILE_TEMP_TOLERANCE:
                _LOGGER.info(
                    "Reconcile: %s setpoint %.1f differs from expected %.1f — correcting",
                    entity_id,
                    current_temp,
                    expected_temp,
                )
                await self._async_push_actual_setpoint(entity_id, force=True)

    async def _persist_option(self, key: str, value: Any) -> None:
        """Persist a single option to the config entry options if changed."""
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if entry:
            current_options = dict(entry.options)
            if current_options.get(key) != value:
                new_options = {**current_options, key: value}
                self.hass.config_entries.async_update_entry(entry, options=new_options)

    async def _persist_mode(self) -> None:
        """Persist the current mode to config entry options."""
        mode_value = self._hvac_mode.value if self._hvac_mode else None
        await self._persist_option("mode", mode_value)

    def _notify_state_changed(self) -> None:
        """Notify all registered entities that state has changed."""
        for select_entity in self._select_entities:
            select_entity.async_write_ha_state()
        for number_entity in self._number_entities:
            number_entity.async_write_ha_state()
        for sensor_entity in self._sensor_entities:
            sensor_entity.async_write_ha_state()

    async def async_request_ha_state_update(self) -> None:
        """Request all registered entities to update their HA state."""
        self._notify_state_changed()

    async def set_entity_preset(self, entity_id: str, preset: str) -> None:
        """Set the preset for a specific zone."""
        if entity_id not in self._zone_presets:
            _LOGGER.warning("Zone %s not managed by this thermostat", entity_id)
            return
        if preset not in PRESETS:
            _LOGGER.warning("Invalid preset: %s", preset)
            return
        self._zone_presets[entity_id] = preset
        await self._persist_option(ATTR_ZONE_PRESETS, self._zone_presets)
        await self.async_push_temperatures()

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
        preset = self.get_active_preset(entity_id)
        preset_config = self._preset_configs.get(preset, {})
        return preset_config.get("heat_temp", DEFAULT_HEAT_TEMP)

    def _get_cool_target(self, entity_id: str) -> float:
        """Get the cooling target temperature for a zone based on its preset."""
        preset = self.get_active_preset(entity_id)
        preset_config = self._preset_configs.get(preset, {})
        return preset_config.get("cool_temp", DEFAULT_COOL_TEMP)

    def get_zone_priority(self, entity_id: str) -> int:
        """Get the priority for a specific zone."""
        for zone_config in self.zone_configs:
            if zone_config[CONF_ENTITY_ID] == entity_id:
                return zone_config.get(CONF_PRIORITY, DEFAULT_PRIORITY)
        return DEFAULT_PRIORITY

    async def async_set_zone_priority(self, entity_id: str, priority: int) -> None:
        """Set the priority for a specific zone."""
        for zone_config in self.zone_configs:
            if zone_config[CONF_ENTITY_ID] == entity_id:
                zone_config[CONF_PRIORITY] = priority
                await self._persist_option(CONF_ZONES, self.zone_configs)
                self._notify_state_changed()
                return

    def get_all_target_temps(self) -> dict[str, float]:
        """Get desired target temperatures for all zones."""
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

    def _get_zone_current_temperature(self, entity_id: str) -> float | None:
        """Get the current temperature for a zone, using override sensor if configured."""
        zone_config = next(
            (z for z in self.zone_configs if z[CONF_ENTITY_ID] == entity_id), None
        )
        if zone_config is None:
            return None

        temp_sensor_id = zone_config.get(CONF_TEMP_SENSOR_ENTITY_ID)
        if temp_sensor_id:
            state = self.hass.states.get(temp_sensor_id)
            if state is not None and state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                try:
                    return float(state.state)
                except (ValueError, TypeError):
                    pass

        zone_state = self.get_zone_state(entity_id)
        if zone_state is not None:
            current_temp = zone_state.get("current_temperature")
            if current_temp is not None:
                try:
                    return float(current_temp)
                except (ValueError, TypeError):
                    pass
        return None

    def determine_hvac_mode(self) -> HVACMode | None:
        """Determine the appropriate HVAC mode based on zone temperatures."""
        if not self._auto_mode:
            return None

        heat_zones: list[tuple[int, str]] = []
        cool_zones: list[tuple[int, str]] = []

        for zone_config in self.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            priority = zone_config.get(CONF_PRIORITY, DEFAULT_PRIORITY)
            current_temp = self._get_zone_current_temperature(entity_id)
            if current_temp is None:
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
            await self._async_push_actual_setpoint(entity_id, force=True)

        self._last_auto_mode_change = time.time()
        self._notify_state_changed()
        await self._persist_mode()

    def setup_state_listeners(self) -> None:
        """Set up state change listeners for underlying zones."""
        entity_ids = [z[CONF_ENTITY_ID] for z in self.zone_configs]

        for zone_config in self.zone_configs:
            quiet_entity = zone_config.get(CONF_QUIET_MODE_ENTITY)
            if quiet_entity:
                entity_ids.append(quiet_entity)

        for zone_config in self.zone_configs:
            temp_sensor = zone_config.get(CONF_TEMP_SENSOR_ENTITY_ID)
            if temp_sensor:
                entity_ids.append(temp_sensor)

        @callback
        def _async_state_changed(event: Any) -> None:
            """Handle state change events."""
            self.hass.async_create_task(self.async_check_and_update_mode())
            changed_entity = event.data.get("entity_id")
            if changed_entity in entity_ids:
                self.hass.async_create_task(self.async_push_temperatures())
            self._notify_state_changed()

        tracker = async_track_state_change_event(
            self.hass, entity_ids, _async_state_changed
        )
        self._remove_trackers.append(tracker)

        self._remove_reconcile_tracker = async_track_time_interval(
            self.hass,
            lambda _: self.hass.async_create_task(self.async_reconcile_zones()),
            timedelta(seconds=RECONCILE_INTERVAL),
        )

    def cleanup(self) -> None:
        """Remove all state change listeners."""
        for remove_tracker in self._remove_trackers:
            remove_tracker()
        self._remove_trackers.clear()
        if self._remove_reconcile_tracker is not None:
            self._remove_reconcile_tracker()
            self._remove_reconcile_tracker = None
