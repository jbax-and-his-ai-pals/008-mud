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
| **No effect could heal, charge, or make the character permanently stronger, and a consumable could only do one fixed thing.** A heart container healed 200 and left the hero as they were; an inn could not take payment; a "class change" was a title that granted nothing. Separately, a consumable whose `effect_type` nothing executes was accepted and did nothing while being used up (`item_swamp_fungus` in `fantasy_frontier` said `poison`, which no branch of `Consumable.use` handles). | 39 of the 71 checks in `test_character_effects.py` and the new slice tests fail on the parent commit; `test_limit_restore_is_not_an_effect` pinned the gap. | **Chunk 7, item 2.3.** `restore`, `raise`, `take_gold`, `forget_spell` and `message` join the effect vocabulary; a consumable with `effect_type: "effects"` runs any effects mapping. The validator warns on an `effect_type` nothing executes, checks a consumable's effects like a conversation's, checks a `raise`'s stats against the set, and warns on a `raise` that can be repeated or is large and on a payment with no guard. The heart container is now `raise` + `restore`; Zelda's fairy pool refills health and mana; FF4 has a paid inn; the swamp fungus became a real poison. |
| **Dialogue effect *values* were never validated, and one failing effect stopped the rest.** `set_flag` given a list stored one flag named after the list; `advance_quest` naming a template id did nothing while reporting success (active quests are keyed by instance); a `has_item` nested under `all`/`any`/`not` was never id-checked; `give_gold: 0` was a silent no-op; an exception in one effect skipped every effect after it. | `"set_flag": ["a", "b"]` set a flag literally called `['a', 'b']`; 11 of the 14 checks in `test_effect_shapes.py` (`TestRunning`, `TestValidating`) failed against the parent commit. | **Chunk 7, item 2.1.** `EFFECT_SHAPES` in `dialogue/effects.py` says what each effect's value may be; the validator (dialogue *and* knowledge topics) and the vocabulary dump read it. `set_flag` and `give_item` take lists and `{id: qty}`; template quest ids resolve to the active instance and report failure when none is active; each step of `apply_effects` is guarded on its own, in a documented order. The FF4 king sets two flags in one choice. |

Still open, with the plan item that closes each
([chunk 7](../plan/chunks-of-work.md), ROADMAP P11). Each was hit while writing or
playing a slice and has a workaround in the slices unless noted. Every limit that is a
behaviour is pinned as a passing test in `test_adaptation_slices.py` (`TestKnownLimits`,
plus the bomb wall), and the item that closes it reverses that assertion.

| Gap | What happens | Workaround used | Closed by | Pinned by |
|---|---|---|---|---|
| **No triggers.** Nothing fires on entering a room, killing an NPC, or clearing a room; a quest stage can spawn a boss and that is the only event hook. `dispatch_event` handles only `npc_killed`, and its narration is dropped for spell and minion kills; damage-over-time and hazard deaths never reach `die()`, so they drop no loot and can never count as "cleared". Campaign node types `DIALOGUE` and `CUTSCENE` are declared and do nothing. | "Kill everything and the door opens" and scripted scenes cannot be written. | A key dropped by a mini-boss; quest stages and dialogue for the story beats. | 4.1, 4.2, 4.3 | — |
| **An element's effect on a room reverts.** `env_interactions` restore after `duration`, and the timer runs only while someone is in the room. | A bombed wall closes again. | None: the wall is re-bombed. | 3.3 | `test_a_bomb_opens_a_cracked_wall_and_the_wall_closes_again` |
| **Exits gate only on a held key or a skill roll.** No gating on a flag, a quest or a condition, and a key is never consumed. | "Small keys open any door once" and kill-all shutters cannot be written. | One named key per door; a state (the Triad) modelled as an item. | 3.1, 3.2 | `test_limit_a_key_is_never_consumed` |
| **Placed hostile NPCs never respawn, and `respawn_cooldown` is inert for every NPC.** Nothing reads it; friendlies respawn on a global constant; only a region's ambient spawner refills a room. | A dungeon does not refill when you leave and return. | Accepted; bosses use `-1` anyway. | 5.2 | `test_limit_a_placed_hostile_never_respawns` |
| **A hazard weaker than the target's resistance does nothing, silently.** Non-physical damage is reduced by a flat amount first (a fresh hero has 2, and gains 1 a level). | A 2-damage hazard against a hero with 3 resistance never hurt. | Damage of 6 or more. No validator warning exists. | 5.3 | `test_limit_a_hazard_below_the_resistance_draws_no_warning` |
| **`health` on an NPC template is where it starts, not its maximum**, and a template `max_health` is silently ignored (only a placement override is read). | A template `health` of 22 spawned as 22/42, a wounded monster. | The generator solves for the constitution that gives the intended maximum. | 5.1 | `test_limit_a_template_max_health_is_ignored` |
| **No companions.** A summon is temporary and a party is other players. An authored NPC cannot be made to follow and fight beside you (`follower` is inert for authored content). | The FF4 slice has no party. | A summon (Ryn's Titan); Kessa sent ahead by `move_npc`. | 6.1, 6.2 | — |
| **Two validators disagree.** `content_set_validator` accepted an NPC `weapon_damage_type` of `physical`; `reference_integrity_validator` (in the gate) rejects it. | The first run of the gate over the new sets. | Corrected the content. | Unscheduled | — |
| **`dark` rooms are only a sentence.** Nothing consults a light source. | A dark room reads "It is very dark here." and plays the same. | Not used; a candle needs this. | Deferred (`work-tracks.md`) | — |

## Where the engine wants a new primitive

In order, now that persistence is known to be the foundation:

0. **Persistence.** ✅ Done (chunk 7, Phase 1). Everything stateful below is meaningless if a restart forgets it.
1. **Triggers with effects** (on-enter, on-kill, on-room-cleared) running the same
   effect vocabulary dialogue already uses. It is the single change that turns set
   pieces, kill-all-to-open doors and scripted scenes from workarounds into content.
2. **More effects, validated.** ✅ Heal, take gold, raise a stat permanently and a
   validator that checks effect *values* (chunk 7, items 2.1 and 2.3). Still to do:
   spawn or remove an NPC (2.4) and teleport the player (3.4).
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

## What would make this wrong

Two slices are not two games. Tuning here is mine: weapon and boss numbers were set
until the walkthroughs could win, so they say nothing about how a real difficulty
curve would feel. Combat was exercised as a MUD fights (a swing per cooldown), never
as the real-time action the first game is about; that part is a translation, not a
port. The editor was checked for fidelity (a clean round trip, a rendered map, the
room inspector on real content) and not for the labour of building three hundred
rooms by hand, and it has no bulk tool for a grid.
