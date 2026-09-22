# Chunks of work

**Status:** chunks 0–4 done; **chunk 5 partly done**; **chunk 6 is where to start**
(expanded 2026-09-21 into the game-authoring journey). Supersedes the phase framing
as the *working* view. `integrated-roadmap.md` still holds the cross-track detail
and the verification; this is what to actually pick up.

Track parallelism is no longer maintained as an organising principle. Each chunk
below is one coherent piece of work with a definition of done, and the `⚡` marks
the items inside it that can genuinely run at the same time as something else.

**Earlier chunks are retained as history, not a fresh readiness claim.** Chunk 1 below is kept as the record
of what was found and fixed, not as a to-do list. Chunk 5's leftovers (CI for the
content gate, the gate-falsification harness, the save round-trip, twenty
discoveries) are still worth doing and are now *behind* chunk 6, because the editor
is what turns every later content change from a JSON edit into a five-minute job.

---

## 1. Correctness sweep — ✅ done 2026-09-19

Nine verified defects, none needing a design decision, nothing on the critical
path. Every item is closed; the outcome of each is in the table.

| Item | Outcome |
|---|---|
| Atomic save write + `.bak` + refuse to clobber an unread save | **Fixed.** Temp file + `fsync` + `os.replace`, one `.bak` per session, refusal unless this session loaded that file. 10 tests in `test_save_write_is_durable.py` |
| `time_of_day` reads `time_period` (`conditions.py:137`) | **Fixed.** Reads `time_period`, falls back to `period`/`time_of_day`. 8 tests |
| Quest loader skips `_` keys and non-objects (`quests/loader.py:17`) | **Fixed.** Per-entry guards, so one bad quest cannot abandon 22. 12 tests |
| Fourteen 0-byte test modules | **Resolved.** Five implemented, ten deleted as redundant (one was outside the discovery pattern). Disposition table in `track-H-testing.md` item 2; `HANDOFF.md` corrected by `archive/README.md` |
| `websockets` pinned, or the WS entry point marked unsupported | **Fixed.** Declared in `requirements.txt` and pinned in `requirements.lock`; `test_transport_entry_points_are_importable.py` guards both |
| `LATEST_REFRESH.json` relative, or the fixture steps documented as skipped | **Fixed.** `resolve_recorded_path` reinterprets the recorded absolute path against this checkout, so the committed fixture is now validated (data integrity + stale audit) instead of skipped |
| `boot-warning-codes.md`: 4 codes that do not exist | **Fixed, and the hole closed.** 5 codes were wrong; the doc now lists the true 20, and `_enforce_boot_warning_policy` **aborts startup** on an unknown code, because a fail-on list that cannot fire is worse than none. `test_boot_warning_codes.py` holds doc, constant and emitters equal |
| `save-content-isolation-policy.md` corrections | **Fixed.** Rewritten against the code — `save_format_version: 4` (int), `MIGRATIONS` in `save_format.py`, and the parts that are policy rather than behaviour marked as such |
| `PLAYER_MANUAL.md`: `titles` → `title` | **Fixed**, and `test_player_manual_commands.py` now fails if the manual and the registry disagree |

**Found while doing it, not on the list:** `client/**/*.gd` is syntax-checked by
nothing (`run_editor_checks.py` globs `mud-world-editor/tests/*.gd` only); 9 of the
11 capability keys the client sends to the server are read by no server code,
which is defensible but was undocumented; and the `default` theme pack omits three
`ui_strings` it reads, so those titles fall back to English.

**Done when:** the three gates are green, and a test kills a save mid-write and
asserts the previous file still loads. **Met** — and the save tests were confirmed
to fail against the old non-atomic write before being accepted.

---

## 0. The world editor, before anything splits — ✅ done 2026-09-19

The editor's foundations (create a set, the NPC stat form, connection authoring,
vocabulary parity, the world-link modal) are closed. What is *not* closed is the
editor's coverage of the engine — that is chunk 6, which supersedes this section as
the editor work.

Not a numbered chunk in the original five, and now the *active* work: get the
editor to a good point before the editor and non-editor tracks separate. The
organising rule for that separation, in the operator's words: **"keep folder
separation where possible and keep things as general systems that are as minimally
coupled to each other as possible."** Two consequences for how work is chosen
here:

* A panel does not hold its own copy of a rule another panel holds. The rule lives
  in one module both import (`PropertyTagRow`, `content_check_steps`).
* A check is declared once. The editor and the gate are two renderings of the same
  list (`toolkit/content_check_steps.py`), never two lists.

| Item | State |
|---|---|
| Round-trip every shipped set and compare bytes (G1) | **Done** `3c9ce5e`; found real drift in five region files |
| Stop the panels flattening nested properties (G3) | **Done.** Three panels, one shared rule, mutation-tested |
| Editor validate runs the gate's checks (G-consensus) | **Done.** 5 of 14 → 9, with gaps reported in `not_run` |
| Connection authoring: reciprocal delete, bow controls, one-at-a-time form (G-new) | **Done.** See below |
| Vocabulary parity + the two wrong `EFFECTS` shape hints (G2) | **Done.** Found a third defect: `talk` |
| Engine reference integrity from the world link check (G4) | **Done.** Advisory wording marks what the engine does not claim |
| NPC stat form reads the set's stat declaration (G5) | **Done.** Four defects; the declaration is in the contracts, not the ruleset |
| Scaffold a new content set by copying one (G6) | **Done.** Engine owns the manifest; rules are copied on request, because a ruleset names the world it came from |
| Where an authoring tool lives now that `tools/` is gone (G7) | **Parked** by decision 6, with the reason in the deferral ledger |

### Creating a content set (done 2026-09-19)

The last "you cannot do this from the editor at all" in the list. `DataRoot`
finds a set by testing for `content_set.manifest.json` and nothing had ever
written one, so the documented way to start a world was to hand-write the
manifest — which is what the editor's own tests did. Now: **New content set...**
in the content-set chooser, a form with an id, a title and a source, and a
receipt that reports what was written and what is still owed.

**The measurement that shaped it.** A ruleset is not a self-contained thing to
copy; it is a manifest of references into the world it was written for. Counted
across the shipped sets, `modern_capsule`'s ruleset names nothing, `night_shift`'s
names three items, `orbital_salvage`'s five and `fantasy_frontier`'s ninety.
Scaffolding from fantasy_frontier *with* its rules produces a set that opens and
fails validation on 72 unresolved references. So copying rules is a checkbox the
dialog explains rather than the default: off gives a ruleset that declares nothing
and a set that validates; on gives a close copy of another world, and its entire
to-do list. The item's done-when ("`EngineValidator.run` returns ok") is met by the
default, and the other mode is honest about what it is.

**The manifest is the engine's, checked.** Its field names moved out of
`load_content_set`'s body into module constants, the vocabulary dump reads them,
and `schema_parity_smoke.gd` compares the editor's table against them in both
directions — mutated to prove it fails. That is the ownership decision, applied.

**Five defects found on the way:** the `quests` capability requires `quests/` and
`campaigns/` data directories the scaffold was not creating; the starter region
was classified from the *source's* ruleset rather than the new set's, copying
fantasy's biome vocabulary into a set whose rules declare nothing; the placeholder
ruleset and starter region must create their own parent directories because
`SaveIO` refuses to; a source without `opening/` was refused though the engine
treats it as optional; and the dialog needed a way to be pointed at scratch state
so a check can drive it without writing into `content_sets/`.

**New check:** `tests/content_set_scaffold_smoke.gd` — 40 assertions including
driving the real dialog and the real `Main.tscn`. 30 editor checks, all passing.

### The NPC stat form (done 2026-09-19)

The last panel in the editor still speaking one world's vocabulary. `attr_keys`
named eight fantasy stats and showed them for every content set, so
`orbital_salvage` (six stats) and `modern_capsule` (none) were offered rows they
do not have. The rows now come from the declaration, with the engine's own
precedence: contracts `stats.order`, then `ruleset.status.stats`, then the stats
`stats.roles` names, then the stats the set's NPCs already carry — and the panel
says which one it used. Nothing falls back to the engine's *default* names: a set
that has declared nothing gets a sentence naming the file to declare them in,
rather than eight rows nobody agreed to.

Three more defects went with it, all in the same panel and all the kind this
track exists for: opening an NPC wrote an empty `stats` object into its file;
every edited number was written as a float (the int-to-float defect the number
gate exists to catch); and the two pool labels said "Mana" and "Health" for every
set, where the declared `resources` entry now answers (orbital reads "Charge").

