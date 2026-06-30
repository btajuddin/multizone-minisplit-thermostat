"""Sensor platform for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENTITY_ID, DOMAIN
from .coordinator import MiniSplitThermostatCoordinator

SENSOR_ENTITY_ID_FORMAT = "sensor.{}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    from . import _get_coordinator

    coordinator = _get_coordinator(entry.entry_id)
    if coordinator is None:
        return

    entities = []
    for zone_config in coordinator.zone_configs:
        entity_id = zone_config[CONF_ENTITY_ID]
        sensor = ActualSetpointSensor(coordinator, entity_id)
        coordinator.add_sensor_entity(sensor)
        entities.append(sensor)

    async_add_entities(entities)


class ActualSetpointSensor(SensorEntity):
    """Sensor entity for the most recent setpoint pushed to a zone."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT

    def __init__(
        self, coordinator: MiniSplitThermostatCoordinator, entity_id: str
    ) -> None:
        """Initialize the sensor entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id
        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Actual Setpoint"
        self._attr_unique_id = f"{coordinator.entry_id}_actual_setpoint_{entity_id}"
        self.entity_id = async_generate_entity_id(
            SENSOR_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_actual_setpoint",
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
    def native_value(self) -> float:
        """Return the current actual setpoint."""
        return self.coordinator.get_actual_setpoint(self._entity_id)
