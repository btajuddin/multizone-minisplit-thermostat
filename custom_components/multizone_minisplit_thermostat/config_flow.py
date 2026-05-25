"""Config flow for Multi-Zone Mini-Split Thermostat integration."""

from __future__ import annotations

from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import selector

from .const import (
    CONF_DEFAULT_PRESET,
    CONF_ENTITY_ID,
    CONF_PRESET_CONFIGS,
    CONF_PRIORITY,
    CONF_ZONES,
    DEFAULT_PRIORITY,
    DOMAIN,
    PRESETS,
)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): str,
})

STEP_ADD_ZONE_SCHEMA = vol.Schema({
    vol.Required(CONF_ENTITY_ID): selector({"entity": {"domain": "climate"}}),
    vol.Optional(CONF_DEFAULT_PRESET, default="comfort"): selector({
        "select": {"options": PRESETS}
    }),
    vol.Optional(CONF_PRIORITY, default=DEFAULT_PRIORITY): selector({
        "number": {"min": 0, "max": 100, "step": 1, "mode": "box"}
    }),
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
                CONF_PRIORITY: user_input.get(CONF_PRIORITY, DEFAULT_PRIORITY),
            }
            self._zones.append(zone_config)

            return self.async_show_form(
                step_id="add_zone_confirm",
                data_schema=vol.Schema({
                    vol.Optional("add_another", default=False): selector({"boolean": {}}),
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
                CONF_NAME: self._name or "Multi-Zone Thermostat",
                CONF_ZONES: self._zones,
                CONF_PRESET_CONFIGS: self._preset_configs,
            },
        )

    @staticmethod
    @config_entries.HANDLERS.register(DOMAIN)
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> MultizoneMinisplitThermostatOptionsFlowHandler:
        """Get the options flow for this handler."""
        return MultizoneMinisplitThermostatOptionsFlowHandler()


class MultizoneMinisplitThermostatOptionsFlowHandler(
    config_entries.OptionsFlow,
):
    """Handle options flow for reconfiguring the integration."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._zones: list[dict[str, Any]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        return await self.async_step_manage_zones()

    async def async_step_manage_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage zones - show summary and actions."""
        merged = {**self.config_entry.data, **self.config_entry.options}
        if not self._zones:
            self._zones = [dict(z) for z in merged.get(CONF_ZONES, [])]

        errors: dict[str, str] = {}
        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                return await self.async_step_add_zone()
            elif action == "remove":
                return await self.async_step_remove_zone()
            return await self.async_step_finalize()

        # Build zone summary for description
        zone_names = []
        for zone in self._zones:
            entity_id = zone[CONF_ENTITY_ID]
            friendly = entity_id.split(".")[-1].replace("_", " ").title()
            zone_names.append(f"- {friendly}")
        zone_summary = "\n".join(zone_names) if zone_names else "No zones configured"

        return self.async_show_form(
            step_id="manage_zones",
            data_schema=vol.Schema({
                vol.Required("action"): selector({
                    "select": {
                        "options": [
                            {"value": "add", "label": "Add a zone"},
                            {"value": "remove", "label": "Remove a zone"},
                            {"value": "done", "label": "Done"},
                        ],
                    }
                }),
            }),
            description_placeholders={
                "zone_count": str(len(self._zones)),
                "zones": zone_summary,
            },
            errors=errors,
        )

    async def async_step_add_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new zone."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input[CONF_ENTITY_ID]
            if entity_id in [z[CONF_ENTITY_ID] for z in self._zones]:
                errors[CONF_ENTITY_ID] = "already_added"
            else:
                zone_config = {
                    CONF_ENTITY_ID: entity_id,
                    CONF_DEFAULT_PRESET: user_input.get(CONF_DEFAULT_PRESET, "comfort"),
                    CONF_PRIORITY: user_input.get(CONF_PRIORITY, DEFAULT_PRIORITY),
                }
                self._zones.append(zone_config)
                return await self.async_step_manage_zones()

        return self.async_show_form(
            step_id="add_zone",
            data_schema=STEP_ADD_ZONE_SCHEMA,
            errors=errors,
        )

    async def async_step_remove_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a zone."""
        if user_input is not None:
            index = user_input.get("zone_index")
            if index is not None and 0 <= index < len(self._zones):
                removed = self._zones.pop(int(index))
            return await self.async_step_manage_zones()

        zone_options = {}
        for i, zone in enumerate(self._zones):
            entity_id = zone[CONF_ENTITY_ID]
            friendly = entity_id.split(".")[-1].replace("_", " ").title()
            zone_options[str(i)] = friendly

        return self.async_show_form(
            step_id="remove_zone",
            data_schema=vol.Schema({
                vol.Required("zone_index"): vol.In(zone_options),
            }),
        )

    async def async_step_finalize(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Finalize and save options."""
        return self.async_create_entry(
            data={
                CONF_ZONES: self._zones,
            },
        )
