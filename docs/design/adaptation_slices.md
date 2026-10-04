# Adaptation slices: how far does the engine stretch?

**The question.** Could this engine and its editor carry a game shaped like an early
action-adventure classic, or like a story-driven console RPG, if the battle system
is allowed to become MUD combat? Two small content sets were written to find out,
each played from its first line to its last boss:

| Set | Shape | Size |
|---|---|---|
| `zelda_slice` | An overworld of screens, two dungeons with keys and bosses, two shards, a sealed tower | 5 regions, 35 rooms, 13 NPC templates, 13 items |
| `ff4_slice` | A throne-room choice, a courier run, a boss that arrives with the plot, a summoner child, a title | 4 regions, 19 rooms, 12 NPC templates, 7 items |

Both are shipped sets (`toolkit/content_check_steps.py`), so the whole content gate
runs over them, and both round-trip through the editor byte-for-byte
(`mud-world-editor/tests/content_round_trip_smoke.gd`). The prose is original; what
is borrowed is the *structure*.

## What carried over with nothing added

Everything here was authored as data and played through the real command loop.

* **A grid overworld.** Sixteen screens joined by exits, opened in the editor as a
  4×4 map; entrances to caves, dungeons and a tower as cross-region links.
* **Item-gated progress.** A locked exit that needs a key item in your pack
  (`exit_requirements` type `locked`, or a room's `locked_by`), with an authored
  message. A raft, a boss key, the assembled Triad are all just items.
* **A lever that opens a hidden exit** (`hidden_exits` plus an Interactive item).
* **An element that opens a wall.** A `bomb` spell of a new `explosive` damage type,
  cast at the room, clears a cracked wall's requirement (`env_interactions`).
* **Two hazards in one room, each on its own clock.** (The multi-hazard work.)
* **Bosses.** Loot tables with guaranteed drops, spells, per-channel resistances and
  weaknesses, and a boss spawned by a quest stage the moment the stage begins.
* **Quest chains.** A campaign hands each quest to the next; kill, deliver and
  turn-in objectives; a courier package handed over when the quest starts.
* **Story by dialogue.** Branching graphs with conditions (`flag`, `has_item`,
  `quest_completed`, `all`/`any`/`not`) and effects (`give_item`, `take_item`,
  `set_flag`, `start_campaign`, `teach_spell`, `move_npc`). A choice can cost you an
  item and be remembered; a friend can be sent ahead to the next town.
* **Healing, shops, chests, titles, a summoned ally**: healer NPCs, vendors,
  containers with contents, a title claimed once its conditions hold, a summon spell.

## What it found

Fixed as part of this work:

| Finding | Evidence | Fix |
|---|---|---|
| **A summon spell produced an inert minion.** The minion was created with no owner and no location, so it existed in no room and never acted. The shipped fantasy set had the same defect; the existing minion tests placed and owned their NPC by hand. | `cast raise skeleton` in `fantasy_frontier`: minion at `None, None`, `owner_id None`. | `magic/effects.py` places the minion with the caster and records its owner. `test_summon_places_owned_minion.py` fails against the old code. |
| **The editor wrote its own `_filename` bookkeeping key into `collections.json` and `discoveries.json`.** | Eight stray `_filename` lines in the shipped fantasy set; a freshly generated set diffed on its first round trip. | `DatabaseManager._save_single_file` strips it; the eight lines are removed from the fantasy data. |
| **The editor opened on the first region alphabetically**, not the manifest's start region (unless the file was `town.json` or `start.json`). | `ff4_slice` opened on Fogreach Cave rather than the castle. | `Main._start_region_filename` reads the manifest first. `editor_start_region_smoke.gd` fails against the old code. |
| **The running server persisted nothing.** Both transports built an in-memory database; the entity table was written after every command and never read back; a returning player could not be told from a new one; `save` printed an unconditional "saved automatically". The desktop save never carried a room's exits or properties, and `adventure reset` never closed a door a lever had opened. | A restart lost the character, and a lever, a picked lock or a bombed wall (`TestKnownLimits.test_limit_a_restart_forgets_the_character_and_the_lever`); `test_finite_adventure_reset_closes_exits` failed on the old code. | **Chunk 7, Phase 1.** `SqliteStore` keeps what it is handed (1.1); `world_snapshot.py` is one serialiser for the desktop save, the finite baseline and a restart, and save format 5 carries the world's changes (1.2); a single-player story resumes its character by name, autosaves the world, and takes `--db-path`, `--ephemeral` and `--new-game` (1.3). The two slices are now `single_player_story`. `TestPersistence` and `test_world_snapshot_round_trip` hold it. |
| **Exits gated only on a held key or a skill roll.** No gating on a flag, a quest, a title or "the room behind you is cleared", so a kill-all shutter room, or a gate that opens once the king has spoken, could not be written. | The Triad was modelled as an item; a boss dropped the key. | **Chunk 7, items 3.0 and 3.1.** A `condition` exit requirement reuses the condition language dialogue and titles already use (read afresh each time; an unknown kind fails closed), and `room_clear` is the condition for a kill-all room (no living hostile is left in it). Arrival is now `World._arrive`, apart from the gate `World._evaluate_exit_gate`, so teleport and triggers can arrive without asking the gate. Zelda's tower stair is shuttered until its guard is dead; FF4's castle gate stays shut until the king has given orders. Documented, not changed: `pick` reads only `locked` gates, and NPCs and companions ignore every exit gate. |
| **Nothing could move the player except walking.** A story beat that carries the hero somewhere (guards marching you out, a sage sending you to the tower) had no way to be written. | Left unwritten. | **Chunk 7, item 3.4.** `teleport: {region, room}` arrives through `World._arrive` (visited, location, quest room entry, what the player sees) and never asks the exit gate, so a lock on the way in does not stop it. It runs last in the effect order, so a message or reward is delivered where the player *was* and the arrival is read at the end. A chain of arrivals that each send the player on stops at three (`TELEPORT_CHAIN_LIMIT`). FF4's guards march you out of the throne room when you defy the king; Zelda's sage sends you to the tower once the Triad is forged. |
| **An element's effect on a room always reverted.** `env_interactions` restored after `duration`, so a bombed wall closed again and a wall that should *stay* open could not be written. | The wall was re-bombed. `test_a_bomb_opens_a_cracked_wall_and_the_wall_closes_again` pinned it. | **Chunk 7, item 3.3.** `permanent: true` on a `clear_exit_req` or `suppress_hazard` reaction applies the change and schedules no revert (not `duration: null`, which the tick would trip on). It is world state (Decision 11): the room's properties changed, and the world snapshot already keeps that, so it survives a restart; `adventure reset` restores the baseline. The validator refuses `permanent` with a `duration`. Zelda's bomb wall stays bombed. FF4 has no wall to melt yet (the Ordeals door belongs to the Phase 7 rebuild). |
| **A key was never spent by the door it opens.** "Small keys open any door once" could not be written: a `locked` door checked for the key and left it in the pack. | `test_limit_a_key_is_never_consumed` pinned it. | **Chunk 7, item 3.2.** `consume` on a `locked` requirement (`true`) or a `condition` requirement (a list of items) spends the key at the **commit point**, after every check has passed and before the move, so a move refused for another reason never costs a key. What is remembered is a flag on the player, `exit_open:<region>:<room>:<dir>`, and never an edit to the room's requirement: a static room is rebuilt from its JSON, so editing it would re-lock the door and soft-lock the player. It saves with the character and is per player. Zelda now has a small key found in the larder the lever reveals, which opens the key chamber, and a second inside the chamber for the vault's flooded hall; boss keys (`locked_by`) are still kept. |
| **A conversation could only shuffle the cast, never bring an NPC in or take one out.** `move_npc` moved an existing NPC; a masked advisor who is really a fiend, or a hermit who was never quite there, could not be written. | 26 of the 58 checks in `test_npc_effects.py` and the new slice tests fail on the parent commit. | **Chunk 7, item 2.4.** `spawn_npc` places an NPC from a template (asking twice does not make two) and `remove_npc` takes one out *without a death*: no loot, no respawn timer, no kill, and a pending return of the same creature is cancelled. Both survive a restart, because the world snapshot keeps whole NPCs and a removed one is simply not in it. FF4's chancellor unmasks into a fiend; Zelda's hermit vanishes. |
| **No effect could heal, charge, or make the character permanently stronger, and a consumable could only do one fixed thing.** A heart container healed 200 and left the hero as they were; an inn could not take payment; a "class change" was a title that granted nothing. Separately, a consumable whose `effect_type` nothing executes was accepted and did nothing while being used up (`item_swamp_fungus` in `fantasy_frontier` said `poison`, which no branch of `Consumable.use` handles). | 39 of the 71 checks in `test_character_effects.py` and the new slice tests fail on the parent commit; `test_limit_restore_is_not_an_effect` pinned the gap. | **Chunk 7, item 2.3.** `restore`, `raise`, `take_gold`, `forget_spell` and `message` join the effect vocabulary; a consumable with `effect_type: "effects"` runs any effects mapping. The validator warns on an `effect_type` nothing executes, checks a consumable's effects like a conversation's, checks a `raise`'s stats against the set, and warns on a `raise` that can be repeated or is large and on a payment with no guard. The heart container is now `raise` + `restore`; Zelda's fairy pool refills health and mana; FF4 has a paid inn; the swamp fungus became a real poison. |
| **Dialogue effect *values* were never validated, and one failing effect stopped the rest.** `set_flag` given a list stored one flag named after the list; `advance_quest` naming a template id did nothing while reporting success (active quests are keyed by instance); a `has_item` nested under `all`/`any`/`not` was never id-checked; `give_gold: 0` was a silent no-op; an exception in one effect skipped every effect after it. | `"set_flag": ["a", "b"]` set a flag literally called `['a', 'b']`; 11 of the 14 checks in `test_effect_shapes.py` (`TestRunning`, `TestValidating`) failed against the parent commit. | **Chunk 7, item 2.1.** `EFFECT_SHAPES` in `dialogue/effects.py` says what each effect's value may be; the validator (dialogue *and* knowledge topics) and the vocabulary dump read it. `set_flag` and `give_item` take lists and `{id: qty}`; template quest ids resolve to the active instance and report failure when none is active; each step of `apply_effects` is guarded on its own, in a documented order. The FF4 king sets two flags in one choice. |
| **Nothing happened when the player walked into a room.** A scripted scene, a warning as you cross a threshold, an ambush that springs once: none could be written. | Story beats lived in dialogue and quest stages only. | **Chunk 7, item 4.1.** `data/triggers/*.json` (objects of triggers keyed by id): `{on: {event: "on_enter", region, room}, when, once, effects}`, running the same effect vocabulary a conversation does, not gated on any capability. Fired from `World._arrive` after the location is set and **before the room is described**, so an exit it reveals or seals is in the room text. `once` is `player` (default; a flag on the player), `world` (a latch in `world_state`, which the snapshot keeps) or `false`. A new `seal_exit` effect closes an exit and remembers it as a hidden one, so a lever or `reveal_exit` can reopen it. Loops are stopped (`MAX_DEPTH`, and the teleport chain cap). Editor: a Triggers library with a real inspector (condition and effects are the shared rows) and a "triggers in this room" list. FF4 has a throne-room scene and a once-only fog ambush (a spawned imp, still one after a restart); Zelda has the wyrm's hall and the tower gate. The boss-door seal waits for 4.2, which gives it the kill that reopens it. |
| **Nothing could react to a death** (item 4.2 closes it). | Kill-all doors were only a condition; a boss's death could reveal nothing. | **Chunk 7, item 4.2.** Two more trigger events: `npc_killed` (a template or placed id, optionally in a room) and `room_cleared` (the last living hostile in a room is gone; `factions.hostiles_in`, the same question the `room_clear` gate asks). The world tick now has a **reaper**: a creature that is dead and that nothing has handled (`_death_processed`) gets `die()` run and the event raised once. **This is a visible behaviour fix:** a creature that dies of poison now drops what it carries, and a friendly that dies that way now returns as a friendly does. A summon that expires and a creature removed by `remove_npc` are released, not killed. What a trigger says on a spell or minion kill is now delivered (it was discarded). Zelda's boss door seals behind you and the wyrm's death reopens it; the tower stair's shutters announce themselves when its guard falls; FF4's Fog Drake unravelling starts a scene. |
| **A campaign could only be quests and an ending.** `DIALOGUE` and `CUTSCENE` were declared node types the manager did nothing on, so the validator refused them and a story beat between two quests had to be a quest itself. | 17 of the new tests (`test_campaign_scenes.py`, one Zelda and one FF4 slice test) fail on the parent commit. | **Chunk 7, item 4.3.** A `CUTSCENE` node applies its `effects` (the conversation vocabulary) and moves straight on along `SUCCESS`; a `DIALOGUE` node applies its `effects` and waits until an `advance_campaign` effect, written in a conversation or a trigger, moves the campaign on. `advance_campaign` refuses to skip a quest (it only moves a campaign waiting on a `DIALOGUE` node). Narration reaches the player from a start, a quest completion or an advance, and a loop of cutscenes stops at 20 nodes. The validator checks node effects like a conversation's, refuses effects on a quest or end node, a cutscene that advances, a loop made only of cutscenes, and warns on a dialogue node nothing advances. FF4 opens with a cutscene node where the king seals the package; Zelda's campaign now waits at a `forge` dialogue node until the sage forges the Triad, and that is what starts the tower quest. |
| **No companions.** A summon is temporary and a party is other players; an authored NPC could not join you. | All but the import of `test_companions.py` (18 tests) is new behaviour; the file cannot even load on the parent commit. | **Chunk 7, item 6.1.** A `recruit` effect binds an NPC standing in the room to the player, a `dismiss` effect sets it back down as it was. It is the existing minion AI made permanent: it follows the owner, joins their fights and credits them with kills; `summon_duration` 0 and `is_summoned` false, so it is neither timed out nor swept away when the owner dies. It also moves with the player through every arrival, across regions, ignoring exit gates as NPCs do. There is no separate ledger: a companion is an NPC carrying `properties.companion` and its owner's id, saved with the NPC; a character resumed on a new connection rebinds its companions to the new id. The cap is the ruleset's `companions.max` (default 1, 0 = none). `companion_present` is a condition kind, `companions` a command. |
| **A monster a room placed never came back**, and `respawn_cooldown` was inert for every NPC. Only friendlies were queued to return (on a global constant); only a region's ambient spawner refilled anything. | 4 of the 8 tests in `test_placed_respawn.py` fail on the parent commit; the pin that a slain blob is still gone after 920 s is flipped. | **Chunk 7, item 5.2.** A hostile listed in a room's `initial_npcs` returns after its authored `respawn_cooldown` (`-1`, or none authored, means never), as the room placed it (placement overrides applied), and waits while a player stands in the room. One the ambient spawner made is not placed and is left to the spawner. The queue entry (`placed: true`) is in the world snapshot, so the wait survives a restart. Shared reads live in `engine/world/placements.py`. `fantasy_frontier`'s ten authored hostile cooldowns (240-900 s) now take effect; the seeded playtest lab still passes there. The slices already authored 180 s for monsters and `-1` for bosses. |
| **A hazard weaker than the target's resistance did nothing, silently.** Non-physical damage is reduced by a flat amount first (a fresh hero has 2, and gains 1 a level; a physical hazard meets the defence of 3). | 4 of the 7 tests in `test_hazard_bite.py` fail on the parent commit; the pin that a 1-damage hazard draws no warning is flipped. | **Chunk 7, item 5.3.** The validator warns when a room's hazard (its own damage, else the declared one, at the weakest weather multiplier) is at or below a fresh hero's flat reduction. A warning, not an error: a background or gear can raise the floor. No shipped set trips it. |
| **A template `max_health` was silently ignored**, and `health` is only where a creature starts. An author who wanted a 250-hit-point boss had to solve for the constitution that produced it (the slices did, with a `health` of 400 that was always clamped away). | 6 of the 13 tests in `test_npc_max_health.py` (the rest guard behaviour that must not change) and the 2 new slice tests fail on the parent commit. | **Chunk 7, item 5.1.** Precedence is a saved or placed value, then the template's `max_health`, then the derived figure; `health` stays the starting figure, clamped. An elite promotion scales an authored maximum (constitution does not move it). The validator refuses a `max_health` that is not a whole number of at least 1 and warns on a `health` above it. The NPC panel gains "Max Health" (0 leaves it derived). Both slices state their monsters' maxima outright. Only one shipped template stated one before (`skeletal_mage_minion`, 30, in `fantasy_frontier`), and that value now applies. |

Still open, with the plan item that closes each
([chunk 7](../plan/chunks-of-work.md), ROADMAP P11). Each was hit while writing or
playing a slice and has a workaround in the slices unless noted. Every limit that is a
behaviour is pinned as a passing test in `test_adaptation_slices.py` (`TestKnownLimits`,
plus the bomb wall), and the item that closes it reverses that assertion.

| Gap | What happens | Workaround used | Closed by | Pinned by |
|---|---|---|---|---|
| **Two validators disagree.** `content_set_validator` accepted an NPC `weapon_damage_type` of `physical`; `reference_integrity_validator` (in the gate) rejects it. | The first run of the gate over the new sets. | Corrected the content. | Unscheduled | — |
| **`dark` rooms are only a sentence.** Nothing consults a light source. | A dark room reads "It is very dark here." and plays the same. | Not used; a candle needs this. | Deferred (`work-tracks.md`) | — |

## Where the engine wants a new primitive

In order, now that persistence is known to be the foundation:

0. **Persistence.** ✅ Done (chunk 7, Phase 1). Everything stateful below is meaningless if a restart forgets it.
1. **Triggers with effects** (on-enter, on-kill, on-room-cleared) running the same
   effect vocabulary dialogue already uses. It is the single change that turns set
   pieces, kill-all-to-open doors and scripted scenes from workarounds into content.
2. **More effects, validated.** ✅ Heal, take gold, raise a stat permanently and a
   validator that checks effect *values*, spawn or remove an NPC, and teleport the player
   (chunk 7, items 2.1, 2.3, 2.4 and 3.4).
3. **Conditions on exits**, consumable keys, and reactions that stay.
4. **NPC lifecycle:** respawn, a real `max_health`.
5. **A follower NPC**: an authored ally that joins, fights and can be dismissed.

## Replaying it

```bash
# the load-bearing moments, deterministic (bosses set to one hit point)
cd server && ../.venv/Scripts/python.exe -m unittest tests.singles.test_adaptation_slices

# the whole run, meant to be watched (combat is random; a boss can win)
.venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_zelda.py --verbose
.venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_ff4.py --verbose

# two questions the slices raised (the answers are in each script's header;
# the persistence one is now settled and pinned by TestKnownLimits)
.venv/Scripts/python.exe toolkit/adaptation_walkthroughs/probe_respawn_death.py
.venv/Scripts/python.exe toolkit/adaptation_walkthroughs/probe_persist.py
```

## Cecil's abilities cost life, not mana

A Dark Knight pays for the dark with his own blood, and the engine had no way to say so:
every ability spent the pool, and the pool could never be empty. `health_cost_fraction`
on an ability and `max` on the ability resource (see `cross_theme_engine_contracts.md`)
close that. In `ff4_slice` Cecil has no mana at all, Dark Wave costs an eighth of his
health and strikes every enemy in the room, and Call Titan costs a quarter (a titan rises for five seconds, shakes every enemy in the room, and sinks away). Ethers are
gone (nothing restores a pool he does not have); the cave chest holds potions instead.
`walk_ff4.py` plays the Fog Drake with potions as the resource: Dark Wave 40 damage
(about 26 after the drake's resistances), cast while his health is above 30%, a potion
below 45%.

## Rewriting the FF4 story

The slice is content only: sixty-one JSON files, no code. Nothing in `server/engine`, `client/` or `mud-world-editor/` names one of its
rooms, characters, quests or flags (checked by scanning every id the set owns), and every key the set uses is read by the engine. The
story can be rewritten without touching the engine.

What a rewrite will touch, and what it will not:

* **Pinned to the real set, meant to change with it.** `test_adaptation_slices.py` (journeys through both slices),
  `test_ff4_opening.py` (the first hour: Mysidia, the airship, the landing, the night),
  `test_slice_geography.py`, `test_every_enemy_pays.py`, the story classes of `test_story_beats.py` (the drake fight, the package, Ryn), the
  content gates and `walk_ff4.py`. Rewriting the story means updating these, deliberately.
* **Not pinned.** Every test of an engine feature (kill credit, level growth, messages, quest-text pace, scene resume, panels,
  conversations that must be answered, health-cost abilities, the client checks and the editor's story-field checks) runs on
  `server/tests/sets/story_fixture`, a frozen copy of the slice (`server/tests/sets/README.md`). `test_story_fixture.py` keeps it valid and
  fails any new test that boots `ff4_slice` to check an engine feature.
* **Needing a new engine feature.** If a story beat cannot be said in the existing declarations (`ready_text`, `spawn_on_start.intro`,
  conversation `entries`, `ruleset.messages`, `advancement.level_up`, ...), add the feature to the engine, with its validator, editor field,
  docs and a test on the fixture. Do not special-case the set.

## What would make this wrong

Two slices are not two games. Tuning here is mine: weapon and boss numbers were set
until the walkthroughs could win, so they say nothing about how a real difficulty
curve would feel. Combat was exercised as a MUD fights (a swing per cooldown), never
as the real-time action the first game is about; that part is a translation, not a
port. The editor was checked for fidelity (a clean round trip, a rendered map, the
room inspector on real content) and not for the labour of building three hundred
rooms by hand, and it has no bulk tool for a grid.
