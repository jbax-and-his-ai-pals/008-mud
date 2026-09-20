# Track D — Content Loading & Contracts

## Assessment

**State.** `content_set.py` is 2629 lines: one front door (`load_content_set`, `:2390-2624`) calling 24
`_validate_*` families over 38 `_load_json` sites, 17 `_load_definition_ids` sites (12 re-reading `items/`),
four walks of `crafting/*.json` and five of `regions/*.json`. `world/` then builds from the same files
(`definition_loader.py:51-176`, `region.py:50-70`, `room.py:196-218`), with `spawner.py`,
`housing_manager.py`, `instance_manager.py` and `region_generator.py` reading authored properties at play
time. Two toolkit gates read the same files again.

**Strongest.** The reachability traversal (`:558-657`): a real adjacency walk with `hidden_exits` as edges
and an explicit `entered_by_system` exemption — the fix for the Portbridge class, copied by every later
check. And `:2198-2204` constructs the real `Recipe` and reports what it refuses, so gate and loader cannot
drift.

**Weakest.** The id tables index *keys*, not entries a loader can produce: `_ability_ids:958-962`, the
quest/recipe tables `:976-983`, and `:1962` never check the value is an object. That is what hides the
quests loader. `core/quests/loader.py:17` neither skips `_` keys nor checks `isinstance(q_data, dict)`, and
its `try` wraps the whole file (`:14-34`), so a `_comment` header — the convention
`crafting/fabrication.json:2` already uses — raises at `:20` and every quest in `quests/quests.json` is
gone. Validation stays green (`quest_ids` is read from the file itself, `:741`; all six
`authored_board_templates` name ids from it); the only signal is `Logger.warning` at
`core/quests/manager.py:158`. Recipes compare declared against loaded
(`content_playability_check.py:347-361`) and abilities at least fail the build (`:324-327`); quests do
neither.

**Surprises.** (1) The shared-loader hypothesis is half wrong: of ~18 in-engine readers only "read one JSON
object, refuse malformed entries, name file and field" is shared — keying differs (payload id
`definition_loader.py:79-95`, filename `:171-174`, one-per-file `campaign_manager.py:31`, three files merged
`quests/loader.py:9`), destination differs (`Logger`×2, `print`×3, `issues`×5, counters×3, one sink, nothing
at `affix_data.py:28`), and refusal already lives in the constructors (`crafting_manager.py:56-60`). A
`BaseLoader` would be a sixth shape, not a unification. (2) The `_` convention is in 14 loaders and ~30
validator sites, missing in two loaders and at `content_set.py:1962`. (3)
`crafting_manager.recipe_errors:24-27` says boot warnings read it; `headless_server.py:169-172` polls five
managers and not that one. (4) `affix_data.py:32-33` mutates globals that `loot_generator.py:7` bound at
import, so the last `World` built in a process sets every world's affixes — and the playability check boots
all four sets in one process. (5) `_load_regions` keys regions by filename (`definition_loader.py:171-174`)
while validation keys them by `region_id` (`:541`); they agree only because every file is named after its id.
`dynamic_themes.json` — skipped by every validator (`:311`, `:336`, `:433`) — is read by
`region_generator.py:24-33` with no shape check.

## Proposed roadmap

### 1. One content index per validation run

**What.** A call-local `ContentIndex` in `load_content_set` — parsed payloads by path, id tables by family —
serving the 17 `_load_definition_ids` sites and the crafting/regions walks.
**Why now.** Not speed (38 parses of small files is milliseconds) but policy: each site re-decides the
`_`/isinstance rules, which is how `:1962` came to disagree with `:976`.
**Depends on.** Nothing. Keep it call-local; the mtime-keyed registry cache (`:2045-2070`) is the precedent.
**Scope.** Medium. **Done when.** An instrumented run over all four sets shows each path parsed at most once
per call, a `_comment` in a recipes file yields the same id set from every reader, gates green.
**Risk.** 13 test modules import from this file, twelve of them private names (`test_content_set_runtime.py:13`),
so the refactor must stay name-preserving.

