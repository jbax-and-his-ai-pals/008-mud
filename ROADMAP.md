# Roadmap

Companion documents:
- [`docs/design/WORLD_DESIGN.md`](docs/design/WORLD_DESIGN.md) — target world shape, design pillars, open decisions.
- [`docs/PLAYER_MANUAL.md`](docs/PLAYER_MANUAL.md) — player-facing handbook (needs revision; see P1).
- Completed-work archive: [`docs/roadmap/archive-2026-09.md`](docs/roadmap/archive-2026-09.md).

Roadmap rewritten 2026-09-14 after a full engine + content audit. The previous
roadmap is preserved in the archive; every completed item it recorded is still
recorded there. What changed is the *order of work*: the audit found that the
engine is in far better shape than the world it holds, and that several defects
sit directly on the new-player path. Expansion now happens behind a short,
non-negotiable repair phase.

---

## Product direction

Build a game in which players can pursue combat, exploration, gathering,
crafting, trade, relationships, collecting, and place-making by preference.
These are complementary routes, not classes or mandatory checklists.

### Design commitments

- The engine stays content-neutral. Mechanics and contracts live in
  `server/engine`; names, values, lore, preferences, recipes, drops, and world
  layouts live in content sets.
- **The world is the progress curve.** XP comes primarily from seeing and
  doing, not from re-killing the same spawn — and from *any* recognised
  activity, so no single playstyle has to carry progression.
- **Gating is invisible.** The world grows richer as you do. Players are not
  shown menus of things they may not have yet.
- **Failure is diegetic.** Refusals speak in the world's voice, not the
  engine's. Timers, counters, and lock reasons are test-mode affordances.
- **Distance is difficulty.** How far you are from a safe town is a learnable
  proxy for danger.
- Every major activity should create value for at least two others.
- Basic progression must not require a single preferred playstyle.
- **Sparse rooms in a dense world.** Most rooms carry prose and exits.
  Interest comes from the region, its landmarks, and what a curious player
  finds by looking — not from filling every room with objects.
- New work ships as a small playable vertical slice with automated coverage.

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

- [ ] **Surface `quest_missing_guard` or shelve it deliberately.** It is the
  largest authored quest in the game (3 stages, 500 XP, the only quest using
  the alchemist and the river troll) and it is unreachable: it is referenced
  only from `data/quests/campaigns.json`, whose `quest_chain` key has **zero**
  readers in `server/engine`, and it is not in
  `ruleset.json`'s `authored_board_templates`.
  Cheapest correct fix: make it reachable. Second cheapest: move the file to a
  `data/unused/` folder so the tree stops implying it ships.
  *Not done in this pass — it is a content decision (wire it into a campaign or
  shelve it), not a repair.*

- [ ] **Fix `craft`'s multi-word matching.** `commands/crafting.py:121-133`
  searches with only `args[0]`, so the natural phrasing the design calls for
  does not work: `craft river clay token` resolves to
  `press_river_token` only by accident, and `craft wildflower posy` does not
  resolve at all (`"wildflower posy"` is an underscore id and the recipe's
  display name is `"Tie Wildflower Posy"`). Substring matching is also
  order-dependent and only reports the first collision.
  **Replace with a shared name-resolution service** (see P3) — this is not a
  one-line patch, it is a missing subsystem.
  *Deferred to P3, where it belongs.*

### Verification notes

The suite cannot be run cleanly from a fresh checkout, and that is a P8 item:

- `engine/utils/text_formatter.py` imports `pygame` at module scope, so the
  whole suite and the content validators need pygame installed just to import.
- `PyYAML` and `msgpack` are declared in `server/requirements.txt` but their
  absence is an import *error*, not a skip: without them two test modules fail
  to import entirely and the msgpack transport snapshots fail.
- In this environment (Python 3.14, no pygame wheel, no PyYAML, no msgpack)
  `tests/singles` reports 41 failures/errors, all of them from those missing
  dependencies or from the local pygame test stub. **None are in a module
  touched by this work.** `tests/batch` (280) and `tests/current` (3) pass
  fully.

### P0 status

