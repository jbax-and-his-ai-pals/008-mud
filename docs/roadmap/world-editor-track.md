# World Editor Track

## Goal

Make worldbuilding first-class for creators who prefer editor workflows over live `@` commands.

## Scope

- Extend `mud-world-editor` toward a supported pipeline.
- Keep parity with headless runtime data contracts and validation.
- Support both static world authoring and optional live sync workflows.

## Checklist

- [ ] Audit current `mud-world-editor` capabilities vs runtime schema contracts.
- [ ] Define canonical import/export contracts (`world.json` migration + new structured formats).
- [ ] Add region/room/entity graph editing with integrity validation.
- [ ] Add authoring UX for exits, NPC spawns, loot tables, and interaction hooks.
- [ ] Add world-effects/weather authoring controls (including disabled/custom modes).
- [ ] Add profile-aware linting (for example static worlds with mutation disabled).
- [ ] Add one-click pack/export path compatible with toolkit validators.
- [ ] Add regression tests for editor-exported content compatibility.

## Exit Gate

- [ ] A creator can build, validate, and export a complete playable world without manual JSON surgery.

## Initial Artifact

- Compatibility audit and priorities: [world-editor-gap-matrix.md](C:/python/old/restart/docs/roadmap/world-editor-gap-matrix.md)
