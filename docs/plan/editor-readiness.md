# World Editor Readiness

## Current assessment — 2026-09-21

**Basis:** current working tree, including uncommitted configuration dialogs.
The planning review was followed by the first 6A hardening pass: staged engine
validation, recoverable single-file writes, actual dialog-event regression tests
and full-scene wiring/dirty-state checks. See
[configuration editing safety](../reference/configuration-editing-safety.md) for
behavior, limitations and the human retest. No visual usability pass is claimed.
Counts/line citations in the September 20 audit below remain historical.

**6A update:** the immediate blockers listed below have been addressed, with
regression coverage. The dialogs remain partial authoring surfaces, not complete
ruleset/contract coverage. Multi-file migration, broader field validation audits,
async save validation, visual/error-layout testing and shutdown resource-retention
cleanup remain open. Save runs the engine's content-set validator; it does not
substitute for the full release gate or runtime journeys.

**Verdict:** broad content-editing foundations, emerging configuration authoring,
but not yet a trustworthy complete game-authoring workflow. The next measure is
field-level, lossless and journey-proven coverage, not a count of CRUD panels.
The [game-authoring roadmap](game-authoring-roadmap.md) defines M0–M5; execution
order is [chunks §6](chunks-of-work.md).
Those supersede the ordered tiers in historical §7 below.

### What changed since the snapshot

| Area | Current evidence | Readiness interpretation |
|---|---|---|
| Ruleset | `RulesetEditorDialog` offers general settings, eight system toggles, custom factions, stats and region policy; `RulesetDraft` writes them. | **Prototype**, not “two read-only keys” and not coverage of every ruleset section. Capability coherence, reachability, lossless edits and save/refresh need proof. |
| Contracts | `ContractEditorDialog` and `ContractDraft` cover resources, families, generation, attack, defense, effects, abilities, work and stats. | **Prototype**, not browse-only. Typed data and save integration defects below prevent a readiness claim. |
| Combat vocabulary | `CombatVocabularyDialog`, its draft and catalog provide channel/hazard authoring; the ability inspector has a channel picker. | Preliminary integration; not a complete damage/hazard policy editor or proof that every consumer refreshes. |
| Item properties/NPCs | `PropertyTagRow` guards structured values; nested-property and NPC-stat vocabulary tests are present. | Historical defects must be rechecked rather than copied verbatim into the next queue. Preserving an unsupported object read-only is safer, but does not make it authorable. |
| Validation | `toolkit/editor_validate.py` now invokes open-set playability; `Main` has background validation and a separate release-gate path. | Historical “no playability button” is superseded. Preserve scoped/skipped/stale result reporting and test failure paths; bootability alone is not an authored-player-journey proof. |
| Project lifecycle | `ContentSetScaffold` creates a starter room and copies selected source material; existing set switching and round-trip tests provide foundations. | Not yet full manifest/system evolution, dependency-aware migration or reproducible authoring release workflow. Copying rules can introduce source-world references; that is surfaced in the scaffold's own contract. |
| Remaining content | Knowledge, campaigns, richer rules/policies, profiles/world data, presentation/opening and unsupported nested fields remain on the coverage ledger. | Inventory engine readers and actual fantasy usage before claiming “everything editable.” No new blanket percentage asserted here. |

### Initial M0 blockers (addressed by the first 6A pass)

These record what the planning review found. The new regression fixtures and
safe-save path address them; retain the descriptions as the reason for that work,
not as claims that the current implementation still behaves this way.

- [`Main.gd`](../../mud-world-editor/scripts/core/Main.gd), `_connect_ui_signals`:
  ruleset and contract save callbacks call `database_mgr.catalog.load()`, while
  [`ContractCatalog.gd`](../../mud-world-editor/scripts/data/ContractCatalog.gd)
  declares `load_contracts()`. Also trace the ruleset request from SidePanel through
  EditorUIManager: declaring a signal and connecting it in Main is not sufficient
  evidence that the button emits it.
