"""Coordinator for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from datetime import timedelta
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
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store

from .const import (
    CONF_DEFAULT_PRESET,
    CONF_DEBOUNCE_INTERVAL,
    CONF_DEBOUNCE_THRESHOLD,
    CONF_ENABLE_OFFSET_LEARNING,
    CONF_ENTITY_ID,
    CONF_PRESET_CONFIGS,
    CONF_PRIORITY,
    CONF_QUIET_MODE_ENTITY,
    CONF_TEMP_SENSOR_ENTITY_ID,
    CONF_ZONES,
    DEFAULT_COOL_TEMP,
    DEFAULT_DEBOUNCE_INTERVAL,
    DEFAULT_DEBOUNCE_THRESHOLD,
    DEFAULT_HEAT_TEMP,
    DEFAULT_PRIORITY,
    PRESET_COMFORT,
    PRESETS,
    AUTOMATIC_MODE_COOLDOWN,
    TEMPERATURE_TOLERANCE,
    OFFSET_RECALC_INTERVAL,
    RECONCILE_INTERVAL,
    RECONCILE_TEMP_TOLERANCE,
)
from .offset_learner import (
    OffsetLearner,
    STORAGE_KEY,
    STORAGE_VERSION_MAJOR,
    STORAGE_VERSION_MINOR,
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

    Features:
    - Offset learning: learns temperature offset between zone thermostats
      and mini-splits using outside temperature as a predictor
    - Quiet mode: prevents temperature adjustments during quiet hours
    - Debounce: prevents rapid/tiny temperature changes
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        zone_configs: list[dict[str, Any]],
        preset_configs: dict[str, dict[str, float]],
        outside_temp_entity: str | None = None,
        debounce_interval: int = DEFAULT_DEBOUNCE_INTERVAL,
        debounce_threshold: float = DEFAULT_DEBOUNCE_THRESHOLD,
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
        self._remove_reconcile_tracker = None
        self._last_auto_mode_change: float = 0.0

        # Offset learning and debounce
        self._outside_temp_entity = outside_temp_entity
        self._debounce_interval = debounce_interval
        self._debounce_threshold = debounce_threshold
        self._last_temp_adjust_time: dict[str, float] = {}
        self._current_offsets: dict[str, float] = {}
        self._offset_learners: dict[str, OffsetLearner] = {}
        self._last_recalc_time: float = 0.0
        self._storage: Store | None = None
        self._zone_offset_learning_enabled: dict[str, bool] = {}

        for zone_config in zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            self._zone_presets[entity_id] = zone_config.get(
                CONF_DEFAULT_PRESET, PRESET_COMFORT
            )
            self._current_offsets[entity_id] = 0.0
            self._last_temp_adjust_time[entity_id] = 0.0
            self._zone_offset_learning_enabled[entity_id] = zone_config.get(CONF_ENABLE_OFFSET_LEARNING, True)

    async def async_set_debounce_interval(self, value: int) -> None:
        """Update the debounce interval."""
        self._debounce_interval = value
        await self._persist_option(CONF_DEBOUNCE_INTERVAL, value)
        self._notify_state_changed()

    async def async_set_debounce_threshold(self, value: float) -> None:
        """Update the debounce threshold."""
        self._debounce_threshold = value
        await self._persist_option(CONF_DEBOUNCE_THRESHOLD, value)
        self._notify_state_changed()

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
    def current_offsets(self) -> dict[str, float]:
        """Return the current learned offsets per zone."""
        return dict(self._current_offsets)

    @property
    def offset_learners(self) -> dict[str, OffsetLearner]:
        """Return the offset learners per zone."""
        return dict(self._offset_learners)

    @property
    def outside_temp_entity(self) -> str | None:
        """Return the outside temperature entity."""
        return self._outside_temp_entity

    async def async_set_zone_offset_learning_enabled(self, entity_id: str, enabled: bool) -> None:
        """Enable or disable offset learning for a specific zone."""
        self._zone_offset_learning_enabled[entity_id] = enabled
        
        # Update zone_configs list
        for zone_config in self.zone_configs:
            if zone_config[CONF_ENTITY_ID] == entity_id:
                zone_config[CONF_ENABLE_OFFSET_LEARNING] = enabled
                break
                
        await self._persist_option(CONF_ZONES, self.zone_configs)
        self._notify_state_changed()

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
        await self._persist_option(CONF_PRESET_CONFIGS, self._preset_configs)
        self._notify_state_changed()
        await self.async_push_temperatures()

    async def async_init_offset_learning(self) -> None:
        """Initialize offset learning system and load persisted data."""
        if self._outside_temp_entity is None:
            _LOGGER.debug("No outside temperature entity configured, offset learning disabled")
            return

        self._storage = Store(
            self.hass,
            STORAGE_VERSION_MAJOR,
            STORAGE_KEY,
            minor_version=STORAGE_VERSION_MINOR,
        )

        for zone_config in self.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            if not self._zone_offset_learning_enabled.get(entity_id, True):
                continue
            learner = OffsetLearner(self.hass, entity_id, self._storage)
            self._offset_learners[entity_id] = learner
            await learner.async_load()
            _LOGGER.debug(
                "Initialized offset learner for %s (%d samples)",
                entity_id,
                learner.get_sample_count(),
            )

        # Perform initial recalculation
        await self.async_recalculate_offsets()

    def is_quiet_mode_active(self, entity_id: str) -> bool:
        """Check if quiet mode is active for a zone."""
        zone_config = None
        for zc in self.zone_configs:
            if zc[CONF_ENTITY_ID] == entity_id:
                zone_config = zc
                break

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

    def should_adjust_temperature(self, entity_id: str, new_offset: float) -> bool:
        """Check if temperature adjustment should be applied (debounce)."""
        last_adjust = self._last_temp_adjust_time.get(entity_id, 0.0)
        current_offset = self._current_offsets.get(entity_id, 0.0)

        # Time-based debounce
        elapsed = time.time() - last_adjust
        if elapsed < self._debounce_interval:
            return False

        # Threshold-based debounce
        if abs(new_offset - current_offset) < self._debounce_threshold:
            return False

        return True

    def _get_outside_temp(self) -> float | None:
        """Get the current outside temperature from the configured entity."""
        if self._outside_temp_entity is None:
            return None
        state = self.hass.states.get(self._outside_temp_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    async def async_record_data_point(self, entity_id: str) -> None:
        """Collect a data point for offset learning."""
        if entity_id not in self._offset_learners:
            return

        if not self._zone_offset_learning_enabled.get(entity_id, True):
            return

        outside_temp = self._get_outside_temp()
        if outside_temp is None:
            return

        zone_temp = self._get_zone_current_temperature(entity_id)
        if zone_temp is None:
            return

        # The mini-split temp is the same as the zone temp from the zone's
        # perspective since we're reading the zone's underlying climate entity
        # which IS the mini-split. The offset is between what the thermostat
        # target says vs what the mini-split reports.
        minisplit_temp = zone_temp

        learner = self._offset_learners[entity_id]
        learner.add_data_point(outside_temp, zone_temp, minisplit_temp)
        await learner.async_persist()

        _LOGGER.debug(
            "Recorded data point for %s: outside=%.1f, zone=%.1f, ms=%.1f",
            entity_id,
            outside_temp,
            zone_temp,
            minisplit_temp,
        )

    async def async_recalculate_offsets(self) -> None:
        """Recalculate offsets for all zones from learners."""
        outside_temp = self._get_outside_temp()
        if outside_temp is None:
            _LOGGER.debug("Outside temperature unavailable, skipping offset recalculation")
            return

        any_changed = False
        now = time.time()

        for entity_id, learner in self._offset_learners.items():
            if not self._zone_offset_learning_enabled.get(entity_id, True):
                continue

            predicted_offset = learner.get_predicted_offset(outside_temp)

            if self.should_adjust_temperature(entity_id, predicted_offset):
                old_offset = self._current_offsets.get(entity_id, 0.0)
                self._current_offsets[entity_id] = predicted_offset
                self._last_temp_adjust_time[entity_id] = now
                any_changed = True
                _LOGGER.info(
                    "Updated offset for %s: %.3f -> %.3f",
                    entity_id,
                    old_offset,
                    predicted_offset,
                )
            else:
                _LOGGER.debug(
                    "Offset for %s unchanged (debounce): predicted=%.3f, current=%.3f",
                    entity_id,
                    predicted_offset,
                    self._current_offsets.get(entity_id, 0.0),
                )

        self._last_recalc_time = now

        # Persist all learners
        for learner in self._offset_learners.values():
            await learner.async_persist()

        if any_changed:
            await self.async_push_temperatures()

    async def async_clear_offset_history(self, entity_id: str | None = None) -> None:
        """Clear offset history for one zone or all zones."""
        if entity_id is not None:
            if entity_id in self._offset_learners:
                self._offset_learners[entity_id].clear_history()
                self._current_offsets[entity_id] = 0.0
                self._last_temp_adjust_time[entity_id] = 0.0
                await self._offset_learners[entity_id].async_persist()
                _LOGGER.info("Cleared offset history for %s", entity_id)
        else:
            for eid, learner in self._offset_learners.items():
                learner.clear_history()
                self._current_offsets[eid] = 0.0
                self._last_temp_adjust_time[eid] = 0.0
                await learner.async_persist()
            _LOGGER.info("Cleared offset history for all zones")

    async def async_push_temperatures(self) -> None:
        """Push the current target temperatures to all underlying thermostats.

        Respects quiet mode and debounce settings.
        """
        outside_temp = self._get_outside_temp()
        now = time.time()

        for zone_config in self.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            base_target = self.get_target_temp(entity_id)

            # Check quiet mode: if active, only push if temperature would change
            # to the same value the mini-split already has (avoid beeping)
            if self.is_quiet_mode_active(entity_id):
                zone_state = self.get_zone_state(entity_id)
                if zone_state is not None:
                    current_ms_temp = zone_state.get("temperature")
                    if current_ms_temp is not None:
                        try:
                            current_ms_temp = float(current_ms_temp)
                            # Only push if significantly different
                            if abs(base_target - current_ms_temp) < 0.5:
                                continue
                        except (ValueError, TypeError):
                            pass

            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": entity_id, "temperature": base_target},
            )

    async def async_sync_zones(self) -> None:
        """Synchronize all underlying thermostats with current mode and temperatures."""
        if self._hvac_mode is None:
            _LOGGER.debug("No HVAC mode set yet, skipping zone sync")
            return

        _LOGGER.info("Synchronizing all zones with mode %s", self._hvac_mode)

        for zone_config in self.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]

            # Skip temperature sync if quiet mode is active
            if self.is_quiet_mode_active(entity_id):
                _LOGGER.debug("Skipping zone sync for %s (quiet mode active)", entity_id)
                await self.hass.services.async_call(
                    "climate",
                    "set_hvac_mode",
                    {"entity_id": entity_id, "hvac_mode": self._hvac_mode.value},
                )
                continue

            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": self._hvac_mode.value},
            )
            target_temp = self.get_target_temp(entity_id)
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": entity_id, "temperature": target_temp},
            )

        self._last_auto_mode_change = time.time()

    async def async_reconcile_zones(self) -> None:
        """Reconcile underlying climate entities with expected state.

        Runs periodically. For each zone, checks that the HVAC mode and
        setpoint match what the integration expects. If they diverge
        (e.g. someone adjusted the mini-split directly), pushes the
        correct values.
        """
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
            expected_temp = self.get_target_temp(entity_id)
            if current_temp is None:
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
                await self.hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {"entity_id": entity_id, "temperature": expected_temp},
                )

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

    def get_target_temp(self, entity_id: str) -> float:
        """Get the target temperature for a zone based on its preset, mode, and offset."""
        if self._hvac_mode == HVACMode.HEAT:
            base = self._get_heat_target(entity_id)
        else:
            base = self._get_cool_target(entity_id)

        # Apply learned offset
        offset = self._current_offsets.get(entity_id, 0.0)
        return base + offset

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

    def _get_zone_current_temperature(self, entity_id: str) -> float | None:
        """Get the current temperature for a zone, using override sensor if configured."""
        # Find zone config
        zone_config = next((z for z in self.zone_configs if z[CONF_ENTITY_ID] == entity_id), None)
        if zone_config is None:
            return None

        # Check for override sensor
        temp_sensor_id = zone_config.get(CONF_TEMP_SENSOR_ENTITY_ID)
        if temp_sensor_id:
            state = self.hass.states.get(temp_sensor_id)
            if state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    return float(state.state)
                except (ValueError, TypeError):
                    pass

        # Fallback to climate entity's current_temperature
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
        """Determine the appropriate HVAC mode based on zone temperatures.

        Returns the mode that should be set, or None if no change is needed.
        If zones conflict, the highest priority zone wins.

        NOTE: This runs even during quiet mode - mode switching is NOT blocked.
        """
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
            # Only push temperature if not in quiet mode
            if not self.is_quiet_mode_active(entity_id):
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

        # Also track outside temp entity if configured
        if self._outside_temp_entity:
            entity_ids.append(self._outside_temp_entity)

        # Track quiet mode entities if configured
        for zone_config in self.zone_configs:
            quiet_entity = zone_config.get(CONF_QUIET_MODE_ENTITY)
            if quiet_entity:
                entity_ids.append(quiet_entity)

        # Track temperature sensor entities if configured
        for zone_config in self.zone_configs:
            temp_sensor = zone_config.get(CONF_TEMP_SENSOR_ENTITY_ID)
            if temp_sensor:
                entity_ids.append(temp_sensor)

        @callback
        def _async_state_changed(event: Any) -> None:
            """Handle state change events."""
            self.hass.async_create_task(self.async_check_and_update_mode())

            # Record data point for offset learning
            changed_entity = event.data.get("entity_id")
            if changed_entity in self._offset_learners and self._zone_offset_learning_enabled.get(changed_entity, True):
                self.hass.async_create_task(self.async_record_data_point(changed_entity))

            # Recalculate offsets if outside temp changed
            if changed_entity == self._outside_temp_entity:
                now = time.time()
                if now - self._last_recalc_time >= OFFSET_RECALC_INTERVAL:
                    self.hass.async_create_task(self.async_recalculate_offsets())

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
