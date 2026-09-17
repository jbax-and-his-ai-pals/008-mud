# Mud-World-Editor Gap Matrix

**Status note (2026-09-16):** written before the current Godot editor's
content sync and generation work (`ROADMAP.md` P8). The path in "Current
Signals" below is stale (an earlier checkout location); the editor now
lives at `mud-world-editor/` in this repo and syncs directly with
`content_sets/fantasy_frontier/`, not a separate un-packaged format. Items
1 and 2 (both P0) are substantially resolved — see the per-item notes.
Items 3–8 remain accurate open gaps.

## Purpose

Map current `mud-world-editor` capability against runtime/toolkit contracts so we can prioritize editor-path worldbuilding.

## Current Signals (Codebase Audit)

- Editor project exists: `C:\python\old\restart\mud-world-editor`
- Uses mixed un-packaged data files (`world_layout.json`, region JSONs, templates, quests).
- Runtime/toolkit now rely on stronger validators and profile-aware behavior.

## Gap Matrix

1. Canonical Data Contract
- **Resolved, differently than proposed.** The editor's `data/` is synced
  from and reads/writes the same files `content_sets/fantasy_frontier/`
  uses — there is no separate export contract because there is no
  separate format. Region files still carry an editor-only `_editor_pos`
  layout field, backfilled on load rather than treated as foreign.
- Priority: P0 — done.

2. Validator Integration
- **Substantially resolved, narrower scope than proposed.** The editor
  has a one-click "Validate Region Policy" action calling
  `engine.server.content_set.validate_region_policy()` (via
  `toolkit/region_policy_validator.py`) for fast, region-scoped feedback
  on classification/level-bands/hazard-coverage. It does not call
  `data_integrity_validator.py`/`reference_integrity_validator.py`
  directly — that whole-content-set check (reachability, cross-file
  references, dialogue wiring) stays a separate, slower pass, run outside
  the editor today.
- Priority: P0 — mostly done; full-validator integration still open.

3. Profile-Aware Authoring
- Current: no visible authoring-time checks for server profile modes (`world_mutation`, `authoring`, `combat`, `weather`).
- Needed: lint mode that flags incompatible content/settings for selected profile.
- Priority: P1

4. World Effects/Weather Authoring
- Current: unclear support for `world_effects` provider wiring and modern weather/world-field toggles.
- Needed: structured controls for disabled/builtin/custom provider selection and metadata.
- Priority: P1

5. Entity/Component Extensibility
- Current: editor appears room/region-centric with limited evidence of generalized component editing.
- Needed: component-driven authoring for extensible systems (positive/negative world-state effects, custom mechanics).
- Priority: P1

6. Pack/Mod Export Path
- Current: no explicit one-click export to toolkit pack pipeline.
- Needed: export target compatible with pack manifests and compatibility checks.
- Priority: P1

7. Collaborative/Live Authoring Bridge
- Current: runtime has lock/event protocol; editor integration path is not obvious.
- Needed: optional bridge mode (`editor -> server`) using lock/update envelope contracts.
- Priority: P2

8. UX for New Creators
- Current: no guided flow equivalent to setup wizard path.
- Needed: "create first region/world" templates and step-by-step checks.
- Priority: P2

## Recommended Sequencing

1. P0: Canonical export contract + validator integration.
2. P1: Profile-aware lint + world-effects/weather + component extensibility + pack export.
3. P2: Live bridge and onboarding polish.

## Definition of Done (Editor Track Increment)

- Editor can produce artifacts that pass runtime validators without manual JSON edits.
- Exported world can be loaded by server and exercised by client with profile-consistent behavior.
