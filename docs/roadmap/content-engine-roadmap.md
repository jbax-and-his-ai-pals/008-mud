# Content Engine Roadmap

## Product charter

Build a reusable engine for authored text-first games. A **content set** is a complete game: it defines its world, playable structure, rules, scenarios, and presentation. The engine supplies stable runtime services and authoring contracts; it does not assume that every game is fantasy, multiplayer, combat-heavy, or persistent.

The first canonical content set is **Fantasy Frontier**. It is both a substantial playable fantasy game and the reference implementation used to evolve the engine. Later canonical sets can explore modern, western, space, horror, or other genres without requiring genre branches in engine code.

This document is the active product roadmap. The earlier phase documents and `next-session.md` remain useful implementation history, but they no longer define priority or completion.

## The boundary we are building

```text
Engine
  session, save/load, simulation, commands, events, UI protocol,
  content loading, validation, accessibility, authoring/export contracts

Content set
  world, actors, items, ruleset choices, progression, scenarios,
  narrative, enabled capabilities, presentation, fixtures, tests

Theme
  the visual/audio/accessibility presentation selected by a content set
```

An engine feature is justified only when it serves more than one plausible content set or is needed by the engine contract itself. A fantasy-specific mechanic belongs in Fantasy Frontier unless it has been deliberately generalized as a capability.

## Content-set contract

Every shipped or development content set must be a versioned package with a manifest. Its minimum contract is:

| Area | Content-set responsibility |
| --- | --- |
| Identity | Stable ID, title, version, engine API range, dependencies and migrations |
| Rules | Selected capabilities, rule parameters, progression, economy, time, conflict resolution, death/failure model |
| World | Regions, locations, connections, map metadata, actors, items, factions, encounters, and mutable-world policy |
| Play structure | Start scenarios, goals, quests/cases/jobs, progression gates, endings or ongoing-play policy |
| Interaction | Enabled verbs, vocabulary, skill/activity definitions, conversation and action affordances |
| Presentation | Theme, UI copy, typography/palette/assets, audio hooks, accessibility descriptions and defaults |
| Quality | Reference validation, deterministic fixtures, smoke scenarios, compatibility snapshots, migration tests |

The initial manifest shape should be deliberately small:

```json
{
  "id": "fantasy_frontier",
  "version": "0.1.0",
  "manifest_schema_version": "1",
  "engine_api_min": "1.0",
  "engine_api_max": "1.0",
  "title": "Fantasy Frontier",
  "paths": {
    "data_root": "../../server/data",
    "ruleset": "rules/ruleset.json",
    "presentation": "presentation/default.json"
  },
  "start": {
    "scenario_id": "arrival_in_town",
    "region_id": "town",
    "room_id": "town_square"
  },
  "capabilities": ["inventory", "quests", "combat", "magic", "crafting"],
}
```

The initial `paths.data_root` may temporarily point outside the package while legacy server data is being extracted. That is a transition adapter, not the final package layout. Rules should be data-driven where practical. When a rule genuinely needs code, it should use a narrow, documented, engine-owned capability adapter—not unrestricted content-set Python executed in the server process.

## Canonical content sets

### 1. Fantasy Frontier — the reference game

Fantasy Frontier is the first complete game, not throwaway sample data. It should contain enough authored content to test exploration, social interaction, progression, economy, quests, conflict, world state, and presentation at meaningful scale.

Its responsibility is to answer: “Can a creator make a coherent full game with this engine?” It is the source of reference fixtures, authoring examples, and player-facing design iteration.

### 2. Modern Capsule — the abstraction test

The second set should be small and intentional, not another large production game. A modern-noir investigation, small-town contemporary drama, or similar capsule should use locations, people, jobs/cases, reputation, dialogue, and possibly vehicles—while omitting fantasy assumptions such as spells, monsters, and loot loops.

Its purpose is to expose hidden fantasy coupling. It succeeds when it can be authored and played without adding `if modern` branches to the engine.

### 3. Future canonical sets

Western, space, and other themes are candidates only after the first two sets demonstrate a stable package boundary and authoring workflow. Each should be proposed as a content-set design brief before engine features are added.

## Delivery sequence

### Milestone A — Make one runtime path dependable

**Goal:** A developer can bootstrap one supported environment and play a small server/client loop reliably.

- Publish one supported Python version and dependency lockfile.
- Separate optional AI, Pygame UI, MessagePack, and server dependencies from the headless core.
- Repair the content preflight and make it runnable in a clean checkout.
- Establish one explicit development launch command; remove dependence on stale fixture markers and silent missing configuration.
- Restore meaningful tests for launcher, transport, persistence, accessibility, and client contracts.