All P0 repair work is complete except the two items explicitly deferred above
(`quest_missing_guard` is a content decision; `craft` matching is P3). Six
defects fixed, four regression suites added (27 tests), three validation gates
added and each proven to catch a reintroduced defect.

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
- [x] **Revised `docs/PLAYER_MANUAL.md`.** It no longer claims combat
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
- [x] `docs/PLAYER_MANUAL.md` revised.

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
- [ ] **Move XP curve constants into the ruleset** (see P4) so pacing is
  authored, not compiled.
- [ ] **Replace `data/player/classes.json`.** It authors four classes with
  distinct stats, gear, and spells and is **unreachable from the server path** —
  applied only by `engine/core/game_manager.py:255`, the legacy pygame screen.
  Every server-side character is `Adventurer` with all stats 10. It also holds
  two of the repo's dangling refs (`smite`, `item_smoke_bomb`). The replacement
  is decided (backgrounds + skills + titles, P4); this item is about removing
  the legacy file and its pygame-only wiring rather than leaving dead design in
  the tree.

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
tables in `WORLD_DESIGN.md` §3.

**Decided:** progression is **hybrid** — XP flows from any recognised activity,
so no single profession carries the game and no content silo has to stand
alone. Exploration is one source among several.

- [ ] **Change the XP curve from ×1.5 to ×1.25** (configurable, ruleset-driven).
  Still load-bearing even under the hybrid model: Ring 3 (L11–15) needs ~11
  regions at ×1.25 versus ~97 at ×1.5.
- [ ] **Add activity XP** from an authored ledger. Generalise the existing
  `DiscoveryManager` from "notable things found" into the advancement record.
  Grant, first time only, for: region first-entry · landmark room · creature
  template encountered · material/item/gem obtained · recipe learned · spell
  learned · named NPC met · relationship tier crossed · quest completed ·
  collection set completed. Values content-authored, not implied.
- [ ] **Set the per-grant values.** `WORLD_DESIGN.md` §3.2 uses placeholders
  (region 120, discovery 15, quest 60, craft 25, tier 40, set 150) and needs
  tuning against real play.
- [ ] **Decide diminishing returns** for repeat kills and repeat gathers, and
  implement it.
- [ ] **Keep the multiplier tunable.** ×1.25 is a starting value, not a
  decision. The ruleset value must be easy to vary during testing so pacing can
  be explored as systems land. Do not chase the long tail — a completionist
  plateaus around level 26 in a large world, and that is intended.
- [ ] **Replace `classes.json` with backgrounds.** A light creation-time choice:
  starting stats, gear, a couple of skills, maybe a recipe or discovery. It
  decides where you begin, not what you can become. Removes the dangling
  `smite` / `item_smoke_bomb` refs with it.
- [ ] **Wire skills to use.** `add_skill` is called only from tests, so `skills`
  always reports "no specialized skills yet" — while `retreat` performs a
  stealth check against a skill no player can ever raise. Wire gain via the
  existing `SkillSystem`, or remove the check.
- [ ] **Add earned titles.** Authored id, display name, and conditions; conferred
  by guild-like constructs that take profession-appropriate names per content
  set. Titles are self-applied, mechanically inert, and revocable if the
  conditions stop holding. Reuses machinery that already exists: spells known,
  faction reputation, relationship tiers, the discovery ledger.
- [ ] **Build one shared condition evaluator** serving dialogue choice
  conditions (P5), title gates, and quest availability. Build it once.
- [ ] **Add a `title` command** to list earned titles and set the active one.
- [ ] **Confirm level-ups stay automatic.** Decided: no per-level choice —
  identity comes from backgrounds, skills, and titles. Revisit only if
  playtesting says levelling feels empty.

### Definition of done

- A pacifist, a merchant, and a monster-hunter can each advance steadily by
  different routes in a designed world.
- No skill check exists against a skill that cannot be raised.
- A player can earn and wear a title that reflects what they actually did.
- Curve, grant values, and per-grant tuning are authored content, not engine
  constants, and the multiplier can be varied without a code change.

---

## P5: Dialogue system

**Goal:** conversations, and the delivery mechanism for quests, recipes, and
directions. Requirements in `WORLD_DESIGN.md` §5.

