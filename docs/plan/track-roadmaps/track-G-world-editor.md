# Track G — World Editor

## Assessment

**State.** 23 checks run by `run_editor_checks.py` (globs `mud-world-editor/tests/*.gd`; the count in `ROADMAP.md` — 19 — and in `.github/workflows/editor-checks.yml` — seventeen — is stale). The same-source rule has a single enforcement point and it is clean: `scripts/data/EngineValidator.gd` finds `toolkit/editor_validate.py`, runs it, parses the last column-zero JSON object, and reimplements nothing. `DataRoot.gd` resolves one content root; `DatabaseManager.gd` loads and writes the engine's own files; `contract_authoring_smoke.gd`, `recipe_authoring_smoke.gd`, `dialogue_authoring_smoke.gd`, `quest_inspector_smoke.gd` and the title/collection/discovery/background suites each end by handing what the inspector wrote to the engine's validator.

**Strongest.** Authoring coverage is genuinely wide — items, recipes, quests, dialogue graphs, titles, collections, discoveries, backgrounds, regions, rooms, districts — and each new surface arrived with a headless test that asserts on the written dictionary, not on the widget. The lesson from the int→float incident is now encoded twice: `SaveIO` writes verified JSON, and `editor_validate.py` runs the engine's reader rather than a second opinion.

**Weakest.** No check re-saves a shipped content set and compares bytes. Every authoring test builds a scratch fixture under `tmp/`, and the one test that touches real content — `tests/content_source_check.gd` — reads `town.json` only. The one class of defect that has already cost this project a build (load → edit → whole-file rewrite → every authored integer becomes a float) has no editor-level regression check today; `run_content_checks.py`'s number gate is the only thing watching, and `editor_validate.py` does not run it. Second: no check compares the editor's vocabulary tables to the engine's *source*. `dialogue_authoring_smoke.gd:145-168` asks whether nine named condition kinds and nine effect keys are present, which a table missing the engine's other thirty keys would pass. Third: the engine button covers 5 of the 10 gate steps `run_content_checks.py` runs — `normalize_content_numbers.py`, `content_neutrality_validator.py`, `skill_audit.py` and `content_playability_check.py` are not in `editor_validate.py`, so the editor can say "No issues found" for a set the build refuses.

**Surprises.** There is one clear reimplementation and a latent data-loss bug next to it. `WorldManager.validate_world_links()` (`WorldManager.gd:112-142`) walks every region and reports unknown exit targets — the same fact `toolkit/reference_integrity_validator.py:131-140` reports, in a different wording and in a modal the engine never sees; it adds a one-way-link rule that is not an engine rule. And `RoomPropertiesPanel.gd:159-197` renders every property and edits it through a `LineEdit`, without the `TYPE_DICTIONARY`/`TYPE_ARRAY` guard its sibling `RegionInspector.gd:199-207` carries — so a room whose `properties.hidden_exits` exists (as in `content_sets/fantasy_frontier/data/regions/obsidian_trial.json:37`, which `dialogue/effects.py:376-404` reads) shows the object as a string, and one edit writes that string back over it. The content-side vocabulary leak has not gone away either: `sub_inspectors/NPCInspector.gd:41` hard-codes eight attribute names, `panels/RoomContentPanel.gd:55,75` default new content to `villager` and `gold_coin`, and three `COMMON_PROPS` tables carry `damp earth` / `default_theme`. Finally, the editor has no idea a manifest exists: `DataRoot.available_content_sets()` finds a set by testing for `content_set.manifest.json` and nothing reads it, so a new set cannot be created from inside the editor — its own tests hand-write the manifest (`tests/contract_authoring_smoke.gd:212`), which is the workflow an author is left with.

## Authorable today

