# Roadmap

## Product direction

Build a game in which players can pursue combat, exploration, gathering,
crafting, trade, relationships, collecting, and place-making by preference.
These are complementary routes, not classes or mandatory checklists.

### Design commitments

- The engine stays content-neutral. Mechanics and contracts live in
  `server/engine`; names, values, lore, preferences, recipes, drops, and
  world layouts live in content sets.
- Every major activity should create value for at least two others.
- Basic progression must not require a single preferred playstyle.
- Systems should offer optional depth, not punish players for ignoring them.
- New work ships as a small playable vertical slice with automated coverage.
- Generic/decorative filler content (ambient wanderers, flavor-only NPCs)
  must never crowd out or outrank named, story-relevant content in what a
  player is shown first -- a room description, an interaction suggestion, or
  a highlighted panel entry.

## Now: trust, recovery, and first-hour truth

**Goal:** a new player can explore safely, recover from a mistake, understand
what a system consumed or rewarded, and make progress through more than one
route. A passing automated journey must mean the player actually made
meaningful progress, not only that the server state stayed valid.

### P0: player trust and recovery

- [x] **Fix the innocent-jail soft lock.** Riverside's barracks no longer has
  a public path into the cell. A served sentence now restores belongings and
  moves the player to the jail cell's content-authored `release_destination`,
  rather than telling them they are free while leaving its only exit locked.
  Focused regressions cover ordinary access, sentence expiry, release,
  confiscation, search, and escape.
- [x] **Make inventory-changing actions transactional.** Inventory now selects
  exact units, preflights post-spend capacity, and atomically removes the
  selected units. Gathering validates space before depleting a node; crafting
  and salvage account for freed slots; commissions, gifts, and vendor orders
  consume their validated instances; house purchase preflights its key; and
  jail release restores the original pack before placing unavoidable overflow
  visibly at the release destination. Regression coverage includes full packs,
  quality/provenance permutations, house keys, and restoration overflow.
- [x] **Repair quality/provenance consumption.** Crafting now consumes the
  high-quality materials that determine result quality, and premium deliveries
  or orders consume qualifying instances rather than an arbitrary matching
  copy. The inventory API supports exact-unit selections across stacks and
  distinct instances.
- [x] **Resolve the masterwork-material contract.** Recipe ingredients now
  contribute to material grade by default, while content can explicitly mark
  a required binding, container, fuel, or similar secondary input as
  `quality_contributes: false`. The talisman therefore grades from its rose
  quartz rather than its ordinary leather cord, and its existing pristine
  quartz source can produce the authored masterwork once familiarity is met.
  `recipes` and the headless-client payload preview the next craft's grade,
  available material score, and the specific quality-setting inputs. Content
  validation rejects malformed contributor flags and quality-gated recipes
  with no contributor.
- [x] **Keep the engine content-neutral.** `CrimeManager` already read its
  reputation key, escape-item ID, and value/threshold tuning from a
  content-authored `crime` ruleset section; the remaining hardcoded
  fantasy assumptions lived just outside it -- `World._attempt_combat_retreat`
  assumed a "stealth" skill, and `World.attempt_pick_lock_direction`,
  `engine/commands/jail.py`, `engine/commands/interaction/traps.py`, and
  `engine/items/lockpick.py` all assumed a "lockpicking" skill and an
  `is_jail_cell` property literal instead of reading the same `crime.custody`
  contract `CrimeManager` already used. Moved the retreat skill to a new
  `combat.retreat` ruleset section and the shared lock-related skill to a
  new `locksmithing` section; deleted `engine/config/config_crime.py`
  outright once every constant it held moved to the ruleset. Added
  `content_sets/night_shift`, a small real content set that renames every
  configurable slot (skills, reputation key, jail-room property, emergency
  item id, currency name) to prove none of it is assumed --
  `test_content_set_crime_vocabulary.py` drives real theft/witness/custody/
  escape/retreat flows against it end-to-end.

### P0: first-hour experience

- [x] **Keep the Journal, encounter panel, inventory, relationship display,
  and crafting ledger contextually useful.** Audited all five: the Journal
  (destination, live objective progress, "ready to turn in", multi-route
  breakdown), relationship display (next-milestone progress), and crafting
  ledger (quality-tier preview with contributing materials) already do
  this -- shipped in earlier slices. The "encounter panel" isn't a single
  named surface; it's the combat payload's `suggested_actions` plus the
  room payload's curated `interactions` list, both already functional.
  Inventory is the one real gap (a flat list, no quest-relevance or
  gift-preference annotations) -- deliberately left open as its own
  follow-up slice rather than folded into this one; see below.
- [x] **Turn failures into useful next actions.** All five named scenarios
  now expose a recovery option instead of a bare refusal:
  - A locked exit or door now names the key it needs (`World._locked_message`,
    `engine/world/world.py`) when one is authored and resolvable, and
    supports an authored `failure_message` override mirroring the
    existing "skill"-type exit's own convention -- but never invents a
    key for a deliberately pick-only lock (`key_id: null`).
  - A depleted `ResourceNode` reports days until it recovers when
    `respawn_days` is set, using data the node already tracked
    (`depleted_day`) but never surfaced.
  - `Inventory.can_add_item`'s weight/slot refusals now point at `drop`.
  - A missing-tool refusal confirms neither equipped gear nor inventory
    has the required tool, instead of a bare "you need a X".
  - A commission's accept-time trust refusal now names the real giver
    NPC. Found and fixed a real bug while wiring this up: every authored
    board commission's `relationship_npc_id` is a *template* id (see
    `QuestManager._add_authored_board_quests`), but `world.get_npc()`
    looks up by instance id only -- `giver` silently resolved to `None`
    for every real commission in the game. New `_resolve_relationship_npc`
    helper (used by both the board listing and the accept handler) falls
    back to a template_id scan, the same pattern quest-reward application
    already uses elsewhere.
- [ ] Signpost parallel orientation, gather/craft/social, trade, and
  exploration/combat paths from the opening without implying that one is
  mandatory. Already true by construction (the opening scenario offers four
  parallel, untracked, unranked paths) -- what's not yet decided is whether
  a one-shot upfront message is a sufficient "signpost" or whether it should
  be re-surfaceable later; left open rather than assumed.