Current state: `data/dialogue/` is **never loaded**. The content loader globs
`regions/ npcs/ items/ crafting/` and nothing else, so the only branching
conversation in the game (`blacksmith.json`, 3 nodes, 6 choices) is dead code —
and it is also broken, referencing `item_iron_ore` and quest `iron_shortage`,
neither of which exists. What actually works is a flat `dialog`
keyword→line dict: 124 lines across 36 of 62 NPCs, and 26 NPCs with nothing
beyond a `default_dialog` one-liner.

- [ ] **Load and validate `data/dialogue/`** with a documented graph schema;
  NPC templates reference a graph id.
- [ ] **Conditions** on choices: has item, has discovery, relationship tier,
  quest state, class, level, time of day, region visited, reputation.
- [ ] **Effects** on choices: start/advance/complete quest, **grant recipe**,
  grant discovery, teach spell, give/take item, adjust relationship, reveal
  exit, move NPC, set flag.
- [ ] **Mode-aware text** so test mode can display conditions and effects.
- [ ] **Fail loudly at validation time** on a missing graph, dangling condition
  target, or unknown effect — never a player-visible crash or a `?`.
- [ ] **Absorb the existing quest-negotiation dialogue path**
  (`commands/interaction/npcs.py`) rather than sitting beside it.
- [ ] **Keep the flat keyword dict** for minor NPCs; it is a good lightweight
  option.

### Definition of done

- An NPC can teach a recipe and explain where to use it, entirely from content.
- Removing a dialogue file or referencing a missing one fails content
  validation, not the game.

---

## P6: Quest flow and scaling

**Goal:** quests are given by people, teach the player what to do, and the
system scales to a world with many towns.

Full target flow in `WORLD_DESIGN.md` §6. Today the flow is inverted: the
player already knows the recipe before anyone teaches it, and the journal shows
`?` instead of the authored instruction.

- [ ] **Reorder the commission flow:** accept on the board → **talk to the
  giver** → they explain the need, **grant the recipe**, and say where the
  materials are → gather → craft → return. This depends on P5 (dialogue
  effects).
- [ ] **Render authored stage prose** in the journal instead of template
  fallbacks.
- [ ] **Support repeatable quests** with diegetic rate limiting (the giver is
  busy, the board is picked over) rather than a visible cooldown.
- [ ] **Add objective types:** escort, defend/hold, timed, puzzle/mechanism,
  explore-region, discover-N, craft-to-quality, deliver-to-multiple,
  gather-N-types, social (raise relationship), trade (fulfil N orders),
  theft/smuggling. Today: 8 deliver, 6 kill, 2 negotiate, 2 scout, 1 fetch.
- [ ] **Extend instanced quests.** The system already works
  (`instance_generic_infestation`: worried homeowner → clear rats → relieved
  homeowner, with a dynamically generated 2–4 room interior) and matches the
  "rats invade a house in town, house is generated and destroyed on completion"
  design exactly. Extend to variable layout templates, boss rooms, level
  scaling, multiple entry towns, and instanced dungeons as well as interiors.
- [ ] **Surface `bandit_rebellion` through normal play.** A complete campaign
  (4 nodes, two endings: peace and war) with a properly hinted quest exists and
  is currently reachable only via `campaign start` — a **debug**-category
  command. This is the cheapest narrative win available.

### Definition of done

- A new player's first commission teaches them a recipe through a person.
- Repeatable tasks exist and do not feel like a machine.
- At least three non-combat objective types are live.

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

- [ ] **Pick and specify the towns** (open decision 10). Tiered with soft
  gating (decided). Candidate identities: the starter village (neutral, mixed
  economy), the existing seaside town (trade/tariffs/smuggling), a mountain
  town (mining/smithing), a desert town (caravan trade/water scarcity), and a
  large prosperous city (crafting guilds, museum, auction).
- [ ] **Attach level bands to regions as authored data**, not derived from
  distance-to-starter-town, so a future player-chosen starting town stays a
  content change rather than an engine change.
- [ ] **Build biome and region-type palette into content templates** so new
  regions are cheap to author. Palette list in `WORLD_DESIGN.md` §4.3.
