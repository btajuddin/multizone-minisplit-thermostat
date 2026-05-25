"""Select platform for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import _get_coordinator
from .climate import MiniSplitThermostatCoordinator
from .const import (
    CONF_DEFAULT_PRESET,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    DOMAIN,
    PRESETS,
)

SELECT_ENTITY_ID_FORMAT = DOMAIN + "_preset_{}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    coordinator = _get_coordinator(entry.entry_id)
    if coordinator is None:
        return

    entities = []
    for entity_config in entry.data.get(CONF_ENTITIES, []):
        underlying_entity_id = entity_config[CONF_ENTITY_ID]
        default_preset = entity_config.get(CONF_DEFAULT_PRESET, "comfort")

        select_entity = ZonePresetSelect(
            coordinator=coordinator,
            underlying_entity_id=underlying_entity_id,
            default_preset=default_preset,
            thermostat_name=entry.data.get(CONF_NAME, entry.entry_id),
        )
        coordinator.add_select_entity(select_entity)
        entities.append(select_entity)

    async_add_entities(entities)


class ZonePresetSelect(SelectEntity):
    """Select entity for controlling the preset of a single zone."""

    _attr_has_entity_name = True
    _attr_options = PRESETS

    def __init__(
        self,
        coordinator: MiniSplitThermostatCoordinator,
        underlying_entity_id: str,
        default_preset: str,
        thermostat_name: str,
    ) -> None:
        """Initialize the select entity."""
        self.coordinator = coordinator
        self._underlying_entity_id = underlying_entity_id

        friendly_part = underlying_entity_id.split(".", 1)[-1].replace("_", " ").title()
        self._attr_name = f"{thermostat_name} - {friendly_part} Preset"
        self._attr_unique_id = f"{coordinator.entry_id}_preset_{underlying_entity_id}"
        self.entity_id = async_generate_entity_id(
            SELECT_ENTITY_ID_FORMAT,
            f"{thermostat_name}_{underlying_entity_id}",
            hass=coordinator.hass,
        )
        self._attr_current_option = default_preset

    @property
    def current_option(self) -> str | None:
        """Return the current preset for this zone."""
        return self.coordinator.entity_presets.get(self._underlying_entity_id)

    def select_option(self, option: str) -> None:
        """Change the selected preset for this zone."""
        self.coordinator.set_entity_preset(self._underlying_entity_id, option)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return zone-specific attributes."""
        target_temps = self.coordinator.get_all_target_temps()
        return {
            "underlying_entity": self._underlying_entity_id,
            "target_temperature": target_temps.get(self._underlying_entity_id),
        }
