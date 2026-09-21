# Track G — World Editor

> **Current handoff, 2026-09-21:** execute [`../chunks-of-work.md`](../chunks-of-work.md)
> §6A–6G against the milestones in the
> [game-authoring roadmap](../game-authoring-roadmap.md). The
> [readiness assessment](../editor-readiness.md) now separates a current source-review
> addendum from its September 20 audit. This file retains historical findings;
> old counts, missing-surface claims and items 8–14 are not the current queue.
> Ruleset/contracts/combat forms now exist as prototypes. First harden their actual
> writes and event paths; then build project/dependency foundations, fantasy field
> coverage, contrasting consumers, migration and the authoring test candidate.

## Assessment

**State.** 23 checks run by `run_editor_checks.py` (globs `mud-world-editor/tests/*.gd`; the count in `ROADMAP.md` — 19 — and in `.github/workflows/editor-checks.yml` — seventeen — is stale). The same-source rule has a single enforcement point and it is clean: `scripts/data/EngineValidator.gd` finds `toolkit/editor_validate.py`, runs it, parses the last column-zero JSON object, and reimplements nothing. `DataRoot.gd` resolves one content root; `DatabaseManager.gd` loads and writes the engine's own files; `contract_authoring_smoke.gd`, `recipe_authoring_smoke.gd`, `dialogue_authoring_smoke.gd`, `quest_inspector_smoke.gd` and the title/collection/discovery/background suites each end by handing what the inspector wrote to the engine's validator.

**Strongest.** Authoring coverage is genuinely wide — items, recipes, quests, dialogue graphs, titles, collections, discoveries, backgrounds, regions, rooms, districts — and each new surface arrived with a headless test that asserts on the written dictionary, not on the widget. The lesson from the int→float incident is now encoded twice: `SaveIO` writes verified JSON, and `editor_validate.py` runs the engine's reader rather than a second opinion.

**Weakest.** No check re-saves a shipped content set and compares bytes. Every authoring test builds a scratch fixture under `tmp/`, and the one test that touches real content — `tests/content_source_check.gd` — reads `town.json` only. The one class of defect that has already cost this project a build (load → edit → whole-file rewrite → every authored integer becomes a float) has no editor-level regression check today; `run_content_checks.py`'s number gate is the only thing watching, and `editor_validate.py` does not run it. Second: no check compares the editor's vocabulary tables to the engine's *source*. `dialogue_authoring_smoke.gd:145-168` asks whether nine named condition kinds and nine effect keys are present, which a table missing the engine's other thirty keys would pass. Third: the engine button covers 5 of the 10 gate steps `run_content_checks.py` runs — `normalize_content_numbers.py`, `content_neutrality_validator.py`, `skill_audit.py` and `content_playability_check.py` are not in `editor_validate.py`, so the editor can say "No issues found" for a set the build refuses.

**Surprises.** There is one clear reimplementation and a latent data-loss bug next to it. `WorldManager.validate_world_links()` (`WorldManager.gd:112-142`) walks every region and reports unknown exit targets — the same fact `toolkit/reference_integrity_validator.py:131-140` reports, in a different wording and in a modal the engine never sees; it adds a one-way-link rule that is not an engine rule. And `RoomPropertiesPanel.gd:159-197` renders every property and edits it through a `LineEdit`, without the `TYPE_DICTIONARY`/`TYPE_ARRAY` guard its sibling `RegionInspector.gd:199-207` carries — so a room whose `properties.hidden_exits` exists (as in `content_sets/fantasy_frontier/data/regions/obsidian_trial.json:37`, which `dialogue/effects.py:376-404` reads) shows the object as a string, and one edit writes that string back over it. The content-side vocabulary leak has not gone away either: `sub_inspectors/NPCInspector.gd:41` hard-codes eight attribute names, `panels/RoomContentPanel.gd:55,75` default new content to `villager` and `gold_coin`, and three `COMMON_PROPS` tables carry `damp earth` / `default_theme`. Finally, the editor has no idea a manifest exists: `DataRoot.available_content_sets()` finds a set by testing for `content_set.manifest.json` and nothing reads it, so a new set cannot be created from inside the editor — its own tests hand-write the manifest (`tests/contract_authoring_smoke.gd:212`), which is the workflow an author is left with.

## Authorable today