- [ ] **Underground layer:** sewers, catacombs, mines, natural caverns,
  undercities, subterranean water.
- [ ] **Crude monster settlements:** kobold warrens, goblin camps, lizardfolk
  villages, bandit camps.
- [ ] **Build guild-like constructs** — the places and factions that confer
  titles (P4). Content-authored names per profession.
- [ ] **Densify `gathering`.** There are **9 resource nodes and each is placed
  exactly once in the entire world** — one herb bed, one clay bank, one rose
  quartz seam. Separately, **every `required_tool` is null**, so the four
  gathering tools vendors sell do nothing. Either add many more nodes and give
  tools a purpose, or remove tool requirements honestly.
- [ ] **Expand the itemisation ladder.** Today: 14 weapons spanning damage 3→8;
  16 armour pieces across 7 slots, with **zero** neck items and exactly one
  each for head/hands/feet. 12 prefixes / 11 suffixes, one gated at level 10
  and therefore unreachable. Target: gear tiers that track the rings, weapon
  *types* with distinct behaviours, armour *types* with distinct tradeoffs
  (light/medium/heavy), and enough affix variety that generated items are
  worth comparing.
- [ ] **Give crafted items reasons to exist** beyond "more content" — the
  audit's core complaint. Consumables are currently 24 entries of which 15 are
  `{uses, effect_value, heal}` food. No buff, resistance, antidote, or
  throwable entries exist.
- [ ] **Exercise the hazard system.** 6 hazard types are authored with flavour
  text and resistances; **exactly one room in the world uses one**. A volcanic
  ring should be hot, a glacial ring cold, catacombs should have bad air.
- [ ] **Extend weather** so it varies meaningfully by region and interacts with
  hazards, travel, and gathering.
- [ ] **Make exploration pay on its own** — discovery XP, discoveries/knowledge
  entries, landmark rooms, rare sites. A player who walks 40 rooms and kills
  nothing should still gain.
- [ ] **Resolve the density contradiction.** The previous roadmap carried an
  unchecked item: *"Densify existing regions before creating new ones."* The
  new design commitment says sparse rooms are correct and the fix for "empty"
  is better prose and more landmarks, not more objects. **Delete or rewrite
  that item** — do not leave both standing.

### Definition of done

- A player can progress from level 1 to 15 by exploring a designed world
  without repeating content.
- No ring is reachable "early" in a way that trivialises it, or late in a way
  that makes it pointless.
- Every hazard type is used by at least one region.
- A new region can be authored from templates without engine changes.

---

## P8: Engine health

Deliberately after P0–P4, because these are refactors and the repair phase is
more urgent.

- [ ] **Split `engine/server/headless_server.py`.** One ~3,374-line,
  ~140-method class covering session lifecycle, TCP/WS/msgpack framing,
  capability negotiation, the operator catalog, and world-effects policy. The
  roadmap itself has flagged this for a while; it is now the main obstacle to
  adding protocol surface for new systems.
- [ ] **Split `client/scripts/ui/main_controller.gd`** (2,993 lines).
- [ ] **Break the pygame dependency for headless runs.**
  `engine/utils/text_formatter.py:3` does `import pygame` at module scope and is
  imported transitively by `container.py` → `item_factory.py` →
  `crafting_manager.py` → `headless_server.py`. Consequence: the content-set
  validator cannot start without the client rendering library, and the command
  registry silently fails to load `inventory`, `locksmithing`, `magic`,
  `mercantile`, and `quest`. The only pygame uses in that file are four type
  annotations. A `TYPE_CHECKING` guard fixes it.
- [ ] **Make the dependency stack installable.** `torch`/`transformers` are
  unconditional because `engine/ai/ai_manager.py` imports `LLMInterface` at
  module scope — a ~1GB ML stack is a hard requirement to import
  `engine.world.world`, for a feature that is off by default. `requirements.txt`
  documents this itself. Add a venv/lockfile story; there are no pinned
  versions, and on Python 3.14 `pygame` has no wheel.
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
- [ ] **Unify the editor path with content-set contracts.** The Godot editor
  targets older unpacked conventions; `mud-world-editor/data` is a stale fork
  missing `casino.json`, `interactive.json`, `materials.json`, `resources.json`,
  `sets.json`, `affixes.json`, `collections.json`, `discoveries.json`,
  `campaigns/`, and much of `magic/`.