- [x] **Retain deterministic maker/economy and low-risk combat routes,
  but make them prove an actual completed goal, recovery from a
  disrupted plan, and no prolonged repeated failure.** "Prove a
  completed goal" already held for `premium`/`opportunity`/`combat`/
  `first-hour` (real outcome checks). The two missing pieces:
  - **Recovery from a disrupted plan.** `FantasyFrontierPremiumMaterialPolicy`
    (inherited by `FantasyFrontierOpportunityPolicy`) now deliberately
    drops its starting foraging knife, attempts to gather river clay
    without it -- a real, fully deterministic, zero-RNG failure hitting
    last slice's improved missing-tool message -- then picks the knife
    back up and completes the same four gathers and full delivery chain
    as before. The low-risk combat route's own disruption is
    deliberately deferred: `flee`'s success is a genuine unmocked skill
    roll in a live run, and a successful flee relocates the player to
    an unpredictable neighboring room, both meaningfully complicating
    deterministic scripting for no clear gain over the maker-route
    proof already shipped.
  - **No prolonged repeated failure.** `gameplay_failure_count` was
    only ever a raw sum across a whole run -- a player failing once
    every ten steps looked identical to one stuck repeating the same
    failing action forever. New `_detect_repeated_failure_stalls`
    (`journey_runner.py`) flags any run of 4-or-more consecutive
    failure-classified steps with no intervening success; both
    `JourneyReport` and `MultiJourneyReport` gained a `stall_errors`
    field that now also gates `passed`, and `run_playtest_lab.py`
    surfaces it in every run's JSON summary.
  `explorer`/`guided`/`sweep` still have no outcome checks -- untouched,
  since the ROADMAP wording names only the maker/economy and combat
  routes specifically.

### Definition of done

- A fresh player cannot become stuck through ordinary movement.
- A player can inspect which specific materials will be spent and receives
  exactly those outcomes after a successful action.
- A full inventory causes a safe, actionable refusal rather than a lost
  resource, payment, or key.
- Solo and shared-world first-hour traces detect repeated failures, dead ends,
  and uncompleted intended goals.
- The first session presents at least three viable next activities, including
  one non-combat route.

## Next: connected lifestyles in existing places

**Goal:** make existing systems feel like a world players can inhabit. Build
depth and cross-system choices before broadening the map or adding a large
number of new mechanics.

### Homes, gathering, and crafting

- [ ] Turn the garden/pond house branches into distinct functional choices:
  a renewable garden with cultivation decisions, and a pond/fishing benefit
  with its own useful output or social connection. Neither should be required
  for progression.
- [ ] Add dependable, persistent home storage plus one player-selected utility
  (display, workstation, garden, pond, trophy space, or similar) before more
  decorative house tiers.
- [ ] Make per-player housing safe for shared worlds: distinct ownership,
  access, keys, save/load behavior, and recovery from lost access. Do not
  present the one-fixed-house prototype as multiplayer-ready housing.
- [ ] Give gathering alternate sources, substitutions, and visible recovery
  information so a depleted shared resource creates a choice rather than an
  abandoned session. Consider whether partial harvests should contribute to
  ecological recovery rather than blocking it.
- [ ] Extend crafting through decisions, not recipe count: explicit ingredient
  selection and previews, substitutions with trade-offs, recipe discovery,
  useful tools/travel supplies/furnishings, and efficient batching for routine
  work.
- [ ] Expand fishing through optional location, season, bait, or target-catch
  choices. Avoid a compulsory reaction minigame.

### Relationships, quests, collecting, and trade

- [ ] Deepen a small cast of named NPCs before adding broad generic social
  content. Each should have discoverable preferences, a personal multi-step
  situation, remembered dialogue, more than one way to earn trust, and a
  concrete access/behavior/opportunity change.
- [ ] Make gifts personal rather than merely valuable: preserve broad gem
  appreciation, while letting preferences and remembered context distinguish
  “valuable” from “thoughtful.”
- [ ] Extend commissions and campaigns with multiple useful resolutions:
  gathering, craft, combat, payment, exploration, social effort, or a
  combination where appropriate. Each resolution should leave a visible
  consequence in the world, access, prices, or dialogue.
- [ ] Turn the 44-gem ledger into a series of attainable discoveries: regional
  and family milestones, museum displays, appraisal leads, and specialist
  commissions. Completion rewards should match the time and rarity involved;
  the collection itself should create intermediate reasons to continue.
- [ ] Measure peaceful, combat, trade, and collecting livelihoods over a real
  session: earnings, travel, consumables, tool costs, gifts/donations, and
  time to a meaningful purchase. Balance toward viable alternatives, not
  identical profit rates.

### Exploration, combat, and crime

- [ ] Densify existing regions before creating new ones. Each meaningful
  exploration cluster should combine a landmark, resource/discovery, person
  or problem, a response choice, and a return reason.
- [ ] Give elite encounters and major enemies readable behavioral identities,
  not only higher statistics: supporters, defenses, warned attacks, retreats
  toward allies, and non-combat bypasses or resolutions where fitting.
- [ ] Audit progression pacing against intended play hours. In particular,
  check whether skill gates such as the two skill-level-20 concealed-pick
  requirement can be reached by normal play rather than repetitive grinding.
- [ ] Complete the crime loop before adding more crime actions: localized
  jurisdiction, clear risk signaling, fines/restitution/recovery, escape
  options, and consequences that are interesting without blocking ordinary
  play.
- [ ] Treat ambient threat awareness and further patrol work as separate,
  authored experience slices once recovery and local consequences are solid.

### Recently completed: opening-room and test-infrastructure hardening

- Randomized-name NPCs (ambient wandering villagers) no longer collide within
  the same room; the factory now prefers an unused first name over the
  content-authored pool before falling back to a repeat.
- The "nearby" interaction hint now prefers named/authored NPCs over generic
  randomized-name filler when picking who gets a "talk" suggestion, so a
  room full of decorative extras can't crowd out the NPC a new player
  actually needs to notice (this is how the villager fix above surfaced --
  the suggestion list is alphabetical among whoever's offered, so it was
  effectively a coin flip whether Elder Thorne made the cut).
