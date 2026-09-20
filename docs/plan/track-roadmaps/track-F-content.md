# Track F — Content

## Assessment

**State.** `fantasy_frontier` is 116 files: 24 regions / 279 rooms, 259 item templates across 10 declared families (thinnest: 2 `key`, 6 `container`), 84 NPC templates (41 hostile), 42 recipes at 4 stations, 22 quests + 1 instance seed, 2 campaigns (11 nodes), 9 dialogue graphs (3–9 nodes each), 23 abilities, 16 titles, 6 backgrounds, 27 affixes, 5 discoveries, 9 resource-node templates at 16 placements, 15 vendors with 66 stock lines and 4 buy orders, hazards on 7 rooms. `orbital_salvage`: 14 files / 4 rooms / 12 items / 1 recipe / 1 ability. `night_shift`: 7 files / 4 rooms / 4 items / 3 NPCs / 0 quests. `modern_capsule`: 8 files / 5 rooms / 3 items / 2 NPCs / 0 quests. Only fantasy and orbital declare `data/contracts/world_contracts.json`; only fantasy declares `advancement`, so the other three sets record ledger entries and pay nothing for them.

**Strongest.** The itemisation/economy spine is the one part that is a system rather than a pile: families declared in `data/contracts/world_contracts.json` and resolved by `ItemFactory`, 66 vendor stock lines and 4 buy orders keyed on family, grade and `crafted_only`, 27 `level_min` affixes, 42 recipes split zero-station (12), `anvil` (23), `alchemy_table` (5), `lapidary_wheel` (1), `carpentry_bench` (1). Quest content is structurally complete too: all 22 quests are offered by something (6 by an authored board entry, 9 only via a dialogue graph, 7 via a campaign) and every turn-in NPC is placed.

**Weakest.** The declared-but-unused layer. Four of P6's five new objective types — `relationship`, `discover_n`, `craft_quality`, `deliver_multi` — have **zero** authored quests; only `gather_types` has one (`quest_local_provisions`). 19 of 22 quests are single-stage. Boards exist in 2 of 5 towns (`ruleset.quest_generation.quest_board_locations`). 172 of 279 rooms (61.6%) carry neither item nor NPC, and 112 carry nothing and are named by no quest, dialogue or campaign — that is §4.4's intent, but its promised compensation is thin: 5 discoveries against a §3.2 ring-3 target of 88. `night_shift` turns on `crime`, `custody` and `locksmithing` in its ruleset while its manifest lists none of them, has no container, and cannot obtain `item_shim_card` — the escape tool its own ruleset names.

**Surprises.** (1) The "16 of 23 abilities have no route" warning is a false positive that hides a smaller real gap. `item_scroll_random` (`properties.procedural_type: random_spell_scroll`), sold by the alchemist at ×2.0 and dropped by four hostiles, rolls uniformly over the 20 spells `item_factory.py:161` admits (`level_required > 0 and mana_cost > 0`) — so 20 of 23 are reachable. The three cantrips (`zap`, `bone_shard`, `ember_bolt`, all `mana_cost: 0`) can never be granted by any content. What is genuinely dead is the deliberately authored half: 5 named scrolls, 4 referenced by nothing and the 5th (`scroll_raise_skeleton`) dropping only from `wandering_mage`. (2) Three complete NPC templates — `forest_hermit`, `wandering_mage`, `wandering_priest` — appear in no room and no spawner; the mage is the only NPC casting `fireball`/`ice_shard`/`magic_missile`. (3) Every room transition pays the 25 XP `landmark` grant (`world.py:477`), so "landmark" carries no information across 279 rooms. (4) `item_dried_herbs` and `item_ale_wort` — stage 1's output and stage 3's input in `duration-primitive.md` — exist in no set; `item_barrel_ale` exists and nothing references it. (5) `presentation.theme_pack` is read by no Python: three of four sets name `modern_neutral`, which does not exist, and `client/themes/scifi_frontier.json` is named by nobody.

## Proposed roadmap

### F-1: Reconnect content that is authored and reachable by nothing
**What to author.** Three room placements (`wandering_mage` and `wandering_priest` into existing NPC-less `town`/`portbridge` rooms, `forest_hermit` into an empty `forest` clearing), loot or stock lines for the four orphan spell scrolls, and a new source for `scroll_raise_skeleton`. ~15 JSON lines across 4 files.
**What it proves.** That "authored" and "in play" are different states, and the second is currently unmeasured — three templates with descriptions, stats, dialog and loot have never existed in a running world.
**Why now.** Smallest change with the largest ratio of work-already-done to work-visible, and it makes the ability question answerable with real content instead of a broken warning.
**Depends on.** Nothing.
**Scope.** Small.
**Done when.** No NPC template and no spell-teaching item is referenced by zero rooms, spawners, vendors and loot tables.
**Risk.** Placement is not findability; no gate measures the gap between them.

