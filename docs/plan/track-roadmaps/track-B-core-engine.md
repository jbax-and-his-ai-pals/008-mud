# Track B — Core Engine

## Assessment

**State.** Five modules own the vocabulary: `contracts/registry.py` (eight sections in
`CONTRACT_SCHEMAS`, `:160-183`), `contracts/schema.py` (a strict reader that refuses unknown fields,
`:166-172`), `contracts/equipment.py` (contract → authored property → default), `contracts/resources.py`,
`contracts/stats.py`. Both shipped sets declare all eight sections. The declarations the engine ignores,
verified by opening every call site:

| Declaration | Status |
|---|---|
| `item_families[].debug_only` (`registry.py:65`) | read by nothing. The three consumers (`items/instance_generator.py:244`, `items/chest_loot_generator.py:53,267`) read `template["properties"]["debug_only"]`, a different location. |
| `item_families[].label` / `.description` (`:52-53`) | authored by all 15 families across both sets; read by no runtime path. |
| `TIER_FIELDS.weight_multiplier` (`:74`) | written but read by nothing — size/quality rolls use `value_multiplier` and `score` only (`instance_generator.py:307-308`). |
| `TIER_FIELDS.weight` on `size_tiers`/`quality_tiers` | **inert.** `_roll_size`/`_roll_quality` (`:396-427`) weight from a hardcoded `canonical` curve and re-sample it by tier *count* (`_weights_for:133-156`). An author who retunes `weight` on a size band changes no roll. Only `rarity_tiers[].weight` is read, at `pick_template_id:254`. |
| `TIER_FIELDS.value_multiplier` on `rarity_tiers` | read by nothing. |
| `ABILITY_FIELDS`/`EFFECT_PACKET_FIELDS` `label`, `description` | read by nothing. |
| `effect_packets[].kind` + `.payload` (`:151-157`) | **the largest.** `kind` is `required: True` and authored by both sets; `registry.effect_packet()` (`:455`) has zero call sites in the repo. The whole section is parsed, reference-checked for `resource` only (`:434-439`), and otherwise unused — all magic behaviour comes from `spell.effects` via `magic/effects.py:48,81`. |

**Strongest.** `contracts/equipment.py` is the pattern this track should keep: one rule
(`contract first, authored property second, engine default last`, `:11-16`), applied to four readers, with
the template/family fallback in one place (`profile_for:55-77`). `contracts/resources.py` shows the same
discipline after the fact — its own docstring (`:19-25`) records `label`/`short`/`max_stat` as fields that
"were declared from the beginning and read by nothing", and they are read now (`ability_resource_short`,
`pool_for`, `regenerates` at `player/core.py:288`). `stats.py` is the model for the next primitive: a role
vocabulary resolved by content with a neutral engine fallback (`STAT_ROLES:42-51`).

**Weakest.** Reference resolution validates *existence* and nothing else. `_resolve_references`
(`registry.py:388-439`) checks that a named profile, resource, family or packet exists; it never checks a
*value*. So `DEFENSE_PROFILE_FIELDS["material"]` (`:130`) is read by `equipment.armor_material`
(`:128-133`), consumed at `game_object.py:146` as
`WEAPON_VS_ARMOR_MULTIPLIERS.get(weapon_damage_type, {}).get(defender_material, 1.0)` — an unvalidated
free string whose only failure mode is a silent ×1.0, i.e. armour that does nothing. The same shape is in
`ATTACK_PROFILE_FIELDS["damage_type"]` and `EFFECT_PACKET_FIELDS["resource"]`, neither of which is
checked against `combat/elements.json` or the declared resources. `ARMOR_MATERIALS`
(`config/config_combat.py:44`) is the list that would close the first one; it has no consumer anywhere in
the repository. `SPELL_EFFECT_TYPES` (`:62`) and `WEAPON_DAMAGE_TYPES` (`:43`, imported only by
`toolkit/reference_integrity_validator.py:784`) are dead or gate-only.

