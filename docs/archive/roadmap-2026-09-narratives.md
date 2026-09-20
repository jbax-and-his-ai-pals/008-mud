# Phase narratives, P0–P9 and the hardening batches

Archived 2026-09-18 from `ROADMAP.md`. These are the completed phase bodies:
what each phase set out to do, what was found, and what was built. Kept because
the reasoning is the useful part and the audit findings reference points into it.

**Not a plan.** The live plan is [`../plan/integrated-roadmap.md`](../plan/integrated-roadmap.md);
the live open items were extracted into `ROADMAP.md`'s `## Still open` section
before this file was cut, so nothing unfinished is stranded here.

---

## P0: Repair the new-player path

**Goal:** a player following the game's own advice can play for an hour without
hitting a crash, a lie, or a dead end. This phase is small — measured in days,
not weeks — and everything else waits behind it.

- [x] **Fix the player-death crash.** `server/engine/npcs/combat.py:201` read
  `target.level` when an NPC landed a killing blow on a player, but `Player`
  has no `.level` (it lives at `runtime_state.progression.level`).
  `_progression_level()` guarded the *killer*, not the *victim*.
  Result: `AttributeError: 'Player' object has no attribute 'level'`, the world
  tick raised, and the command never returned to the player.
  **Fixed.** Both the killer and the victim now resolve through
  `_progression_level`, and `max_health` is read defensively.
  **A second defect was found on the same path:** the message carrying
  "You have been defeated!" was assembled and then discarded, because the
  delivery guard required `player.is_alive` and the player had just died — so
  the player died in total silence. The victim is now always told.
  Regression coverage: `tests/singles/test_npc_kills_player.py` (6 tests,
  deterministic via `always_hit`, verified to fail against the unfixed code).

- [x] **Stop the journal from withholding instructions.** `commands/quest.py`
  rendered missing optional objective fields as a literal `?`
  (`... to Elder Thorne in ?.`), and the authored stage description that
  actually explains the task was only shown by the generic fallback branch, so
  every typed objective (kill/fetch/deliver) hid it.
  **Fixed.** Unknown detail is omitted rather than placeholder-rendered, the
  authored stage instruction is always shown, and named kill targets read as
  "Defeat an elite troll" instead of "Defeat 0/1 targets".
  Regression coverage: `tests/singles/test_quest_journal_instructions.py`
  (6 tests, verified to fail against the unfixed code).

- [x] **Make loot visible.** Killing something printed "dropped a rat tail and a
  rat fur" while the inventory stayed unchanged — the items were correctly
  placed in the room, but nothing said where they went or that they could be
  picked up, so the reward moment read as a bug.
  **Fixed.** The drop message now names the pickup command, with the wording
  authored by the content set (`ruleset.loot.take_hint`, `{items}` expands to
  the dropped names); `false` suppresses it. The hint is shown only to a player
  credited with the kill, not to a bystander watching someone else's fight.
  Regression coverage: `tests/singles/test_loot_visibility.py`
  (7 tests, including a check that the suggested command actually works).

- [x] **Gate debug commands behind test mode.** A brand-new level-1 character
  could run `level 5`, `setgold 1000`, `sethealth 9999`, and
  `teleport forest forest_edge` from the real game server. Five debug commands
  declared an `operator.world.debug` entitlement, but that gate exists only when
  a setup-wizard-generated server config is in use
  (`server/config/server_config.json` is not in the tree) and
  `EntitlementGuard.check()` returns *allow* for an undefined gate; everything
  else in the `debug` category declared no gate at all.
  **Fixed.** Sessions now carry a `presentation_mode` (`player`/`test`) and the
  whole `debug` category is blocked for `player` sessions. The game entry points
  — `JsonLineMudServer`, `JsonWebSocketMudServer`, `launch_content_set.py`
  (`--presentation-mode`, default `player`) — default to `player`; a directly
  constructed `HeadlessServer` still defaults to `test` so the existing suite,
  the journey lab, and operator tooling are unchanged. Unrecognised modes fail
  closed to `player`.
  Regression coverage: `tests/singles/test_presentation_mode_gating.py`
  (8 tests, including that ordinary commands still work and that a denied
  command does not change state).

- [x] **Open the Portbridge quarter.** Five rooms were unreachable from the
  start room (`town_center_portbridge`, `port_authority_office`,
  `shipwright_road`, `shipwright_yard`, `lumber_storage`), orphaning
  `harbourmaster_voss` — the only quest giver for the entire **Portbridge
  Smugglers campaign** — plus a vendor and two stock lines.
  **Fixed** with a single east exit from `town_gate_south`, restoring the loop
  that the guard's own authored patrol route
  (`["harbor_district", "town_center_portbridge", "harbor_road"]`) already
  assumed. Verified by walking the route and starting the campaign: it now
  appears in the journal as an active campaign.
  (`town:jail_cell` and `night_shift:depot:holding_room` are *intentionally*
  unreachable — entered via custody — and now declare
  `properties.entered_by_system` so the validator knows that is deliberate.)

- [x] **Add a reachability gate to `run_content_checks.ps1` — and fix the reason
  it never worked.** The check existed as a *warning* and, more importantly, was
  **structurally incapable of detecting a closed zone**: it appended every
  room's exit targets to the traversal queue while still validating those rooms,
  so any room named as an exit target counted as reachable no matter how it was
  reached. That is precisely why five Portbridge rooms and an entire campaign
  shipped with no way in while the validator reported the content set clean.
  **Fixed.** Traversal now builds an adjacency map and walks outwards from the
  start room only; `properties.hidden_exits` count as edges so a lever-gated
  room is not a false positive; and an unreachable room is now an **error**
  unless it declares `properties.entered_by_system`. The gate caught a real
  second orphan in `night_shift` on its first run.
  Regression coverage: `tests/singles/test_content_set_direct.py`
  (error severity, edge-only traversal, and the `entered_by_system` exemption).

- [x] **Add a set-reference gate, and a content-neutrality gate.** Both are now
  in `run_content_checks.ps1` for all three content sets.
  `reference_integrity_validator.py` validates `items/sets.json` members against
  the item catalog and flags bonus thresholds above the member count — it
  immediately found `mage_set`'s two nonexistent members, which it had reported
  as "0 issues" before. `toolkit/content_neutrality_validator.py` parses engine
  source with `ast` and reports content ids appearing as string literals; it
  independently reproduced the P2 audit's leak list (7 real leaks + 5 debug-only).
  Both use explicit allowlists (`KNOWN_DANGLING_REFERENCES`,
  `KNOWN_NEUTRALITY_LEAKS`) rather than an error-count threshold, so a **new**
  instance of either mistake still fails the build while the known gaps stay
  documented and visible in the output.

- [x] **`run_content_checks.ps1` now actually runs.** It was broken three ways
  and stopped at the first step: `pack_tool.py` had a bare `%` in an argparse
  help string (rejected from Python 3.12 onward, so the `validate` subcommand
  could not start at all); the `server/data` steps pointed at a directory
  deleted in `ce625bd` when content moved to `content_sets/`; and the fixture
  block hard-failed because the committed `LATEST_REFRESH.json` points at a
  different checkout. All swept: 14 steps pass, with a missing optional
  dependency (PyYAML) reported as a setup problem rather than a content failure.
  **All three gates verified to fail on a deliberately reintroduced defect.**

- [x] **Surface `quest_missing_guard`.** Guard Captain Elara now offers the
  three-stage quest in a conditional dialogue graph. The old mill carries the
  tabard, the Captain preserves it as evidence, Kaelan consumes it for the
  diagnosis, and entering Murkwater's Stagnant Pool spawns the River Troll.
  `tests/singles/test_p6_quest_flow.py` walks the whole route through the final
  return, so this cannot regress into an offered-but-dead quest.

- [x] **Fix `craft`'s multi-word matching** — done in P3, with the shared
  resolver the item asked for. `craft wildflower posy`, `craft posy`, and
  `craft tie_wildflower_posy` all resolve, and no command silently takes the
  first of several matches. Original note follows, kept for the record.
  `commands/crafting.py:121-133`
  searched with only `args[0]`, so the natural phrasing the design calls for did
  not work: `craft river clay token` resolved to
  `press_river_token` only by accident, and `craft wildflower posy` did not
  resolve at all (`"wildflower posy"` is an underscore id and the recipe's
  display name is `"Tie Wildflower Posy"`). Substring matching was also
  order-dependent and only reported the first collision.
- [x] **The five dangling references are gone.** `smite` and `item_smoke_bomb`
  went with `classes.json` (P4); `item_iron_ore` and `iron_shortage` lived in
  the dead dialogue graph P5 replaced; `item_scrap` was the ruleset's loot
  fallback and is defined. Nothing references a missing id except the two
  allow-listed `mage_set` members.

### Verification notes

The suite cannot be run cleanly from a fresh checkout, and that is a P8 item:

- `engine/utils/text_formatter.py` imports `pygame` at module scope, so the
  whole suite and the content validators need pygame installed just to import.
- `PyYAML` and `msgpack` are declared in `server/requirements.txt` but their
  absence is an import *error*, not a skip: without them two test modules fail
  to import entirely and the msgpack transport snapshots fail.

**Resolved, and the original diagnosis was wrong.** Those failures were blamed
on dependencies that "cannot be installed here". They were installed — for
Python 3.12 — while the shell was running Python 3.14, which has none of them.
Measured both ways on the same checkout:

| Interpreter | `tests/singles` | Cause of failures |
|---|---|---|
| Python 3.14 (no deps) | 3,554 tests, 40 failures/errors | 3 modules fail to import; pygame stub stands in for the real client library |
| Python 3.12 (deps present) | **3,649 tests, 0 failures** | — |

The 95-test difference is the coverage that was silently missing: modules that
could not even import, plus transport snapshot tests that were skipping. So the
"41 failures" recorded through P0–P4 were never defects and never a reason to
distrust a green run elsewhere; they were an interpreter mismatch. `README.md`
now names the supported versions, `run_tests.ps1` resolves the interpreter and
checks the three packages before running, and `run_content_checks.ps1` uses the
same resolution instead of bare `python`.

### P0 status

All P0 repair work is complete. Its regression suites and validation gates have
been added and proven to catch deliberately reintroduced defects.

### Definition of done

- Following the manual's four starting paths for one hour produces no
  traceback, no `?`, no `(locked)`, and no unexplained dead end.
- A level-1 player cannot invoke any debug command.
- Every room in every content set is reachable from its declared start, or is
  explicitly declared as conditionally reachable.
- Content validation runs in CI and fails on unreachable rooms, dangling set
  references, and hardcoded content ids in the engine.

---

## P1: Test mode vs player mode

**Goal:** the server knows whether it is talking to a player or a tester, and
never shows one what belongs to the other. Full specification in
`WORLD_DESIGN.md` §2. **Complete.**

- [x] **Introduced `presentation_mode`** (`player`/`test`) — done as part of
  P0's debug gating. Session field, resolved from an explicit launch flag or
  session parameter; unrecognised values fail closed.
- [x] **Added `engine/presentation.py`** as the single place that answers "may
  this viewer see engine internals?". Resolution order is session -> world ->
  default, with `test` as the fallback so test worlds, the journey lab, and
  operator tooling keep today's exact output, while the game entry points
  default to `player`. Deliberately not under `engine/server/`, whose
  `__init__` imports the whole runtime and would create an import cycle with
  `engine/items/resource_node.py`.
- [x] **Moved board gating behind the mode.** A task behind a trust gate is now
  simply *not offered* to a player rather than shown as `Trust: 0/10 (locked)`.
  Because `accept quest <#>` resolves by board position, the handler keeps a
  per-session displayed-number -> board-index map (fingerprinted against the
  board contents) so a player's contiguous numbering stays correct and cannot
  be applied to a board that changed underneath it. Verified end to end: the
  hidden entries leave no gaps and `accept 1` takes the task shown as #1.
- [x] **Moved resource-node telemetry behind the mode.** `(5 remaining)` and
  "(recovers in about N days)" are gone for players; a picked-over patch says
  so in the world's voice and points at alternatives, which are kept because
  they are genuinely useful. `survey` likewise drops the `charges/max`, reset
  timers, and season windows for players.
- [x] **Moved NPC vitals and difficulty colouring behind the mode.** A player
  sees "a wolf", or "a wolf (wounded)" when it is hurt — not
  `(Level 6, 95/95 HP, 40/40 MP)` in a hue keyed to the level gap. Reading a
  number off a colour is the opposite of the world teaching you what is
  dangerous. Test mode keeps the full readout.
- [x] **Moved crafting internals behind the mode.** A player no longer sees
  `[Locked]`, the `has/req` ingredient counters, the craft counter, or the
  `material score` formula; they see the materials a recipe needs, the quality
  it would produce now, and what would raise it.
- [x] **Content can author both voices.** `presentation.variant()` selects a
  `player`/`test` sub-key from an authored `text` block, falling back to
  `default` then any string. Systems with authored strings can now vary their
  wording per mode rather than the engine hardcoding two versions.
- [x] **Test-mode output is unchanged.** This was the safety rail for the whole
  change and it held: `tests/batch` (280) and `tests/current` (3) pass fully,
  every affected singles suite passes, and the journey lab's `first-hour`
  policy still reports `passed: true` with no gameplay failures. The failing
  singles modules are the same six that failed before P1 started — missing
  `PyYAML`/`msgpack` and the local pygame stub — with **zero** new failures.
- [x] **Revised `docs/reference/PLAYER_MANUAL.md`.** It no longer claims combat
  "continues automatically as you exchange blows" (it does not: each `attack`
  is one exchange and your opponent keeps swinging), no longer documents
  `Trust: 0/10` gating, and no longer promises charge counts or reset timers
  from `survey`. Added what is actually true and useful: loot falls on the
  ground and must be picked up; death is recoverable; the board simply shows
  less until people trust you; creatures do not display their level.

### Definition of done

- [x] No player-mode output contains `(locked)`, `[Locked]`, `remaining)`,
  `depleted`, `Trust:`, or a bare `?` — asserted directly by
  `tests/singles/test_presentation_mode_displays.py` (16 tests) and confirmed
  by side-by-side live renders.
- [x] Test mode reproduces current output; all previously-passing tests still
  pass.
- [x] `docs/reference/PLAYER_MANUAL.md` revised.

Regression coverage: `tests/singles/test_presentation_mode_displays.py`
(16 tests) covers mode resolution, the player-mode-wins tie-break, content
variants, and end-to-end renders of the board, survey, recipes, and NPC
display in both modes. `tests/singles/test_presentation_mode_gating.py`
(8 tests) covers command access.

---

## P2: Content neutrality cleanup

**Goal:** no content identifiers hardcoded in engine code; every mechanic a
content set might want to rename is authored.

**The engine-side leaks are done.** `content_neutrality_validator.py` now reports
**0 issues against an empty allowlist**, for all three content sets. Every fix
followed the same shape: author the choice in the ruleset, then fall back to a
*structural* signal that already exists rather than to another content id.

- [x] `commands/debug/general.py` — `"knock"` / `"arcane_lock"` replaced by an
  authored `debug.lock_test_spells` list, falling back to any registered spell
  whose effects include an `unlock` or `lock` type.
- [x] `commands/debug_crafting.py` — `"item_anvil"` / `"item_alchemy_kit"`
  replaced by an authored `debug.spawnable_stations` map, falling back to any
  item carrying a `crafting_station_type` property (all four stations do).
  The refusal now names the types the content set actually has.
- [x] `items/chest_loot_generator.py` — `_CHEST_MATERIALS` and
  `"item_gold_coin"` replaced by authored `loot.chest_materials` and
  `loot.currency_item_id`, falling back to any `Container` template and to any
  item whose `treasure_type` is `coin` (an existing content convention, not a
  new one). Verified both paths: with config it uses the authored chests, and
  without it still generates chests. A content set with no coin item now
  produces no currency slot instead of a broken one.
