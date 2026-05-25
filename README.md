# Multi-Zone Mini-Split Thermostat

A Home Assistant custom integration that creates a virtual thermostat to manage multiple mini-split zones with per-zone preset control and automatic mode switching.

## Features

- **Mode select** - control heat, cool, or off mode for all mini-splits at once
- **Automatic mode switching** - automatically switches between heat and cool based on zone temperatures
- **Per-zone preset selectors** - each zone has its own select input for preset (comfort, eco, failsafe)
- **Global preset temperatures** - define heating and cooling targets for each preset, shared across all zones
- **Zone priority** - when zones conflict, the highest priority zone determines the mode
- **HACS compatible** - easy installation via HACS

## Architecture

This integration creates three types of entities, all grouped under a single device:

1. **Mode select** - controls HVAC mode (heat/cool/off) for all zones
2. **Select entities** (one per zone) - control the active preset for each individual zone
3. **Number entities** (one per preset × mode) - configure heating and cooling target temperatures

Temperature targets are derived from the global preset configuration and the currently active preset for each zone.

## Automatic Mode Switching

The integration automatically determines whether to operate in HEAT or COOL mode based on zone temperatures:

- Each zone has a **comfort band** defined by its preset's heating and cooling targets
- If a zone's current temperature drops below `heat_target - 1°F`, it needs HEAT
- If a zone's current temperature rises above `cool_target + 1°F`, it needs COOL
- If all zones are within their comfort bands, the mode does not change
- If zones conflict (some need heat, some need cool), the **highest priority zone** wins
- Mode changes have a 5-minute cooldown to prevent rapid switching

Setting the mode manually keeps auto-switching enabled. Setting it to OFF disables auto-switching.

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

#### Reconfiguration

After initial setup, you can reconfigure the integration to add or remove zones:
1. Go to Settings > Devices & Services > Multi-Zone Mini-Split Thermostat
2. Click the integration entry, then click **Configure**
3. Add or remove zones as needed
4. Click **Finalize** to save changes

Preset temperatures can be adjusted anytime using the number entity controls on the dashboard—no reconfiguration needed.

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

## Services

### `multizone_minisplit_thermostat.set_zone_preset`

Set the preset for a specific zone (alternative to using the select entity).

| Field | Required | Description |
|-------|----------|-------------|
| `zone` | Yes | The climate entity ID of the zone |
| `preset` | Yes | The preset to apply (`comfort`, `eco`, or `failsafe`) |

## Presets

| Preset | Description |
|--------|-------------|
| `comfort` | Normal comfort temperatures for occupied spaces |
| `eco` | Energy-saving temperatures for unoccupied or sleeping periods |
| `failsafe` | Extreme temperatures to prevent pipe freezing or overheating during equipment failures |

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│   Device: {Thermostat Name}                     │
│                                                 │
│   ┌───────────────────────────────────────────┐ │
│   │  Select: Mode → heat                      │ │
│   └───────────────────────────────────────────┘ │
│   ┌───────────────────────────────────────────┐ │
│   │  Select: Server Room Preset → failsafe    │ │
│   │  Select: Living Room Preset → comfort     │ │
│   │  Select: Bedroom Preset → comfort         │ │
│   └───────────────────────────────────────────┘ │
│   ┌───────────────────────────────────────────┐ │
│   │  Number: Comfort Heating Target → 70°F    │ │
│   │  Number: Comfort Cooling Target → 72°F    │ │
│   │  Number: Eco Heating Target → 65°F        │ │
│   │  Number: Eco Cooling Target → 78°F        │ │
│   │  Number: Failsafe Heating Target → 60°F   │ │
│   │  Number: Failsafe Cooling Target → 85°F   │ │
│   └───────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```
