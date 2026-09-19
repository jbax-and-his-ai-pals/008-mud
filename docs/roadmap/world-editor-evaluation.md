# World editor evaluation (2026-09-20)

An assessment of `mud-world-editor` as an authoring tool: what it is good at, what
is broken right now, what it cannot author at all, and what to do next.

**Method.** Read-only audit of all 70 GDScript files (13,247 lines) plus the 10
headless tests, against the engine's loaders and validators. Two defects were
reproduced by running the code rather than by reading it, and are marked
*reproduced*. The editor GUI was not exercised interactively, so nothing here
speaks to how it *feels* to use — only to what the code does.

**Status: Batches A–D are implemented** (see §6–§9). The table in §2 keeps the
defects as found, with what each fix now guarantees.

**Verdict in one line.** The hard parts are built and the safety layer is missing:
the content-source reconciliation, the editor/layout split and the district
geometry are genuinely good work, but a single region click can destroy an
hour of edits, a failed save is indistinguishable from a successful one, and the
one button that would tell an author whether the engine will accept their content
is dead.

---

## 1. What is good, and should not be disturbed

- **One content source, resolved explicitly.** `DataRoot.gd` resolves
  `--data-root` → `user://editor_settings.json` → checkout
  (`../content_sets/fantasy_frontier`) → standalone `<project>/data`, and puts the
  winner in the window title (`DataRoot.gd:47-78,168-172`). The retired mirror is
  gone and a guardrail test fails if any editor script hard-codes `res://data/...`
  again (`tests/content_source_check.gd`, `test_editor_content_source.py`).
- **Editor state is separated from game content, in one place.**
  `EditorLayout.gd` lifts `_editor_pos` / `_editor_exit_layout` into
  `<content set>/editor/`, merges them back on load, removes the sidecar when it
  empties, and strips recursively so nothing `_editor_*` reaches `data/`
  (`EditorLayout.gd:26-77,139-157`). The sidecar round trip is tested.
- **The district/territory work is real geometry, not decoration.** Territory
  tracing, despeckling, pinch detection, label anchoring and shared-influence
  dilation all have headless tests that assert against real region files
  (`tests/district_*.gd`, `tests/territory_shape_dilate_smoke.gd`).
- **The layout optimiser** aligns rooms to the cardinal grid with half-step
  stacking, asserts alignment across every shipped region, and commits
  auto-arrange as a single undoable step (`LayoutOptimizer.gd`, `Main.gd:939-973`).
- **The editor already reads the engine's contracts** from the same file the
  engine reads, and refuses a schema version it does not know
  (`ContractCatalog.gd:36-75`). Nothing in the UI uses it yet (see §4), but the
  hard part — agreeing on a source — is done.

## 2. Defects that cost work, ranked

