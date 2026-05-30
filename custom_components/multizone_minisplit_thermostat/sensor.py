"""Sensor platform for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENTITY_ID, DOMAIN

SENSOR_ENTITY_ID_FORMAT = "sensor.{}"

_LOGGER = logging.getLogger(__name__)


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

    # Only create sensors if offset learning is initialized
    if not coordinator.offset_learners:
        _LOGGER.debug("No offset learners initialized, skipping sensor platform")
        return

    entities = []

    for zone_config in coordinator.zone_configs:
        entity_id = zone_config[CONF_ENTITY_ID]
        if entity_id in coordinator.offset_learners:
            entities.append(OffsetSensor(coordinator, entity_id))
            entities.append(OffsetSampleCountSensor(coordinator, entity_id))
            entities.append(OffsetLearnerSlopeSensor(coordinator, entity_id))
            entities.append(OffsetLearnerInterceptSensor(coordinator, entity_id))
            entities.append(OffsetLearnerModelStatusSensor(coordinator, entity_id))
            entities.append(OffsetLearnerLastCalculationSensor(coordinator, entity_id))

    async_add_entities(entities)


class OffsetSensor(SensorEntity):
    """Sensor entity for the current learned offset for a zone."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT

    def __init__(
        self,
        coordinator,
        entity_id: str,
    ) -> None:
        """Initialize the sensor entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Learned Offset"
        self._attr_unique_id = f"{coordinator.entry_id}_offset_{entity_id}"
        self.entity_id = async_generate_entity_id(
            SENSOR_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_learned_offset",
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
        """Return the current learned offset."""
        return self.coordinator.current_offsets.get(self._entity_id, 0.0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        learner = self.coordinator.offset_learners.get(self._entity_id)
        if learner is None:
            return {}

        model_info = learner.get_model_info()
        attrs = {
            "sample_count": model_info.get("sample_count", 0),
            "has_model": model_info.get("has_model", False),
        }

        if model_info.get("has_model"):
            attrs["slope"] = round(model_info.get("slope", 0.0), 4)
            attrs["intercept"] = round(model_info.get("intercept", 0.0), 4)

        last_calc = model_info.get("last_calculation")
        if last_calc:
            attrs["last_calculation"] = datetime.fromtimestamp(last_calc).isoformat()

        return attrs


class OffsetSampleCountSensor(SensorEntity):
    """Sensor entity for the number of data points in the learning window."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "samples"

    def __init__(
        self,
        coordinator,
        entity_id: str,
    ) -> None:
        """Initialize the sensor entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Offset Samples"
        self._attr_unique_id = f"{coordinator.entry_id}_offset_samples_{entity_id}"
        self.entity_id = async_generate_entity_id(
            SENSOR_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_offset_samples",
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
    def native_value(self) -> int:
        """Return the number of data points."""
        learner = self.coordinator.offset_learners.get(self._entity_id)
        if learner is None:
            return 0
        return learner.get_sample_count()


class OffsetLearnerSlopeSensor(SensorEntity):
    """Sensor entity for the slope coefficient of the offset learner."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        entity_id: str,
    ) -> None:
        """Initialize the sensor entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Offset Slope"
        self._attr_unique_id = f"{coordinator.entry_id}_offset_slope_{entity_id}"
        self.entity_id = async_generate_entity_id(
            SENSOR_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_offset_slope",
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
    def native_value(self) -> float | None:
        """Return the slope coefficient."""
        learner = self.coordinator.offset_learners.get(self._entity_id)
        if learner is None:
            return None
        model_info = learner.get_model_info()
        return round(model_info.get("slope", 0.0), 4)


class OffsetLearnerInterceptSensor(SensorEntity):
    """Sensor entity for the intercept coefficient of the offset learner."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        entity_id: str,
    ) -> None:
        """Initialize the sensor entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Offset Intercept"
        self._attr_unique_id = f"{coordinator.entry_id}_offset_intercept_{entity_id}"
        self.entity_id = async_generate_entity_id(
            SENSOR_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_offset_intercept",
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
    def native_value(self) -> float | None:
        """Return the intercept coefficient."""
        learner = self.coordinator.offset_learners.get(self._entity_id)
        if learner is None:
            return None
        model_info = learner.get_model_info()
        return round(model_info.get("intercept", 0.0), 4)


class OffsetLearnerModelStatusSensor(SensorEntity):
    """Sensor entity for the model fitting status of the offset learner."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator,
        entity_id: str,
    ) -> None:
        """Initialize the sensor entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Offset Model Status"
        self._attr_unique_id = f"{coordinator.entry_id}_offset_model_status_{entity_id}"
        self.entity_id = async_generate_entity_id(
            SENSOR_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_offset_model_status",
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
    def native_value(self) -> str | None:
        """Return the model fitting status."""
        learner = self.coordinator.offset_learners.get(self._entity_id)
        if learner is None:
            return None
        model_info = learner.get_model_info()
        if model_info.get("has_model"):
            return "Fitted"
        return "Not Fitted"


class OffsetLearnerLastCalculationSensor(SensorEntity):
    """Sensor entity for the timestamp of the last model calculation."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator,
        entity_id: str,
    ) -> None:
        """Initialize the sensor entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Offset Last Calculation"
        self._attr_unique_id = f"{coordinator.entry_id}_offset_last_calc_{entity_id}"
        self.entity_id = async_generate_entity_id(
            SENSOR_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_offset_last_calculation",
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
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last model calculation."""
        learner = self.coordinator.offset_learners.get(self._entity_id)
        if learner is None:
            return None
        model_info = learner.get_model_info()
        last_calc = model_info.get("last_calculation", 0.0)
        if last_calc > 0:
            return datetime.fromtimestamp(last_calc)
        return None