| Content type | Can author | Cannot author |
|---|---|---|
| Content-set manifest (`content_set.manifest.json`) | — | everything: id, title, paths, `start`, capabilities. Not read by any editor script. |
| Ruleset (`rules/ruleset.json`) | — | everything. Read-only, and only for `world.regions.biomes`/`region_types` (`Main.gd:125-138`). |
| Regions | new-region wizard (`CreatorModal`), name, description, scalar properties, `spawner` (level range, toggles, weights), districts | `level_band` (only via the wizard), `world_effects`/weather, hazard declarations |
| Rooms | id, name, description, exits (same-region links, typed as `region:room`), `initial_npcs` (per-row template), `items`, scalar properties | nested properties (`hidden_exits`, `exit_requirements`), room `level_band` |
| NPCs | level, health, `max_mana`, eight hard-coded stats, loot table | `friendly`/behaviour vocabularies, dialogue graph binding, vendor `buy_orders` |
| Items | core template fields, `item_family`, `generation_profile`, rarity from the profile's bands, equip-slot property rows, salvage output | nested `properties` objects, attack/defense profile selection |
| Abilities (`abilities/` or `magic/`) | spell/ability entries, spell groups | ability *contracts* (`contracts/world_contracts.json`) |
| Quests | stages, 15 objective types with their fields, `objectives_any`, choices, choices outcomes, `turn_in_id`, completion dialogue | `spawn_on_entry`/`spawn_on_start` as structured control (kept as unmodelled keys) |
| Recipes | result, quantity, station, explicit difficulty, ingredients by `item_id`/`item_family`/`capability` plus grade floor, quality tiers, familiarity milestones | — |
| Dialogue | nodes, presentations, choices, aliases, conditions from 17 kinds, effects from 15 keys, node-target pickers | composite conditions as a tree (edited as JSON) |
| Titles / Collections / Discoveries / Backgrounds | entries, guild registry, condition editor for titles, `_default` background | — |
| Campaigns (`campaigns/`) | — | everything: loaded, never written |
| Combat/config data (`combat/elements.json`, `knowledge/`, `player/`) | — | everything |

## Proposed roadmap

### 1. Round-trip every shipped content set and compare bytes

**What.** A check that loads every region and library file from all four shipped sets through `RegionManager`/`DatabaseManager`, saves through the real writer, and fails on any difference from the original except the `_filename` bookkeeping key.
**Why now.** It is the one structurally missing check, and the only one that would have caught the defect this track exists to prevent.
**Depends on.** Nothing.
**Scope.** medium.
**Done when.** New `tests/content_round_trip_smoke.gd` over `tmp/` copies of the shipped sets reports zero diffs, and a deliberately corrupted fixture (a float written where the file held an int) makes it fail.
**Risk.** A noisy diff becomes a relaxed check. If it fails on first run, the fix is the editor or a recorded exception, never a looser comparison.

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

### 4. Run the engine's reference integrity from the world link check

**What.** Call `toolkit/reference_integrity_validator.validate_catalogs` alongside the editor's walk in `_show_validation_results`, and keep the one-way-link note as a clearly labelled advisory the engine does not make.
**Why now.** The editor's walker is the one reimplemented check in the tree, and an author currently gets two vocabularies for the same finding.
**Depends on.** Nothing.
**Scope.** small.
**Done when.** A scratch set with an unknown exit target produces the engine's finding with its `file.field` path in the modal, and a test asserts the editor reports no exit finding the engine's validator does not.
**Risk.** The engine's check is geometry-blind (it cannot see "does not link back"); deleting the advisory outright would change behaviour an author may rely on.

### 5. Read the NPC stat form from the ruleset's declaration

**What.** Populate `NPCInspector`'s attribute rows from the content set's declared stats, the way `Main.gd:125-138` populates biomes; write nothing for a stat the set does not declare.
**Why now.** Eight hard-coded names are a second vocabulary, and `contracts/stats.py:42-51` exists precisely so a set can name its own.
**Depends on.** Item 1 (its diff verdict tells us what the implicit writes did to shipped NPCs).
**Scope.** small.
**Done when.** A fixture whose ruleset declares three stats renders three rows and writes no fourth; the shipped fantasy templates keep their existing numbers.
**Risk.** Shipped templates may carry undeclared stats that only survive because the form writes them; item 1 tells us before this lands.