- [x] `core/quest_generation/objectives.py` — `"quest_package_generic"`
  replaced by an authored `quest_generation.delivery_package_item_id`. Unlike
  the others this has **no fallback**, deliberately: there is no structural
  signal for "the item you carry on a delivery", so the generator declines
  rather than guessing. A content set that wants generated delivery quests
  declares its package.
- [x] `npcs/npc.py` — `"wandering_villager"` replaced by an authored
  `properties.ambient_wanderer` flag, set on that template. Behaviour is
  identical; respawn tests confirm it.
- [x] `npcs/ai/dispatcher.py` — `behavior_type` documented as a closed set the
  engine owns and the validator therefore treats as shared vocabulary, alongside
  factions and damage types. (The full behaviour-type list is still only
  discoverable by reading the dispatcher; see the open item below.)
- [x] **The neutrality gate itself**, with an explicit allowlist that is now
  empty, so any new leak fails the build.
- [x] `toolkit/reference_integrity_validator.py` — validates `items/sets.json`
  members and bonus thresholds (this is what found `mage_set`'s two nonexistent
  members), and no longer crashes on a minimal content set with no
  `quests/quests.json`.

### Still open

- [ ] **Consolidate the faction model behind an accessor.** `== "hostile"` is
  still compared inline in ~25 places across commands, UI, AI, world, and utils.
  The validator treats faction *values* as shared engine vocabulary, so this is
  not a leak — but a content set that extends or renames its factions still
  requires editing many call sites. Introduce something like
  `world.is_hostile(a, b)`.
- [ ] **Document the reserved `behavior_type` values.** They are an engine-owned
  closed set (`aggressive`, `stationary`, `wanderer`, `scheduled`, `patrol`,
  `healer`, `minion`, …), currently knowable only by reading
  `npcs/ai/dispatcher.py`. Put them in the content-authoring guidelines so an
  author knows `healer` is special and a typo means "no AI routine".
- [ ] **`game_object.py:147`** — `self.__class__.__name__ == "Player"` as a type
  check. Fragile; use `isinstance`. Not a content leak, hence not blocking.
- [x] **Move XP curve constants into the ruleset** (done in P4:
  `advancement.curve` in `rules/ruleset.json`, read by
  `engine/core/advancement.py`).
- [x] **Replace `data/player/classes.json`** (done in P4). The file and its
  pygame-only wiring in `engine/core/game_manager.py` are gone; backgrounds
  replace it, and the dangling `smite` / `item_smoke_bomb` refs went with it.
  `game_manager.py` now loads `player/backgrounds.json` for the legacy screen.

### Definition of done

- [x] The neutrality validator passes: no engine string literal matches a
  content id. (`0 issues`, empty allowlist, all three content sets.)
- [ ] `night_shift` exercises the newly neutralised systems. The renames-everything
  content set predates this pass and does not yet cover chest generation,
  delivery quests, or debug stations; worth extending so the next such change is
  caught by an existing test rather than by the validator alone.

### Verification

- Content checks: 14 steps pass, including the neutrality gate and the new
  set-reference check.
- Full suite: 41 failures, **identical to the pre-P2 baseline**, with zero new
  failures. `tests/batch` (280) and `tests/current` (3) pass fully.
- Two regressions were caught and fixed during the pass: three
  `test_quest_objectives_full` tests broke because their `_FakeWorld` double had
  no `ruleset_section` (now expresses the authored-package contract), and one
  `test_debug_crafting_commands` test asserted the old bare refusal string (the
  message is deliberately richer now).
- One near-miss worth recording: adding `properties.ambient_wanderer` to
  `wandering_villager` initially created a **duplicate `properties` key** in the
  JSON, which `json.load` silently collapses — the original block won and the
  flag vanished. Caught by explicitly checking for duplicate keys. The content
  integrity validator does not currently detect duplicate keys; see below.

- [ ] **Consider a duplicate-JSON-key check.** `json.load` silently keeps the
  last of any duplicated key, which turns an authoring mistake into a silent
  behaviour change. The near-miss above is exactly that failure mode. A cheap
  `object_pairs_hook` pass over content files would catch it.

---

## P3: Shared name resolution

**Goal:** players type what they see. **Complete for the resolver and all five
original call sites.**

`engine/naming.py` now holds one resolver used everywhere. Five ad-hoc matchers
are gone: `commands/crafting.py`, `commands/interaction/npcs.py`,
`items/inventory/core.py`, and `world/world.py::find_npc_in_room*` all delegate
to it.

- [x] **One resolver** (`engine/naming.py`) matching display name, id, and
      authored aliases; scoring so the most specific match wins; resolving the
      whole input rather than the first token; and reporting ambiguity as a
      question. Two deliberately distinct entry points: `resolve_one` returns
      None on a tie (ask the player), `resolve_best` picks one (for commands
      where refusing is worse). `resolve_exact` adds a strict equality tier for
      two-phase lookups.
- [x] **The crafting bug is fixed.** `craft` joined its arguments before
      searching, so `river clay token` no longer relies on dict ordering and
      `wildflower posy` no longer fails. Recipes are matched by their **output
      item's name** as well as the recipe name and id, because the item is what
      a player knows and the recipe's authored verb ("Tie …") is not.
- [x] **Authored aliases.** 15 recipes gained an `aliases` list naming what a
      player would actually ask for — `posy`, `flowers`, `bouquet`, `sword`,
      `healing potion`, `rations`. Verified: all of those now resolve, including
      aliases that appear in no name or id.
- [x] **Alias validation** in the content-set loader: wrong type, blank entry,
      duplicates, and too-short-to-match aliases are reported, with a negative
      test confirming the gate fails on a bad alias.
- [x] **`Recipe.aliases`** added; the resolver reads aliases from
      `properties.aliases`, `obj_id`, or a plain `.aliases` attribute, so items,
      NPCs, and recipes all work without special cases.

### Two design decisions worth recording

**Subsequence ("fuzzy") matching was built, then removed.** It was meant to
forgive typos, but it resolved the query `chest` to the NPC **"Kaelan the
Alchemist"** — the letters c-h-e-s-t do appear in order across that name. It
turned "look in chest" into a conversation with an alchemist, and broke a
batch loot test. Word-boundary matching already supplies the useful forgiveness
("elder" finds "Elder Thorne"), so fuzzy matching is gone and the module
docstring explains why it must not come back by default.

**Ties break on specificity, not on sort order.** Two guards in the town square
made `ask Guard job` reach "Guard Captain Elara" rather than the guard actually
called "Guard". `resolve_best(..., prefer_shortest_name=True)` now prefers the
candidate the query describes most completely, which is what a person means.

### Definition of done

- [x] `craft wildflower posy`, `craft posy`, and `craft tie_wildflower_posy` all
  work — verified live, along with `flowers` (an alias in no name), the recipe
  display name, mixed case, and messy whitespace.
- [x] No command resolves an ambiguous input by silently taking the first match.
  Ties are detectable (`resolve_all`), refusable (`resolve_one`), or explicitly
  resolved by a caller that has opted into a tie-break.

### Still open

- [ ] **`items/container.py`'s key-vs-container fuzzy match** (the one that
      strips "key" from a key's name to match a strongbox) still uses its own
      bespoke logic. It is a *property* comparison rather than a player-facing
      name lookup, so it was left alone rather than forced through the resolver.
      Worth revisiting if key matching produces a confusing failure.
- [ ] **Route `take`/`drop`/`use`/`equip`/`buy`/`sell` through the resolver
      explicitly.** They reach it today via `Inventory.find_item_by_name`,
      `World.find_item_in_room_for_player`, and `find_npc_in_room_for_player`,
      which is the intended path — but the commands that build a target phrase
      themselves should be audited for the same "only the first token" mistake
      that `craft` had.

### Verification

`tests/singles/test_naming_resolver.py` (26 tests) covers normalization,
scoring bands, whole-input matching, aliases, ambiguity, deterministic tie
ordering, custom accessors, and the deliberate absence of fuzzy matching.
`test_crafting_commands.py` gained natural-phrasing and ambiguity coverage.

Full suite after P3: 41 failures, **identical to the pre-P3 baseline**, zero
new. Batch (280) and current (3) pass fully. Content checks: 14 steps, all pass.

---

## P4: Progression spine

**Goal:** make progression authorable, make it work for any playstyle, and
replace classes with something that fits a hybrid game. Full rationale and
tables in `WORLD_DESIGN.md` §3. **Complete.**

**Decided:** progression is **hybrid** — XP flows from any recognised activity,
so no single profession carries the game and no content silo has to stand
alone. Exploration is one source among several.

- [x] **Changed the XP curve from ×1.5 to ×1.25, ruleset-driven.**
  `engine/core/advancement.py` owns `xp_to_reach_level` /
  `xp_for_next_level`, reads `advancement.curve` from the ruleset, and
  `player/progression.py` asks it instead of holding a constant. `base: 100`,
  `multiplier: 1.25` in `fantasy_frontier`; a content set that authors nothing
  gets those as the documented default. L15 costs **8,694** cumulative XP
  against **57,952** at ×1.5 — the difference between "a designed world can
  carry you there" and "only a grind can".
- [x] **Activity XP, from an authored ledger.** `AdvancementManager` replaces
  the kill-only model. It generalises `DiscoveryManager` rather than running
  beside it: discoveries are now one *kind* of ledger entry (imported once from
  the old `player.discoveries` so nobody loses their history), and the field
  journal is the same record. Entry keys are `"<kind>:<identifier>"`; kinds are
  region · landmark · creature · item · recipe · spell · npc · relationship ·
  quest · collection · discovery. `advancement.award(player, kind, id, ...)` is
  the one call gameplay code makes, and it is total — no ledger, no world, or a
  raising rule cannot break the movement or combat path that triggered it.
- [x] **Per-grant values are authored, and one rule table matches by fact.**
  Fifteen rules ship in the ruleset: region 90 · landmark 25 · creature 15 ·
  recipe 25 · spell 30 · named NPC 10 · relationship tier 40 · quest 40 ·
  collection set 150 · discovery 15, plus item rules split by type (material 8,
  gem 15, treasure 10, curios 3, consumable 5). Rules narrow on
  `region_id` / `npc_tags` / `item_type` / `item_tags` / `entry_ids`, and
  `once_per_kind` pays a rule only once ever. Values are deliberately
  provisional: they are content, so tuning them is a data edit, and playtesting
  will move them.
- [x] **Diminishing returns are structural.** A ledger entry pays once and never
  again, so the tenth rat is worth its combat XP and nothing more; the first
  region, recipe, gem, and quest are worth something on their own. No separate
  decay curve to tune or explain, and nothing to grind: repeat content pays the
  ordinary reward and the journal has already stopped being impressed. Existing
  combat and quest XP stay as they were — advancement XP is **additive** on top
  as a first-encounter bonus, which is why tests assert floors, not exact sums.
- [x] **The multiplier is one number in one file.** No engine constant, no code
  change to vary pacing mid-test; `advancement.json` is also read if a content
  set would rather keep a larger table in its own file, with the ruleset section
  winning for anything both define. A malformed curve or an unknown
  `match.kind` is reported as an issue and the rule is skipped rather than left
  in the table looking live.
- [x] **`classes.json` is gone; backgrounds replace it.**
  `data/player/backgrounds.json` authors six (wanderer, labourer, apprentice,
  acolyte, pedlar, poacher) with `_default: wanderer`. Each is stats, a kit, a
  couple of starting skills, and a recipe or two — a place to begin, never a
  gate. Chosen at creation with `char create <name> as <background>`, listed
  with `backgrounds`, reviewed with `background`. A background owns the *whole*
  starting kit, so the ruleset's generic starter inventory is the fallback for
  a content set with no backgrounds rather than something to be stacked on top
  of one (doing both gave every character two foraging knives from two systems).
  Two kit conventions came out of walking the opening as each background:
  **weapons ship carried, not equipped** (a new player's first `inventory`
  should show the weapon they own, and drawing it is the first thing the game
  teaches), and **every background carries a foraging knife**, because the
  opening commission cannot be started without one. The legacy pygame-only
  `classes.json` and its `smite` / `item_smoke_bomb` refs are deleted.
- [x] **Skills are wired to use.** `SkillSystem.practice_check` performs the
  check *and* trains the skill on the attempt, so the paths that were dead —
  `retreat`'s stealth check and skill-gated exits — raise the skill they test.
  Crafting, lockpicking, theft, and traps already called `attempt_check` +
  `grant_xp`; that is now the same helper. `_ensure_skill` means a skill at
  level 0 reports as known-but-untrained rather than missing, and the crafting
  and merchant paths that grant skill XP now show up in `skills`.
- [x] **Earned titles, self-applied and revocable.** `data/titles.json` authors
  thirteen with conditions over spells known, skills, relationship tiers, quests,
  the ledger, and level. `TitleManager.sync` grants *and* revokes, so a title
  reflects what is true now. Titles are mechanically inert — nothing reads them
  for a bonus — and the player chooses which to wear with `title <name>`.
  Player mode says "Not yet yours: …" instead of printing the numeric threshold;
  test mode still shows the condition, because that is the authoring surface.
- [x] **One condition evaluator, built once.** `engine/conditions.py` serves
  dialogue choice conditions (P5), title gates, and quest availability, with
  composites (`all` / `any` / `not`) and **unknown kinds failing closed** so a
  typo in content cannot open a gate. `explain()` is the test-mode counterpart
  that says why.
- [x] **`advancement` (the field journal) and `title` commands ship.**
  `advancement` lists earned entries by kind with `progress` and `fieldjournal`
  as aliases; `title` lists earned titles, `title <name>` wears one, and
  `titles`/`mytitle`/`wearth` alias it. `journal` was left alone — it belongs to
  the quest log.
- [x] **Level-ups stay automatic.** No per-level choice, no level cap. The
  exponential curve is the brake, and identity comes from background, skills,
  and title instead of from a build.

### Still open

- [ ] **Tune the grant values against real play.** They are authored and
  editable; they are not yet *tuned*. Expect region and quest values to move
  once there is a world big enough to walk, and revisit the level-26-ish
  completionist plateau then. The ×1.25 multiplier is also a starting value —
  vary it freely during testing, it is one number in the ruleset.
- [ ] **Decide whether a mirrored party quest should pay every member the
  first-completion bonus.** Today it does, because each member's ledger entry is
  their own. Defensible ("you were there"), but it means a party levels faster
  than a solo player on the same content; revisit once party play is exercised
  at scale.
- [ ] **`advancement.json` is supported but unused.** All configuration
  currently lives in the ruleset. Either split the fifteen rules out into a
  content file when the table grows, or drop the alternative path so there is
  only one place to look.
- [ ] **Backgrounds are chosen blind.** `char create <name> as <background>` and
  `backgrounds` both work, but a player is told *"Choose where you begin with
  ..."* without being shown the options at the moment of creation, and no
  background is earmarked per town (open decision 10 wants a chosen starting
  town later). Worth revisiting when character creation is given a proper
  screen rather than a command.
- [ ] **Rule out the same class of blockout for later content.** The opening
  commission needs a foraging knife, and three of the six shipped backgrounds
  did not carry one — a creation choice that locked a player out of the first
  thing the game asks them to do, which is exactly what the design says must
  never happen. `tests/singles/test_background_opening_kit.py` now walks every
  background through the opening move, so the mechanical half is covered. What
  is not covered is a *later* gate — a region reachable only with a tool, a
  quest completable only with a spell. Re-run that reasoning when P7 adds
  regions and tools.

### Definition of done