- The disabled local-LLM integration no longer imports `torch`/`transformers`
  at module scope, since `AI_AMBIENT_ENABLED` defaults on and every
  `GameManager` construction (including each of the ~3,500 legacy unit
  tests) was paying that import cost for a feature that is currently a no-op.
- Root-caused and fixed a reproducible segfault in the full legacy
  (`unittest discover`) run: a few UI tests called `pygame.quit()` in
  `tearDown`, which tears down the process-wide SDL font subsystem and left
  `engine/ui/panel_content.py`'s module-level font cache holding dangling
  `Font` objects for the rest of the suite. `GameManager` also now reuses an
  existing display surface instead of recreating one on every construction.
  The full suite (3,520 tests) now runs clean in under a minute.
- `content_set.py`'s ruleset/ambient-loot reference validation no longer
  crashes with a `KeyError` when a manifest's `ruleset` path entry is itself
  invalid; it now degrades to reporting that error instead of masking it.

### Recently completed: collectable gem loop

- Generic collections are now an explicit content capability, with a
  contract-gated client ledger rather than a fantasy-specific panel.
- Static collection membership is authored in `collections.json`; item
  annotations remain available for broader families of collectables.
- A collection unlocks on discovery, records inventory versus donated items,
  and accepts turn-ins through any content-authored collector NPC.
- Content validation catches malformed collection definitions, duplicate
  members, and missing item templates before runtime.
- The fantasy slice includes a 44-item gem ledger, a mineable rose-quartz
  seam, and an end-to-end museum donation route covered by headless tests.
- The first refinement hook is live: generic `appraise` metadata and a
  content-authored station/recipe turn a rough specimen into a faceted trade
  good. Further cutting and socketing can build on this contract.
- NPC gift preferences can now target generic item tags, with transparent
  player-facing feedback; refined goods can therefore bridge crafting,
  collecting, and relationship progression.
- The first museum commission is relationship-gated and requires a player
  crafted refined item, closing the loop from discovery through reward.

## Completed vertical slice: Riverlands Craft & Kinship

**Goal:** make gathering, crafting, gifts, and commissions a complete early
route alongside combat and exploration.

- [x] Formalize gathering as a content capability and author real resource
  nodes in two approachable regions.
- [x] Add 8-12 recipes spanning utility, equipment, trade goods, and gifts
  (9 authored: posy, charm, token, bandage, talisman, faceted quartz, iron
  sword, healing brew, leather cap).
- [x] Give three NPCs preferences, visible relationship milestones, and
  small reward or access changes (five NPCs author gift preferences:
  blacksmith, merchant, healer, alchemist, curator).
- [x] Add craft/gather/delivery commissions and at least one
  relationship-gated quest or item (four commissions; the museum showcase
  is relationship- and craft-gated).
- [x] Give gems regional sources, appraisal/cutting hooks, and collection
  value.
- [x] Expand the journey runner with real (not debug-provisioned) gathering
  and outcome assertions for each route.

## Completed vertical slice: Portbridge comes alive

**Goal:** turn a fully-mapped but nearly empty 21-room second town into a
real, playable place, closing the biggest dormant-content gap found in a
survey of existing playstyles.

- [x] Populated the harbor/inn/town-center core with named NPCs (a
  harbourmaster, an innkeeper, a fisherman, a shipwright, three guards --
  two fixed at the north gate, one on patrol -- and randomized-name
  dockhands for ambient life), reusing every existing NPC-authoring
  pattern (vendor `sells_items`/`buys_item_types`, `is_guard`, the guard
  patrol mechanism) with zero new engine mechanics for placement itself.
- [x] Gave the previously-decorative smuggler's tunnel real teeth: two
  tunnel hostiles, and a branching "bust or join the smugglers" campaign
  (`portbridge_smugglers`) mirroring the existing Bandit Rebellion
  campaign's exact shape -- a negotiate-or-fight quest stage whose
  outcome (`PEACEFUL_SUCCESS` vs. `VIOLENT_SUCCESS`) drives the campaign
  branch, reusing the same objective-type-decides-resolution mechanism.
  The previously-unclaimed "dubious cargo" loot in the tunnel's
  underground cache now has real narrative purpose (the join path's
  delivery quest target).
- [x] No fence NPC or "this item is stolen" tracking -- explicitly
  deferred; vendors don't currently know or care whether an item was
  stolen, and that's a separate design question for later.

Found and fixed three real, pre-existing engine gaps while authoring the
negotiate-driven branch -- none specific to Portbridge, all now benefit
the existing Bandit Rebellion campaign too:
- `spawn_on_entry`'s `dialog` override was silently dead: the JSON
  supports it (and Bandit Rebellion's bandit_leader spawn already
  authored one), but the engine never read it, so a quest boss always
  showed its generic combat greeting instead of the negotiation-specific
  line an author wrote for it. Fixed to merge onto the base template's
  dialog rather than replace it, so threat/flee lines survive.
- `talk`'s hostile-faction refusal ("refuses to listen and prepares to
  attack!") fired unconditionally, with no exception for a spawned quest
  NPC waiting on a negotiation -- meaning a `"negotiate"` objective
  targeting any hostile-template NPC (which is all of them, quest bosses
  are always spawned from combat templates) was **unreachable by a real
  player** through any phrasing, including the dedicated `negotiate`
  command. Fixed with a narrow, quest-scoped exception.
- A successful negotiation's own completion branch never computed or
  passed a `resolution` to `complete_quest`, silently defaulting to plain
  `SUCCESS` -- meaning a campaign transition keyed on `PEACEFUL_SUCCESS`
  could never fire. This is very likely why Bandit Rebellion's own
  peaceful ending has never actually been reachable in real play. Fixed
  to compute `PEACEFUL_SUCCESS`/`VIOLENT_SUCCESS` from which choice
  branch actually completed the quest.

## Completed vertical slice: the smuggler-crew follow-up

