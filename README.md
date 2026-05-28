# Multi-Zone Mini-Split Thermostat

A Home Assistant custom integration that creates a virtual thermostat to manage multiple mini-split zones with per-zone preset control, automatic mode switching, offset learning, and sleep mode.

## Features

- **Mode select** - control heat, cool, or off mode for all mini-splits at once
- **Automatic mode switching** - automatically switches between heat and cool based on zone temperatures
- **Per-zone preset selectors** - each zone has its own select input for preset (comfort, eco, failsafe)
- **Global preset temperatures** - define heating and cooling targets for each preset, shared across all zones
- **Zone priority** - when zones conflict, the highest priority zone determines the mode
- **Offset learning** - ML-based regression that learns the temperature offset between zone thermostats and mini-splits using outside temperature as a predictor; toggleable via config or runtime switch entity
- **Per-zone sleep mode** - prevents continuous beeping adjustments in zones (e.g., bedrooms) during sleep by forcing a preset, while still allowing mode switching
- **Debounce system** - prevents rapid or tiny temperature adjustments to mini-splits
- **HACS compatible** - easy installation via HACS

## Architecture

This integration creates entities grouped under multiple devices:

- **Main device**: Mode select, preset temperature numbers, and debounce configuration (global settings shared across all zones)
- **Zone devices** (one per zone): Zone preset select, zone priority number, and offset learning sensors

Each zone device is linked to the main device via `via_device`, creating a hierarchical structure.

Temperature targets are derived from the global preset configuration, the currently active preset for each zone, and any learned offset adjustments.

## Automatic Mode Switching

The integration automatically determines whether to operate in HEAT or COOL mode based on zone temperatures:

- Each zone has a **comfort band** defined by its preset's heating and cooling targets
- If a zone's current temperature drops below `heat_target - 1°F`, it needs HEAT
- If a zone's current temperature rises above `cool_target + 1°F`, it needs COOL
- If all zones are within their comfort bands, the mode does not change
- If zones conflict (some need heat, some need cool), the **highest priority zone** wins
- Mode changes have a 5-minute cooldown to prevent rapid switching

Setting the mode manually keeps auto-switching enabled. Setting it to OFF disables auto-switching.

## Offset Learning System

The integration can learn the temperature offset between your zone thermostats and mini-splits, using outside temperature as a predictor variable. This helps compensate for temperature differences caused by sensor placement, ductwork, or environmental factors.

### How It Works

- A simple linear regression model is maintained per zone: `offset = a * outside_temp + b`
- Data points are collected automatically whenever zone states change
- The model uses a 30-day sliding window to stay current
- Offsets are clamped to ±5°F to prevent extreme values
- Data persists across restarts via Home Assistant storage

### Configuration

1. Set an **outside temperature entity** during setup or via reconfiguration (e.g., a weather sensor)
2. The system starts with zero offset and gradually learns as data accumulates
3. Monitor learning progress via the **Offset Samples** sensor per zone
4. View current offset and model coefficients via the **Learned Offset** sensor per zone

### Debounce System

To prevent rapid or unnecessary temperature adjustments:

- **Debounce Interval**: Minimum time between adjustments (default: 15 minutes)
- **Debounce Threshold**: Minimum offset change to trigger an adjustment (default: 0.5°F)
- **Both criteria must be met** before a new offset is applied

These settings can be configured during setup or adjusted anytime via the number entity controls.

## Sleep Mode (Per-Zone)

Sleep mode prevents continuous beeping from mini-splits receiving new setpoints during sleep hours, while still allowing HVAC mode switching for dramatic outside temperature changes.

### How It Works

1. Configure a **Sleep Mode Entity** per zone (e.g., `input_boolean.bedroom_sleep`)
2. Configure a **Sleep Preset** per zone (e.g., "eco")
3. When the sleep mode entity is "on", the zone uses the sleep preset instead of its normal preset
4. Temperature adjustments are suppressed during sleep mode to avoid beeping
5. **Mode switching still works** - the system can still switch between HEAT and COOL as needed

### Setup