- [`ContractEditorDialog.gd`](../../mud-world-editor/scripts/ui/modals/ContractEditorDialog.gd):
  `_stats_value()` routes string short labels through numeric `_map_split()`,
  discarding nonnumeric values; `_item_list_split()` splits on any `x` in a work
  item string, including inside an ID; `_payload_split()` turns typed values into
  strings. These paths need structured controls and preservation tests.
- [`ContractDraft.gd`](../../mud-world-editor/scripts/data/ContractDraft.gd):
  `_clean_entries()` omits blank-ID rows before `validate()` can report them;
  `save()` calls its local validator and `SaveIO`, not the authoritative engine
  validator. Partial local checks must not certify a valid contract.
- [`RulesetEditorDialog.gd`](../../mud-world-editor/scripts/ui/modals/RulesetEditorDialog.gd):
  saving writes every displayed section/system state, while an absent system
  declaration displays as false. Prove effective defaults are preserved and the
  manifest agrees; an unrelated field edit must not disable inherited capabilities.

**Required next evidence:** tests through actual dialog controls/callbacks, rich
records with unknown and nested fields, invalid input retained with an error,
cancel/revert, repeated open, save failure, external modification, set switch and
engine validation of the saved result. Existing fixture round-trip tests do not
automatically exercise new dialog serialization. UI layout and interaction still
need a human retest in addition to headless tests.

### How future updates should record coverage

For each engine-read field family, record its reader, validator, UI writer,
dependency/refactor support, no-op survival, meaningful edit, runtime journey and
recovery evidence. Use **absent / read-only / prototype / validated writer /
journey-proven** explicitly. Revisit stale claims below as work lands; do not
declare an entire game authorable while engine-used fields remain unsupported.

---

## Historical audit — 2026-09-20 (retained evidence)

The remaining sections describe the earlier snapshot. They are not the current
execution queue; findings and “open” labels may have been superseded by subsequent
working-tree changes. Preserve the record, but reproduce a finding before acting.

**How close is the editor to "edit and manage all aspects of the engine and its
capabilities", with easy content-set switching and robust validation?**

Measured 2026-09-20 by reading the editor's own code, running its validator and its
30-test suite, and diffing what the engine reads against what the editor can
write. Every claim here has a `file:line` or a command behind it. This document is
the assessment; the ordered work is at the end, and the fixes already made while
measuring are listed in §6.

**Short answer.** The editor is a genuinely capable *content* editor — regions,
rooms, items, NPCs, abilities, quests, recipes, dialogue, titles, collections,
discoveries, backgrounds and the manifest are all create/edit/delete with undo and
a real save path — and its validation is now closely tied to the engine's. What it
is *not* yet is an editor for the engine's **configuration**: the ruleset, the
contracts, the damage/hazard vocabulary, knowledge topics and campaigns are
read-only or invisible, and those are exactly where "the engine's capabilities"
are declared. Switching sets works and is now safe, with two gaps left. Validation
covers 10 of the 18 gate steps in-editor, and the eight it skips are listed to the
author with reasons.

---

## 1. What the editor can manage today

Verified by reading each inspector, not by its file name. Delete is undoable
through the command stack (`Main.gd:1034-1042`).