### 6. Scaffold a new content set by copying a chosen one

**What.** A create-set flow that writes `content_set.manifest.json` (id validated as `[a-z][a-z0-9_]*`, required path strings, `start`), copies `rules/`, `presentation/` and `opening/` from a set the author picks, and creates the three required data directories.
**Why now.** This is the biggest new-set gap: without a manifest the editor will not even list the set, and today the only documented way to get one is to hand-write it.
**Depends on.** Items 1 and 2 (a scaffold must be checked by the same gates).
**Scope.** medium.
**Done when.** New `tests/content_set_scaffold_smoke.gd` creates a set, has `EngineValidator.run` return `ok`, opens and saves it from `Main.tscn`, and asserts no file was dropped or invented.
**Risk.** A copied ruleset carries the reference set's vocabulary into a world it does not fit. It must be an explicit copy of a known-good set, never a generated one.

### 7. Decide where an authoring tool lives now that `tools/` is gone

**What.** A scoped spike: name the operations a tool needs (read a content set, edit a declaration, ask the engine whether the result is valid), and build one as a mod plugin against the existing manifest/plugin API.
**Why now.** `tools/` was deleted 2026-09-18 and `work-tracks.md` records that a plugin surface has no owner; the mods API is real but nothing demonstrates it as a tool surface.
**Depends on.** A Track K owner decision, then items 1-2 as the safety net.
**Scope.** medium.
**Done when.** A spike note plus one working plugin that reads and writes a content set through `toolkit/editor_validate.py`, or a recorded finding that the mod API cannot reach it.
**Risk.** `authoring.gm` (`commands/system.py:202`) already exists as a capability, so the gap is capability *drift*, not absence; an in-game tool must not become a second writer.

## Explicitly not proposing

- **Contract/family authoring in the editor.** The schema owns what may exist; a layout editor over `item_families` is a second schema. Already deferred, and `docs/design/cross_theme_engine_contracts.md` owns the shape.
- **Pack/mod export and a one-click package path.** P8 deferred it pending manifest authoring *and* an engine-side mod-layering concept; item 6 removes one of the three blockers and the other two remain.
- **Hot reload / live server sync.** It needs a watch mode and engine-side verification, and it would let the editor claim engine state it cannot see. Lane: not ours.
- **Territory recompute performance** (`GraphController.gd:513-517`). Known, bounded at current scale, costs patience rather than correctness.
- **Turning the one-way-link rule into a hard gate.** It is not an engine rule; item 4 keeps it as an advisory and no more.
- **An autosave timer.** The quit and switch prompts already stand between the author and lost work; nothing here can lose work that was saved.

## Risks

- The round-trip check fails on first run against shipped content and someone fixes it by relaxing the comparison — which removes the only guard against this track's most expensive defect class.
- The parity check fails, and the response is a patch that adds keys to the editor tables rather than a decision about who owns the vocabulary.
- The schema copies cannot be removed (the editor needs field *types* to choose widgets), so parity can only ever be enforced, not eliminated; if that is not accepted, the drift returns and the tests rot.
- Items 1-2 need Godot to run, so the proposals land as unverified files if the checks are never executed locally or in CI.
- Item 6's copied ruleset imports genre vocabulary into a new world, which is the failure mode this track exists to prevent, dressed as convenience.

## Unknowns

- I could not run the 23 checks (no Godot invocation from this audit), so "all green" is not a claim I can make; nor can I tell whether `editor-checks.yml` has ever succeeded on GitHub.
- I could not exercise the editor interactively, so every claim here is about code, not about feel.
- Whether the round-trip diff is actually empty on the shipped sets is unverified — and it is the premise of item 1.
- Whether the plugin/mod API can reach a content set at runtime (paths, permissions) is unread; item 7 is a spike partly because of that.
- It is unread whether shipped NPC templates rely on `spell_power`/`magic_resist` values that only exist because the editor's form writes them.
- Whether anyone relies on the one-way-link warning is a question for the author, not the code.