**Gate:** a clean machine can load a selected content root, create a character, move, interact, save, reload, and run the relevant automated checks.

### Milestone B — Define and load the content-set package

**Goal:** The selected game is explicit and validated before the world boots.

- Add the manifest schema, version policy, and structured validation output.
- Introduce a `GameDefinition`/content-set loader that resolves all paths from one selected package root.
- Replace process-global data-root rewrites with instance-scoped content resolution.
- Make a missing, invalid, or incompatible content set a clear startup failure.
- Define capability registration and ruleset configuration independently from transport/server profiles.

**Current implementation:** `--content-set <directory-or-manifest>` now validates and selects a package for the headless, TCP, and WebSocket startup paths. Fantasy Frontier now carries a packaged `data/` root rather than pointing at `server/data`. The headless boot path uses instance-scoped content paths for definition, spell, quest, campaign, knowledge, collection, crafting, and item-set loading; it no longer rewrites imported data-path constants through `sys.modules`. Legacy Pygame/save/debug paths still need the same migration before the global path model can be retired everywhere.

**First genre-neutral seam:** A selected package's declared capabilities now govern optional system loading and player-facing access. A game without `magic` neither loads spell definitions nor exposes mana, spells, or magic help. A game without `crafting` does not construct its crafting manager or show crafting help. A game without `quests` may omit both `quests/` and `campaigns/` and does not construct their managers. A game without `combat` hides combat status and rejects combat commands. The package ruleset now controls presentation and command availability for level-based progression and economy: a `progression_model` of `none` omits class, level, XP, RPG stats, and skills from text, structured status, and help; `economy.enabled: false` omits currency and trade commands. On creation and loading, inactive systems are also normalized out of player state—no default spells/mana, combat values, progression state, currency, or quest/campaign state. The remaining underlying player-model, dialogue, and client-facing assumptions still need the same treatment; this is a tested boundary, not a claim that all runtime behavior is capability-driven.

**Gate:** `--content-set <id-or-path>` selects a game deterministically; no gameplay data is loaded from ambient working-directory defaults.

### Milestone C — Extract Fantasy Frontier

**Goal:** Existing fantasy content becomes the first canonical package without losing gameplay.

- Move or package current fantasy regions, actors, items, quests, campaigns, presentation assets, and profiles beneath `content_sets/fantasy_frontier`.
- Resolve current content warnings: duplicate spell IDs, item-schema ambiguity, and fixture-path drift.
- Define the fantasy ruleset explicitly rather than inferring it from permissive runtime defaults.
- Author a compact, repeatable opening scenario and a representative longer progression path.
- Create canonical save fixtures and content-set smoke scenarios.

**Gate:** Fantasy Frontier launches through the content-set loader and remains the source for reference tests and design iteration.

**Current implementation:** `server/launch_content_set.py` is the deterministic TCP/WebSocket launch entry point and defaults to Fantasy Frontier. Its dry-run contract is tested. Fantasy Frontier's package-owned opening brief is shown after character creation; the canonical journey smoke test verifies the Town Square, opening cast, and movement to the North Gate Road. Saves now record the selected content-set ID/version and reject a mismatched game at load time.

### Milestone D — Deliver the reference-game vertical slice

**Goal:** A player can install/run Fantasy Frontier as a coherent game.

- Make the offline launcher actually start or attach to the correct local runtime and transport.
- Align client/server protocol versions and transport behavior.
- Complete a polished first-session path: launch, create character, learn controls, explore, interact, progress, save, resume.
- Keep finite-story play as the default delivery lane; treat co-op and persistent operation as opt-in capabilities.
- Validate the player journey in Godot runtime rather than source-regex contract tests alone.

**Gate:** a new player can complete a representative session without operator commands, manual port changes, or undocumented setup.

### Milestone E — Prove the engine with Modern Capsule

**Goal:** Validate that the package model is genre-neutral.

- Write a one-page game/content brief before implementation.
- Author a small modern content set using the same manifest, loader, validation, editor export, client, and save systems.
- Add only general engine capabilities proven necessary by both games.
- Reject genre-specific leakage into core APIs.

**Gate:** both Fantasy Frontier and Modern Capsule launch from the same executable using only content-set selection.

