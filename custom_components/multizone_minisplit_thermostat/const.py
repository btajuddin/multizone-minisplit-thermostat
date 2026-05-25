"""Constants for the Multi-Zone Mini-Split Thermostat integration."""

from homeassistant.components.climate import HVACMode

DOMAIN = "multizone_minisplit_thermostat"

# Preset names
PRESET_COMFORT = "comfort"
PRESET_ECO = "eco"
PRESET_FAILSAFE = "failsafe"
PRESETS = [PRESET_COMFORT, PRESET_ECO, PRESET_FAILSAFE]

# Supported HVAC modes
HVAC_MODES = [HVACMode.HEAT, HVACMode.COOL]

# Configuration keys
CONF_ENTITIES = "entities"
CONF_ENTITY_ID = "entity_id"
CONF_PRESET_CONFIGS = "presets"
CONF_DEFAULT_PRESET = "default_preset"

# Per-preset temperature keys (these are shared across all entities)
CONF_HEAT_TEMP = "heat_temp"
CONF_COOL_TEMP = "cool_temp"

# Entity attribute keys
ATTR_ENTITY_PRESETS = "entity_presets"
ATTR_ENTITY_TARGET_TEMPS = "entity_target_temps"

# Service constants
SERVICE_SET_ENTITY_PRESET = "set_entity_preset"
ATTR_ENTITY = "entity"
ATTR_PRESET = "preset"

# Defaults
DEFAULT_HEAT_TEMP = 68.0
DEFAULT_COOL_TEMP = 74.0
