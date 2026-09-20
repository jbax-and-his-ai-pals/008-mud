# Track A — Brainstorm

## Assessment

**State.** Four content sets, one mature. `fantasy_frontier` declares all eleven
capabilities (`content_sets/fantasy_frontier/content_set.manifest.json:20-32`);
`orbital_salvage` six; `night_shift` three; `modern_capsule` two, at
`progression_model: "none"` (`content_sets/modern_capsule/rules/ruleset.json:4`).
110 registered commands, 22 of them `debug`. The game today *is* a levelled
fantasy world — combat, crafting, quests, dialogue, collections, housing, crime,
weather, hazards, a spatial field simulation — plus three thin sets that mostly
prove the loader works. So it cannot be a game where anything the player starts
takes time, where a second player can see what you did, or where the world is
observably different when you come back.

**Strongest.** The contract seam: `engine/contracts/**` plus each set's
`data/contracts/world_contracts.json`, with one matcher
(`engine/items/references.py`) serving recipe ingredients, vendor orders and
salvage, and `orbital_salvage` as a real second reader. Second, underexercised:
the Godot client already renders what the server barely produces
(`client/scripts/ui/atmosphere_controller.gd`,
`client/scripts/ui/effects/blight_text_effect.gd`, `world_field_id` in
`client/themes/fantasy_classic.json:18`).

**Weakest.** The skill ladder is the one exponential content cannot touch.
`server/engine/core/skill_system.py:7-8` — `BASE_XP_TO_LEVEL_SKILL = 100`,
`SKILL_XP_MULTIPLIER = 1.5` — is never read from a ruleset, unlike
`advancement.curve`, which P4 authored. Cumulative cost is ≈7,600 XP to skill 10,
≈443,000 to skill 20. Both crime sets gate the jail escape at 20
(`fantasy_frontier/rules/ruleset.json:171-176` stealth+lockpicking;
`night_shift/rules/ruleset.json:45-48` awareness+security) while the only grants
to those skills are 2–35 per attempt (`items/lockpick.py:77,81`;
`core/crime_manager.py:71,73`). The concealed-pick flavour beat and both
emergency tools (`item_lockpick_shiv`, `item_shim_card`) are dead content, and no
gate can see it.

**Surprises.** (1) `steal` is gated by neither capability nor `crime.enabled`
(`commands/interaction/theft.py:9`; `core/crime_manager.py:35-36,52-53`). In
`orbital_salvage`, which declares no `crime` section at all, `steal rail pistol
from ivo` succeeds unnoticed forever, minting a fresh value-120 weapon each time
(`npcs/crew.json:17-20`, `items/gear.json:15-25`) — where the engine's own
precedent, `quest_generation.delivery_package_item_id`, declines rather than
guesses. (2) The field system is fully live and fully unread.
`headless/field_fx.py:118-140` seeds the centre cell of an 8×8 grid for any set
shipping `world/field_interactions.json`; `headless/world_effects.py:158-194`
ticks it, applies pairwise polarity rules, persists cells to SQLite
(`persistence/sqlite_store.py:64-65`) and emits `world_state` events carrying
per-cell intensity. No code maps a cell to a room or region — `cell_id` appears
only in the heartbeat, persistence, the field mixin and tests — so the
coordinates mean nothing, and the only seeder is a debug command behind
`authoring.gm` (`field_fx.py:142-185`). (3) **`night_shift` is the most under-used
set relative to what already exists.** Its ruleset authors the whole
crime → custody → escape → release loop in renamed vocabulary and the depot has
the holding room to match (`data/regions/depot.json:31-42`). But no room places
an item, nothing in it is a `Container`, nothing is worth the 100-credit custody
threshold, the player starts with a box cutter and 0 credits
(`player/core.py:110`) in a set whose only income is selling it at the default
0.4 rate against a value of 3, and `item_master_shim` — a `Lockpick`, durability
20 — is referenced by nothing in the repository. The set is a stage with no play
on it. `modern_capsule` is under-used differently: the only numbers-off set, and
five rooms of dialogue is all the engine has ever been asked to be.

## Proposed roadmap

### 1. `night_shift` becomes the crime system's second theme