**Surprises.** (1) **A clock that already does what the duration design asks for exists.**
`server/engine/core/clock.py` is an injectable `Clock` of *absolute* timestamps (`now()`/`advance()`),
deliberately for "cooldowns and expiries set once as `clock.now() + duration` and later compared against a
fresh `clock.now()`" (`:6-9`), used by jail sentences (`core/crime_manager.py:156`), summon expiry
(`magic/effects.py:230`), NPC respawn (`world/respawn_manager.py:27`) and `world.update`
(`world/world.py:260`). `docs/design/duration-primitive.md` says "everything else with a 'later' in it
needs the calendar" while overlooking this. (2) **Environment is already a half-primitive.**
`Room.env_properties` (`world/room.py:22`) merges into `properties` (`:31`), `World.get_env_property`
(`world/world.py:783-816`) resolves room → district → region, `dark` is authored across ten fantasy region
files, and it is *validated* only by accident: `room.update_property("env_properties", ...)` means
`room.get_property("dark")` returns `None`, so the resolution silently continues to the district tier. The
sole consumer is prose (`world/description_generator.py:51-57`). The mechanical consumer is a *separate*
hardcoded property, `hazard_type`, ticked per-tick on `world.clock` and applied at `player/core.py:271`.
(3) `PLAYER_MANA_LEVEL_UP_MULTIPLIER` and `PLAYER_MANA_LEVEL_UP_INT_DIVISOR`
(`config/config_player.py:53-54`) are read by nothing.

**Verdict on `docs/design/duration-primitive.md`.** The right half is right: absolute `started_at`/
`ends_at` and evaluate-on-read is the design, and there is no `timers` property anywhere today. Four
problems to fix **before** it is written. (a) **The persistence claim is false as written.**
"No new persistence shape" (`:219-220`) holds for items (`utils/utils.py:56-135` diffs instance properties
against the template, so a `timers` key survives) but not for rooms — `world/save_manager.py:51-54` saves
only `dynamic_*`/`instance_*` regions, and `:192-197` clears every static room's items on load — and not
for world state, which has no store in the save dict at all (`:79-92`). A drying rack in a static town room
is the stage-1 demo, and its timer dies on reload. (b) **It anchors to the wrong clock for the verbs it
names.** `TimeManager.game_time` (`core/time_manager.py:51,64`) is the right anchor for "how long until the
barrel is worth something" — persisted, scaled by `TIME_REAL_SECONDS_PER_GAME_DAY`, and already the anchor
`respawn_days` uses — but `ResourceNode._day_number` (`items/resource_node.py:200-202`) reaches it through
`world.game.time_manager`, a `GameManager` attribute that headless test worlds do not have. A primitive
needs an accessor that works with no `GameManager`. (c) **The condition table (`:129-136`) is over-built
for v1.** `season`, `time_of_day` and `requires_present` each need a consumer; the adopted two-theme rule
already says the second consumer is orbital, and `core/time_manager.py:122` hardcodes
`["winter","spring","summer","fall"]` by month index, which an orbital calendar has no meaning for.
(d) **`duration_days` vs `duration_seconds`** is listed as open (`:228-231`) and is not open — it is the
one decision that must be made in the contract, and `respawn_days` already proves days-as-sugar is
lossy (`int()` truncation at `resource_node.py:85`).

## Proposed roadmap

### 1. Contract hygiene: every declared field either has a reader or is deleted

