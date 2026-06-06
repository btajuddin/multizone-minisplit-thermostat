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
    CONF_DEBOUNCE_INTERVAL,
    CONF_DEBOUNCE_THRESHOLD,
    CONF_ENABLE_OFFSET_LEARNING,
    CONF_ENTITY_ID,
    CONF_MINISPLIT_RUNNING_THRESHOLD,
    CONF_OUTSIDE_TEMP_ENTITY,
    CONF_PRESET_CONFIGS,
    CONF_PRIORITY,
    CONF_QUIET_MODE_ENTITY,
    CONF_TEMP_SENSOR_ENTITY_ID,
    CONF_ZONES,
    DEFAULT_DEBOUNCE_INTERVAL,
    DEFAULT_DEBOUNCE_THRESHOLD,
    DEFAULT_MINISPLIT_RUNNING_THRESHOLD,
    DEFAULT_PRIORITY,
    DOMAIN,
    PRESETS,
)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): str,
})

def _build_add_zone_schema(exclude_entities: list[str] | None = None) -> vol.Schema:
    """Build the schema for adding a zone, excluding already-selected entities."""
    return vol.Schema({
        vol.Required(CONF_ENTITY_ID): selector({"entity": {
            "domain": "climate",
            "exclude_entities": exclude_entities or [],
        }}),
        vol.Optional(CONF_DEFAULT_PRESET, default="comfort"): selector({
            "select": {"options": PRESETS}
        }),
        vol.Optional(CONF_PRIORITY, default=DEFAULT_PRIORITY): selector({
            "number": {"min": 0, "max": 100, "step": 1, "mode": "box"}
        }),
        vol.Optional(CONF_QUIET_MODE_ENTITY): selector({
            "entity": {"domain": ["input_boolean", "switch", "binary_sensor", "schedule"]}
        }),
        vol.Optional(CONF_TEMP_SENSOR_ENTITY_ID): selector({
            "entity": {"domain": ["sensor", "number"]}
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
        self._outside_temp_entity: str | None = None
        self._debounce_interval: int = DEFAULT_DEBOUNCE_INTERVAL
        self._debounce_threshold: float = DEFAULT_DEBOUNCE_THRESHOLD
        self._enable_offset_learning: bool = True
        self._minisplit_running_threshold: float = DEFAULT_MINISPLIT_RUNNING_THRESHOLD

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

    def _build_configure_description(self) -> str:
        """Build the status summary for the configure hub."""
        lines = []

        lines.append(f"**Zones ({len(self._zones)}):**")
        if self._zones:
            for zone in self._zones:
                entity_id = zone[CONF_ENTITY_ID]
                friendly = entity_id.split(".")[-1].replace("_", " ").title()
                preset = zone.get(CONF_DEFAULT_PRESET, "comfort")
                priority = zone.get(CONF_PRIORITY, DEFAULT_PRIORITY)
                lines.append(f"  - {friendly} (preset: {preset}, priority: {priority})")
        else:
            lines.append("  No zones configured")

        preset_count = sum(1 for p in self._preset_configs.values() if p.get("heat_temp") is not None or p.get("cool_temp") is not None)
        lines.append(f"\n**Preset temperatures:** {preset_count} value(s) set")

        if self._outside_temp_entity:
            lines.append(f"\n**Outside sensor:** {self._outside_temp_entity}")
        else:
            lines.append("\n**Outside sensor:** Not set")

        offset_status = "Enabled" if self._enable_offset_learning else "Disabled"
        lines.append(f"**Offset learning:** {offset_status}")

        lines.append(f"\n**Debounce:** {self._debounce_interval}s interval, {self._debounce_threshold}°F threshold")
        lines.append(f"\n**Running detection:** {self._minisplit_running_threshold}°F/min threshold")

        return "\n".join(lines)

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
            return await self.async_step_configure()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_configure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Hub menu for configuring zones, presets, and settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input.get("action")
            if action == "add_zone":
                return await self.async_step_add_zone()
            elif action == "remove_zone":
                return await self.async_step_remove_zone()
            elif action == "preset_config":
                return await self.async_step_preset_config()
            elif action == "outside_temp":
                return await self.async_step_outside_temp()
            elif action == "debounce_config":
                return await self.async_step_debounce_config()
            elif action == "running_threshold":
                return await self.async_step_running_threshold()
            elif action == "done":
                if not self._zones:
                    errors["action"] = "no_zones"
                else:
                    return await self.async_step_finalize()

        return self.async_show_form(
            step_id="configure",
            data_schema=vol.Schema({
                vol.Required("action"): selector({
                    "select": {
                        "options": [
                            {"value": "add_zone", "label": "Add a zone"},
                            {"value": "remove_zone", "label": "Remove a zone"},
                            {"value": "preset_config", "label": "Configure presets"},
                            {"value": "outside_temp", "label": "Outside temp sensor"},
                            {"value": "debounce_config", "label": "Debounce settings"},
                            {"value": "running_threshold", "label": "Running detection threshold"},
                            {"value": "done", "label": "Finish setup"},
                        ],
                    }
                }),
            }),
            description_placeholders={"status": self._build_configure_description()},
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

            return await self.async_step_configure()

        schema_dict = {}
        for preset in PRESETS:
            existing_heat = self._preset_configs.get(preset, {}).get("heat_temp")
            existing_cool = self._preset_configs.get(preset, {}).get("cool_temp")
            schema_dict[vol.Optional(f"{preset}_heat_temp", default=existing_heat)] = vol.Coerce(float)
            schema_dict[vol.Optional(f"{preset}_cool_temp", default=existing_cool)] = vol.Coerce(float)

        return self.async_show_form(
            step_id="preset_config",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={"presets": ", ".join(PRESETS)},
        )

    async def async_step_outside_temp(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure outside temperature entity for offset learning."""
        if user_input is not None:
            self._outside_temp_entity = user_input.get(CONF_OUTSIDE_TEMP_ENTITY)
            self._enable_offset_learning = user_input.get(CONF_ENABLE_OFFSET_LEARNING, True)
            return await self.async_step_configure()

        return self.async_show_form(
            step_id="outside_temp",
            data_schema=vol.Schema({
                vol.Optional(CONF_OUTSIDE_TEMP_ENTITY, default=self._outside_temp_entity): selector({
                    "entity": {"domain": ["sensor", "weather", "input_number"]}
                }),
                vol.Optional(CONF_ENABLE_OFFSET_LEARNING, default=self._enable_offset_learning): selector({
                    "boolean": {}
                }),
            }),
            description_placeholders={
                "info": "Optionally select an outside temperature sensor to enable offset learning. This helps the system learn temperature differences between zone thermostats and mini-splits."
            },
        )

    async def async_step_add_zone(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle adding a zone to the thermostat group."""
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
                if user_input.get(CONF_QUIET_MODE_ENTITY):
                    zone_config[CONF_QUIET_MODE_ENTITY] = user_input[CONF_QUIET_MODE_ENTITY]
                if user_input.get(CONF_TEMP_SENSOR_ENTITY_ID):
                    zone_config[CONF_TEMP_SENSOR_ENTITY_ID] = user_input[CONF_TEMP_SENSOR_ENTITY_ID]
                self._zones.append(zone_config)
                return await self.async_step_configure()

        exclude_entities = [z[CONF_ENTITY_ID] for z in self._zones]
        return self.async_show_form(
            step_id="add_zone",
            data_schema=_build_add_zone_schema(exclude_entities),
            errors=errors,
        )

    async def async_step_remove_zone(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Remove a zone."""
        if user_input is not None:
            index = user_input.get("zone_index")
            if index is not None and 0 <= int(index) < len(self._zones):
                self._zones.pop(int(index))
            return await self.async_step_configure()

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

    async def async_step_debounce_config(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure debounce settings (advanced)."""
        if user_input is not None:
            self._debounce_interval = user_input.get(CONF_DEBOUNCE_INTERVAL, DEFAULT_DEBOUNCE_INTERVAL)
            self._debounce_threshold = user_input.get(CONF_DEBOUNCE_THRESHOLD, DEFAULT_DEBOUNCE_THRESHOLD)
            return await self.async_step_configure()

        return self.async_show_form(
            step_id="debounce_config",
            data_schema=vol.Schema({
                vol.Optional(CONF_DEBOUNCE_INTERVAL, default=self._debounce_interval): selector({
                    "number": {"min": 60, "max": 3600, "step": 60, "mode": "box", "unit_of_measurement": "s"}
                }),
                vol.Optional(CONF_DEBOUNCE_THRESHOLD, default=self._debounce_threshold): selector({
                    "number": {"min": 0.1, "max": 5.0, "step": 0.1, "mode": "box", "unit_of_measurement": "°F"}
                }),
            }),
            description_placeholders={
                "info": "Debounce settings control how often temperature adjustments are pushed to mini-splits. Higher values reduce frequent changes but may slow response to temperature shifts."
            },
        )

    async def async_step_running_threshold(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure running detection threshold."""
        if user_input is not None:
            self._minisplit_running_threshold = user_input.get(CONF_MINISPLIT_RUNNING_THRESHOLD, DEFAULT_MINISPLIT_RUNNING_THRESHOLD)
            return await self.async_step_configure()

        return self.async_show_form(
            step_id="running_threshold",
            data_schema=vol.Schema({
                vol.Optional(CONF_MINISPLIT_RUNNING_THRESHOLD, default=self._minisplit_running_threshold): selector({
                    "number": {"min": 0.01, "max": 1.0, "step": 0.01, "mode": "box", "unit_of_measurement": "°F/min"}
                }),
            }),
            description_placeholders={
                "info": "The minimum rate of temperature change (°F/min) required to detect that the minisplit is running. The detection also requires the temperature change direction to match the HVAC mode (rising in heat, falling in cool)."
            },
        )

    async def async_step_finalize(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Finalize the config entry."""
        data = {
            CONF_NAME: self._name or "Multi-Zone Thermostat",
            CONF_ZONES: self._zones,
            CONF_PRESET_CONFIGS: self._preset_configs,
        }
        if self._outside_temp_entity:
            data[CONF_OUTSIDE_TEMP_ENTITY] = self._outside_temp_entity
            data[CONF_ENABLE_OFFSET_LEARNING] = self._enable_offset_learning
        data[CONF_DEBOUNCE_INTERVAL] = self._debounce_interval
        data[CONF_DEBOUNCE_THRESHOLD] = self._debounce_threshold
        data[CONF_MINISPLIT_RUNNING_THRESHOLD] = self._minisplit_running_threshold

        return self.async_create_entry(
            title=self._name or "Multi-Zone Thermostat",
            data=data,
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
        self._quiet_mode_zone_index: int | None = None
        self._minisplit_running_threshold: float = DEFAULT_MINISPLIT_RUNNING_THRESHOLD

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
            elif action == "outside_temp":
                return await self.async_step_outside_temp()
            elif action == "offset_learning":
                return await self.async_step_offset_learning()
            elif action == "quiet_mode":
                return await self.async_step_quiet_mode()
            elif action == "debounce":
                return await self.async_step_debounce_config()
            elif action == "running_threshold":
                return await self.async_step_running_threshold()
            return await self.async_step_finalize()

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
                            {"value": "outside_temp", "label": "Outside temperature sensor"},
                            {"value": "offset_learning", "label": "Offset learning"},
                            {"value": "quiet_mode", "label": "Quiet mode entity"},
                            {"value": "debounce", "label": "Debounce settings"},
                            {"value": "running_threshold", "label": "Running detection threshold"},
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

    async def async_step_outside_temp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure outside temperature entity."""
        merged = {**self.config_entry.data, **self.config_entry.options}
        current_entity = merged.get(CONF_OUTSIDE_TEMP_ENTITY)

        if user_input is not None:
            new_entity = user_input.get(CONF_OUTSIDE_TEMP_ENTITY)
            current_options = dict(self.config_entry.options)
            current_options[CONF_OUTSIDE_TEMP_ENTITY] = new_entity
            return self.async_create_entry(data=current_options)

        return self.async_show_form(
            step_id="outside_temp",
            data_schema=vol.Schema({
                vol.Optional(CONF_OUTSIDE_TEMP_ENTITY, default=current_entity): selector({
                    "entity": {"domain": ["sensor", "weather", "input_number"]}
                }),
            }),
        )

    async def async_step_offset_learning(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure offset learning settings."""
        merged = {**self.config_entry.data, **self.config_entry.options}
        current_entity = merged.get(CONF_OUTSIDE_TEMP_ENTITY)
        current_enabled = merged.get(CONF_ENABLE_OFFSET_LEARNING, True)

        if user_input is not None:
            current_options = dict(self.config_entry.options)
            current_options[CONF_OUTSIDE_TEMP_ENTITY] = user_input.get(CONF_OUTSIDE_TEMP_ENTITY)
            current_options[CONF_ENABLE_OFFSET_LEARNING] = user_input.get(CONF_ENABLE_OFFSET_LEARNING, True)
            return self.async_create_entry(data=current_options)

        return self.async_show_form(
            step_id="offset_learning",
            data_schema=vol.Schema({
                vol.Optional(CONF_OUTSIDE_TEMP_ENTITY, default=current_entity): selector({
                    "entity": {"domain": ["sensor", "weather", "input_number"]}
                }),
                vol.Optional(CONF_ENABLE_OFFSET_LEARNING, default=current_enabled): selector({
                    "boolean": {}
                }),
            }),
        )

    async def async_step_debounce_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure debounce settings."""
        merged = {**self.config_entry.data, **self.config_entry.options}
        current_interval = merged.get(CONF_DEBOUNCE_INTERVAL, DEFAULT_DEBOUNCE_INTERVAL)
        current_threshold = merged.get(CONF_DEBOUNCE_THRESHOLD, DEFAULT_DEBOUNCE_THRESHOLD)

        if user_input is not None:
            current_options = dict(self.config_entry.options)
            current_options[CONF_DEBOUNCE_INTERVAL] = user_input.get(CONF_DEBOUNCE_INTERVAL, current_interval)
            current_options[CONF_DEBOUNCE_THRESHOLD] = user_input.get(CONF_DEBOUNCE_THRESHOLD, current_threshold)
            return self.async_create_entry(data=current_options)

        return self.async_show_form(
            step_id="debounce_config",
            data_schema=vol.Schema({
                vol.Optional(CONF_DEBOUNCE_INTERVAL, default=current_interval): selector({
                    "number": {"min": 60, "max": 3600, "step": 60, "mode": "box", "unit_of_measurement": "s"}
                }),
                vol.Optional(CONF_DEBOUNCE_THRESHOLD, default=current_threshold): selector({
                    "number": {"min": 0.1, "max": 5.0, "step": 0.1, "mode": "box", "unit_of_measurement": "°F"}
                }),
            }),
        )

    async def async_step_running_threshold(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure running detection threshold."""
        merged = {**self.config_entry.data, **self.config_entry.options}
        current_threshold = merged.get(CONF_MINISPLIT_RUNNING_THRESHOLD, DEFAULT_MINISPLIT_RUNNING_THRESHOLD)

        if user_input is not None:
            current_options = dict(self.config_entry.options)
            current_options[CONF_MINISPLIT_RUNNING_THRESHOLD] = user_input.get(CONF_MINISPLIT_RUNNING_THRESHOLD, current_threshold)
            return self.async_create_entry(data=current_options)

        return self.async_show_form(
            step_id="running_threshold",
            data_schema=vol.Schema({
                vol.Optional(CONF_MINISPLIT_RUNNING_THRESHOLD, default=current_threshold): selector({
                    "number": {"min": 0.01, "max": 1.0, "step": 0.01, "mode": "box", "unit_of_measurement": "°F/min"}
                }),
            }),
            description_placeholders={
                "info": "The minimum rate of temperature change (°F/min) required to detect that the minisplit is running. The detection also requires the temperature change direction to match the HVAC mode (rising in heat, falling in cool)."
            },
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
                if user_input.get(CONF_QUIET_MODE_ENTITY):
                    zone_config[CONF_QUIET_MODE_ENTITY] = user_input[CONF_QUIET_MODE_ENTITY]
                if user_input.get(CONF_TEMP_SENSOR_ENTITY_ID):
                    zone_config[CONF_TEMP_SENSOR_ENTITY_ID] = user_input[CONF_TEMP_SENSOR_ENTITY_ID]
                self._zones.append(zone_config)
                return await self.async_step_manage_zones()

        exclude_entities = [z[CONF_ENTITY_ID] for z in self._zones]
        return self.async_show_form(
            step_id="add_zone",
            data_schema=_build_add_zone_schema(exclude_entities),
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

    async def async_step_quiet_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a zone to configure its quiet mode entity."""
        if user_input is not None:
            self._quiet_mode_zone_index = int(user_input["zone_index"])
            return await self.async_step_quiet_mode_edit()

        zone_options = {}
        for i, zone in enumerate(self._zones):
            entity_id = zone[CONF_ENTITY_ID]
            friendly = entity_id.split(".")[-1].replace("_", " ").title()
            quiet_entity = zone.get(CONF_QUIET_MODE_ENTITY)
            if quiet_entity:
                friendly += f" (quiet: {quiet_entity})"
            else:
                friendly += " (quiet: none)"
            zone_options[str(i)] = friendly

        return self.async_show_form(
            step_id="quiet_mode",
            data_schema=vol.Schema({
                vol.Required("zone_index"): vol.In(zone_options),
            }),
        )

    async def async_step_quiet_mode_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit the quiet mode entity for a selected zone."""
        zone = self._zones[self._quiet_mode_zone_index]
        current_quiet_entity = zone.get(CONF_QUIET_MODE_ENTITY)

        if user_input is not None:
            new_entity = user_input.get(CONF_QUIET_MODE_ENTITY)
            if new_entity:
                zone[CONF_QUIET_MODE_ENTITY] = new_entity
            elif CONF_QUIET_MODE_ENTITY in zone:
                del zone[CONF_QUIET_MODE_ENTITY]
            return await self.async_step_manage_zones()

        return self.async_show_form(
            step_id="quiet_mode_edit",
            data_schema=vol.Schema({
                vol.Optional(CONF_QUIET_MODE_ENTITY, default=current_quiet_entity): selector({
                    "entity": {"domain": ["input_boolean", "switch", "binary_sensor", "schedule"]}
                }),
            }),
        )

    async def async_step_finalize(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Finalize and save options."""
        merged = {**self.config_entry.data, **self.config_entry.options}
        current_threshold = merged.get(CONF_MINISPLIT_RUNNING_THRESHOLD, DEFAULT_MINISPLIT_RUNNING_THRESHOLD)
        return self.async_create_entry(
            data={
                CONF_ZONES: self._zones,
                CONF_MINISPLIT_RUNNING_THRESHOLD: current_threshold,
            },
        )
