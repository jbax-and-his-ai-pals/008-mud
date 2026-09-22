# From content editor to game-authoring workbench

**Planning baseline: 2026-09-21, including the current uncommitted working tree.**
This is a proposed delivery plan, not a description of features already shipped.
[`chunks-of-work.md`](chunks-of-work.md) §6 is the canonical execution queue;
this document defines its milestones, author journey, and acceptance criteria.
[`editor-readiness.md`](editor-readiness.md) separates current evidence from older
audit findings. The [authoring guide](../reference/AUTHORING_A_CONTENT_SET.md)
documents today's supported file/CLI workflow, not the future UI described here.

## 1. The target, and where to stop

The near-term target is a **trustworthy, broadly complete authoring tool for the
engine we have**: an author can reshape Fantasy Frontier, build a small different
game, revise its rules safely, and hand a reproducible candidate to testers without
routine JSON editing. This is an authoring-beta / production-candidate milestone,
not a claim of commercial readiness, balanced content, or safe live deployment.

“Modify everything about the fantasy game” means every engine-consumed declaration
used by that game has a tested authoring path, including its connections to other
declarations. A panel existing, a file loading, or an untouched file surviving a
save does **not** demonstrate this. Each supported change must survive reopening
and have the intended effect in a running game.

There is a boundary: changing supported rules, values, distributions, content,
presentation and flows is authoring. Inventing a new combat resolver, condition
operator, crafting algorithm or persistence model is engine work. The editor must
explain that boundary, not offer arbitrary strings or a script box that pretends
to implement a mechanic. Unsupported fields stay visible/read-only and survive
untouched; that is an honest interim state, not completion of fantasy coverage.

Fantasy's exploration/progression design remains its design. A minimal modern
vignette must not acquire combat, levels, gems, or an economy just to satisfy the
tool's defaults. Use existing sets as contrasting proofs before expanding them.

## 2. One author's complete journey

The workbench should provide these destinations with a persistent active-set name,
dirty state, and readiness summary. They need not become six new modal windows;
reuse the world canvas, content library and configuration surfaces.

| Author's step | Workbench experience to build | Evidence before moving on |
|---|---|---|
| **Create the project** | Choose minimal starter, versioned system preset, or full copy. Name the game, choose paths, opening/start location and player-facing terminology. Explain what is copied and which references it needs. | Fresh set opens and boots; no references back to its source set; source remains unchanged. |
| **Decide the experience** | A small design brief: player activities, first session, success/failure, time model, intended scale, systems deliberately absent. A Systems view shows enabled capabilities, effective rules, dependencies and prerequisites. | Manifest and ruleset agree; unresolved requirements are explicit. A design brief is documentation, not a new executable flow language. |
| **Build one playable loop** | Define necessary contracts, then a few rooms, one interaction, inputs/rewards and an opening that leads to them. Link existing dialogue, quest, recipe and work-job flows. | Author launches a disposable test session, completes the loop and sees the expected state changes; failure/retry also works. |
| **Bring the world to life** | Grow regions/districts, room prose and connections; populate NPCs, encounters, items, loot, generation pools, relationships and discoveries. Search and “used by” link those surfaces. | No accidental orphan/blocked content, broken geometry or lost references; names and descriptions survive generate/reroll/edit. |
| **Iterate on the game** | Tune values or propose a system overhaul; preview dependencies, consequences and migrations before applying. Compare seeded samples and playtest scenarios. | Both old content and newly authored content behave as intended; save compatibility has an explicit decision. |
| **Prepare a test release** | Save/checkpoint, run scoped checks and player journeys, build a versioned candidate with manifest, compatibility requirements, assets and validation report. | Another machine can open/boot it; original project and player saves are not modified by packaging or tests. |

Readiness is a checklist, not a compulsory linear wizard. Authors can work out of
order and retain incomplete drafts. Do not confuse “saved draft” with “valid to
play” or “ready to release.” Validation must identify whether it checked disk or
the staged draft and mark its results stale after relevant edits.
Persist incomplete drafts separately from runtime-consumed declarations until
their apply gate passes; do not weaken the engine's validation to accommodate an
unfinished form. Inactive content likewise needs an engine-defined handling policy,
not a UI-only excuse to ignore broken references.