**Goal:** the Portbridge smuggling campaign's join path ("You're one of
them now.") was a dead end with no ongoing payoff, and the busted path
had no closure with Voss beyond the quest's own reward. This gives both
endings real weight and answers the fence/stolen-goods question deferred
when Portbridge shipped -- narrowly, on purpose.

- [x] The smuggler leader (a permanent, stationary NPC once negotiation
  succeeds -- nothing in the engine ever despawns a `spawn_on_entry`
  NPC) is now a repeatable fence: a new `item_contraband_bundle`
  (worthless to any ordinary vendor) drops from the tunnel's
  already-respawning `smuggler_thug`s, and she'll buy it via a
  repeatable vendor buy order for a flat 35 gold, unlocked the moment
  "Cutting You In" pays out its new relationship reward. No global
  stolen-item-tracking system was added -- deliberately narrower in
  scope than that would be; contraband is just an item type no honest
  merchant wants.
- [x] Both campaign endings now get a real reaction from Harbourmaster
  Voss on asking about smuggling again: grateful closure if busted,
  frustrated dramatic irony if you joined and he never found out.
- [x] Two small, generically useful engine gaps closed to support this:
  a new `campaign_outcome` dialogue condition (`knowledge_manager.py`)
  checks *which* END node a completed campaign reached, not just
  whether it's completed -- `campaign_state` couldn't do this, and
  nothing else did either. And vendor `buy_orders` can now carry a
  `relationship_min` gate, reusing the same mechanism `sells_items`
  already had; a buy-orders-only vendor no longer gets misreported as
  "has nothing to sell right now" with the `orders` hint unreachable.
