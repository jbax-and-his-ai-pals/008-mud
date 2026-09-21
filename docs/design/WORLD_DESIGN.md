# World Design — Target Shape

Companion to `ROADMAP.md`. This document is the *design intent* for where the
world is going. The roadmap is the *work queue*. Where they disagree, this file
describes the destination and the roadmap describes the sequence.

Status: drafted 2026-09-14 from a full engine/content audit. Nothing here is
implemented yet unless noted.

---

## 1. Design pillars

These four commitments drive every decision below. When two options conflict,
the earlier pillar wins.

1. **The world is the progress curve.**
   XP must come primarily from *seeing and doing*, not from re-killing the same
   spawn. If a player wants level 12, the answer should be "go find the places
   you have not been", not "kill 449 more things." This makes world authoring
   directly productive: every new region is also progression content.

2. **Gating is invisible.**
   A player should never be shown a locked door they cannot understand, and
   should rarely be shown one they cannot open. Content reveals itself as
   capability grows. The world gets richer as you get stronger — it does not
   present a menu of things you are not allowed to have yet.

3. **Failure is diegetic.**
   Refusals speak in the world's voice, not the engine's. "You've picked this
   patch clean" beats "has been depleted (recovers in 2 days)". Precise numbers
   and reset timers are *test-mode* affordances, not player-facing ones.

4. **Distance is difficulty.**
   How far you are from a safe town is a rough, learnable proxy for how
   dangerous a place is. Players should be able to feel this without being told.

---

## 2. Test mode vs player mode

Everything the audit flagged as "leaking internals" reduces to one missing
concept: the server has no idea whether it is talking to a player or a tester.

### Definition

A single resolved `presentation_mode` on the session, defaulting to `player`:

| | `player` | `test` |
|---|---|---|
| Trust/relationship gates on board listings | hidden; the task simply is not offered | shown as `Trust: 0/10 (locked)` |
| Resource node state | flavour text ("picked clean") | `(5 remaining)`, `(recovers in 2 days)` |
| Debug command category | not registered | registered |
| Level-diff colouring and exact HP/XP on look | off | on |
| Quest objective internals (`location_hint` fallbacks) | resolved to prose, never `?` | raw values |
| Simulated-clock / deterministic affordances | off | on |
| Empty-result refusals that reveal system shape | softened or omitted | verbatim |

### Rules

- **Default is `player`.** Fail closed. The audit found the entitlement gate
  defaults to *open* (`server/engine/entitlement.py:51-54`), which is how
  `level 5`, `setgold 1000` and `teleport` are reachable by a brand-new
  character. Same class of bug; fix both the same way.
- **Test mode is requested, never inferred**, via an explicit launch flag or
  session parameter, and is recorded in the session so logs are unambiguous.
- **Content may vary its wording per mode** (`text.player` / `text.test`
  variants in content JSON) rather than the engine hardcoding two strings. The
  engine supplies the mode; content decides the voice.
- Debug commands live behind the existing `debug` category; that category is
  only registered in test mode.

### Acceptance

- A fresh `player`-mode session cannot reach any `debug`-category command.
- No player-mode output contains `(locked)`, `[Locked]`, `0/10`, `remaining)`,
  `depleted`, or a bare `?`.
- A `test`-mode session reproduces today's exact output, so existing tests and
  the journey lab keep working unchanged.

---

## 3. Progression model

### 3.1 Change the curve

Today: `experience_to_level = 100 × 1.5^(n-1)`, uncapped. The cost of a
5-level band under this curve, versus what the shipped world can supply:

| Band | XP required at ×1.5 | On-level kills to fund it |
|---|---|---|
| L1 → L5 | 812 | ~34 |
| L6 → L10 | 6,147 | ~96 |
| L11 → L15 | 46,659 | ~449 |
| L16 → L20 | 354,297 | ~2,460 |

**Verdict: ×1.5 is not authorable.** A 20-level game under it needs thousands of
kills in the top band, which no amount of regional variety survives.

Proposed curve and the same bands:

| Curve | L1→5 | L6→10 | L11→15 | L16→20 |
|---|---|---|---|---|
| ×1.50 (today) | 812 | 6,147 | 46,659 | 354,297 |
| ×1.35 | 662 | 2,948 | 13,201 | 59,174 |
| **×1.25 (proposed)** | **576** | **1,743** | **5,307** | **16,181** |
| ×1.20 | 536 | 1,324 | 3,288 | 8,168 |

**Recommendation: ×1.25, as a tunable parameter.** Keeps a real sense of
escalation, makes a 20-level arc authorable, and leaves room to go past 20
without re-tuning.