| Area | Read | Create | Update | Delete | Written back |
|---|---|---|---|---|---|
| regions, rooms, exits, districts, spawner | explorer tree + graph | creator modal, district generator, stamp tool | name, description, scalar properties, spawner, district fields, connections | rooms yes; **no region delete** | `save_region` |
| items (incl. gems) | library | yes | type, weight, value, stackable, family, profile, rarity, equip slots, salvage, **scalar** properties | yes | `save_all` |
| NPCs / monsters | library | yes | level, `max_mana`, declared stats, loot table | yes | `save_all` |
| abilities | library ("Abilities") | yes | cost, level, cooldown, target, effects, messages, group | yes | `save_all` |
| quests | library | yes | title, stages, 15 objective types, routes, turn-in, spawn fields | yes | `save_all` |
| recipes | library | yes | result, station, difficulty, ingredients, quality tiers, milestones | yes | `save_all` |
| dialogue graphs | library | yes | nodes, text, choices, aliases, conditions (17 kinds), effects (15 keys) | yes (file removed) | `save_all` |
| titles + `_guilds` | library | yes | name, description, guild registry, conditions | yes | `save_all` |
| collections, discoveries, backgrounds | library | yes | all modelled fields | yes | `save_all` |
| `content_set.manifest.json` | chooser (presence) | yes ("New content set…") | **no** — create-time only | **no set delete** | scaffold only |
| `rules/ruleset.json` | 2 keys (`world.regions.biomes`/`region_types`, `status.stats`) | no | **no** | no | never |
| `data/contracts/world_contracts.json` | contract browser, read-only | no | **no** | no | never |
| `data/combat/elements.json` | no | no | no | no | never |
| `data/knowledge/topics.json` | no | no | no | no | never |
| `data/campaigns/` | **loaded, invisible** | no | no | no | **never** |
| `data/profiles/`, `data/world/`, `presentation/`, `opening/` | no | scaffold copy | no | no | scaffold only |
| `data/items/sets.json`, `affixes.json` | skipped deliberately | no | no | no | never |

**Authorable: 12 of 21 areas. Reachable-but-unwritable: 1 (campaigns). Invisible:
5 (ruleset config, contracts, damage/hazard types, knowledge topics, profiles/world
data). Copied-not-edited: 2 (presentation, opening).**

### By engine capability

The capabilities an author declares are the engine's systems; this is the same
question asked the way the manifest asks it.

| Capability | Can an author deliver it through the editor? |
|---|---|
| `inventory` | **Yes** — items, containers, resource nodes, room placement. |
| `dialogue` | **Yes** — graphs, conditions, effects, flat topic `dialog`… except the flat `dialog` dict and `properties.dialogue` binding on an NPC, which have no widget. |
| `crafting` | **Yes** — recipes, stations (items), tiers, milestones, difficulty. |
| `collections`, `discoveries` | **Yes.** |
| `social` | **No** — the ladder is `ruleset.social`, and gift preferences are nested NPC properties; neither is editable. |
| `quests` | **Partly** — quests yes; campaigns no; `quest_generation` rules no; `rewards` has no widget. |
| `abilities`, `magic` | **Partly** — abilities yes; ability *contracts* and damage types no. |
| `combat` | **Partly** — NPC levels/stats/loot yes; damage types, hazards, factions, aggro and `combat.retreat` no. |
| `gathering` | **Partly** — nodes exist as items; their `yields`/`yield_table` are nested and read-only. |
| `progression` / `advancement` | **No** — the ledger's curve and grants are ruleset-only. |

Cross-cutting: `ruleset.json` holds ~19 sections the engine reads (calendar,
combat, crafting, crime, economy, elites, locksmithing, loot, npc_naming,
npc_schedules, player_defaults, quest_generation, skills, social, spawning, status,
weather, world, advancement) — **none of them editable**.

---

## 2. Content-set switching — safe now, two gaps left

Discovery: `DataRoot.available_content_sets()` lists any sibling directory with a
manifest; create exists ("New content set…"); **there is no delete path for a
set**. Switching reuses the managers and re-runs every load: `region_mgr.reset()`,
`view_states.clear()`, `cached_hierarchy.clear()`, `database_mgr.load_all()`,
`world_mgr.load_world_layout()`, `ui_mgr.set_catalog(…)`, then the new start
region. The choice is remembered in `user://editor_settings.json`; editor-only
state lives under `<set>/editor/` and is never read by the engine or the gate.

The dirty prompt offers three exits — "Save and switch", "Keep editing", "Switch
without saving" — which is the right shape.

