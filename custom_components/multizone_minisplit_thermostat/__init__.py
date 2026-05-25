"""Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ENTITY,
    ATTR_PRESET,
    CONF_DEFAULT_PRESET,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_PRESET_CONFIGS,
    DOMAIN,
    PRESETS,
    SERVICE_SET_ENTITY_PRESET,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE]

# Per-preset temperature configuration schema (shared across all entities)
PRESET_CONFIG_SCHEMA = vol.Schema({
    vol.In(PRESETS): {
        vol.Optional("heat_temp"): vol.Coerce(float),
        vol.Optional("cool_temp"): vol.Coerce(float),
    }
})

# Per-entity configuration schema
ENTITY_CONFIG_SCHEMA = vol.Schema({
    vol.Required(CONF_ENTITY_ID): cv.entity_id,
    vol.Optional(CONF_DEFAULT_PRESET, default="comfort"): vol.In(PRESETS),
})

# Top-level integration schema
INTEGRATION_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_ENTITIES): vol.All(cv.ensure_list, [ENTITY_CONFIG_SCHEMA]),
    vol.Optional(CONF_PRESET_CONFIGS, default={}): PRESET_CONFIG_SCHEMA,
})

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            cv.slug: INTEGRATION_SCHEMA,
        })
    },
    extra=vol.ALLOW_EXTRA,
)

# Store coordinators for service lookup
_coordinators: dict[str, "MiniSplitThermostatCoordinator"] = {}


def _register_coordinator(coordinator: "MiniSplitThermostatCoordinator") -> None:
    """Register a coordinator for service lookups."""
    _coordinators[coordinator.entry_id] = coordinator


def _unregister_coordinator(entry_id: str) -> None:
    """Unregister a coordinator."""
    _coordinators.pop(entry_id, None)


def _find_coordinator_for_entity(entity_id: str) -> "MiniSplitThermostatCoordinator | None":
    """Find the coordinator that manages a given underlying entity."""
    for coordinator in _coordinators.values():
        if entity_id in coordinator.entity_presets:
            return coordinator
    return None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Multi-Zone Mini-Split Thermostat integration from YAML."""
    if DOMAIN not in config:
        return True

    for entry_id, entry_config in config[DOMAIN].items():
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data={
                    "entry_id": entry_id,
                    **entry_config,
                },
            )
        )

    # Register services once at the integration level
    _async_register_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Multi-Zone Mini-Split Thermostat from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        _unregister_coordinator(entry.entry_id)
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services (called once from async_setup)."""

    async def async_set_entity_preset(call: ServiceCall) -> None:
        """Set the preset for a specific underlying entity."""
        target_entity = call.data[ATTR_ENTITY]
        preset = call.data[ATTR_PRESET]

        coordinator = _find_coordinator_for_entity(target_entity)
        if coordinator is None:
            _LOGGER.warning(
                "Entity %s is not managed by any %s thermostat",
                target_entity,
                DOMAIN,
            )
            return

        coordinator.set_entity_preset(target_entity, preset)
        # Trigger HA state update for the thermostat entity
        coordinator.async_request_ha_state_update()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ENTITY_PRESET,
        async_set_entity_preset,
        schema=vol.Schema({
            vol.Required(ATTR_ENTITY): cv.entity_id,
            vol.Required(ATTR_PRESET): vol.In(PRESETS),
        }),
    )