**What.** Give `CONTRACT_SCHEMAS` an owner per field. Delete `TIER_FIELDS.weight_multiplier`,
`rarity_tiers[].value_multiplier`, `item_families[].debug_only` and `EFFECT_PACKET_FIELDS.payload`
outright. Either delete `effect_packets[].kind`, or give it the one reader that earns it: `equipment.
ability_numbers` (`:168-207`) resolving the packet's `kind` when the ability declares no cost/value —
that is the smallest consumer that makes the section real. Make `size_tiers[].weight` either honoured or
refused: the cheapest honest fix is to delete the field and document that a band's position in the list
is its weight, which is what `_weights_for` actually does. Smallest version: fields first, one commit.
**Why now.** This is the exact failure the whole initiative exists to fix — `resources.py:19-25` documents
this same class as already having happened once, and content currently believes four fields do something.
It is also a precondition for the duration contract, which will add four new fields and should not add
them to a schema that cannot tell a live field from a dead one.
**Depends on.** Track F to delete the now-refused keys from `content_sets/*/data/contracts/*.json`;
Track I to add the falsification test.
**Scope.** Small.
**Done when.** A new check enumerates `CONTRACT_SCHEMAS` fields and fails when one has no reader — the
"reader" list written by hand in the schema, and a test that fails when a field is added without one.
Concretely: deleting `size_tiers[].weight` from both sets changes no roll in
`test_instance_generator.py`, and that is asserted rather than assumed.
**Risk.** `label`/`description` on families and abilities are plausibly *editor* surfaces (Track G renders
controls from the same schema). They may be read by `mud-world-editor/`, which I did not inspect; keep
them if so, and say so in the schema comment rather than deleting a reader I did not find.

### 2. A world-time accessor and the world-value store the calendar needs

**What.** Two small things in B's lane. (a) `contracts/world_time.py`: `world_time(world) -> float`,
resolving `TimeManager.game_time` through `getattr` chains and falling back to a plain counter, so a
headless world with no `GameManager` still has a monotonic world clock; `ResourceNode._day_number` becomes
its first caller. (b) A *declared* world-value section — a `state` contract mapping a name to
`{kind: number|bool|string, initial, min, max}`, kept in a persisted dict on `world` — plus the reference
check that a `state` name referenced by content exists. One unit: seconds, with a days helper that does
not truncate.
**Why now.** Duration is unsaveable without (b) and untestable without (a). Every later item on this list
(world-state thresholds, "how long can you stay") needs the same store, and adding it now means adding it
once. The save-format change is Track C's; this item is the shape plus the read path, and it ships with
C's bump.
**Depends on.** Track C for the save field (a declared, versioned addition to `save_data`, migrated by
`world/save_format.py`). Track D for the content-file validation of `state` references.
**Scope.** Medium.
**Done when.** A world with no `game` attribute returns a non-decreasing `world_time`; a save/load round
trip through `save_manager` preserves a state value and a timer written to a static region's room; both
asserted in `server/tests/singles/`.
**Risk.** The store becomes "a dict anything can write", which is how content names leak into the engine.
The contract must be the only writer's vocabulary: content declares the name, the engine resolves it, and
an undeclared name is a refusal.

### 3. Duration: the timer property, four verbs, anchored to world time

**What.** `timers` as a property (a list of `{id, started_at, ends_at, work}`) plus a `work` contract
section, and exactly two verbs in v1: `start(entity, work_id, actor) -> timer` and
`resolve(entity, timer_id) -> {ready, seconds_left, outputs}`. No `sweep` verb in v1 — `resolve` on read is
the whole mechanism, and a sweep is a UI convenience (Track E). No `condition` map, no `duration_multiplier`,
no `requires_timer` in v1: those are the second and third consumers of the *same* four fields, and adding
them before the first consumer exists is how a primitive becomes a feature. Validation: `duration` positive
(mirroring the existing `base_duration` gate at `server/engine/server/content_set.py:2310-2315`), every
`inputs`/`outputs` item id resolves, and an unknown `work` id is refused by name.
**Why now.** It is the one the other tracks are waiting on, it has a precedent to generalise
(`respawn_days`), and item timers already survive a save (`utils.py:104-120`).
**Depends on.** Item 2 for a testable clock and a persisted home; Track F for the two consumers (`drying
rack` at `alchemy_table`, and a salvage-crate aging case); Track H for the reference/lazy-equivalence tests.
**Scope.** Medium.
**Done when.** Two themes declare work: `fantasy_frontier` dries herbs and brews a tonic through the
existing `brew_minor_heal` chain, and `orbital_salvage` ages a salvaged crate. A timer started at T reports
`seconds_left` decreasing linearly with `TimeManager.game_time`, is unchanged by advancing the world in one
jump versus many small steps (lazy evaluation is order-free), survives `save`→`load` from a static room, and
an unknown `work` id is a gate error naming file and field.
**Risk.** The verbs are command-shaped and will tempt Track E into `work_manager.py` with a tick loop. The
lane boundary has to be explicit: B resolves, E narrates.