**Found and recorded rather than fixed:** orbital declares `ability_power` and
`resistance` as `spell_power`/`magic_resist` and carries neither on any NPC, so
both mechanics sit at the neutral default for that set. Omitting the roles would
not help — the engine falls back to the same names — so a set that wants a real
value must name a stat it has. That is a balance decision, and it is now visible.

**New check:** `tests/npc_stat_vocabulary_smoke.gd`, one fixture per source plus
the empty case plus the shipped set. 29 editor checks, all passing.

### Connection authoring (done 2026-09-19)

Asked for by the author of the world, from actually authoring in it. Five changes,
all in `mud-world-editor/`, all with a check in
`tests/connection_editing_smoke.gd` (24 assertions, mutation-tested):

- **Deleting a connection removes both ends by default.** Connections are authored
  in pairs, and removing one end left a half-link that still drew and still claimed
  to lead somewhere. The one-way removal — the case that needs saying so — has its
  own quieter button, and only appears when a pair actually exists. Committed as
  one undo step. A cross-region exit deliberately reports *no* pair rather than
  guessing: its far end is in a file this region has not loaded.
- **The bow's side and distance are authorable** (`_editor_exit_layout`, which
  `EditorLayout` already keeps out of content files). Without this the side was the
  perpendicular of the line between two rooms, so moving a room silently flipped
  it. Both controls are click-to-cycle, shift-click-to-clear; `normal` is stored as
  *no key* rather than as a value, since an override meaning "the same as no
  override" is state with no meaning.
- **The form reads in the order it is filled in:** reciprocal above both direction
  rows, and both rows in one format —
  `Connect <room> [dir] to <room>` / `Return <room> [dir] to <room>`.
- **Connection mode.** While the form is open, a map click means "the far end" and
  nothing else, checked *before* the paint and stamp tools so one click cannot both
  pick a target and paint a property onto it; and room dragging does not start at
  all, because a room moved while aiming at it is a content change that reaches the
  save. Set through one entry point used by both ways in, cleared whenever a room
  loads, so it cannot get stuck on.
- **Connecting closes the form; "Connect another" does not.** The second keeps the
  source, direction and reciprocal choice and clears only the target, which is how
  a room with four exits gets authored.

**Two defects found on the way, both fixed:**

- `ConnectionEditor._on_conn_region_changed` passed `rooms[r_id]` — the room
  *object* — straight to `OptionButton.add_item`, which wants a string. The target
  room list was rendering object dumps instead of names.
- `next_curve_amount` treated an unrecognised value as "start of the cycle" rather
  than as `normal`, so a fresh exit's first click gave the wrong step.

**Not done here, and deliberately:** panning, zooming, box-select and the
right-click context menu still work while the connection form is open. They do not
conflate with target selection, and locking them costs usability.

### Vocabulary parity (done 2026-09-19)

`tests/schema_parity_smoke.gd` compares both directions against the engine's own
sets, read through the new `toolkit/engine_vocabulary_dump.py` — which *imports*
them, rather than listing them a third time. Both directions matter, for different
reasons: a kind the editor offers but the engine ignores is a gate that never
fires; a kind the engine routes but the editor lacks forces hand-edited JSON.

**Three defects found, one of them new:**

- `adjust_relationship`'s hint said `{amount}`; the engine requires `npc` as well,
  and fails with "no npc or amount" without it.
- `move_npc`'s hint said `{npc_id, region_id, room_id}`; the engine reads
  `npc`/`region`/`room` and reads none of the `_id` names.
- **`talk` is a routed objective type** (`npcs.py` treats it with
  negotiate/deliver/fetch at turn-in) that the editor's `QuestSchema` did not
  offer. Authored quests use 7 of the 16 types so far, so nothing shipped broken —
  but an author wanting a "just go talk to them" objective had to hand-edit JSON.

The check also asserts that every effect shape hint names the fields the engine's
own reader pulls, with two recorded exceptions: `delta` is an alias for `amount`,
and `generated_item_data` is a pre-rolled instance written by the procedural-loot
path, which hinting would invite authors to hand-write.

Mutation-tested: dropping the `talk` entry fails the check by name.

### The world-link modal (done 2026-09-19)

`Main._show_validation_results` now shows the engine's reference verdict before the
editor's own walk, via a new `--only` filter on `editor_validate.py` so the modal
gets the *link* findings without the item, quest and contract ones.

The editor's walk stays — it reaches every loaded region in one pass — but its
wording is marked `[advisory]`, including the one-way-link note, which the engine
deliberately does not make: it is geometry-blind and has no opinion about whether a
connection is symmetric. Previously the two voices were equally loud for the same
fact, in two different wordings.

The `--only` filter recomputes its counts, because stale counts would make the
modal's summary disagree with its own list. `test_editor_validate.py` covers that,
the narrowing direction, and that an unfiltered run is unchanged.

**Done when:** the editor's Validate button and `run_content_checks.py` cannot
disagree about any check, and no two panels implement one rule twice.

---

## 2. Seasons and settling — ✅ done 2026-09-19

Two halves, and they are **independent — do them in whatever order, or at once.**

### 2a. Preservation content — ✅ done 2026-09-19

Winter now has an answer, using only the proven chain and no timer work. Authored
into `fantasy_frontier`:

| What | Ids |
|---|---|
| Items | `item_dried_herbs` (Consumable, heal 2, value 4), `item_ale_wort` (material, value 8) |
| Station | `item_drying_rack` — field-for-field the `item_anvil` shape, `crafting_station_type: "drying_rack"` |
| Recipes (instant, `station_required: drying_rack`) | `dry_wild_herbs` (3 herbs → 3 dried), `steep_gruit_wort` (2 dried + vial → 2 wort), `ferment_house_ale` (4 wort → 1 barrel, DC 12) |
| Placements | `farmland:barn_interior` (a room from the authored `node_herb_bed`) and `town:tavern_kitchen` |
| Also | `ruleset.json` `debug.spawnable_stations["drying"]` — required, or `spawnstation` cannot reach it |

The walkable chain is now `node_herb_bed → item_wild_herbs → (rack) dried herbs →
(rack) wort → (rack) barrel of ale`, and the existing `item_wild_herbs →
item_alchemy_kit → brew_minor_heal` chain is untouched. `item_barrel_ale`, which
had no source, now has one.

**Verified** by gate (all four sets clean on the number check, content checks
passed), by 140 targeted tests, and by an end-to-end headless probe: gathered 6
herbs, dried them at the barn, steeped wort at the tavern, fermented a barrel.

**Deliberately left open — a real decision, not an oversight.** The design doc's
stage 2 wants the *alchemy table* to consume `item_dried_herbs`, which would close
the literal `herb bed → rack → alchemy table → tonic` line. Doing it means adding
`item_dried_herbs` to an existing brew's `alternatives` (the set's own
substitution convention) or authoring one more recipe. Both edit existing content
beyond this chunk's brief.

### 2b. Settling the contract — ✅ clock decided, gate built, `work` shaped

- **The clock decision — ✅ made.** See "Decisions that gate chunks" below. The
  fix it implied is landed and tested.
- **The read-or-delete gate — ✅ built** as `toolkit/contract_field_audit.py`,
  wired into `run_content_checks.py` as "Audit contract fields for a reader". It
  is a **ledger, not a scanner**, and the module docstring records why: a
  quoted-literal scan gives both false negatives and false positives on this
  codebase, all three measured. It fails when a contract field is declared and
  unclassified, and when a ledger entry outlives its field. Fault injection
  confirmed both directions, and `test_contract_field_audit.py` (13 tests) keeps
  it honest.
- **What the gate found on its first run** — 63 fields, **10 declared and read by
  nothing**:

  | Field | State |
  |---|---|
  | `attack_profiles.cooldown` | declared and type-validated; weapon cooldowns are not implemented |
  | `attack_profiles.resource_cost` (+`resource`, `amount`) | `registry.py` reads it only to check the named resource exists; nothing charges it |
  | `abilities.effect_packet` | see below |
  | `effect_packets.kind`, `.value`, `.duration`, `.tags`, `.payload` | the packet's payload fields; nothing consults them |

  These are recorded as debt with a reason each, pinned in `KNOWN_UNREAD`, which
  can shrink deliberately but not grow by accident.
- **`effect_packets` — verdict now measured: wire it, and it is the last mile of
  work already half-done.** The layer is not inert: abilities declare
  `effect_packet` (`required: True`), the registry validates that the reference
  resolves, and `registry.effect_packet()` is a public accessor. What is missing
  is the final step — `ability_numbers()` reads cost, cooldown, targeting and
  level but **not** the packet, and effect application is per-spell code in
  `magic.py`. `docs/design/cross_theme_engine_contracts.md` §2 "Combat and ability
  seam" is exactly this seam, and its equipment and ability-resource halves are
  already built and tested. The alternatives are to delete the two abilities and
  three packets from both sets (smaller, loses the worked example of a neutral
  ability) or to apply a cast through its packet rather than per-spell code.