| # | Defect | Evidence | Why it matters |
|---|---|---|---|
| D1 | **A room rename's cross-region repair never runs.** Paths are built by concatenation without a separator (`regions_dir() + fname`), and `DataRoot.content_dir` returns a `path_join` result with no trailing slash. | `RegionManager.gd:190,193,205` vs `DataRoot.gd:144-146` | Renaming a room leaves `otherregion:roomid` exits dangling in every other region, silently. Every other call site in the project uses `path_join`. |
| D2 | **A quest stage added in the editor cannot be completed, and validation says it is fine.** The inspector writes `{id, description, type: "KILL", target, count, next}`; the engine reads `stage.objective.type` / `stage.objectives_any` and routes nothing else. *Reproduced:* appending such a stage to `quest_wildflower_commission` gives **0 validator errors**, and `get_active_objectives` returns `[]` for that stage, so the quest stalls forever. | `QuestInspector.gd:80-89,126-132` vs `content_set.py:1232-1242`, `quests/manager.py:72-92`, `tracker.py:20-23` | The editor's quest surface looks functional and produces content that is silently unplayable. Existing stages also *display* wrong (a `deliver` stage renders as `KILL`). |
| D3 | **`items/affixes.json` is truncated by any item save.** The loader keeps only dictionary-valued top-level keys; the saver rewrites each file purely from that cache. The file's `generated_effect_name_pattern` and `generated_description_suffix` are strings, so both are dropped. | `DatabaseManager.gd:144-163,187-205`; file keys verified | Editing one item deletes engine-read data that drives generated affix names and descriptions. No validator notices. |
| D4 | **Switching regions discards unsaved edits with no prompt.** `_load_region` consults nothing; `RegionManager.load_region` clears the dirty flag *before* it even tries to load. A dirty marker is drawn but never checked by any navigation path. | `Main.gd:605-611`, `RegionManager.gd:20-21`, `ExplorerPanel.gd:286` | One click in the Explorer tree is enough. `is_region_dirty` is read in exactly three places, none of them navigation. |
| D5 | **Saves are never verified, and the editor reports success anyway.** `save_region(); mark_clean()` is unconditional; `save_region()` returns void and swallows a failed open (`if file:` with no `else`). The same pattern is repeated in `save_all`, `save_world_layout` and the two direct writers in `Main.gd`. | `Main.gd:268-273`, `RegionManager.gd:58-60`, `DatabaseManager.gd:204-205` | On a read-only file or a permission error the Save button greys out as "saved" and the work is gone. Errors go to Godot's console only. |
| D6 | **No close handler and no autosave.** Grep for `NOTIFICATION_WM_CLOSE_REQUEST` / `auto_accept_quit` / `close_requested` across the editor finds one unrelated hit. | `DistrictModal.gd:79` | Closing the window loses everything since the last manual save, silently. |
| D7 | **A malformed region is replaced by a blank one under the real filename.** On a parse failure `data` is reset to `{"rooms": {}}` while `current_filename` keeps the real name, and the only signal is `push_error`. Any later Save overwrites the file — and Ctrl+Z alone is enough to enable Save. | `RegionManager.gd:23,43-47,55-60`, `Main.gd:402,1039` | One bad JSON read plus one keystroke can reduce a 46-room region to `{}`. |
| D8 | **The undo stack survives a region change.** It is created once and never cleared on load, so Ctrl+Z after switching regions replays a closure captured against the previous region. | `Main.gd:50`, `CommandProcessor.gd:5-33` | Corrupts the newly loaded region or raises a missing-key error. |
| D9 | **Database deletes are unconfirmed and not undoable** (rooms get both). | `ContentLibraryDialog.gd:390-394` → `Main.gd:241-243`; room path: `EditorUIManager.gd:272-283`, `ActionHandler.gd:136-155` | Deleting an item or NPC is one misclick, permanently. |
| D10 | **"Validate Region Policy" is dead in a checkout.** It builds `content_root`/`ruleset_path` from `res://data/...`, which no longer exists. *Reproduced:* the call the editor makes returns `unable to read ruleset: .../mud-world-editor/data/ruleset.json`; the same command against `content_sets/fantasy_frontier` returns `ok: true`. | `Main.gd:749-774` vs `DataRoot.gd:141-146` | The only engine-acceptance check in the editor never runs. The fix is two lines. |
| D11 | **Every save reformats and reorders the whole file.** The editor wrote tab-indented JSON, and `JSON.stringify`'s `sort_keys` defaults to **true**, so every object in a saved file was alphabetised as well. | `RegionManager.gd:60`, `DatabaseManager.gd:205`, `EditorLayout.gd:187` vs `town.json`, `gems.json` (4 spaces; `region_id` first, `name` second) | One room edit produced a whole-file diff, destroyed `git blame`, and reordered authored keys — which the engine does not care about but a human diff does. |
| D12 | **Opening a content set writes directories into it.** `DatabaseManager._init` created `npcs/ items/ magic/ quests/ templates/ campaigns/` unconditionally, so pointing the editor at `orbital_salvage` would create `data/magic/` and `data/quests/` in a set that deliberately has neither. | `DatabaseManager.gd:42-52` | The editor's first act on a new world is to add vocabulary the world does not use — the same class of leak as the retired `pickaxe` default. |
| D13 | **`all.txt` is a 268 KB stale source dump, tracked in git, at the editor root.** It contains pre-reconciliation copies of the scripts. | `git ls-files mud-world-editor/all.txt`, last written 2026-09-13 | Greps — human and automated — match the stale duplicate first. It should be deleted. |
| D14 | **`_proxy_positions` could reach content.** The editor's key rule is "anything `_editor_*`", but this editor-state key predates the prefix and is written onto the region dictionary, so a save put it in `data/regions/*.json`. | `RegionManager.gd:123-124`, `EditorLayout.gd:139-140` | Editor state in a file the engine reads. Latent — no shipped file has it yet. |
| D15 | **The last entry of a file could not be deleted.** A file was only rewritten if some entry still pointed at it, so deleting the final item of `library.json` left the file untouched and the entry returned on the next load. | `DatabaseManager.gd:187-205` | "Delete" that does not delete. |

