# Multi-Zone Mini-Split Thermostat

A Home Assistant custom integration that creates a virtual thermostat to manage multiple mini-split zones with per-zone preset control, automatic mode switching, manual setpoint adjustment, and quiet mode.

## Features

- **Mode select** - control heat, cool, or off mode for all mini-splits at once
- **Automatic mode switching** - automatically switches between heat and cool based on zone temperatures
- **Per-zone preset selectors** - each zone has its own select input for preset (comfort, eco, failsafe)
- **Global preset temperatures** - define heating and cooling targets for each preset, shared across all zones
- **Zone priority** - when zones conflict, the highest priority zone determines the mode
- **Setpoint adjustment** - pushes an adjusted mini-split setpoint based on measured zone error and a configurable max adjustment
- **Per-zone quiet mode** - suppresses setpoint writes during quiet hours while still allowing mode switching
- **HACS compatible** - easy installation via HACS

## Architecture

This integration creates entities grouped under multiple devices:

- **Main device**: Mode select, preset temperature numbers, and max adjustment number
- **Zone devices** (one per zone): Zone preset select, zone priority number, quiet mode diagnostic binary sensor, and actual setpoint diagnostic sensor

Each zone device is linked to the main device via `via_device`, creating a hierarchical structure.

Temperature targets are derived from the global preset configuration and the currently active preset for each zone. The mini-split receives an adjusted actual setpoint when the measured zone temperature is away from the desired target.

## Automatic Mode Switching

The integration automatically determines whether to operate in HEAT or COOL mode based on zone temperatures:

- Each zone has a **comfort band** defined by its preset's heating and cooling targets
- If a zone's current temperature drops below `heat_target - 1°F`, it needs HEAT
- If a zone's current temperature rises above `cool_target + 1°F`, it needs COOL
- If all zones are within their comfort bands, the mode does not change
- If zones conflict, the **highest priority zone** wins
- Mode changes have a 5-minute cooldown to prevent rapid switching

Setting the mode to OFF disables auto-switching.

## Setpoint Adjustment

The integration separates the **desired target** from the **actual setpoint** sent to the mini-split:

- Desired target: the selected preset's heating or cooling target
- Actual setpoint: the desired target plus a clamped correction in the active control direction
- Heat mode: if the zone is below the desired target, the pushed setpoint is raised above the desired target by up to Max Adjustment
- Cool mode: if the zone is above the desired target, the pushed setpoint is lowered below the desired target by up to Max Adjustment
- If no current temperature is available, the actual setpoint equals the desired target
- The **Max Adjustment** number entity defaults to `3°F` and can be adjusted from `0–5°F`
- The per-zone **Actual Setpoint** diagnostic sensor reports the most recent value pushed to each mini-split

Quiet mode skips actual setpoint writes entirely, so mini-splits do not beep during quiet hours. HVAC mode changes are still allowed.

## Quiet Mode (Per-Zone)

Quiet mode prevents continuous beeping from mini-splits receiving new setpoints during quiet hours, while still allowing HVAC mode switching.

### Setup

- Create an `input_boolean`, `switch`, `binary_sensor`, or Home Assistant `schedule` helper for quiet mode
- Configure it via the zone setup screen or reconfiguration options
- If using a `schedule` helper, set the quiet hours directly in Home Assistant

## Zone Priority

Each zone has a priority value (integer, default: 0). When zones have conflicting needs, the zone with the highest priority determines the system mode.

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
   - Add zones one by one, selecting a default preset, priority, optional quiet mode entity, and optional temperature sensor override
   - Configure preset temperatures
   - Configure max adjustment

After setup, preset temperatures, max adjustment, and zone priorities can be adjusted with number entity controls.

### Via YAML

Add to your `configuration.yaml`:

```yaml
multizone_minisplit_thermostat:
  main_thermostat:
    name: "Whole House Thermostat"
    max_adjustment: 3.0
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
        quiet_mode_entity: input_boolean.bedroom_quiet
        temp_sensor_entity_id: sensor.bedroom_temperature
```

## Configuration Options

| Key | Required | Description |
|-----|----------|-------------|
| `name` | Yes | Display name for the virtual thermostat |
| `presets` | No | Global preset temperature configuration shared across all zones |
| `heat_temp` | No | Target temperature when in heat mode for this preset (default: 68°F) |
| `cool_temp` | No | Target temperature when in cool mode for this preset (default: 74°F) |
| `max_adjustment` | No | Maximum actual setpoint correction in °F (default: 3°F, range: 0–5°F) |
| `zones` | Yes | List of climate zones to manage |
| `entity_id` | Yes | The climate entity ID (e.g., `climate.living_room`) |
| `default_preset` | No | Default preset for this zone (default: `comfort`) |
| `priority` | No | Zone priority for mode conflict resolution |
| `quiet_mode_entity` | No | Entity that controls quiet mode for this zone |
| `temp_sensor_entity_id` | No | Optional temperature sensor used instead of the climate entity's current temperature |

## Entities

### Mode Select

Controls the HVAC mode for all zones: `heat`, `cool`, or `off`.

### Select Entities (Per-Zone Preset)

One select entity is created for each zone. Changing it updates the zone's desired target temperature based on the global preset configuration and current HVAC mode.

### Number Entities

- **Preset Temperature**: one for each preset × mode combination, range 40°F to 95°F, step 1°F
- **Zone Priority**: one per zone, range 0 to 100, step 1
- **Max Adjustment**: global correction limit, range 0°F to 5°F, step 0.1°F

### Sensor Entities

- **Actual Setpoint**: per-zone diagnostic sensor showing the most recent setpoint pushed to the mini-split

### Binary Sensor Entities

- **Quiet Mode**: per-zone diagnostic sensor indicating whether quiet mode is active, when a quiet mode entity is configured

## Services

### `multizone_minisplit_thermostat.set_zone_preset`

Set the preset for a specific zone.

| Field | Required | Description |
|-------|----------|-------------|
| `zone` | Yes | The climate entity ID of the zone |
| `preset` | Yes | The preset to apply (`comfort`, `eco`, or `failsafe`) |

## Presets

| Preset | Description |
|--------|-------------|
| `comfort` | Normal comfort temperatures for occupied spaces |
| `eco` | Energy-saving temperatures for unoccupied or quiet periods |
| `failsafe` | Extreme temperatures to prevent pipe freezing or overheating during equipment failures |

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│   Device: {Thermostat Name}                                     │
│                                                                 │
│   Select: Mode → heat                                           │
│   Number: Comfort Heating Target → 70°F                         │
│   Number: Comfort Cooling Target → 72°F                         │
│   Number: Eco Heating Target → 65°F                             │
│   Number: Eco Cooling Target → 78°F                             │
│   Number: Failsafe Heating Target → 60°F                        │
│   Number: Failsafe Cooling Target → 85°F                        │
│   Number: Max Adjustment → 3°F                                  │
└─────────────────────────────────────────────────────────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Device: Server   │  │ Device: Living   │  │ Device: Bedroom  │
│ Room             │  │ Room             │  │                  │
│ Preset: failsafe │  │ Preset: comfort  │  │ Preset: comfort  │
│ Priority: 100    │  │ Priority: 10     │  │ Priority: 0      │
│ Actual: 70°F     │  │ Actual: 71°F     │  │ Actual: 70°F     │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```