## 3. The model the UI must make understandable

Keep five layers distinct, with links between them:

1. **Engine primitives and validators** define the supported operations, shapes,
   numeric types, ranges, closed vocabularies and runtime semantics.
2. **Game systems/ruleset** select capabilities and their policies: combat,
   crafting, advancement, social, crime, weather, time and so on. The manifest and
   ruleset are coordinated views of one effective configuration, not independent
   toggles allowed to contradict each other.
3. **Contracts and reusable profiles** declare resources, stat roles, item
   families, attack/defense/effect/ability/work definitions and generation rules.
4. **Authored templates and world content** provide names, prose, recipes,
   encounters, districts, quests, dialogue and their references to those contracts.
5. **Runtime instances and player state** hold owned items, resolved rolls, active
   jobs, relationships, progress and saves. Editing a template does not silently
   rewrite these. Compatibility rules must say which values are frozen or resolved
   again; the current runtime behavior must be inventoried before promising either.

**Recommended preset policy:** instantiate a versioned snapshot into a content
set, with provenance. It becomes locally owned; changing the source preset never
changes existing games automatically. Offer explicit diff-and-upgrade later.
Live cross-set inheritance and arbitrary author plugins are not prerequisites.
In the UI, distinguish a default, an inherited engine value, and a local override;
“Reset to default” is an explicit change with an impact preview.

“Magic,” “devices,” and other player-facing names belong to presentation or a
system configuration, not new kernel branches. The existing `magic` and `abilities`
paths still require a reader/precedence audit: do not rename controls and imply
those models are already interchangeable. Likewise, only expose generation
dimensions the resolver actually supports, not every dimension imaginable.

## 4. Milestones and delivery gates

Milestone IDs below are stable; execution batches are in chunks §6. All milestones
are **open**. Existing code contributes to them but does not waive their gates.
Owners use the existing [track boundaries](work-tracks.md): G editor, B engine
contracts, E systems, F proving content, H/I tests/validation, J documentation;
C joins recovery, packaging and runtime save compatibility. K resolves design
choices rather than allowing UI defaults to make them accidentally.

### M0 — Trust an edit before adding more fields

Harden the new ruleset, contract and combat-vocabulary dialogs as well as shared
edit infrastructure. Resolve signal/refresh wiring, typed collections and nested
payloads, unknown-value preservation, enum defaults and malformed input. A blank
ID is an error to fix, never an instruction to silently drop an entry.

Use draft-based dirty tracking, cancel/revert, undo/redo where applicable, and
save/switch/close guards across **all** editor surfaces. If an external process
changed the file since it loaded, refuse to overwrite blindly and offer reload,
comparison or save-a-copy. Keep technical IDs stable behind human-readable names.

**Gate:** exercise actual controls and their save callbacks in scratch copies:
create, edit, revert, cancel, save, close/reopen and switch sets. An unrelated edit
preserves every untouched typed field; no-op save preserves bytes unless an
explicit, separately previewed migration is requested. Failed writes retain the
old file and the draft. Reopen and engine validation must succeed. A screenshot
pass checks narrow/normal/ultrawide layouts, wrapping, keyboard/focus behavior and
disabled states; headless smoke tests alone cannot certify usability.

### M1 — Create and configure a coherent game

Complete set identity/manifest/start/opening management; support safe copy and
rename, registered external roots and recoverable set removal. Keep label rename
separate from technical identity/reference rename. Reconcile capabilities with
ruleset activation and dependencies in one transaction.

Build the **first dependency index and change preview here**, before bulk system
editing: engine-known references with source paths, target identities and scope;
“used by,” missing references, supported rename/delete impact and unresolved
opaque references. Add staged multi-file writes and checkpoint/recovery. Expand
engine-emitted authoring metadata and validation coverage before enabling fields.

