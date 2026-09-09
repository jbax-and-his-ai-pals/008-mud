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
  found. Chests are locked when first found, full stop -- as home/NPC-house
  furniture, and also as ordinary combat loot (chests are a normal random
  drop from defeated enemies, not just something houses contain). A town
  locksmith offers a paid service to open a chest for players who'd rather
  spend gold than invest in lockpicking. This gives lockpicking skill
  everyday utility in ordinary adventuring, not just in the theft/crime
  loop -- one more case of a system paying into more than one playstyle.
  Quest rewards deliberately sidestep the whole question: a quest never
  hands out a locked chest, only the raw item(s) that would have been
  inside one.
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

- **What a district needs beyond identity, eventually.** Decided as "just a
  group of rooms" for now; town security iteration may later want to hang
  patrol routes, ambient encounter posture, or crime-severity modifiers off
  district membership. Not deciding now, just noting the tag/grouping should
  be designed so those can attach later without re-authoring the district.
- **Guard patrol density/route shape.** Whole-town coverage is decided; the
  actual route(s) -- one big loop, several overlapping short ones, guard
  count -- is "iterate on it," i.e. build a first pass and see how it feels
  rather than fully specify up front.