**Fixed while measuring (see §6):** the "Save and switch" branch could silently
discard work; a failed region load left the previous set's undo armed; and state
keyed by one world's ids (armed stamp tool, clipboard, search index, library
selection, ignored validation warnings) travelled into the next set.

**Remaining, in order:**

1. **No way to delete or rename a content set** from the editor, and no way to edit
   an existing manifest (capabilities, `start`, paths) after creation. An author who
   scaffolds a set and then needs `quests` on it must hand-edit JSON.
2. **A set opened outside `content_sets/`** (via `--data-root`) never appears in the
   chooser, so it cannot be switched back to without relaunching.
3. Cosmetic: content-library tab colours are global (`user://content_library_tabs.cfg`).

---

## 3. Validation — what a green light means

`toolkit/editor_validate.py` is the one implementation; the check list is shared
with `run_content_checks.py` through `toolkit/content_check_steps.py`, so the
editor's Validate button and the build cannot disagree about *what a check is*.

**Runs in-editor (10):** `engine` (the engine's own reader), `references`,
`templates` (placeholder text), `abilities` (new — see §6), `stale` (stale
references), `json` (raw integrity), `numbers` (the int/float gate, report-only),
`contracts` (contract field audit), `skills` (skill audit, warnings only),
`neutrality`.

**Not run in-editor (8), each shown to the author with its reason:**
`content_set_schema` (the editor runs the engine reader directly instead),
`json_integrity` (scoped to fantasy's data root; the editor runs the raw-JSON
validator over the open set), `mod_manifests`, `playability` (boots and plays all
four sets — too slow for a button), `starter_packs`, `theme_packs`, and the two
fixture checks (they validate a committed fixture, not the open set).

Gaps worth closing, in order:

1. **`playability` is the honest one to worry about.** Everything else reads files;
   it boots the set and plays it. An author can be green in the editor and still
   have a set whose opening does not run.
2. **The gate's number check is report-only in the editor** by design (a Validate
   button must not rewrite files), which is right, but nothing offers a *fix* action
   either — an author sees "N numbers would change" and has to run the CLI.
3. **The editor can be stricter than the engine** (it filters manifest capabilities
   through a parity-checked list while the engine had no allowlist). That gap is now
   closed engine-side (§6); the general rule stands: when the editor knows a rule
   the engine does not enforce, one of the two is wrong.

---

## 4. Vocabulary copies (the drift risk)

Only three vocabularies *can* be parity-checked, because
`toolkit/engine_vocabulary_dump.py` emits only those: condition kinds, effect keys
(and effect shape hints), and objective types — plus the manifest block. Each has a
parity check in `schema_parity_smoke.gd`.

**Not parity-checked** (each a second copy of engine vocabulary, verified absent
from every test): item class names and the default `"Item"`/`"Gem"` strings, equip
slot list, ability target/effect type lists and per-effect field maps, the
filename→group map, background stat names, the pool labels, the four `COMMON_PROPS`
tables, the reference-editor target kinds, `ContractCatalog`'s fallbacks,
`EngineValidator`'s source list, and the **direction cluster** — which already
disagrees with the engine: `Constants.gd:46` makes `climb`'s opposite `dive`, while
`server/engine/utils/utils.py:306` makes it `descend`.

The remedy is not "check harder" but "emit more": every vocabulary the editor needs
should come out of `engine_vocabulary_dump.py` (which the editor already imports
for parity), so a copy becomes a checked copy.

---

## 5. Dead and dangerous controls found

Ordered by what they cost an author. **Five were fixed in this pass (§6)**; the
rest are the remaining work.