**What.** The player works a depot shift whose stock is *logged*, and the log is
all that stands between them and it: crates are real containers with an owner,
the supervisor's schedule decides whether the supply room is watched, and getting
caught runs the authored custody, holding-room and release loop instead of a
fantasy jail. The world does what it already does — witness roll, notoriety,
confiscation, a real-clock sentence.
**Why now.** The ruleset half is written and unreachable (Surprises 3). Cheapest
possible second consumer for crime, and content-only: containers with
`owned_by_npc`, one lockpick for sale, one item past the custody threshold, a
schedule on Priya.
**Depends on.** F; item 3 if the free-theft hole closes first.
**Scope.** Small.
**Done when.** A headless run of the shipped set steals, is witnessed, is held in
`depot:holding_room`, is released to `depot:loading_dock`, and the escape is
either demonstrably reachable or explicitly authored as closed.
**Risk.** It may expose that the loop's interesting part is its *numbers*
(`fine_rate`, `custody_cumulative_threshold`) rather than its shape.

### 2. The skill ladder becomes authored, and unreachable rungs fail the build

**What.** A set declares its own skill curve the way it declares
`advancement.curve`, and a gate reports every authored skill threshold the set's
budget cannot pay for. The player sees only that a door the world described is a
door they can open.
**Why now.** Two shipped sets promise an escape nobody can earn, invisibly,
because each half is individually legal.
**Depends on.** B/K (the curve), I (the gate), F/H (the numbers, and proof the
gate fires).
**Scope.** Medium.
**Done when.** The gate fires on both shipped `minimum: 20` entries as they stand
and passes once each set authors a threshold it can pay for, with fantasy's
numbers unchanged unless that set changes them.
**Risk.** Reachability is a *rate* argument. A gate comparing cumulative XP to
level N overstates what a player can do, and the wrong denominator produces a
check that is confidently wrong.

### 3. Theft has no default

**What.** A set that declares no ownership consequences refuses `steal` in the
world's voice; a set that wants free theft says so.
**Why now.** A live unlimited item source ships today (Surprises 1), and `steal`
is the one command that mints goods behind neither a capability gate nor a
ruleset gate nor a cost.
**Depends on.** B/E (the refusal), F (each set's declaration), I (a check that a
set with stealable content declares consequences).
**Scope.** Small.
**Done when.** The command declines in a set with no `crime` section, the
`orbital_salvage` journey asserts it, and the fantasy and night_shift loops are
unchanged.
**Risk.** Turns an unnoticed hole into a visible refusal in a set nobody tested;
`content_playability_check.py` must be re-run for all four sets.

### 4. Fallow: time as quality on a renewable node

**What.** A node left alone yields better, not merely more — three common herbs
now, or one rare one next week — and the patch remembers when it was last
touched. `ResourceNode` already stores the elapsed days
(`items/resource_node.py:176-180`, read at `:212-229`) and already reads an
authored `material_quality` with a `yield_table` override (`:133-149`).
**Why now.** The composition neither primitive suggests alone: a node treats time
as *recovery* (charges return to the same value), the instance generator treats
quality as a *roll*. Composed, time becomes quality, and leaving something alone
becomes a decision rather than an absence.
**Depends on.** B (a declared idle-quality field), F (a herb bed and a salvage
node).
**Scope.** Small.
**Done when.** One fantasy node and one `orbital_salvage` node yield a
demonstrably higher quality band after the authored idle window than
immediately, asserted headlessly.
**Risk.** It rewards not playing. Without a competing pressure on the same node,
"wait a week" is strictly correct and the mechanic collapses into a delay.

### 5. Region cells: give the field grid a world

**What.** Regions declare coordinates, rooms read their own field intensity in
the world's voice, a field source is a content declaration rather than a debug
command, and a field multiplies an existing room hazard the way weather already
does (`weather_hazard_multipliers`). The player watches a poisoned mine worsen
because of something two regions away, and can act at a shrine to push it back
over the following days.
**Why now.** The engine simulates and persists a grid, and the client renders it
with a polarity-aware atmosphere layer, for a coordinate system connected to
nothing (Surprises 2). The seam that makes it visible is a near-copy of one that
already exists and is authored.
**Depends on.** B (the mapping and the multiplier), C (seeding and persistence),
F (field sources in two sets).
**Scope.** Large.
**Done when.** Two sets seed a field from content, a room's `look` reports it,
and hazard damage differs measurably between a high and a low cell headlessly.
**Risk.** The item most likely to become decoration. Shipping a read without a
player action that changes a field is the same unread declaration one layer
deeper — and the honest alternative is deleting the field system.

