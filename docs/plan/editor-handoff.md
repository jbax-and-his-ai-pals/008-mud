# Editor authoring handoff — 2026-09-22

## Start here

This is the current handoff for the editor-authoring push. Read it with the
[authoring roadmap](game-authoring-roadmap.md) for gates, the
[coverage ledger](editor-coverage-ledger.md) for declaration-level truth, and
[chunks of work](chunks-of-work.md) for the ordered queue. This note records the
current working tree; it does **not** claim that any milestone is closed.

The immediate objective is an editor that can safely author the supported engine,
then prove Fantasy Frontier, a contrasting content set, a late rules change, and a
test candidate. It is not a promise that arbitrary new mechanics can be built by
editing JSON in the UI.

## Current estimate

These are planning estimates, not substitute evidence. The status ladder in the
coverage ledger (absent → read-only → prototype → validated writer → journey-proven)
is the authoritative measure.

| Milestone | Rough progress | What is genuinely in place | What keeps it open |
|---|---:|---|---|
| M0 — trust an edit | ~90% | Draft/dirty/cancel flows, staged engine validation, recovery/checkpoints, configuration dialog smoke coverage and several real save-failure paths. | Mandatory human visual/interaction pass, broader external-change and unsupported-value retests, and the headless resource-retention warning. |
| M1 — coherent game | ~92% | Scaffold/copy, start and opening authoring, active-set switching, external-root registration, basic reverse index, guarded rename/delete, and a coordinated manifest/ruleset capability transaction. | Broader dependency/impact coverage, clear affected-flow reporting for every system switch, opaque/unindexed reference treatment, and complete lifecycle human proof. |
| M2 — author Fantasy Frontier | ~38% | Strong world/district tooling; substantial NPC, item, contract, ability, dialogue, advancement, weather selection and first combat-retreat surfaces. | Most generation, policy, campaign/knowledge, presentation/profile and runtime-journey coverage remains; many ledger rows are still absent or prototype. |
| M3–M5 | 0–10% | Existing alternate sets and validation/checkpoint foundations provide useful fixtures. | Contrasting authored journeys, rehearsal of a late rules migration, export/test-candidate workflow and independent human retest are not yet built. |

## Work completed in the current uncommitted batch

- Added registered external content-set roots: authors may add an exact
  manifest-bearing folder to the chooser and later forget its registration without
  scanning, moving, or deleting anything outside the project root.
- Added a structured opening editor for heading, introduction and objectives. Its
  draft validates scenario/start alignment and basic objective structure before a
  staged engine verdict.
- Made capability changes coordinate matching explicit `ruleset.systems` values in
  one staged, recoverable two-file transaction. Disabling a capability preserves
  related content as inactive; it does not delete it.
- Added typed ruleset controls for combat retreat policy and a ruleset-backed
  weather-profile picker in region authoring.
- Extended the current hardening work with NPC runtime-shape validation and typed
  inspector surfaces for behavior, patrols, spells, inventory, vendor data, gifts,
  dialogue bindings/topics, faction and related tuning.

## Verified evidence

Run these from the repository root. The Godot path is explicit because the bundled
editor test launcher needs a Python interpreter for several checks.

```powershell
$godot = 'C:\Users\baxte\Downloads\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe'
$python = 'C:\Users\baxte\AppData\Local\Programs\Python\Python312\python.exe'

& $godot --headless --path mud-world-editor --script tests/external_content_set_roots_smoke.gd -- --python $python
& $godot --headless --path mud-world-editor --script tests/opening_editing_smoke.gd -- --python $python
& $godot --headless --path mud-world-editor --script tests/manifest_editing_smoke.gd -- --python $python
& $godot --headless --path mud-world-editor --script tests/configuration_dialog_smoke.gd -- --python $python
& $python -m unittest server.tests.singles.test_configuration_save -v
& $python -m unittest server.tests.singles.test_content_set_validator -v
& $python toolkit/run_content_checks.py
```

Focused smoke and Python tests above passed in this working sequence. The
configuration-dialog smoke also exits with Godot ObjectDB/resource-retention
notices (most recently 35 objects / 17 resources) after reporting zero test
failures. Treat this as a M0 investigation item, not as a passing usability signoff.
The content gate passes with its existing, known warnings (for example the fantasy
mage-set dangling references); warnings are not silently converted into success.

## Recommended next sequence

1. **Close M0 evidence, not more fields.** Run the focused smoke suite and a
   deliberate human pass on normal, narrow and ultrawide layouts. Exercise modal
   focus/escape, error wrapping, disabled/enabled states, cancel/reopen, an invalid
   staged save, set switch with drafts, and external file change handling. Diagnose
   the headless resource-retention report if reproducible outside test shutdown.
2. **Finish M1’s impact story.** Extend the reverse index rather than inventing
   ad-hoc delete rules. Surface indexed coverage and opaque-reference limits in the
   UI; make system changes name affected flows/content, while retaining inactive
   content. Keep manifest paths deliberately read-only unless a safe path-migration
   design is explicitly approved.
3. **Advance M2 by activity slice.** The next high-leverage slice is typed weather
   profiles/descriptions plus their consumers, then the remaining combat/system
   policy fields only after engine validators exist. Follow with campaigns and
   knowledge. Each slice needs a nontrivial edit, reopen, engine validation,
   recovery, and a runtime journey—not merely another form.

## Guardrails for the next conversation

- Preserve unknown fields and unsupported nested values. A missing form is not
  authorization to normalize or delete content.
- Do not mark M0/M1 100% before the stated human gates. Headless green is
  necessary but not sufficient.
- Keep technical IDs stable behind names in normal UI. Use the dependency index for
  rename/delete decisions and show its coverage limits.
- System names such as magic, devices, gems or weather are theme-level expressions
  of engine contracts; do not generalize by creating a parallel fantasy-only kernel.
- New authorable fields need an engine reader, validator, typed draft/widget,
  save/recovery test and runtime evidence. Update the coverage ledger in the same
  change.
- The working tree is intentionally dirty. Inspect `git status --short` before
  rebasing, committing or beginning unrelated cleanup; do not discard existing
  changes or the generated `.uid` files casually.

## First commands for a new owner

```powershell
git status --short
git log --oneline -12
git diff --check
```

Then read the changed ledger rows and run the smallest relevant evidence command
before expanding scope. Keep commits narrow: engine validator/contract, editor
surface, regression evidence, and documentation should tell one coherent story.
