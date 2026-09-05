# Multi-Modal 1-Bit MUD Engine Brief

## Core Vision

- Aesthetic: 1-bit minimalist terminal feel with subtle atmosphere.
- Architecture: authoritative Python server + dumb Godot GUI-first client.
- Identity: rich-client MUD platform with a single modern transport contract.
- Extensibility: live player authoring with GM system toggles (for example blight/permadeath).
- Flexibility: a Swiss-army platform that supports different text-game philosophies, not a single fixed ruleset.

## Technical Direction

- Server: Python headless runtime.
- Client: Godot 4.x primary client.
- Persistence: SQLite + JSON hybrid, memory-resident runtime with async persistence pipeline.
- Data: YAML/JSON object-component templates + SVG for 1-bit player-authored assets.
- Transport:
  - Rich client: WebSocket or TCP socket with binary serialization (MessagePack/Protobuf).

## Architecture Pillars

1. Dumb Client Rendering
- Server controls state and semantics.
- Client renders 1-bit visuals, text effects, and atmospheric audio.

2. Server-Side Truth
- Component-based entities (data-driven behaviors).
- Background heartbeat systems (including blight propagation).
- Multi-modal output translation by client capability.
- Feature-profile gating for optional systems (combat/weather/authoring/world mutation/mod runtime).

3. SVG UGC Loop
- Godot authoring UI -> Python validation/storage -> broadcast/update to clients.
- Runtime SVG rasterization in client + 1-bit post shader for style consistency.

## Operator Choice Principles

- Live authoring is optional, never mandatory.
- Combat can be disabled for non-combat worlds.
- Weather can be builtin, custom-defined, or disabled.
- Worlds can run in fully readonly/static mode.
- External editor pipelines (such as `mud-world-editor`) are first-class alongside in-client tools.

## Non-Goals (Default Runtime Assumptions We Avoid)

- No assumption that every server wants combat.
- No assumption that every server wants mutable worlds.
- No assumption that every server wants weather simulation.
- No assumption that in-session `@` commands are always enabled.

## Immediate Priorities

1. WebSocket/JSON bridge baseline for Godot-Python integration.
2. Resource-to-SQLite serialization path.
3. RichTextEffect template for atmospheric text corruption.
4. SVG ingestion, validation, broadcast, and runtime rendering pipeline.
