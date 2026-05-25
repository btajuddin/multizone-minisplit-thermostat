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
    CONF_ENTITY_ID,
    CONF_PRESET_CONFIGS,
    CONF_ZONES,
    DEFAULT_COOL_TEMP,
    DEFAULT_HEAT_TEMP,
    DOMAIN,
    PRESET_COMFORT,
    PRESETS,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = DOMAIN + ".{}"


class MiniSplitThermostatCoordinator:
    """Coordinator for managing state across multiple mini-split zones.

    Preset temperature configurations (heat_temp/cool_temp per preset) are
    shared across all zones. Each zone tracks which preset is currently
    active independently.
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
        self._thermostat_entity: MultiZoneMinisplitThermostat | None = None
        self._select_entities: list["ZonePresetSelect"] = []
        self._remove_trackers: list[CALLBACK_TYPE] = []

        # Initialize default presets from config
        for zone_config in zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            self._zone_presets[entity_id] = zone_config.get(
                "default_preset", PRESET_COMFORT
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

    def _notify_state_changed(self) -> None:
        """Notify all registered entities that state has changed."""
        if self._thermostat_entity is not None:
            self._thermostat_entity.async_write_ha_state()
        for select_entity in self._select_entities:
            select_entity.async_write_ha_state()

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
        self._notify_state_changed()

    async def async_set_hvac_mode(self, mode: HVACMode) -> None:
        """Set the HVAC mode for all underlying zones."""
        if mode not in (HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF):
            _LOGGER.warning("Unsupported HVAC mode: %s", mode)
            return
        self._hvac_mode = mode
        self._notify_state_changed()

    def get_target_temp(self, entity_id: str) -> float:
        """Get the target temperature for a zone based on its preset and current mode."""
        preset = self._zone_presets.get(entity_id, PRESET_COMFORT)
        preset_config = self._preset_configs.get(preset, {})

        if self._hvac_mode == HVACMode.HEAT:
            return preset_config.get("heat_temp", DEFAULT_HEAT_TEMP)
        else:
            return preset_config.get("cool_temp", DEFAULT_COOL_TEMP)

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

    def setup_state_listeners(self) -> None:
        """Set up state change listeners for underlying zones."""
        entity_ids = [z[CONF_ENTITY_ID] for z in self.zone_configs]

        @callback
        def _async_state_changed(event: Any) -> None:
            """Handle state change of an underlying zone."""
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
                "preset": self.coordinator.entity_presets.get(entity_id),
                "target_temp": self.coordinator.get_target_temp(entity_id),
                "current_state": state,
            }

        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode for all underlying zones."""
        await self.coordinator.async_set_hvac_mode(hvac_mode)

        for zone_config in self.coordinator.zone_configs:
            entity_id = zone_config[CONF_ENTITY_ID]
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": hvac_mode},
            )
