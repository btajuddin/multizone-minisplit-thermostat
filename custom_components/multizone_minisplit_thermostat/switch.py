"""Switch platform for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENTITY_ID, DOMAIN

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

    # Only create switches if offset learning is configured (outside temp entity set)
    if coordinator.outside_temp_entity is None:
        return

    entities = []
    for zone_config in coordinator.zone_configs:
        entity_id = zone_config[CONF_ENTITY_ID]
        entities.append(ZoneOffsetLearningSwitch(coordinator, entity_id))

    async_add_entities(entities)


class ZoneOffsetLearningSwitch(SwitchEntity):
    """Switch entity to enable/disable offset learning for a specific zone."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        entity_id: str,
    ) -> None:
        """Initialize the switch entity."""
        self.coordinator = coordinator
        self._entity_id = entity_id

        zone_name = entity_id.split(".")[-1].replace("_", " ").title()
        self._attr_name = f"{zone_name} Offset Learning"
        self._attr_unique_id = f"{coordinator.entry_id}_offset_learning_{entity_id}"
        self.entity_id = async_generate_entity_id(
            SWITCH_ENTITY_ID_FORMAT,
            f"{coordinator.entry_name}_{zone_name}_offset_learning",
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
        """Return whether offset learning is enabled for this zone."""
        return self.coordinator._zone_offset_learning_enabled.get(self._entity_id, True)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable offset learning for this zone."""
        await self.coordinator.async_set_zone_offset_learning_enabled(self._entity_id, True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable offset learning for this zone."""
        await self.coordinator.async_set_zone_offset_learning_enabled(self._entity_id, False)