- [x] **Portbridge tariffs.** All three of Portbridge's honest vendors
  (innkeeper, fisherman, shipwright) carry a flat 10% penalty on both
  buying and selling until `portbridge_smugglers` is completed, either
  ending -- mechanical teeth for Voss's "the tariffs never add up" line,
  and a felt reward for finishing the questline regardless of which way
  you resolved it. A new generic `tariff` vendor property (distinct from
  the existing `economy_impact`, which is a *timed* modifier that
  expires on its own and so can't be gated on quest state) is evaluated
  live against the player's `completed_campaigns`, reusing the
  `campaign_outcome` groundwork above. A `(Portbridge Tariff in
  Effect!)` banner mirrors the existing discount banner so a worse price
  is never unexplained. The smuggler leader's fence deal is untouched --
  her payout is a flat `reward_gold`, a separate code path from ordinary
  buy/sell pricing, so dealing with a smuggler isn't taxed.

## Resolved design question: procedural world placement

Raised while scoping place-making: should more of the world be seeded
procedurally at world-init time (bandit camp locations, mineral vein
placement, other landmarks), not just the player's home? Resolved: no --
the static, fully-authored content is the point (it's what "authored
resource placement rather than generic random abundance," below, already
commits to), and generating variance from it works against that reason for
being static in the first place. Bandit camps, mineral veins, and other
world content stay exactly as authored. Only the player-home placement
question remains open, and it turned out to need a different mechanism
entirely (materializing a new, persistent room rather than picking among
existing authored candidates) -- see place-making below.

## Connected progression

### Exploration and gathering

- Regional resource identities, seasonal availability, node quality, rare
  finds, landmarks, and a discovery journal.
- Ecological regeneration and authored resource placement rather than generic
  random abundance.
- A first generic `survey` command now exposes a node's availability, tool,
  recovery cadence, and seasonal constraints using the same state as harvest.
- [x] **Fishing shipped, at zero engine cost.** Four fish-themed rooms
  across both towns (`fish_stall`/`fishing_hut` in town,
  `fish_market`/`fishing_pier` in Portbridge) were pure flavor text with
  no mechanics; two new `ResourceNode` fishing spots (one per town, at
  the actual gathering room rather than the market) turn them into a
  real activity using entirely existing gathering machinery -- no new
  command, no new engine code. The already-authored (but unwired)
  `item_fishing_net` became the required tool for the first time. Each
  spot's rare-catch `yield_table` entry gives `item_pearl`/
  `item_coral_gem` -- both already listed in the 44-item Riverside Gem
  Ledger collection with **no drop source anywhere in the game** -- their
  first home, so a lucky catch now surfaces a real, immediate collection
  discovery. Fenn the Fisherman's existing "if you're fishing yourself"
  greeting line finally pays off with a dialogue hint pointing at the pier.
  Caught along the way: an unrelated pre-existing test
  (`test_batch_enhancements.py::test_pick_door_direction`) patched
  `SkillSystem.attempt_check`, but `attempt_pick_lock_direction` has
  called `attempt_check_with_margin` since this session's lockpick
  durability rework -- a silent no-op that left the test dependent on a
  real, unseeded dice roll and occasionally failing under full-suite
  ordering. Fixed to patch the method actually called.

### Crafting and economy

- Recipe familiarity, ingredient quality, stations, salvage, and optional
  masterwork variants.
- Recipe familiarity is persistent and visible in terminal/client crafting
  ledgers. Content may author deterministic quality tiers that retain their
  value and gift provenance.
- Masterwork tiers are now live on five gift/trade-good recipes (posy, charm,
  river token, faceted rose quartz, rose quartz talisman), using the existing
  combined `min_crafts` + `min_material_quality` gate. This is a capability,
  not yet fully player-validated: the exact-material transaction and
  multi-ingredient quality contract are P0 work above. Equipment/consumable
  recipes (sword, cap, bandage, potion) deliberately do not yet have tiers:
  the current quality system affects value and gift bonus, not combat stats.
  Giving equipment a meaningful masterwork tier needs a distinct,
  quality-affects-stats design.
- Gatherable nodes may also author material quality. Recipes use the limiting
  score across their required inputs, demonstrated by fine river clay creating
  a premium token even before repeated practice unlocks later tiers.
- Resource-node yield entries can now replace the regional baseline with an
  authored rare material grade. The engine records its neutral grade and
  source provenance, while Riverside demonstrates a rare pristine foothill
  rose quartz find alongside ordinary rough specimens.
- A state-driven opportunity journey now crosses economy, prospecting,
  appraisal, social access, and a museum craft commission. It is deliberately
  a content-level policy over neutral runner contracts, providing a useful
  precursor to later NPC intent selection without coupling NPCs to commands.
- Crafted equipment, tools, furnishings, gifts, curios, and commission goods.
- Vendor specialties, buy orders, local needs, and quality/provenance-aware
  trade—without punitive market simulation.
- Content-authored vendor buy orders now provide repeatable or one-time
  delivery outlets with item, quantity, provenance, gold, and relationship
  terms. The first merchant orders connect river gathering and crafted charms
  to trade and social progression.
- Premium orders and commissions can optionally require a minimum material
  quality score. Riverside keeps its ordinary clay outlet while offering a
  higher-value fine-token trade order and trust-gated delivery commission.
- The premium-material route is now an outcome-asserted journey: it validates
  trust gating, fine gathering, quality-aware crafting, merchant fulfillment,
  and the separate commissioned delivery in one headless pass.

### Relationships and quests

- NPC preferences, daily gifts, milestones, favors, story arcs, prices,
  training, access, and rumours.
- Relationship ledger commands now show known bonds and their next authored
  milestone, keeping social progression legible without a hidden checklist.
- Quests that can accept multiple solutions: fighting, gathering, crafting,
  exploring, social effort, or payment where appropriate.
- The first reusable alternative-resolution contract is live for quest stages:
  an authored `objectives_any` list accepts any one valid route. The museum
  commission demonstrates a player-refined or sourced-specimen resolution.

### Combat and adventure

- [x] **Meaningful retreat shipped.** Fleeing combat was previously free
  and guaranteed: any ordinary movement command while `in_combat` walked
  the player out with no roll, no cost, and no risk
  (`test_combat_flee_mechanics.py` used to document exactly this).
  `World._attempt_combat_retreat` now gates every room change while
  engaged with a live hostile behind a contested `stealth` skill check
  (difficulty scales off the toughest engaged hostile's level) --
  reusing the exact skill this session's crime system already added,
  giving it a second real use. Failure blocks the move outright and
  costs nothing extra: NPCs already auto-attack every tick while
  `in_combat` (`engine/npcs/ai/dispatcher.py`), so simply not letting
  the player leave is the entire "cost," no new combat code needed. A
  new `flee`/`retreat` command auto-picks an exit (preferring a safe
  destination, the mirror image of a hostile NPC's own `try_flee`,
  which prefers *unsafe* ones) and funnels through the identical check
  -- no second formula. Deliberately does **not** force combat to end on
  a successful retreat: a hostile left behind keeps remembering the
  fight, matching existing, intentional aggro-persistence behavior
  (`test_npc_aggro_persistence.py`), and cleans up its own combat state
  naturally once it finds no same-room target on its next turn.
- [x] **Elite encounters shipped, then generalized.** Originally two
  hand-authored templates (`dire_wolf_alpha`, `troll_elder`); per
  follow-up request, folded into one generic system instead:
  `engine/npcs/elite.py`'s `roll_elite_overrides` gives **any** hostile
  template a content-configured chance (`ruleset.json`'s new `"elites"`
  section: chance, stat multiplier, loot guarantee/quantity multiplier,
  a naming prefix pool) to spawn as a boosted, guaranteed-bonus-loot,
  randomly-named variant -- "Alpha dire wolf," "Dread orc grunt,"
  "Ancient harpy" all fall out of the same small config block, wired
  into the ambient `Spawner`'s existing per-region weighted pool with
  one call site and zero per-species content. `NPCFactory`'s override
  plumbing needed no changes at all -- `stats`/`attack_power`/`defense`/
  `loot_table` overrides and the `properties_override` merge (not a
  destructive replace) already existed exactly as needed. Deliberately
  scoped to the ambient `Spawner` only, not a global `NPCFactory` hook
  -- promoting arbitrarily-placed named villagers or quest bosses to
  "elite" would risk breaking scripted encounters. Found along the way:
  `troll` itself (already a fully-defined, level-5 template with
  "regenerative abilities" flavor) was never placed in any static
  hand-authored region -- only in `dynamic_themes.json`'s
  procedurally-generated-region pool. It now has a genuine home in the
  mountains.
- [x] **Bounties shipped.** Two hand-authored kill quests
  (`quest_bounty_dire_wolf_alpha`, `quest_bounty_troll_elder`) posted to
  the quest board via the existing `authored_board_templates` mechanism,
  turned in to Guard Captain Elara. Retargeted once elites went generic:
  a bounty now names a base species (`target_template_id: "dire_wolf"`/
  `"troll"`) plus a new `require_elite` flag on the `kill` objective
  (`engine/core/quests/tracker.py`, one extra condition on the existing
  template-id match) rather than a since-deleted fixed template id --
  "kill an elite dire wolf," not one specific creature. Confirmed the
  procedural kill-quest generator (`generate_kill_objective`) was
  already a bounty system in everything but name -- reward scaling
  already keys off the target's own level -- but these stay
  hand-authored (like every other named-boss quest) so they can require
  the elite roll specifically. Because authored board seeding only
  checks "already on the board," never "already completed," a bounty
  against a rare elite naturally reposts once cleared -- a real "hunt
  it down again when it reappears" loop with zero extra code. Found and
  fixed along the way: two tests (`test_batch_21.py`'s quest-board-overflow
  test, `test_quest_manager_lifecycle.py`'s board-already-full test)
  hardcoded the assumption that authored board quests would never
  outnumber `MAX_QUESTS_ON_BOARD` -- true by coincidence at 4 authored
  templates, false the moment a 5th and 6th were added, even though the
  engine has explicitly treated authored quests as cap-exempt since
  before this session. Fixed both to assert the actual intended
  invariant (no unbounded/duplicate growth) instead of a stale headcount.
- [x] **Combat-derived crafting inputs shipped.** `item_wolf_pelt`,
  `item_wolf_fang`, and `item_troll_hide` were already dropping from
  existing hostile loot tables with **zero recipes consuming any of
  them** -- the same "authored but orphaned" shape this session already
  closed twice (fishing's gem-ledger gap, the smuggler fence's
  contraband). Three new recipes close it: a wolf pelt cloak, a wolf
  fang trophy necklace (a new gift-economy curio), and a trollhide vest
  (the toughest basic body armor in the game). An elite kill now has an
  immediate, legible crafting payoff on top of gold.
- Ensure ambient loot selectors distinguish appropriate NPC categories using
  content-authored tags.
- Fixed a real bug found while pursuing this: `NPCFactory` only ever read
  spell lists from `properties.required_spells`/`properties.random_spells`,
  never from a template's own top-level `usable_spells` field. Five
  templates author that field directly (`goblin`, `skeleton`, `dark_cultist`,
  `orc_shaman`, `wraith`), plus the player-summonable `skeletal_mage_minion`
  -- every one of them has been silently mute (never casting) since spawn.
  The factory now reads both.
- `orc_shaman` (found alongside `orc_grunt`/`hobgoblin_soldier` in the
  mountains region's spawner) now authors `behavior_type: healer` and knows
  `minor_heal`, so it prioritizes healing a wounded ally over attacking --
  the engine's existing `healer` behavior applied to a hostile for the first
  time, giving mountain encounters a real "kill the healer first" dynamic.
  Verified directly (a wounded orc_grunt gets healed before the shaman
  attacks) and against the full journey-runner suite across multiple seeds.
- `scheduled` and `minion` turned out not to be equally cheap next steps:
  `scheduled` needs a real authored patrol route (multi-room, time-of-day),
  and there's no existing fixed hostile camp to attach one to without new
  room content; `minion` is player-summon-only infrastructure (a hostile
  "summoner" archetype would need engine work, not just authoring, to spawn
  and own a minion itself). Both remain open for a dedicated slice rather
  than a quick addition.
- `retreating_for_mana` is not an authored `behavior_type` choice at all --
  it's a transient state any NPC with `max_mana > 0` and `usable_spells`
  already enters automatically mid-combat when low on mana. With the spell
  wiring fixed above, `dark_cultist`, `orc_shaman`, and `wraith` now get this
  for free.

### Gems, collections, and knowledge

- Gem veins, cutting, appraisal, socketing, gifts, displays, and regional
  provenance.
- Bestiary, flora/mineral catalogues, recipes, landmarks, archive donations,
  and optional collection rewards.
- Initial attachment support is now generic: authored hosts expose slots and
  authored tokens expose modifiers; installation, combat/stat effects, save
  persistence, client inventory presentation, and safe detachment are
  engine-level. Content validation rejects malformed attachment contracts at
  load time.
- A generic discovery journal now records authored, item- or tag-triggered
  entries across pickup, gathering, and crafting. It is persistent,
  contract-gated, structured for clients, and validated at content load; the
  fantasy slice uses it to connect field materials, clay, prospecting, and
  lapidary work.

### Place-making

Grew in conversation into a combined housing/theft/town-security design (a
home worth having implies things worth stealing, which implies guards and a
place for them to patrol). Full decision log, engine-fact grounding, and
open questions: [docs/design/place_making_and_town_security.md](docs/design/place_making_and_town_security.md).

- [x] **First implementation slice shipped: a persistent, player-owned
  house.** A property agent (`town:player_house_exterior`, off the
  Residential Street) sells a house for gold via `buy house`; the door is
  key-locked to everyone else and survives save/load. This proved the
  riskiest unproven part of the whole design and fixed a real, pre-existing
  bug along the way: `InstanceManager`'s quest-dungeon doors were silently
  losing their wiring on every save/load round trip, because the permanent
  room they're wired onto is always rebuilt fresh from static content-set
  JSON before a save is loaded, and nothing replayed the wiring afterward.
  `InstanceManager.apply_entry_exit` now does, for both quests and houses.
  Deliberately scoped to exactly one house existing in the world for now
  (a single fixed offer/region id, one shared key template) -- making
  houses genuinely per-player is real follow-up work, not an oversight.
- [x] **Tier 2 shipped: a branching garden/pond expansion.** `expand house
  <garden|pond>` (same property agent, now doubling as contractor) reflavors
  the house's interior room and records `house_tier`/`house_branch` on the
  region, gated on gold plus distinct materials per branch; a new `house`
  command shows current tier/branch and, near the contractor, the next
  tier's options. Confirmed content alone can't wire quest completion to an
  arbitrary side effect like a tier bump -- `_grant_rewards`/
  `grant_party_rewards` only support `xp`/`gold`/`items`/`relationships` --
  so this reuses a direct command (mirroring `buy_house`) rather than a
  quest, the same way `CraftingManager`'s multi-ingredient check/deduct
  loop was reused for the materials cost. A real, multi-stage delegated
  commission (contractor sends you to the blacksmith, then the wood shop)
  remains real follow-up work, not yet built.
- [x] **Chest loot slice 1 shipped: findable, lockable, randomized-content
  chests.** Three chest materials drop from five "hoarder" hostiles with
  contents and lock difficulty generated per-drop (junk/currency/gem/
  equipment via `weighted_choice`, a new `roll_around` distribution utility
  for the "usually expected, rarely a big swing" shape, and a recursive
  per-item value roll on top) -- reusing the existing affix system for
  equipment and the gathering system's quality-score convention for gems
  rather than inventing new mechanics. A locksmith opens a chest for a fee;
  opening/looking-inside/taking already worked with zero new command code.
  Caught and fixed along the way: dynamic template-pool discovery surfaced
  test-only debug gear into real loot, now excluded via a `debug_only` flag.
- [x] **General-store economy overhaul shipped.** Vendors now support a
  per-vendor `sell_rate_multiplier` (default 0.4 preserved for anyone who
  doesn't set one), a weight-only price for a still-*locked* container
  (ignores value/contents, worse than unlocking first), and a universal
  quest-item sale exclusion. Talia is now the general store: broadest
  `buys_item_types` of any vendor, worst rate (0.2) of any vendor -- no new
  NPC. Reconciled two dead, redundant "unique quest item" property flags
  in content down to one (`quest_item`) while wiring the check up. Nine
  pre-existing unit tests that used Talia's template as a generic
  stand-in vendor needed an explicit rate override to keep testing the
  *default* rate rather than her now-intentionally-different one.
- [x] **Lockpick durability rework shipped.** `Lockpick` now carries a
  `durability`/`max_durability` pool that only depletes on a *failed* pick
  attempt, scaled by how badly the attempt missed (a new
  `SkillSystem.attempt_check_with_margin`, additive alongside the unchanged
  `attempt_check`). Lockpicks are no longer stackable (durability requires
  per-instance uniqueness). A real crude/fine x bronze/steel quality
  matrix now exists as four new blacksmith-sold templates. Room-exit
  picking (`World.attempt_pick_lock_direction`), previously a totally
  separate code path that never touched a `Lockpick` object, now shares
  the same wear logic as chest-picking. Caught along the way: the old
  master lockpick's `break_chance` was nested under a `"properties"` block
  in content and never actually reached the constructor -- a latent,
  harmless bug now moot since `break_chance` is gone.
- [x] **Chest traps and disarming shipped -- closes out the chest-locking
  design.** Chest generation now rolls a trap as a fourth independent
  draw (kind -- damage or poison, both reusing existing primitives -- plus
  its own difficulty). Traps are hidden from `examine` (a new, reusable
  `HIDDEN_EXAMINE_PROPERTIES` opt-out on `Item`). `Container.trigger_trap`
  is the one place a trap's consequence fires, called from every way a
  lock can be forced: picking blind (always sets it off, win or lose), a
  bad-enough `disarm` failure, and a "Knock" spell that turned out to
  already exist as a live alternative to lockpicking (previously
  undocumented, and a free trap-bypass until now). A new `disarm` command
  reuses the lockpicking skill exactly as designed -- a narrow miss is
  safe and retryable, a bad one sets the trap off -- and paying the
  locksmith safely defuses any trap at no risk, real extra value over DIY
  picking. Keys stay out of the normal loop, reserved for one-off
  quest/exploration treasure. Deliberately not built: a trap that
  permanently ruins the lock -- a real idea, but what happens to that
  chest afterward needs more thought first (open question in the design
  doc). Full detail:
  [docs/design/place_making_and_town_security.md](docs/design/place_making_and_town_security.md).
- [x] **Crime and notoriety system shipped.** A `steal` command covers
  both robbing a vendor's shop stock and burgling an NPC's home, either
  way resolved by one perception-vs-stealth witness roll against NPCs
  actually present (a new `stealth` skill; NPC "perception" is a derived
  difficulty, not a tracked skill, with a `is_guard` bonus for
  `town_guard`/`guard_captain`). Getting caught is multi-factor (this
  theft's value, running total stolen, `"town_guard"` notoriety in the
  existing `reputation` dict) deciding fine vs. jail. Jailing strips the
  full backpack, held until release; crossing a stealth+lockpicking
  bottleneck exempts or freshly issues one escape lockpick, so an attempt
  is always available once earned. Escape reuses the existing
  `pick <direction>` mechanism with zero new command -- a success forfeits
  confiscated items (a new asymmetry vs. waiting out the sentence, which
  returns everything), a severe-enough failure extends the sentence. One
  home (Mira the Weaver's cottage, reusing a previously-decorative,
  unused room) and one lazily-loot-generated furniture container were
  authored as the concrete first burglary case. Deliberately out of scope:
  the ambient multi-room threat-detection system from the original
  brainstorm (a separate exploration-awareness feature, not a crime
  prerequisite) and guard patrol AI (guards remain stationary). Full
  detail: [docs/design/place_making_and_town_security.md](docs/design/place_making_and_town_security.md).
- [x] **Guard patrol AI shipped.** Turned out to be almost entirely a
  content task -- a `"patrol"` NPC behavior already existed end-to-end in
  the engine (dispatcher routing, pathfinding movement, three pre-existing
  unit tests) but no content had ever used it. All four `town_guard`
  instances now walk short, overlapping routes hubbed at `town_square`
  (route shape was explicitly left "iterate on it"); both Guard Captains
  stay stationary at their posts. One small engine addition: per-NPC-
  placement route overrides, extending an existing room-level NPC-override
  allow-list that already supported per-instance `behavior_type`. Full
  detail: [docs/design/place_making_and_town_security.md](docs/design/place_making_and_town_security.md).
- [x] **Residential district shipped -- closes the original housing/theft/
  guards/district trio.** Needed zero new engine mechanics: a "gate" is
  just an exit keyed `in`/`out` instead of a compass direction (already
  fully registered movement verbs), and a district is a plain
  `{"name", "rooms"}` entry in a new `districts` key on a region's
  existing, schema-free `properties` dict. The existing residential
  street (plus Mira the Weaver's home from the crime slice) became the
  first district; its old compass-direction link to the rest of town was
  changed outright to a non-directional gate, per the design's explicit
  "not a compass direction." One new `World.get_district` lookup powers
  the entire player-visible effect: the room header names the district
  when you're in one. No mechanical behavior yet -- deliberately, per
  design -- but the registry shape leaves room for future patrol routes
  or encounter posture to attach to a district without re-tagging every
  room in it. Full detail:
  [docs/design/place_making_and_town_security.md](docs/design/place_making_and_town_security.md).
- Still to build: further house tiers beyond 2 (a Manor-level tier, and
  whether a later tier lets a player pick up the branch they didn't
  originally choose); the ambient perception/threat-detection system.

- A modest player home, camp, or workshop: storage, displays, workstations,
  gardens, trophies, and furnishings.
- It should strengthen many playstyles without becoming required progression.

## Quality bar and playtesting

- Unit and contract tests for engine behavior; content validation for authored
  references and capabilities; headless client smoke tests.
- Journey runner policies for explorer, combat/quest, gather/craft, social,
  and economy routes; multi-agent shared-world runs for interaction coverage.
- Persist traces, replay and minimize failures, and distinguish player-visible
  dead ends from invariant or protocol failures.
- Maintain headless defaults for bulk test runs.
- [x] **Redefine passing playtests around progress.** Solo outcome checks
  and "repeated failed commands" (the stall detector) already shipped in
  earlier slices. Two real gaps remained, both closed:
  - **The classifier was missing exactly the three named patterns.**
    `_GAMEPLAY_FAILURE_PATTERN` (`journey_runner.py`) had no match for a
    locked exit/container, a depleted resource node, or a missing
    crafting ingredient -- all three previously passed through as
    ordinary, non-failure text with zero effect on `gameplay_failure_count`
    or stall detection. Added narrow phrase matches (`is locked`,
    `has been depleted`, `missing ingredient`) rather than the bare words,
    since each bare word also appears in genuinely informational,
    non-failure text: a container's `examine` status line ("It's locked.",
    a `[Locked]` tag), the quest-trust display's `"(locked)"` annotation,
    and the `survey` command's bare `"(depleted)"` status tag for any
    exhausted node in view. Verified both the true positives and these
    specific false-positive candidates with dedicated unit tests.
  - **Multi-agent reports had zero outcome-check support.**
    `MultiJourneyRunner` only ever computed invariant and stall errors;
    `JourneyRunner`'s `outcome_checks` had no multi-agent equivalent at
    all. Added `outcome_checks_factory`/`agent_outcome_check_factories`,
    mirroring the existing `policy_factory`/`agent_policy_factories`
    two-tier shape exactly, plus a new `outcome_errors` field on
    `MultiJourneyReport` that gates `passed`, each message prefixed by
    agent id like the stall detector already does. `run_playtest_lab.py`'s
    multi-agent branch now selects per-agent outcome checks by policy name,
    reusing the same four `fantasy_frontier_*_outcome_checks` functions the
    solo branch already used.
  This immediately paid off: running two `opportunity`-policy agents in one
  shared world (previously invisible to any outcome check) now correctly
  reports both agents failing their museum-commission and curator-access
  goals, because they contend for the same single-instance rose quartz
  seam and the second agent's fixed script has no way to notice or adapt.
  Real evidence for the not-yet-started "Strengthen shared-world
  playtesting" item below, not something fixed here.
  Deliberately not attempted: "prolonged lack of location/goal progress"
  and "an abandoned route with no alternate plan." Both describe a
  fuzzier condition than either fix above -- a policy could issue
  successful-looking commands (`look`, `wait`) forever without advancing
  any goal, which neither a failure-keyed stall detector nor a
  final-state-keyed outcome check can catch. That needs its own
  progress-over-a-window instrumentation and is a meaningfully larger,
  separate feature.
- [ ] **Separate simulated and real time.** A fast 30-minute journey advances
  game/calendar time but some NPC, cooldown, spawn, and jail behavior still
  uses wall-clock time. Establish a shared injectable clock for deterministic
  simulation, then retain a genuinely real-time background soak mode for
  timing/concurrency behavior.
- [ ] **Strengthen shared-world playtesting.** Give every agent a goal and
  evaluate resource contention, alternate recovery routes, party/reconnect
  behavior, housing/access, shared doors, and transactions while another
  player changes the same world. A run with gameplay failures must not be
  summarized as a clean pass merely because no invariant failed.
  "Give every agent a goal" now has the mechanism (`MultiJourneyRunner`'s
  per-agent outcome checks, above) and one real contention finding to
  start from; still needed: alternate recovery routes, party/reconnect,
  housing/access, shared doors, and transaction interference specifically.
- [ ] **Add route-disruption tests.** Intentionally fill inventory, deplete a
  resource, remove a tool, alter vendor/relationship availability, trigger
  jail/death/recovery, and permute item order. Assert a useful recovery path,
  correct state, and understandable player feedback.
- [ ] **Run coached and uncoached human sessions.** Observe at least a maker,
  explorer/collector, social player, and adventurer. Record where a player’s
  intention fails to become an action, not just crashes or rules violations.
- [ ] **Track player validation separately from implementation.** Every
  feature should record: engine contract verified, authored content available,
  automated player journey demonstrated, and human playtest completed. A
  checked implementation box alone is not evidence of satisfying play.
- No test may call `pygame.quit()`: it tears down the process-wide SDL font
  subsystem for every other test in the same run, not just the one that
  called it (see the segfault fix above). `pygame.init()` is idempotent and
  safe to leave initialized for the life of the process.
- Add a generic content-validation check that renders every authored dialog/
  description/vendor-listing template with representative substitutions and
  fails on any leftover `{placeholder}`. This class of bug (a vendor listing
  once showed a raw `{spell_name}`) has recurred at least twice with only
  ad hoc, per-feature test coverage; a single generic check would catch the
  whole class instead of one incident at a time.
- `engine/server/headless_server.py` has grown into a single ~3,600-line,
  ~140-method class covering session lifecycle, TCP/WS/msgpack framing,
  capability negotiation, the operator catalog, and world-effects policy.
  It still works, but it's the file most likely to become hard to safely
  review or extend; worth splitting along those seams before it grows much
  further.

## Content authoring, client, and maintenance

- [ ] **Make the normal client a player experience.** Separate player-facing
  panels and contextual actions from server/profile/authoring/operator
  controls. Surface expected craft quality, qualifying delivery items,
  resource leads, locked-content reasons, and recovery actions without
  exposing internal schema language.
- [ ] **Add generic text rendering validation.** Render every authored
  dialogue, description, objective, and vendor template with representative
  substitutions and fail on leftover placeholders or schema-flavored prose.
  This should catch issues such as “Deliver the delivery” before playtest.
- [ ] **Unify the editor path with content-set contracts.** The Godot world
  editor still targets older unpackaged data conventions. Deliver a canonical
  export, validator preflight, profile-aware linting, and a launchable
  validate → run → test workflow before broadening authoring tools or adding
  live collaboration.
- [ ] **Keep the roadmap honest and usable.** Reconcile stale documentation,
  counts, and implementation claims as systems change. Record whether a
  feature is a proven engine mechanism, a thin authored example, or a
  player-validated loop.

## Deliberately later

- Advanced NPC use of playtester policies.
- Large-scale economy simulation or mandatory player trading.
- Decorative/deep housing tiers beyond a useful personal storage and one
  functional branch, until the core loops and their first-hour guidance are
  proven.