- Create an `input_boolean` or use a `switch`/`binary_sensor` in Home Assistant for sleep scheduling
- Configure it via the zone setup screen or reconfiguration options
- Optionally automate it with Home Assistant automations based on time of day

## Zone Priority

Each zone has a priority value (integer, default: 0). When zones have conflicting needs, the zone with the highest priority determines the system mode. Use higher priority for zones with sensitive equipment or critical comfort requirements.

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Click "Custom repositories"
3. Add this repository URL
4. Select "Integration" as the category
5. Install "Multi-Zone Mini-Split Thermostat"
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/multizone_minisplit_thermostat` folder to your `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Via UI

1. Go to Settings > Devices & Services > Add Integration
2. Search for "Multi-Zone Mini-Split Thermostat"
3. Follow the setup wizard:
   - Name your thermostat
   - Configure preset temperatures (heat/cool targets for comfort, eco, failsafe)
   - Optionally select an outside temperature sensor for offset learning
   - Add zones one by one, selecting a default preset, priority, and optional sleep mode configuration
   - Configure debounce settings (advanced)

#### Reconfiguration

After initial setup, you can reconfigure the integration to:
- Add or remove zones
- Change the outside temperature sensor
- Adjust debounce settings

1. Go to Settings > Devices & Services > Multi-Zone Mini-Split Thermostat
2. Click the integration entry, then click **Configure**
3. Choose the action you want to perform
4. Click **Finalize** to save changes

Preset temperatures, debounce settings, and zone priorities can be adjusted anytime using the number entity controls on the dashboard—no reconfiguration needed.

### Via YAML

Add to your `configuration.yaml`:

```yaml
multizone_minisplit_thermostat:
  main_thermostat:
    name: "Whole House Thermostat"
    outside_temp_entity: "sensor.outside_temperature"
    enable_offset_learning: false
    debounce_interval: 900
    debounce_threshold: 0.5
    presets:
      comfort:
        heat_temp: 70
        cool_temp: 72
      eco:
        heat_temp: 65
        cool_temp: 78
      failsafe:
        heat_temp: 60
        cool_temp: 85
    zones:
      - entity_id: climate.server_room
        default_preset: failsafe
        priority: 100
      - entity_id: climate.living_room
        default_preset: comfort
        priority: 10
      - entity_id: climate.bedroom
        default_preset: comfort
        priority: 0
        sleep_mode_entity: input_boolean.bedroom_sleep
```

## Configuration Options

| Key | Required | Description |
|-----|----------|-------------|
| `name` | Yes | Display name for the virtual thermostat |
| `presets` | No | Global preset temperature configuration (shared across all zones) |
| `heat_temp` | No | Target temperature when in heat mode for this preset (default: 68°F) |
| `cool_temp` | No | Target temperature when in cool mode for this preset (default: 74°F) |
| `outside_temp_entity` | No | Entity ID for outside temperature sensor (enables offset learning) |
| `enable_offset_learning` | No | Enable offset learning system (default: false, requires `outside_temp_entity`) |
| `debounce_interval` | No | Minimum seconds between temperature adjustments (default: 900 / 15 min) |
| `debounce_threshold` | No | Minimum offset change in °F to trigger adjustment (default: 0.5) |
| `zones` | Yes | List of climate zones to manage |
| `entity_id` | Yes | The climate entity ID (e.g., `climate.living_room`) |
| `default_preset` | No | Default preset for this zone when the integration starts (default: `comfort`) |
| `priority` | No | Zone priority for mode conflict resolution (default: 0, higher = more important) |
| `sleep_mode_entity` | No | Entity that controls sleep mode for this zone (e.g., `input_boolean.bedroom_sleep`) |

## Entities

### Mode Select

Controls the HVAC mode for all zones:
- **Options**: `heat`, `cool`, `off`
- **Setting to OFF** disables automatic mode switching

### Select Entities (Per-Zone Preset)

One select entity is created for each zone:
- **Name**: `{Thermostat Name} - {Zone Name} Preset`
- **Options**: `comfort`, `eco`, `failsafe`

Changing the select updates the zone's preset, which recalculates its target temperature based on the global preset configuration and current HVAC mode.