### 6. The opening is a contract, not a paragraph

**What.** Every set authors `opening/*.json` objectives carrying an `instruction`
and a `command`, and nothing reads them beyond printing them as a numbered list
(`headless/session.py:264-286`). Give an objective a completion condition in the
language `engine/conditions.py` already evaluates, and a set with no `quests`
capability has a first session that can be *finished*.
**Why now.** `modern_capsule` and `night_shift` declare no quests, so the opening
is their entire spine, and it is unverified prose.
**Depends on.** C (the session), E (the evaluator, already written), I (a check
that every authored `command` resolves against the registry, as
`toolkit/content_playability_check.py` already does).
**Scope.** Small–medium.
**Done when.** An objective in a shipped set is demonstrated complete in a
headless session, and a typo'd `command` fails content checks.
**Risk.** One step from a second quest system. If objectives need ordering,
rewards or givers, they belong in quests and this should be dropped.

## Explicitly not proposing

- **The duration primitive and its two consumers** — already the next Track B
  deliverable with both cases named (`docs/plan/work-tracks.md:471-475`).
- **A new fantasy or sci-fi content set** — settled: extend `fantasy_frontier`.
- **A general flow concept as a bespoke `power_grid`** — refused in the ledger.
- **Per-theme special cases in general code**, and edits to files other tracks
  own.
- **Unifying the stopwatch and calendar models** — refused; the duration doc says
  why.
- **Shared-world contention, per-agent goals, party/scaling, transactions** — P8
  open item owned by C/H; all four sets declare a single-player `world_mode`.
- **Player-chosen starting towns** — deferred; each candidate needs a full first
  ring.
- **Conversation-history predicates, per-player hidden exits, hostile-NPC
  dialogue** — P5 "Still open", owned by E.
- **The ambient multi-room perception system and a `perception` skill** — already
  designed and deliberately parked in
  `docs/design/place_making_and_town_security.md` (Open questions).
- **An in-game authoring tool or mod-facing tool API** — a real gap
  (`work-tracks.md`, Known gaps 6) that needs a lane before it needs an idea.
- **A third theme for housing, and rental income** — periodic, not durational;
  parked by the duration doc.

## Risks

- **Only item 1 is content-only.** The other five ask the bottleneck track for
  time, which is the opposite of what an empty content set usually needs.
- **Items 1 and 6 can be satisfied by authoring rather than by proving
  anything** — the bar has to be "a headless walk of the shipped set does X".
- **Item 5 is the one that may become decoration**; the field system has no
  gameplay consumer today, and the ledger names that failure.
- **Item 2 could be answered by lowering two numbers**, fixing both symptoms and
  leaving the next set free to author another unreachable rung.
- **Under the adopted convention, most of these are fantasy-shaped in their
  examples** until a second theme picks them up.

## Unknowns

- Whether the client's atmosphere layer is reachable in a *player* session — I
  read `atmosphere_controller.gd` and the event handler, not the scene wiring,
  and `client/scenes/main.tscn:75` still carries a developer field input.
- Whether `steal`'s free-success path in `orbital_salvage` has been observed in
  play; nothing asserts it either way, so I cannot tell a known gap from an
  unnoticed one.
- Whether the skill grants I traced are complete — a set may name different
  skills for `locksmithing` and `crime.witness`, and I checked only the two crime
  sets.
- How much of the field tick cost is per-session versus per-world. I did not
  measure it, so I cannot say whether item 5 is affordable at scale.
- Whether `toolkit/content_playability_check.py` boots a `progression_model:
  none` set and exercises it — I read the design in `ROADMAP.md`, not the tool.
- What a *player* does that ought to seed a field. The engine's only answer is a
  debug command, and no content has ever had a field source to author.