- [x] A pacifist, a merchant, and a monster-hunter can each advance steadily by
  different routes in a designed world. Fourteen of the fifteen grant rules pay
  for something other than killing; the only combat-shaped one (creature 15) is
  worth less than a single region (90) and pays once per species.
- [x] No skill check exists against a skill that cannot be raised.
  `practice_check` is now the only check-then-train path, and `_ensure_skill`
  reports untrained skills at level 0 instead of omitting them.
- [x] A player can earn and wear a title that reflects what they actually did.
  Thirteen authored titles, granted and revoked by condition, worn with
  `title <name>`.
- [x] Curve, grant values, and per-grant tuning are authored content, not engine
  constants, and the multiplier can be varied without a code change.
- [ ] The routes are *balanced*, not merely present. Adventuring still pays best
  in absolute terms because combat XP and quest XP stack with the ledger; making
  a pure gatherer-and-crafter comparable needs the P7 economy, so this stays
  open deliberately rather than being tuned twice.

### Verification

- `tests/singles/test_p4_progression.py` — 40 tests over the ledger, the curve,
  backgrounds, titles, the condition evaluator, and the two new commands.
- `tests/singles/test_background_opening_kit.py` — every authored background
  creates a character, carries a weapon, and gathers from the herb bed the
  opening commission sends them to. This is the test that would have caught the
  knife-less kits.
- Full suite re-run against the pre-P4 baseline: **41 failing tests before, 40
  after, zero new**. Those 40 turned out to be an interpreter mismatch rather
  than missing dependencies, and are now **0**: on Python 3.12 the suite runs
  3,649 + 280 + 3 tests with nothing failing. One pre-existing failure was
  *fixed* on the way through (below).
- `run_tests.py` (new) is the test entry point on every platform: it runs under
  the interpreter that invoked it, checks PyYAML/msgpack/pygame before running
  anything, and refuses to start without them, because a suite missing a
  dependency reports failures that are not defects. `run_content_checks.py`
  (new) does the same for the content gates, which until now had no Linux path
  at all — the fourteen steps only existed as a PowerShell script. The `.ps1`
  files of both names are thin Windows launchers that resolve 3.12 → 3.11 →
  3.13 → `python` and hand over.
- `.github/workflows/server-tests.yml` no longer installs a CPU-only torch. It
  was there because `requirements.txt` claimed a module-scope import chain
  forced it; nothing imports torch at module scope, and the suite passes on an
  interpreter without it.
- `tests/singles/snapshot_assertions.py` now rewrites the repo root wherever it
  appears in a payload, not only at the start of a string. Two audit snapshots
  had been failing because the stale-reference audit warns about the two
  allow-listed `mage_set` refs and embedded the absolute repo path in that
  warning; the snapshots were re-recorded with `<REPO_ROOT>` normalization, so
  they are no longer machine-specific. Pre-existing, not a P4 regression.
- `tests/singles/test_encoding_hygiene.py` — new tripwire. A pre-existing
  relationship test was failing because the engine read `villagers.json`
  without `encoding="utf-8"`, so Windows' cp1252 default turned a U+2019 into
  `â€™` in player-visible text. Eleven engine modules were fixed; the tripwire
  parses the engine with `ast` and fails on any future text-mode `open()`,
  `read_text()`, or `write_text()` that does not pin an encoding.
- `run_content_checks.ps1` — all 14 steps pass after the content changes,
  including neutrality (`0 issues`, empty allowlist) and reference integrity
  (2 allow-listed `mage_set` warnings, 0 errors).
- `tmp/verify_p4.py` drove a live server: background chosen at creation, region
  and landmark entries paying on first encounter and paying nothing on repeat,
  a crafted recipe paying once, the starting region seeded *without* paying,
  the field journal rendering, `skills` non-empty after crafting and trading,
  thirteen titles listing their conditions, and the curve table (L15 = 8,694
  cumulative, against 57,952 at ×1.5).

---

## P5: Dialogue system

**Goal:** conversations, and the delivery mechanism for quests, recipes, and
directions. Requirements in `WORLD_DESIGN.md` §5. **Complete.**

What it replaced: `data/dialogue/` was **never loaded** — the content loader
globbed `regions/ npcs/ items/ crafting/` and nothing else — so the only
branching conversation in the game (`blacksmith.json`, 3 nodes, 6 choices) was
dead code, and it referenced `item_iron_ore` and quest `iron_shortage`, neither
of which existed. What worked was a flat `dialog` keyword dict, and even that
only half worked: `npc.talk()` was only ever called with no argument, so
`greeting` was reachable and the other ten lines of a smith's dialogue were not.

- [x] **`data/dialogue/` is loaded and validated** with a documented graph
  schema. `parse_graph` builds nodes and choices from `dialogue/*.json`; an NPC
  template points at one with `properties.dialogue`. Structural problems — a
  root that is not a node, a `next_node` pointing at nothing, a choice that
  goes nowhere, a `check` missing a branch, an unknown effect — are reported
  rather than discovered mid-sentence, and are **errors in content validation**.
- [x] **Conditions on choices**, via `engine/conditions.py` — the evaluator P4
  built for titles. All sixteen kinds work unchanged: has item, knows recipe,
  spell known, relationship tier, quest state, discovery, region visited, in
  region, level, gold, title, background, flag, time of day, season. Unknown
  kinds fail closed.
- [x] **Effects on choices**, in one interpreter shared with the topic path
  (`engine/dialogue/effects.py`): start quest, start/advance/complete campaign
  and quest, grant recipe, grant discovery, teach spell, give/take item, give
  gold, adjust relationship, set flag, reveal exit, move NPC, and the structured
  `give_rewards` bundle. The topics path used to implement a private five-key
  subset, so `start_quest` behaved one way when a topic said it and another when
  a conversation did; it now delegates to the same interpreter.
- [x] **Mode-aware text.** `text` may be a string or a `{"player": …, "test": …}`
  mapping. Test mode annotates every choice with its destination, check, and
  effects, and lists gated replies as `- … (unavailable: needs 2 x iron ingot)`;
  player mode shows the conversation and nothing else.
- [x] **Nothing is discovered by the player.** Every failure mode above is a
  content-validation error, tested with a real content set and one deliberate
  break. A missing graph fails the build; it cannot reach a conversation.
- [x] **The quest-negotiation path is absorbed.** A `negotiate` objective is now
  *played*: the quest authors the stakes (`approach`, `choices`), and the
  dialogue system presents the approach as a reply, rolls the skill through
  `practice_check` (so the attempt trains the skill), and reports the authored
  outcome. Same machinery, same rendering, same command as any other
  conversation — not a dice roll hidden behind the word "complete".
- [x] **The flat keyword dict is kept** for minor NPCs, and now actually
  reachable: `ask grenda about missing supplies` reads her own `dialog` dict
  through the shared resolver, so `missing supplies` finds `missing_supplies`.
  Twenty-one templates keep their one-line answers; nobody has to author a graph
  to say hello.

### A content defect this uncovered

`quest_bandit_lieutenant` stage 0 is a negotiation whose success outcome said
nothing about what happened next, so the engine's default — "advance to the
next stage" — sent a **successful truce to "Kill the Lieutenant"**. The
`bandit_rebellion` campaign branches on `PEACEFUL_SUCCESS` at exactly that node,
so a two-ending campaign had one ending, and the peaceful half of it was
unreachable. Outcomes must now declare `next_stage` or `complete: true`, and the
validator refuses them otherwise. This is the same class of defect as P0's
unreachable campaign giver: content that looks complete and can never be played.

### Definition of done

- [x] An NPC can teach a recipe and explain where to use it, entirely from
  content. Grenda's graph teaches `forge_travelers_hatchet` when you bring her
  the iron, and explains the whole route: two ingots (she sells them, or salvage
  a blade), softwood from the fallen boughs in the woods, and her anvil — which
  the recipe requires.
- [x] Removing a dialogue file or referencing a missing one fails content
  validation, not the game.

### Still open

- [x] **Three authored graphs now ship.** Grenda teaches forge work, Elder
  Thorne teaches the first commission's recipe and directions, and Guard Captain
  Elara gives the Missing Guard route. P7 still needs a broader cast of distinct
  town voices, but P5 is no longer demonstrated by a single conversation.
- [ ] **Conditions cannot see the conversation.** There is no "you already asked
  me that" or "we discussed this last week" predicate, because the conversation
  history is not part of the condition language. `set_flag` covers the cases
  that matter today; revisit if authors start hand-rolling one flag per line.
- [ ] **`reveal_exit` is world state, not player state.** Opening a hidden exit
  from a conversation opens it for everyone on the server, exactly as a lever
  does. Correct for "the guard unlocks the gate", wrong for "he tells you where
  the smugglers' tunnel is" — that should be a discovery or a flag until exits
  can be per-player.
- [ ] **No dialogue for hostile NPCs** beyond negotiation. Talking is refused
  unless a quest stage is waiting on a negotiation, so a bandit cannot be
  taunted, bribed, or warned off.

### Verification

- `tests/singles/test_p5_dialogue.py` — 57 tests: graph parsing and its failure
  modes, loading and broken files, five validation gates (each proven by
  breaking a real content set), condition gating, every effect, choice matching
  including authored aliases and ambiguity, mode-aware rendering, the flat
  `dialog` dict, and the absorbed negotiation.
- Full suite: **3,706 + 280 + 3 tests, nothing failing**. Two real defects were
  found and fixed on the way, both of the "content that looks fine and is not"
  class:
  - the unreachable peaceful ending of `bandit_rebellion` (above);
  - the shared name resolver silently ignoring dict candidates, which made
    `reply <words>` match nothing at all — it read identity with `getattr`
    only, so a mapping scored zero and no error was raised anywhere.
- `run_content_checks.py` — all 14 steps pass, including the two new gates
  (dialogue references, quest outcome routing).
- `tmp/verify_p5.py` and `tmp/verify_p5_negotiation.py` drove live servers:
  a conversation opened by name, replies matched by number, by words, and by
  authored alias; a gated reply invisible to a player and explained to a tester;
  a recipe taught mid-conversation (with its ledger entry and XP); a flag set
  and read back by a later condition; the flat `dialog` dict answering `ask`;
  and a negotiation played, rolled, and completed into the campaign's peaceful
  resolution.

---

## P6: Quest flow and scaling

**Goal:** quests are given by people, teach the player what to do, and the
system scales to a world with many towns. **Complete** for the two items
below in the scope described; harder sub-asks are recorded as still open
rather than attempted half-built.

Full target flow in `WORLD_DESIGN.md` §6. The first commission now follows that
flow: it comes from the board, Elder Thorne teaches the recipe and points to the
garden, and the journal renders its authored stage instruction.

- [x] **Reorder the commission flow:** accept on the board → **talk to the
  giver** → they explain the need, **grant the recipe**, and say where the
  materials are → gather → craft → return. The recipe is no longer granted by a
  background; Elder Thorne grants it through dialogue effects.
- [x] **Render authored stage prose** in the journal instead of template
  fallbacks.
- [x] **Support repeatable quests** with diegetic rate limiting. Board entries
  now opt in through an authored `repeatable` policy (`delay_seconds` and
  in-world `unavailable_text`); an active notice never duplicates, completion
  records the player's next availability in their save, and the board checks
  the world clock when read. Riverside's commissions and elite bounties now
  use that policy. Players see, for example, that the board is picked over or
  a giver took down a notice — never a countdown or a cooldown value.
- [x] **Add objective types: five shipped, five reused existing
  infrastructure end to end.** Read the quest engine to separate what was
  cheap from what would need a subsystem of its own: `check_quest_completion`
  (`core/quests/tracker.py`) already runs every world tick for every active
  quest and already did one passive check (`clear_region`), so it was the
  natural home for two more -- **`relationship`** (checks
  `player.npc_relationships[target_npc_template_id]` against a threshold,
  no new tracking) and **`discover_n`** (counts P4's advancement-ledger
  entries of an authored kind, also no new tracking: the ledger already
  grows on its own). **`craft_quality`** hooks `CraftingManager.craft()`
  right after it already computes the result's quality tier. **`gather_types`**
  hooks `ResourceNode.gather()` the same way `discovery_manager` already does
  inline, recording which of a required set of resources has been gathered.
  **`deliver_multi`** extends `give`'s existing single-recipient delivery
  match to track partial progress across several recipients before
  completing. All five are additive: none changes how `kill`/`fetch`/
  `deliver`/`negotiate`/`scout` behave, so no existing quest or test needed
  to change. One is authored end to end, not just unit-tested: Talia the
  Merchant's `quest_local_provisions` (`dialogue/talia_provisions.json`)
  demonstrates `gather_types` -- no fixed source dictated, any mix of wild
  herbs and softwood from wherever the player finds them completes it, and
  `resolve_turn_in_name`'s existing template-or-instance matching meant her
  `wander_chance: 0` placement needed no new plumbing to turn in to.
  **Deliberately not attempted**, because each needs a genuinely new
  subsystem rather than a hook into one that exists: `escort` (its
  `is_escort_target`/`escort_quest_id` scaffolding in
  `_setup_stage_mechanics` was found to be dead code -- nothing anywhere
  reads either property, so real NPC-following movement AI, arrival
  detection, and death-of-escort failure would all be new), `defend/hold`
  (wave-spawn plus a survive timer), `timed` (a generic deadline/failure
  wrapper worth building once, not per-objective), `puzzle/mechanism`
  (bespoke per-puzzle logic, not a reusable type), `trade`
  (the vendor buy-order system `vendor_orders_completed` already tracks is a
  plausible future hook, just not exercised this pass), and `theft/smuggling`
  (belongs with the existing separate crime/theft system, not bolted onto
  quests).
- [x] **Extend instanced quests: level scaling and a boss room shipped;
  layout/entry-town/dungeon-type work stays open.** Read
  `generate_instance_quest`/`instantiate_quest_region`
  (`quest_generation/generator.py`, `world/instance_manager.py`) to find that
  target-creature choice was a uniform `random.choice` over the whole pool
  regardless of player level, and every spawn was an ordinary copy of the
  same template with no distinguished encounter. Fixed both without a
  generator rewrite: `_pick_level_scaled_creature` weights the pick toward
  templates whose authored level is close to the player's (still
  non-deterministic -- a *preference*, not a guarantee, so a sparse pool
  doesn't always hand back the same entry); the deepest generated room now
  gets one guaranteed elevated spawn via a new `compute_elite_overrides`
  (`npcs/elite.py`, factored out of the ambient spawner's chance-gated
  `roll_elite_overrides` so a boss room can reuse the exact same promotion
  math without an ambient roll) -- but only when there are at least two
  targets *and* two distinct non-entry rooms, so the smallest/oldest shape
  (`target_count: [1, 1]`, a single room) is completely unchanged and no
  existing test needed to move. **Still open:** branching (non-linear)
  layouts, wiring `possible_entry_regions` to more than the one starting
  town in practice, and instanced dungeons as a distinct shape from a
  generated house interior.
- [x] **Surface `bandit_rebellion` through normal play.** Asking Elder Thorne
  about trouble starts the campaign's opening route; `campaign start` is no
  longer required.

### Still open

- [ ] `escort`, `defend/hold`, `timed`, `puzzle/mechanism`, `theft/smuggling`
  objective types -- each needs its own subsystem (see above).
- [ ] `trade` (fulfil N vendor orders) -- infrastructure
  (`vendor_orders_completed`) already exists; wiring it as a quest objective
  type is a smaller lift than the others above, just not done this pass.
- [ ] Branching (non-linear) instanced-quest layouts, multiple real entry
  towns in practice, and instanced dungeons distinct from a house interior.

### Definition of done

