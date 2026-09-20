# Operator Profile Recipes

These recipes are baseline server-level configurations for common game styles.  
Each recipe is a JSON feature profile loaded by the authoritative server.

Profile files:
- `content_sets/fantasy_frontier/data/profiles/static_world.profile.json`
- `content_sets/fantasy_frontier/data/profiles/creative_world.profile.json`
- `content_sets/fantasy_frontier/data/profiles/social_no_combat.profile.json`
- `content_sets/fantasy_frontier/data/profiles/mobile_low_fx.profile.json`

## Static World

Use when you want a fixed world with no live edits and minimal runtime variance.

- `world_mutation.mode`: `readonly`
- `authoring.mode`: `disabled`
- `mods.mode`: `disabled`
- `weather.mode`: `disabled`
- `world_field.mode`: `disabled`
- `world_effects.mode`: `disabled`

## Creative World

Use when you want collaborative building, mutable systems, and mod extension.

- `world_mutation.mode`: `mutable`
- `authoring.mode`: `all`
- `mods.mode`: `enabled`
- `weather.mode`: `builtin`
- `world_field.mode`: `enabled`
- `world_effects.mode`: `enabled`

## Social No-Combat

Use for social/story worlds where conflict systems are off but world evolution remains on.

- `combat.mode`: `disabled`
- `authoring.mode`: `gm_only`
- `world_mutation.mode`: `mutable`
- `mods.mode`: `enabled`
- `world_field.mode`: `custom`
- `world_effects.mode`: `custom` (`provider_id`: `sample.effects.balance`)

## Mobile Low-FX

Use for constrained devices or accessibility-first reduced-effect servers.

- `weather.mode`: `disabled`
- `world_field.mode`: `disabled`
- `world_effects.mode`: `disabled`
- `world_mutation.mode`: `readonly`
- `authoring.mode`: `gm_only`
- `mods.mode`: `disabled`

## How To Apply

1. Copy `server/config/server_config.example.json` to `server/config/server_config.json`.
2. Set `feature_profile.path` to one of the profile files.
3. Start server (`poc_server.py` / `poc_ws_server.py`) with `--config`.

For `authoring.mode = gm_only`, grant GM authoring capability at session bootstrap:
- Add `"session": { "default_capabilities": ["authoring.gm"] }` to `server/config/server_config.json`.
- This applies to new sessions and enables live authoring commands/envelopes under GM-only mode.

Alternative (runtime elevation):
- Set `"session": { "gm_auth_token": "<strong token>" }` in config.
- In-client, run `gm auth <token>` to grant `authoring.gm` to the current session.

Profile selection:
- Set `paths.feature_profile` in the selected content-set manifest; transport configuration does not override it.

Runtime check:
- In a TCP or WebSocket session, run `server policy` to receive the active profile source, startup warnings, and effective policy/provider flags.

Runtime profile management (PoC):
- `profile list` (or `profiles`) to list available preset names from `content_sets/fantasy_frontier/data/profiles/`.
- `profile apply <preset_name>` to apply a preset at runtime.
- Client shell safety flow: entering `profile apply <preset_name>` prompts for `profile apply confirm` (or `profile apply cancel`) before sending.
