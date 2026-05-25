"""Config flow for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DEFAULT_PRESET,
    CONF_ENTITY_ID,
    CONF_PRESET_CONFIGS,
    CONF_ZONES,
    DOMAIN,
    PRESETS,
)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): str,
})

STEP_ADD_ZONE_SCHEMA = vol.Schema({
    vol.Required(CONF_ENTITY_ID): str,
    vol.Optional(CONF_DEFAULT_PRESET, default="comfort"): vol.In(PRESETS),
})


class MultizoneMinisplitThermostatFlowHandler(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for Multi-Zone Mini-Split Thermostat."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._name: str | None = None
        self._entry_id: str | None = None
        self._zones: list[dict[str, Any]] = []
        self._preset_configs: dict[str, dict[str, float]] = {}

    async def async_step_import(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle YAML import."""
        if user_input is None:
            return self.async_abort(reason="invalid_config")

        entry_id = user_input.pop("entry_id", None)
        if entry_id:
            await self.async_set_unique_id(entry_id)
            self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=user_input.get(CONF_NAME, entry_id or "Multi-Zone Thermostat"),
            data=user_input,
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._name = user_input[CONF_NAME]
            self._entry_id = str(uuid.uuid4())
            await self.async_set_unique_id(self._entry_id)
            self._abort_if_unique_id_configured()

            self._zones = []
            self._preset_configs = {}
            return await self.async_step_preset_config()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_preset_config(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure global preset temperatures."""
        errors: dict[str, str] = {}

        if user_input is not None:
            for preset in PRESETS:
                self._preset_configs[preset] = {}
                heat = user_input.get(f"{preset}_heat_temp")
                cool = user_input.get(f"{preset}_cool_temp")
                if heat is not None:
                    self._preset_configs[preset]["heat_temp"] = heat
                if cool is not None:
                    self._preset_configs[preset]["cool_temp"] = cool

            return await self.async_step_add_zone()

        # Build schema with optional temp fields for each preset
        schema_dict = {}
        for preset in PRESETS:
            schema_dict[vol.Optional(f"{preset}_heat_temp")] = vol.Coerce(float)
            schema_dict[vol.Optional(f"{preset}_cool_temp")] = vol.Coerce(float)

        return self.async_show_form(
            step_id="preset_config",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={"presets": ", ".join(PRESETS)},
        )

    async def async_step_add_zone(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle adding a zone to the thermostat group."""
        errors: dict[str, str] = {}

        if user_input is not None:
            zone_config = {
                CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
                CONF_DEFAULT_PRESET: user_input.get(CONF_DEFAULT_PRESET, "comfort"),
            }
            self._zones.append(zone_config)

            return self.async_show_form(
                step_id="add_zone_confirm",
                data_schema=vol.Schema({
                    vol.Optional("add_another", default=False): bool,
                }),
            )

        return self.async_show_form(
            step_id="add_zone",
            data_schema=STEP_ADD_ZONE_SCHEMA,
            errors=errors,
        )

    async def async_step_add_zone_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle confirmation of adding another zone."""
        if user_input and user_input.get("add_another"):
            return await self.async_step_add_zone()

        return await self.async_step_finalize()

    async def async_step_finalize(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Finalize the config entry."""
        return self.async_create_entry(
            title=self._name or "Multi-Zone Thermostat",
            data={
                CONF_NAME: self._name,
                CONF_ZONES: self._zones,
                CONF_PRESET_CONFIGS: self._preset_configs,
            },
        )
