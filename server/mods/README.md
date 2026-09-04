# Mods

This folder contains example runtime mods for the server.

## Included Example

- `sample_weather_provider`
  - Registers custom weather provider id: `sample.weather.static_clear`
  - Capability required: `system_provider_registration`
  - Behavior: forces weather to `clear`/`mild` on each time-period transition
- `sample_world_effects_provider`
  - Registers custom world-effects provider id: `sample.effects.balance`
  - Capability required: `system_provider_registration`
  - Behavior: seeds a negative (`blight`) and positive (`sanctity`) field pair and runs builtin propagation/interactions

## Manifest Contract (v1)

Each mod must provide `manifest.json` with:

- `plugin_id`
- `name`
- `version`
- `manifest_schema_version` (currently `"1"`)
- `engine_api_min` (for example `"1.0"`)
- `engine_api_max` (for example `"1.0"`)
- `capabilities` (array of approved capability strings)

Approved capabilities:

- `command_registration`
- `world_modification`
- `server_broadcast`
- `system_provider_registration`

## Enable The Sample Provider

Use a server profile with:

```json
{
  "weather": {
    "mode": "custom",
    "provider_id": "sample.weather.static_clear"
  },
  "mods": {
    "mode": "enabled"
  }
}
```

To enable the sample world-effects provider:

```json
{
  "world_effects": {
    "mode": "custom",
    "provider_id": "sample.effects.balance"
  },
  "mods": {
    "mode": "enabled"
  }
}
```
