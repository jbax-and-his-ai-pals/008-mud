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

## Now: first-hour hardening

**Goal:** a new player can look around, meet someone, choose an activity,
complete a small goal, receive a visible reward, and see several compelling
next paths in their first session.

- [x] Keep the Journal, encounter panel, inventory, relationship display, and
  crafting ledger contextually useful.
- [x] Turn failures into useful next actions; retain the journey runner's
  gameplay-failure classification and outcome assertions.
- [x] Signpost parallel orientation, gather/craft/social, trade, and
  exploration/combat paths from the opening without implying that one is
  mandatory.
- [x] Maintain a deterministic first-hour maker/economy route that proves two
  commissions, a trust gain, a tool purchase, and a destination visit.
- [x] Add an equally deterministic low-risk combat route with a confirmed
  encounter resolution, then run it beside the existing route assertions.

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

### Crafting and economy

- Recipe familiarity, ingredient quality, stations, salvage, and optional
  masterwork variants.
- Recipe familiarity is persistent and visible in terminal/client crafting
  ledgers. Content may author deterministic quality tiers that retain their
  value and gift provenance.
- Masterwork tiers are now live on all five gift/trade-good recipes (posy,
  charm, river token, faceted rose quartz, rose quartz talisman), using the
  engine's existing (already-generic, no code changes needed) combined
  `min_crafts` + `min_material_quality` gate. The token and quartz recipes
  require both sustained practice *and* their material's best available
  grade, not just one or the other. Equipment/consumable recipes
  (sword, cap, bandage, potion) deliberately don't get a tier yet: the
  quality-tier system only affects an item's `value` and gift bonus, not
  combat stats, so a "masterwork" sword would currently be identical in a
  fight to a plain one -- giving equipment a real masterwork tier needs a
  quality-affects-stats extension, which is a distinct, larger feature.
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

- Distinct enemy behavior, bounties, elite encounters, meaningful retreat,
  trophies, and combat-derived crafting inputs.
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

**Design in progress, not yet scoped for implementation.** Grew in
conversation into a combined housing/theft/town-security design (a home
worth having implies things worth stealing, which implies guards and a
place for them to patrol). Full decision log, engine-fact grounding, and
open questions: [docs/design/place_making_and_town_security.md](docs/design/place_making_and_town_security.md).

Decided so far: tiered house expansion (Cottage -> House -> Manor) with
some tiers branching by playstyle (e.g. a garden tier toward a future
farming system, a pond tier toward fishing); expansion paid for via a
contractor NPC requiring gold plus fetched/crafted materials, possibly
delegated across other named NPCs as a multi-stage commission; residential
containers locked by default so theft requires continuous skill
engagement; a multi-factor crime/notoriety system (theft value, cumulative
crime value, reputation) driving a fine-or-jail outcome, with jail time
passing on the existing real-time clock and an escape mechanic gated behind
a not-yet-decided skill/perk; a residential district as a labeled room
group connected by a non-directional gate; guards patrolling the whole
town as a first iteration.

Still open: exact scope of "unowned containers are locked," how a thief
senses guard proximity, how the concealed-lockpick perk is earned, and the
prerequisite engineering gap (persisting a player-created region through
save/load, since the current instance-region mechanism is built to be
torn down, not kept forever).

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

## Deliberately later

- Advanced NPC use of playtester policies.
- Large-scale economy simulation or mandatory player trading.
- Deep housing expansion before the core loops and their first-hour guidance
  are proven.
