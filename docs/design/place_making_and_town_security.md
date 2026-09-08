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
- **A perception-style skill lets a thief gauge guard proximity** before or
  during a theft (Elder-Scrolls-"how close is trouble" flavor) -- mechanism
  not yet chosen, see open questions.
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
  if a skill/perk grants it -- not available from the start. Exact gating is
  an open question (see below).
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
- **Perception/stealth: one skill or two?** Classic split is "stealth" (how
  detectable *you* are while sneaking) vs. "perception" (how well you notice
  guards/threats/hidden things) as two skills; the alternative is one unified
  skill covering both directions. A single skill is simpler to level and
  teach; two skills let a player specialize (a good sneak who's bad at
  noticing threats, or vice versa) at the cost of two things to raise.
- **How proximity awareness is surfaced.** An explicit command in the
  `survey`/`appraise` idiom (a player-initiated "how close is the nearest
  guard" check) fits the codebase's existing pattern of specialized
  info-gathering verbs better than ambient text injected into every room
  description, but ambient cues read more atmospheric. Leaning toward an
  explicit command; not decided.
- **Detection roll shape.** Is a guard's chance to notice a theft driven by
  distance/line-of-sight through the room graph, a flat per-room chance
  modified by the thief's stealth, or something else? Feeds directly into
  the proximity-awareness question above, since whatever the thief can sense
  should be the same signal the detection roll actually uses.
- **How a prisoner gets a concealed lockpick at all.** Not available from
  the start; a few candidate shapes, none chosen:
  - A passive perk automatically granted at some skill threshold (simplest,
    least narratively interesting).
  - A discrete, deliberately-acquired perk/feat (a trainer NPC or specific
    quest reward) -- gives it a clear narrative moment.
  - Standing with a criminal-underground faction (reusing the existing
    reputation system on a *different* faction than town_guard) -- "earn
    your way into the thieves' circle before they'll trust you with a
    concealment trick." Ties two already-existing reputation tracks into
    real tension (liked by the underworld vs. liked by the guards) without
    new engine plumbing.

  Reputation-gated (the third option) is the strongest fit with what's
  already built, but this was explicitly left open to think through further.
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
