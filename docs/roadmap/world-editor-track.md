# World Editor Track

**Status note (2026-09-16):** this checklist predates the current
`mud-world-editor` (Godot 4.7) and its own progress, tracked in
`ROADMAP.md` P8. Real, done: the editor's data is synced with the actual
content-set files (not a separate export format), and it can generate
seeded, classification/population-complete regions plus validate a
region against the ruleset in-editor
(`engine.server.content_set.validate_region_policy`,
`toolkit/region_policy_validator.py`). Still genuinely open, matching
items below: profile-aware linting, weather/interaction-hook authoring,
and the one-click pack/export path — the last is flagged in P8 as a real
follow-on effort, not started. Treat the items below as still-accurate
gaps, not a stale-and-superseded plan.

## Goal

Make worldbuilding first-class for creators who prefer editor workflows over live `@` commands.

## Scope

- Extend `mud-world-editor` toward a supported pipeline.
- Keep parity with headless runtime data contracts and validation.
- Support both static world authoring and optional live sync workflows.

## Checklist

- [x] Audit current `mud-world-editor` capabilities vs runtime schema contracts.
  Done as P8's "Unify the editor path" — see `ROADMAP.md`.
- [x] Define canonical import/export contracts. Resolved differently than
  envisioned here: the editor now reads/writes the real content-set files
  directly (synced from `content_sets/fantasy_frontier/`) rather than a
  separate `world.json` migration format.
- [x] Add region/room/entity graph editing with integrity validation.
  Topology generation plus connectivity validation predate this track;
  region-policy validation (classification/level-bands/hazard-coverage)
  added this session.
- [ ] Add authoring UX for exits, NPC spawns, loot tables, and interaction
  hooks. Partial: NPC population is authorable at generation time; loot
  tables and interaction hooks (dialogue/quest wiring) are not.
- [ ] Add world-effects/weather authoring controls (including disabled/custom modes).
- [ ] Add profile-aware linting (for example static worlds with mutation disabled).
- [ ] Add one-click pack/export path compatible with toolkit validators.
  Deliberately deferred — flagged in `ROADMAP.md` P8 as real, separate work
  (needs its own manifest-authoring UI), not attempted alongside generation.
- [ ] Add regression tests for editor-exported content compatibility.
  Partial: the Python-side validator has real test coverage
  (`server/tests/singles/test_region_policy_validator.py`); there is still
  no Godot-side automated test infrastructure at all.

## Exit Gate

- [ ] A creator can build, validate, and export a complete playable world without manual JSON surgery.

## Initial Artifact

- Compatibility audit and priorities: [world-editor-gap-matrix.md](world-editor-gap-matrix.md)