- [x] A new player's first commission teaches them a recipe through a person.
- [x] Repeatable tasks exist and do not feel like a machine.
- [x] At least three non-combat objective types are live (fetch, deliver,
  scout, and negotiate) -- now eight, with relationship, discover_n,
  craft_quality, gather_types, and deliver_multi added.

### Verification

- `tests/singles/test_p6_quest_flow.py` covers the recipe-less opening through
  Elder Thorne's lesson, the full Missing Guard route through its quest-only
  River Troll spawn, and Talia's `quest_local_provisions` played live end to
  end (dialogue offer -> gather from two different rooms/regions -> auto-ready
  -> `talk ... complete`).
- `tests/singles/test_repeatable_board_quests.py` covers explicit opt-in,
  active-task de-duplication, hidden re-post timing, and save/load state;
  `test_content_set_runtime.py` rejects a malformed repeatable policy.
- `tests/singles/test_p6_new_objective_types.py` (16 tests) drives the real
  event each new objective type hooks into -- a tick-driven check, a craft, a
  gather, a give -- for all five, including negative cases (a different NPC's
  relationship, a different kind's ledger entries, a different recipe, an
  unrelated resource, double-delivery to the same recipient).
- `tests/singles/test_quest_generator.py`
  (`TestPickLevelScaledCreature`) and `tests/singles/test_instance_manager_full.py`
  (boss-room tests) cover the instanced-quest generation changes, including
  that a single-target instance is provably unaffected.
- `tests/singles/test_content_set_runtime.py` covers the new
  `_validate_new_quest_objective_types` gate: every bad reference/shape for
  all five types, and a well-formed quest of each producing zero issues.
- Full suite (`run_tests.py`, all three suites): **3,751 + 280 + 3 tests,
  zero failures** -- run twice for stability. This is the first time in this
  roadmap's history the full suite has been genuinely green rather than
  carrying "known pre-existing" failures forward; P4's encoding-hygiene fix
  is what actually retired the last of those.

---

## P7: World expansion

**Goal:** build the world described in `WORLD_DESIGN.md` §4 — concentric
difficulty rings anchored by 4–5 towns.

This is where the bulk of the work goes once P0–P6 have made it safe to add
content. Sizing from the hybrid advancement model (`WORLD_DESIGN.md` §3.2), at
×1.25 with a balanced source mix:

| Ring | Levels | Regions | Discoveries | Quests | Recipes |
|---|---|---|---|---|---|
| 1 (starter town) | 1–5 | 1–3 | ~10 | ~2 | ~2 |
| 2 | 6–10 | 4–6 | ~29 | ~6 | ~7 |
| 3 | 11–15 | 11–13 | ~88 | ~18 | ~21 |

No single column has to be complete for the ring to work — that is the point of
the hybrid. Author in whatever order the world wants; a region that arrives
late still pays.

- [x] **Pick and specify the towns** (decision 12, `WORLD_DESIGN.md` §8 --
  the roadmap's own "open decision 10" reference was stale; §8's list has no
  item 10 touching towns). Tiered with soft gating (decision 6). Five towns
  now live, signed off as final rather than left open by default: Riverside
  (L1–3, neutral starter, mixed local economy), Portbridge (L2–4, coastal
  trade/tariffs, with the smuggling pressure that commerce brings), Frostpeak
  (L5–8, mining/smithing outpost with a forge, supply yard, and Mining
  Lodge), Sunscorch Caravanserai (L9–12, desert water-and-caravan anchor with
  a water court, caravan yard, bazaar, and map house, reached through the
  Sunscorch Expanse from Frostpeak), and Aurelia (L11–15, prosperous-city
  anchor with a guild square, museum, and auction hall, beyond which lie the
  dangerous Aurelian Outlands). This is exactly the 4-5-town target and the
  five candidate identities `WORLD_DESIGN.md` §4.2 originally seeded.
  Player-chosen starting towns (decision 6's other half) stays deliberately
  deferred -- five towns existing doesn't reduce the actual cost (every
  candidate start still needs a complete, levelled first ring plus character-
  creation/tutorial rework), so it remains its own future roadmap item rather
  than something this decision unblocks by default.
- [x] **Attach level bands to regions as authored data.** Every static Fantasy
  Frontier region now declares `properties.level_band` (L1–3 around Riverside,
  L2–6 through the middle ring, L5–8 Frostpeaks/Trial). The ruleset opts into
  a validation gate requiring positive ordered bands and keeping explicit
  spawn ranges inside them; the spawner uses the band when a new region omits a
  duplicate range. No graph-distance or start-town identity is in the engine,
  so another starting town remains a content change.
- [x] **Build biome and region-type palette into content templates.** Every
  static Fantasy Frontier region now declares `properties.biome` and
  `properties.region_type`; the content-owned palette and opt-in validation
  live in `rules/ruleset.json`, so a missing or drifted label fails content
  checks. Palette list and authoring contract in `WORLD_DESIGN.md` §4.3.
- [x] **Underground layer:** Riverside Catacombs is now a L1–3 starter
  dungeon under the shrine and tavern cellar, with a burial network that loops
  through a natural root cavern. Aurelia's L14–15 Starwell Archive extends the
  museum into a guarded undercity vault and a capstone route. Portbridge's L6–8
  Tidewell Underworks adds flooded sewer and under-harbor spaces through the
  smugglers' crossroads, plus Voss's survey-then-clearance arc to make the
  route matter to the town. Mines and natural caverns already existed. The
  last gap -- a real subterranean lake/river, not just a connector pool --
  is now a three-room wing off the Shadow Caves' flooded mine bottom (L3–6):
  Sunken Lake Landing, a proper Sunken Lake chamber, and a Drowned Gallery
  reached by diving along the lake bed, with its own discovery (a cave pearl
  pried from older, pre-mine stonework). Landmark XP applies automatically
  to every new room via the existing P4 ledger, so no special wiring was
  needed beyond authoring the rooms. Every named item in the underground
  palette (`WORLD_DESIGN.md` §4.3) is now covered. Verified with a new
  test_p7_sunken_lake.py (room-graph reachability, landmark XP paid once,
  the discovery firing, item placement) plus the full suite (4,077 tests)
  and `run_content_checks.py`, both clean.
- [x] **Crude monster settlements:** Tideglass Warren is now a compact kobold
  settlement off the coastal sea caves, while Gallows Hollow makes the foothill
  bandits a watched, supplied camp with a guarded approach, archer perch, and
  stolen-goods cache. Reedscale Village gives the lizardfolk a defended
  root-platform settlement in Murkwater, with food stores, homes, and a ritual
  platform. Briarhook Scrapcamp completes the set with a watched forest
  approach, scrap gate, shared firepit, mushroom patch, and carefully sorted
  trophies. These turn their inhabitants into small communities with stores and
  territory, not ambient encounters.
- [x] **Build guild-like constructs** (decision 13, `WORLD_DESIGN.md` §8).
  Titles retain an optional content-authored conferring place as well as a
  group name: the Riverside Workward at the forge, Market Row, the Roads at
  the north gate, the Museum, Order of the Dawn shrine, Frostpeak Mining
  Lodge, and the two quieter social groups all have real locations. Aurelia
  adds the Surveyors' Hall (Aurelian Surveyor, tied to a survey commission)
  and now the Artificers' Exchange too -- a new `aurelian_artificer` title
  (crafting skill 10, relationship with Ves the Artificer, level 11) closes
  the one Aurelia location that had a vendor NPC but no guild tie-in.
  Sixteen titles across ten guild-like groups total. **Membership model
  signed off rather than left open**: no separate join/application action
  (a guild confers its title once conditions hold, revokes it the moment
  they stop -- membership already *was* the title), and holding titles from
  several guilds at once stays unrestricted by deliberate choice, matching
  decision 1's hybrid-advancement stance. Titles still confer no mechanical
  access -- identity only, as designed. Verified against real content (all
  16 titles load with zero issues) plus the full suite and
  `run_content_checks.py`, both clean.
- [x] **Densify `gathering`.** The seven ordinary renewable node templates now
  have **16 static sources across eight regions** (the garden plot and house
  pond remain player-housing tools, not world placements). Every ordinary node
  has at least two locations, and each vendor tool supports a route through at
  least two regions: forage around town/farms/forest, cut wood through farm,
  forest, and mountain spaces, prospect foothills and caves, or fish river and
  coast. The placement test protects that baseline while allowing future node
  templates and higher-tier resource materials to extend it.
