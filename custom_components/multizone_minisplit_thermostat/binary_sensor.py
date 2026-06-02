"""Binary sensor platform for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENTITY_ID, CONF_QUIET_MODE_ENTITY, DOMAIN

BINARY_SENSOR_ENTITY_ID_FORMAT = "binary_sensor.{}"
BINARY_SENSOR_ENTITY_ID_FORMAT_RUNNING = "binary_sensor.{}"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    from . import _get_coordinator

    coordinator = _get_coordinator(entry.entry_id)
    if coordinator is None:
        return

    entities = []

    for zone_config in coordinator.zone_configs:
        entity_id = zone_config[CONF_ENTITY_ID]
        # Only create the diagnostic entity if a quiet mode entity is configured
        if zone_config.get(CONF_QUIET_MODE_ENTITY):
            entities.append(QuietModeBinarySensor(coordinator, entity_id))

        # Always create the minisplit running diagnostic entity
        entities.append(MinisplitRunningBinarySensor(coordinator, entity_id))

    async_add_entities(entities)


class QuietModeBinarySensor(BinarySensorEntity):
    """Binary sensor entity indicating whether quiet mode is active for a zone."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator,
        entity_id: str,
    ) -> None:
        """Initialize the binary sensor entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Quiet Mode"
        self._attr_unique_id = f"{coordinator.entry_id}_quiet_mode_{entity_id}"
        self.entity_id = async_generate_entity_id(
            BINARY_SENSOR_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_quiet_mode",
            hass=coordinator.hass,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry_id}_zone_{entity_id}")},
            name=f"{coordinator.entry_name} - {zone_name}",
            manufacturer="Multi-Zone Mini-Split Thermostat",
            model="Zone Controller",
            via_device=(DOMAIN, coordinator.entry_id),
        )

    @property
    def is_on(self) -> bool:
        """Return True if quiet mode is active."""
        return self.coordinator.is_quiet_mode_active(self._entity_id)


class MinisplitRunningBinarySensor(BinarySensorEntity):
    """Binary sensor indicating whether the minisplit is running for a zone."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator,
        entity_id: str,
    ) -> None:
        """Initialize the binary sensor entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Minisplit Running"
        self._attr_unique_id = f"{coordinator.entry_id}_minisplit_running_{entity_id}"
        self.entity_id = async_generate_entity_id(
            BINARY_SENSOR_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_minisplit_running",
            hass=coordinator.hass,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry_id}_zone_{entity_id}")},
            name=f"{coordinator.entry_name} - {zone_name}",
            manufacturer="Multi-Zone Mini-Split Thermostat",
            model="Zone Controller",
            via_device=(DOMAIN, coordinator.entry_id),
        )

    @property
    def is_on(self) -> bool:
        """Return True if the minisplit is detected as running."""
        return self.coordinator.is_minisplit_running(self._entity_id)