### F-2: First quest for each unused objective type, and boards in the other three towns
**What to author.** Four short quests, one per type — `craft_quality` (Ves, Artificers' Exchange), `relationship` (a Riverside NPC), `discover_n` (Curator Vane's collection), `deliver_multi` (a Sunscorch caravan run) — each 1–2 stages with a dialogue graph or board entry; add Frostpeak, Sunscorch and Aurelia rooms to `quest_board_locations`. ~4 quests, 2–3 graphs, 3 ruleset lines.
**What it proves.** That four engine features only tests have driven are usable by an author, and that the board scales past the two towns it was written for.
**Second theme.** Not yet; `trade` (vendor orders) belongs to `night_shift`.
**Why now.** A type with zero consumers is at "proposed" under the two-theme rule applied one level down.
**Depends on.** Nothing; all four types ship and validate.
**Scope.** Medium.
**Done when.** Each type appears in shipped content and `run_content_checks.py` passes.
**Risk.** A `relationship` or `discover_n` gate may read to a player as a counter; that would be a Track E finding, not a content fix.

### F-3: Make `night_shift`'s crime loop playable
**What to author.** Sources for `item_shim_card` and `item_master_shim` (2 of 4 items are unobtainable); 2–3 containers carrying `owned_by_npc`; a locked storeroom; an `advancement.grants` table so the ledger pays; 2–4 rooms to carry stolen goods to. ~6 items, 3–4 room edits, 1 ruleset section.
**What it proves.** That `crime` + `custody` + `locksmithing` have a second theme — today the loop is one fantasy jail cell and one unobtainable shim.
**Second theme.** This *is* the second theme, and the only one available with no new primitive.
**Why now.** Track K's step 4; it is small, and it turns the two-theme convention into a shipped instance rather than an aspiration.
**Depends on.** Nothing — `owned_by_npc` and `is_authority` exist and Priya is already an authority.
**Scope.** Small–medium.
**Done when.** A player can take what is not theirs, be caught, be held and get out, in a set with no fantasy nouns.
**Risk.** `steal <item> from <container>` requires naming an item the container only generates on the first attempt (`theft.py:40`), so the slice must not depend on container theft.

### F-4: Give `modern_capsule` a goal — the repair café
**What to author.** Enable `quests` in the ruleset and manifest, then author the event `community_flyer` already promises: 3 quests (bring a broken thing, fetch a part, deliver the mended item), 2 dialogue graphs for Maya and Devon, a noticeboard item, 3–4 rooms. ~10 small file edits.
**What it proves.** That quests and dialogue run with combat, magic, crafting, gathering and economy all off — the non-combat extreme no other set exercises.
**Second theme.** Second theme for `quests`.
**Why now.** Smallest set, and the only content whose promise is currently a lie: the flyer advertises an event with no content behind it.
**Depends on.** Nothing.
**Scope.** Small.
**Done when.** A player finishes an errand in `modern_capsule` without touching any system fantasy depends on.
**Risk.** `progression_model: none` may be a deliberate vignette; if so this item is wrong and the call is Track K's.

### F-5: Author the duration chain's missing endpoints (lesser version)
**What to author.** `item_dried_herbs`, `item_ale_wort`, a `drying_rack` station item authored exactly like `item_anvil` (`crafting_station_type`), 3 instant recipes on it, 2 placements, one source for wort. **No wait** — ordinary recipes until B declares `work`, at which point each gains `duration_days` and nothing else changes.
**What it proves.** That the preservation case is content and not a diagram: the endpoints exist, `node_herb_bed` → shelf-stable tonic is walkable, and winter counterplay has something to be.
**Why now.** It is the content half of Track K's step 2, and it survives the contract landing — the only condition under which it can precede it.
**Depends on.** `item_wild_herbs`, `item_forest_berries`, `node_herb_bed`, `item_alchemy_kit` and `brew_minor_heal` all exist; B's `work` declaration does *not* gate this version.
**Scope.** Small.
**Done when.** The three recipes exist, craft, and pass `run_content_checks.py`.
**Risk.** A different `work` shape costs the recipes one more edit; keeping timers out of v1 bounds that.

