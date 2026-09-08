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

## Next vertical slice: Riverlands Craft & Kinship

**Goal:** make gathering, crafting, gifts, and commissions a complete early
route alongside combat and exploration.

1. Formalize gathering as a content capability and author real resource nodes
   in two approachable regions.
2. Add 8–12 recipes spanning utility, equipment, trade goods, and gifts.
3. Give three NPCs preferences, visible relationship milestones, and small
   reward or access changes.
4. Add craft/gather/delivery commissions and at least one relationship-gated
   quest or item.
5. Give gems regional sources, appraisal/cutting hooks, and collection value.
6. Expand the journey runner with real (not debug-provisioned) gathering and
   outcome assertions for each route.

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
  value and gift provenance; masterwork outcomes remain a future extension.
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

## Deliberately later

- Advanced NPC use of playtester policies.
- Large-scale economy simulation or mandatory player trading.
- Deep housing expansion before the core loops and their first-hour guidance
  are proven.