**Current implementation:** `content_sets/modern_capsule` is now a small present-day exploration and dialogue package: a transit plaza, café, library walk, two authored people, and ordinary inventory items. It intentionally declares only `inventory` and `dialogue`; its regression journey creates a character, receives the package opening, speaks with Maya, and enters the café. It is a deliberately small proof, not yet a full second reference game.

### Decoupling completion program

The current capability work is a safe compatibility layer around a legacy fantasy-RPG runtime. Finishing the separation requires four larger, ordered chunks rather than more command-by-command gates.

1. **Canonical game contract.** Replace the loose manifest capability list plus ad-hoc ruleset keys with one validated, normalized game contract: enabled systems, progression/economy policy, player-facing labels, UI sections, and supported commands. The server emits that contract at connection time. Gate: Fantasy Frontier and Modern Capsule both validate against the schema; unsupported or contradictory combinations fail before boot.

2. **Composable runtime aspects.** Split the legacy `Player` and manager construction into a neutral actor core plus opt-in magic, combat, progression, economy, quest/campaign, and crafting aspects. Saves use aspect-keyed state and migrate legacy saves. Gate: Modern creates and reloads an actor without RPG/magic/combat fields; Fantasy preserves its current journey and save behavior.

3. **Package-scoped command catalog.** Replace process-global command registration and HeadlessServer's handwritten command maps with command descriptors resolved against the game contract. Help, completion, execution, and the client command palette consume the same catalog. Gate: disabled commands are neither registered for the active game nor discoverable through help, aliases, or completion.

4. **Capability-driven client shell.** Have Godot consume the game contract to render status fields and show/hide panels, quick actions, quest/adventure UI, and theme labels. Remove hard-coded Level/XP/MP and quest assumptions from the main controller. Gate: switching only `--content-set` produces a correct Fantasy or Modern UI in a live client smoke test.

After those four chunks, package authoring/export and content-set-isolated save storage become the next productionization slice.

### Milestone F — Creator pipeline and safe distribution

**Goal:** A creator can author, validate, package, and share a content set.

- Make the world editor export the content-set contract directly and deterministically.
- Provide schema-aware validation, migration, preview, and playable smoke scenarios.
- Define pack versioning, dependency resolution, signing/trust policy, and compatibility reporting.
- Treat code-bearing extensions as trusted until a real isolation boundary exists.
- Harden authored-asset handling with strict SVG/XML allowlisting and clear provenance rules.

**Gate:** Fantasy Frontier can be rebuilt from editor/toolkit output, validated, launched, and compared against its canonical fixtures.

### Milestone G — Optional service and commercial layers

**Goal:** Add only the operational features justified by the games.

- Durable persistence and restart recovery.
- Authenticated accounts and opaque session-resume tokens.
- A real background simulation clock and transport parity.
- Co-op/persistent service operation, deployment, moderation, and observability.
- Packaging, storefront, and platform-specific delivery.

**Gate:** these features are proven against a stated content-set need, with end-to-end operational tests—not just policy payloads.

## Priority rules

### Do now

1. Reproducible runtime and test baseline.
2. Content-set manifest, loader, and validator.
3. Fantasy Frontier extraction and a playable opening loop.
4. Editor-to-content-set export path.
5. Modern Capsule design brief, then its small implementation.

### Defer until the package boundary is proven

- Broad mod marketplace work.
- More theme samples.
- Steam packaging and mobile polish.
- Persistent-shard expansion, account systems, and live-service operations.
- New genre mechanics added solely for a hypothetical future game.

### Do not do

- Add more global feature-profile switches as substitutes for content-set definitions.
- Make a second large game before Modern Capsule proves the boundary.
- Call in-process arbitrary Python mods “safe.”
- Treat documentation claims or empty contract files as evidence of working behavior.

## Measures of progress

Progress is demonstrated by observable content-engine outcomes:

1. `fantasy_frontier` is a valid, playable, versioned package.
2. A second non-fantasy package works without core genre branching.
3. The editor and toolkit can produce a package that the runtime accepts.
4. A clean checkout can run validation and a representative player journey.
5. Save/load, protocol, and content compatibility are covered by executable tests.

## Immediate next work

The next implementation slice should be **Milestone A plus the first contract of Milestone B**:

1. Establish the supported runtime/dependency baseline.
2. Fix the broken content gate and fixture selection path.
3. Specify `content_set.manifest.json` and validator behavior.
4. Add a loader seam that can select a content-set root without mutating global engine modules.
5. Use current fantasy data as the first migration fixture; do not relocate all data until the loader contract is tested.