**Built.** `advancement.curve` in `rules/ruleset.json` carries `{"base": 100,
"multiplier": 1.25}`, `engine/core/advancement.py` owns the two curve functions,
and `player/progression.py` asks the manager instead of holding a constant. The
table above is now the shipped behaviour: cumulative cost to L15 is **8,694 XP**
(against 57,952 at ×1.5).

**This does not have to be right yet, and it should not be frozen.** The correct
process is to build the advancement ledger (§3.2) and the content, then tune
the multiplier against real play. Treat ×1.25 as the starting value, not a
decision.

### 3.2 Hybrid advancement — no profession carries the game alone

**Decided.** Progression must not be funded by a single activity. Requiring
enough content for *every* profession is not affordable, and forcing a player
into one (e.g. "explore to level") makes the game narrow. Instead, XP flows
from **any recognised activity**, and the player advances by doing whatever
combination they actually enjoy.

This is affordable precisely because the sources are shared. A single region
entry pays discovery XP *and* contains new creatures, materials, and places
that each pay again. One authored region feeds four or five advancement
sources at once.

Modelled at ×1.25 with modest per-grant values (region 120 XP, discovery 15,
quest 60, first craft 25, relationship tier 40, set 150), each band funded by
a balanced mix with no source exceeding a quarter:

| Ring | Budget | Regions | Discoveries | Quests | Recipes | Tier-ups | Sets |
|---|---|---|---|---|---|---|---|
| 1 (L1–5) | 576 | 1.2 | 10 | 2 | 2 | 1 | 0.4 |
| 2 (L6–10) | 1,743 | 3.6 | 29 | 6 | 7 | 4 | 1.2 |
| 3 (L11–15) | 5,307 | 11.1 | 88 | 18 | 21 | 13 | 3.5 |

Compare funding Ring 3 from exploration *alone*: **27 regions**. From a
balanced mix: **11 regions plus 88 discoveries, 18 quests, 21 recipes.** The
hybrid roughly halves the world the game needs — which is the whole argument
for it.

**The curve is still the constraint.** The same balanced mix at ×1.5 demands
**97 regions and 778 discoveries** for Ring 3. The hybrid mix makes the world
affordable; the ×1.25 curve is what makes the hybrid mix affordable. Both are
needed.

**As shipped** (`ruleset.json` → `advancement.grants`, fifteen rules; the
planner numbers above are still the design target, these are the starting
values):

| Entry kind | XP | Narrowing |
|---|---|---|
| Region first entry | 90 | — |
| Landmark room | 25 | — |
| Recipe learned | 25 | — |
| Spell learned | 30 | — |
| Relationship tier crossed | 40 | — |
| Quest completed | 40 | — |
| Named NPC met | 10 | — |
| Creature template encountered | 15 | — |
| Discovery | 15 | — |
| Collection set completed | 150 | — |
| Item obtained | 8 / 15 / 10 / 5 / 3 | by `item_type`: material · gem · treasure · consumable · curio |

Two properties worth keeping when these are tuned: a **region is worth more
than a creature** (90 vs 15, and the creature pays once per species) so walking
beats farming, and the **starting region is seeded silently** — a character is
recorded as having been to the town they spawned in, but is not paid for it.
Paying it put every new character at 90/100 XP for their first level before
they had done anything, which made the first level-up meaningless and broke the
early quest-share arithmetic in several tests.

### 3.3 What counts as a recognised activity

The existing `DiscoveryManager` already has the right shape and should be
generalised from "notable things found" into the **advancement ledger**. A
grant is recorded the first time a player:

- enters a region (and optionally a landmark room within one)
- encounters a creature template
- obtains a material, item, or gem template
- learns a recipe or a spell
- meets a named NPC
- crosses a relationship tier
- completes a quest, or a collection set
- finds a place of interest (ruin, shrine, camp, natural wonder)

Each entry is content-authored, so a content set decides what is notable and
what it is worth. The ledger is player-visible as a field journal, which is
also the natural home for the "exploration pays on its own" requirement in
§4.4 — a player who walks forty rooms and kills nothing still fills pages.

**Built.** `engine/core/advancement.py`. Entry keys are `"<kind>:<identifier>"`,
the eleven kinds above are the namespace, and gameplay code calls one total
helper — `advancement.award(player, kind, identifier, payload=...)` — which
returns player-facing feedback and never raises into the calling path. The old
`player.discoveries` dict is imported once so existing characters keep their
history, and `discovery` remains a condition kind (§5, titles).

