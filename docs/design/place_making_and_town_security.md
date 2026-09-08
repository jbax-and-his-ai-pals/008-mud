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

## Engine facts this design leans on

Found while scoping this, all already built and tested -- most of this
system is content authoring on top of existing primitives, not new engine
work:

- `InstanceManager.instantiate_quest_region` already creates a `Region` at
  runtime and wires a new exit onto an existing, real, authored room to reach
  it. Built for temporary quest dungeons (torn down on completion); a home
  needs the same attachment trick but made *persistent* across save/load,
  which is the one genuinely new engine lift in this whole design.
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
- **Expansion is paid for via a contractor NPC**, requiring gold plus
  fetched/crafted materials (not a flat gold sink). The contractor can
  delegate sub-fetches to other named NPCs (blacksmith for nails, wood shop
  for boards) as stages of one multi-stage commission quest.
- **Residential containers are locked by default** (scope: home/residential
  containers specifically -- see open question below on exact boundary), so
  a thief has to keep re-engaging lockpicking/skills rather than loot being
  free once inside.
- **Any NPC can witness and report a crime; guards are better at noticing.**
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

- **Residential container scope.** "Unowned containers are locked" should
  almost certainly mean *residential* containers (homes, NPC houses), not
  every container in the world (a dungeon loot chest becoming a lockpicking
  gate would be a much bigger, probably unwanted, game-feel change). Confirm
  the boundary explicitly before authoring content against it.
- **Whether/how a *guard's* detection of an in-progress theft reuses the
  perception mechanism above**, versus being its own separate roll. The
  perception design above was framed around a thief sensing threats; a
  guard noticing a *crime* is the inverse case and hasn't been explicitly
  decided to use the same range/edge-trigger/fidelity shape, though reusing
  it directly (guards have their own perception skill, rolled against the
  thief's stealth) would keep one mechanism serving both directions instead
  of two parallel systems.
- **What a district needs beyond identity, eventually.** Decided as "just a
  group of rooms" for now; town security iteration may later want to hang
  patrol routes, ambient encounter posture, or crime-severity modifiers off
  district membership. Not deciding now, just noting the tag/grouping should
  be designed so those can attach later without re-authoring the district.
- **Guard patrol density/route shape.** Whole-town coverage is decided; the
  actual route(s) -- one big loop, several overlapping short ones, guard
  count -- is "iterate on it," i.e. build a first pass and see how it feels
  rather than fully specify up front.
- **Persisting player-created regions.** The one real engine gap: save/load
  currently only knows about content-authored (static) regions. A home
  needs its region, its exit-wire on the entry room, and its contents to
  survive a save/load round trip. Scoping this is prerequisite engineering
  work before any of the above can ship, independent of which design
  choices above get made.
