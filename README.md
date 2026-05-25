# Multi-Zone Mini-Split Thermostat

A Home Assistant custom integration that creates a virtual thermostat to manage multiple mini-split zones with per-zone preset control and automatic mode switching.

## Features

- **Group mode control** - set heat, cool, or off mode for all mini-splits at once
- **Automatic mode switching** - automatically switches between heat and cool based on zone temperatures
- **Per-zone preset selectors** - each zone has its own select input for preset (comfort, eco, failsafe)
- **Global preset temperatures** - define heating and cooling targets for each preset, shared across all zones
- **Zone priority** - when zones conflict, the highest priority zone determines the mode
- **HACS compatible** - easy installation via HACS

## Architecture

This integration creates two types of entities:

1. **Climate entity** (group controller) - manages HVAC mode (heat/cool/off) for all zones, shows average current temperature, and exposes per-zone state as attributes
2. **Select entities** (one per zone) - control the active preset for each individual zone

Temperature targets are derived from the global preset configuration and the currently active preset for each zone. The climate entity does not expose a target temperature or preset mode directly since those are managed per-zone.

## Automatic Mode Switching

The integration automatically determines whether to operate in HEAT or COOL mode based on zone temperatures:

- Each zone has a **comfort band** defined by its preset's heating and cooling targets
- If a zone's current temperature drops below `heat_target - 1°F`, it needs HEAT
- If a zone's current temperature rises above `cool_target + 1°F`, it needs COOL
- If all zones are within their comfort bands, the mode does not change
- If zones conflict (some need heat, some need cool), the **highest priority zone** wins

Setting the mode manually to HEAT or COOL keeps auto-switching enabled. Setting it to OFF disables auto-switching.

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
   - Add zones one by one, selecting a default preset and priority for each

### Via YAML

Add to your `configuration.yaml`:

```yaml
multizone_minisplit_thermostat:
  main_thermostat:
    name: "Whole House Thermostat"
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
```

## Configuration Options

| Key | Required | Description |
|-----|----------|-------------|
| `name` | Yes | Display name for the virtual thermostat |
| `presets` | No | Global preset temperature configuration (shared across all zones) |
| `heat_temp` | No | Target temperature when in heat mode for this preset (default: 68°F) |
| `cool_temp` | No | Target temperature when in cool mode for this preset (default: 74°F) |
| `zones` | Yes | List of climate zones to manage |
| `entity_id` | Yes | The climate entity ID (e.g., `climate.living_room`) |
| `default_preset` | No | Default preset for this zone when the integration starts (default: `comfort`) |
| `priority` | No | Zone priority for mode conflict resolution (default: 0, higher = more important) |

## Entities

### Climate Entity (Group Controller)

The main climate entity provides:
- **HVAC mode control** - heat, cool, or off (propagates to all zones)
- **Current temperature** - average across all zones
- **Attributes** - per-zone preset, priority, heat/cool targets, current target temperature, and raw state

### Select Entities (Per-Zone Preset)

One select entity is created for each zone:
- **Name**: `{Thermostat Name} - {Zone Name} Preset`
- **Options**: `comfort`, `eco`, `failsafe`
- **Attributes**: zone's entity ID, current target temperature

Changing the select updates the zone's preset, which recalculates its target temperature based on the global preset configuration and current HVAC mode.

### Number Entities (Preset Temperatures)

Six number entities are created (one for each preset × mode combination):
- **Names**: `{Thermostat Name} - {Preset} {Heating|Cooling} Target`
- **Range**: 40°F to 95°F, step 1°F
- **Purpose**: Configure the target temperatures for each preset globally

Changing a preset temperature updates the target for all zones using that preset. The new target takes effect when the system mode matches (heating targets apply in HEAT mode, cooling targets in COOL mode).

## Services

### `multizone_minisplit_thermostat.set_zone_preset`

Set the preset for a specific zone (alternative to using the select entity).

| Field | Required | Description |
|-------|----------|-------------|
| `zone` | Yes | The climate entity ID of the zone |
| `preset` | Yes | The preset to apply (`comfort`, `eco`, or `failsafe`) |

#### Example

```yaml
# Set bedroom to eco mode (energy saving)
service: multizone_minisplit_thermostat.set_zone_preset
data:
  zone: climate.bedroom_minisplit
  preset: eco
```

## Presets

| Preset | Description |
|--------|-------------|
| `comfort` | Normal comfort temperatures for occupied spaces |
| `eco` | Energy-saving temperatures for unoccupied or sleeping periods |
| `failsafe` | Extreme temperatures to prevent pipe freezing or overheating during equipment failures |

## Architecture Diagram

```
┌─────────────────────────────────────────┐
│   Climate Entity (Group Controller)      │
│                                          │
│   Mode: HEAT (auto-switched)             │
│   Current Temp: 71°F (avg)              │
│                                          │
│   Attributes:                            │
│   - zone_presets: {...}                  │
│   - zone_target_temps: {...}             │
│   - zones: {                             │
│       climate.server_room: {             │
│         priority: 100,                   │
│         preset: failsafe,                │
│         heat_target: 60°F,               │
│         cool_target: 85°F,               │
│         target_temp: 60°F,               │
│         ...                              │
│       },                                 │
│       ...                                │
│     }                                    │
└─────────────────────────────────────────┘
          │
          ├──▶ Select: Server Room Preset → failsafe
          ├──▶ Select: Living Room Preset → comfort
          └──▶ Select: Bedroom Preset → comfort
          
          ┌─────────────────────────────────────────┐
          │   Number Entities (Preset Temperatures) │
          │   - Comfort Heating/Cooling Target      │
          │   - Eco Heating/Cooling Target          │
          │   - Failsafe Heating/Cooling Target     │
          └─────────────────────────────────────────┘
```