- [x] **Expand the itemisation ladder.** Was 14 weapons spanning damage 3→8,
  11 armour pieces (the ladder's real count -- the roadmap's own "16" and "one
  each for head/hands/feet" had already drifted stale) with zero neck items,
  and 12 prefixes / 11 suffixes with "of Vampirism" gated at level 10.
  **A blocking bug surfaced first**: neither a player's equipped armour nor
  an NPC's authored `defense` stat actually reduced damage taken in combat --
  `GameObject.take_damage`'s `get_effective_stat("defense")` read a value
  nothing populated (a player's real defense lived in the separate
  `runtime_state.combat.defense`; an NPC's lived in a bare `npc.defense`
  attribute never copied into `npc.stats`). Every hit in the game had been
  landing at full raw damage minus only explicit buffs. Fixed in
  `engine/player/core.py`/`engine/npcs/npc_factory.py` before any of the new
  mechanic work could mean anything; verified with new equip-a-real-item and
  real-NPC-template regression tests plus the full suite run twice.
  **New mechanic**: weapon `weapon_damage_type` (slashing/piercing/crushing)
  vs. armour `armor_material` (cloth/leather/chain/plate), a real-world-
  grounded 3×4 multiplier table in `engine/config/config_combat.py` --
  slashing beats cloth but loses to plate, piercing beats chain (mail's
  historical weakness to a thrusting point) but loses to plate, crushing
  beats plate/chain (concussive force ignores what it can't cut) but is
  weakest against padding. Both fields are optional with a neutral 1× default
  (only the body slot drives the matchup), so every pre-existing item and any
  content set that never sets them is unaffected; threaded through
  `CombatSystem.execute_attack` and `GameObject.take_damage` as a new
  optional parameter alongside the existing elemental-resistance multiplier.
  All 14 existing weapons, 11 existing armour pieces, and all 31 hostile NPC
  templates were tagged in a pure-data pass.
  **Content**: ring 2 (levels 6–10) adds 6 weapons (rounding out the
  crushing gap: war mace, battle hammer, hunting spear, steel rapier,
  broadsword, waraxe) and introduces **chain** armour (coif/hauberk/
  gauntlets/sabatons) plus the ladder's first **neck** item (a warding torc)
  and a cloth option (an acolyte's mantle trading defense for spell power).
  Ring 3 (levels 11–15) adds 4 more weapons and introduces **plate**
  (helm/cuirass/gauntlets/sabatons, the cuirass carrying a real tradeoff via
  an agility-penalty `equip_effect`) plus a second neck item. Since authored
  hostile NPCs still cap at level 8, ring-3 gear is deliberately delivered
  through crafting recipes gated behind rare monster-drop materials
  (`item_chitin_plate` from giant scorpions armors the plate line,
  `item_troll_hide`/`item_living_rock` gate the ring-3 weapons) rather than
  invented high-level monsters -- 21 new recipes total across both rings,
  following the existing minimal recipe shape. Added 4 new affixes (Brutal/
  Adamant prefixes, of the Serpent/of Stoneskin suffixes) at level_min 6–7,
  reachable within the actual NPC level ceiling unlike the pre-existing
  "of Vampirism" -- which stays gated at 10 rather than fixed here, since
  fixing it properly needs a live level≥10 loot-generation path that doesn't
  exist in this content set yet (flagged separately). Verified with
  `run_content_checks.py` (clean, zero dangling references), the full suite
  run after every step, and 15 new tests covering the tier tagging, the two
  new materials, the neck-slot fix, the cuirass's tradeoff, the new affixes'
  reachability, and two real end-to-end crafts (including the rare-material
  gate).
- [x] **Give crafted items reasons to exist** beyond "more content." Field
  alchemy now supplies four distinct answers at the existing alchemy station:
  a three-minute Marshguard poison-resistance ward, a Trailblazer agility
  buff, a Purifying Draught that cleanses poison/disease effects, and a
  targeted Sunfire Flask (`use sunfire flask on <foe>`). The engine exposes
  these as content-authored temporary effects, cleansing tags, and target
  damage, so later content can add further preparations without bespoke item
  classes.
- [x] **Exercise the hazard system.** All six authored hazard types now have
  clearly telegraphed rooms in distinct regions: volcanic heat, glacial cold,
  poisoned mine air, a sparking shipwreck, an unholy ritual chamber, and the
  existing quicksand pit. The Fantasy Frontier ruleset requires coverage from
  its authored mapping, validates hazard timing/damage, and has a runtime test
  that proves each damage type is active.
- [x] **Extend weather.** Weather resolves through optional content-owned
  regional profiles: coast turns clear conditions windy, alpine rain to snow
  and storms to blizzards, desert clear to windy and storms to sandstorms,
  and swamp clear/cloudy conditions to mist; authored room climates still
  win. Exposed travel receives region-specific advisory text, while
  sea/river fishing, river-clay banks, forest berry brambles, and alpine
  fallen wood are genuinely unavailable in their dangerous conditions.
  Broader hazard interactions include content-authored storm-amplified
  electrical hazards on the coast and mist-amplified quicksand in the swamp.
  Closed the remaining gap -- every outdoor wilderness/dungeon region now
  has a deliberate weather treatment, not just the original four: forest
  (and the woods-set ruins) gets dappled canopy light and storm-felled
  branches, foothills gets its already-described constant wind, farmland
  turns rainy fields to mud, the Aurelian Outlands reuses the desert profile
  (its own text already calls it desert country loosening into farmland),
  and the two remaining unlabeled dungeons (Starwell Archive, Obsidian
  Trial) got the existing no-op "underground" profile for consistency
  rather than staying unclassified. Deliberately did **not** remap any
  region's "storm" condition unless a matching gathering-node
  `weather_blocked_by` was already authored against the mapped value
  (alpine's blizzard-blocked fallen wood is the existing example) --
  forest's own storm text stays a pass-through so the berry bramble's
  existing `weather_blocked_by: ["storm"]` keeps working exactly as before.
  Verified with the full suite and `run_content_checks.py`, both clean.
- [x] **Make exploration pay on its own.** The P4 ledger already awards 25 XP
  for each first-time landmark room and 90 XP for each first region, alongside
  its discovery/knowledge entries; the expanded gathering routes supply rare
  sites without turning ordinary rooms into object piles. A headless P7 journey
  now walks forty unique town rooms without combat, gathering, or talking and
  earns at least 1,000 landmark XP. Revisits remain silent, so this is genuine
  exploration rather than a route to farm.
- [x] **Resolve the density contradiction.** The obsolete “densify existing
  regions before creating new ones” instruction is no longer retained as open
  work. Sparse rooms are deliberate; the work above adds better prose,
  landmarks, hazards, and renewable rare sites rather than indiscriminate item
  clutter. `WORLD_DESIGN.md` §4.4 is the source of truth for that choice.

### Definition of done

- [x] A player can progress from level 1 to 15 by exploring a designed world
  without repeating content. A continuous headless walk through every public
  static room earns only first-time landmark/region awards and reaches level
  15 (9,060 exploration XP before quests, combat, loot, crafting, or social
  rewards are counted).
- No ring is reachable "early" in a way that trivialises it, or late in a way
  that makes it pointless.
- Every hazard type is used by at least one region.
- A new region can be authored from templates without engine changes.

---

## P8: Engine health

Deliberately after P0–P4, because these are refactors and the repair phase is
more urgent.

- [x] **Split `engine/server/headless_server.py`.** Was one 3,786-line,
  134-method class. This entry's own description was stale: TCP/WS/msgpack
  framing, capability negotiation, and the operator catalog actually live in
  `poc_server.py` (`JsonLineMudServer`) and `poc_ws_server.py`
  (`JsonWebSocketMudServer`), confirmed by grep -- not in this file at all.
  What's actually here: boot/init, session lifecycle, finite-adventure state,
  party management, shard runtime state, broadcast/shutdown/persistence/tick,
  world-effects/weather providers, command execution+gating, field/fx debug,
  and UI status-payload builders. Split into ten mixins under a new
  `engine/server/headless/` package (`boot_warnings.py`, `session.py`,
  `finite_adventure.py`, `party.py`, `shard.py`, `lifecycle.py`,
  `world_effects.py`, `command_execution.py`, `field_fx.py`,
  `status_payloads.py`), matching the existing `Player`/`engine/player/*`
  mixin convention: each is a bare class, no base class, no `__init__` of its
  own. `headless_server.py` shrinks to 265 lines -- the module imports,
  `_NullRenderer`/`_NullInputHandler`, `HeadlessServer.__init__`, the tiny
  shared `_event()` helper (called pervasively by both PoC servers), and the
  class declaration composing all ten mixins. A pure move: every method body
  is byte-identical to before, verified with an AST-driven extraction script
  (built the exact line range for every one of the 134 methods, asserted the
  grouping covered each exactly once with no duplicates/omissions before
  writing a single file) rather than manual cut-and-paste at this scale.
  **One real circularity surfaced and got fixed properly, not papered over**:
  `Session`/`Party` were dataclasses defined directly in `headless_server.py`;
  two mixins (`session.py`'s `create_session`, `party.py`'s
  `_ensure_party_for_leader`) construct them at runtime, not just as type
  hints, so a `TYPE_CHECKING`-only import (fine for every other cross-mixin
  reference, since `from __future__ import annotations` already makes every
  annotation lazy) wasn't enough -- it produced a `NameError` at runtime and
  would have been a real circular import for a non-lazy usage. Moved both
  dataclasses to a new dependency-free `engine/server/headless/models.py`
  that neither `headless_server.py` nor any mixin needs to import back
  through, which both resolved the circularity and is the more correct home
  for them regardless. One simplification from the `Player` mixin convention,
  by deliberate choice: `Player`'s mixins add `cast('Player', self)` at the
  top of methods needing the full instance for a type checker's benefit, but
  this repo runs no mypy/pyright step in CI (confirmed by grep) -- the cast
  calls would be 134 individual touch-points buying nothing except a nicer
  hover-hint in an editor no CI ever checks, so this split skips them. No
  subclassing of `HeadlessServer` exists anywhere, and no test monkeypatches
  a private method, but several call sites (`poc_server.py`, `poc_ws_server.py`,
  and multiple test files) do reach directly into "private" attributes
  (`server._event(...)`, `server._ensure_field(...)`,
  `server._shard_runtime_state`, `server.boot_warning_records`, etc.) --
  a same-class mixin composition preserves every one of these unchanged,
  since it's still one class and one `self`. Full suite run twice
  (`run_tests.py`): identical pass count before and after at every step.
- [x] **Split `client/scripts/ui/main_controller.gd`.** Was 3,218 lines, ~138
  functions, one script. There is no Godot test infrastructure in this repo
  at all, so verification leaned on Godot 4.7.2 itself (confirmed available
  locally) rather than a test suite: a fast per-file `load()`/`reload()`
  probe script (much quicker than a whole-project `--headless --check-only`,
  which took minutes and once had to be killed), plus an actual headless
  launch of `scenes/main.tscn` compared side by side against the pre-split
  file to confirm zero new runtime errors.
  Godot allows exactly one script per node, so the ~110 `@onready` bindings
  and the `_ready`/`_process`/`_input`/`_notification` entry points can't
  leave this file without restructuring `main.tscn` -- kept that file
  untouched (your call over reparenting nodes into new scene-tree children,
  the codebase's own dominant convention for Onboarding/CrashRecovery/etc.,
  which would have been a bigger, scene-file-touching diff with no test
  suite to catch a mistake). Instead, ~114 of the ~138 functions moved into
  nine `RefCounted` helper classes under a new `scripts/ui/main/` directory
  (network lifecycle, operator console, profiles, GM auth, authoring/locks,
  finite-adventure UI, theme, accessibility, game-state-payload rendering),
  each holding a `main: MainController` reference and instantiated in
  `_ready()`; the other ~24 (entry points, the central `_on_line_received`
  dispatch switch, and small generic utilities like `_bbcode_escape`/
  `_to_float` used across concerns) stayed on Main. The ~330 top-level
  member/function references inside every moved function body were
  reference-qualified mechanically (a Python script parsing top-level
  declarations, computing per-function local/parameter exclusions, and
  rewriting bare references to `main.X` / `main.<controller>.X` /
  `<same-controller-method>` as appropriate) rather than by hand at this
  scale -- verified by re-reading every generated file. Two real defects the
  mechanical pass caught or would have shipped silently:
  - `theme` was the chosen name for the theme controller's instance
    variable -- `Control` already has a built-in `theme: Theme` property,
    so declaring `var theme: ThemeController` would have silently shadowed
    it. Caught by writing a throwaway script that instantiates a `Control`
    and lists `get_property_list()`/`get_method_list()`, checking all nine
    candidate names against it before generating anything; renamed to
    `theme_controller`.
  - `_apply_text_scale` (now in `theme_controller.gd`) called `get_window()`
    bare -- a `Control` method inherited on the original `MainController`,
    invisible to a script scanning only this *file's own* top-level
    declarations. Found by grepping the original file for a short list of
    common `Node`/`Control` methods (`get_window`, `get_tree`,
    `get_viewport`, `add_child`, ...) restricted to lines inside moved
    functions; fixed to `main.get_window()`. The rest of that grep came back
    clean.
  A third issue was a `main: Control` typing choice, not a functional bug:
  every controller originally typed its back-reference as the generic
  `Control` base, which made GDScript's static analyzer unable to infer the
  type of `main.<main-only-property>` chains (`Cannot infer the type of
  "host"` etc.) since `Control` doesn't declare `main`'s actual properties.
  Fixed by adding `class_name MainController` to `main_controller.gd` and
  typing every controller's `main` as `MainController` instead.
  **Found and deliberately not fixed, since it's unrelated to this file
  split**: `_is_connected_to_game_server()`'s `tcp_client.is_connected_to_
  server()` call spams `Nonexistent function 'is_connected_to_server'` from
  `_ready()` onward on every headless launch -- reproduced identically
  against the pre-split file at the same commit, so it predates this work.
  Flagged as a separate suggested task rather than folded in here.
  `main_controller.gd`: 3,218 -> 969 lines. The nine new files range from 79
  (`gm_auth.gd`) to 470 (`game_state_payloads.gd`) lines.
- [x] **Break the pygame dependency for headless runs.** Reproduced the
  claim first (`sys.modules['pygame'] = None` before importing) and it was
  worse than described: not five command modules but nine (`inventory`,
  `locksmithing`, `magic`, `mercantile`, `quest`, `crafting`, `gathering`,
  the whole `interaction` package, and the whole `debug` package) failed to
  load, and `engine.server.headless_server` itself could not be imported at
  all -- `container.py` → `engine/utils/utils.py` →
  `text_formatter.py`, not through `item_factory.py`/`crafting_manager.py`
  as originally traced, but the same root cause. Three of `text_formatter`'s
  four pygame uses really were bare type annotations (`pygame.Rect`,
  `pygame.font.Font`, `pygame.Surface`); the fourth (`pygame.Rect(...)`
  inside `render()`) is a genuine runtime construction, not just a hint, so
  a bare `TYPE_CHECKING` guard on the import alone would have broken that
  method. Fixed with `from __future__ import annotations` (making every
  annotation lazy, so the three type-only uses need no `TYPE_CHECKING`
  import at all) plus one local `import pygame` inside `render()` -- the one
  method that touches a live surface, and which can only ever be called by
  client code that already has pygame, since it requires a real
  `pygame.Surface` argument. `engine/commands/__init__.py`'s loader logs an
  `ImportError` and moves on rather than failing loudly, which is why this
  shipped invisibly in the first place and why the fix needed a regression
  guard rather than trusting "it imports now, so it's fixed":
  `tests/singles/test_headless_import_without_pygame.py` has an AST check
  that fails immediately if `text_formatter.py` ever imports pygame outside
  `TYPE_CHECKING`/a function body again, plus a subprocess probe (a fresh
  interpreter, not in-process `sys.modules` patching, since this test
  suite's own process has already imported the real pygame) that imports
  the headless server and the full command registry with pygame genuinely
  unavailable and asserts nothing logged a load failure. Both tests
  verified to fail against the unfixed code.
- [x] **`torch`/`transformers` removed from `server/requirements.txt`.** The
  claim that `engine/ai/ai_manager.py` forces a ~1GB ML stack on every import
  was stale: the only torch imports in the engine sit inside
  `LLMInterface._load_model`, *after* an unconditional early `return`, and there
  is no module-scope torch import anywhere under `server/`. Verified by running
  the whole suite on an interpreter with neither installed. The requirements
  file now explains why they are absent and what to install to switch local-LLM
  dialogue back on.
- [x] **Pin the interpreter, and stop blaming the wheels.** The remaining
  installability problem is not missing packages, it is an ambiguous
  `python`. This project was developed on Linux, where CI and a single system
  interpreter meant `pip install -r requirements.txt` always lined up. On the
  Windows checkout, three runtime dependencies were all present — for Python
  3.12 — while the shell ran 3.14, which has none, so three test modules failed
  to import, a pygame stub stood in for the real library, and 40 "failures"
  appeared that were not defects. Two things follow. **Done:** `run_tests.py`
  and `run_content_checks.py` are the real implementations (stdlib only, same
  behaviour on every platform), the `.ps1` files are thin Windows launchers that
  pick a versioned interpreter, the test runner checks the three packages and
  refuses to run without them, `README.md` documents both platforms, and CI no
  longer installs a CPU-only torch it never imported. **Now complete:**
  `.python-version` pins 3.12; `bootstrap.ps1` creates and verifies the local
  `.venv`; both Windows launchers require it unless an interpreter is explicitly
  requested for diagnosis; `server/requirements.lock` pins the four test
  dependencies; and CI installs that same lock on Python 3.12. Facts worth
  keeping: plain `pygame` has **no cp314 wheel**
  (`pygame-ce` does, and provides the same `pygame` module), while PyYAML and
  msgpack both ship cp314 wheels, so on 3.14 the only genuinely awkward package
  is pygame.
- [ ] **Make the normal client a player experience.** Separate player-facing
  panels and contextual actions from server/profile/authoring/operator
  controls. (Unchanged from before; still true.)
- [ ] **Strengthen shared-world playtesting** — per-agent goals, contention,
  party/reconnect, housing/access, shared doors, transactions.
- [ ] **Run coached and uncoached human sessions** across maker, explorer,
  social, and adventurer playstyles.
- [ ] **Track player validation separately from implementation.** Every feature
  records: engine contract verified, authored content available, automated
  journey demonstrated, human playtest completed. A checked box is not evidence
  of satisfying play.
- [x] **Unify the editor path with content-set contracts.** The audit went
  deeper than the stale-file list suggested: `mud-world-editor/data` was a
  hand-copied snapshot from before the whole P4-P7 content push -- 12 of 25
  real regions, and every item/npc/magic/quest file added since. A real bug
  blocked a naive copy: every editor-authored room carries an `_editor_pos`
  layout field real content rooms never have, and while most read sites
  default safely, several on the main interaction path
  (`GraphController.update_specific_node`, `Main.gd`'s drag/select
  handlers) index it directly -- every synced room would have crashed the
  editor the moment its node needed to redraw. Fixed at the one choke point
  that matters: `RegionManager.load_region()` now backfills a deterministic
  grid position for any room missing one right after parse (mirroring the
  same fallback `QuestViewBuilder.gd` already used per quest stage), so
  none of the ~15 call sites that assume it exists needed auditing
  individually. `DatabaseManager.gd` gained the two genuinely-missing
  categories: a dedicated single-campaign-per-file loader for the
  branching-campaign directory `campaigns/` (its generic single-vs-library
  heuristic would have silently misread a campaign's own `nodes` dict as a
  second top-level entry -- caught by a verification script, not assumed),
  and simple single-file loads for root-level `collections.json`/
  `discoveries.json`. All 39 missing content files copied in (every
  `items/`/`magic/`/`npcs/`/`campaigns/` file, `collections.json`,
  `discoveries.json`, `quests/quests.json`, `quests/campaigns.json`, 14
  brand-new region files); the 11 regions that existed in both places were
  merged rather than overwritten -- real content as the base, but every
  room id already known to the editor keeps its existing hand-placed
  `_editor_pos` (up to 46/46 rooms carried for `town.json`), so nothing a
  human previously laid out was discarded. Removed a confirmed-dead
  `town.json.old` backup while in there; left the empty stray top-level
  `data/quests.json` and the scratch `new_region.json` alone since neither
  is content-set data. Added default world-map positions for the 14 new
  regions to `world_layout.json` as a finishing touch (not required --
  `WorldViewBuilder` already degrades gracefully for an unlisted region).
  Verified with a GDScript script run through the actual Godot 4.7.2
  binary (`RegionManager`/`DatabaseManager` loading all 26 region files and
  every data category with zero errors, every room confirmed to carry a
  valid `_editor_pos` after the backfill) -- the same headless-launch
  technique used to verify the `main_controller.gd` split. No native-GUI
  automation is available to click through the editor interactively, so a
  live spot-check of a newly-synced region is left for a human to confirm.
- [x] **Superseded the copy with one source.** The item above made the editor's
  mirror *complete* by copying canonical content into it. That was the wrong
  shape: a copy is a fork with a delay, and while the editor was a viewer nobody
  noticed, but the moment it became the authoring front-end the two trees
  started disagreeing in both directions. It was missing 164 item ids and 52 NPC
  ids, still had the legacy magic schema, and — the part that mattered — held
  *newer* authoring for gems and town districts that the game could not see.
  `GemGenerator` reads a gem's intrinsic `rarity`; the 28 tagged gems and 10 new
  ones lived only in the mirror, so every gem in play was generated off the
  value-derived fallback. `world.get_district` reads
  `properties.districts[*].members` for the room title and the atmosphere chain;
  canonical town still had the legacy block (one district, four rooms).
  Now: a `DataRoot` resolver picks the content set (CLI, then
  `user://editor_settings.json`, then the checkout layout, then a standalone
  copy), every editor path goes through it, the title bar names the world, and
  editor bookkeeping (`_editor_pos`, `_editor_exit_layout`, quest stage
  positions, world layout, magic groups, templates) lives in
  `content_sets/<set>/editor/`, split and merged at the two chokepoints in
  `EditorLayout` so no canonical file ever carries `_editor_*`. The mirror was
  `mud-world-editor/legacy-mirror/`, read by nothing; its two open editorial
  questions were settled and it was **deleted** (2026-09-20) — the fork was
  strictly older (38 rooms against 46, missing `community_garden`, one NPC
  reference naming a template that no longer exists), everything real in it had
  been migrated, and a test now asserts it stays gone. Detail:
  `docs/archive/editor-content-source.md`. Verified by a headless Godot script
  (`mud-world-editor/tests/content_source_check.gd`, 20 assertions: resolver
  lands on the content set, `town.json` loads with all 46 rooms positioned from
  the sidecar, the on-disk file stays clean, split/merge round-trips restore the
  author's layout), plus `tests/singles/test_editor_content_source.py` as the
  Python-side tripwire, plus the editor's existing layout smoke test and a
  `--quit-after 2` boot.
- [x] **Make the editor safe to work in (2026-09-20).** The reconciliation above
  left the editor reading the right files but with no safety layer around
  writing them. `docs/archive/world-editor-evaluation.md` is the audit; its
  Batch A is implemented:
  - one verifying writer (`SaveIO.write_json`) writes and reads back, so a
    failed save is a reported failure instead of a greyed-out Save button;
  - loading another region while the current one is dirty asks first, cancelling
    keeps the edits, and the undo history no longer outlives the region it was
    recorded against;
  - a region that fails to parse leaves the loaded one alone and refuses to be
    saved over, instead of becoming a blank region under the real filename;
  - closing the window offers **Save and quit** / **Quit without saving** /
    **Keep editing**;
  - content-library deletes are confirmed and undoable;
  - files the editor does not model keep their keys (`affixes.json` was losing
    two engine-read string keys on any item save, and `sets.json`/`affixes.json`
    are no longer loaded as items at all);
  - deleting the last entry of a file actually deletes it;
  - saves write 4-space indented JSON in authored key order — `JSON.stringify`
    sorts keys by default, so every save until now alphabetised every object in
    the file and destroyed its blame;
  - the dead "Validate Region Policy" button works (it built paths from the
    retired mirror), as does the cross-region exit repair on a room rename;
  - opening a content set no longer creates `magic/`, `quests/` or `campaigns/`
    directories in a set that has none.

  Two new headless suites (`tests/editor_save_safety_smoke.gd` and
  `tests/editor_session_safety_smoke.gd`, the second driving the real
  `Main.tscn`) pin the behaviours, and `run_editor_checks.py` runs all 14 editor
  checks in one command.
- [x] **Make the editor's surfaces honest (2026-09-20).** Batch B of the same
  audit:
  - **Quest authoring writes the engine's schema.** `QuestSchema.gd` holds the
    engine's 15 objective types with the fields the tracker and validator read;
    the inspector writes `stage.objective.type` (not a stage-level `type`),
    renumbers `stage_index` on any reorder, edits alternative routes and choice
    outcomes, and preserves every key it does not model — including the engine's
    own runtime bookkeeping. The old shape wrote stages the engine could never
    satisfy *and* passed validation with zero errors.
  - **The engine now refuses that shape**: `_validate_quest_stages` reports a
    stage with neither `objective` nor `objectives_any`, naming the fields that
    misled the author, because such a stage stalls the quest forever
    (`get_active_objectives` returns nothing). Shipped content has zero errors
    under it; the old editor shape is now a loud one.
  - **The editor runs the engine's validation**: `toolkit/editor_validate.py`
    runs the same five checks `run_content_checks.py` runs in one interpreter and
    prints one JSON document; a **Validate Content (engine)** button shows the
    merged result (overlapping findings reported once, with every validator that
    saw them). One subprocess call, so the editor and CI cannot drift.
  - **Ability definitions are editable in the sets that name them** —
    `abilities/` is preferred over `magic/`, as the engine does.
  - **`all.txt`** (a 268 KB stale source dump, tracked in git, that made greps
    match pre-reconciliation copies) is deleted, and the editor has a README.

  Editor checks are now 14, including a quest test that hands what the inspector
  wrote to the engine's validator and asserts it passes.
- [x] **Author the engine as it is now (2026-09-20).** Batch C of the same audit:
  - **Item contracts**: the item inspector has family and roll-table pickers
    driven by `ContractCatalog` (the same file the engine reads), says what the
    chosen family makes the engine build, and offers intrinsic rarity from *that
    profile's* bands instead of the fantasy set's four names. Its type dropdown
    now lists the engine's item classes — it used to offer "Tool" and "Material",
    which name no class, so a template authored that way could not be built.
  - **A Contracts browser** shows what the set declares (families, profiles,
    resources, attack/defense profiles, abilities, effect packets), read-only
    because the schema decides what may exist.
  - **Recipes are authorable**: a Recipes category in the Content Library edits
    `data/crafting/*.json` against `engine/crafting/recipe.py` — ingredients,
    quality tiers, familiarity milestones, station, an explicit-difficulty switch
    (absent means "derive it", so a spin box would have written 0 everywhere) and
    `requires_discovery`. The system connecting every item to every other item had
    no surface at all before this.
  - **Open Content Set…**: the editor switches between the sets beside the
    checkout, reloading every manager, re-pointing the contract browser and
    writing `user://editor_settings.json` so the next launch agrees. Unsaved work
    raises the same prompt as quitting, including "switch without saving".

  Editor checks are now **17**, three of them authoring tests that end by handing
  what an inspector wrote to the engine's validator (`quest`, `contract`,
  `recipe`), plus a switch test that drives the real `Main.tscn` between two
  scratch content sets.
- [x] **Finish the editor: dialogue, CI, and its own vocabulary (2026-09-20).**
  Batch D of the same audit:
  - **Dialogue graphs are authorable.** `data/dialogue/*.json` was the last
    content system with no surface and the most player-facing weight — a
    conversation can gate a reply on what the player has done, teach a recipe
    mid-sentence, or let a negotiation go two ways, and all nine shipped graphs
    were hand-written JSON. `DialogueSchema.gd` holds the engine's 17 condition
    kinds and 15 effect keys with their fields and payload shapes; the inspector
    offers node targets as **pickers over the graph's own nodes**, and renaming a
    node **repoints every reference to it** — the operation a hand-edited graph
    gets wrong. Dialogue needed its own loader too: one graph per file, because
    `nodes` is the graph's structure and the generic entry heuristic would read
    it as a second entry.
  - **The editor tests run in CI** (`.github/workflows/editor-checks.yml`): a
    pinned Godot, one project import for the class-name registry, then
    `run_editor_checks.py` and `run_content_checks.py`.
  - **The UI says "ability", not "spell"** — category, create button, group
    manager, inspector headers and the database filter. The *keys* stay `magic`,
    because they name caches, dirty flags and persisted editor state.
  - A real bug this found in the new code: GDScript's `or` returns a **bool**, so
    `str(x or fallback)` yields `"true"` — four places had that idiom, including
    the dialogue graph id, and every graph loaded as `"true"`. Caught on the
    test's first run because it asserted on ids rather than on "something
    loaded".

  Editor checks are now **18**. Still open for the editor: editing the contracts
  themselves (the browser is read-only by design), backgrounds/titles/
  collections/discoveries surfaces, and campaign authoring.
- [x] **Give the world editor bulk-generation tools for scaling a world.**
  Follow-on to the item above, aimed at end-user builders/modders rather
  than just closing a staleness gap. The editor already had a working
  17-algorithm room-topology generator, but it only ever produced bare
  rooms -- empty `properties`, no `spawner`, no NPCs/items, unseeded (so
  nothing was reproducible), and no way to wire a new region into the rest
  of the world except by hand, one exit at a time. Four additions:
  - **Seeded generation.** Every generator calls the bare global
    `randf()`/`randi()`, which Godot backs with one shared RNG --
    `RegionGenerator.generate()` now seeds it once before dispatch, making
    the whole call chain reproducible for a given (algo, params, seed)
    without touching any of the five generator files individually.
  - **A standalone region-policy validator**,
    `engine.server.content_set.validate_region_policy()` (plus a
    `toolkit/region_policy_validator.py` CLI), reusing the exact same
    per-region checks `load_content_set` already runs internally
    (classification, level bands, hazard coverage) without needing a full
    manifest-driven content set -- fast, targeted feedback while a region
    is still being authored or bulk-generated.
  - **Real content on generation**, not just a room graph: the New Region
    wizard now has a classification section (biome/region_type/level band,
    read from the ruleset's real vocabulary) and a population section
    (multi-select NPC templates + a density slider) that write
    `properties`/`spawner`/`initial_npcs` into the generated region, plus
    a one-click "Validate Region Policy" button wired to the new validator.
  - **One-step region-to-region connection**: an optional section in the
    same wizard picks a target region/room and direction and wires a real
    bidirectional exit at creation time -- the existing manual connection
    tool only handles true two-way linking for same-region exits, so this
    writes the reciprocal side itself (patching the target region's file
    directly, or its in-memory data plus an immediate save if that region
    happens to be the one currently open, since the view switches away to
    the new region right after and a merely-dirty edit would otherwise be
    silently lost).

  Also removed `data/regions/new_region.json`, confirmed generator debris
  from before this work, since it permanently failed the very
  classification check being added and would have been the first thing
  "Validate Region Policy" ever complained about; synced
  `rules/ruleset.json` and `data/combat/elements.json` into the editor's
  data so the classification vocabulary and hazard mapping are real, not
  invented. Verified throughout via the Godot 4.7.2 binary: deterministic-
  seed checks across all four generator families, a direct
  `_create_region` call producing correct classification/spawner/
  population (checked against the raw JSON on disk, not a round-trip
  through GDScript's own JSON parser, which silently turns every number
  into a float), the exact `OS.execute()` validator call path exercised
  standalone, and all three connection-wiring cases (forward exit,
  cross-file reciprocal patch, same-region persist-immediately) --
  including a real bug the verification script itself caught and a fix
  confirmed before it shipped. Full headless scene boot: zero script
  errors throughout. Deliberately out of scope: an addon/mod-content
  layering system (no `extends`/`depends_on` manifest concept exists
  anywhere in the engine today -- a real engine-architecture question, not
  an editor feature) and a full manifest-authoring/one-click-package export
  path, both flagged as necessary follow-on work for this audience to ever
  ship something, not attempted here.

---

## P9: Cross-theme contracts and a sci-fi proving slice

**Goal:** make Fantasy Frontier's combat, items, magic, armour, crafting, and
loot systems implementations of engine-owned contracts rather than genre-bound
primitives. Prove the boundary with a deliberately minimal sci-fi content set,
not a second large game.

The canonical design and delivery sequence live in
[`docs/design/cross_theme_engine_contracts.md`](docs/design/cross_theme_engine_contracts.md).
That document is the detailed contract reference; this section is the active
work order.

### First batch

- [x] **Map present genre coupling.** `toolkit/genre_coupling_audit.py` scans
  engine literals for genre vocabulary and separates a *branch* (a comparison)
  from a *name* (a field, a log line). 208 literals, **49 real branch sites** —
  41 of them magic, 5 `Gem`, 3 weapon/armour — concentrated in `items/` (41),
  `commands/` (25), `player/` (23), `server/headless/` (20) and `magic/` (18).
  The classification, six coupling families and their dispositions are written
  up in the design doc; the short version is that magic is an engine *subsystem*
  rather than a content capability, which is the largest single piece of P9.
- [x] **Define the contract registry.** `server/engine/contracts/` — a strict
  declarative schema language (unknown fields are errors, required fields, enums,
  bounds, nesting), and a `ContractRegistry` that validates and reference-checks
  item families, generation profiles, resources, attack/defense profiles,
  abilities and effect packets, **versioned and fail-closed**: a
  `schema_version` this engine does not implement is refused rather than
  best-effort read. Fantasy Frontier declares 5 families, 2 resources, the
  `faceted_stone` profile (the tables `GemGenerator` used to hardcode), 2 attack
  profiles, 3 effect packets and 2 abilities. It is wired, not aspirational:
  `ItemFactory` resolves a template's class family-first, `GemGenerator` rolls
  from the authored profile, `_validate_contract_content` turns registry
  refusals into content errors, and the editor reads the same file
  (`ContractCatalog.gd`) so its controls offer what content declares.
  `tests/singles/test_contract_registry.py` — 35 tests.
- [x] **Normalize one vertical combat slice.** Done, with the equivalence stated
  as a test rather than a claim. `engine/contracts/equipment.py` resolves
  contract-first, authored-property-second, engine-default-last, so items migrate
  one at a time; six read sites moved onto it (weapon damage, weapon damage type,
  armour defense, armour material, armour resistances, and a spell's cost /
  cooldown / targeting / level). `item_iron_sword` → `attack_profiles.melee_blade`,
  `item_leather_tunic` → `defense_profiles.light_armour`, `magic_missile` →
  `abilities.magic_missile`, values copied verbatim from the templates.
  `test_combat_contract_slice.py` (15 tests) asserts both directions: the numbers
  match what the templates still carry, *and* retuning a profile changes the
  fight. Two things it caught: a placeholder `resistances: {"physical": 0.1}`
  that would have quietly given every leather tunic resistance it never had, and
  that a family named `equipment` cannot serve both weapons and armour (a family
  names one engine class; capabilities are the shared vocabulary).
- [x] **Generalize generated item instances.** Done.
  `engine/items/instance_generator.py` rolls instances for any family whose
  contract says it rolls them, and `gem_generator.py` is a compatibility facade
  over it rather than the implementation. The vocabulary is neutral
  (`instance_*`, plus the cross-system `material_quality*` trio) and a set that
  reads its own keys declares `property_prefix` — the shipped stones declare
  `"gem"`, a sci-fi component family declares `"component"`. Naming is content
  too: `name_template` over `{base}`/`{quality}`/`{size}`/`{rarity}`, with the
  gaps from unused bands closed up. The last genre branch went with it: the
  engine no longer treats `"type": "Gem"` as "this rolls instances", and a
  content guardrail fails if a shipped Gem-class template stops declaring the
  family that does. An ungraded template in a set with its own rarity names used
  to produce zero total weight and crash the roll; it now resolves to the
  commonest declared band.
  This step also found a **save bug worth the whole exercise**: instances are
  saved as references, and value/weight/stackability were skipped as "core
  attributes", so a perfect ruby reloaded as an ordinary *stackable* one — and a
  crafted quality tier's value reverted the same way. Core attributes are now
  recorded when they differ from what the template produces.
  `test_instance_generator.py` (6, non-fantasy family end to end),
  `test_generated_instance_round_trip.py` (4, through a real save file).
- [x] **Build the sci-fi proof.** Done: `content_sets/orbital_salvage`, a dead
  salvage station in four rooms with one foreman, one hostile drone, a kinetic
  sidearm, an impact vest, a salvage bench that rolls components, a fabrication
  recipe, and one ability that spends **charge**. It declares `abilities` and
  not `magic`, keeps its ability definitions in `data/abilities/`, names its own
  damage channels (`kinetic`, `thermal`, `electric`), rolls components with the
  property prefix `component` and its own band names (`scrap`/`serviceable`,
  `micro`/`bulk`, `worn`/`true`), and shows no fantasy word on a status line.

  The ability half needed real engine work, and the seam was where it was
  predicted: the pool an ability spends was mana by name. It is now the
  **declared ability resource** (`engine/contracts/resources.py`) — `label`,
  `short`, `max_stat` and `regeneration_stat` all read, the curve staying
  engine-side — `abilities` became its own capability with `magic` implying it,
  the status payload carries `ability_resource: {id, label, short, current,
  max}`, the ability commands and definitions load for a set with no magic, and
  two content-word defaults went with it (a resource node no longer requires a
  `pickaxe` unless content says so; a status line no longer shows
  `SPELL_POWER` to a set that has none). Fantasy Frontier's numbers are
  unchanged and pinned.
  `test_sci_fi_proving_slice.py` walks the journey and scans every
  player-visible line for vocabulary the set never declares — which found three
  real leaks while it was being written.
  *Still open, and recorded in the design doc:* the `Spell`/`known_spells`/
  `mana_cost`/`runtime_state.magic` internal names, the fantasy aliases the
  ability command advertises in `help`, and NPC casting.

### Third batch: the crafting seam (2026-09-21)

- [x] **An ingredient is a reference, not an item id.** A recipe may name an
  exact template (unchanged, and it still wins when several are given), an item
  **family**, or a **capability** a family declares, each with an optional
  `min_material_quality` floor. `alternatives` may themselves be whole
  references, and each carries the `quality_penalty` that makes a substitution a
  trade-off rather than a free swap.
- [x] **One matcher for every call site.** `CraftingManager._ingredient_matches`
  is what counting, selecting, the craftable check, the crafting command's
  requirement list, the headless status payload, `givemats` and the editor all go
  through — a recipe that looks craftable and then fails to craft is worse than
  one that says what it is missing. `Inventory.select_items_matching` and
  `count_items_matching` are the inventory half of the same rule.
- [x] **The validator resolves the rule against real vocabulary.** A family is
  checked against the set's own contracts and a capability against what its
  families declare, so a typo fails the build instead of reading as a recipe that
  can never be made. An ingredient naming nothing is an error; naming two things
  at once is a warning that the second is ignored.
- [x] **The sci-fi proof uses it for real.** `orbital_salvage`'s fabrication
  recipe now asks for *two salvaged parts of grade 2 or better* rather than two
  named components, and its salvage bench yields exactly that grade — so the
  recipe reads the set's own family and the set's own grade, and knows no item
  name at all.
- [x] **The editor followed.** Each ingredient row has a kind picker and a grade
  floor, with suggestions drawn from the content set's contracts rather than a
  hard-coded list.
- [x] **A loader bug this found:** a top-level `_comment` in a recipe file
  crashed the crafting loader and silently removed *every* recipe in that file.
  Notes are skipped now, and a non-object recipe value is skipped by name.

*Still open here:* nothing — the seam was extended to the other two call sites in
the fourth batch below.

### Fourth batch: one rule, three call sites (2026-09-21)

- [x] **`engine/items/references.py` is the one implementation.** A recipe
  ingredient, a vendor's buy order and a salvage rule ask the same question
  about the same items, so they call the same `matches` / `describe` /
  `match_plan` rather than each having their own idea of what "counts".
- [x] **Vendor orders take a family or a capability.** Plus the older
  `min_material_quality_score` spelling alongside the shorter one, and a refusal
  that names *every* requirement rather than one of them.
- [x] **Salvage output is a reference, and rules key on the family.** The engine
  class key (`Weapon`, `Armor`) was a proxy for the family; `by_family` says it
  directly, and the class key is still read for a template that has no family.
  Fantasy Frontier's two class rules migrated.
- [x] **Nothing validated any of it before.** A typo'd salvage key fell silently
  to the scrap default and a rule naming a missing template failed only when a
  player tried it. Rules, `by_family` keys, template-level outputs and the weight
  rate are all checked now.
- [x] **Two content gaps closed.** `orbital_salvage` enabled `salvage` and
  declared no rule, so every attempt refused; it strips down to `item_scrap_alloy`
  by family now. And its foreman — already `is_vendor: true` in a set with no
  `economy` system — trades, with two buy orders by family and grade.
- [x] **The editor followed.** `ReferenceEditor` is one control used by the
  recipe ingredient row, the item's own salvage output, and whatever asks next;
  the item inspector gained a salvage section, which is how the eleven fantasy
  templates that override the family rule were authorable by hand and nothing
  else was.

### Fourth-batch evidence (2026-09-21)

- `test_salvage_references.py` (14) pins the rule lookup order, the family and
  class keys, and the yield arithmetic.
- `test_vendor_order_references.py` (17) walks Ivo's shipped orders in the
  sci-fi set and the shapes it does not use yet — capability, crafted-only, both
  quality spellings.
- `test_content_set_validator.py` gained 10 salvage cases;
  `test_sci_fi_proving_slice.py` is 19 and now breaks a part down and trades.
- Editor checks are **19** (`item_authoring_smoke.gd`), all green.

### Lessons from the first batch

- **A contract is only real once something reads it.** The registry was
  designed, loaded and validated before any behaviour changed, which is exactly
  when it is worth least. Wiring it into `GemGenerator` and `ItemFactory` is
  what turned three declarations into a seam — and it immediately found a defect
  the design had not: the roll weights assumed *exactly five* tiers, so a
  content profile declaring two crashed `random.choices`.
- **Contracts need a compatibility rule, not a flag day.** `item_family` wins
  when present and `type` still resolves when it is not, so a content set can
  migrate one family at a time and nothing shipped stops working. The same
  applies to the tests: they pinned `type == "Gem"` behaviour and kept passing
  while the resolution underneath changed.
- **The editor is the second consumer, and it is not optional.** Reading the
  same file is what stops a hand-written control list from drifting from the
  schema — and Godot's JSON parser handing back floats caught a real
  reading bug that only the editor could have exposed.

### Evidence required

- Fantasy Frontier and the sci-fi proof use one loader, one contract registry,
  and no genre branches in core engine paths.
- A resolved generated instance survives inventory and save/load exactly.
- The editor and command-line validator reject the same invalid contract.
- End-to-end smoke journeys run for both content sets.

### Second-batch evidence (2026-09-20)

- Both sets boot through the same loader, the same registry and the same command
  set; `run_content_checks.py` validates four content sets and runs the
  neutrality gate against **both** reference sets.
- A rolled instance round-trips through inventory and a real save file
  (`test_generated_instance_round_trip.py`) — the value/weight/stackable bug this
  found is fixed.
- The sci-fi journey never shows a word its content does not declare
  (`test_sci_fi_proving_slice.py`, 16 tests).
- Genre coupling re-measured: **213 engine literals** (167 CONTENT_LEAK, 18
  CAPABILITY, 28 KERNEL) by `toolkit/genre_coupling_audit.py`. Note that tool
  counts genre *string literals*, not branch sites — see the correction in the
  design doc. What remains is spell-school vocabulary and NPC casting; the
  crafting vocabulary left the list with the ingredient seam, because what it
  removed were identifiers rather than literals.

---

## Engine hardening

Independent of the contract work: the things that make a defect survivable
rather than fatal. Neither of these is a feature; both are the difference between
a playtester finishing a session and filing a bug about one.

### A handler that raises no longer ends the session (2026-09-18)

- [x] **`CommandProcessor.process_input` is the one dispatcher**, and it wrapped
  the handler call in nothing. An exception from a handler therefore reached the
  desktop loop — ending the run — or the headless command path, which on a shared
  server means the connection. Both call it; the boundary belongs there, once.
- [x] **The player is answered, and the bug is reported.** The message names the
  command and the exception *type* and deliberately not the exception's text,
  which can carry filesystem paths and internal identifiers. Full traceback goes
  to the log under one filterable source (`CommandCrash`).
- [x] **The operator can see it too.** `HeadlessServer.record_command_failure`
  counts failures per command and raises a `runtime.command.failed` warning, so
  "this command has crashed four times" appears in the same diagnostics an
  operator already reads. Counting matters more than logging here: one crash is
  noise, four is a content bug.
- [x] **A second boundary around the whole headless command.** The status,
  inventory and quest payloads built *after* a command, and the world tick that
  follows it, read the same content and can fail the same way. `execute_command`
  now delegates to `_execute_command` and converts a failure into an error event
  rather than losing the command's own output.
- [x] **A crash the boundary would have caught, found while testing it:**
  `game_manager.process_command` took the first word of the line to decide what a
  dead player may still do, with `text.strip().lower().split()[0]` — which raises
  `IndexError` on an empty line. Pressing Enter at the death screen ended the run.

### Content numbers keep the types the engine reads (2026-09-18)

JSON has one number type, so `2.0` and `2` are the same file and different
values — `isinstance(2.0, int)` is False.

- [x] **What happened:** the editor's GDScript `JSON.stringify` wrote every
  number as a float, and one save turned 2,058 values across `fantasy_frontier`
  into floats. The content validator then rejected ingredient quantities, region
  level bands, vendor order prices, quest stage indexes and material grades —
  fields nobody had edited — while every test that never read those fields kept
  passing. The editor is fixed (`a543cec`); the content it had already written
  was not.
- [x] **`toolkit/normalize_content_numbers.py`** converts whole-number floats to
  ints under a deliberately narrow rule: only where the field is one the engine
  means as an integer. `weight`, `chance`, `value_multiplier` and the rest keep
  their precision, because a JSON writer turning `3` into `3.0` did not make it a
  different kind of field. `--check` is what the gate runs; `--apply` rewrites
  only files that actually changed, and proves itself idempotent on a second
  pass. 1,278 values across 15 files.
- [x] **The rule is measured, not guessed.** Every name it converts is one that
  appears *only* as a whole number across all four shipped sets; a name seen both
  ways is left alone, and a test fails if that ever stops being true.
- [x] **The first version of the rule was wrong, and the suite said so.** It knew
  the fields the content-set validator checks — and not `min_crafts`, which
  `Recipe` reads with `isinstance(..., int)` when it decides whether to keep a
  quality tier. A float there silently dropped every tier a recipe authored, so
  crafting reported no quality at all while the validator was perfectly happy and
  six route tests failed. The lesson is the general one: *what the validator
  checks is not the same as what the engine reads*, and only the second list is
  the one that matters.
- [x] **It is a content gate now**, not a one-off cleanup:
  `run_content_checks.py` fails if any shipped set needs it.
- [x] **A duplicate error this uncovered:** `_validate_vendor_orders` checked the
  material-quality floor itself *and* through the shared reference helper, so one
  bad value was reported twice and read as two problems in the content.

### A save says what it is (2026-09-18)

`save_format_version` was written into every save and **never read**. Every load
was a per-key `.get(default)` walk, which is the right shape for tolerant reading
and the wrong shape for a format: a file from a newer build produced a
half-restored character rather than a refusal, and an old file had no way to say
what it needed.

- [x] **`engine/world/save_format.py` owns the format.** One constant for what
  this engine writes, a migration chain keyed by version pair, and a rule that a
  save from the future is **refused** rather than read for the keys we recognise.
  Refusing is recoverable; a character that loaded "successfully" is not.
- [x] **A version bump with no migration is still recorded**, because the next
  person needs to know *why* it was safe. A test asserts every step up to the
  current version has an entry.
- [x] **Unstamped saves read as version 1** — the state the earliest saves
  actually carried — and the missing 0→1 step is reported rather than invented.
- [x] **The stamp earned its keep immediately.** Version 4 exists because
  summoned NPCs cannot be reloaded: a summon keeps its duration and creation time
  in its own `properties`, and `NPC.to_dict` does not persist properties, so a
  saved summon always came back as an ordinary creature that would never expire.
  The player's summon ledger therefore could not honestly survive a save either,
  and version 3 files are told so by a migration rather than by a guess.

### Two persistence defects the stamp was hiding (2026-09-18)

- [x] **An aspect could be dereferenced while it was None.** `MagicState` and
  `ProgressionState` are nulled for a content set that does not present them, and
  `Player.from_dict` read their fields unconditionally. It worked only because
  the desktop load path happened to normalize *after* reading, so the crash was
  one call-order change away. The reader now applies the world's aspects first
  and then reads, and a save written by a build with abilities loads into a
  content set without them.
- [x] **The summon ledger is honest now.** It is written when there is something
  to say, held on load rather than applied (its entries are a claim about NPCs,
  and only the NPC restore can check them), and settled by `SaveManager` once
  those NPCs exist — dropping entries whose instance is gone instead of keeping a
  dangling id that a later `despawn` would search for and never find. In practice
  that means a summon does not survive a save, which is now stated in one place
  instead of being an accident of what `to_dict` forgot.
- [x] **`max_total_summons` was written and never enforced.** Nothing reads it to
  refuse a cast; `Player.from_dict` overwrote it with the default on every load.
  Recorded here rather than "fixed", because making it bind would remove a
  mechanic players currently have — it is the last item in this batch, below.

### The build plays the content (2026-09-18)

Everything `run_content_checks.py` did was *read files*. It could prove a content
set was well-formed and say nothing about whether the game made from it worked.
Two shipped defects lived in that gap, both validating perfectly:

* `orbital_salvage` enabled `salvage` and declared no rule for any item, so the
  whole advertised system answered "You cannot salvage the X".
* A `_comment` at the top of a recipe file aborted the crafting loader and
  silently removed **every** recipe in that file. Valid JSON, valid references,
  no recipes.

- [x] **`toolkit/content_playability_check.py` boots each set and plays it.**
  A character is created, the starting region is walked by its own exits, and
  every command the set's *capabilities* turn on is exercised with an argument
  drawn from its own content — its recipes, its nodes, its abilities, its NPCs.
- [x] **The plan is read from the command registry, not written down.** A
  hand-maintained list of command names goes stale the first time one is renamed,
  and the renamed one stops being checked with nothing saying so. The first
  version of this file asked for `collections` and got "Unknown command" — the
  command is `collection`.
- [x] **It fails on silence, not on refusal.** A command may answer anything,
  including "you cannot do that here", as long as the engine handled it. What it
  looks for is the message `CommandProcessor` returns when a handler *raised*,
  a command that answers with nothing at all, and a content file that declares
  something the loader did not produce.
- [x] **Proven against the failure it exists for**, on a copy of a real set: a
  recipe whose value is not an object is reported by name, and the same file with
  a `_comment` instead is correctly not reported.
- [x] **A loader inconsistency it found on the first run.** `_load_item_templates`
  counted `_`-prefixed keys as item templates missing required fields, so the
  `_comment` in an items file showed up in the boot warnings as a template
  somebody had got wrong. Every other loader in the engine skips notes; now this
  one does too.

### A recipe that cannot be read is refused, by name (2026-09-18)

An audit of how the engine reads numbers out of content found the shape of the
`min_crafts` bug in a great many places. The full sweep is deliberately not done
— it is 120-150 call sites across 15 modules and every one needs a judgement
about what a wrong value should mean. What **was** done is the worst-covered
surface, chosen because it had no second line of defence at all: `Recipe` was the
only reader of a recipe, and the content-set validator checked almost nothing
about one.

- [x] **`engine/utils/content_values.py`** is the one place that reads a number
  out of authored JSON. It refuses a value that is not what the field means and
  names the field the way the file spells it —
  `recipes.tie_posy.quality_tiers[1].min_crafts must be an integer (got '1')`.
  `world/housing_manager.py` had done this by hand in three places since before
  the module existed; this is that pattern, shared.
- [x] **A present-but-wrong value raises; only an absent one defaults.** The
  distinction is the whole point: `.get("min_crafts", 1)` covering a key that is
  there and wrong is how a typo becomes a silently dropped tier.
- [x] **A whole float is read as that integer; a fraction is refused.** `2.0` is
  what a JSON writer with one number type produces and means 2. `2.5` means the
  author wrote something the engine cannot honour, and truncating it would invent
  a threshold nobody chose.
- [x] **The three shipped-shaped mistakes this closes.** `min_crafts: 3.0` kept
  the tier list empty; `requires_discovery: "false"` made a recipe permanently
  unlearnable (`bool("false")` is True); `result_quantity: "2"` made a batch craft
  produce `"222"` by string multiplication. None raised, none was reported.
- [x] **One unusable recipe no longer takes its file with it.** The loader keeps
  the well-formed recipes and records the refused one in
  `CraftingManager.recipe_errors` — the same shape as the `_comment` bug, where a
  single bad key lost every recipe in the file.
- [x] **The validator now asks the reader instead of re-listing the fields.**
  `_validate_crafting_quality_contracts` constructs a `Recipe` and reports what it
  refuses, so the engine's rules and the validator's rules cannot drift the way
  they did. Verified: a string `min_crafts` that the validator used to accept now
  fails the build with the same message the engine would have logged at runtime.
- [x] **All 43 shipped recipes still parse**, and every content set still
  validates clean — the strictness was adopted without changing any content.

**Both arithmetic defects recorded here were fixed the same day** — see "A
reference nothing checked is a bug already shipped", below, for what the widened
reference check went on to find. The lesson that outlived them is the one worth
keeping: they were reachable *only* through arithmetic, and no gate read the
fields they were computed from.

---

## Engine hardening (continued)

### A reference nothing checked is a bug already shipped (2026-09-18)

An audit of what the engine resolves out of content, cross-referenced against
what any check opens the file for, found eighteen dangling references shipping
in content that passed all three gates. Thirteen were in `fantasy_frontier`:
seven items named a collection nobody had authored, three summon spells named
minion templates nobody had authored, two NPCs were scheduled to work in rooms
that did not exist, and one spell dealt `cold` in a set whose channel is `ice`.
Each one was invisible in play — a collection that never completes, a spell that
spends mana and produces nothing, a shopkeeper standing in the wrong place.

The gates were not wrong. They were **absent**: `reference_integrity_validator.py`
read four families and the engine resolves about fifty.

**What the validator checks now.** The four original families plus six more,
each as an explicit walker function over a named list of files:

- [x] **item, NPC template, ability, room** (as before), now also reading the
      files those references actually live in rather than only the ones that
      happened to be checked first.
- [x] **collection** (`properties.collection_id`), **recipe**
      (`properties.recipe_to_learn`) — both were being read as *item* references
      and reported as thirteen missing items the first time the widened check
      ran. Three of `properties`' keys name three different families, and the
      walker that took all of them for items was itself the bug.
- [x] **damage channel** (`damage_type`, `dot_damage_type`) against the set's own
      `combat/elements.json`, and the set's `default_damage_type` against the
      same list.
- [x] **weapon damage type** against `config_combat.WEAPON_DAMAGE_TYPES`. A
      *different vocabulary* on purpose — edge geometry against body armour, not
      a damage channel — and conflating the two reported 41 working weapons as
      broken. The two checks now say which axis they are on.
- [x] **The rewritten walkers are written out, not described by a path DSL.** The
      first attempt used a compact `$key`/`$value`/`*` expression language, and
      two of its sigils were silently wrong: the check reported success while
      finding nothing. That is the exact failure this file exists to prevent, so
      the replacement is verbose and obviously correct. A test now asserts the
      validator *fires* on each family, not only that it stays quiet.

**Two silent bugs in the checks themselves**, both found by writing a check and
then proving it could fail:

- [x] `_at(entry, "properties.collection_id")` looks up one literal key of that
      dotted name, finds nothing, and reports nothing. It was written that way in
      a walker whose entire purpose was to catch the dangling collection id in
      shipped content. `_at` now accepts dotted or separate keys.
- [x] The id tables counted `_`-prefixed authoring notes as real ids, so
      `_comment` in `collections.json` was a collection every typo could resolve
      to. An empty bucket and a bucket full of notes look the same to a check
      that only asks "is this id in the set?".

**Three content defects the widened check then found, all fixed:**

- [x] **`_comment` was loading as an NPC template.** `npcs/minions.json` gained
      an authoring note; `_load_npc_templates` had no `_` guard, so the note
      became a template whose value was a *string*. Nothing failed at load. The
      first reader to call `.get` on it — the kill-objective generator, walking
      every template's faction — raised `'str' object has no attribute 'get'`
      halfway through seeding a quest board. Three board-quest tests and one
      batch test went down with it. The item loader had grown the same guard
      earlier in this session; the NPC loader had not.
- [x] **`_comment` was loading as a collection.** `CollectionManager` kept the
      whole file, so the note was one more entry in the player-facing collection
      ledger. Fixed at the load, with the same rule every other definition file
      uses.
- [x] **`default_damage_type` was dead content.** Every set declares one
      (`magical` in fantasy, `kinetic` in the sci-fi proof) and the engine read
      none of them: `magic/effects.py` fell back to the literal string
      `"magical"`. A set whose channels are `kinetic`/`thermal` therefore dealt
      `magical` damage. The fallback now comes from the set, held in a mutable
      cell because the config is loaded at world construction — *after* every
      module has imported it — so a module-level string would have frozen at the
      built-in value, which is the same bug wearing a different hat.
- [x] `disease` (giant rat, zombie) and `magical` are now declared channels in
      `fantasy_frontier`, since the engine was already dealing both.

### A stat nobody has is a stat that silently does nothing (2026-09-18)

`BackgroundManager` copies a background's `stats` keys straight into
`player.stats` and its `skills` keys into `progression.skills`. Nothing
downstream reads `strengh`, so a typo in a starting background is silent in both
directions — it changes no number and it reports nothing — and the same is true
of a `weather_profile` a region selects but the ruleset does not declare, or a
`skills.stat_bonuses` entry naming a stat the set never defines.

- [x] **`player/backgrounds.json` stats are checked against a real vocabulary**:
      the engine's `PLAYER_DEFAULT_STATS` (read, not re-listed — a second list is
      a second thing to drift) unioned with whatever the set's own ruleset names,
      so a set with a different stat vocabulary is not wrong and a misspelling of
      its own vocabulary is. `resistances` is excluded on purpose: it is the
      container the per-channel resistances live in, not a stat.
- [x] **A skill no `stat_bonuses` rule backs is a warning**, not an error. Skill
      names are content-authored, so an unknown one is legal; one that is
      *recorded and never consulted* is worth saying out loud.
- [x] **A region's `weather_profile` must be one the ruleset declares.**
      `WeatherManager` falls back to the unmapped global weather, which is the
      right default and a completely invisible one: an alpine region authored to
      turn rain into snow just reports rain.
- [x] **`skills.stat_bonuses` itself is checked for shape only.** The ruleset is
      where a set declares which stats it has, so `stat: "grit"` there *defines*
      grit; calling the author's own vocabulary wrong would be the check
      inventing a finding. The mismatch that matters is across files.

None of this adds content: "Deliberately later" is unchanged. It makes the
content that already exists tell the truth.

### An ability nobody teaches is now a warning (2026-09-18)

Sixteen of `fantasy_frontier`'s twenty-three spells have no route to the player:
no scroll or tome teaches them, no background grants them, and the ruleset does
not start a character knowing them. They are cast *at* you by NPCs, which is a
real use of a template, so this is authored content rather than a defect — the
kind of thing that is fine to ship and must not be invisible.

- [x] **`content_playability_check.py` reports it as a warning**, so the build
      stays green while the gap is visible in CI output. Three routes count, and
      all three are content: `properties.spell_to_learn` on an item, a
      background's `spells`, and `player_defaults.magic.known_spells`.
- [x] **An NPC casting a spell is not a route for the player.** `usable_spells`
      and `random_spells.pool` say a template can cast it; reading them as
      "taught" would have silenced the warning on every spell in the set.
- [x] **Guarded on the set's own capability, not on the registry being empty.**
      `SPELL_REGISTRY` is process-wide and the check boots all four sets in one
      process, so the fantasy set's spells were still registered while the
      sci-fi sets were played. That read as "23 of 23 abilities have no route to
      the player" for two sets that declare no abilities at all — a check
      inventing a finding is worse than one that misses.

### Where player stats stand against "an instance of a general system" (2026-09-18)

**Landed.** Stats were the last system in the engine with no contract, and the
investigation split them cleanly, which is what made the work tractable:

- **Mechanical roles** needed a declaration. `constitution` was written into five
  files, `strength` into four, and a content set could not rename any of them:
  health would keep reading a stat nobody had, find the default, and produce a
  character whose physical stat did nothing. Nothing failed, because nothing was
  wrong — the engine was playing a different set's vocabulary.
- **Display** needed to read the declaration that already half-existed.
  `world.declared_status_stats()` read `ruleset.status.stats`, and
  `player/display.py` used it — but `ui/panels/status.py`, `ui/panel_content.py`
  and `ui/screens.py` each carried their own hardcoded list and their own
  abbreviation rule, so the text status line and the graphical one could disagree
  about what a character has.

- [x] **`engine/contracts/stats.py`** resolves a **role** to the stat that fills
      it: `health`, `attack`, `defence`, `evasion`, `regeneration`, `power`,
      `ability_power`, `resistance`. The naming is content, the curve is engine
      config — the same split `resources` already used for the ability pool.
- [x] **The `stats` section is the one contract that is an object rather than a
      list of `id` entries**, because it is a mapping from role to stat and not a
      family of things. It gets its own ingest, and a role the engine has no
      meaning for is an error rather than a silently-ignored key.
- [x] **A set that declares nothing behaves exactly as it did.** The fallbacks
      are the names the engine had hardcoded, so no shipped number moved — the
      whole suite passed with the refactor in place, which is the only evidence
      that matters for a change of this shape.
- [x] **`NPC_NEUTRAL_STAT_VALUE = 8` and `PLAYER_NEUTRAL_STAT_VALUE = 10` are now
      named.** The two values were a real difference between the kinds of entity
      and were written as literals at each read; they read as `10` in six places
      and `8` in four, which is the kind of thing that looks like a typo.
- [x] **`Player.recalculate_max_health()`** replaced three copies of the same
      formula (two in `player/core.py`, one in `BackgroundManager`).
- [x] **One display path for all four surfaces.** `display_stats()` returns the
      declared order and the declared short labels; the text status line, the
      graphical panel, the character sheet and the creation screen all read it.
      A set may now declare `short`, which is why `player/display.py` no longer
      special-cases `spell_power` and `magic_resist` for their abbreviation.
- [x] **Both shipped contract sets declare the section**, fantasy with its full
      vocabulary and labels, orbital with the six stats it shows. Declaring what
      the fallback would have supplied anyway is the difference between a set
      that has been checked and one that happens to work.
- [x] **`world.declared_status_stats()` reads the contract first** and still
      reads `ruleset.status.stats`, because a set written before the contract
      existed should not stop working. **Recorded, not done:** those two
      spellings of the same declaration should become one, in the older set's own
      time and not in the middle of a refactor.

### Gems: what is and is not already general (2026-09-18)

**Landed.** The generation pipeline was already general; the item class was not.

- [x] **The generation pipeline needed nothing.** `InstanceGenerator` rolls
      whatever a family's `generation_profiles` entry describes, `GemGenerator`
      is a compatibility facade over it with only tests and itself as callers,
      and `resource_node.py` / `chest_loot_generator.py` had already moved to
      `InstanceGenerator` directly.
- [x] **`Gem`, `Junk` and `Treasure` are gone**, and `ItemFactory` maps their
      type names to the base `Item` so a set that still writes the old word keeps
      working. A class is now reserved for a **mechanic** the template cannot
      express — a container holds items, a key unlocks, a weapon equips. None of
      those three had one: they held a `stackable` default, a gift tag and a
      sentence.
- [x] **`use_text` is a general item field.** `Item.use()` reads it and
      substitutes `{name}` **literally rather than through `str.format`**:
      authored prose is not a format string, and a stray brace would have raised
      and lost the sentence, which is the entire content of the field.
- [x] **`gift_tags` moved into the templates**, so a set can retag its stones
      instead of receiving `["gem"]` from a Python class.
- [x] **`toolkit/materialize_item_class_defaults.py`** is the migration, and it
      proves it is complete: it materialises what the classes did into 202
      template fields across five files, then re-runs and reports nothing left.
      Behaviour is identical by construction rather than by hope.
- [x] **A latent bug this uncovered:** the vendor's `sell` command compared
      `item.__class__.__name__` against `buys_item_types`, which meant the
      Python class name was the vendor's trade vocabulary. It reads the item's
      declared `type` now, which is the same string the template writes and the
      one the contract calls `item_class` — so a vendor buying `"Gem"` keeps
      buying gems, and a family whose `item_class` is `"SalvagePart"` can be sold
      without an engine class existing for it.

### What a skill is, and the first specimens (2026-09-18)

A skill is a named number with a level and xp that `SkillSystem` rolls against a
difficulty. That mechanism is already general and already content-neutral — nine
systems call it and it knows no content. What was missing is a **declaration**:
a skill is only a string, so nothing can be paired with it and nothing can check
it, and the same idea was spelled four ways.

- [x] **`toolkit/skill_audit.py`** reads what exists and reports what the names
      are used for, then flags what is currently silent. Wired into
      `run_content_checks.py` for all four sets, and **every finding is a
      warning**: a skill no check rolls is a design question, not a broken build,
      and the point of listing the instances is to be able to see them before
      deciding the pattern.
- [x] **Three uses are distinguished, because they are not the same thing.**
      `rolls` (the engine checks it *and* trains it — `practice_check`, or an
      explicit `grant_xp` beside the roll), `attempts` (a roll that grants
      nothing: a room exit's requirement, or a `{"skill", "minimum"}` threshold
      that only compares a level), and `named` (a title condition or a background
      grant, which reads and neither rolls nor trains).
- [x] **The instrumentation bug this found in itself, twice.** Site keys made
      only of the key name collided, so `locksmithing.skill` and
      `combat.retreat.skill` read as one site and two unrelated practices were
      reported as co-located. And a `difficulty`-less block was read as a roll
      when `world.py` defaults the difficulty — a condition is a comparison, and
      reading it as a check would have invented one the engine never makes.
- [x] **A skill the *engine* rolls is only a finding for a set that runs that
      system.** `crafting_manager` always writes `"crafting"`; for a set with
      crafting switched off that string is never reached, and reporting it would
      be the check inventing a finding. Orbital enables crafting and gets the
      finding; modern_capsule does not and gets nothing.

**The specimens, for the pattern conversation.** Every one of these is a warning,
none is a bug, and each is invisible until somebody looks:

| Set | Finding | Why it matters |
|---|---|---|
| fantasy | `crafting` is declared, but the only roll against it is engine-declared | the set cannot retune the check, and nothing it authored consults the skill |
| fantasy | `diplomacy` is rolled by a quest negotiation and declared nowhere | rolls at level 0 with no stat bonus; a typo of it would be invisible too |
| fantasy | `custody.concealed_tool_requirements` needs `stealth >= 20` **and** `lockpicking >= 20` | one action, two skills, `all()`-ed — the weaker link decides, so the stronger is partly pointless |
| fantasy | `advancement.grants` branch on item classes `Gem`, `Treasure`, `Junk` | the XP ledger speaks the Python class name, not a family or capability |
| night_shift | `custody` needs `awareness >= 20` and `security >= 20` | the same two-skill gate with different names; `security` is never rolled anywhere |
| orbital | crafting is enabled and rolls engine-declared `crafting` | the set renamed `evasion` and `security`, and could not rename this one |
| modern | nothing | crafting is off, so the hardcoded name is never reached |

**Nine patterns, all warnings.** 1: a skill named in content and declared nowhere.
2: a skill a background grants and nothing declares. 3: a declared skill no
content names. 4: a declared skill nothing rolls — *including* the case where the
only roll is engine-declared, which is the hardcoded-name finding wearing a
different hat. 5: a skill backed by a stat no vocabulary declares. 6: a skill
whose name is also a stat name. 7: one action requiring two skills, with both
thresholds printed. 8: a ruleset section that is authored, reached, and names no
skill to gate on. 9: the engine branching on an item class name.

**Recorded, not built:** the deeper version of pattern 7 — two skills that
*always* move together across many sites are one practice wearing two names —
needs more shipped instances to be worth a heuristic. What is built reports the
single action where the co-requirement is knowable, which is where the question
is answerable today. The pairings themselves (crafting types, weapon
disciplines, magic schools) wait on that read.

**Three distinctions the audit had to make, each after getting it wrong first:**

- **`rolls` / `attempts` / `named` are not the same use.** A dialogue check or
  quest negotiation rolls through `practice_check`, so the attempt trains. A room
  exit's `skill_name` rolls and grants nothing. A title's `condition` and a
  `{"skill", "minimum"}` threshold only compare a level.
- **A skill the engine rolls is only a finding for a set that runs that system.**
  `crafting_manager` always writes `"crafting"`; for a set with crafting off that
  string is never reached, and reporting it would be inventing a finding.
- **A background granting a skill is a *use*, not a declaration.** Having that
  backwards silenced the exact finding it should produce.

---