### 4. Environment as a declared, validated value — not as `hazard_type`

**What.** The smallest version that is not a feature: promote the existing `env_properties` keys into a
declared vocabulary with types, defaults and allowed values, resolved through the deviation chain that
already exists (`world/world.py:783`). v1 keys: `light` (a level, not a bool — `dark` as a bool cannot
express a lantern) and `hazard` (the existing `hazard_type` plus its damage, moved from an untyped room
property into the declaration). Then one mechanical consumer each: light gates what a look/read returns,
hazard is the existing per-tick damage. Drop `temperature` and `atmosphere` from v1 — they are arguments to
this contract later, not separate primitives.
**Why now.** The vocabulary is already authored in ten fantasy region files and never mechanically read;
`hazard_type` is already validated against `combat/elements.json` (`content_set.py:441-455`), so half the
work is done. It is the primitive that unblocks "how long can you stay", which is duration × environment,
and doing it before duration means duration's first consumer is not a bespoke hazard.
**Depends on.** Item 2 if a suppressed hazard must survive a save (`room.active_env_effects` currently does
not). Item 3 for the stay-limit case. Track D owns `world/**` mechanics for the resolver; B supplies the
declaration and the shape. Track F authors orbital's first environment value — the station declares none
today.
**Scope.** Medium.
**Done when.** A room's `dark` and a region's `dark` both resolve through one reader; an undeclared
environment key in a room is a gate error naming the file; armour/hazard lookup tables take their
vocabulary from the contract instead of `config_combat.ARMOR_MATERIALS` being dead and
`hazard_type` being free text.
**Risk.** This is the item most likely to collapse back into "a special case for light". The test is that
orbital declares a key fantasy does not and both go through one code path.

### 5. Resource flow: capacity as a declaration, not a per-class property

**What.** The smallest real version: a `resources` extension — `capacity` (a number or an expression over
declared stats) and `replenish` (`{per: seconds, amount: n, requires: <declared name>}`), with two
consumers: the ability pool (`contracts/resources.py:124-160`, currently a hardcoded curve keyed on one
stat) and `ResourceNode.charges`/`max_charges`/`respawn_days` (`items/resource_node.py:204-230`, currently
four ad-hoc item properties with two different partial-recovery branches). A draw verb
(`draw(world, holder, resource_id, amount) -> granted`) so both report the same way.
**Why now.** After duration, this is the highest-value generalisation, and the deferral ledger already
refuses the alternative ("It wants a general **flow** concept on the resource contract"). It is also where
a second theme is free: orbital's charge pool and fantasy's herb bed are the same shape.
**Depends on.** Items 2 and 3 (replenishment is a duration). Track E owns the item classes that consume it.
**Scope.** Large.
**Done when.** `node_herb_bed`'s recovery is expressed by the contract rather than by
`respawn_days`+`depleted_day`+`last_partial_gather_day`, its behaviour is unchanged for every existing
test, and orbital declares a replenishing pool through the same path with no engine change.
**Risk.** This is a rewrite of a working mechanism with subtle partial-recovery semantics
(`resource_node.py:217-229`); the regression surface is the whole gathering path. Do it behind a
contract-first fallback, exactly as item 1's discipline requires.

### 6. Deadlines: a timer plus a condition, not a new manager