## 3. Friction in the daily loop

- **Edit → Save → restart the server.** There is no hot reload and no watch;
  every iteration costs a restart. Both Save buttons write different subsets of
  state (`InspectorController.gd:87-90` vs `ContentLibraryDialog.gd:396-400`) and
  the library warns about nothing when closed with pending edits.
- **Undo covers a minority of edits.** Ctrl+Z/Ctrl+Y is keyboard-only, capped at
  50, and covers graph operations (connections, room create/delete/move, renames,
  districts, auto-arrange) while *not* covering paste, the paint and stamp tools,
  every inspector field edit, every database edit, or template saving. Two buttons
  are labelled "(undoable)" — an admission that most are not.
- **All diagnostics are console-only.** ~20 `push_error`/`print` sites; the only
  dialogs are the validation and region-policy modals. An author who does not have
  Godot's console open never learns that a write failed.
- **Every room click re-reads every region file** (`RoomConnectionsPanel.gd:25` →
  `WorldManager.gd:71-83`, 24 files), and every structural refresh rebuilds the
  whole node tree (`LocalViewBuilder.gd:60-76`).
- **The Explorer's region list is cached forever** — a newly created region
  disappears from the tree on the next edit until restart
  (`Main.gd:21,1047-1060`).
- **No shortcut map, documented nowhere.** The editor has no README; `all.txt` is
  not documentation.
- **District territory is recomputed per redraw** over a ~5,000-cell grid against
  ~40 member rooms and ~45 segments — per mouse-motion frame while dragging. The
  author's own comment calls it "the single most-executed loop in the whole
  renderer" (`GraphController.gd:513-517`), so this is known, not overlooked.

## 4. What the editor cannot author at all

The editor has working surfaces for **items, NPCs, regions/rooms (with districts)
and abilities — plus a partially-wrong quest surface.** Everything else the
engine reads has none:

| Engine content | Loaded by | Editor surface |
|---|---|---|
| `crafting/` recipes | `crafting_manager.py:24-39` | none |
| `dialogue/` graphs | `content_set.py` dialogue validation | none |
| `contracts/world_contracts.json` | `engine/contracts/registry.py` | **read by `ContractCatalog.gd`, referenced by no UI code** |
| item `item_family` / `generation_profile` | `content_set.py:1388-1413` | none — so the fields the contract validator checks cannot be set |
| `resources` (`kind`, `label`, `short`, `max_stat`, `regeneration_stat`) | `contracts/resources.py` | none |
| `attack_profiles` / `defense_profiles` / `effect_packets` | `contracts/equipment.py` | none |
| `player/backgrounds.json` | `core/backgrounds.py` | none |
| `titles.json`, `collections.json`, `discoveries.json` | `content_set.py` | loaded at most; never written |
| `campaigns/` | `content_set.py` | loaded, never written |
| `combat/elements.json`, `world/`, `knowledge/`, `profiles/` | engine | none |
| `abilities/` (the directory the loader now *prefers* over `magic/`) | `spell_registry.py:34-37` | invisible — the editor hardcodes `magic/` |
| any content set but `fantasy_frontier` | — | not reachable: no switcher, and `editor_settings.json` is read but never written |

## 5. Recommended tasks, in order

### Batch A — stop losing work (small, local, high leverage)
1. **Refuse to navigate away from a dirty region** without confirmation, and
   clear the undo stack when the loaded region changes. (`Main.gd:605-611`,
   `RegionManager.gd:20-21`, `CommandProcessor.gd`.)
2. **Make saves return a result**, and only `mark_clean()` on success; surface a
   dialog on failure. Add a close-request handler with the same prompt.
3. **Make a failed region load non-destructive**: keep the last good data, refuse
   to save over a file that failed to parse, and say so in a dialog.
4. **Fix the two one-line bugs**: `DataRoot.ruleset_path()` in
   `_validate_region_policy`, and `path_join` in `_patch_external_references`.