- The other three named in this item turned out **not** to be unread, and the
  ledger says who reads each: `debug_only` (three generators exclude those
  templates from loot and generation), `attack_profiles.cooldown` is the genuine
  one of that pair, and the tier weights are **partly** inert — `value_multiplier`
  and `weight_multiplier` are read, while `tier.weight` is not, because
  `instance_generator._weights_for` synthesizes weights from a positional curve.
- **`work` — ✅ the shape landed 2026-09-19; the resolver did not, on purpose.**
  The roadmap line for this was "the shape, not the resolver": E and F can author
  against it, and a consumer test exists. What that means concretely:

  | Piece | Where | State |
  |---|---|---|
  | The declaration (`id`, `label`, `description`, `duration_days`, `inputs`, `outputs`, `skill`, `difficulty`, `tags`) | `registry.py` `WORK_FIELDS`, the eighth top-level section | same schema language as the rest; a typo'd field fails content validation |
  | Start / read / complete | `engine/contracts/work.py` — `work_for`, `duration_seconds`, `begin`, `remaining_seconds`, `is_due`, `observe` | built and tested (41 tests) |
  | Vocabulary check | `work.declaration_issues()` | a skill with no difficulty gates nothing; a difficulty with no skill rolls nothing |
  | Moving items, the start/collect verb, a tick loop | nowhere | **not built** — see below |

  **A timer is two absolute numbers.** `started_at` and `ends_at`, both against
  `world.clock` — a `WallClock` on a live server, a `SimulatedClock` the tests can
  `set()`. Not `TimeManager.game_time`, which is a frame-delta calendar that stops
  when the process does. Completion is therefore a comparison rather than an event:
  nothing has to fire at a moment, every observer agrees because they all compute
  from the same two numbers, and a saved timer is still meaningful after the
  process has been down — where a saved "seconds remaining" would not be. That
  last claim is asserted by round-tripping a timer through JSON and reading it
  against a clock that moved on, which is exactly what a save file does.

  **What is declared and not yet read** — measured, not assumed: `inputs`,
  `outputs` and `tags` are `UNREAD` in the ledger, because `begin()` returns a
  timer without consuming anything. Moving items needs to answer *which* inventory
  and *which* container first, and that is a decision about the game's shape rather
  than about durations. They stay declared (content can author against them, which
  is the point of this item) and they stay pinned in `KNOWN_UNREAD` with a reason,
  so the debt is a recorded decision rather than a silent no-op.
- **`duration_days` is the one field that makes a declaration take time**, and it
  is wired: no duration means instant, which is how a plain recipe and a
  three-day ferment are the same kind of declaration. `ResourceNode.respawn_days`
  is the precedent for the unit.
- **`work` has its first consumer — ✅ 2026-09-19, and it is a second theme.**
  `orbital_salvage` declares a fabrication batch: three salvaged parts into the
  workshop's bay, half a day, two patch kits out, against the instant recipe's one
  kit from two parts. So a duration now means something in a set with no winters,
  which is what "a system is not finished until two themes use it" was asking for.
  The verbs landed with it (`start`, `collect`, `due_jobs`), the two fields the
  ledger had recorded as unread (`inputs`, `outputs`) now move items, and the
  command surface is `jobs` / `begin` / `collect`. Chunk 2's open item — *which*
  inventory — is answered: the player's, because a player is an owner that already
  round-trips through a save, and a room is not.
- **The day was 72× too long, and only content found it.** `duration_days` was
  multiplied by 86400, but the clock it anchors to counts real seconds and a game
  day is `TIME_REAL_SECONDS_PER_GAME_DAY` (1200). An authored "one day" would have
  taken 72 of them. Every test agreed with the bug because every test used the
  constant the bug was in. The fix is one import, and the test that pins it now
  asserts the meaning: a one-day job is due after one game day and not before.
- Also fixed on the way: `ContractRegistry.is_empty` did not count the new section,
  so a set declaring only `work` still reported "this content set declares no
  contracts" and skipped its own validation.

**Done when:** the gate can be shown to fire (re-add `debug_only` with no reader
and watch it go red) — **met**, by injecting `silent_no_op` and by deleting
`debug_only` from the schema to prove the orphan direction — and `work` is
documented enough that E and F can author against it — **met**, above, with the
declaration validated by the same schema language as every other section and a
41-test consumer for the part the engine actually does.

**⚡ 2a and 2b do not touch each other.** 2a is JSON; 2b is `server/engine/` +
`tools/`. The only collision is if the `work` shape changes how a recipe is
written, which is why 2a ships without timers and gains `duration_days` later as
one data edit. The authored recipes reuse the design doc's own numbers so that
change is one field.

---

## 3. The second consumer

The chunk that decides whether the engine is general or is fantasy with different
nouns. Four pieces, and **each can run alone.**

| Piece | What | Owner | Scope |
|---|---|---|---|
| ~~**Night shift crime loop**~~ ✅ **done 2026-09-19** | Two lockpick sources, three owned containers, a locked storeroom, a fence, an `advancement` table — and three engine seams it exposed | F (+E for what it exposes) | small–medium |
| ~~**Orbital duration**~~ ✅ **done 2026-09-19** | A fabrication batch in the workshop's bay — a set with no winters, and `work`'s first consumer | F (+B if the shape strains) | small |
| ~~**Environment: one declared value, one reader**~~ ✅ **done 2026-09-19** | Three expressions of "this room is dangerous" collapsed into one record; orbital's empty `hazards` seat filled with `hull_frost` | B declares, E reads, F authors | medium |
| ~~**Social declared**~~ ✅ **done 2026-09-19** | The ladder is a set's own or there is none: three sets declare one, the surface is gated on the capability, and a set that declares nothing shows no bond at all | F + E | small |

**Why together:** each is the *second* use of something. Doing one proves the
convention; doing all four is what stops the next system being fantasy-shaped by
default.

**✅ Orbital duration is done, and it answered chunk 2's open item rather than
dodging it.** The consumer turned out to need the item-movement verb after all —
not because a dock window does, but because a *job* does: `start` consumes
declared inputs and `collect` yields declared outputs, both against the player's
inventory. That is the owner the design doc had already scoped to (players and
items are what round-trip through a save), so the answer was a sentence rather
than a container system. What landed: `start`/`collect`/`due_jobs` in
`contracts/work.py`, the player's `WorkState` aspect with its save round-trip,
`jobs`/`begin`/`collect` commands, a `station` field on the declaration, an
orbital batch that trades time for a better yield, and a journey test that starts
a batch in one process and finishes it in the next.

**✅ Environment is done too, and it is the piece that found a balance bug.**
A hazard was three expressions of one fact — a channel map, a sentence keyed by
*channel* (so two hazards sharing a channel shared prose and a hazard's own name
never reached a player), and per-room damage/interval properties. Now it is one
record in the set's own `combat/elements.json` (`channel`, `flavor`, `damage`,
`tick_interval`), a room names it, and one reader
(`engine/world/environment.py`) resolves it. `orbital_salvage`, which shipped
`"hazards": {"mapping": {}, "flavor": {}}`, now declares `hull_frost` in the cargo
hold — `thermal`, its own channel, in its own words — and its `impact vest` resists
it, so mitigation is 3 damage bare against 2 through the vest.

The bug: the engine subtracts the `resistance` role's stat **raw value**, so
pointing that role at a core attribute means subtracting 10 from every energy hit.
Orbital did exactly that (from the earlier stat-vocabulary work) and its new
hazard was therefore harmless until a test measured it. The role now names
`insulation`, a small derived rating — the shape fantasy's `magic_resist` (2) has —
carried by the crew at 1–2 and by no salvager, who survives the cold on gear. That
also vindicates the deferral ledger's refusal of a "a role must name a stat some
entity carries" gate, which would have forbidden the correct declaration.

**One fork this closed, deliberately.** The `work` declaration is a *contract*
section, and recipes gained no `duration_days`. The two routes to "this takes
time" were: a timed recipe (reusing the crafting surface's stations, quality tiers
and familiarity) or declared work (a general primitive any system can use). v1
built the second, because it is the one the design doc described and because
recipe durations need a decision about how waiting interacts with quality tiers
that nobody has made yet. **Recorded, not refused:** a recipe *may* later declare a
wait and reuse this timer, and the thing to avoid is a second duration mechanism
with different semantics.