### 2. Id tables may only index entries the loader can produce

**What.** In `_ability_ids:958-962`, the quest tables `:976-983`, `_load_recipes:1404-1416` and `:1962`,
require an object value before the key becomes a reference target; report key, file and field.
**Why now.** It is the one validator-side change that catches the quests-loader class, and it fixes the
`:1962` inconsistency without editing a loader another track owns.
**Depends on.** Nothing. **Scope.** Small. **Done when.** `"quest_x": "text"` in `quests.json`, and a
non-object value in `magic/*.json`, each error naming the key and are not offered to reference checks; a
`_comment` produces no finding.
**Risk.** If shipped content holds a non-object value under a real key the build reddens — intended, and
answered with a content fix or a reasoned allowlist, never a suppressed check.

### 3. Refuse duplicate JSON keys at the reader

**What.** An `object_pairs_hook` in `_load_json` (`:178-185`), and in the shared helper once item 1 lands.
**Why now.** `json.load` keeps the last duplicate, so an authoring mistake becomes a silent behaviour
change; the ROADMAP P2 near-miss (a duplicated `properties` block that swallowed a flag) is exactly this and
is invisible to every gate.
**Depends on.** Item 1 for the single-reader form. **Scope.** Small. **Done when.** A duplicated key yields
an error naming file and key, and all four sets validate clean. **Risk.** Land it report-only first.

### 4. Validate placement overrides, and report the ones the loader drops

**What.** `_validate_authored_world` checks room `items[].item_id` (`:618-622`) and the *type* of
`initial_npcs[].overrides` (`:616`) but not `properties_override`, which `definition_loader.py:232` unpacks
unguarded (`TypeError` at world init for a string), nor the allowlist at `:245-250`, which silently discards
any key outside its seven.
**Why now.** One `properties_override` is already authored; the failure today is a traceback inside
`initialize_new_world`, not a message an author can act on.
**Depends on.** Nothing. **Scope.** Small. **Done when.** `"properties_override": "burning"` and an unknown
key inside `initial_npcs[].overrides` each error naming `region:room` and the field, and world init cannot
raise on a placement ref that passed validation.
**Risk.** What a placement may override is Track E's call — ask the loader/`NPCFactory`, do not keep a
second copy of the list.

### 5. Validate `ruleset.player_defaults.starting_inventory`

**What.** Check the list shape, each `item_id` against the item table, and `quantity` as a positive integer,
naming the ruleset path and the entry index.
**Why now.** Live in `fantasy_frontier` (3 entries) and `orbital_salvage` (2) and read by
`grant_starting_inventory` (`definition_loader.py:178-198`), which skips a dangling id with a
`Logger.warning` (`:194`) and calls `int(...)` unguarded (`:188`). It is the P4 "background with no foraging
knife" class one layer down; nothing covers it (`reference_integrity_validator.py:470-472` walks NPC
`initial_inventory`, not this).
**Depends on.** Track H for the fixture. **Scope.** Small. **Done when.** A dangling starter item and a
non-numeric quantity each fail validation naming the ruleset file and entry index.
**Risk.** Overlaps Track I item 6 (`content_values` widening) — this is a reference/shape check in D's validator.

### 6. Quest instance templates: check what the generator reads

**What.** `quests/instances.json` fields consumed by `core/quest_generation/generator.py`:
`objective.possible_target_template_ids` (`:91`), `possible_entry_regions` (`:101`),
`layout_generation_config.min_rooms/max_rooms/possible_room_names/target_count` (`:98`, `:206-219`).
Content_set checks list non-emptiness and range order; the reference half is handed to Track I as
`REFERENCE_FAMILIES` rows rather than reimplemented.
**Why now.** The one shipped instance template uses all of them; a bogus creature id reaches
`instance_manager.py:183` as a runtime failure and `min_rooms > max_rooms` raises in `random.randint`
(`generator.py:207`).
**Depends on.** Track I accepting the reference half. **Scope.** Small. **Done when.** A bad range or empty
list fails validation naming file and field, and (if I takes it) a bogus `possible_target_template_ids` entry
exits `reference_integrity_validator.py` non-zero.
**Risk.** If I declines, only the shape half lands and dangling ids still reach the generator.