5. **Confirm database deletes**, and push them through the undo stack.
6. **Preserve top-level keys the editor does not model** (`affixes.json`), or
   treat `sets.json`/`affixes.json` as read-only the way campaigns already are.
7. **Write 4-space JSON**, matching the content convention.

*Why first:* each is a few lines, none needs a design decision, and together they
close every way the editor can silently destroy an author's work.

### Batch B — make the surfaces honest
8. **Rewrite the quest stage inspector to the real schema** (`objective` +
   `objectives_any`, `turn_in_id`, `completion_dialogue`, `stage_index`), with an
   objective-type list that comes from the engine's own objective vocabulary
   rather than five invented types.
9. **Make the editor's validation the engine's validation** — a button that runs
   `toolkit/content_set_validator.py` for the resolved content set and shows the
   same issues `run_content_checks.py` would. The editor's own link checker stays
   as a fast pre-check, not the final word.
10. **Neutralise the content vocabulary**: read `abilities/` when a set has it,
    and stop creating directories (`magic/`, `quests/`, `campaigns/`) in sets that
    do not declare those systems.
11. **Delete `all.txt`** and add a short editor README (what it is, how to point it
    at a content set, the shortcut list).

### Batch C — author the engine as it is now
12. **Wire `ContractCatalog` into the UI.** It already reads the same file as the
    engine; what is missing is controls — a family/profile picker on the item
    inspector (`item_family`, `generation_profile`), and read-only views for
    resources, attack/defense profiles, abilities and effect packets, so an author
    can see what a family means before naming it.
13. **Recipe authoring** for `data/crafting/`, and **dialogue graph authoring** for
    `data/dialogue/` — the two content systems with real player-facing weight and
    no surface at all.
14. **A content-set switcher** that writes `editor_settings.json` and reloads, so
    `orbital_salvage` and the other sets are reachable without a command line.