| Control | What it does today | Cost |
|---|---|---|
| "Create Ability" | Seeded `effects: []` and no description → `Spell` refused the entry and `spell_registry`'s file-wide `try` dropped **every remaining ability in that file** | content-breaking — **fixed** |
| "Cast Time" / "Range" | Wrote `cast_time`/`range`, which `Spell` does not accept → same file-wide failure | content-breaking — **fixed** |
| group picker on an ability | Wrote `magic_group` into content, which `Spell` refuses → same failure | content-breaking — **fixed** |
| nested item `properties` | Rendered with `str(val)` and wrote the string back — flattens `salvage_output`, `resistances`, `yield_table`, `substitute_resource_ids` (11 shipped items have one) | silent data loss — **open** |
| NPC "Health" | `health` on a template is read by **nothing**; the engine derives `max_health` from the constitution stat and reads `health` only from a room placement's `overrides` | an author sets 250 HP and gets the derived value — **open** |
| `rewards` on a quest | No widget, excluded from the "kept as authored" note; a malformed `rewards` raises *between* popping the quest from `active` and archiving it, and the desktop and headless paths disagree about the default quantity | an unreachable, unrepairable, quest-destroying field — **open** |
| effect `duration` | Written for every effect type except `apply_dot`; the engine reads `dot_duration` / `base_duration` | silently inert — **open** |
| unknown effect types | Shown as "Damage"; touching the picker rewrites the type | rewrites authored `cleanse`/`life_tap`/`unlock`/`stat_mod` — **open** |
| `objectives_any` as an object | Every reader filters `isinstance(route, dict)`, the validator passes it | dropped silently — **open** |
| "Stackable" | Forced off by class for 7 of the 12 classes the same panel offers | dead for most items — **open** |
| `gem_generation` sliders, room item `quantity` | Nothing in the engine reads either key | dead — **open** |
| `dialogue_choice` objective | Full authoring surface; the engine only consults it when a `choice_id` is supplied, which only negotiation does | offers a dead objective type — **open** |
| effects on a checked choice; effects on a root node | `runner.py` returns at the check before applying choice effects, and never applies the opening node's effects | silently inert — **open** |
| "+ Ingredient" | Appends `{"item_id": ""}`, which the gate then errors on | an editor-produced validation failure — **open** |

---

## 6. Fixed in this pass

Engine (all with tests, all falsified before being trusted):

- **`data/abilities/*.json` is now validated.** `toolkit/ability_load_check.py`
  builds every authored ability and reports the ones the engine would refuse, with
  file and id; it is in the shared check list, so both the build and the editor run
  it. Nothing checked these files before: the contract's ability *declarations* were
  validated, the entry files were not.
- **Manifest `capabilities` now has an allowlist.** `"craftting"` used to validate
  clean and enable nothing; it is now an error naming the engine's list.
- **`editor_validate.py` counts match the list it prints** — the summary said seven
  warnings over five rows, because counts were computed before dedupe (the `--only`
  path already recomputed them; the modal's path did not).
- **`docs/reference/AUTHORING_A_CONTENT_SET.md`** documents the contract, the
  capabilities and the gates from the code.

Editor:

- **"Save and switch" saves everything** it promises: the world layout in world
  view, the region when dirty, and the content library when dirty. It used to save
  only the region and return early when the region was clean, which dropped
  library edits after telling the author they were saved.
- **State keyed by one world does not travel**: tool mode and its data, the
  clipboard, the search index, the library selection and its inspector, and ignored
  validation warnings are all cleared on switch; undo history is cleared *before*
  the new set loads, so a failed load cannot leave it armed against the old data.
- **`set_root` requires a manifest**, so pointing the editor at a directory that is
  not a content set is refused (it used to reload into an empty world silently).
- **Ability creation writes a loadable entry** (description + one typed effect), the
  two unread spinboxes are gone, and an ability's group now lives in
  `editor/magic_groups.json` — migrated out of content on load, stripped on save.

Verified: `run_editor_checks.py` 30/30, `run_content_checks.py` clean, and the
Python suites green.

---

## 7. What remains, in the order it should be done

**Tier 1 — the editor cannot manage the engine's configuration (the user's goal).**