**Gate:** author creates a minimal bootable set without borrowing source-world IDs,
changes its start and one capability safely, saves/reopens, and boots the new
start. A used identifier cannot be deleted unnoticed. A failed multi-file apply
recovers the previous coherent set. System disable preserves content as inactive
and reports affected flows; it does not delete recipes, NPCs or items.

### M2 — Fantasy Frontier is fully authorable on the supported engine

Close coverage by playable activity, not by adding one more generic JSON form.
Use this minimum inventory; expand it from engine readers, manifest paths and the
actual fantasy set. Track fields, not just files or menu entries.

| Coverage family | Authoring scope and representative proof |
|---|---|
| Project and experience | Manifest, rules/profile selection, start, opening, presentation/terminology; a new character arrives with the intended defaults and guidance. |
| World | Regions, districts, rooms, exits, hazards, spawners, world layout; expand/contract/reroll with preview, preserved external links and continuity checks. Explicitly acknowledge intentional one-way/non-geometric links. |
| Characters and social | NPC templates/instances, stats, factions, behaviors, schedules, vendors, dialogue bindings, gifts/relationships; an NPC acts and responds according to the edited policy. |
| Items and generation | Families, templates, resources, loot pools, affixes/sets and supported quality/size/material distributions; seeded samples and normalized weights reveal what will be generated. Existing owned instances remain governed by the declared compatibility policy. |
| Crafting, gathering and work | Skills, stations, recipes, yields/substitutions, quality, salvage, durations and active-job semantics; gather an input, make/use an output, complete a timed job and save/reload. |
| Combat and abilities | Resources, stat roles, attacks/defenses, damage channels, hazards, costs, targeting, effects, cooldowns and learning/groups; changing a declaration demonstrably changes a real encounter. |
| Progression and flows | Backgrounds/defaults, advancement/grants, quests/rewards, dialogue conditions/effects, campaigns, titles/guilds, collections, discoveries and knowledge; complete an authored route and retain its progress after reload. |
| World/system policy | Economy, crime/locksmithing, weather/calendar, spawning, naming, elites and remaining engine-read rules; expose actual effective values and test one consumer per edited section. |

For **each** family record: engine reader, validator, widget/draft writer,
reference picker/index, unsupported fields, no-op survival test, nontrivial edit
test, runtime journey and recovery test. “Read-only,” “prototype,” “validated
writer,” and “journey-proven” are separate statuses. Do not use a single percentage
of CRUD panels as a completeness measure. The live record of this is the
[coverage ledger](editor-coverage-ledger.md).

**Gate:** on an isolated fantasy copy, edit every supported family above through
the editor, including existing rich records and newly created ones. Prove the
gather/craft/use, dialogue/quest/reward, combat/ability and discovery/advancement
routes. No shipped fantasy field is silently inaccessible or rewritten. If an
engine-used feature is deferred (campaigns, for example), record the exception and
call the milestone partial; do not delete its content to manufacture completeness.

### M3 — Different games, not fantasy with different nouns

Keep proving slices small. The following builds on existing consumers; proposed
experiments are **not claims of current mechanics**.

| Set | Existing foothold | Proposed editor-authored contrast | What it tests |
|---|---|---|---|
| `fantasy_frontier` | Broad progression, crafting/preservation, abilities and collectible items | Reshape a preservation chain and generation profile without engine edits | Depth and preservation of existing content. |
| `orbital_salvage` | Salvage/repair work, fabrication and `hull_frost`/protective gear | A repair/calibration loop using components and a device resource; explore charge **or** heat only after confirming supported semantics | Different resource/work choices, hazard mitigation, generation without mandatory gems. Unsupported heat accumulation is an engine proposal, not a renamed mana field. |
| `night_shift` | Crime, custody and locksmithing proving slice | Reconfigure access, consequences and recovery around that existing route | Non-combat failure, ownership and law policies rather than a fantasy loot treadmill. |
| `modern_capsule` | Deliberate repair-cafe vignette, item exchange and dialogue flags | Author an alternate interaction/outcome with combat, crafting, economy and progression still absent | Useful minimal scaffolding, optional systems, and no forced reward loop. |

