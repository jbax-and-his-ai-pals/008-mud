# Roadmap

> **What is next, in order, is [`docs/plan/chunks-of-work.md`](docs/plan/chunks-of-work.md).**
> This file holds the standing direction, the decisions that constrain it, and the
> live open items. The completed P0–P9 narratives were archived to
> [`docs/archive/roadmap-2026-09-narratives.md`](docs/archive/roadmap-2026-09-narratives.md)
> on 2026-09-18 — including the reasoning behind every decision below.
>
> Three document kinds, kept apart on purpose: **plan** (what is next, churns
> weekly), **reference** (how a thing works, stable), **record** (why a thing is
> the way it is, never changes). See [`docs/README.md`](docs/README.md).

**Companion documents**
- [`docs/plan/work-tracks.md`](docs/plan/work-tracks.md) — how work is divided into eleven tracks, what each may not do, and the contract-first handoff.
- [`docs/plan/track-roadmaps/README.md`](docs/plan/track-roadmaps/README.md) — eleven independent track evaluations and the findings verified from them.
- [`docs/design/WORLD_DESIGN.md`](docs/design/WORLD_DESIGN.md) — target world shape, design pillars, open decisions.
- [`docs/reference/PLAYER_MANUAL.md`](docs/reference/PLAYER_MANUAL.md) — player-facing handbook.

Roadmap rewritten 2026-09-14 after a full engine + content audit. What that
rewrite changed was the *order of work*: the audit found the engine in far better
shape than the world it holds, and several defects sitting directly on the
new-player path. Expansion happened behind a short, non-negotiable repair phase —
and that phase is now complete, which is why the narratives are archived and this
file is short.

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

## Still open

Live work pulled out of the phase bodies when they were archived. Each keeps
the phase it came from, because the reason it is unfinished is usually in that
phase's narrative.

### P2: Content neutrality cleanup


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

### P3: Shared name resolution


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

### P4: Progression spine


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

### P5: Dialogue system


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

### P6: Quest flow and scaling


- [ ] `escort`, `defend/hold`, `timed`, `puzzle/mechanism`, `theft/smuggling`
  objective types -- each needs its own subsystem (see above).
- [ ] `trade` (fulfil N vendor orders) -- infrastructure
  (`vendor_orders_completed`) already exists; wiring it as a quest objective
  type is a smaller lift than the others above, just not done this pass.
- [ ] Branching (non-linear) instanced-quest layouts, multiple real entry
  towns in practice, and instanced dungeons distinct from a house interior.

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
   Blocked on the human playtesting P8 still lists as not started.
2. **Per-grant XP values** and the shape of diminishing returns. Same block:
   real tuning needs real play, not just automated coverage.
3. ~~Test mode surface~~ — **Settled in practice.** `presentation_mode`
   resolves per session with `test` as the safe default; P1 shipped and is
   marked Complete above.
4. ~~Which 4–5 towns~~ — **Settled.** Five towns (Riverside, Portbridge,
   Frostpeak, Sunscorch Caravanserai, Aurelia), each with its own economy
   focal point. Full detail and rationale in `WORLD_DESIGN.md` decision 12.
5. ~~Guild model~~ — **Settled.** Ten guild-like groups, membership implicit
   and title-shaped (conferred once conditions hold, no separate join
   action), unlimited multi-guild stacking by design. Full detail in
   `WORLD_DESIGN.md` decision 13.
6. ~~Condition language~~ — **Settled.** `engine/conditions.py` is the one
   evaluator serving dialogue, titles, and quest availability. What remains
   is narrower and already tracked under P5's own "Still open": no
   conversation-history predicates, `reveal_exit` is world- not per-player
   state, and hostile NPCs have no dialogue beyond negotiation.

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
| `quest_missing_guard` unreachable | Repaired: Guard Captain Elara's dialogue offers the complete route; `test_p6_quest_flow.py` walks it |
| Debug commands ungated | live: `level 5`, `setgold`, `sethealth`, `teleport` |
| `craft` multi-word matching broken | `commands/crafting.py:121-133` |
| Classification unreachable in server path | applied only at `game_manager.py:255` |
| `data/dialogue/` never loaded | loader globs exclude it |
| `mage_set` references 2 nonexistent items | `items/sets.json`; validator reports 0 issues |
| 5 dangling refs (`smite`, `item_smoke_bomb`, `item_iron_ore`, `iron_shortage`, `item_scrap`) | each referenced once, defined nowhere |
| pygame blocks headless content validation | transitive import chain; validator cannot start |
| 99 hardcoded content refs in engine | AST audit across 30 files |
| Content prose mojibaked on Windows | `definition_loader.py` and 10 other engine modules opened UTF-8 content without `encoding=`; the cp1252 default turned U+2019 into `â€™` in live output |

Every row above is fixed except the two `mage_set` refs, which stay allow-listed
in the reference validator until that set has obtainable members. The dialogue
row is P5's work: `data/dialogue/` is loaded and validated now, which also retired
`item_iron_ore` and `iron_shortage` (they existed only inside the dead graph)
and `item_scrap` (the ruleset's generic loot fallback, now a real junk item). The
mojibake row was found during P4 by a failing relationship test and fixed across
eleven engine modules; `tests/singles/test_encoding_hygiene.py` is the tripwire
that keeps it fixed.

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
