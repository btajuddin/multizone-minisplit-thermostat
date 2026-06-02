"""Number platform for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEBOUNCE_INTERVAL,
    CONF_DEBOUNCE_THRESHOLD,
    CONF_ENTITY_ID,
    CONF_MINISPLIT_RUNNING_THRESHOLD,
    CONF_PRIORITY,
    CONF_ZONES,
    DEFAULT_DEBOUNCE_INTERVAL,
    DEFAULT_DEBOUNCE_THRESHOLD,
    DEFAULT_MINISPLIT_RUNNING_THRESHOLD,
    DEFAULT_PRIORITY,
    DOMAIN,
    PRESETS,
)
from .coordinator import MiniSplitThermostatCoordinator

NUMBER_ENTITY_ID_FORMAT = "number.{}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    from . import _get_coordinator

    coordinator = _get_coordinator(entry.entry_id)
    if coordinator is None:
        return

    entities = []

    # Create preset temperature numbers
    for preset in PRESETS:
        for mode in ("heat", "cool"):
            number_entity = PresetTemperatureNumber(
                coordinator=coordinator,
                preset=preset,
                mode=mode,
            )
            coordinator.add_number_entity(number_entity)
            entities.append(number_entity)

    # Create zone priority numbers
    for zone_config in coordinator.zone_configs:
        entity_id = zone_config[CONF_ENTITY_ID]
        priority_entity = ZonePriorityNumber(
            coordinator=coordinator,
            entity_id=entity_id,
        )
        coordinator.add_number_entity(priority_entity)
        entities.append(priority_entity)

    # Create debounce configuration entities (global)
    debounce_interval_entity = DebounceIntervalNumber(coordinator=coordinator)
    coordinator.add_number_entity(debounce_interval_entity)
    entities.append(debounce_interval_entity)

    debounce_threshold_entity = DebounceThresholdNumber(coordinator=coordinator)
    coordinator.add_number_entity(debounce_threshold_entity)
    entities.append(debounce_threshold_entity)

    # Create running threshold configuration entity (global)
    running_threshold_entity = RunningThresholdNumber(coordinator=coordinator)
    coordinator.add_number_entity(running_threshold_entity)
    entities.append(running_threshold_entity)

    async_add_entities(entities)


class PresetTemperatureNumber(NumberEntity):
    """Number entity for controlling a preset's target temperature."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _attr_native_min_value = 40.0
    _attr_native_max_value = 95.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: MiniSplitThermostatCoordinator,
        preset: str,
        mode: str,
    ) -> None:
        """Initialize the number entity."""
        self.coordinator = coordinator
        self._preset = preset
        self._mode = mode

        # Create friendly name like "Comfort Heating Target"
        mode_label = "Heating" if mode == "heat" else "Cooling"
        preset_label = preset.title()
        self._attr_name = f"{preset_label} {mode_label} Target"
        self._attr_unique_id = f"{coordinator.entry_id}_{preset}_{mode}_temp"
        self.entity_id = async_generate_entity_id(
            NUMBER_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{preset}_{mode}_target",
            hass=coordinator.hass,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=coordinator.entry_name,
            manufacturer="Multi-Zone Mini-Split Thermostat",
            model="Virtual Thermostat",
        )

    @property
    def native_value(self) -> float:
        """Return the current target temperature."""
        return self.coordinator.get_preset_temp(self._preset, self._mode)

    async def async_set_native_value(self, value: float) -> None:
        """Update the target temperature."""
        await self.coordinator.async_set_preset_temp(self._preset, self._mode, value)


class ZonePriorityNumber(NumberEntity):
    """Number entity for controlling a zone's priority."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: MiniSplitThermostatCoordinator,
        entity_id: str,
    ) -> None:
        """Initialize the priority number entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        # Create friendly name like "Office Priority"
        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Priority"
        self._attr_unique_id = f"{coordinator.entry_id}_priority_{entity_id}"
        self.entity_id = async_generate_entity_id(
            "number.{}",
            f"{coordinator.entry_name}_{zone_name}_priority",
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
        """Return the current priority."""
        return self.coordinator.get_zone_priority(self._entity_id)

    async def async_set_native_value(self, value: float) -> None:
        """Update the priority."""
        await self.coordinator.async_set_zone_priority(self._entity_id, int(value))


class DebounceIntervalNumber(NumberEntity):
    """Number entity for controlling the debounce interval (seconds)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 60
    _attr_native_max_value = 3600
    _attr_native_step = 60
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "s"

    def __init__(
        self,
        coordinator: MiniSplitThermostatCoordinator,
    ) -> None:
        """Initialize the debounce interval number entity."""
        self.coordinator = coordinator

        self._attr_name = "Debounce Interval"
        self._attr_unique_id = f"{coordinator.entry_id}_debounce_interval"
        self.entity_id = async_generate_entity_id(
            NUMBER_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_debounce_interval",
            hass=coordinator.hass,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=coordinator.entry_name,
            manufacturer="Multi-Zone Mini-Split Thermostat",
            model="Virtual Thermostat",
        )

    @property
    def native_value(self) -> int:
        """Return the current debounce interval."""
        return self.coordinator._debounce_interval

    async def async_set_native_value(self, value: float) -> None:
        """Update the debounce interval."""
        self.coordinator._debounce_interval = int(value)
        self.coordinator._notify_state_changed()


class DebounceThresholdNumber(NumberEntity):
    """Number entity for controlling the debounce threshold (degrees F)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0.1
    _attr_native_max_value = 5.0
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT

    def __init__(
        self,
        coordinator: MiniSplitThermostatCoordinator,
    ) -> None:
        """Initialize the debounce threshold number entity."""
        self.coordinator = coordinator

        self._attr_name = "Debounce Threshold"
        self._attr_unique_id = f"{coordinator.entry_id}_debounce_threshold"
        self.entity_id = async_generate_entity_id(
            NUMBER_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_debounce_threshold",
            hass=coordinator.hass,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=coordinator.entry_name,
            manufacturer="Multi-Zone Mini-Split Thermostat",
            model="Virtual Thermostat",
        )

    @property
    def native_value(self) -> float:
        """Return the current debounce threshold."""
        return self.coordinator._debounce_threshold

    async def async_set_native_value(self, value: float) -> None:
        """Update the debounce threshold."""
        self.coordinator._debounce_threshold = value
        self.coordinator._notify_state_changed()


class RunningThresholdNumber(NumberEntity):
    """Number entity for controlling the minisplit running detection threshold (°F/min)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0.01
    _attr_native_max_value = 1.0
    _attr_native_step = 0.01
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "°F/min"

    def __init__(
        self,
        coordinator: MiniSplitThermostatCoordinator,
    ) -> None:
        """Initialize the running threshold number entity."""
        self.coordinator = coordinator

        self._attr_name = "Running Threshold"
        self._attr_unique_id = f"{coordinator.entry_id}_running_threshold"
        self.entity_id = async_generate_entity_id(
            NUMBER_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_running_threshold",
            hass=coordinator.hass,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=coordinator.entry_name,
            manufacturer="Multi-Zone Mini-Split Thermostat",
            model="Virtual Thermostat",
        )

    @property
    def native_value(self) -> float:
        """Return the current running threshold."""
        return self.coordinator._minisplit_running_threshold

    async def async_set_native_value(self, value: float) -> None:
        """Update the running threshold."""
        await self.coordinator.async_set_minisplit_running_threshold(value)