**Gate:** fantasy plus at least one genuinely contrasting consumer exercise each
newly generalized primitive; all four sets still boot. Record where two themes
share an operation and where they require different policies. When a second
consumer reveals a missing primitive, add the smallest contract with validation
and tests; do not grow another genre-specific subsystem or another full game.

### M4 — Change the rules after content exists

Build on M1's reference index and transactions, then add semantic impact, migration
plans, compatibility reports and representative save fixtures. Section 5 is the
required crafting-overhaul rehearsal. System switches and schema changes are never
equivalent to merely hiding fields in the library.

**Gate:** apply, abandon and recover a multi-file overhaul on an established test
game. Demonstrate renamed references, a removed station/profile, inactive content,
an existing generated item and an in-progress job. Every affected record receives
a disposition; unsupported save conversion blocks deployment to those saves, not
continued authoring in a new isolated project revision.

### M5 — An editor-made release candidate for human testers

Provide a reproducible export/checkpoint with content version, engine compatibility,
asset requirements, included content and validation/journey results. Exclude editor
preferences, credentials and player saves. The release gate must label skipped or
unavailable checks, not paint them green. Warnings may be acknowledged with reason
and a scope/fingerprint; changed findings reappear, blocking errors cannot be
acknowledged into correctness, and the candidate report retains the full findings.

Include engine/build identity, deterministic seeds where used, source asset paths
and redistribution/license notes. Validate project-relative paths and missing
dependencies; opening/importing a set must never execute arbitrary authored code
or let a manifest path redirect a save/export outside its intended root.

**Gate:** a second person follows the documented author-to-tester journey on a
clean install, boots the candidate, finishes its first loop and reloads progress.
Complete a human usability/accessibility pass, a representative large-world
performance check, and an interrupted-save/recovery drill. Record remaining
limitations explicitly. Stop here for the current production-quality push.

**Beyond this push:** arbitrary custom mechanics/plugins, live multiplayer
migrations and hot reload, collaborative editing/merge, marketplace dependency
management, exhaustive localization, commercial packaging/certification, and
full-game balance/content completion. They need separate decisions and gates;
M5 does not imply any of them.

## 5. A concrete late change: overhauling crafting

An author has recipes, station items, resource drops, quest requirements and players
with crafted equipment. They now want to replace station-based instant crafting
with skill-gated timed fabrication and a different quality model.

1. **Propose in a draft revision.** Compare the requested policy to supported
   recipe/work primitives. If this needs a new resolver or condition, say so and
   require engine implementation first. Do not write content the runtime ignores.
2. **Take a checkpoint and show impact.** Enumerate direct references (recipes,
   stations, skills, families, profiles, inputs/outputs) and downstream consumers
   (drops, vendors, starting gear, quests, dialogue, rewards). Also report semantic
   changes that have no broken ID: duration, costs, quality and progression pace.
   Preview sample outputs and relevant journey tests; do not claim a reference
   graph proves that the revised economy is balanced or every quest is solvable.
3. **Choose dispositions.** Retain existing definitions, create replacements and
   migrate selected consumers, mark old content inactive/deprecated, or remove it
   after all references are resolved. Never silently select the first available
   replacement. Show exact records and before/after values; ambiguous free-form
   or extension references require manual review.
4. **Decide runtime compatibility separately.** Candidate choices include keeping
   old generated items' resolved values, explicitly converting specified instances,
   finishing jobs under the old definition, refunding/cancelling jobs, or requiring
   a fresh test save. These are policies to implement and validate, not switches
   presumed to exist today. Missing old definitions or unsupported conversion must
   produce a compatibility failure, not delete an item or strand a job silently.
5. **Validate the entire staged set.** Run authoritative schema/reference checks,
   the changed systems' runtime journeys, seeded generation comparisons, and old
   save fixtures where compatibility is promised. Apply nothing on cancel/failure.
   Authors can retain an incomplete draft, but not publish it as a valid candidate.