| Content type | Can author | Cannot author |
|---|---|---|
| Content-set manifest (`content_set.manifest.json`) | everything: id, title, paths, `start`, capabilities, from the "New content set..." flow in the content-set chooser | — |
| Ruleset (`rules/ruleset.json`) | — | everything. Read-only, and only for `world.regions.biomes`/`region_types` (`Main.gd:125-138`). |
| Regions | new-region wizard (`CreatorModal`), name, description, scalar properties, `spawner` (level range, toggles, weights), districts | `level_band` (only via the wizard), `world_effects`/weather, hazard declarations |
| Rooms | id, name, description, exits (same-region links, typed as `region:room`), `initial_npcs` (per-row template), `items`, scalar properties | nested properties (`hidden_exits`, `exit_requirements`), room `level_band` |
| NPCs | level, health, `max_mana`, the stats this content set declares (or, undeclared, the ones its NPCs carry), loot table | `friendly`/behaviour vocabularies, dialogue graph binding, vendor `buy_orders` |
| Items | core template fields, `item_family`, `generation_profile`, rarity from the profile's bands, equip-slot property rows, salvage output | nested `properties` objects, attack/defense profile selection |
| Abilities (`abilities/` or `magic/`) | spell/ability entries, spell groups | ability *contracts* (`contracts/world_contracts.json`) |
| Quests | stages, 15 objective types with their fields, `objectives_any`, choices, choices outcomes, `turn_in_id`, completion dialogue | `spawn_on_entry`/`spawn_on_start` as structured control (kept as unmodelled keys) |
| Recipes | result, quantity, station, explicit difficulty, ingredients by `item_id`/`item_family`/`capability` plus grade floor, quality tiers, familiarity milestones | — |
| Dialogue | nodes, presentations, choices, aliases, conditions from 17 kinds, effects from 15 keys, node-target pickers | composite conditions as a tree (edited as JSON) |
| Titles / Collections / Discoveries / Backgrounds | entries, guild registry, condition editor for titles, `_default` background | — |
| Campaigns (`campaigns/`) | — | everything: loaded, never written |
| Combat/config data (`combat/elements.json`, `knowledge/`, `player/`) | — | everything |

## Proposed roadmap

> **Next batch, added 2026-09-20.** Items 1–6 below are done; item 7 is parked. What
> follows them is the batch the project picks up next, planned in
> [`../../plan/chunks-of-work.md`](../../plan/chunks-of-work.md) §6 and measured in
> [`../../plan/editor-readiness.md`](../../plan/editor-readiness.md). Items 8–14 are
> written here, in this track's format, because this is the track's own roadmap.

### 1. Round-trip every shipped content set and compare bytes

**What.** A check that loads every region and library file from all four shipped sets through `RegionManager`/`DatabaseManager`, saves through the real writer, and fails on any difference from the original except the `_filename` bookkeeping key.
**Why now.** It is the one structurally missing check, and the only one that would have caught the defect this track exists to prevent.
**Depends on.** Nothing.
**Scope.** medium.
**Done when.** New `tests/content_round_trip_smoke.gd` over `tmp/` copies of the shipped sets reports zero diffs, and a deliberately corrupted fixture (a float written where the file held an int) makes it fail.
**Risk.** A noisy diff becomes a relaxed check. If it fails on first run, the fix is the editor or a recorded exception, never a looser comparison.

> **✅ Done (2026-09-19, `3c9ce5e`).** `tests/content_round_trip_smoke.gd` (190
> lines) has both halves: the byte comparison over `tmp/` copies of all four sets,
> and `_check_the_check_itself_catches_a_corrupted_file()` writing a float where an
> int belonged to prove it goes red.
>
> **It earned its keep immediately.** The round-trip rewrote `forest.json` (470
> lines), `gallows_hollow.json`, `goblin_scrapcamp.json`, and the whole
> `modern_capsule` and `night_shift` trees -- latent drift that had been sitting in
> shipped content because nothing re-saved a shipped set.

### 2. Assert the editor's vocabularies equal the engine's, and fix the shape hints

