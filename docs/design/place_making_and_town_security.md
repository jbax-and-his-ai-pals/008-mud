# Place-making and town security: design notes

Living design record for the postponed place-making slice (see ROADMAP.md).
This captures decisions made in conversation plus the engine facts that
grounded them, so the brainstorm survives between sessions. Update it as
decisions change; it is not a spec to build against verbatim until the open
questions are closed out.

Scope: player housing (with tiered, playstyle-branching expansion), a crime
and jail loop, a residential district, and a first pass at town guards. These
were designed together because housing motivates theft, theft motivates
guards, and guards motivate a district for them to patrol -- but each is
buildable as its own vertical slice once its open questions are resolved.

## Shipped: first slice (persistent single-player-house purchase)

A property agent (`property_agent`, at `town:player_house_exterior`, off
Residential Street) sells one house for 500 gold via a new `buy house`
command; the buyer receives `item_house_key_starter`, and the door
(`player_house_exterior`'s `in` exit) is locked to everyone else via the
existing `exit_requirements` mechanism. Implementation: `InstanceManager`
gained `build_region`/`apply_entry_exit`/`remove_entry_exit` (extracted from
`instantiate_quest_region`, which now calls them instead of inlining the
same logic), and `SaveManager.load()` now replays `apply_entry_exit` for
every restored dynamic/instance region. That replay is the fix for a real,
independently-confirmed bug: a quest instance's door onto its permanent
entry room was silently lost on every save/load round trip, because that
permanent room's (static) region is always rebuilt fresh from content-set
JSON before a save is loaded, and nothing ever re-applied the runtime
wiring afterward. A new `HousingManager` (`engine/world/housing_manager.py`)
owns house-specific behavior (ownership via `region.properties
["owner_player_id"]`, payment, key granting) separately from
`InstanceManager`, so it can't touch quest cleanup/abandonment code paths.

Deliberately scoped to exactly one house existing in the world: the offer's
`region_id` is a single fixed string, so a second buyer is turned away, and
every key made from the shared key template is interchangeable
(`ItemFactory` sets a created item's `obj_id` to its template id). Making
houses genuinely per-player -- unique region and key per owner -- is
follow-up work, not an oversight; flagged in code where it matters.

## Shipped: tier 2 (branching garden/pond expansion)

`expand house <garden|pond>` reflavors the house's interior room and
records `house_tier`/`house_branch` on the region (`house_tier` starts at 1
from purchase), gated on gold plus branch-specific materials
(`HousingManager.expand_house`, `engine/world/housing_manager.py`) -- the
same property agent, Cobb, doubles as the contractor rather than
introducing a separate NPC (a pure content move to split out later, not a
structural one). A new `house` command (`describe_house_status`) shows
current tier/branch and, near a contractor, the next tier's options --
the "look before you spend" step tier 1 didn't need with only one option.

Investigated wiring this through the quest system first, since the
contractor-delegation narrative ("fetch nails from the blacksmith, boards
from the wood shop") was the original framing below. Confirmed that's not
achievable with content alone: `QuestManager.complete_quest`/
`_grant_rewards` and `HeadlessServer.grant_party_rewards` only support four
hardcoded reward keys (`xp`/`gold`/`items`/`relationships`) with no hook
for an arbitrary side effect like a tier increment, even though the
NPC-delegation chain itself needs no new mechanic (`quest_missing_guard`
already proves fetch-from-A-then-deliver-to-B works). Built the direct
command instead (mirroring `buy_house`'s gold check, reusing
`CraftingManager.can_craft`/`craft`'s multi-ingredient check-then-deduct
loop for the materials cost) -- a real multi-stage delegated commission is
follow-up work once a quest-engine reward hook exists, not part of this
slice.

Not yet built: tiers beyond 2, whether a later tier lets a player pick up
the branch they didn't originally choose, chest locking, crime/jail,
districts, and guards -- everything else in this document below is still
just design, not implementation.

## Chest locking and lockpicking economy

### Shipped: slice 1 -- findable, lockable, randomized-content chests

Chests are now real: three material tiers (`item_chest_wooden`/
`item_chest_iron_bound`/`item_chest_gilded`, `content_sets/fantasy_frontier/data/items/chests.json`)
drop from five thematically "hoarder" hostiles (bandit leader, troll, river
troll, hobgoblin soldier, orc shaman), each with contents and lock
difficulty generated per-drop, not templated. `ChestLootGenerator`
(`engine/items/chest_loot_generator.py`) rolls the material and difficulty,
then 1-3 content slots across junk/currency/gem/equipment categories
(via `weighted_choice`), reusing three systems that already existed and
were tested rather than inventing new ones: `LootGenerator`'s level-scaled
affix rolls for equipment, the gathering system's `material_quality_score`
convention for gems, and a new `roll_around` utility
(`engine/utils/utils.py`, `random.triangular`-based) for the "usually
expected, rarely a big swing" distribution shape nothing in this engine had
before. Every generated item also gets one more `roll_around` pass on its
own value, so quality varies recursively regardless of category. Opening,
looking inside, and taking items out all worked with zero new command code
-- `Container`'s generic mechanics (confirmed mature but never previously
exercised by any authored content) already handled it.

A locksmith (the blacksmith, doubling the role rather than a new NPC, same
scope pattern as housing) opens a locked chest for a fee via a new `unlock`
command, computed from lock difficulty and weight -- a placeholder formula,
not yet tuned. Selling a chest uses the existing flat 40%-of-value vendor
formula via Talia (now accepting `Container`) as an interim stand-in.

Caught along the way: dynamically discovering "any Weapon/Armor template"
for the equipment category surfaced `debug_items.json`'s test-only gear
(a "Debug Amulet" with +50 to every stat) into real loot, since nothing
had ever needed to treat that file as excludable before -- fixed by adding
a `debug_only` property flag to those templates and checking it wherever
this generator discovers pools.

### Shipped: general-store economy overhaul

`sell_handler` (`engine/commands/mercantile.py`) now supports a per-vendor
`sell_rate_multiplier` (falling back to the prior global 0.4 default for
every vendor that doesn't set one), a weight-only pricing branch for a
still-*locked* container (ignores its value/contents entirely, so it's
worth notably less than unlocking it first), and a universal `quest_item`
sale exclusion. Talia is now the general store: broadest `buys_item_types`
of any vendor (already extended to include `Container` in chest slice 1)
plus an explicit `sell_rate_multiplier: 0.2` -- worse than every other
vendor's implicit 0.4, exactly the "accepts almost anything, pays the
least" role the design called for. No new NPC, same reuse pattern as the
housing contractor and chest locksmith.

Found and reconciled in passing: two different "this is a unique quest
item" property flags existed in content (`is_quest_item`, `quest_item`),
neither read by any engine code. Standardized on `quest_item` (renamed the
one `is_quest_item` usage) rather than having `sell_handler` check both
forever.

Caught by the full test suite, not by design: nine pre-existing unit tests
across `tests/batch/` and `tests/singles/` spawned the `"merchant"`
template as a generic stand-in vendor and asserted the old flat 0.4 rate --
now that Talia genuinely has a different, lower rate by design, those
tests needed an explicit `sell_rate_multiplier: 0.4` override to keep
testing what they actually meant to test (the *default* rate), not
Talia specifically.

### Shipped: lockpick durability rework

`Lockpick` (`engine/items/lockpick.py`) no longer rolls a flat break chance
independent of outcome. It now carries a `durability`/`max_durability`
pool that only depletes on a **failed** pick attempt, with the loss scaled
by how badly the attempt missed (`max(1, abs(margin) // 10)`, a new
`LOCKPICK_DURABILITY_LOSS_DIVISOR` tunable) -- reusing the same "how badly
you missed matters" idea already established for perception's soft/hard
detection fidelity. A clean success costs nothing. Reaching 0 durability
destroys that specific pick instance. This required a new additive
`SkillSystem.attempt_check_with_margin` (a signed `total_score -
difficulty` alongside the existing pass/fail bool) sharing a refactored
score-computation helper with the unchanged `attempt_check` -- every
pre-existing caller of `attempt_check` was left untouched.

Durability inherently requires each pick to be a distinct instance, so
lockpicks are no longer stackable (matches how `Weapon`/`Armor` already
work); carrying three lockpicks is now three inventory entries. Durability
display needed no new code -- `Item.examine()` already prints any numeric
property not on its skip-list generically.

The crude/fine x bronze/steel matrix is real content now: four new
templates (`item_lockpick_crude_bronze`, `item_lockpick_crude_steel`,
`item_lockpick_fine_bronze`, `item_lockpick_fine_steel`,
`content_sets/fantasy_frontier/data/items/tools.json`) scaling durability
and price with tier, sold by the blacksmith (same locksmith-role reuse as
the chest-unlock fee) alongside the two pre-existing templates
(`item_lockpick`, `item_master_lockpick`), which kept their ids but moved
from `break_chance` to `durability`/`max_durability`.

Room-exit picking (`World.attempt_pick_lock_direction`,
`engine/world/world.py`) was a completely separate code path from
`Lockpick.use()` that never touched a `Lockpick` object at all -- it only
checked that *some* pick existed in inventory, then ran its own
`attempt_check`. Both `exit_requirements`-locked exits and `locked_by`-locked
rooms now capture the actual pick instance and call the same
`Lockpick.apply_wear()` used by chest-picking, so a pick used to open a
door wears down exactly like one used on a chest, rather than two
mechanics for one physical tool.

Caught along the way: `item_master_lockpick`'s old `break_chance` property
was nested under a `"properties"` sub-object in content, but
`ItemFactory.create_item_from_template` pops `"properties"` out of
`creation_args` *before* building constructor kwargs -- so that value
never actually reached `Lockpick.__init__`, and the master lockpick always
used the constructor's default break chance regardless of what the
template said. Moot now that `break_chance` is gone, but the general
lesson (template properties meant to reach the constructor must be
top-level keys, not nested under `"properties"`) is worth remembering for
future item templates.

### Shipped: chest traps and disarming

Chest generation now rolls a trap as a fourth independent draw
(`ChestLootGenerator._roll_trap`, `CHEST_TRAP_CHANCE`, a new tunable):
whether one exists, its kind (`damage` or `poison`, both reusing existing
engine primitives -- `take_damage()` for a direct hit, the same
`apply_effect()`/DoT shape already authored for poison weapons and
hostiles for the poison kind), and its own difficulty. Traps are hidden --
`Item.examine()`'s generic "show any numeric/string/bool property"
fallback (the same mechanism that shows `Lockpick`/`Weapon`/`Armor`
durability for free) got a small, reusable opt-out
(`HIDDEN_EXAMINE_PROPERTIES`) so a chest doesn't leak its own trap state
to `examine`.

`Container.trigger_trap(user)` is the single place a trap's consequence is
computed and applied; it's a safe no-op if nothing's armed, and spends the
trap (one-shot) the moment it fires. Every way a lock can be forced open
calls it the same way: trying to pick a trapped-and-undisarmed lock always
sets it off (`Lockpick.use()`), regardless of whether the pick roll itself
succeeds; the "Knock" spell going through `Container.magic_interact()`
does too (see below); and a bad-enough `disarm` failure does as well.

A new `disarm` command reuses the **lockpicking** skill exactly as
designed: it finds the trap by attempting to disarm it (no separate
detection step or skill), and a narrow miss fails safely and is retryable
(costs only lockpick durability, via the same `apply_wear` used
everywhere else) while a miss beyond `TRAP_DISARM_TRIGGER_MARGIN_THRESHOLD`
sets the trap off. Paying the locksmith (`unlock_handler`) safely defuses
any trap with zero risk as part of the fee -- real added value over DIY
picking on a trapped chest, on top of skipping the skill check entirely.

Found and closed along the way: a "Knock" spell already existed
(`content_sets/fantasy_frontier/data/magic/utility_spells.json`, wired
through `Container.magic_interact()`/`engine/magic/effects.py`) as a
genuine, already-live alternative to lockpicking -- undocumented by this
doc's earlier "spells... not building yet" framing. Left alone, it would
have been a zero-risk, zero-cost way to bypass any trap entirely. It now
triggers a trap exactly like manual picking does.

**Explicitly deferred:** a trap that permanently ruins the lock (unpickable
by anyone, including the locksmith). Noted below as an open question
rather than built -- what happens to a chest in that state (sold as a
total loss? a future spell-based retrieval path?) needs more thought
first. This was the last piece of the original chest-locking design list;
only that open question remains. Full original design below.

**The chest as an object:**
- Chests are portable loot items (not fixed furniture) -- picked up like
  any other item, not opened-in-place.
- A chest has its own intrinsic value from its *material* (a gold chest is
  worth a lot as an object), independent of whatever's inside it.
- A chest can be sold, still locked, to a vendor that accepts chests (e.g.
  a general store) via the existing `buys_item_types` vendor filter --
  priced purely by weight, deliberately much less than lockpicking it open
  and selling the contents separately. This exists as a fallback for a
  player with no lockpicking skill and no other money, not as a viable
  alternative to actually engaging the lock -- the return has to stay bad
  enough that it never out-competes picking or paying a locksmith.
- The general store more broadly should be the worst-rate vendor for
  *everything*, not just chests -- it accepts nearly any item (unlike
  specialist vendors) but always pays the least. Specialist vendors remain
  the better sale for anything in their specialty. Exception: unique quest
  items are never purchasable by any vendor, general store included.

**Contents:** generated at drop time, not fixed per template.
- A normalized distribution around a tier-appropriate expected value, so
  most chests land near what you'd expect for their level and only rarely
  swing well above or below it.
- Draws from systems already built: junk, straight currency, gems, and
  crafted/attachment-bearing equipment. No nested chests (a chest can never
  contain another chest).
- Whatever item type gets rolled is *itself* then quality-rolled the same
  way (a rolled gem gets its own good-or-mediocre quality roll; this
  applies generically to any generated chest item, not just gems) -- the
  same normalized-distribution idea applied recursively: first roll what's
  inside, then roll how good that specific thing is.

**Difficulty and traps:**
- Lock difficulty scales with level using the same normalized-distribution
  shape as contents -- usually near expected for the tier, occasionally a
  notable outlier in either direction.
- Traps are occasional. Difficulty (of both the lock and any trap) and
  whether a trap is present at all, and the contents roll, are four
  **independent** rolls -- a chest's difficulty says nothing about what's
  inside it or whether it's trapped.
- Disarming a trap reuses the **lockpicking** skill rather than a separate
  disarm skill, specifically so a player capable of picking a given chest's
  lock is never under-trained for a trap on that same chest -- no second
  skill to keep in sync.

**Access methods:**
- Lockpicking only, for now. Spells as an alternative unlock method are
  worth keeping in mind for later, not building yet.
- A locksmith opens a chest for a fee based on a formula combining its lock
  difficulty and (probably) its weight -- distinct from, and much more
  generous than, the general store's weight-only locked-chest purchase
  above. Exact formula constants are an implementation detail, not a
  design decision to settle here.
- Keys stay out of the normal chest loop entirely. The one place they'd
  earn their keep: quest/exploration-specific unique treasure -- a named
  boss or puzzle drops a unique key that opens one specific,
  otherwise-unpickable legendary chest elsewhere. An occasional authored
  exception, not a parallel access system competing with lockpicking for
  ordinary loot.

**Lockpicks:**
- Lockpicks can break. Rather than (or alongside) a flat break-chance-per-
  use, they carry a durability/"health" pool that depletes on failed
  attempts, with a **worse failure margin costing more durability** --
  reusing the "how badly you missed matters" idea already established for
  perception's soft/hard detection fidelity.
- Lockpicks vary along two independent axes: a quality tier (crude / fine)
  crossed with a material (bronze / steel / ...), mirroring how tools and
  materials already vary elsewhere in this content set (e.g. quality-tiered
  crafting outputs). A "crude bronze lockpick" and a "crude steel lockpick"
  are different templates, not the same template with a material label.

## Engine facts this design leans on

Found while scoping this, all already built and tested -- most of this
system is content authoring on top of existing primitives, not new engine
work:

- `InstanceManager.instantiate_quest_region` already creates a `Region` at
  runtime and wires a new exit onto an existing, real, authored room to reach
  it. Built for temporary quest dungeons (torn down on completion) -- a home
  needed the same attachment trick made *persistent* across save/load,
  which was the one genuinely new engine lift in this whole design and is
  now done (see "Shipped" above).
- `Container` already has native `locked`/`key_id` fields, and
  `exit_requirements` already supports a `locked` type with `key_id` and a
  lockpicking skill check (`pick_difficulty`). Locked-but-pickable containers
  and doors need zero new engine code.
- `player.reputation: Dict[faction, int]` (-100..100, `adjust_reputation`/
  `get_reputation`) already exists and is unused for anything like this --
  it's ready-made notoriety tracking against a `town_guard` (or similar)
  faction.
- `TimeManager` already advances on real elapsed time independent of player
  input (the idle-world-ticking work), so a jail sentence can simply run down
  in the background rather than needing a new time system.
- Skills are free-form strings checked via `SkillSystem.attempt_check` --
  adding `perception`/`stealth` as new skills needs no engine change.
- Movement already supports non-directional exits (`in`/`enter`/`inside`,
  `out`/`exit`/`outside`) alongside compass directions -- a district gate can
  just be an authored room using `in`/`out`, no new exit-command mechanism
  needed.
- Multi-stage quests already support a different `turn_in_id` (and NPC) per
  stage -- a contractor who delegates "fetch nails from the blacksmith, then
  boards from the wood shop, then deliver to me" is an ordinary multi-stage
  commission quest, not a new quest-delegation mechanic.
- NPCs already have `home_region_id`/`home_room_id`, but today it's just a
  schedule fallback destination -- for most named NPCs it points at their
  shop/workroom, not a separate residence. Robbable NPC homes are new
  authored rooms, not new bookkeeping.
- The `scheduled` NPC behavior_type (found underused during the combat pass)
  is the natural mechanism for a guard patrol route.
- `lockpicking` is already a real, functioning skill (`Lockpick` item class,
  `get_skill_level`, `SkillSystem.attempt_check`/`grant_xp` wired up) --
  needs no introduction, only combining with the new stealth skill for the
  jail-escape gate below.

## Decided

- **House expansion is tiered** (Cottage -> House -> Manor, or similar), not
  room-by-room or footprint-only. The base room's description/capacity
  changes at each tier.
- **Some tiers branch by playstyle.** A tier can offer a choice (e.g. a
  garden -> ties into a future farming system, vs. a pond -> ties into
  fishing) rather than one fixed upgrade. Each branch implies its own
  materials/crafting/quest requirements, so each is effectively its own small
  vertical slice riding on the shared tier-gate mechanism.
- **Early branch tiers are exclusive (pick one); later tiers accumulate.**
  The first branching tier or two force a real choice, so a player commits
  to and establishes a playstyle rather than trivially getting everything
  at once; eventually (a later tier, or a separate unlock) a player can
  round out their house with the branches they didn't originally pick.
- **Expansion is paid for via a contractor NPC**, requiring gold plus
  fetched/crafted materials (not a flat gold sink). The contractor can
  delegate sub-fetches to other named NPCs (blacksmith for nails, wood shop
  for boards) as stages of one multi-stage commission quest.
- **Locking is a property of the container *type* (chests), not of
  location** (not "residential vs. everywhere" as originally framed).
  Barrels and similar incidental containers are never locked, wherever
  found; chests are locked when first found, full stop. A town locksmith
  offers a paid alternative to lockpicking. Full chest design (contents
  generation, traps, lockpick durability/materials, vendor economics) is
  its own section above, not repeated here.
- **Any NPC can witness and report a crime; guards are better at noticing.**
  A guard noticing an in-progress theft is the *same* perception-vs-stealth
  mechanism described below, run in the other direction (guard's perception
  vs. thief's stealth), not a separate detection system -- one mechanism
  serves both "thief senses guard" and "guard senses thief."
- **Perception and stealth are two separate skills**, not one unified skill.
  Perception governs sensing threats/guards; stealth (paired with
  lockpicking, see the jail-escape entry below) governs your own
  detectability and manual dexterity.
- **Perception detects hostile-faction NPCs and guards in nearby rooms**,
  starting at one room away at base skill; each further skill tier extends
  range by one more room (measured as actual room-graph distance, reusing
  the engine's existing pathfinding rather than any new spatial model).
  Ordinary/generic NPCs (wandering villagers, shopkeepers) never trigger
  this -- only things worth caring about do, which is most of what keeps
  this from becoming spam (see the next point).
- **Detection is edge-triggered, not continuous.** A cue fires only when a
  detectable NPC crosses your detection-range boundary (enters or leaves
  range), never on every step it takes while already inside it -- a goblin
  pacing two rooms over stays silent after the first "you hear it
  approach." A short per-NPC debounce prevents something loitering right at
  the boundary from flickering in and out repeatedly.
- **Detection fidelity is soft or hard, decided by roll margin on one
  check** (not two separate rolls): a narrow success gives an ambiguous cue
  ("you hear something moving to the north"); a wide success identifies it
  ("you're fairly sure that's a goblin, north"). Higher perception raises
  both the chance to notice at all and the odds of a wide-margin (hard)
  result, so high-skill play trends toward specific information rather than
  just longer range.
- **The jail-escape concealed lockpick is a bottleneck of two existing
  skills**, not a new stat or a faction-reputation gate: a player needs
  *both* stealth and lockpicking independently above some floor (not a
  combined/compensatory score where one covers for the other) -- a
  narrative reading being that concealing a pick from a search takes
  practiced sleight of hand (stealth), and having a reason to carry one at
  all takes lockpicking competence. First time both floors are crossed,
  it's marked with a one-time flavor beat ("you've learned to keep a spare
  pick where a search won't find it") rather than silently changing
  behavior with no acknowledgment.
- **Punishment severity is multi-factor:** value of this theft, cumulative
  value stolen, cumulative crime value, and notoriety (reputation) all feed
  into whether the outcome is a fine, jail, or both. Reputation-gated
  escalation (first offenses lean toward fines, low reputation escalates to
  jail) is the agreed shape.
- **Jail time passes via the existing real-time clock**; an explicit
  `wait`/`rest`-in-cell command is added purely for player feedback, not
  because the sentence needs it to advance.
- **Searching a jail cell can rarely turn up something useful**, gated by a
  search-relevant skill (perception or similar).
- **Escape is a lockpicking check on the cell door** (reusing the existing
  locked-exit mechanism), but a prisoner only has a concealed pick available
  if the stealth+lockpicking bottleneck above has been crossed -- not
  available from the start.
- **Escape failure is usually a no-op; only a major/critical failure alerts
  the guards** (extends sentence and/or raises alertness) -- ordinary failure
  is a free retry.
- **Districts are just a labeled group of rooms for now** -- no mechanical
  behavior of their own yet, just an identity. Connection to/from the
  district is a specific, non-directional link (a gate), not a compass
  direction -- the existing `in`/`out` movement verbs cover this with zero
  new engine work.
- **Guards patrol the whole town**, not just the residential district.

## Open questions

- **A trap that permanently ruins the lock.** Raised as a real idea when
  disarm/traps shipped: some traps could make a chest unpickable by
  anyone, locksmith included. What happens to that chest afterward --
  sold to a vendor as a total loss, some other authored escape hatch, or
  a future spell-based retrieval path -- needs more thought before it's
  built. Not decided, not built.
- **What a district needs beyond identity, eventually.** Decided as "just a
  group of rooms" for now; town security iteration may later want to hang
  patrol routes, ambient encounter posture, or crime-severity modifiers off
  district membership. Not deciding now, just noting the tag/grouping should
  be designed so those can attach later without re-authoring the district.
- **Guard patrol density/route shape.** Whole-town coverage is decided; the
  actual route(s) -- one big loop, several overlapping short ones, guard
  count -- is "iterate on it," i.e. build a first pass and see how it feels
  rather than fully specify up front.
