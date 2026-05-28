"""Switch platform for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

SWITCH_ENTITY_ID_FORMAT = "switch.{}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    from . import _get_coordinator

    coordinator = _get_coordinator(entry.entry_id)
    if coordinator is None:
        return

    # Only create switch if offset learning is configured (outside temp entity set)
    if coordinator.outside_temp_entity is None:
        return

    async_add_entities([OffsetLearningSwitch(coordinator)])


class OffsetLearningSwitch(SwitchEntity):
    """Switch entity to enable/disable offset learning."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
    ) -> None:
        """Initialize the switch entity."""
        self.coordinator = coordinator

        self._attr_name = "Offset Learning"
        self._attr_unique_id = f"{coordinator.entry_id}_offset_learning_enable"
        self.entity_id = async_generate_entity_id(
            SWITCH_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_offset_learning",
            hass=coordinator.hass,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=coordinator.entry_name,
            manufacturer="Multi-Zone Mini-Split Thermostat",
            model="Virtual Thermostat",
        )

    @property
    def is_on(self) -> bool:
        """Return whether offset learning is enabled."""
        return self.coordinator.offset_learning_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Enable offset learning."""
        await self.coordinator.async_set_offset_learning_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable offset learning."""
        await self.coordinator.async_set_offset_learning_enabled(False)
