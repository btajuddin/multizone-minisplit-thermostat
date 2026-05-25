"""Climate platform for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

import logging
import time
from statistics import mean
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_track_state_change_event

from . import _register_coordinator
from .const import (
    CONF_DEFAULT_PRESET,
    CONF_ENTITY_ID,
    CONF_PRESET_CONFIGS,
    CONF_PRIORITY,
    CONF_ZONES,
    DEFAULT_COOL_TEMP,
    DEFAULT_HEAT_TEMP,
    DEFAULT_PRIORITY,
    DOMAIN,
    PRESET_COMFORT,
    PRESETS,
    AUTOMATIC_MODE_COOLDOWN,
    TEMPERATURE_TOLERANCE,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = "climate.{}"


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
        self._entry_name = entry.data.get(CONF_NAME, entry.entry_id)
        self.zone_configs = zone_configs
        self._preset_configs: dict[str, dict[str, float]] = preset_configs
        self._zone_presets: dict[str, str] = {}
        self._hvac_mode: HVACMode | None = None
        self._auto_mode: bool = True
        self._thermostat_entity: MultiZoneMinisplitThermostat | None = None
        self._select_entities: list["ZonePresetSelect"] = []
        self._number_entities: list["PresetTemperatureNumber"] = []
        self._remove_trackers: list[CALLBACK_TYPE] = []
        self._last_auto_mode_change: float = 0.0

        # Initialize default presets from config
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

    def set_thermostat_entity(self, entity: "MultiZoneMinisplitThermostat") -> None:
        """Register the thermostat entity for state update callbacks."""
        self._thermostat_entity = entity

    def add_select_entity(self, entity: "ZonePresetSelect") -> None:
        """Register a select entity for state update callbacks."""
        self._select_entities.append(entity)

    def add_number_entity(self, entity: "PresetTemperatureNumber") -> None:
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

    def _notify_state_changed(self) -> None:
        """Notify all registered entities that state has changed."""
        if self._thermostat_entity is not None:
            self._thermostat_entity.async_write_ha_state()
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
        """Determine the appropriate HVAC mode based on zone temperatures and presets.

        Evaluates each zone's current temperature against its preset-specific
        heat and cool targets (with tolerance). Returns the mode that should
        be actively set. Returns None when all zones are within their comfort
        band, signaling that the current mode should remain unchanged.
        If zones conflict (some need heat, some need cool), the highest
        priority zone wins.
        """
        if not self._auto_mode:
            return None

        heat_zones: list[tuple[int, str]] = []  # (priority, entity_id)
        cool_zones: list[tuple[int, str]] = []  # (priority, entity_id)

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

        # Both needs detected - highest priority zone wins
        if heat_zones and cool_zones:
            max_heat_priority = max(heat_zones, key=lambda x: x[0])
            max_cool_priority = max(cool_zones, key=lambda x: x[0])

            if max_heat_priority[0] >= max_cool_priority[0]:
                return HVACMode.HEAT
            else:
                return HVACMode.COOL

        if heat_zones:
            return HVACMode.HEAT
        if cool_zones:
            return HVACMode.COOL

        # All zones are within their comfort band - keep current mode unchanged
        return None

    async def async_check_and_update_mode(self) -> None:
        """Check if HVAC mode needs to change and apply it if so."""
        elapsed = time.time() - self._last_auto_mode_change
        if elapsed < AUTOMATIC_MODE_COOLDOWN:
            remaining = AUTOMATIC_MODE_COOLDOWN - elapsed
            _LOGGER.debug(
                "Skipping auto mode check, %d seconds remaining in cooldown",
                int(remaining),
            )
            return

        determined_mode = self.determine_hvac_mode()
        if determined_mode is None:
            # All zones within range - keep current mode unchanged
            return

        if determined_mode == self._hvac_mode:
            return

        _LOGGER.info(
            "Auto-switching HVAC mode from %s to %s",
            self._hvac_mode,
            determined_mode,
        )
        self._hvac_mode = determined_mode

        # Propagate mode change to all underlying zones
        for zone_config in self.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": determined_mode},
            )
            # Set the new target temperature for this zone
            target_temp = self.get_target_temp(entity_id)
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": entity_id, "temperature": target_temp},
            )

        self._last_auto_mode_change = time.time()
        self._notify_state_changed()

    def setup_state_listeners(self) -> None:
        """Set up state change listeners for underlying zones."""
        entity_ids = [z[CONF_ENTITY_ID] for z in self.zone_configs]

        @callback
        def _async_state_changed(event: Any) -> None:
            """Handle state change of an underlying zone."""
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the climate platform."""
    entry_data = dict(entry.data)

    zone_configs = entry_data.get(CONF_ZONES, [])
    preset_configs = entry_data.get(CONF_PRESET_CONFIGS, {})

    coordinator = MiniSplitThermostatCoordinator(
        hass, entry, zone_configs, preset_configs
    )

    _register_coordinator(coordinator)

    name = entry_data.get(CONF_NAME, entry.entry_id)
    thermostat = MultiZoneMinisplitThermostat(coordinator, name)
    coordinator.set_thermostat_entity(thermostat)

    async_add_entities([thermostat])

    # Initialize mode from first zone's state
    await coordinator.async_check_and_update_mode()

    coordinator.setup_state_listeners()