### Batch D — make it verified
15. **Run the 10 headless editor tests in CI** (they need Godot; a job that runs
    `content_source_check.gd` at minimum would have caught D10's dead path and
    would catch D11's indentation churn if a round-trip is added).
16. **Add tests for the untested four**: save (write → re-read → compare, including
    unknown-key preservation), undo (commit → undo → compare, and across a region
    switch), deletion (room and database entry), and error paths (malformed JSON,
    missing file, read-only target).
17. **Keep the dirty-state contract in one place** — a small `EditorSession` object
    that owns "current region + dirty + undo stack" would make the Batch A fixes
    structural rather than four separate checks.

### Not recommended
- **Rewriting the editor's UI framework or its district geometry.** They work, they
  are tested, and the failures above are all local.
- **Chasing the per-frame territory recomputation before the safety fixes.** It is
  known, bounded at the content's current scale (46 rooms), and it costs an author
  patience rather than work.

## 6. Batch A — implemented (2026-09-20)

Everything below is in the tree, with the behaviour pinned by two new headless
tests. `run_editor_checks.py` runs all 12 editor checks in one command (Godot is
probed, not assumed; `--godot`/`$GODOT_EXE` override).

| Batch A item | What it does now | Where |
|---|---|---|
| Dirty-navigation guard | Loading another region while the current one is dirty raises a confirmation; refusing is the default, and the edits survive a cancel | `Main.gd:_load_region`, `EditorUIManager.confirm` |
| Undo does not cross regions | `CommandProcessor.clear_history()` on every successful load | `CommandProcessor.gd`, `Main.gd:_load_region_now` |
| Saves are verified | One writer, `SaveIO.write_json`, writes and reads back; every caller keeps its dirty state and shows a dialog on failure | `SaveIO.gd`, `RegionManager.save_region`, `DatabaseManager.save_all`, `WorldManager.save_world_layout` |
| Quit is asked about | `NOTIFICATION_WM_CLOSE_REQUEST` with **Save and quit** / **Quit without saving** / **Keep editing** | `Main._request_quit`, `EditorUIManager.show_quit_prompt` |
| A failed read is non-destructive | The loaded region and filename are left alone, `load_error` says why, and `save_region` refuses when nothing valid is loaded | `RegionManager.load_region/can_save` |
| Region policy check works | Paths come from `DataRoot`; the interpreter is probed instead of hardcoded | `Main._validate_region_policy`, `Main._find_python` |
| Cross-region repair works | `path_join`, a parse guard that refuses to rewrite what it could not read, and the verified writer | `RegionManager._patch_external_references` |
| Deletes are confirmed and undoable | One confirmation dialog, then a `cmd_proc` commit whose undo restores the entry with its data | `Main._confirm_delete_db_entry/_delete_db_entry`, `DatabaseManager.delete_entry/restore_entry` |
| Unmodelled keys survive | Non-entry top-level keys are recorded at load and re-emitted on save; `sets.json`/`affixes.json` are not loaded as items at all | `DatabaseManager.file_extras`, `READ_ONLY_ITEM_FILES` |
| Deleting the last entry sticks | A file the editor loaded is rewritten even when it has no entries left — scoped per directory, so a relative filename in one category is never written into another | `DatabaseManager.known_files`, `_save_category` |
| Files are written as content is | 4-space indent and **authored key order** (`sort_keys = false`; the default alphabetised every object) | `SaveIO.INDENT/SORT_KEYS` |
| No directories are created on open | `DatabaseManager._init` no longer makes `magic/`, `quests/`, `campaigns/`; a directory appears when a file is written into it | `DatabaseManager._init`, `_ensure_dir` in the save path |
| `_proxy_positions` is editor state | Added to the editor-key namespace, so it lands in the sidecar and never in `data/` | `EditorLayout.LEGACY_EDITOR_KEYS` |

**Two defects were found while implementing, by the new tests:**

- `JSON.stringify` sorts keys by default, so the editor had been alphabetising
  every object in every file it saved (D11). Found by asserting the authored key
  order of a saved region rather than only its indentation.
- The first cut of the "rewrite a file whose entries were all deleted" fix keyed
  known files by relative name alone, which wrote an empty `library.json` into
  every other content directory. Found by listing the scratch content set after a
  test run; the fixture now asserts no stray files. The same run also caught a
  `load_all()` I had dropped from `DatabaseManager._init`, which would have opened
  the editor with an empty content library — an integration test through
  `Main.tscn` is what saw it, not the unit-level checks.

**Verification.** `run_editor_checks.py`: 12/12 pass, including the two new
suites:

- `tests/editor_save_safety_smoke.gd` — the writers: verified writes, refusals, a
  failed read leaving the loaded region intact, unknown keys surviving, read-only
  item files byte-identical after a save, delete-then-reload, delete/restore,
  the cross-region rename repair, editor keys never reaching content, and history
  clearing. All against a throwaway content set under `tmp/`.
- `tests/editor_session_safety_smoke.gd` — the same guarantees driven through the
  real `Main.tscn`: the prompt that stands between a region click and an hour of
  work, cancelling keeping the edits, a failed save staying dirty with a dialog,
  a confirmed-and-undoable delete, and the quit prompt.

Python suite and content checks are unaffected (the editor is not on their path),
and were re-run to confirm it.

**Still open from Batch A's intent:** autosave (the quit prompt exists; a timed
save does not), and the `settle` of undo coverage — inspector field edits, paste,
and the paint/stamp tools remain outside the undo stack. Both are Batch B/D
material rather than safety gaps: nothing in them can lose work that was already
saved.

## 7. Batch B — implemented (2026-09-20)

**The quest surface writes the engine's schema.** `QuestInspector` was rewritten
against a new `scripts/data/QuestSchema.gd`, which holds the engine's objective
vocabulary — 15 types, each with the fields the tracker or validator reads and a
note naming where the engine reads it — plus the stage-level fields. Adding or
reordering stages renumbers `stage_index` (the engine reads order from the list),
alternative routes are editable as first-class objectives, `choices` outcomes get
their own editor because "every outcome must declare `next_stage` or `complete`"
is a validation failure the editor can prevent, and every key it does not model —
including the engine's own `_spawn_on_entry_triggered` — is shown and preserved
rather than dropped.

**The engine now refuses the shape that fooled it.** `content_set.py` gained
`_validate_quest_stages`: a stage with neither `objective` nor `objectives_any`
has no route to satisfaction (`get_active_objectives` returns `[]`), so it is an
error. The message names the fields that misled the author:
`"quest 'quest_wildflower_commission' stage 1 declares neither 'objective' nor
'objectives_any', so nothing can satisfy it. It carries count, id, next, target,
type, which is not a stage field the engine reads."` The shipped content set has
zero errors under it; the old editor shape now fails loudly instead of passing
with zero errors — which is the D2 reproduction, inverted.

