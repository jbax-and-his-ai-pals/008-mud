# Platform Architecture

## Product Shape

The product is a platform, not just one game:

- `runtime/engine`: authoritative simulation + networking + persistence
- `client`: shipped player-facing application (desktop + mobile variants)
- `toolkit`: content editor, validators, packaging, publish flow
- `mod-sdk`: extension APIs, plugin hooks, capability model
- `sample-packs`: playable reference projects for different themes

## Core Style + Protocol Identity

- Visual identity: 1-bit terminal-forward presentation with subtle atmosphere.
- Interop identity: uses the rich client protocol as its single player transport path.
- Authoring identity: players can live-author worlds through guided, permissioned tooling.
- Product identity: server operators can choose feature profiles (combat/no-combat, weather/no-weather, mutable/readonly world, authoring on/off).

## Proposed Repo Direction

1. `engine/` remains the core simulation source.
2. `engine/server/` becomes canonical authoritative runtime path.
3. New `client/` module/project for the shipped player app and mobile variant.
4. New `toolkit/` module for validation, pack build, and export.
5. New `samples/` for theme demos:
   - fantasy-classic
   - sci-fi-frontier
   - cyberpunk-city
   - post-apoc-wasteland

## Architecture Boundaries

- Engine must not require rendering/UI to run.
- Client must consume versioned protocol events and tolerate partial feature mismatch.
- Client must expose platform abstraction for desktop input and mobile touch/lifecycle handling.
- Server must expose multi-modal output translation:
  - rich packets for Godot clients
- Content must be data-driven and schema-validated.
- Mods must load through explicit contracts and capability checks.
- Client (Godot or otherwise) consumes versioned protocol events.
- Core systems must be optional by policy/profile, not mandatory:
  - combat
  - weather
  - world-field simulation (blight-like or positive/neutral variants)
  - live authoring

## Feature Profile Model

Each server runs with an explicit feature profile (file- or DB-backed), for example:

- `combat.mode`: `enabled` | `disabled`
- `weather.mode`: `builtin` | `custom` | `disabled`
- `world_field.mode`: `enabled` | `disabled`
- `authoring.mode`: `all` | `gm_only` | `disabled`
- `world_mutation.mode`: `mutable` | `readonly`
- `mods.mode`: `enabled` | `disabled`

Profiles are first-class runtime inputs and must gate command routing, background tick systems, and protocol events.

## Worldbuilding Modalities

The platform must support multiple parallel worldbuilding paths:

1. Static data packs (JSON/YAML) loaded at boot.
2. External tooling/editor workflows (for example `mud-world-editor` pipelines).
3. Live in-session authoring commands (`@dig`, `@edit`, related lock/update flows).
4. Programmatic mod/plugin authoring via capability-limited APIs.

No single modality is required. Operators can combine or disable paths by profile.

## Extensibility Guardrails

- New systems should expose provider contracts (`builtin`, `custom`, `none`) instead of hard-coded manager assumptions.
- Legacy protocol support remains stable even when individual gameplay systems are disabled.
- Unknown feature payloads should degrade gracefully in clients and never hard-fail connection/session establishment.

## Persistence + Data Contracts

- Runtime state is memory-resident and authoritative.
- Persistence uses async SQLite + JSON payload strategy.
- Entity behavior is component-driven from YAML/JSON templates.
- Player-authored visual assets are SVG-first with validation before broadcast.

## Modding Levels

1. Data mods: JSON/YAML content packs only.
2. Logic mods: limited scripting/plugin extensions.
3. Full conversions: replace content/theme pack while retaining runtime API.