Guardrails:
- **Diminishing, not zero.** Repeat entries pay nothing, but a returned-to
  place should still be worth visiting for other reasons (nodes, NPCs, quests).
  This is structural rather than a decay curve: the ledger is a set, so there is
  no rate to tune and nothing to grind.
- **No single source may be required.** A pacifist, a merchant, and a
  monster-hunter should each be able to advance steadily, by different
  routes, in a designed world.
- **Grants are authored, not implied.** The engine records; content sets the
  values. An entry no rule matches is still recorded — the journal shows it —
  and a malformed rule is reported as an authoring issue rather than silently
  paying nothing.

### 3.4 No level cap — the curve is the brake

**Decided: uncapped.** There is no `MAX_LEVEL`. The exponential curve
self-limits, which produces the intended feel without any engine rule: levels
keep coming for anyone who wants them, but each one costs 25% more than the
last, so past the content's band they slow to a crawl and eventually stop
mattering.

Modelled against a generously-sized fully-authored world (30 regions, ~900
discoveries, 90 quests, 60 crafts, 60 relationship tiers, 15 sets, ~2,000
kills ≈ 128,650 XP total):

| Curve | Full-world budget reaches | Next level then costs |
|---|---|---|
| **×1.25** | **level 26** | 26,470 XP ≈ 42 regions' worth |
| ×1.5 | level 16 | 43,789 XP ≈ 70 regions' worth |

Cost of a single level-up as the curve runs on:

| Level-up | ×1.25 | ×1.5 |
|---|---|---|
| L10 → L11 | 745 XP (1.2 regions) | 3,844 XP (6.1 regions) |
| L20 → L21 | 6,939 XP (11 regions) | 221,684 XP (352 regions) |
| L30 → L31 | 64,623 XP (103 regions) | 12.8M XP (20,291 regions) |
| L40 → L41 | 601,853 XP (955 regions) | 737M XP (1.17M regions) |

Two things follow:

1. **Uncapped is safe at ×1.25.** A completionist plateau around level 26 in a
   large world is a feature — there is something for players who like to
   maximise, and it never becomes a requirement. At ×1.5 the curve becomes
   punitive almost immediately (level 21 costs more than most players will ever
   accumulate), which is the real argument for the lower multiplier.
2. **Content should not chase the tail.** Authoring should target the rings in
   §4.1 and stop worrying about the long tail. Nobody will reach level 40, and
   that is fine. If a future content set wants a different shape, it changes
   its own multiplier.

Implementation note: with no cap, `experience_to_level` grows without bound.
At ×1.25 it passes 32-bit range around **level 77** (2.3 × 10⁹) and stops being
exactly representable as a double around level 145. Neither matters in practice
— no player will get there — but the current code does
`int(p.runtime_state.progression.experience_to_level * PLAYER_XP_TO_LEVEL_MULTIPLIER)`
(`player/progression.py:44`), and that `int()` cast is worth revisiting when the
multiplier moves into the ruleset. It is not a de-facto cap today (the value is
already whole), but it silently becomes one if anyone ever sets a fractional
multiplier.

### 3.5 Backgrounds, skills, and earned titles (replaces classes)

**Decided.** `data/player/classes.json` is removed as a *class* system. The
replacement has three separable pieces:

1. **Background** — a starting kit chosen at creation. Stats, gear, a couple of
   starting skills, and possibly a starting recipe or discovery. This is the
   only creation-time choice, and it should be light: it decides where you
   *begin*, not what you can become.
2. **Skills** — improved by use, as the engine already intends
   (`SkillSystem` exists; `add_skill` is currently called only from tests).
   Skills are the real mechanical progression. Anyone can raise any skill by
   doing the work.
3. **Titles** — **earned, gated, and self-applied.** A player becomes entitled
   to call themselves a Cleric by meeting authored conditions — enough cleric
   spells learned, enough standing with the relevant faction or guild, enough
   related discoveries — and may then set that title if they wish. Titles
   confer no mechanics; they are identity and social signal.

This solves the class problem cleanly:
- No content is locked behind a creation-time choice, so a hybrid playstyle is
  the default rather than a compromise.
- Identity emerges from what the player actually did, which fits a game whose
  whole hook is the trust/crafting economy.
- It reuses machinery that already exists: spells known, faction reputation,
  relationship tiers, and the discovery ledger.

**Guild-like constructs** are the natural home for titles. They take
profession-appropriate names in each content set (guild, order, college, crew,
circle, lodge) and are content-authored, like everything else. A guild is
essentially a named faction with entry conditions, a title it can confer, and
typically a place.