1. **A ruleset editor.** One form per section, generated from the sections the
   engine reads, each field typed and validated by the engine's own validators. The
   editor already reads two keys of it; this is the difference between editing a
   world and editing a *game*. Start with the sections that gate content an author
   authors: `social` (ladders), `skills` (names and stat bonuses), `factions`,
   `advancement` (curve and grants), `quest_generation`, `combat`, `weather`.
2. **A contract editor.** `item_families`, `stats`, `resources`,
   `generation_profiles`, `attack_profiles`, `defense_profiles`, `effect_packets`,
   `abilities`, `work`. The browser already parses all of it; what is missing is a
   writer and per-section validation (the registry refuses malformed contracts, so
   the editor can ask it rather than re-deriving rules).
3. **A damage-and-hazard editor** for `data/combat/elements.json`, and a
   **knowledge-topic editor** for `data/knowledge/topics.json`. Both are read by the
   engine today and validated by neither.

**Tier 2 — the editor writes content the engine rejects or ignores.**

4. Reuse `PropertyTagRow`'s nested-value rule in the item inspector (the room and
   region panels already have it) — the one remaining silent-data-loss path.
5. Give the NPC inspector the fields its capability needs: `faction`,
   `behavior_type`, `friendly`, the flat `dialog` dict, `properties` (vendor stock,
   `dialogue` graph binding, gift preferences, `work_location`, quest interests) —
   and remove or wire the inert `health`.
6. Give quests a `rewards` widget, and make `rewards` a validation error rather than
   a runtime exception between two map operations.
7. Close the four ability/dialogue inert-effect paths: effect `duration` vs
   `dot_duration`/`base_duration`, unknown effect types preserved rather than
   rewritten, effect fields available on the type actually selected, and a warning
   where the engine ignores a combination (effects on a checked choice; effects on a
   root node).
8. Delete the dead controls (`gem_generation`, room item `quantity`, `stackable`
   where the class forces it) or write the keys the engine reads.

**Tier 3 — campaigns, switching and validation scope.**

9. **Campaign authoring.** The editor loads `data/campaigns/` into a cache nothing
   can show, create or write, while the dialogue vocabulary lets an author reference
   a campaign by id. Either build the graph editor (the quest stage view is most of
   it) or stop loading them and say so.
10. **Set management:** delete/rename a set, edit an existing manifest's
    capabilities and `start`, and list sets opened from outside `content_sets/`.
11. **Run `playability` behind a "Validate (full)" action** so the honest end-to-end
    check is available in the editor without slowing the common case.
12. **Emit the remaining vocabularies from `engine_vocabulary_dump.py`** — item
    classes, equip slots, effect field maps, directions (starting with the
    `climb`→`dive` vs `climb`→`descend` disagreement) — so every editor copy becomes
    a checked copy.

**Tier 4 — the audit's smaller findings.** `objectives_any` as an object silently
dropped; `dialogue_choice` offered with no engine caller; "+ Ingredient" appending
an empty id; fractional values typed into integer SpinBoxes; the two dead
capability/ruleset constants (`_RULESET_SYSTEMS`, `world.regions` policy flags that
are enforced but invisible).

**Where each tier is written up as work.** This section is the order; the proposals,
with their depends-on, scope and done-when, are items 8–14 of
[`track-roadmaps/track-G-world-editor.md`](track-roadmaps/track-G-world-editor.md); the
sequence and the parallel marks are `chunks-of-work.md` §6.

| Here | There |
|---|---|
| Tier 1 §1–3 | G items 8, 9, 10 |
| Tier 2 §4–8, Tier 4 | G item 12 |
| Tier 3 §9 | G item 11 |
| Tier 3 §10–11 | G item 13 |
| Tier 3 §12 | G item 14 |

The dependency that crosses tracks: every section a form exposes needs a validator
from Track B, or it is shown read-only with the reason on screen — see Track B's
`Handoffs`.
