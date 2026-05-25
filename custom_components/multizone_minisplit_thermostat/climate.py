"""Climate platform for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

import logging
from statistics import mean
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    HomeAssistant,
    Event,
    callback,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_track_state_change_event

from . import _register_coordinator
from .const import (
    CONF_DEFAULT_PRESET,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_PRESET_CONFIGS,
    DEFAULT_COOL_TEMP,
    DEFAULT_HEAT_TEMP,
    DOMAIN,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_FAILSAFE,
    PRESETS,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = DOMAIN + ".{}"


class MiniSplitThermostatCoordinator:
    """Coordinator for managing state across multiple mini-split entities.

    Preset temperature configurations (heat_temp/cool_temp per preset) are
    shared across all entities. Each entity tracks which preset is currently
    active independently.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        entity_configs: list[dict[str, Any]],
        preset_configs: dict[str, dict[str, float]],
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry_id = entry.entry_id
        self._entry_name = entry.data.get(CONF_NAME, entry.entry_id)
        self.entity_configs = entity_configs
        self._preset_configs: dict[str, dict[str, float]] = preset_configs
        self._entity_presets: dict[str, str] = {}
        self._hvac_mode: HVACMode | None = None
        self._thermostat_entity: MultiZoneMinisplitThermostat | None = None
        self._remove_trackers: list[CALLBACK_TYPE] = []

        # Initialize default presets from config
        for entity_config in entity_configs:
            entity_id = entity_config[CONF_ENTITY_ID]
            self._entity_presets[entity_id] = entity_config.get(
                CONF_DEFAULT_PRESET, PRESET_COMFORT
            )

    @property
    def entity_presets(self) -> dict[str, str]:
        """Return the current preset for each entity."""
        return dict(self._entity_presets)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the shared HVAC mode."""
        return self._hvac_mode

    def set_thermostat_entity(self, entity: "MultiZoneMinisplitThermostat") -> None:
        """Register the thermostat entity for state update callbacks."""
        self._thermostat_entity = entity

    def async_request_ha_state_update(self) -> None:
        """Request the thermostat entity to update its HA state."""
        if self._thermostat_entity is not None:
            self._thermostat_entity.async_write_ha_state()

    async def async_initialize(self) -> None:
        """Initialize coordinator by reading current state of underlying entities."""
        for entity_config in self.entity_configs:
            entity_id = entity_config[CONF_ENTITY_ID]
            state = self.hass.states.get(entity_id)
            if state and state.state in (HVACMode.HEAT, HVACMode.COOL):
                if self._hvac_mode is None:
                    self._hvac_mode = HVACMode(state.state)
                return

        # Default to HEAT if no valid state found
        if self._hvac_mode is None:
            self._hvac_mode = HVACMode.HEAT

    def set_entity_preset(self, entity_id: str, preset: str) -> None:
        """Set the preset for a specific entity."""
        if entity_id not in self._entity_presets:
            _LOGGER.warning("Entity %s not managed by this thermostat", entity_id)
            return
        if preset not in PRESETS:
            _LOGGER.warning("Invalid preset: %s", preset)
            return
        self._entity_presets[entity_id] = preset

    async def async_set_hvac_mode(self, mode: HVACMode) -> None:
        """Set the HVAC mode for all underlying entities."""
        if mode not in (HVACMode.HEAT, HVACMode.COOL):
            _LOGGER.warning("Unsupported HVAC mode: %s", mode)
            return
        self._hvac_mode = mode

    def get_target_temp(self, entity_id: str) -> float:
        """Get the target temperature for an entity based on its preset and current mode."""
        preset = self._entity_presets.get(entity_id, PRESET_COMFORT)
        preset_config = self._preset_configs.get(preset, {})

        if self._hvac_mode == HVACMode.HEAT:
            return preset_config.get("heat_temp", DEFAULT_HEAT_TEMP)
        else:
            return preset_config.get("cool_temp", DEFAULT_COOL_TEMP)

    def get_all_target_temps(self) -> dict[str, float]:
        """Get target temperatures for all entities."""
        return {
            entity_id: self.get_target_temp(entity_id)
            for entity_id in self._entity_presets
        }

    def get_entity_state(self, entity_id: str) -> dict[str, Any] | None:
        """Get the current state dict for an underlying entity."""
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

    def setup_state_listeners(self) -> None:
        """Set up state change listeners for underlying entities."""
        entity_ids = [e[CONF_ENTITY_ID] for e in self.entity_configs]

        @callback
        def _async_state_changed(event: Event) -> None:
            """Handle state change of an underlying entity."""
            if self._thermostat_entity is not None:
                self._thermostat_entity.async_schedule_update_ha_state()

        for entity_id in entity_ids:
            remove_tracker = async_track_state_change_event(
                self.hass, entity_ids, _async_state_changed
            )
            self._remove_trackers.append(remove_tracker)

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

    entity_configs = entry_data.get(CONF_ENTITIES, [])
    preset_configs = entry_data.get(CONF_PRESET_CONFIGS, {})

    coordinator = MiniSplitThermostatCoordinator(
        hass, entry, entity_configs, preset_configs
    )

    _register_coordinator(coordinator)

    name = entry_data.get(CONF_NAME, entry.entry_id)
    thermostat = MultiZoneMinisplitThermostat(coordinator, name)
    coordinator.set_thermostat_entity(thermostat)

    async_add_entities([thermostat])

    await coordinator.async_initialize()
    coordinator.setup_state_listeners()


class MultiZoneMinisplitThermostat(ClimateEntity):
    """Representation of a multi-zone mini-split thermostat."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
    )
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
        """Return the average current temperature across all entities."""
        temps = []
        for entity_config in self.coordinator.entity_configs:
            entity_id = entity_config[CONF_ENTITY_ID]
            state = self.coordinator.get_entity_state(entity_id)
            if state and state.get("current_temperature") is not None:
                try:
                    temps.append(float(state["current_temperature"]))
                except (ValueError, TypeError):
                    pass
        return mean(temps) if temps else None

    @property
    def target_temperature(self) -> float:
        """Return the average target temperature across all entities."""
        temps = list(self.coordinator.get_all_target_temps().values())
        if not temps:
            return DEFAULT_HEAT_TEMP
        return round(mean(temps), 1)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        return self.coordinator.hvac_mode or HVACMode.HEAT

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity-specific state attributes."""
        attrs: dict[str, Any] = {
            "entity_presets": self.coordinator.entity_presets,
            "entity_target_temps": self.coordinator.get_all_target_temps(),
            "entities": {},
        }

        for entity_config in self.coordinator.entity_configs:
            entity_id = entity_config[CONF_ENTITY_ID]
            state = self.coordinator.get_entity_state(entity_id)
            attrs["entities"][entity_id] = {
                "preset": self.coordinator.entity_presets.get(entity_id),
                "target_temp": self.coordinator.get_target_temp(entity_id),
                "current_state": state,
            }

        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode for all underlying entities."""
        if hvac_mode == HVACMode.OFF:
            # Turn off all underlying entities
            self.coordinator._hvac_mode = HVACMode.OFF
            for entity_config in self.coordinator.entity_configs:
                entity_id = entity_config[CONF_ENTITY_ID]
                await self.hass.services.async_call(
                    "climate",
                    "set_hvac_mode",
                    {"entity_id": entity_id, "hvac_mode": HVACMode.OFF},
                )
        elif hvac_mode in (HVACMode.HEAT, HVACMode.COOL):
            await self.coordinator.async_set_hvac_mode(hvac_mode)
            for entity_config in self.coordinator.entity_configs:
                entity_id = entity_config[CONF_ENTITY_ID]
                await self.hass.services.async_call(
                    "climate",
                    "set_hvac_mode",
                    {"entity_id": entity_id, "hvac_mode": hvac_mode},
                )

        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set temperature.

        For mini-splits, this stores the preference but doesn't directly
        control equipment. The actual target temps are derived from preset
        configurations.
        """
        if ATTR_TEMPERATURE in kwargs:
            self._attr_target_temperature = kwargs[ATTR_TEMPERATURE]
            self.async_write_ha_state()