**Done when:** for each system touched, two themes declare it — asserted by
content, not claimed. For duration: `orbital_salvage` declares `work`, and its
journey test asserts the loop end to end. For environment: two sets declare
hazards through two different channels. For social: **three** sets declare a
ladder, in three different sets of words, and a fourth deliberately declares none.
For crime: `night_shift` plays the whole loop — take what is not yours, be caught,
be held, get out — in a set with no fantasy nouns.

**✅ The night shift crime loop is done, and authoring it found three seams that
content alone could not fix.** The set now has its two lockpick sources (a tool
crib of shim cards in the supply room, a master shim in a locked wire cage behind
a locked storeroom door), three containers that belong to somebody, a fence
(`Otis`) at the end of the alley who buys anything and sells the tool for getting
back out, two new rooms, and an `advancement` table so the ledger pays for
arriving, meeting and fighting rather than recording entries for nothing.

What the authoring exposed, all three fixed:

1. **An authored container's `contains` never reached the constructor.**
   `ItemFactory` pops a template's `properties` out before instantiating, and
   `Container.__init__` is what turns `{item_id, quantity}` into items — so every
   container authored with contents came out empty, and the factory's property
   loop skipped `contains` on the assumption the constructor had hydrated it. Two
   comments describing an intent, neither implemented, and invisible because no
   shipped set had ever authored a container's inventory.
2. **`quantity` in those references was read and thrown away.** "Two energy
   drinks" put one in the till. A container holds instances and has no stack
   model, so a count is now that many instances.
3. **`get <item> from <container>` was a risk-free robbery.** `steal` consulted
   `owned_by_npc` and rolled a witness; `open locker` then `get multitool from
   locker` took the same thing with no consequence at all, which made the crime
   system optional for the only containers it was written for. Both phrasings now
   settle the risk through one helper, and the second phrasing also records the
   acquisition in the collection, discovery and advancement ledgers, which it
   silently skipped before.

**New check:** `test_night_shift_crime_loop.py` (13 tests) walks the loop, and
`test_container_authoring.py` (7) pins the two container fixes so the next set
that authors a chest fails a small named test rather than a journey. Also fixed
on the way: a pre-existing flaky assertion (`test_npc_core_full`) that counted a
corpse's whole drop list, which includes a chance-rolled ambient item — it now
counts the loot it is actually about.

**✅ Social is done, and it ended up bigger than "declare it in orbital".** The
finding was that the engine kept a fantasy-shaped *default* ladder: a set that
never mentioned relationships rendered "Close Friend" and quietly took up to 15%
off its own vendors' prices. A default that moves prices is not a default, it is
an undeclared rule. So the ladder is now the set's or there is none — no tier
names, no score kept, and no discount — and the section is validated for the first
time (a `tier` typo, a string `min`, a gift category the engine never scores, a
repeated threshold, or a ladder with no bottom rung each fall back silently today
and are errors now). Presenting the surface and declaring the ladder became one
decision, checked both ways: a ladder with no capability is an **error** (a
declaration nobody can see), and a capability with no ladder is a **warning** plus
honest degradation — a scaffolded set inherits its source's capability list on its
first day, so its commands say "this game does not track bonds" rather than
printing a score with no name attached.

