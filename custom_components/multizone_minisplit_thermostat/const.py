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
CONF_ZONES = "zones"
CONF_ENTITY_ID = "entity_id"
CONF_PRESET_CONFIGS = "presets"
CONF_DEFAULT_PRESET = "default_preset"
CONF_PRIORITY = "priority"

# Optional temperature sensor entity ID to override the zone's temperature source
CONF_TEMP_SENSOR_ENTITY_ID = "temp_sensor_entity_id"

# Per-preset temperature keys (shared across all zones)
CONF_HEAT_TEMP = "heat_temp"
CONF_COOL_TEMP = "cool_temp"

# Zone attribute keys
ATTR_ZONE_PRESETS = "zone_presets"
ATTR_ZONE_TARGET_TEMPS = "zone_target_temps"

# Service constants
SERVICE_SET_ZONE_PRESET = "set_zone_preset"
ATTR_ZONE = "zone"
ATTR_PRESET = "preset"

# Defaults
DEFAULT_HEAT_TEMP = 68.0
DEFAULT_COOL_TEMP = 74.0
DEFAULT_PRIORITY = 0

# Auto mode control
TEMPERATURE_TOLERANCE = 1.0  # degrees F before triggering mode change

AUTOMATIC_MODE_COOLDOWN = 300  # 5 minutes in seconds

# Quiet mode configuration keys
CONF_QUIET_MODE_ENTITY = "quiet_mode_entity"
CONF_DEBOUNCE_INTERVAL = "debounce_interval"
CONF_DEBOUNCE_THRESHOLD = "debounce_threshold"

# Debounce defaults
DEFAULT_DEBOUNCE_INTERVAL = 900  # 15 minutes in seconds
DEFAULT_DEBOUNCE_THRESHOLD = 0.5  # degrees F

# Reconciliation
RECONCILE_INTERVAL = 60
RECONCILE_TEMP_TOLERANCE = 0.5