### Number Entities (Preset Temperatures)

Six number entities are created (one for each preset × mode combination):
- **Names**: `{Thermostat Name} - {Preset} {Heating|Cooling} Target`
- **Range**: 40°F to 95°F, step 1°F
- **Purpose**: Configure the target temperatures for each preset globally

### Number Entities (Zone Priority)

One number entity is created per zone for adjusting zone priority:
- **Names**: `{Zone Name} Priority`
- **Range**: 0 to 100, step 1
- **Purpose**: Adjust zone priority for automatic mode conflict resolution (higher = more important)

### Number Entities (Debounce Configuration)

Two global number entities for controlling temperature adjustment behavior:
- **Names**: `Debounce Interval`, `Debounce Threshold`
- **Range**: 60–3600 seconds / 0.1–5.0°F
- **Purpose**: Prevent rapid or tiny temperature changes from being pushed to mini-splits

### Sensor Entities (Offset Learning)

Two sensor entities are created per zone when offset learning is enabled:
- **Names**: `{Zone Name} Learned Offset`, `{Zone Name} Offset Samples`
- **Purpose**: Monitor offset learning progress and current model
- **Learned Offset attributes**: `slope`, `intercept`, `sample_count`, `has_model`, `last_calculation`

### Switch Entities

- **Offset Learning**: Toggle to enable/disable the offset learning system at runtime
  - When disabled, learned offsets are reset to zero and no new data is collected
  - Requires an outside temperature entity to be configured

## Services

### `multizone_minisplit_thermostat.set_zone_preset`

Set the preset for a specific zone (alternative to using the select entity).

| Field | Required | Description |
|-------|----------|-------------|
| `zone` | Yes | The climate entity ID of the zone |
| `preset` | Yes | The preset to apply (`comfort`, `eco`, or `failsafe`) |

### `multizone_minisplit_thermostat.recalculate_offsets`

Force recalculation of learned temperature offsets.

| Field | Required | Description |
|-------|----------|-------------|
| `zone` | No | The climate entity ID of a specific zone. Leave empty for all zones. |

### `multizone_minisplit_thermostat.clear_offset_history`

Clear learned offset data.

| Field | Required | Description |
|-------|----------|-------------|
| `zone` | No | The climate entity ID of a specific zone. Leave empty for all zones. |

## Presets

| Preset | Description |
|--------|-------------|
| `comfort` | Normal comfort temperatures for occupied spaces |
| `eco` | Energy-saving temperatures for unoccupied or sleeping periods |
| `failsafe` | Extreme temperatures to prevent pipe freezing or overheating during equipment failures |

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│   Device: {Thermostat Name}                                     │
│                                                                 │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │  Select: Mode → heat                                      │ │
│   │  Number: Comfort Heating Target → 70°F                    │ │
│   │  Number: Comfort Cooling Target → 72°F                    │ │
│   │  Number: Eco Heating Target → 65°F                        │ │
│   │  Number: Eco Cooling Target → 78°F                        │ │
│   │  Number: Failsafe Heating Target → 60°F                   │ │
│   │  Number: Failsafe Cooling Target → 85°F                   │ │
│   │  Number: Debounce Interval → 900s                         │ │
│   │  Number: Debounce Threshold → 0.5°F                       │ │
│   │  Switch: Offset Learning → On                             │ │
│   └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Device:          │  │ Device:          │  │ Device:          │
│ {Name} - Server  │  │ {Name} - Living  │  │ {Name} - Bedroom │
│ Room             │  │ Room             │  │                  │
│                  │  │                  │  │                  │
│  Preset:         │  │  Preset:         │  │  Preset:         │
│  failsafe        │  │  comfort         │  │  comfort         │
│                  │  │                  │  │  Sleep: eco      │
│  Priority: 100   │  │  Priority: 10    │  │  Priority: 0     │
│                  │  │                  │  │                  │
│  Offset: 0.0°F   │  │  Offset: 1.2°F   │  │  Offset: -0.8°F  │
│  Samples: 45     │  │  Samples: 120    │  │  Samples: 89     │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```