`orbital_salvage` (Unvetted / Known / Trusted / Crew, 3-9-18 — sized so four
crafted gifts or a few days of Ivo's orders reach the top) and `night_shift`
(Never seen you / Not a stranger / A face / On the list) both declare ladders and
the capability; `modern_capsule` declares neither and now presents no bond surface
at all, which is right for a vignette. Gift *scoring* still has engine defaults,
because a gift has to be worth something; the words and the numbers are content's.

**Note:** the night shift piece will expose container-theft seams
(`theft.py:40` requires naming an item the container only generates on first
attempt). That is E's, not a content fix.

---

## 4. The thin sets and the front door

Content-only, bounded, and the answer to "are the other three sets games?"

| Piece | What | Owner | Scope |
|---|---|---|---|
| ~~**`night_shift` plays**~~ ✅ **done 2026-09-19** (as chunk 3's crime loop) | It has containers that belong to somebody, a fence to sell to, a locked way out and a 13-test journey. The row's premise — a ruleset declaring systems its manifest omits — does not apply to `crime`/`custody`/`locksmithing`: the engine's capability vocabulary (`_CAPABILITY_SYSTEMS`) has no such names, and those sections are read directly by their managers | F | small–medium |
| **`modern_capsule` gets its repair café** | ~~Its own flyer already advertises an event with no content behind it~~ ✅ **done 2026-09-20 as a vignette** (decision 2): two dialogue graphs, two props, and an exchange with a real outcome, with every other system still switched off | F | small |
| ~~**The four unused objective types**~~ ✅ **done 2026-09-20** | `relationship`, `discover_n`, `craft_quality`, `deliver_multi` had **zero** authored quests; each now has one, and two of them exposed engine defects | F (+B for what it exposed) | medium |
| ~~**Three NPC templates placed**~~ ✅ **done 2026-09-20** | `forest_hermit`, `wandering_mage`, `wandering_priest` existed in no room and no spawner | F | tiny |

**✅ Chunk 4 is done, and the "content-only" label was wrong for half of it.**
Four engine defects and one dead feature came out of authoring content that had
never been authored, which is the same lesson chunk 3 taught. The pieces:

**✅ The four objective types are done, and they were not a content-only job.**
One quest per type, all four reachable from the town board: Elder Thorne asks after
Old Bryn and the hermit's trust is the objective (`relationship`, 5 — one crafted
gift); Curator Vane wants six different things handled (`discover_n` on the
journal's `item` entries); Barlin wants one barrel of house ale laid down until it
comes out **Fine** (`craft_quality`, which is eight brews of that recipe, because
the ladder is the recipe's own authored `min_crafts`); and Talia's two sealed
packets to Portbridge and Frostpeak are the game's first `deliver_multi`.

What authoring them exposed, all fixed:

1. **`deliver_multi` had no way to obtain its goods, in any content set, ever.**
   `give_handler` matches copies of one template, and the acceptance path handed
   out a package for `deliver` only — so the type was unplayable by construction
   rather than merely unauthored. The rule is now one rule for both
   (`engine/core/quests/packages.py`): a single delivery hands over its named
   instance-scoped package, a courier run hands over one per recipient, and
   everything is built before anything is given so a full pack refuses the job
   instead of leaving the player holding half of it.
2. **The bandit campaign's peaceful branch could not be accepted at all.** Its
   `deliver` objective named no package instance and targeted `recipient_instance_id:
   "bandit_king"`, an id no factory ever creates (the King is spawned from the
   `bandit_leader` template by that stage's own `spawn_on_entry`). Any player who
   negotiated a truce was told "This delivery task has incomplete item data." Two
   fields and a template reference fix a whole branch of a campaign.
3. **A quest item could be given away.** Selling one has always been refused
   ("isn't something you can part with"); handing one to a bystander was not, which
   for a two-packet courier run means a permanently unfinishable quest — and
   nothing in the game can hand an item back.
4. **Every single-stage quest threw away its authored closing line.**
   `advance_quest_stage` answers the end of a quest with the sentinel
   `"QUEST_COMPLETE"`, so `completion_dialogue` on a final stage never reached the
   player: 21 of the set's 26 quests ended on `"Thank you!" says <npc>`. The
   turn-in path now prefers what the author wrote, then the NPC's own parting line,
   then the fallback.

**✅ The three unplaced NPCs are placed, and the reason they were unplaced is worth
keeping.** All three were authored for the ambient wanderer spawner
(`spawner.npc_types`), a fully implemented and unit-tested feature that **no
content set has ever declared** — so it has never spawned anything, and three
finished NPCs sat unreachable. Old Bryn is pinned to the ancient oak
(`behavior_type: stationary` at the placement, not in the template: his quest needs
him found twice, and the oak's east exit leads into the Shadow Caves). The mage at
the forest crossroads and the priest at the farmland bridge keep their authored
wandering, which gives the valley a healer outside town. Switching the spawner on
for real is a world-density decision, recorded in the deferral ledger rather than
made here in passing.

**New checks:** `test_p6_new_objective_types_journey.py` (7) plays all four
through the board, the real command paths and the turn-in dialogue — reading the
board *as a player sees it*, markup and hidden notices included.

**The front door was stale too, and is now honest.** `night_shift`'s opening
briefing still told a new arrival to "check the supply room, mind the dog in the
alley" and then stopped — two objectives, written before the set had a loop. It
now names the three things a shift actually involves (the register and tool crib
under Dana's eye, a shim and the locked storeroom door, Otis at the end of the
alley), each instruction ending in the literal next command to type.

**✅ The café is answered in dialogue, and that closes the chunk.** `modern_capsule`
is a vignette by decision (2, below), so its flyer is answered with the systems it
actually has: two dialogue graphs (Maya explains the neighbourhood and the rule
about the library's shelf; Devon runs the electronics table and mends the desk lamp
you brought, with `take_item` + `give_item` + `set_flag` and no reward loop), plus
the two props the scene needs — the flyer's small print, and a broken lamp on the
shelf. `test_modern_capsule_repair_cafe.py` (5) plays it and asserts in the same
breath that quests, crafting, combat, magic, abilities and economy are all still
off and the player still has no progression.

**Done when:** a player can finish an errand in `modern_capsule` without touching
a fantasy system — ✅ done, as a vignette whose "errand" is a conversation with an
outcome — and `night_shift` has a loop rather than a ruleset — ✅ done in chunk 3.

---

## 5. Operations, docs, depth

The chunk you pick up when you do not want to think hard, plus the work that only
matters once the world is bigger.

| Piece | Owner | Scope | Parallel |
|---|---|---|---|
| ~~`AUTHORING_A_CONTENT_SET.md` — the missing document~~ ✅ **done 2026-09-20** | J | medium | ⚡ |
| ~~Stale-path sweep~~ ✅ **done 2026-09-20** (plus the README's front door) | J | small | ⚡ |
| ~~`README.md` rewrite — it fails at step one~~ ✅ **done 2026-09-20** | J | small | ⚡ |
| CI runs `run_content_checks.py`; Windows job | C | medium | ⚡ |
| Gate-falsification harness | H+I | medium | ⚡ |
| Whole-state save round-trip + an old-version fixture | H | medium | ⚡ |
| ~~Editor: byte-compare round-trip, nested-property guard, schema parity~~ → **moved to chunk 6** (items 1, 12, 14) | G | medium | ⚡ |
| Save-key manifest | C | small | ⚡ |
| Twenty discoveries (5 → 25) | F | medium | — |
| `content_values` widened one loader at a time | B+I | large | — |
| Extract the duplicated command ladder | C | medium | — |

**Why last:** none of it de-risks anything above it, and two items (discoveries,
the command ladder) only pay off once there is more world to walk.

### The documentation front door — ✅ done 2026-09-20

All three J items above, and all three were worse than "stale":

* **The README's entry point did not exist.** "Running the Game" said
  `python main.py`; there is no root `main.py`. It now names the two real entry
  points (`server/server_main.py` for a terminal, `server/launch_content_set.py`
  for a served set), explains `--content-set` and `--presentation-mode`, and its
  62-command reference was checked against the shipped command registry — the
  only two names not in it (`climb`, `swim`) turned out to be *correct*: content
  declares those exits and the player can use them where they exist, which the
  command registry alone cannot show. Verified by playing it, not by reading it.
* **The stale-path sweep was 65 links, not 52 lines**: `C:/python/old/restart/`
  appeared in 11 documents, and every target exists here at the same relative
  path. All 65 are now relative, so they work wherever the repository lives.
* **The operator guide's commands could not run.** Rewritten after being
  executed: `setup_wizard_cli.py` requires `--content-set`, both servers require
  it too, the wizard writes `<server-slug>.server_config.json` rather than
  `server_config.json`, and feature profiles live in the content set they
  describe (`content_sets/<set>/data/profiles/*.profile.json`), not in
  `server/data/profiles/`. The section that told operators to launch
  `server/launch_from_latest_fixture.py` now names the file that exists.
* **`AUTHORING_A_CONTENT_SET.md` is written** — the document a new contributor
  needs and the repository did not have. Every command in it was run and every
  fragment is a truncation of a file that exists: a minimum set (manifest, two
  rooms, one item, one NPC, ruleset, presentation, opening) was built in `tmp/`,
  booted with `launch_content_set.py`, played through `char create` → `look` →
  `north` → `talk Orla` → `get ledger` → `look ledger`, and swept with each
  per-set validator first. Authoring it found three facts the code knows and no
  document said: `opening/*.json` requires a `scenario_id`; the `quests`
  capability requires **two** data directories (`quests/` *and* `campaigns/`);
  and a manifest capability disagreeing with
  `ruleset.systems.<name>.enabled` is an error rather than a default.

**Two further documentation defects the widened checks found, both fixed:**

* **32 relative links under `docs/` landed nowhere** — not absolute, just written
  from the wrong base directory (`docs/plan/work-tracks.md` linked
  `world-editor-track.md` as if it sat beside it; `docs/archive/archive-2026-09.md`
  linked `docs/design/...` as if it sat at the repository root). Every target
  existed, so all 32 were repaired mechanically, and the rule is now wholesale:
  **every** relative link under `docs/` must resolve.
* **`docs/archive/archive-2026-09.md` was not valid UTF-8** — a tool had written
  cp1252 punctuation into an otherwise UTF-8 file, so seven passages rendered as
  `�` for every reader. Repaired with a cp1252 error handler, which is the only
  approach that works on a file mixing both: a blanket byte replace also ate the
  tail of four genuine en dashes, and the archive had to be restored from git and
  redone.

* **New check:** `test_documentation_links.py` (4 tests) refuses an absolute link
  target anywhere in the docs, resolves every relative link under `docs/`, and
  requires every markdown file to be UTF-8. Falsified before it was trusted: a
  planted absolute link fails three of its tests, a planted cp1252 byte fails the
  encoding one, and a planted dangling link fails the resolution one.

### Pulled forward: the P2 neutrality trio — ✅ done 2026-09-20

Not on this list, because it was on `ROADMAP.md`'s "Still open" instead — three
engine-vocabulary items that every content set depends on and none could see. All
three are done, and the pair of them found more than the roadmap entry described:

1. **Factions are asked in one place.** ~29 call sites compared a faction *string*
   to `"hostile"`; `engine/world/factions.py` answers instead, and a set can
   declare its own names (`ruleset.factions.extra`/`overrides` with a disposition)
   for display, targeting, conversation, wandering, quest generation and
   kill-reputation at once. Two things the strings were hiding: `npcs/combat.py`
   read the engine's *flat* matrix, so a set's own factions would never have been
   enemies in combat; and the matrix itself is now derived from one table, proven
   byte-identical to the shipped one by test.
2. **`behavior_type` is a vocabulary with a reader.** `NPC_BEHAVIOR_TYPES` had no
   reader at all and was wrong — `healer`, used by three shipped templates, was
   missing from it. It is complete, the dispatcher dispatches through a routine
   table a test holds equal to it, a misspelled value is a gate *warning* ("this
   NPC will stand still and do nothing"), and the list with each value's meaning
   is in the authoring guidelines beside the other closed vocabularies.
3. **`game_object.py`'s class-name type check is `isinstance`**, behind a lazy
   import, because the cycle its old comment named is real.

**And the neutrality pass turned up a live progression bug.** Reviewing the audit's
own warning — "branches on item class 'Junk' … the Python class name, not the
family" — showed that **three of `fantasy_frontier`'s five item grants had never
fired**: `Gem`, `Junk` and `Treasure` are families whose class the engine retired,
so an item built from one reports `Item` and only the generic material rule (8 XP)
could match. Gems paid a material's XP, and the ledger's "A stone worth
cataloguing." had never once been shown to a player. Item instances now carry the
family their template declared, `match.item_family` narrows a grant, fantasy's five
rules name families, and the gate now *errors* on a class-name match that can never
match (with `item_family` in the message) rather than only warning about four
curated names. New checks: `test_faction_dispositions.py` (18),
`test_npc_behavior_vocabulary.py` (7), `test_advancement_item_families.py` (8),
including two tripwires — no inline faction comparison may reappear in the engine,
and the declared behaviour list and the dispatch table may not disagree.

**Still unclaimed in this area:** weapons and armour pay no item XP at all in
fantasy (25 weapon and 32 armour templates, no rule matches them). That is a
balance decision, not a defect — the ledger records the find and pays nothing,
which the design allows on purpose — so it stays for playtesting.

---

## 6. The editor manages a game's lifecycle — ⏭ **start here**

**Replanned 2026-09-21.** This is the canonical execution order for P10. Read the
[game-authoring roadmap](game-authoring-roadmap.md) for the end-to-end journey,
milestones M0–M5, coverage inventory and the late-crafting-overhaul example. Read
[editor-readiness](editor-readiness.md) for the current code-review addendum and
dated historical audit. Do not interpret the older “12 of 21 CRUD” count as a
current completeness measure, or new configuration forms as finished workflows.

Deliver these as cohesive batches, each including implementation, negative-path
tests, documentation and a specific human retest. Owners below are responsibilities,
not an instruction to split the batch across agents.

| Order | Batch / milestone | Scope and exit evidence | Owners |
|---|---|---|---|
| **6A — active** | **Safe configuration edits (M0)** | First hardening slice landed 2026-09-21: signal/refresh wiring, typed edits, draft lifecycle, staged engine validation and atomic single-file saves with backups/conflict checks. Next: visual/error-layout retest, exhaustive field/default coverage, teardown cleanup and async validation for large sets. See [current safety behavior](../reference/configuration-editing-safety.md). M0 is not yet closed. | G + B; H/I prove |
| **6B** | **Project setup and change foundations (M1)** — *spec below* | Scaffold/manifest/start/opening coherence, minimal vs copied starter semantics, capabilities/ruleset reconciliation. Build engine-known dependency index, “used by,” refactor preview, external-change detection and recoverable multi-file staging. Gate: fresh authored set boots, used-ID deletion is caught, interrupted apply recovers. | G + B/C; F first user |
| **6C** | **Fantasy materials-to-outcomes (M2, first slice)** | Resources, families/profiles/distributions, items, loot/yields, stations, recipes, work, relevant skill/policy fields. Harden existing forms rather than adding duplicate editors. Gate: author changes a gather → craft/work → use route, samples generation, saves/reloads and plays it; no hidden nested-field rewrite. | G + B/E; F/H/I |
| **6D** | **Fantasy actors, progression and flows (M2, remainder)** | NPC behavior/social/vendor/schedules; combat/ability configuration; quest rewards/campaigns/dialogue/knowledge; backgrounds, advancement, collections/discoveries; remaining world/policy/presentation fields. Work from the [field-level coverage ledger](editor-coverage-ledger.md) and preserve district editing/continuity. Gate: complete fantasy inventory and representative authored journeys, with exceptions explicitly still open. | G + B/E; F/H/I; K campaign boundary |
| **6E** | **Contrasting consumers (M3)** | Small editor-authored orbital repair/device/resource proof, night-shift consequence/access proof, modern non-progression interaction. Do not build new full games or force absent systems on. Gate: new generalizations work in two themes; all four existing sets boot. | F/G + B/E; H/I |
| **6F** | **Established-game overhaul (M4)** | Extend 6B's reference/transaction foundation to semantic impacts, versioned change plans, generated-item and active-job compatibility. Rehearse the crafting overhaul: apply, abandon, interrupted apply and rollback. Unsupported old-save conversion requires an isolated fresh-save revision, not silent data loss. | B/C/G + E; H/I |
| **6G** | **Authoring release candidate (M5)** | Reproducible export/checkpoint, compatibility and validation reports, clear warning acknowledgments, clean-install journey, human usability/accessibility and large-world performance/recovery passes. Gate: another person can create/edit/test and play the candidate using the documentation. | G/C/J + F/H/I |

**Dependencies:** 6A → 6B → 6C → 6D → 6E → 6F → 6G is the default queue.
Carry the second-theme and migration fixtures into 6C/6D to expose bad assumptions
early; 6E/6F are completion gates, not the first time those risks are considered.
Do not postpone dependency indexing until every destructive control already exists.

**First 6A evidence (2026-09-21):** the callback mismatch, numeric short-label map,
work-ID delimiter and dropped blank entries have been addressed. New dialog tests
exercise real signals, exact unrelated-field survival, tiers, discard, conflicts,
malformed shapes, and Main's Ruleset request/save/dirty-state route. Python tests
exercise the staged engine verdict and failure paths. The runner now fails on a
Godot script error even with exit code zero. This is not evidence that every
configuration field is journey-proven; keep the remaining M0 gates open.

### 6B — Project setup and change foundations (M1)

**What.** Four deliverables, in this order. The first two are the reason the batch
exists; the last cannot be honest without them.

1. **A reference index, built from the engine's own readers.** The gate already walks
   six reference families and knows which files each may appear in
   (`toolkit/reference_integrity_validator.py:582-592` — items, npcs, abilities, rooms,
   collections, recipes). The editor needs that same walk **in reverse**: id → the files
   and JSON paths that name it. New `toolkit/reference_index.py` emits
   `{id: [{file, path, family}]}` for one set, consuming `REFERENCE_FAMILIES` rather
   than re-deriving the shapes, so the index and the gate cannot disagree about what a
   reference is.
2. **"Used by" in the inspectors, and a refusal instead of silence on delete.** Today
   `DatabaseManager.delete_entry` (`:647-656`) removes the entry and marks it dirty, and
   `rename_entry` (`:593-613`) renames the cache key and patches *nothing* — for five
   types only (npc, item, magic, quest, template). The one repair path that exists
   covers room ids in `exits` (`RegionManager.gd:247-289`) and does not touch content
   references to a room — an NPC schedule, a title's guild `place`, a quest's
   `spawn_on_entry.room_id` all keep pointing at the old id.
3. **A change preview before applying.** Rename and delete show the referrer list with
   paths and offer patch / leave / deprecate per family; the write waits until the author
   has seen it. This is M4's rehearsal shape, single-set and unversioned — enough to make
   6C/6D's new rename/delete paths safe without pretending to be a migration system.
4. **The project lifecycle half.** Register a content set outside `content_sets/`, rename
   and delete a set behind a typed confirmation that names the path and the file count,
   and edit an existing manifest's `capabilities` and `start` (creation-only today).
   Manifest edits stay single-file and go through the staged engine verdict that
   `ConfigurationSave.gd` already uses.

**Why now.** The ledger's §J puts it plainly: 6B is the batch that stops destructive
controls existing before the index does. Every family the ledger marks *prototype* gains
a rename or delete path in 6C/6D, and without the index each one deletes silently. The
reference facts are already written, tested and green — so this is a re-projection of
what the gate knows, not a new validator.

**Depends on.** **B** for field-level ownership: the index may only claim a reference the
engine resolves, so any family the readers do not actually consume stays out (the ledger
lists several). **C** for the write protocol: a multi-file apply needs a journal and
external-change detection, and `ConfigurationSave.gd` is the single-file precedent to
generalise. **H/I** for fault injection — "an interrupted apply recovers" is a claim that
needs a test that interrupts one.

**Done when.** (a) a used identifier cannot be deleted without its referrers being shown;
(b) renaming an item, recipe, ability or NPC patches every index-known referrer or names
the ones it deliberately leaves, and a test asserts both directions; (c) an interrupted
multi-file apply leaves the previous coherent set, proven by fault injection rather than
by reading the code; (d) a set outside `content_sets/` can be opened, renamed and deleted
from the editor; (e) the three gates stay green and the four-set byte round trip stays
empty.

**Risk.** The index becomes a second opinion about what a reference is — the exact defect
class this project keeps paying for. The mitigation is structural: it consumes the gate's
`REFERENCE_FAMILIES`, and it never decides whether a reference is *valid*, only where it
is. Second risk: patching references rewrites files the author never opened, so it must
use the same stripper and verified writer as a normal save (precedent:
`RegionManager.gd:283-289`) and must never rewrite a file it could not parse.

**First 6B evidence (2026-09-21).** Deliverable 1 is built and the first half of
deliverable 2 is wired:

- **`toolkit/reference_index.py`** — the reverse of the gate's sweep, sharing
  `REFERENCE_FAMILIES` *and* a new `reference_tables()` in
  `reference_integrity_validator.py` (extracted, not copied) so the index and the
  gate cannot disagree about what a reference is. `--json` for tools, `--id <id>`
  for "what names this", and a readable report that ranks the ids a rename would
  touch — `item_healing_potion_small` in the reference set is named 12 times across
  recipes and three NPC files.
- **The index states its own coverage** in the payload and in the report: the six
  families it reads, and the bindings it does not (room placements and exits,
  dialogue bindings, guild places, quest spawn rooms, contract references), so an
  empty answer cannot be read as "unused".
- **`mud-world-editor/scripts/data/ReferenceIndex.gd`** runs it, caches it per set,
  and phrases it; **the delete confirmation now names the referrers** before an
  entry goes (`Main._confirm_delete_db_entry`), and the cache is cleared when the
  set changes. A failed run says the check did not happen rather than reading as
  "nothing refers to this".
- **Evidence:** `server/tests/singles/test_reference_index.py` (10 tests, parity
  with the gate on one fixture) and `mud-world-editor/tests/reference_index_smoke.gd`
  (a real recipe and a real vendor line found in two different files). The parity
  test was falsified by pretending the index never learned the `items` family: four
  sub-tests fail.

**Third piece, the same day — the manifest is editable after creation.** 6B's own gate
asks for "changes its start and one capability safely, saves/reopens, and boots the new
start", and until now the manifest was written once by the scaffold and never again.
`ManifestEditorDialog` + `ManifestDraft` now edit the title, the start (scenario, region,
room) and the capability set, through the same staged engine verdict the other
configuration dialogs use — `configuration_save.py` gained the manifest as a supported
file, and checks the *draft's* `paths` for escape rather than only the file on disk,
because a draft that moves its own paths would make the staged validation read another
tree. Deliberately not offered: the `id` (the directory name, and the identity saves are
partitioned by) and `paths`.

The evidence is the interesting part: `manifest_editing_smoke.gd` (33rd editor check)
asserts that an unrelated edit preserves every field the form does not show, that
dropping a capability the ruleset enables is refused **by the engine with the form raising
no objection**, that a title save keeps a `.bak`, and that a start room the set does not
have is refused while the draft is kept so the author can fix it.

**Fourth piece, the same day — a set can be renamed and removed.** The last of 6B's
project-lifecycle half, and the first pair of actions in the editor that cannot be
undone. `ContentSetAdmin` does the work and owns the refusals; the content-set chooser
owns the asking:

- **Only inside the sets root.** The editor lists sets beside the checkout and removes
  only what it lists; a set opened from elsewhere is refused rather than
  half-supported (external roots are still unbuilt, and the message says so).
- **Nothing without the name typed.** The delete prompt shows the file count and the
  size and asks for the directory name back; a rename is pre-filled with the current
  name so an accidental Enter is not a rename.
- **The directory and the manifest id move together.** A rename that cannot rewrite
  the id reports exactly that, rather than a clean rename with a disagreeing manifest.
  Existing saves carry the old id and the prompt says they will refuse to load.
- The open set is refused by the UI, not by the admin layer: that is a fact about the
  editor's state, not about disk.

**Evidence:** `content_set_lifecycle_smoke.gd` (34th editor check) works entirely in a
scratch parent under `tmp/` and tests the refusals more than the actions: a directory
without a manifest, a set outside the sets root, an empty allowed-parent, a partial
typed name, an id the engine would reject, an id another directory holds, and the same
name twice — each followed by "the set is still where it was". Then the rename, and a
delete asserted to remove *exactly* the files its report promised.

**Fifth piece, the same day — a failed save puts the set back.** M1's other gate line
is "a failed multi-file apply recovers the previous coherent set", and the editor had
the ingredients without the guarantee: every individual write is atomic and verified,
but `save_all()` rewrites a dozen files one at a time, so a failure on the fourth left
three new files beside an old rest. `SaveCheckpoint` copies the set's `data/` tree
before the first write (610 KB, 92 files for the reference set — small enough that the
whole tree is the honest unit), and `Main._save_everything` restores it on any failure
before reporting.

Two decisions worth keeping:

- **Restore replaces rather than merges.** A file the failed save *created* has to go
  and a file it truncated has to come back whole, so the checkpoint carries the tree
  and a restore refuses a checkpoint belonging to a different set.
- **The in-memory caches are deliberately not rolled back.** The author's work stays on
  screen and stays dirty, so the fix is to save again; the message says whether the set
  was restored or whether restoring also failed, because those need different next steps.

Checkpoints live under `<set>/editor/checkpoints/` (editor state, pruned to the newest
three, now in `.gitignore`), and `content_set_scaffold_smoke.gd` was tightened rather
than loosened when it noticed them: it now asserts that no *content* file was invented
**and** that the only files a save adds are its own recovery state.

**First 6C evidence (2026-09-21).** The two families the ledger listed as `absent` in the
item family — the ones an author tunes a distribution with — are authorable:

- **Affixes** (`data/items/affixes.json`, 14 prefixes + 13 suffixes in the reference set)
  and **item sets** (`data/items/sets.json`) were the only content files the editor never
  loaded, deliberately: an old save rewrote `affixes.json` from the *items* cache and
  deleted its string-valued keys. They are now loaded as themselves —
  `DatabaseManager._load_affixes`/`_load_item_sets`, their own caches, never the items
  cache — with `AffixInspector` (types, level floor, modifiers, worn stats, value
  multiplier) and `ItemSetInspector` (members with a "does this item exist" marker,
  per-count bonus tiers) and the library's *Prefixes*, *Suffixes* and *Item Sets*
  categories, which until now were grouping labels over unrelated files.
- **The corruption is now pinned, not avoided.** `affix_and_set_authoring_smoke.gd` (36th
  editor check) edits an affix and a set and asserts the generator's string keys survived
  the save, that untouched entries are untouched, that a no-op save is byte-identical, and
  that a set with neither file does not grow one merely by being opened and saved.

**Two things the gates caught while landing it**, both worth more than the feature:

- The editor was *inventing* `affixes.json`/`sets.json` in the three sets that have none —
  the rule that keeps it from creating `magic/` or `quests/` for sets that lack them
  applies here too, and now does.
- Those two files were the only content files not in `SaveIO`'s byte form (2-space
  indentation, CRLF, `2.0` where the editor writes `2`), because they were the only ones
  the editor never wrote. The round-trip gate said so immediately; they are normalised,
  and the check is green again.

**Latest 6B safety hardening (2026-09-22).** The rename review is now a
preflight, not merely a report: every indexed library or region path is tested on
a copy before the first real reference changes. A path that is stale, malformed,
unparseable or would collide blocks the entire rename and names the failing path;
it cannot leave the earlier references half-repaired. Deleting an entry that has
indexed referrers is now refused rather than confirmed with known breakage. The
ordinary **Save Changes** path also runs the open-set engine validator after
writing region/library content. A rejection restores the checkpointed `data/`
tree and keeps the editor's visible data dirty for correction. Configuration
drafts retain their own staged single-file protocol. This is deliberately not a
general multi-file refactor transaction yet: it does not cover unindexed bindings
or external roots, and config plus library edits are not one combined commit.

**Still open in 6B:** rename/delete previews and repair dispositions for every
engine-known reference family, an actual all-file refactor transaction, and external
content-set roots. **Still open in 6C:** node yields, container contents, the nested item
properties the panel will not write, and station pickers.

**Second piece, the same day — rename repairs what it can reach.** The ID field in an
entry inspector no longer renames in place: it asks (`DatabaseInspector.request_entry_rename`
→ `InspectorController` → `Main._on_request_entry_rename`), and the answer is the
index's referrer list split in two:

- **Repaired automatically:** references held in the loaded library caches. New  `ReferencePatch.gd` walks an indexed path and edits it — value mode
  (`merchant.properties.work_location`) or key mode
  (`spawner.monster_types.giant_rat`, where the walker spells a keyed reference by
  ending the path with the id). A key rename rebuilds the dictionary in place, so
  the renamed key keeps its position and the byte round trip still passes.
  `DatabaseManager.patch_reference` resolves which cache owns the path, and the
  whole rename is one `cmd_proc.commit`, with the undo built from the paths *after*
  the patch (`path_after`), because a key rename moves the path.
- **Also repaired, since the same day: region files.** The index now reports a
  reference's **JSON path** as well as its human label
  (`reference_json_path()` in the validator — region labels name the room or the
  spawner field without the container the file nests it under, and that is spelled
  out per family rather than guessed, because it feeds a writer). `RegionManager.patch_reference`
  then patches a spawner weight or a locked door: in memory when the region is the
  one the editor has open (so unsaved edits survive and the normal save path writes
  it), or read-patch-write with the same stripper and verified writer when it is
  another file. A file that cannot be parsed is never rewritten.
- **Evidence:** `reference_index_smoke.gd` now drives the real content — it reads the
  recipe that produces `item_patch_kit`, renames it through `DatabaseManager`, and
  asserts the loaded recipe *and* the vendor line that sells it both follow; it
  plants a spawner weight in a copied region, sees the index report
  `spawner.npc_types.<id>`, and renames it both on disk and in an open region. Plus
  the refusals: an id the path does not hold, a path that does not exist, a key
  rename onto an existing key, an entry that is not loaded, an unparseable region
  file left byte-for-byte alone, and a region file that is not in the set.

### Shared rules for 6A–6G

**Shared completion rule:** the engine defines schemas, runtime semantics and
validation; the editor consumes them. Unsupported sections remain read-only with
a reason. Surface status advances from prototype → validated writer → journey-proven,
never directly from “dialog exists” to “complete.” Tests must exercise the new
control/save path as well as the old fixture writers. Existing round-trip,
switching, open-set validation and release-gate work should be retained and extended,
not re-created from the historical gap list.

**Stop at 6G for this push.** This prepares an authoring-beta / test candidate,
not arbitrary engine scripting, hot migration of a live world, collaborative
editing, marketplace publishing or full commercial readiness. Broad content growth
and balance tuning remain later; the small proving content in each batch is required.

---

## Decisions that gate chunks

**1. The clock anchor — ✅ DECIDED 2026-09-19.** The answer turned out to be
neither (a) nor (b) as written, because both assumed the question was about the
*save*. It is about the **process**:

> "If everything is a server, even when single player, then the world time advances
> continuously for as long as the server is up."

So: `game_time` advances with the server's uptime, with or without sessions. It
does **not** advance while the process is stopped, and a save resumes from the
`game_time` it recorded — no wall-clock stamp, no catch-up, and
`TIME_MAX_CATCHUP_SECONDS` stays irrelevant. A single-player session is a server on
the player's own machine, so it is the same rule rather than an exception.

**This was already wrong in the code, which is why it was worth deciding.** Both
`_run_background_ticks` loops read `if not active_session_ids: continue`, so the
world advanced *only while somebody was connected* — under option (a)'s failure
mode, and invisible in play because the disconnect and the freeze happen together.
Fixed; `test_world_time_is_continuous.py` (13 tests) holds it, and the tests were
confirmed to fail against the old `continue`.

What this settles for authors, recorded in full in
`docs/design/duration-primitive.md`:

- A duration is real elapsed time **while the server runs**.
- A brew finishes while a player is logged out, if the server is up. Three days is
  three days of server time, not three days of play.

**2. Is `modern_capsule` a vignette or a game? — ✅ DECIDED 2026-09-20: a
vignette.** `progression_model: none` is deliberate, and the flyer's promise is
answered in dialogue rather than with a reward loop. What landed:

- The set's first `data/dialogue/` content — two graphs, one per existing NPC.
  **Maya** explains the neighbourhood (where the noticeboard is, who runs the
  electronics table, and the one rule about the library's shelf of left things);
  **Devon** runs the table, and the conversation with him has a real outcome:
  `take_item` the broken desk lamp, `give_item` the mended one, `set_flag` so the
  second visit remembers the first. Those three effects are the whole mechanical
  vocabulary the set needs, and it needs none of the systems it switched off.
- Two props so the scene has something to be about: the flyer on the library bench
  now says what to bring, and a broken desk lamp sits on the library lobby's
  "free to a good home" shelf — the shelf Maya tells you about, and the thing
  Devon's opening reply is gated on carrying.
- The exchange is written as *speech*: the dialogue renderer quotes node text, so
  narration inside a node reads as the NPC saying it. The hand-over is carried by
  Devon's line plus the effect message rather than by prose that pretends to be
  dialogue.

**Why a vignette and not a game:** the engine's claim to be content-neutral is
best served by a set that is not fantasy *and* not a levelling treadmill — five
rooms, two people, no combat, no economy, no crafting, and still something a
player can finish. Turning progression on would have made it a fourth
half-finished game, and the flyer's "this Saturday" is a *scheduled event*, which
the engine still has no shape for (it is in F's contract-gap list). The vignette
answer needs no primitive.

**New check:** `test_modern_capsule_repair_cafe.py` (5 tests) plays the whole
thing and asserts, in the same file, that quests, crafting, combat, magic,
abilities and economy are all still off and the player still has no progression
when it is over. The set's opening briefing was rewritten to walk a new arrival
into the scene (Maya → the flyer on the bench → the shelf in the lobby → Devon),
because a vignette nobody finds is a vignette nobody plays.

**3. Does world time advance with zero clients?** Folded into decision 1: yes.

**4. How does a player get better? — one of the three already exists, and the
real defect is the curve.** Measured 2026-09-19, prompted by the question of
whether to raise stats on level-up, by practising a craft, or through a trainer.

* **(a) Stats on level-up — already shipped.** `progression.level_up()`
  (`engine/player/progression.py:78-82`) adds `PLAYER_LEVEL_UP_STAT_INCREASE` (1)
  to **every** numeric stat, and the comment there records the deliberate choice
  that which stats grow is the content set's business, not six hard-coded names.
  `advancement.curve` in the ruleset already lets a set pace its own levelling.
* **(b) Skill in use — also shipped.** `SkillSystem.practice_check` trains on
  every check (more on success than failure), and the skill check is
  `roll + skill_level + stat_bonus` against a DC, so skill and stat both feed it.
* **(c) A trainer — not built, and not blocked.** `SkillSystem.grant_xp` is the
  explicit hook a trainer would call for a fee. What does not exist is an NPC
  kind that sells it.

**So the choice is not which of the three to build — it is whether to build (c)
at all, and the curve has to be fixed either way.** The arithmetic is the reason:

| | |
|---|---|
| Cost of skill 20 | **664,843 cumulative XP** (the curve is `100 × 1.5ⁿ`, `skill_system.py:7-8`) |
| Earned per practice check at DC 12 | 6 XP on success, 2 on failure |
| Therefore | **~110,807 successful actions** to reach skill 20 |

Meanwhile the check value grows *linearly*: +1 per skill level against a cap of
100. An exponential price for a linear benefit is the actual defect, and it has
teeth — `ruleset.json:171-176` gates concealed-tool jail escape on `stealth` and
`lockpicking` at **minimum 20**, so the gate is unreachable by design rather than
by difficulty.

**Recommended, in this order:**

1. **Make the skill curve content-authored and roughly linear**, so skill *N*
   costs about *N*×100 (skill 20 ≈ 21,000 XP ≈ 3,500 successes). The engine
   already has the pattern: `advancement.curve` lives in the ruleset. `100 × 1.5ⁿ`
   is in `skill_system.py` as a module constant, which is the same "a rule in the
   engine" shape that the cross-theme work exists to remove.
2. **Then decide (c) on its own merits, as an economy decision.** A trainer selling
   *skill levels* competes with practising the skill; a trainer selling *stat
   points* competes with levelling. Both are defensible, but neither fixes the
   curve, and building one first would disguise an arithmetic bug as a design
   choice. The design question to answer is which of time and gold buys skill —
   the engine currently supports "time", via `practice_check`.

**5. Who owns the content-set manifest — ✅ DECIDED 2026-09-19.** The engine does.
`content_set.py` is what refuses a set, so the required strings, the eleven
capability names and the three required data directories are its list; the editor
holds a **copy** in a table a parity check keeps equal to the engine's, the same
arrangement already accepted for condition kinds, effect kinds and objective types
(`toolkit/engine_vocabulary_dump.py` + `schema_parity_smoke.gd`). The alternative —
reading the list from Python at create time — was refused because creating a set
would then need an interpreter beside the editor, and because the copy is not the
risk: an *unchecked* copy is. What makes this decision cheap is that
`EngineValidator.run` already validates the manifest the editor just wrote, so a
set that a parity check let through still meets the engine's verdict immediately.

**6. An in-game authoring tool — ✅ PARKED 2026-09-19.** G7 proposed a spike to
decide where an authoring tool lives now that `tools/` is gone. Refused for now,
with the reason recorded in the deferral ledger: the editor is the authoring
front-end and `toolkit/` is the validation surface, so a mod-plugin tool has no
named consumer. The spike would answer a question nobody is asking, and the
plugin surface's absence is only a gap if in-game tooling is wanted — which is a
product decision, not a missing primitive.

---

## What is deliberately not scheduled

- **Economy and skill-curve tuning.** Blocked on human playtesting, which blocks
  four decisions in `ROADMAP.md`. No chunk substitutes for it.
- **Faction and territory work.** A system with no consumer; already refused once.
- **Additional full content sets.** Use the four existing sets as proving slices;
  `modern_capsule` intentionally remains a vignette.
- **The field grid.** First it needs a decision: give cells a world, or delete the
  system. It is currently persisted, client-rendered, and connected to nothing.
- **In-game tooling ownership.** `tools/` was deleted; no track owns player-facing
  tools or a plugin surface.

---

## If you only do one thing

**Chunk 6A.** Prove the real configuration edit/save/reopen paths before expanding
them. The editor already authors substantial content and runs validation; the
remaining problem is trustworthy end-to-end coverage, not starting from nothing.
Then follow §6 through game setup, fantasy coverage, contrasting consumers,
safe overhaul and a test candidate. Scope: [game-authoring roadmap](game-authoring-roadmap.md).

*(Was chunk 1 — nine small defects, one of which could destroy a player's character.
Those are fixed and gated as of 2026-09-19.)*