### F-6: Twenty discoveries, and a reason in the regions that have none
**What to author.** 20 new `discoveries.json` entries keyed on `item_ids`/`item_tags` that already exist and are findable, covering the 18 regions with no discovery source; plus 1–2 placed items and an ambient-loot line in each of `riverside_catacombs`, `goblin_scrapcamp`, `kobold_warren`, `gallows_hollow` and `reedscale_village` — 27 rooms with no quest, no vendor, no node and no hazard between them.
**What it proves.** That the discovery surface scales by content alone (no discovery-per-room primitive exists), and whether 5→25 moves what a walker earns — the number §3.2's ring budget rests on.
**Why now.** Largest remaining gap against a stated target (5 of 29 ring-2, of 88 ring-3), pure content, no shape risk. Last because it verifies nothing new about the engine.
**Depends on.** Nothing.
**Scope.** Medium.
**Done when.** Every region with rooms has a discovery source and the five named regions have a non-spawn reason to enter.
**Risk.** Discoveries are item-shaped, so this pays on *obtaining*, not *seeing*; if the intent was per-place reward, the landmark gap below is the answer instead.

## Contract gaps found

- **A container cannot declare what is inside it.** `item_factory.py:241` skips `contains` for Containers and `Container.__init__` reads only the `contents` argument or `kwargs['contains']`; template `properties` are applied after construction. No template in any of the four sets declares contents. Existing routes are `ChestLootGenerator` or `owned_by_npc` → `generate_household_loot`. *Lesser version needing nothing:* place the contents in the room and lock the exit.
- **A procedural teaching item is invisible to the route check.** `content_playability_check.py:458` reads only static `spell_to_learn`, so the real route to 20 abilities is unseen and the warning is inverted. Track I owns the gate; this is the gap report.
- **`teach_spell` is documented and unused.** `dialogue/effects.py:17,44,209` teaches an ability in conversation; no graph uses it and the route check does not count it, so a set with no scroll shop has no ability route at all.
- **`landmark` is not a declaration.** `world.py:477` pays `KIND_LANDMARK` on every transition, so 279 rooms are interchangeable and content cannot mark one as notable or as deliberately plain.
- **`presentation.theme_pack` has no reader.** The client scans `client/themes/*.json` and picks by hand; three sets name a pack that does not exist. Either a reader or the field goes.
- **No shape for a scheduled or one-shot world event.** The flyer promises "a repair café this Saturday"; the only periodic declaration is `respawn_days`. `temperature` — the modifier `duration-primitive.md` proposes — is set on 2 rooms and read only for prose (`room.py:162-169`).

## Explicitly not proposing

- **Engine work of any kind** — lane; every item lands as JSON.
- **A fourth content set** — two of the three existing ones are not games yet.
- **Porting fantasy content into the other sets** — that is fantasy with different nouns, and the neutrality claim dies with it.
- **Retuning the ×1.25 curve, the grant values or vendor prices** — blocked on the human playtesting `ROADMAP.md` still lists as not started.
- **Level-gating `item_scroll_random`'s pool** — the pool is engine-side; the content lever is price, and moving it pre-playtest is a guess.
- **A flow/power-grid system for `orbital_salvage`** — deferral ledger; wants a general flow primitive.
- **A skill-pairing heuristic or new weapon disciplines** — `skill_audit` pattern 7 has one instance; the ledger says revisit at five.
- **Fixing `steal`-from-container usability** — Track E's file; handed over, not touched.
- **Anything about `time_of_day`** — already verified in `track-roadmaps/README.md`.

## Risks

- **Verification is not authoring.** None of these items proves a player can find what was written; 112 of 279 rooms are already invisible to a gate that only checks reachability.
- **The thin sets may not want to be games.** If `modern_capsule`'s `progression_model: none` and `night_shift`'s manifest are deliberate, F-3 and F-4 are the wrong work and that call is Track K's.
- **Sets with no contracts.** `night_shift` and `modern_capsule` declare no families or profiles, so anything they express as a family must be declared first or authored twice.
- **A gate that reports the wrong thing trains authors to ignore it.** The ability warning is measurably inverted; authoring against it would hide the five dead scrolls.
- **F-5 depends on B's `work` shape.** Bounded so a surprise costs one data edit — unless the endpoints change meaning.

## Unknowns

- **Whether anyone reaches ring 2 or 3 in play.** The level-15 headless walk proves the arithmetic, not that a person finds the route.
- **Whether `item_scroll_random` is the intended ability ladder.** The alchemist entry and derived price look deliberate; nothing says so, and it makes a level-1 goblin a source of level-6 spells.
- **Whether the four P7 monster settlements are quest hubs or ambient danger.** No content declares an intent.
- **Whether `night_shift` is a shipped theme or only the contract-currency exercise.** K's step 4 says the latter; its ruleset says the former.
- **How much of the 61.6% sparse-room figure is deliberate.** No gate separates "nothing here on purpose" from "nothing here yet", and I could not tell from the files.