6. **Apply as one recoverable change.** A journal/checkpoint plus staged writes must
   handle process interruption between files; individual atomic JSON writes are
   not a multi-file transaction. Check for external changes before commit. Record
   the migration, source/target versions and unresolved warnings. Rollback restores
   the coherent prior project, not just one recipe file.

**Change policy to implement:**

| Change class | Normal author action | Required additional guard |
|---|---|---|
| Name/prose/editor color | Direct edit, undo, save | Preserve identity; invalidate relevant previews only. |
| Numeric tuning/distribution | Edit and compare | Engine ranges/types; sample/journey effects and runtime-instance impact shown. |
| ID/reference rename or deletion | Refactor preview | All known dependents, collision checks, unresolved-reference review and transaction. |
| Toggle a system or replace a shared contract | Staged configuration change | Capability coherence, inactive-content view, dependent-flow review and test launch/restart rules. |
| Schema/algorithm or persistent-state meaning | Versioned migration or new revision | Engine support, compatibility fixtures and explicit old-save policy; no automatic live application. |

All classes remain editable during development. Risk determines review and apply
behavior, not an arbitrary “you have created content, so settings are locked” rule.
Default to testing a new revision in a separate runtime session, not hot-changing
an existing server. Do not invent a second version field before auditing the
existing manifest/API/schema versions and player-save format; document their
distinct meanings and add only the migration metadata actually required.

## 6. UX and verification that cut across every milestone

- **Systems overview:** enabled/inactive/unsupported states, effective values,
  prerequisites, “used by,” and links into the relevant configuration and content.
  Complexity is progressively disclosed; an inactive system retains its records
  in an explicit inactive view, not a disappearing inventory of lost work.
- **Content library:** names-first typed pickers, grouping/search, duplicate and
  bulk actions with previews; raw IDs available diagnostically. Label swapping
  changes labels, not references. New entries should be valid starting drafts,
  never fabricated references to the first item in a dropdown.
- **Generation:** preview and reroll with deterministic seeds; pools, allowed
  dimensions, normalized probabilities and final resolved samples. Commit only
  the accepted draft. District rerolls must explain removal of authored content
  and external connections and offer a non-destructive alternative.
- **Flows:** start with an inspection/link view over existing opening, dialogue,
  quest, work and reward declarations plus a journey trace. Do not introduce a
  second runtime graph interpreter just to get a visual flow editor.
- **Validation:** distinguish invalid data, runtime failures, geometry policy,
  design warnings and unchecked areas. Show source/name/path, remediation and a
  jump-to-editor action. Intentional warnings remain auditable and resettable.
- **Tests:** run targeted authoring smoke tests plus engine/content gates for
  behavior changes. Add GUI event-path tests for new dialogs, fault injection for
  write/recovery, and fresh/edited/existing-rich-record fixtures. Passing an old
  fixture sweep is not evidence for a new form's save path.
- **Performance and accessibility:** avoid blocking the canvas on large dependency
  or validation runs; report progress/cancellation and stale results. Test readable
  contrast, non-color-only errors/selections, focus order, scroll/zoom and resizing.

## 7. Decisions and handoff

Planning defaults above keep delivery moving; promote them to design records only
when their contracts are implemented. Before each dependent batch, settle:

- **B/G:** engine-owned schema/authoring metadata, per-section validation coverage,
  and which references the dependency index can discover reliably.
- **B/E/K:** the `magic`/`abilities` boundary, policy versus genuinely new mechanic,
  and campaigns' minimum supported authoring path. Fantasy coverage stays partial
  if a live feature is deferred.
- **C/B:** generated-instance, active-job and player-save compatibility, and the
  transaction/recovery protocol. Choose the first supported migration rather than
  promising arbitrary conversions.
- **G/F/J:** the exact small fantasy and orbital authoring journeys, minimal starter
  contents, and what a new author can complete without repository knowledge.

For every completed batch update the [coverage ledger](editor-coverage-ledger.md) with
the affected reader,
writer, tests actually run and a short human retest recipe. Never upgrade status
solely because a menu was added. Keep older audit evidence dated rather than
allowing yesterday's “not implemented” or “all tests passed” to become today's
unqualified claim.
