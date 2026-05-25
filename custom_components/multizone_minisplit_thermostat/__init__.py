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
    ATTR_PRESET,
    ATTR_ZONE,
    CONF_DEFAULT_PRESET,
    CONF_ENTITY_ID,
    CONF_PRESET_CONFIGS,
    CONF_PRIORITY,
    CONF_ZONES,
    DEFAULT_PRIORITY,
    DOMAIN,
    PRESETS,
    SERVICE_SET_ZONE_PRESET,
)
from .coordinator import MiniSplitThermostatCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SELECT, Platform.NUMBER]

# Per-preset temperature configuration schema (shared across all zones)
PRESET_CONFIG_SCHEMA = vol.Schema({
    vol.In(PRESETS): {
        vol.Optional("heat_temp"): vol.Coerce(float),
        vol.Optional("cool_temp"): vol.Coerce(float),
    }
})

# Per-zone configuration schema
ZONE_CONFIG_SCHEMA = vol.Schema({
    vol.Required(CONF_ENTITY_ID): cv.entity_id,
    vol.Optional(CONF_DEFAULT_PRESET, default="comfort"): vol.In(PRESETS),
    vol.Optional(CONF_PRIORITY, default=DEFAULT_PRIORITY): vol.Coerce(int),
})

# Top-level integration schema
INTEGRATION_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_ZONES): vol.All(cv.ensure_list, [ZONE_CONFIG_SCHEMA]),
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
_coordinators: dict[str, MiniSplitThermostatCoordinator] = {}


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_coordinator(coordinator: MiniSplitThermostatCoordinator) -> None:
    """Register a coordinator for service lookups."""
    _coordinators[coordinator.entry_id] = coordinator


def _get_coordinator(entry_id: str) -> MiniSplitThermostatCoordinator | None:
    """Get a registered coordinator by entry ID."""
    return _coordinators.get(entry_id)


def _unregister_coordinator(entry_id: str) -> None:
    """Unregister a coordinator."""
    _coordinators.pop(entry_id, None)


def _find_coordinator_for_zone(entity_id: str) -> MiniSplitThermostatCoordinator | None:
    """Find the coordinator that manages a given underlying zone entity."""
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
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Merge entry.options (from reconfiguration) with entry.data (from initial setup)
    merged_data = {**entry.data, **entry.options}
    zone_configs = merged_data.get(CONF_ZONES, [])
    preset_configs = merged_data.get(CONF_PRESET_CONFIGS, {})

    coordinator = MiniSplitThermostatCoordinator(
        hass=hass,
        entry=entry,
        zone_configs=zone_configs,
        preset_configs=preset_configs,
    )
    _register_coordinator(coordinator)
    coordinator.setup_state_listeners()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = _get_coordinator(entry.entry_id)
        if coordinator:
            coordinator.cleanup()
        _unregister_coordinator(entry.entry_id)
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services (called once from async_setup)."""

    async def async_set_zone_preset(call: ServiceCall) -> None:
        """Set the preset for a specific underlying zone."""
        target_zone = call.data[ATTR_ZONE]
        preset = call.data[ATTR_PRESET]

        coordinator = _find_coordinator_for_zone(target_zone)
        if coordinator is None:
            _LOGGER.warning(
                "Zone %s is not managed by any %s thermostat",
                target_zone,
                DOMAIN,
            )
            return

        coordinator.set_entity_preset(target_zone, preset)
        await coordinator.async_check_and_update_mode()
        coordinator.async_request_ha_state_update()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ZONE_PRESET,
        async_set_zone_preset,
        schema=vol.Schema({
            vol.Required(ATTR_ZONE): cv.entity_id,
            vol.Required(ATTR_PRESET): vol.In(PRESETS),
        }),
    )