class MultiZoneMinisplitThermostat(ClimateEntity):
    """Representation of a multi-zone mini-split thermostat.

    This entity acts as a group mode controller. It does not expose
    a single target temperature or preset mode, since those are managed
    per-zone via separate select entities.
    """

    _attr_has_entity_name = True
    _attr_supported_features = ClimateEntityFeature.TURN_OFF
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT

    def __init__(
        self,
        coordinator: MiniSplitThermostatCoordinator,
        name: str,
    ) -> None:
        """Initialize the thermostat."""
        self.coordinator = coordinator
        self._attr_name = name
        self._attr_unique_id = coordinator.entry_id
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, name, hass=coordinator.hass
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=name,
            manufacturer="Multi-Zone Mini-Split Thermostat",
            model="Virtual Thermostat",
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        self.coordinator.cleanup()
        await super().async_will_remove_from_hass()

    @property
    def current_temperature(self) -> float | None:
        """Return the average current temperature across all zones."""
        temps = []
        for zone_config in self.coordinator.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            state = self.coordinator.get_zone_state(entity_id)
            if state and state.get("current_temperature") is not None:
                try:
                    temps.append(float(state["current_temperature"]))
                except (ValueError, TypeError):
                    pass
        return mean(temps) if temps else None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        mode = self.coordinator.hvac_mode
        return mode if mode is not None else HVACMode.HEAT

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return zone-specific state attributes."""
        attrs: dict[str, Any] = {
            "zone_presets": self.coordinator.entity_presets,
            "zone_target_temps": self.coordinator.get_all_target_temps(),
            "zones": {},
        }

        for zone_config in self.coordinator.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            state = self.coordinator.get_zone_state(entity_id)
            attrs["zones"][entity_id] = {
                "priority": zone_config.get(CONF_PRIORITY, DEFAULT_PRIORITY),
                "preset": self.coordinator.entity_presets.get(entity_id),
                "heat_target": self.coordinator._get_heat_target(entity_id),
                "cool_target": self.coordinator._get_cool_target(entity_id),
                "target_temp": self.coordinator.get_target_temp(entity_id),
                "current_state": state,
            }

        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode for all underlying zones.

        Setting a mode manually disables auto mode switching until
        the mode is set back to auto (by setting to the determined mode).
        """
        if hvac_mode == HVACMode.OFF:
            self.coordinator._auto_mode = False
        else:
            # Re-enable auto mode when user selects heat or cool
            self.coordinator._auto_mode = True

        await self.coordinator.async_set_hvac_mode(hvac_mode)

        for zone_config in self.coordinator.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": hvac_mode},
            )