---

## Deliberately later

- Advanced NPC use of playtester policies.
- Large-scale economy simulation or mandatory player trading.
- Housing tiers beyond a useful personal storage and one functional branch.
- Planar / cross-world content.
- Anything requiring production auth, billing, or live-service operations —
  the operator/authoring/entitlement layer already exists and has no audience
  yet. Do not extend it while the player path is the constraint.

---

## Decisions

### Settled

- **Progression is hybrid.** XP from any recognised activity; no single
  profession carries the game. Discovery is one source among several.
- **No level cap.** The exponential curve is the brake — levels stay available
  and simply become very slow past the content's band.
- **No level-up choices.** Automatic stat growth. Identity comes from
  backgrounds, skills, and earned titles instead.
- **Classes are replaced** by backgrounds + use-based skills + earned, gated,
  self-applied titles, conferred by guild-like constructs.
- **Curve ×1.25 as a starting value, explicitly tunable** — not frozen. Build
  the ledger and content, then tune against play.
- **Tiered towns with soft gating.** Rings gated by danger alone. Player-chosen
  starting towns earmarked for later and not precluded by the design.
- **Extend `fantasy_frontier`**, not a new content set.
- **Distance is difficulty.** No hard level doors or invisible walls.

### Still open

1. **Final curve multiplier** — ×1.25 to start; revisit with real play data.
2. **Per-grant XP values** and the shape of diminishing returns. *(blocks P4)*
3. **Test mode surface** — launch flag, per-session, or both? *(blocks P1)*
4. **Which 4–5 towns**, and each one's economy focal point and personality?
   *(blocks P7)*
5. **Guild model** — how many, how joined, may a player hold titles from
   several, do guilds have halls? *(blocks P4/P7)*
6. **Condition language** — the shared evaluator serving dialogue, titles, and
   quest availability needs a schema. *(blocks P4/P5)*

---

## Audit findings reference

Recorded here so they are not lost when the detail scrolls off.

### Verified defects

| Finding | Evidence |
|---|---|
| Death crash on NPC killing blow | `npcs/combat.py:201`; full traceback reproduced |
| Journal shows literal `?` | `commands/quest.py:309`; live output |
| Loot invisible after kills | live output; inventory unchanged |
| 5 rooms unreachable incl. campaign giver | BFS over 206 rooms from `town:town_square` |
| `quest_missing_guard` unreachable | `quest_chain` has 0 readers in `engine/` |
| Debug commands ungated | live: `level 5`, `setgold`, `sethealth`, `teleport` |
| `craft` multi-word matching broken | `commands/crafting.py:121-133` |
| Classification unreachable in server path | applied only at `game_manager.py:255` |
| `data/dialogue/` never loaded | loader globs exclude it |
| `mage_set` references 2 nonexistent items | `items/sets.json`; validator reports 0 issues |
| 5 dangling refs (`smite`, `item_smoke_bomb`, `item_iron_ore`, `iron_shortage`, `item_scrap`) | each referenced once, defined nowhere |
| pygame blocks headless content validation | transitive import chain; validator cannot start |
| 99 hardcoded content refs in engine | AST audit across 30 files |

### Content volume (as of audit)

| | Count |
|---|---|
| Regions / rooms | 12 / 206 (200 reachable) |
| Item templates | 219 (45 gems, 38 junk, 41 misc, 14 weapons, 16 armour) |
| Spells | 23 |
| NPC templates | 62 (31 hostile, levels 1–8) |
| Quests | 14 authored + 1 instance seed |
| Campaigns | 2 (one unplayable) |
| Recipes | 15 |
| Affixes | 12 prefixes / 11 suffixes |
| Knowledge topics | 13 |
| Dialogue graphs | 1 (unloaded) |
| Resource nodes | 9, each placed once; no tool requirements |
| Hazard types | 6 authored, 1 used |
