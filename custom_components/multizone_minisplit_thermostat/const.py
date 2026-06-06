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

# Offset learning and quiet mode configuration keys
CONF_OUTSIDE_TEMP_ENTITY = "outside_temp_entity"
CONF_QUIET_MODE_ENTITY = "quiet_mode_entity"
CONF_DEBOUNCE_INTERVAL = "debounce_interval"
CONF_DEBOUNCE_THRESHOLD = "debounce_threshold"
CONF_ENABLE_OFFSET_LEARNING = "enable_offset_learning"

# Offset learning and debounce defaults
DEFAULT_DEBOUNCE_INTERVAL = 900  # 15 minutes in seconds
DEFAULT_DEBOUNCE_THRESHOLD = 0.5  # degrees F
OFFSET_LEARNING_WINDOW = 2592000  # 30 days in seconds
OFFSET_RECALC_INTERVAL = 300  # recalculate every 5 minutes
OFFSET_MAX_VALUE = 5.0  # maximum absolute offset in degrees F (clamp)

# Running detection configuration key
CONF_MINISPLIT_RUNNING_THRESHOLD = "minisplit_running_threshold"

# Running detection defaults
MINISPLIT_RUNNING_WINDOW = 600  # seconds (10 minutes) lookback window for temp change rate
DEFAULT_MINISPLIT_RUNNING_THRESHOLD = 0.05  # degrees F per minute minimum change to detect running

# Service constants
SERVICE_RECALCULATE_OFFSETS = "recalculate_offsets"
SERVICE_CLEAR_OFFSET_HISTORY = "clear_offset_history"
