# Multi-Zone Mini-Split Thermostat

A Home Assistant custom integration that creates a virtual thermostat to manage multiple mini-split climate entities with per-entity preset control.

## Features

- **Group multiple climate entities** under a single virtual thermostat
- **Unified HVAC mode** - all underlying entities share the same mode (heat, cool, or off)
- **Global preset temperatures** - define heating and cooling target temperatures for each preset (comfort, eco, failsafe), shared across all entities
- **Per-entity preset selection** - each underlying entity can independently be set to a different preset
- **HACS compatible** - easy installation via HACS

## How It Works

This integration creates a virtual climate entity that groups multiple mini-split units. Since mini-splits don't have direct impact on whether equipment is running (they just receive settings), this integration focuses on managing and coordinating the settings across all your units.

- When you change the **HVAC mode** on the virtual thermostat, it propagates to all underlying entities
- **Preset temperatures** (heating/cooling targets) are configured globally per preset and shared across all entities
- Each underlying entity independently tracks which **preset** it's currently using (comfort, eco, or failsafe)
- The virtual thermostat displays the **average** of all current and target temperatures

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
| `presets` | No | Global preset temperature configuration (shared across all entities) |
| `heat_temp` | No | Target temperature when in heat mode for this preset (default: 68°F) |
| `cool_temp` | No | Target temperature when in cool mode for this preset (default: 74°F) |
| `entities` | Yes | List of climate entities to manage |
| `entity_id` | Yes | The climate entity ID (e.g., `climate.living_room`) |
| `default_preset` | No | Default preset for this entity when the integration starts (default: `comfort`) |

## Services

### `multizone_minisplit_thermostat.set_entity_preset`

Set the preset for a specific underlying climate entity. This allows you to change the temperature target for individual zones independently.

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

# Set living room to comfort mode
service: multizone_minisplit_thermostat.set_entity_preset
data:
  entity: climate.living_room_minisplit
  preset: comfort
```

#### Automation Example

```yaml
# Set all zones to eco when leaving home
automation:
  - alias: "Set all zones to eco on leave"
    trigger:
      - platform: state
        entity_id: person.homeowner
        to: "not_home"
    action:
      - service: multizone_minisplit_thermostat.set_entity_preset
        data:
          entity: climate.bedroom_minisplit
          preset: eco
      - service: multizone_minisplit_thermostat.set_entity_preset
        data:
          entity: climate.living_room_minisplit
          preset: eco
```

## Entity Attributes

The virtual thermostat exposes the following attributes:

| Attribute | Description |
|-----------|-------------|
| `entity_presets` | Current preset for each underlying entity (dict mapping entity_id to preset name) |
| `entity_target_temps` | Current target temperature for each underlying entity based on its preset and mode |
| `entities` | Detailed state of each underlying entity including preset, target temp, and raw state |

## Presets

| Preset | Description |
|--------|-------------|
| `comfort` | Normal comfort temperatures for occupied spaces |
| `eco` | Energy-saving temperatures for unoccupied or sleeping periods |
| `failsafe` | Extreme temperatures to prevent pipe freezing or overheating during equipment failures |

## Architecture

```
┌─────────────────────────────────────────┐
│   Virtual Thermostat (this integration)  │
│                                          │
│   Mode: HEAT (shared across all)         │
│   Target Temp: 69°F (average)            │
│                                          │
│   ┌─────────────┬──────────────────┐     │
│   │ Entity      │ Active Preset    │     │
│   ├─────────────┼──────────────────┤     │
│   │ climate.lr  │ comfort → 70°F   │     │
│   │ climate.br  │ eco → 65°F       │     │
│   │ climate.kt  │ comfort → 70°F   │     │
│   └─────────────┴──────────────────┘     │
└─────────────────────────────────────────┘
```