**The editor runs the engine's validation, not a second opinion.**
`toolkit/editor_validate.py` runs the same five checks `run_content_checks.py`
runs (content-set schema, reference integrity, template placeholders, stale
references, JSON integrity) in one interpreter and prints one JSON document;
`scripts/data/EngineValidator.gd` runs it and parses it; a **Validate Content
(engine)** button shows the merged issues, with overlapping findings reported once
and labelled with every validator that saw them. It is a new entry point rather
than `--json` on five scripts so the editor makes one subprocess call and cannot
drift onto a different set of checks than CI. `toolkit/stale_reference_audit.py`
also had its sibling import made dual-mode, because `import
toolkit.stale_reference_audit` used to fail outright.

**Ability definitions are visible in the sets that name them.** The engine prefers
`data/abilities/` and falls back to `data/magic/`; the editor now asks the same
question in the same order (`DatabaseManager.abilities_dir`), so
`orbital_salvage/data/abilities/overcharge.json` is editable instead of
invisible. The internal cache is still called `magic` and the inspector still says
"Spell"/"Mana Cost" — a vocabulary pass over ~50 strings is its own batch, and a
half-renamed UI would be worse than an honest one.

**`all.txt` is gone**, and the editor has a README: how to point it at a content
set, what it can and cannot author, the shortcut list, the save semantics, and the
command that runs its tests.

**Verification.** Three new checks, and the suite now stands at 14:

- `tests/quest_inspector_smoke.gd` — renders an existing stage without touching
  it, adds a stage and asserts it carries `objective`/`stage_index` and *not* the
  old `type`/`target`/`count`/`next`, reorders and renumbers, keeps unmodelled and
  runtime keys, exercises choices, checks the vocabulary against the engine's — and
  then hands the saved quest to the **engine's validator** and asserts a stage
  authored here validates clean.
- `tests/engine_validation_smoke.gd` — the subprocess seam: it runs, parses past
  the engine's import logging (CRLF included), reports relative paths, fails a
  broken content set, and reports a missing interpreter as a setup problem.
- `server/tests/singles/test_editor_validate.py` (9 tests) and four new
  `test_content_set_validator.py` cases pin the Python side: the validator runs
  every check, dedupes across them, and the new stage rule accepts `objective`
  and `objectives_any` while naming the old shape.

## 8. Batch C — implemented (2026-09-20)

**Item contracts are authorable.** The editor could read
`data/contracts/world_contracts.json` (`ContractCatalog`, used only by a test) but
no inspector offered a single field from it — including `item_family` and
`generation_profile`, the two fields the content validator checks on *every*
template. Now:

- `ContractCatalog` indexes attack and defense profiles too, and answers the
  questions an inspector asks: a family's class, capabilities and icon style; the
  profiles belonging to a family; the bands a profile declares; families by class
  and by capability.
- The **item inspector** has a family picker and a roll-table picker, says what
  the chosen family makes the engine build (and when it overrides the template's
  own `type`), and offers intrinsic rarity from *the profile's* bands — the list
  used to be the fantasy set's four rarity names, which a set with its own band
  names could not express at all.
- The type dropdown now lists the engine's item classes. It used to offer "Tool"
  and "Material", which are not classes: a template with one of those names no
  engine class, so `ItemFactory` refuses to build it and the item cannot exist.
  (No shipped template used them — checked — so this was a trap rather than a bug.)
- A **Contracts browser** shows everything the set declares — families, profiles,
  resources, attack and defense profiles, abilities, effect packets — because
  asking an author to type a family id that nothing in the UI explains is how
  typos become validation failures. It is read-only: the schema decides what may
  exist, and a freehand editor would be a second schema.

**Recipes are authorable.** `data/crafting/*.json` had no surface at all, so the
one system connecting items to each other was hand-written JSON. A **Recipes**
category in the Content Library edits the engine's fields
(`engine/crafting/recipe.py`): name, aliases, description, result item and
quantity, station, an *explicit* difficulty (a switch, because absent means the
engine derives it from the result's value — a spin box would write 0 on every
recipe it touched), `requires_discovery`, ingredients, quality tiers (with
`gift_bonus`, `min_material_quality` and `rank` preserved as JSON), and
familiarity milestones. Structural rows add and remove; unmodelled keys are named
and kept.