Requirements for the engine:
- A **title registry**: authored id, display name, conditions, and the guild
  or faction that confers it.
- An **`entitlements`/condition evaluator** shared with dialogue conditions
  (§5) — the same predicate language should serve dialogue choices, title
  gates, and quest availability. Build it once.
- A **`title` command** to list earned titles and set the active one.
- Titles must be **revocable** if conditions stop holding (a falling-out with a
  guild should cost you the name).

**Built** (P4): `data/player/backgrounds.json` (six backgrounds, `_default:
wanderer`), `data/titles.json` (sixteen titles as of the Aurelia guild
additions), `engine/core/backgrounds.py`,
`engine/core/titles.py`, and `engine/conditions.py` — the shared evaluator
described above, serving titles today and dialogue and quest availability when
P5 and P6 get there. Commands: `backgrounds`, `background`, `titles`, `title`.
Conditions are authored over the same facts the ledger records, so a title can
be earned by travelling, crafting, trading, collecting, or knowing the right
people, not only by fighting. Unknown condition kinds **fail closed** — a typo
in content cannot open a gate — and player mode says "not yet yours" instead of
printing the threshold.

Two kit conventions the shipped content settled on, both learned the hard way
(see the roadmap's P4 notes): **weapons ship carried rather than equipped**, so
a new player's first `inventory` shows them the weapon they own; and **every
background carries the tool the opening commission needs**, because no
creation-time choice may lock a player out of the first thing the game asks
them to do. `tests/singles/test_background_opening_kit.py` holds both.

### 3.6 Skills must actually exist

`add_skill` is currently called only from tests, so `skills` always reports
"no specialized skills yet" — while `retreat` performs a stealth check against
a skill no player can raise. Either wire skill gain to use (the
`SkillSystem` already exists and has a `stat_bonuses` ruleset section), or
remove the skill check from retreat. A check that cannot be improved is worse
than no check.

**Built** (P4): `SkillSystem.practice_check` is now the single check-then-train
path, and the two dead call sites (retreat's stealth check and skill-gated
exits) use it, so the paths that test a skill also raise it. `_ensure_skill`
reports an untrained skill at level 0 rather than omitting it, so `skills` no
longer claims a character has no trades. Crafting, lockpicking, theft, and
traps already granted skill XP; they now share the same helper.

---

## 4. World shape

### 4.1 Concentric rings around towns

```
        [ Ring 4: L16+ ]          far frontier, other continents
      [ Ring 3: L11-15 ]
    [ Ring 2: L6-10 ]
  [ Ring 1: L1-5 ]  <- starter town at centre
```

Not required to be geometric — **graph distance and travel time from a town**
are the real metric. Rings are a mental model for authoring, not a literal map.

Each ring is a *band of regions* with a consistent level range, its own biome
mix, and its own resource and loot tables. Crossing into the next ring should
feel like a decision.

### 4.2 Towns as anchors

Target: **4–5 towns**, each an anchor with:
- a level band it serves,
- an economy focal point (what it buys, what it lacks),
- a personality (who lives there, what they care about),
- its own surrounding ring of regions.

Towns are what make distance legible. A region 3 hops from a level-10 town
should be level-10-ish content.

**Decided for now: tiered towns with soft gating.** The starter town serves
Ring 1; a second town serves roughly L5; a third roughly L10. Rings are gated
by danger alone — no invisible walls, no level doors, per pillar 2. Travel
between rings is a decision the player makes, not a permission they are
granted.

**Earmarked for later:** letting the player **choose a starting town**, with
region levels assigned relative to wherever they began. This is attractive
(replay value, and it makes the world feel less like one prescribed corridor)
but it multiplies the content needed at launch, because every candidate start
needs a complete first ring. Revisit once two or three towns exist and the
tiering has proven out.

The design must not *preclude* it: region level bands should be **authored data
attached to regions**, not derived from "distance from the starter town", so a
future second start point is a content change rather than an engine change.

The shipped contract is `properties.level_band: {"min": N, "max": N}` on
every static region in a level-banded content set. The set opts into enforcing
that coverage through `ruleset.world.regions.require_level_bands`; a region's
spawner may use the band as its level range when it has no narrower local range.
This is authoring metadata, not a player-facing level gate or a replacement for
learning danger by travel and observation.

**Current town ladder.** Riverside is the L1–3 neutral starter village and
mixed local economy; Portbridge is the L2–4 coastal trade and tariff town,
with the smuggling pressure that commerce brings. Frostpeak is the L5–8
mining-and-smithing outpost at the mountain approach, with a forge, supply
yard, Mining Lodge, and a surveyed route into the existing mine/mountain
spaces. Sunscorch Caravanserai is the L9–12 desert anchor: its water court,
caravan yard, bazaar, and map house serve a marked route from Frostpeak through
the Sunscorch Expanse. Aurelia is the L11–15 prosperous-city anchor, with its
guild square, museum, auction hall, and the dangerous Aurelian Outlands beyond
the imperial road. Its late-game route is content-connected rather than a
fictional future connection.

### 4.3 Biome and region-type palette

A working list to author against. Not exhaustive; meant to be argued with.

Every static Fantasy Frontier region now carries two content properties:
`biome` names its physical character and `region_type` names its play-space
role. The content set opts into `require_classification` and supplies the
allowed vocabulary in `rules/ruleset.json`; validation rejects an unclassified
region or a spelling that has drifted from that vocabulary. This keeps templates
cheap to author while leaving another content set free to use its own palette.

**Surface / wilderness**
- Temperate forest, deep woods, haunted wood
- Grassland, moorland, heath
- Farmland, orchard, vineyard, pasture
- Foothills, badlands, mesa, canyon
- Mountains: alpine, volcanic, glacial, karst
- Swamp, marsh, mangrove, bog
- Coast: beach, cliffs, tidal flats, islands, sea caves
- Desert: dunes, oasis, salt flat, rocky erg
- Tundra, taiga, frozen lake
- Jungle, rainforest, river delta
- Steppe, savanna

**Underground** (explicitly wanted)
- Sewers, cisterns, aqueducts
- Catacombs, crypts, ossuaries
- Mine networks, collapsed mines, deep mines
- Natural cave systems, caverns, sinkholes
- Dwarven/engineered halls, undercities
- Subterranean lakes and rivers
- Volcanic lava tubes
- Root-warrens beneath old forest

**Settled / built**
- Crude monster villages (kobold warrens, goblin camps, lizardfolk village)
- Bandit camps, smuggler coves, pirate anchorages
- Ruins: ancient, recent, overgrown, sunken
- Shrines, temples, monasteries, pilgrimage routes
- Towers, keeps, fortresses, watchposts
- Estates, plantations, manors
- Caravanserai, waystations, crossroads inns
- Ports, docks, shipwrecks, lighthouses
- Markets, fairs, festival grounds
- Academies, libraries, observatories
- Mines, quarries, logging camps, fishing villages
- Graveyards, battlefields, monuments

**Special / interstitial**
- Instanced interiors (see §6.4)
- Player housing and its surroundings
- Planar or magical anomalies (later, if ever)
- Seasonal variants of existing regions (see §7)

### 4.4 Sparse rooms are correct

The audit noted 69% of rooms have no items or NPCs. **That is not a defect and
should not be "fixed."** The target is *sparse rooms in a dense world*: most
rooms carry prose and exits, and interest comes from the region as a whole,
from landmarks, and from what a curious player finds by looking. The fix for
"empty" is better prose and more landmarks, not more clutter.

Corollary: **exploration must pay on its own.** Discovery XP (§3.2),
discoveries/knowledge entries, landmark rooms, and rare gathering sites are the
rewards. A player who walks 40 rooms and kills nothing should feel they gained
something.

---

## 5. Dialogue system

The audit found `data/dialogue/` is **never loaded** — the content loader globs
`regions/ npcs/ items/ crafting/` and nothing else. The only branching
conversation authored in the game (`blacksmith.json`, 3 nodes) is dead code,
and it is also broken (references `item_iron_ore` and quest `iron_shortage`,
neither of which exists). What actually works is a flat `dialog`
keyword→line dict on NPC templates: 124 lines across 36 of 62 NPCs; 26 NPCs
have nothing beyond a `default_dialog`.

A dialogue system is required, and it is on the critical path for the quest
flow change in §6.

### Requirements

- **Content-authored dialogue graphs** loaded from `data/dialogue/`, with NPC
  templates referencing a graph id.
- **Conditions** on choices: has item, has discovery, relationship tier,
  quest state, class, level, time of day, region visited, reputation.
- **Effects** on choices: start/advance/complete quest, grant recipe, grant
  discovery, teach spell, give/take item, adjust relationship, reveal exit,
  move NPC, set flag.
- **Free-text topic fallback** retained — the flat keyword dict is a good
  lightweight option and should stay for minor NPCs.
- **Mode-aware text** (§2) so test output can show conditions and effects.
- **Graceful degradation:** a missing graph, a dangling condition target, or an
  unknown effect must produce a clear authoring error at validation time, never
  a player-visible crash or a `?`.

The existing `server/engine/commands/interaction/npcs.py` quest-dialogue path
already handles negotiation choices; the general dialogue system should absorb
and generalize that rather than sit beside it.

### Built (P5)

`engine/dialogue/` — `graph.py` (the model), `manager.py` (loading, sessions,
rendering, choice matching), `effects.py` (what a line *does*), `runner.py` (the
flow a command drives). Content lives in `data/dialogue/*.json`; an NPC template
points at a graph with `properties.dialogue`.

A conversation is a small directed graph: nodes are what the NPC says, choices
are what the player can say back. A choice may carry a `condition` (the same
`engine/conditions.py` predicate language that gates titles), an `effects`
mapping, a `check` (skill, difficulty, and the two branches it leads to), and
`aliases` — because a player who types "show me the pattern" when the author
wrote "Show me how to make one" should be understood.

Three decisions worth keeping:

- **The player is never the one who finds the bug.** A root that is not a node,
  a `next_stage` pointing at nothing, a condition kind the engine cannot
  evaluate, an effect naming an item nobody authored: all of it is a
  content-validation error. Conversations cannot crash because they cannot load
  broken.
- **Mode awareness is presentation, not logic.** Test mode annotates each reply
  with its destination, check and effects, and lists gated replies as
  `- … (unavailable: needs 2 x item_iron_ingot)`; player mode shows the
  conversation and nothing else. The same graph serves both.
- **Negotiation is a conversation.** A quest's `negotiate` objective supplies the
  stakes (`approach`, `choices`); the dialogue system presents the approach as a
  reply, rolls the skill through `practice_check` (so the attempt trains the
  skill), and applies the authored outcome. What used to be a dice roll behind
  the word "complete" is now something the player can see themselves choosing.

The flat `dialog` keyword dict stays, and now actually works: `npc.talk()` was
only ever called without a topic, so `greeting` was reachable and every other
authored line was dead text. `ask <npc> about <topic>` reads the NPC's own dict
through the shared name resolver.

**One content rule came out of this.** A branching objective must say where each
outcome leads — `next_stage`, or `complete: true`. The default used to be "the
stage after this one", which silently turned a successful truce in
`quest_bandit_lieutenant` into an order to kill the man, and made the
`bandit_rebellion` campaign's `PEACEFUL_SUCCESS` branch unreachable. Half of a
two-ending campaign could not be played. Authors now have to mean it, and the
validator refuses them otherwise.

---

## 6. Quests

### 6.1 Fix the flow (currently inverted)

Observed today:

```
> look board          -> [1] A Posy for Riverside  25 XP, 12 Gold
> accept quest 1      -> [Quest Accepted] A Posy for Riverside
> journal             -> Task: Deliver wildflower posy to Elder Thorne in ?.
                         (You don't have the package!)
> gather / craft      -> the player already knows the recipe
> give posy to Elder  -> [Quest Complete]
```

Two problems: the recipe is known before anyone teaches it, and the journal —
which the accept message explicitly points at — shows a literal `?` instead of
the authored instruction (`"Gather herbs, craft a wildflower posy, and deliver
it to Elder Thorne."`, which exists in `quests.json` and is simply not shown).

Target flow:

```
> look board                 -> a notice, in the world's voice
> accept quest 1             -> the task is taken; journal shows the giver
> talk Elder Thorne          -> he explains what he needs, GIVES THE RECIPE,
                                and says where the wildflowers grow
> journal                    -> "Elder Thorne would like a wildflower posy.
                                 He says the herbs grow in the community
                                 garden, west and south of the square."
> gather / craft             -> now possible, because the recipe was taught
> give posy to Elder Thorne  -> complete
```

This needs: dialogue effects to grant recipes (§5), quest stages to carry
player-facing instructions, and `journal` to render authored prose rather than
template fallbacks.

### 6.2 Quest categories to support

- **Board tasks** — posted, repeatable, level-banded, the bread and butter.
- **Repeatable tasks** — explicitly wanted. Need rate limiting that is
  *diegetic* (the giver is busy, the board is picked over) rather than a
  cooldown timer the player can see.
- **Story/campaign quests** — multi-stage, branching, town-anchored.
- **World quests** — triggered by discovering a place or thing, no giver.
- **Profession quests** — crafting/gathering/social routes that never require
  combat.
- **Instanced quests** — see §6.4.

### 6.3 Objective types to add

Today: 8 deliver, 6 kill, 2 negotiate, 2 scout, 1 fetch — all effectively
single-stage. Missing: escort, defend/hold, timed, puzzle/mechanism, explore-
region, discover-N-things, craft-to-quality, deliver-to-multiple, chain-with-
choice, gather-N-types, social (raise relationship with X), trade (fulfil N
orders), theft/smuggling.

### 6.4 Instanced quests — already working, keep and extend

The engine already supports this: `instance_generic_infestation` has the
"worried homeowner → clear the rats → relieved homeowner" shape, generating a
2–4 room interior dynamically via `layout_generation_config`. This matches the
requested "rats invade a house in town, house is generated dynamically and
destroyed on completion" exactly.

Extend to: variable layout templates per theme, boss/objective rooms, scaling
to player level, multiple entry towns, and instanced *dungeons* as well as
interiors. Instances are the best tool for delivering bespoke-feeling content
without hand-authoring rooms, so this system should grow.

---

## 7. Hazards, weather, and environment

A hazard is **one declared record**, in the content set's own words:
`combat/elements.json`'s `hazards` maps an id to `{channel, flavor, damage,
tick_interval}`, and a room names it with `properties.hazard_type`. The room may
override `hazard_damage`/`hazard_tick_interval` when its instance of the same
hazard is worse, and may scale it with `weather_hazard_multipliers`. One reader
resolves all of it: `engine/world/environment.py`, with `Room.apply_hazards`
delegating to it.

That shape is new (2026-09-19) and replaced three expressions of the same fact:
`hazards.mapping` said which channel a hazard *was*, `hazards.flavor` said what it
read like **keyed by that channel** -- so two hazards sharing a channel shared one
sentence, and a hazard's own name never reached a player -- and each room restated
its damage and interval as untyped properties. Fantasy Frontier's seven hazard
rooms keep their authored numbers, so the migration is behaviour-preserving
except for the prose, which is now the hazard's own.

Fantasy Frontier authors **6 hazards** (`extreme_heat`, `extreme_cold`,
`poison_gas`, `electrified_floor`, `unholy_aura`, `quicksand`), each used by a
distinct region: the obsidian sanctum's heat, Frostpeak's inner ice chamber, a
poisoned mine level, the sparking shipwreck, a ruin's ritual chamber, and the
swamp's quicksand pit. They are telegraphed in room prose and placed in optional
or late-route spaces rather than on the starter path. Fantasy Frontier opts into
`ruleset.world.regions.require_hazard_coverage`, which derives the required names
from its own declarations and rejects an incomplete world at
content-validation time.

**The second theme is `orbital_salvage`'s `hull_frost`**: the cargo hold, damaging
through `thermal` (this set's own channel), in a sentence this set wrote. The set
shipped with `"hazards": {"mapping": {}, "flavor": {}}` -- an empty seat -- and the
seat is now filled. Its `impact vest` declares a `thermal` resistance, so the
mitigation axis is real rather than declared: wearing it measurably reduces the
frost. Nothing about hull frost exists outside that set's files.

Goals:
- Hazards become a defining feature of regions, not a one-off. A volcanic ring
  should be hot; a glacial ring should be cold; catacombs should have bad air.
- Weather resolves through a content-owned regional profile before it is
  described: a coast can make clear weather windy, an alpine region can turn
  rain to snow, and a marsh can turn clear weather to mist. A room's authored
  local climate still takes precedence. Profiles may supply travel advisories;
  gathering nodes can opt into `weather_blocked_by` when a condition makes
  their work unsafe (the sea-fishing node blocks storms), and a hazardous room
  can use `weather_hazard_multipliers` to scale its hazard damage for named
  effective weather (the shipwreck's electrical danger grows in storms; swamp
  quicksand worsens in mist). Both are optional, content-authored maps validated
  for non-empty weather names and positive numeric multipliers.
- Resistance becomes a real itemisation axis, which in turn gives armour and
  consumables a reason to exist beyond raw defense. **Partly real:** the flat
  reduction uses the stat the set's `stats.roles.resistance` names, and the
  per-channel percentages come from equipped `resistances`. That role must name a
  *small derived* rating (fantasy's `magic_resist` defaults to 2), not a core
  attribute: pointing it at `constitution` subtracts 10 from every energy hit and
  makes hazards harmless, which is how `orbital_salvage` found the distinction.
- Hazards should be *learnable*: a player should be able to deduce what they
  need, and prepare. Telegraph before punishing -- the prose is authored per
  hazard precisely so it can say what the danger *is*.
- **Open:** `env_interactions` (a spell suppressing a hazard for a duration, and
  it returning) is engine-complete and unit-tested, but no shipped content
  declares one and the sets' abilities target enemies rather than rooms, so the
  path has no content consumer yet.

---

## 8. Decisions

### Settled

1. **Progression is hybrid.** XP flows from any recognised activity; no single
   profession carries the game. Discovery/exploration is one source among
   several, not *the* source. (§3.2, §3.3)
2. **No level cap.** The exponential curve is the brake. Levels stay available
   to anyone who wants them and simply become very slow past the content's
   band. (§3.4)
3. **No level-up choices.** Level-ups are automatic stat growth. Identity comes
   from backgrounds, use-based skills, and earned titles instead. (§3.5)
4. **Classes are replaced** by backgrounds + use-based skills + earned, gated,
   self-applied titles, with guild-like constructs conferring titles under
   profession-appropriate names. (§3.5)
5. **Curve ×1.25 as a starting value, explicitly tunable.** Not frozen — build
   the ledger and content first, then tune against play. (§3.1)
6. **Tiered towns with soft gating.** Rings gated by danger alone. Player-chosen
   starting towns earmarked for later, and not precluded by the design. (§4.2)
7. **Extend `fantasy_frontier`.** Not a new content set. (§4)
8. **Distance is difficulty.** No hard level doors or invisible walls.

### Still open

9. **Final curve multiplier** — ×1.25 to start; revisit once the ledger exists
   and there is real play data. (§3.1)
10. **Per-grant XP values** — the table in §3.2 uses placeholders (region 120,
    discovery 15, quest 60, craft 25, tier 40, set 150). These need tuning
    against real play. As shipped they are region 90 / landmark 25 / recipe 25 /
    spell 30 / tier 40 / quest 40 / NPC 10 / creature 15 / discovery 15 /
    set 150, with items split 8 · 15 · 10 · 5 · 3 by type.
11. **Test mode surface** — a launch flag, a per-session request, or both?
    *(Resolved in practice: both. `presentation_mode` resolves per session, the
    server has a default, and real entry points default to `player` while
    test/operator paths default to `test`. Kept here only as a note that the
    default is a deliberate choice, not an accident.)*
12. **Town count and identity** — which 4–5, and each one's economy focal point
    and personality? Seeds in §4.2 and the roadmap's P7.
    *(Settled: five towns, per §4.2's "Current town ladder" — Riverside
    (L1–3, neutral starter), Portbridge (L2–4, coastal trade/tariffs/
    smuggling), Frostpeak (L5–8, mining/smithing), Sunscorch Caravanserai
    (L9–12, desert caravan trade), and Aurelia (L11–15, guilds/museum/
    auction). Kept here, like decision 11, as a record that this was a
    deliberate sign-off rather than an accident of how content happened to
    land.)*
13. **Guild model** — how many, how they are joined, whether a player may hold
    titles from several, and whether guilds have places (halls) or are purely
    social.
    *(Settled: ten guild-like groups (nine conferring titles plus the
    Artificers' Exchange added alongside this sign-off), each with a real
    place per §4.2/the roadmap's P7. Membership stays exactly what it already
    was in practice — implicit and title-shaped: a guild "confers" a title
    once its authored conditions hold, revoked the moment they stop, with no
    separate join/application action. A player may hold titles from as many
    guilds as they've earned, unrestricted — a thief's crew title and a
    healing order's title can be worn by the same character, matching
    decision 1's hybrid-advancement stance that no single path should lock
    out another. No new engine mechanism needed; this closes the item by
    confirming the shipped behaviour is the deliberate answer, like decisions
    11 and 12.)*
14. **Diminishing returns shape** — settled structurally for ledger grants
    (repeat entries pay nothing, §3.3). Still open for repeat *kills* and repeat
    *gathers*, which currently pay their ordinary reward every time. Watch it in
    play: the ledger removes the incentive to farm, but not the possibility.
15. **Whether a party share should include first-completion bonuses** for every
    member of a mirrored quest, or only the player who completed it. (§3.2)

---

## 9. What "done" looks like

A player who has never seen the game before:

1. Creates a character by choosing a background, and that choice matters without
   locking them out of anything.
2. Is given a reason to walk out of town that is not "kill things".
3. Crosses into a second region and *gains something* for having done it.
4. Takes a task, is taught how to do it by a person, and does it.
5. Never sees `?`, `(locked)`, a reset timer, or a debug command.
6. Chooses between a dangerous trip and a productive one, and can tell which
   is which from the world itself.
7. Advances at a steady pace regardless of which activities they prefer.
8. Can earn a title by pursuing what interests them, and it means something.
9. Loses a fight, and gets a death screen.

Nothing in this document is more important than item 9.