### 7. Split `content_set.py` at the seams it already has

**What.** Keep `content_set.py` as front door and re-exporter; move validator bodies into
`engine/server/content_validators/{manifest,world_content,ruleset,quests_dialogue,contracts_content}.py`
along the boundaries the file already has: manifest `:27-200`, world/region policy `:201-660`,
ruleset/starting `:660-940` and `:1795-2044`, id tables `:940-1043`, dialogue+quests `:1044-1503`,
contracts/economy/items `:1504-2380`.
**Why now.** 31 top-level functions across ~8 unrelated domains, appended to at the end; items 1-6 land here
anyway, so the seams are being redrawn regardless.
**Depends on.** Items 1-3. **Scope.** Medium. **Done when.** No file exceeds ~600 lines, every currently
imported name resolves from the same path (`test_content_set_direct.py:16`, `test_region_policy_validator.py:15`,
and the twelve private names at `test_content_set_runtime.py:13`), gates green.
**Risk.** Pure churn, no correctness gain, on the file every other track imports.

## Explicitly not proposing

- **A `BaseLoader` template-method class.** The loaders are not alike (keying, destination, refusal — see
  Surprises) and refusal already lives in the family constructors. Item 1 plus a documented convention is
  the whole of the win.
- **Re-listing a family's field vocabulary in `content_set`.** B owns `Spell`/`Recipe`/`Title`; the check
  asks the reader. Handoff: ask E to make `Spell.__init__` (`magic/spell.py:24-25`) name the missing field
  rather than raising `TypeError` out of `from_dict`.
- **Fixing `quests/loader.py` / `spell_registry.py` / `recipe_errors` / the `affix_data` globals here.**
  All four are Track E's lane (`core/**`, `magic/**`, `crafting/**`, `items/**`); filed as findings, with
  item 2 supplying the validator-side half of the first.
- **A closed vocabulary for exit directions.** Refused on evidence: content ships `climb`, `descend`, `dive`,
  `surface`, and `go <direction>` (`movement.py:67`) lowercases any word and passes it to `change_room`, so
  those exits work. `DIRECTIONS` (`movement.py:9-25`) is a command list, not a validity boundary.
- **A duplicate-key gate in `toolkit/`.** I's lane; the reader refusing is stronger (item 3).
- **Caching the content index across runs.** The editor validates files it just saved.
- **Track I's inbound content_set items** (condition buckets `:1117-1197`, the `(kind, field, bucket)` table).
  Already filed and owned there; D implements, does not re-propose.

## Risks

- **Every item here is a check, and a check nobody falsified is decoration.** H's rule applies to all six;
  none should land without a demonstrated failing case.
- **Widening reddens green gates on real content** (items 2, 4, 5) — content fix or reasoned allowlist, never
  a suppressed check.
- **Items 1 and 7 touch the module every track imports**; E and I are mid-flight against it.
- **Handoff dependence:** item 6's reference half and item 4's override vocabulary belong to another track's
  reader. Declined handoffs leave the items half-done and the dangling reference alive.
- **Index staleness** if it outlives one `load_content_set` call — the editor's validate-after-save path.

## Unknowns

- Whether any shipped file has a duplicate JSON key today; I read the ROADMAP's near-miss, not the corpus.
- What `mud-world-editor` writes for room item refs — `items` (what validation checks, `content_set.py:618`)
  or `initial_items` (what `Room.from_dict` prefers, `room.py:209-210`). If the editor writes the latter that
  divergence is live, not latent. I did not open `mud-world-editor/`.
- Whether the save stack rebuilds rooms through `Room.from_dict` with `items` (Track C's lane) — same question.
- Whether any tool outside the three runners validates `dynamic_themes.json`; I checked `content_set.py` and
  `toolkit/*.py` and found only deliberate skips.
- Whether a player has hit the quests-loader drop; no log evidence was surveyed.
