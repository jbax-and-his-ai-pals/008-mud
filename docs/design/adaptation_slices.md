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

Still open. Each was hit while writing or playing a slice, and each has a workaround
in the slices unless noted.

| Gap | What happens | Workaround used |
|---|---|---|
| **No triggers.** Nothing fires on entering a room, killing an NPC, or clearing a room. A quest stage can spawn a boss (`spawn_on_start`, `spawn_on_entry`) and that is the only event hook. Campaign node types `DIALOGUE` and `CUTSCENE` are declared and do nothing. | "Kill everything and the door opens" and scripted scenes cannot be written. | A key dropped by a mini-boss; quest stages and dialogue for the story beats. |
| **An element's effect on a room reverts.** `env_interactions` restore after `duration`. | A bombed wall closes again (`test_a_bombed_wall_closes_again_after_its_duration` documents it). | None: the wall is re-bombed. |
| **Exits gate only on a held key or a skill roll.** No gating on a flag, a quest or a condition, and a key is never consumed. | "Small keys open any door once" cannot be written. | One named key per door; a state (the Triad) modelled as an item. |
| **Placed hostile NPCs never respawn.** `respawn_cooldown` on a hostile template does nothing: 920 s after a kill the monster is still gone. Only a region's ambient spawner refills a room. | A dungeon does not refill when you leave and return. | Accepted; bosses use `-1` anyway. |
| **`set_flag` takes one name.** Given a list it stores a single flag named after the list, and the validator checks effect *names* only, never their values. | `"set_flag": ["a", "b"]` set a flag literally called `['a', 'b']`. | One flag per choice. |
| **A hazard weaker than the target's resistance does nothing, silently.** Non-physical damage is reduced by a flat amount first. | A 2-damage hazard against a hero with 3 resistance never hurt. | Damage of 6 or more. No validator warning exists. |
| **`health` on an NPC template is where it starts, not its maximum.** The maximum comes from constitution and level. | A template `health` of 22 spawned as 22/42, a wounded monster. | The generator solves for the constitution that gives the intended maximum. |
| **Two validators disagree.** `content_set_validator` accepted an NPC `weapon_damage_type` of `physical`; `reference_integrity_validator` (in the gate) rejects it. | The first run of the gate over the new sets. | Corrected the content. |
| **No companions.** A summon is temporary and a party is other players. An authored NPC cannot be made to follow and fight beside you. | The FF4 slice has no party. | A summon (Ryn's Titan); Kessa sent ahead by `move_npc`. |
| **No classes or jobs, and nothing permanent.** A title grants nothing; no effect raises maximum health or a stat, and no dialogue effect heals. | The "class change" is a title; a heart container heals. | Healers, vendors and the fairy pool for recovery. |
| **`dark` rooms are only a sentence.** Nothing consults a light source. | A dark room reads "It is very dark here." and plays the same. | Not used. |
| **Persistence is unverified.** In a headless restart with a real database file, `char create` made a new character and a lever's or a bomb's change to the world was not restored. That may be the harness rather than the engine. | `probe_persist` (see below). | Not concluded. Worth checking on the real transports before a story depends on it. |

## Where the engine wants a new primitive

In order of how much of both games it would unlock:

1. **Triggers with effects** (on-enter, on-kill, on-room-cleared) running the same
   effect vocabulary dialogue already uses. It is the single change that turns set
   pieces, kill-all-to-open doors and scripted scenes from workarounds into content.
2. **More effects.** Heal, spawn or remove an NPC, teleport the player, change a
   room, raise a stat permanently, and a validator that checks effect *values*.
3. **Conditions on exits**, and consumable keys.
4. **Persistent room changes** (an option on `env_interactions`).
5. **A follower NPC**: an authored ally that joins, fights and can be dismissed.

## Replaying it

```bash
# the load-bearing moments, deterministic (bosses set to one hit point)
cd server && ../.venv/Scripts/python.exe -m unittest tests.singles.test_adaptation_slices

# the whole run, meant to be watched (combat is random; a boss can win)
.venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_zelda.py --verbose
.venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_ff4.py --verbose

# two questions the slices raised (the answers are in each script's header)
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
rooms by hand, and it has no bulk tool for a grid. Persistence is not settled.
