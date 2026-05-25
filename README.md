# Multi-Zone Mini-Split Thermostat

A Home Assistant custom integration that creates a virtual thermostat to manage multiple mini-split climate entities with per-zone preset control.

## Features

- **Group mode control** - set heat, cool, or off mode for all mini-splits at once
- **Per-zone preset selectors** - each zone has its own select entity for preset (comfort, eco, failsafe)
- **Global preset temperatures** - define heating and cooling targets for each preset, shared across all zones
- **HACS compatible** - easy installation via HACS

## Architecture

This integration creates two types of entities:

1. **Climate entity** (group controller) - manages HVAC mode (heat/cool/off) for all underlying entities, shows average current temperature, and exposes per-zone state as attributes
2. **Select entities** (one per zone) - control the active preset for each individual zone

Temperature targets are derived from the global preset configuration and the currently active preset for each zone. The climate entity does not expose a target temperature or preset mode directly since those are managed per-zone.

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
   - Add climate entities one by one, selecting a default preset for each

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
    entities:
      - entity_id: climate.living_room_minisplit
        default_preset: comfort
      - entity_id: climate.bedroom_minisplit
        default_preset: eco
      - entity_id: climate.kitchen_minisplit
        default_preset: comfort
```

## Configuration Options

| Key | Required | Description |
|-----|----------|-------------|
| `name` | Yes | Display name for the virtual thermostat |
| `presets` | No | Global preset temperature configuration (shared across all zones) |
| `heat_temp` | No | Target temperature when in heat mode for this preset (default: 68°F) |
| `cool_temp` | No | Target temperature when in cool mode for this preset (default: 74°F) |
| `entities` | Yes | List of climate entities to manage |
| `entity_id` | Yes | The climate entity ID (e.g., `climate.living_room`) |
| `default_preset` | No | Default preset for this zone when the integration starts (default: `comfort`) |

## Entities

### Climate Entity (Group Controller)

The main climate entity provides:
- **HVAC mode control** - heat, cool, or off (propagates to all zones)
- **Current temperature** - average across all underlying entities
- **Attributes** - per-zone preset, target temperature, and raw state

### Select Entities (Per-Zone Preset)

One select entity is created for each zone:
- **Name**: `{Thermostat Name} - {Zone Name} Preset`
- **Options**: `comfort`, `eco`, `failsafe`
- **Attributes**: underlying entity ID, current target temperature

Changing the select updates the zone's preset, which recalculates its target temperature based on the global preset configuration and current HVAC mode.

## Services

### `multizone_minisplit_thermostat.set_entity_preset`

Set the preset for a specific underlying climate entity (alternative to using the select entity).

| Field | Required | Description |
|-------|----------|-------------|
| `entity` | Yes | The underlying climate entity ID |
| `preset` | Yes | The preset to apply (`comfort`, `eco`, or `failsafe`) |

#### Example

```yaml
# Set bedroom to eco mode (energy saving)
service: multizone_minisplit_thermostat.set_entity_preset
data:
  entity: climate.bedroom_minisplit
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
│   Mode: HEAT (controls all zones)        │
│   Current Temp: 71°F (avg)              │
│                                          │
│   Attributes:                            │
│   - entity_presets: {...}                │
│   - entity_target_temps: {...}           │
│   - entities: {...}                      │
└─────────────────────────────────────────┘
          │
          ├──▶ Select: LR Preset → comfort (70°F)
          ├──▶ Select: BR Preset → eco (65°F)
          └──▶ Select: KT Preset → comfort (70°F)
```