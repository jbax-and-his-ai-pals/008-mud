# Mud-World-Editor Gap Matrix

## Purpose

Map current `mud-world-editor` capability against runtime/toolkit contracts so we can prioritize editor-path worldbuilding.

## Current Signals (Codebase Audit)

- Editor project exists: `C:\python\old\restart\mud-world-editor`
- Uses mixed un-packaged data files (`world_layout.json`, region JSONs, templates, quests).
- Runtime/toolkit now rely on stronger validators and profile-aware behavior.

## Gap Matrix

1. Canonical Data Contract
- Current: editor targets older un-packaged `world.json`/custom region files.
- Needed: explicit export contract aligned with current runtime data schema + validator inputs.
- Priority: P0

2. Validator Integration
- Current: no clear direct call path from editor to `data_integrity_validator.py` and `reference_integrity_validator.py`.
- Needed: editor export preflight that runs both validators and surfaces actionable errors.
- Priority: P0

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