**What.** The `work` record of item 3 gains one field: `requires` (a condition in the existing
`engine/conditions.py` language). A timer whose condition was true at `started_at` and false at
`ends_at` resolves as failed rather than complete; the vocabulary for "failed" is a declared
`on_fail` output list, same shape as `outputs`. No new evaluator, no new manager.
**Why now.** "Contracts with deadlines" is named as a pending need and it needs *only* this: the deadline
is a duration, the obligation is a condition, and both exist. Adding it here keeps it out of Track E's
`crafting/**` as a quest-shaped special case.
**Depends on.** Item 3; Track E for the command surface and Track F for content that uses it.
**Scope.** Small.
**Done when.** A work declared with `requires` a condition that lapses produces the `on_fail` outputs, and
one that holds produces `outputs`; both asserted, with no new module in `engine/`.
**Risk.** `conditions.py` is player-scoped (`evaluate(condition, player)`, `:142`) with `KNOWN_KINDS`
frozen at `:44-49`. A condition about a room, a station or the world has no player to evaluate against,
so this item may be blocked on widening that evaluator — which is Track E's file, and would make it a
handoff rather than a small item.

## Explicitly not proposing

- **A bespoke power-grid or atmosphere system for `orbital_salvage`.** Already in the deferral ledger;
  item 5 is the generalisation it wants.
- **Unifying the stopwatch (`game_object.py:244-258`) and the calendar.** Already refused, and
  `core/clock.py` proves there are three clocks, not two — the argument for keeping them separate is
  stronger than the design doc states.
- **A save-format change authored by this track.** Item 2 needs one; `world/save_format.py` and
  `save_manager.py` are Track C's, so this is a shape request, not a commit.
- **Turning `damage_type` and `weapon_damage_type` into one field.** `equipment.py:91-115` deliberately
  keeps them apart and `reference_integrity_validator.py:669-675` records the 41-weapon false positive that
  proved they must stay apart.
- **Deleting `contracts/registry.py:490-512 status()` and `stats.py:182 roles_summary`.** They have no
  call sites, but they are the only read-out of what a set declares; wire one into an authoring command
  (Track E's surface) rather than deleting the only view of the contract.
- **Adding a second duration unit.** `duration_seconds` is canonical; a days helper is arithmetic.
- **Widening `conditions.py` myself.** Track E's file — filed under item 6's risk as a handoff.

## Risks

- **A contract with no reader is the failure this track exists to prevent, and item 3 is where it will
  happen.** `work` will be declared before Track E has a command for it. The mitigation is that item 3's
  "done when" names two content sets, not two consumer modules.
- **Item 1 deletes fields an unseen reader may use.** I searched `server/`, `toolkit/` and the tests; I did
  not search `mud-world-editor/`. A field deleted for the engine could break the editor's generated
  controls (Track G).
- **Items 2 and 4 both touch `world/**`, which is Track D's lane.** `get_env_property` and `Room` are D's
  to change; only the declaration and the resolver belong to B. Getting this wrong is the exception the
  work-tracks document says costs more than the handoff.
- **Lazy evaluation has an unbounded cost profile.** With no tick loop, `observe` is O(timers on the
  object) on every read, and `sweep` (deferred) is O(timers) whenever a container is opened. `ROADMAP.md`
  already records "no performance track" as a known structural gap. Neither of the first two consumers has
  enough timers for this to matter; a third might.
- **The persistence claim may be wrong in a way I could not test.** I read the save/load code but did not
  run a round trip. If `room_items_state` does not restore a static room's `ResourceNode` properties, then
  `respawn_days` is already broken today and item 2 is larger than described.

## Unknowns

- Whether `mud-world-editor/` reads the contract schemas directly for its controls. If it does, item 1's
  deletions are a Track G break, and `label`/`description` are load-bearing.
- Whether `TimeManager.game_time` is genuinely monotonic across load in every path — `initialize_time`
  (`core/time_manager.py:62-67`) is also called with defaults on a `None` state, which resets the calendar
  to midnight rather than preserving it. I did not trace every caller.
- Whether anything in `server/engine/server/**` or `client/` consumes `registry.status()`, which would
  make the contract already visible to an author somewhere I did not look.
- How the editor renders an `effect_packets` entry, and therefore whether deleting `kind` is a schema
  change or a schema *and* tooling change.
- Whether `modern_capsule` and `night_shift` could carry item 3's second consumer more cheaply than
  `orbital_salvage`. They are nearly empty, and I did not inventory them.