**The editor can open another content set.** `--data-root` was the only way to
choose a world; now "Open Content Set…" lists the sets beside the checkout,
switches by reloading every manager (regions, library, contracts, world layout),
re-points the contract browser, and writes `user://editor_settings.json` so the
next launch agrees. An unsaved edit raises the same prompt as quitting, including
the "switch without saving" branch — a dialog offering only save-or-cancel pushes
an author into saving work they meant to drop.

**Verification.** Three new checks (17 total):

- `tests/contract_authoring_smoke.gd` — the catalog's answers, a family chosen
  through the picker writing `item_family`, the class-mismatch note, rarity
  offered from the profile's own bands, the browser's sections — then saves and
  has the **engine's validator** check the result.
- `tests/recipe_authoring_smoke.gd` — the recipe loads, the widgets write the
  engine's fields, add/remove works for ingredients, tiers and milestones, an
  unmodelled key survives, and the saved recipe passes the engine's validator
  (which resolves every ingredient and the result against real templates).
- `tests/content_set_switch_smoke.gd` — drives the real `Main.tscn` between two
  scratch content sets and asserts *everything* reloaded (region, items, recipes,
  contracts), that the settings file names the new set, that an unknown path is
  refused, and that the contract browser follows.

**Still open for the editor:** dialogue-graph authoring (the largest remaining
gap: P5's graphs have real player-facing weight and no surface), contract
*editing* (the browser is read-only by design; authoring the families themselves
is a schema-shaped feature, not a form), a vocabulary pass over the ~50 places
the UI still says "magic"/"spell" while editing ability data, and CI for the
editor tests.

## 9. Batch D — implemented (2026-09-20)

**Dialogue graphs are authorable.** `data/dialogue/*.json` was the last content
system with no surface, and the one with the most player-facing weight: a
conversation can gate a reply on what the player has done, teach a recipe
mid-sentence, or let a negotiation go two ways. All nine shipped graphs were
hand-written JSON.

- `DialogueSchema.gd` holds the engine's two vocabularies: the 17 **condition
  kinds** (`engine/conditions.py`) with their fields and a note saying what each
  reads, and the 15 **effect keys** (`engine/dialogue/effects.py`) with the
  payload shape each one expects. An unrecognised condition kind fails *closed*,
  so a typo silently closes a conversation — the picker is how that stops.
- A **Dialogue** category in the Content Library edits a graph: nodes with text
  (including presentations that carry `player`/`test` variants), choices with
  aliases, a condition built from the schema's kinds, effects picked from the
  known list with a shape hint, and a **target picker over the graph's own node
  ids** rather than a text field.
- **Renaming a node repoints every reference to it** — `next_node` and a check's
  `success_node`/`fail_node`, plus the graph's `root`. That is the operation a
  hand-edited graph gets wrong, and the one content validation then reports as a
  choice that leads nowhere.
- Dialogue needed its own loader: one *graph* per file, not a library of entries,
  because `nodes` is the graph's own structure. `_load_file`'s single-vs-library
  heuristic would have read the node map as a second entry. Saving writes each
  graph back to its own file, and deleting a graph takes its file with it.

**A real bug this found, in my own code and worth naming.** GDScript's `or`
returns a *bool*, unlike Python's, so `str(x or fallback)` does not fall back — it
produces `"true"`. Four places I had written that idiom, including the graph id:
every graph loaded as `"true"`. The dialogue test caught it on first run
(`dialogues: ["true"]`) because it asserted on ids rather than on "something
loaded". All four are fixed, and `DialogueSchema.value_of` is the one place the
nullable-id idiom now lives.

**The editor tests run in CI.** `.github/workflows/editor-checks.yml` downloads a
pinned Godot, imports the project once (the `--script` runs need the class-name
registry), runs `run_editor_checks.py`, then runs the content checks — the other
half of the same surface, since those validators are what the editor's "Validate
Content" button calls. It is unverified until it runs on GitHub; it is written to
fail loudly rather than skip.

**The UI says "ability", not "spell".** The category, its create button, the
group manager, the inspector headers and the database filter now read "Abilities"
/ "Ability Group" / "Cost". The *keys* stay `magic` — the category key is a cache
name, a dirty-flag key, and the name of persisted editor state
(`magic_groups.json`) — and that is recorded here rather than renamed halfway.

**Verification.** `tests/dialogue_authoring_smoke.gd` (18 editor checks in total)
loads graphs through the dedicated loader, drives the inspector, adds a node,
renames one and asserts every reference followed, checks both vocabularies
against the engine's, and ends twice with the engine's verdict: once that a graph
edited here validates clean, and once that **deleting a graph an NPC still points
at is reported** rather than leaving a silent hole.

## 10. Following the engine: ingredients that name a rule (2026-09-21)

The engine's crafting seam learned to read an ingredient as a *reference* rather
than an item id — an exact template, an item family with an optional material
grade floor, or a capability a family declares
(`docs/design/cross_theme_engine_contracts.md`, step 4). The editor followed in
one place, because until it did, a recipe using the new shape could only be
hand-written JSON.

- Each ingredient row now leads with a **kind picker** — `item_id`,
  `item_family`, `capability`, in the engine's resolution order — and the field
  beside it changes placeholder and suggestion source to match. Switching the
  kind writes exactly one reference: the engine resolves the first it finds and
  ignores the rest, so an ingredient carrying two was an authoring trap rather
  than a feature. A value only carries across the switch when the new kind
  actually knows it, which is why changing a template id to a family empties the
  field instead of saving `item_family: "item_servo_cluster"`.
- A **material grade floor** spin box sits next to it, enabled only for the kinds
  where the engine reads one. A template reference is one exact thing, so a floor
  on it would be a second, contradictory answer — switching back to `item_id`
  takes the floor with it, the same way the reference moves.
- `ContractCatalog.capability_ids()` enumerates the capabilities this content set
  actually declares, so the picker offers the set's own vocabulary rather than a
  hard-coded list. A content set with no contracts offers none, which is honest:
  it has no families for a capability to belong to.

**A bug the test caught, and the shape of it.** The picker switched, the label
changed, and the reference was still written under `item_id` — because the
field's `text_changed` closure captured the *local* variable holding the kind.
GDScript lambdas capture by value, so the handler kept writing the kind the row
started with. The smoke test asserted on the dictionary rather than on the
widget, which is exactly what made it visible: the field looked right. The
current kind now lives in a small dictionary the closure reads through.

**Recipe editor extras.** A recipe file's top-level `_comment` is a note to the
reader, and the crafting loader crashed on one (`'str' object has no attribute
'get'`), which — because one bad key aborts the whole file — silently removed
every recipe in that file. Two tests in `test_crafting_manager_full.py` pin the
fixed behaviour: notes and non-object recipe values are skipped, the rest load.

**Verification.** `tests/recipe_authoring_smoke.gd` gained
`_check_an_ingredient_can_name_a_rule`, and its engine-verdict case now saves a
recipe carrying one ingredient of each kind — a template, a family with a grade
floor, and a capability — so the validator is asked to resolve all three from the
same file. The Python side is
`tests/singles/test_crafting_reference_ingredients.py` (27 tests) and eleven new
cases in `test_content_set_validator.py`.

## 11. One control for one shape (2026-09-21)

The engine extends the same authored reference to the other two places content
asks for an item — a vendor's `buy_orders` entry and an item's own
`salvage_output` — so the editor stopped growing a second copy of the row.

- **`ReferenceEditor.gd`** is the kind picker, the reference field with its
  suggestions, and the material-grade floor, in one place. The recipe ingredient
  row and the item inspector's new salvage section both build it. The lesson from
  batch 10 is baked in rather than repeated: the current kind lives in a
  dictionary the closures read through, because GDScript lambdas capture by
  value and a captured kind silently writes the wrong key after a switch. The
  picker is named (`ReferenceKindPicker`) so a test can find it on a panel that
  has four other OptionButtons.
- **The item inspector can author salvage output.** The property is a nested
  object and the property editor offers string/number/bool/equip-slot rows, so
  `salvage_output` was hand-written JSON — which is why exactly eleven templates
  in the fantasy set said "leather, not iron" and no others said anything. There
  is now a switch and a reference row, with the rate beside it and a sentence
  saying what answers instead when the switch is off.

**Verification.** `tests/item_authoring_smoke.gd` (19 editor checks in total)
drives the switch and the row, asserts the kind picker offers the engine's three
kinds in its resolution order, asserts that switching kind clears the reference
it is no longer using, and ends with the engine's verdict on a template whose
salvage output names a family rather than a template.