**What.** A parity check importing `engine/conditions.py` (`KNOWN_KINDS`), `engine/dialogue/effects.py` (`KNOWN_EFFECTS`) and the objective types the tracker routes in `server/engine/core/quests/tracker.py`, compared as sets against `DialogueSchema.CONDITION_KINDS`/`EFFECTS` and `QuestSchema.TYPES`, both directions. Fix the two `DialogueSchema.EFFECTS` shape hints that disagree with `effects.py`: `adjust_relationship` says `{amount}` (engine reads `npc`), `move_npc` says `{npc_id, region_id, room_id}` (engine reads `npc`/`region`/`room`).
**Why now.** The tables are copies by necessity, the tests only prove they contain nine known keys, and the doc drift is already in the file an author reads.
**Depends on.** Nothing.
**Scope.** small.
**Done when.** New `tests/schema_parity_smoke.gd` fails on a missing or extra key in either direction, and fails when a hint contradicts the engine's reader.
**Risk.** A real mismatch surfaces and tempts a quick "add the key" edit that leaves the tables drifting; the fix belongs in the engine's declaration or in a note naming it.

### 3. Stop the room panel flattening nested properties

**What.** Give `RoomPropertiesPanel` the same dictionary/array guard `RegionInspector` has, and show such properties explicitly as preserved-but-not-editable-here.
**Why now.** `hidden_exits` is a real, engine-read property in shipped content, and the write path does not round-trip it.
**Depends on.** Nothing.
**Scope.** small.
**Done when.** A test loads a room carrying `properties.hidden_exits`, edits a scalar property through the panel, saves, reloads, and asserts the nested object is byte-identical.
**Risk.** Low. Deliberately *not* a nested-row editor here; a room-property shape editor needs the ruleset contract to declare property shapes, which is a handoff, not this item.

> **✅ Done (2026-09-19).** Wider than the item assumed, and the shape of the fix
> changed because of it.
>
> **Three panels carried the flaw, not one.** `RoomPropertiesPanel` (no guard),
> `RegionInspector` (had it inline), and `MultiRoomInspector` (`str(val)` into a
> LineEdit, and a multi-room edit writes the stringified value into *every*
> selected room). Copying the guard into the two that lacked it would have left
> three copies of one rule -- so the rule moved into
> `scripts/ui/inspectors/panels/PropertyTagRow.gd`: `is_inline_editable`,
> `editable_keys`, `build_row`, and `build_nested_row`, which shows a structured
> value read-only (`editable = false`, the editor's convention) with a note saying
> where it *can* be edited. All three panels now ask rather than decide.
>
> **Measured exposure, not assumed:** six shipped rooms carry a nested property --
> `weather_hazard_multipliers` on three (`swamp`, `sunscorch_road`,
> `coastal_path`), `exit_requirements` on two (`town:jail_cell`,
> `depot:holding_room`), `hidden_exits` on one (`obsidian_trial:hall_of_gates`).
> All six are engine-read state, so the loss was real rather than cosmetic, and
> `town.json` is a file this track's authoring work touches.
>
> **One extra defect fixed while generalising:** an integer property submitted
> through the row became a float (`t.to_float()`), which is the number-gate failure
> this project has already lost a build to. An int field now stays an int.
>
> **Verified** by `tests/nested_property_survival_smoke.gd` (25 assertions over
> five cases: the rule itself, the room panel, a scalar edit beside a nested value,
> the int case, and the multi-room analysis), and **mutation-tested**: making
> `is_inline_editable` return true for everything fails 7 of them, including
> "no editable field is built for a structured property (found 1)".

### 4. Run the engine's reference integrity from the world link check

**What.** Call `toolkit/reference_integrity_validator.validate_catalogs` alongside the editor's walk in `_show_validation_results`, and keep the one-way-link note as a clearly labelled advisory the engine does not make.
**Why now.** The editor's walker is the one reimplemented check in the tree, and an author currently gets two vocabularies for the same finding.
**Depends on.** Nothing.
**Scope.** small.
**Done when.** A scratch set with an unknown exit target produces the engine's finding with its `file.field` path in the modal, and a test asserts the editor reports no exit finding the engine's validator does not.
**Risk.** The engine's check is geometry-blind (it cannot see "does not link back"); deleting the advisory outright would change behaviour an author may rely on.

> **✅ The larger half done (2026-09-19), by a different route.** The two
> vocabularies existed because the editor's Validate button ran a *different list*
> of checks from the gate's -- by then five of fourteen, so it could report "No
> issues found" for a content set the build refuses.
>
> The list moved to `toolkit/content_check_steps.py`, used by both
> `run_content_checks.py` and `toolkit/editor_validate.py`. The editor now runs
> nine checks instead of five -- including reference integrity through the engine's
> own validator -- and reports the ones it does not run in a `not_run` field with a
> reason each, so an author sees the scope of a green light rather than inferring
> it. `server/tests/singles/test_content_check_steps.py` (16 tests) asserts the
> parity in both directions.
>
> **Still open here:** the editor's own `WorldManager.validate_world_links()` walk
> is still a second implementation of the unknown-exit-target finding, and the
> one-way-link advisory is still presented as though the engine made it. The
> `_show_validation_results` half is untouched.
>
> **Found while wiring it:** adding the skill audit made three authoring smoke
> checks fail on a real, accurate warning (`crafting` is named by content and
> declares no level). They asserted an *empty* issue list, which held only while
> the editor ran a subset; they now assert no **errors**, matching the gate.

### 5. Read the NPC stat form from the ruleset's declaration

**What.** Populate `NPCInspector`'s attribute rows from the content set's declared stats, the way `Main.gd:125-138` populates biomes; write nothing for a stat the set does not declare.
**Why now.** Eight hard-coded names are a second vocabulary, and `contracts/stats.py:42-51` exists precisely so a set can name its own.
**Depends on.** Item 1 (its diff verdict tells us what the implicit writes did to shipped NPCs).
**Scope.** small.
**Done when.** A fixture whose ruleset declares three stats renders three rows and writes no fourth; the shipped fantasy templates keep their existing numbers.
**Risk.** Shipped templates may carry undeclared stats that only survive because the form writes them; item 1 tells us before this lands.

> **✅ Done (2026-09-19).** `NPCInspector.attr_keys` is gone; the rows come from
> `ContractCatalog.stat_vocabulary()`, whose precedence is the engine's own
> (`World.declared_status_stats` then `contracts/stats.py`): the contracts'
> `stats.order`, then the ruleset's `status.stats`, then the distinct stats
> `stats.roles` names, then the stats the set's NPCs already carry. The row says
> which of the four it used, in a tooltip, so an author can tell a declaration
> from a fallback.
>
> **Correction to this item as written:** the stats declaration is **not** in the
> ruleset. The contract is `stats` in `data/contracts/world_contracts.json`;
> `ruleset.status.stats` is the older spelling of the same list and the engine
> still reads it, which is why the editor reads both, in that order. There is no
> rule to read from the ruleset at all.
>
> **Four defects found on the way, all fixed:**
>
> 1. **Two rows offered to write stats the set does not have.** `orbital_salvage`
>    declares six stats and `modern_capsule` declares none; the panel showed eight
>    fantasy names for all four sets.
> 2. **Opening an NPC wrote to it.** `_build_stats` did `cur_data["stats"] = {}`,
>    so merely selecting an NPC in the library added an empty object to the file
>    it would next save. Nothing is written now until a row is touched, and the
>    opening case is asserted.
> 3. **Every edited number became a float.** A `SpinBox` emits a float, and the
>    handlers wrote it straight into `level`, `health`, `max_mana` and every stat.
>    That is the int-to-float defect the number gate exists to catch, fixed at the
>    write with `int()`.
> 4. **"Mana" and "Health" were the panel's own words.** The two pool labels now
>    come from the declared `resources` entry of that `kind` -- orbital reads
>    "Charge" -- with the engine's neutral "Ability" as the fallback, because
>    `contracts/resources.py` names it that on purpose.
>
> **New check:** `tests/npc_stat_vocabulary_smoke.gd`, 5 fixtures (one per source
> plus the empty case) and the shipped set: every declared stat has a row in the
> declared order, every row shows the number the file holds, and opening the panel
> changes nothing. 29 editor checks now, all passing.
>
> **Recorded, not fixed — a content finding this exposed.** `orbital_salvage`
> declares `stats.roles.ability_power = "spell_power"` and `resistance =
> "magic_resist"`, and carries neither stat on any NPC. The engine reads those
> roles (`magic/effects.py:96` adds the flat ability bonus, `game_object.py:132`
> shrugs off non-physical damage), so for that set both mechanics resolve to the
> neutral default and never move. Omitting the two roles would not help: the
> engine falls back to the same fantasy names. A set that wants a real value there
> must name a stat it has. That is a balance decision for orbital, not an editor
> fix, and the declaration is now visible enough to make it.

### 6. Scaffold a new content set by copying a chosen one

**What.** A create-set flow that writes `content_set.manifest.json` (id validated as `[a-z][a-z0-9_]*`, required path strings, `start`), copies `rules/`, `presentation/` and `opening/` from a set the author picks, and creates the three required data directories.
**Why now.** This is the biggest new-set gap: without a manifest the editor will not even list the set, and today the only documented way to get one is to hand-write it.
**Depends on.** Items 1 and 2 (a scaffold must be checked by the same gates).
**Scope.** medium.
**Done when.** New `tests/content_set_scaffold_smoke.gd` creates a set, has `EngineValidator.run` return `ok`, opens and saves it from `Main.tscn`, and asserts no file was dropped or invented.
**Risk.** A copied ruleset carries the reference set's vocabulary into a world it does not fit. It must be an explicit copy of a known-good set, never a generated one.

> **✅ The ownership call was made first (2026-09-19).** The **engine owns** the
> manifest field list — `content_set.py` is what refuses a set. The editor holds a
> copy in a table a parity check keeps equal to the engine's, the arrangement
> already in use for condition kinds, effect kinds and objective types
> (`toolkit/engine_vocabulary_dump.py` + `schema_parity_smoke.gd`), and
> `EngineValidator.run` validates the manifest the editor just wrote, so a mistake
> meets the engine's verdict in the same session. Reading the list from Python at
> create time was refused: it would make creating a set depend on an interpreter
> beside the editor, and the risk was never the copy — an *unchecked* copy is.
> To make that checkable, the manifest's shape moved from literals inside
> `load_content_set` to module constants (`REQUIRED_MANIFEST_STRINGS`,
> `REQUIRED_MANIFEST_PATHS`, `OPTIONAL_MANIFEST_PATHS`, `REQUIRED_START_FIELDS`),
> and the loader reads them, so there is one spelling of each rule rather than two.
>
> **✅ Done 2026-09-19 — with one measured change to the plan.** `ContentSetScaffold`
> writes the manifest, copies what it is asked to copy, writes a one-room starter
> region, and reports what is left. `CreateContentSetDialog` is the form, reached
> from the content-set chooser ("New content set..."), and it is a receipt rather
> than a dismissible box: creating locks the fields, reports what was written, and
> the button becomes "Open it".
>
> **The measurement that changed the plan: rules are not copied by default.** This
> item assumed `rules/` is a self-contained thing to copy. It is not — a ruleset is
> a manifest of references into the world it was written for. Counted across the
> shipped sets: `modern_capsule`'s ruleset names nothing, `night_shift`'s names
> three items, `orbital_salvage`'s five, and `fantasy_frontier`'s ninety. Scaffolding
> from fantasy_frontier with its rules produces a set that opens and fails validation
> on **72 references** it cannot resolve (missing item/quest/NPC templates, loot
> pools, salvage outputs, plus the hazard coverage its ruleset demands). So
> `copy_rules` is a checkbox the dialog explains rather than the default: off gives a
> ruleset that declares nothing (the engine's defaults apply, and the set validates
> immediately, with only the pre-existing `crafting` warning), on gives a close copy
> of another world and its whole to-do list.
>
> **Five defects found on the way, all fixed:**
>
> 1. **The capability/directory mismatch.** The `quests` capability requires
>    `data/quests` and `data/campaigns` to exist (`content_set.py`, campaigns being a
>    quest-progression implementation). Copying the capability without them produced
>    two errors the author could do nothing about. The scaffold now mirrors that rule.
> 2. **The starter region read the wrong ruleset.** It was classified from the
>    *source's* ruleset, so a set with empty rules was still written with fantasy's
>    `biome`/`region_type`/`level_band` — precisely the vocabulary leak this track
>    exists to prevent. It now reads the ruleset the manifest points at.
> 3. **`SaveIO` does not create directories, deliberately** — so the placeholder
>    ruleset and the starter region each ensure their own parent exists.
> 4. **A source missing `opening/` was refused entirely**, though `paths.opening` is
>    optional in the engine. Only `rules/` and `presentation/` are required of a
>    source now.
> 5. **The dialog wrote to `content_sets/`** — as shipped that is correct (it is
>    where sets live), but it means a check that drives the dialog must be able to
>    point it elsewhere, so `set_target_root` exists and the smoke check uses it.
>
> **New check:** `tests/content_set_scaffold_smoke.gd`, 40 assertions: what it
> copied is byte-identical, the manifest carries every name the engine requires
> (parity-checked), the engine loads the result, opening and saving it from the real
> `Main.tscn` changes no file, both rules modes behave as described, four refusals
> refuse, and the dialog itself creates a set, reports it and switches to it.
> **30 editor checks, all passing.**

### 7. Decide where an authoring tool lives now that `tools/` is gone

**What.** A scoped spike: name the operations a tool needs (read a content set, edit a declaration, ask the engine whether the result is valid), and build one as a mod plugin against the existing manifest/plugin API.
**Why now.** `tools/` was deleted 2026-09-18 and `work-tracks.md` records that a plugin surface has no owner; the mods API is real but nothing demonstrates it as a tool surface.
**Depends on.** A Track K owner decision, then items 1-2 as the safety net.
**Scope.** medium.
**Done when.** A spike note plus one working plugin that reads and writes a content set through `toolkit/editor_validate.py`, or a recorded finding that the mod API cannot reach it.
**Risk.** `authoring.gm` (`commands/system.py:202`) already exists as a capability, so the gap is capability *drift*, not absence; an in-game tool must not become a second writer.

> **⏸ Parked 2026-09-19** (Track K decision 6, and recorded in `work-tracks.md`'s
> deferral ledger). The editor is the authoring front-end and `toolkit/` is the
> validation surface, so a mod-plugin tool has no named consumer; the spike would
> answer whether the plugin API *could* reach a content set, which only matters
> once in-game tooling is wanted. Un-park it by naming the consumer, not by
> running the spike.

### 8. Author the ruleset from the editor

**What.** One form per section the engine reads for a content set:
`social`, `skills`, `factions`, `advancement`, `quest_generation`, `combat`,
`weather` first, then `crafting`, `crime`, `locksmithing`, `loot`,
`npc_schedules`, `elites`, `economy`, `status`, `calendar`, `player_defaults`.
Fields typed from the engine's constant, ranges enforced, and every verdict from
the engine's own validator beside the field.
**Why now.** It is the single largest gap against "the editor can manage the
engine's capabilities": `social` and `progression` cannot be declared through the
editor at all, and an author who cannot write `social.tiers` cannot ship a set that
uses the social system, however good the NPC inspector is. Today the editor reads
exactly two keys of this file (`world.regions.biomes`/`region_types` in
`Main.gd:128`, and `status.stats` through `ContractCatalog.gd:99`).
**Depends on.** B: a validator per exposed section, or the section is shown
read-only with the reason. `content_set.py` validates `social`, `factions`,
`skills`, `advancement`, `weather`, `world`, `quest_generation`, `systems` today and
none of the rest.
**Scope.** large.
**Done when.** A scratch set's `social.tiers`, `skills` and `factions` can be
authored in the editor, the engine loads the result, and the editor's verdict on a
malformed section is the engine's message with a `file.field` path. Save/reload
changes nothing the author did not touch (the item/gem inspectors' lesson).
**Risk.** A form is a second schema. The mitigation is the project's standing rule:
the editor writes the section, then asks `EngineValidator` — it never decides
whether a value is legal.

### 9. Author the contracts from the editor

**What.** Writers for `item_families`, `stats`, `resources`, `generation_profiles`,
`attack_profiles`, `defense_profiles`, `effect_packets`, `abilities` and `work` in
`data/contracts/world_contracts.json`. The browser already parses all of it
(`ContractBrowserDialog.gd`); what is missing is a writer, plus the refusal surface
that says why a contract is malformed.
**Why now.** Every item template points at a family or profile, so a set whose
author cannot declare one cannot use the item contract at all — and a contract that
is malformed makes the *catalog* empty, which silently removes the item inspector's
family picker rather than reporting anything.
**Depends on.** Item 8's editorial pattern; `engine/contracts/registry.py`'s
existing refusals (the editor asks the registry; it does not re-derive the rules).
**Scope.** large.
**Done when.** A new family with two capabilities and one stat row can be authored,
an item can select it, and the gate is green; a malformed contract shows the
registry's own message in the editor.
**Risk.** This reverses a recorded refusal (§ "Explicitly not proposing"). The
reason it is safe now is the same reason the refusal was right then: the schema must
stay the engine's, and the editor must *ask*, never model.

### 10. Author the two engine-read files that have no surface at all

**What.** `data/combat/elements.json` (damage types and hazard types: channel,
flavor, damage, tick interval) and `data/knowledge/topics.json` (display name,
keywords, per-response conditions, priority, effects).
**Why now.** Both are read by the engine — hazards damage players, topics answer
`ask <npc> <topic>` and gate dialogue conditions — and neither is visible in the
editor or validated by any gate.
**Depends on.** B for the validators (the hazard shape is validated today; the
topic shape is not).
**Scope.** medium.
**Done when.** A hazard can be declared and attached to a room, a knowledge topic
can be written with a conditioned response, and the engine plays both.
**Risk.** Damage types are shared vocabulary: an editor that lets an author delete
one in use must say what still points at it.

### 11. Campaigns: build the editor, or stop loading them

**What.** Either a graph editor over `data/campaigns/` (nodes, transitions by
trigger, narrative text, end nodes — the quest stage view is most of it), or stop
loading them and say so. Today they are loaded into `DatabaseManager.campaigns`
and never written, while `DialogueSchema` offers a `start_campaign` effect naming a
campaign the editor cannot list.
**Why now.** It is the largest single "the editor loads it and can do nothing with
it" gap, and the reference set ships two campaigns, one of which the engine cannot
fully play.
**Depends on.** Track K's build-or-drop call on campaign authoring.
**Scope.** medium.
**Done when.** Either an author can create a node, wire a transition and save a
campaign the engine loads, or `data/campaigns/` is not loaded and the
`start_campaign` picker offers only campaigns that exist.
**Risk.** A half-built graph editor is worse than none: the campaign format has
triggers the editor would have to validate (`SUCCESS`, `VIOLENT_SUCCESS`,
`PEACEFUL_SUCCESS`), and an unknown trigger is a campaign that never advances.

### 12. Stop the inspector writes that break or are ignored

**What.** Nested `properties` in the item inspector get the `PropertyTagRow` rule
the room and region panels already carry (the one remaining silent-data-loss path);
the NPC inspector loses `health` or gains the field the engine actually reads; quest
`rewards` gets a widget and a validator; the four ability/dialogue inert paths are
closed (effect `duration` vs `dot_duration`/`base_duration`, unknown effect types
preserved rather than rewritten, effects on a checked choice, effects on a root
node); and the five dead controls are deleted or wired.
**Why now.** These are the writes that cost an author work today, and one of them
is the same defect class this track already lost a build to.
**Depends on.** Nothing.
**Scope.** medium.
**Done when.** `nested_property_survival_smoke.gd` covers the item panel, a scratch
set with `salvage_output` survives an unrelated edit byte-identically, and each
removed control has a test that would fail if it came back.
**Risk.** Removing a control looks like a regression to an author who used it;
each removal ships with the reason in the file, and a dead control that *writes* a
key the engine ignores is worse than a missing one.

### 13. Set management and the editor's validation scope

**What.** Delete and rename a content set; edit an existing manifest's
`capabilities` and `start` (creation only today); list sets opened from outside
`content_sets/`; and a "Validate (full)" action that runs the playability check —
the one gate step that boots the set and plays it, deliberately kept out of the
common path.
**Why now.** Switching is now safe but a set cannot be removed or its manifest
corrected without a text editor, and an author can be green in the editor for a set
the build refuses because its opening does not run.
**Depends on.** Nothing.
**Scope.** small.
**Done when.** A set created by mistake can be deleted from the editor after a
confirmation that names what will be removed; a manifest's capabilities can be
changed and revalidated; "Validate (full)" reports the playability result with the
same shape as the other steps.
**Risk.** Deleting a set deletes an author's world: the confirmation must name the
path and require it to be typed, and nothing may be removed before that.

### 14. Widen the vocabulary dump so every editor copy is a checked copy

**What.** `toolkit/engine_vocabulary_dump.py` emits the remaining vocabularies the
editor copies: item class names, equip slots, ability target and effect types with
their per-effect field maps, the filename→group map, and the movement directions
with their reciprocals. `schema_parity_smoke.gd` then compares all of them.
**Why now.** More than a dozen copies are unverifiable today, and one is already wrong:
`Constants.gd:46` makes `climb`'s opposite `dive` while
`server/engine/utils/utils.py:306` makes it `descend` — so the connection editor
writes a reciprocal exit the engine will not resolve.
**Depends on.** B (the dump is the engine's), then G consumes it.
**Scope.** small.
**Done when.** The parity check fails when any emitted vocabulary differs in either
direction, and the `climb` disagreement is either fixed or recorded as deliberate.
**Risk.** A parity test over a list the engine does not really own would force the
editor to copy something arbitrary; emit only what the engine actually reads.

## Explicitly not proposing

- ~~**Contract/family authoring in the editor.**~~ **Reversed 2026-09-20 — see item
  9.** The original reason was that "the schema owns what may exist; a layout editor
  over `item_families` is a second schema". That reason still holds, and it is now
  the *constraint* rather than the refusal: the editor must ask
  `ContractRegistry`/`content_set.py` what is valid instead of modelling families
  itself, which is the same arrangement `EngineValidator` already uses for content.
  The new reason to do it: every item template points at a family, so a set whose
  author cannot declare one cannot use the item contract at all.
- **Pack/mod export and a one-click package path.** P8 deferred it pending manifest
  authoring *and* an engine-side mod-layering concept; item 6 removes one of the
  three blockers and the other two remain.
- **Hot reload / live server sync.** It needs a watch mode and engine-side verification, and it would let the editor claim engine state it cannot see. Lane: not ours.
- **Territory recompute performance** (`GraphController.gd:513-517`). Known, bounded at current scale, costs patience rather than correctness.
- **Turning the one-way-link rule into a hard gate.** It is not an engine rule; item 4 keeps it as an advisory and no more.
- **An autosave timer.** The quit and switch prompts already stand between the author and lost work; nothing here can lose work that was saved.

## Risks

- The round-trip check fails on first run against shipped content and someone fixes it by relaxing the comparison — which removes the only guard against this track's most expensive defect class.
- The parity check fails, and the response is a patch that adds keys to the editor tables rather than a decision about who owns the vocabulary.
- The schema copies cannot be removed (the editor needs field *types* to choose widgets), so parity can only ever be enforced, not eliminated; if that is not accepted, the drift returns and the tests rot.
- Items 1-2 need Godot to run, so the proposals land as unverified files if the checks are never executed locally or in CI. *(2026-09-20: the checks do run locally — 30/30 — and `run_editor_checks.py` is one of the three gates, so this risk is about CI, not about the tooling existing.)*
- Item 6's copied ruleset imports genre vocabulary into a new world, which is the failure mode this track exists to prevent, dressed as convenience.
- **Items 8-11 are where "the editor shows fields and asks the engine" is most tempting to break.** A ruleset or contract form is the first surface that can hold a *rule* rather than a value, and the first that can disagree with `content_set.py` about legality. The mitigation is structural: no section ships before its validator does (Track B's handoff 1), and the section appears read-only with the reason until then.
- **Every new writer multiplies the round-trip risk, and only item 1's check catches it.** That check is done and green (2026-09-19), which is exactly why items 8-14 are affordable now; the risk is that a new writer lands without a fixture of its own, so the next silent rewrite ships inside a *new* file the four-set round trip never touches.
- **Item 13's delete is the first irreversible action in the editor.** Every other control can be undone by not saving; a typed confirmation is the only thing between an author and a deleted world, so it must name the path and the file count.
- **Item 11 may resolve as "stop loading campaigns".** That is a deletion of a loaded surface, and the `start_campaign` dialogue effect names campaigns today; the picker must be narrowed in the same change or the effect offers a campaign that cannot load.

## Unknowns

- I could not run the checks (no Godot invocation from this audit), so "all green" is not a claim I could make; nor can I tell whether `editor-checks.yml` has ever succeeded on GitHub. *(Run 2026-09-20: `run_editor_checks.py --godot <path>` is 30/30 locally and is now part of the three gates; the CI workflow's own history is still unread.)*
- I could not exercise the editor interactively, so every claim here is about code, not about feel.
- Whether the round-trip diff is actually empty on the shipped sets is unverified — and it is the premise of item 1.
- Whether the plugin/mod API can reach a content set at runtime (paths, permissions) is unread; item 7 is a spike partly because of that.
- It is unread whether shipped NPC templates rely on `spell_power`/`magic_resist` values that only exist because the editor's form writes them.
- Whether anyone relies on the one-way-link warning is a question for the author, not the code.
- **Items 8-11.** Whether `content_set.py`'s section validators can be asked about one section at a time
  without loading a whole set — the form needs a verdict on a ruleset the author is halfway through
  editing, and today every entry point validates a whole set. Unread; if they cannot, item 8's first task
  is a per-section entry point (Track B's handoff 1).
- **Items 8-9.** Whether the editor's save path preserves key order and untouched keys in a file it only
  partly understands. Item 1's byte comparison answers this for the four shipped sets, but no shipped set
  has a section the editor writes *and* a section it ignores in the same file the way an in-progress
  ruleset does.
