# The zelda adaptation: the first quest, built whole

`content_sets/zelda1` (to be created; the old proof-sized `zelda_slice` stays until this one replaces it) adapts the first quest of the original
Legend of Zelda for the NES. Like `dq1_slice` it is a **complete** game, finishable in a sitting, and a test of the engine more than a release. The set is data only;
each engine gap below is built as a general feature with the whole chain (`docs/reference/ENGINE_CHANGE_RECIPES.md`: reader, validator, editor, vocabulary,
tests, docs, ledger). Every name is new (`docs/plan/zelda-rename-table.md`); the story and content otherwise follow the original as closely as the engine allows.

## What was settled with the author

* **Scope.** First quest only. About eight overworld regions (forest, lake, graveyard, mountain, desert, coast, ...) with districts for monster groups, and
  every dungeon and cave of the original as its own region. Dungeons keep room count, key count, the item, the boss, and which walls are bombable and which
  rooms shut until cleared, but not the tile grid.
* **Combat.** The engine's own real-time combat. No sword beams. Bow, boomerang, bombs, candles, rod and book are abilities and items built from what the
  engine expresses, and as many of the original's enemy behaviours as possible (below).
* **Hearts.** A literal heart count in the status line with **half hearts**: one point of health is half a heart. Three hearts to start, sixteen at most.
* **Currency.** Rupees (the set names its gold). Capped at 255. **Death returns the hero to the start and keeps the rupees** (and the hearts).
* **Bombs.** Eight to start; upgrades to twelve and sixteen. `use bomb` is the whole input: no direction and no target. It goes off in the room you are in,
  hurts what is there, and fires the room's explosive reaction if it has one (a hidden wall opens, with a message). In a room with nothing to find it is spent.
* **Candles.** The blue candle lights the room you stand in until you leave it, and works **once per room visit**; it is also a weak fire attack, and some enemies
  are weak to fire. The red candle is the same without the limit. Both burn bushes.
* **Reed pipe (the recorder and the whistle are one item).** Played in the right place it reveals the seventh dungeon and, separately, a fairy fountain; played at
  the burrowing eye it shrinks it.
* **Triforce.** All eight pieces are needed to enter the last dungeon, as in the game. The last fight is **not** in a dark room: the tyrant disappears and moves between
  a few rooms of a small final region; the hero must **search** to find and expose him, strike, and he vanishes again. He is finished with the silver arrows.
* **Order of play.** As the original: open, with gates that are items (the raft for the third dungeon's island and the fourth's dock; the ladder; the power bracelet; the
  candle for the burnt bush; the pipe; hearts for the better swords).
* **No maps, no compasses.** Hints come from the old men, in rewritten words.
* **Slices** (each ends with all gates green, a walk-script segment and a commit): (1) start, overworld core and dungeon 1; (2) dungeons 2 and 3, the raft; (3) dungeons 4 to 6;
  (4) dungeons 7 and 8, the pipe; (5) Death Mountain, the last dungeon and the ending; (6) checkpoints and a hand-testing walkthrough.

## The game, in play order (names in brackets are the original's; for this document only)

Overworld items and secrets (from the Wikibooks guide, the Zelda Dungeon and Zelda Archive wikis; **verify an unlisted detail against play before relying on it**):

* A cave in sight of the start gives the **wooden sword**. The **white sword** (a cave above a waterfall) needs five hearts; the **magical sword** (under a movable
  gravestone in the graveyard) needs twelve.
* Heart containers outside the dungeons: one on the lowest row of the south-west map, one in a giant boulder (bomb), one under a burned tree in the east (candle), one on an
  island (raft), one on a far dock (ladder), plus a hidden one behind a bombed boulder's south side.
* The **power bracelet** lies under one of the stone guardians east of the graveyard. It moves rocks and gravestones and opens secret passages.
* A **letter** from a cave, shown to a medicine woman (behind a bombed north wall) lets her sell **red potions** and the **spring water**.
* **Shops.** Blue candle 60; key 100; magical shield 130-160 (the **magical shield** is eaten by a shield-eater); arrows 80; bombs 20; monster bait; hearts 10;
  the **blue ring** at 250 in a hidden shop. Bomb capacity upgrades for 100 rupees (the fifth dungeon's hall), and another in the seventh.
* **Money.** A gambling game inside a tree, 30 and 100 rupee gifts for bombing walls, old men who charge "door repair" for the wall you bombed, a charge for a hungry guard
  (feed it bait).
* **Lost Woods and Lost Hills** (a fixed sequence of directions; a wrong turn sends you back) hide the fifth dungeon and the bracelet's approach.

| # | Dungeon (original) | Where / how in | Item | Boss | Notes |
|---|---|---|---|---|---|
| 1 | The Eagle | a tree-lined entrance, west of the start | bow, boomerang | Aquamentus | wallmasters, bats, bone warriors |
| 2 | The Moon | desert, north-east | magical boomerang | Dodongo | bombs kill the boss |
| 3 | The Manji | lakeside; raft to reach the island heart | raft | Manhandla | a raft is needed for the island |
| 4 | The Snake | needs the raft | ladder | Gleeok (two heads) | a miniboss: Manhandla |
| 5 | The Lizard | Lost Hills puzzle | reed pipe | Digdogger | pipe shrinks the boss; bomb upgrade in a hall |
| 6 | The Dragon | the graveyard side | wand (rod) | Gohma | gleeok miniboss; arrows beat Gohma |
| 7 | The Demon | pipe reveals the entrance | red candle | Aquamentus (second) | feed the hungry guard; bomb upgrade |
| 8 | The Lion | a bush that needs a candle to burn | magic key, magic book | Gleeok (four heads) | key opens every locked door |
| 9 | Death Mountain | Spectacle Rock; all eight shards | silver arrows, red ring | the tyrant | shards required to enter |

## Systems the original has, against what the engine has

| The original | What it needs | Engine today |
|---|---|---|
| Half hearts, hearts as the health display | a display unit | **new**: `ruleset` health display (`hearts`, a unit size); damage already whole |
| Health gates (5 / 12 hearts for better swords) | a condition on max health | check conditions; likely **new** `max_health_at_least` |
| Heart containers | max health up | `raise` effect exists (+2 health = one heart) |
| Bombs: counted, capped, upgraded; open hidden walls; hurt a room; kill Dodongo | a counted consumable with a cap | **new**: counted item with a `cap` and `use` that fires the room's explosive reaction and damages the room; capacity raised by an upgrade |
| Hidden exits found by bombing | env interaction `explosive` | exists (`clear_exit_req`, `permanent`) |
| Candles: light a room until you leave; blue once per visit; burn bushes; fire damage | a use latch per visit; `fire` reaction; light status cleared on leave | dark rooms and `light` exist; **new**: the visit latch; fire env reaction to check |
| Bow and arrows (arrows cost rupees), silver arrows | an ability that costs a currency | **new** (or an item count); silver arrows an item requirement |
| Boomerang: stuns, returns | a stun ability | `status_immune` and stun status exist; the ability is content |
| Reed pipe in a place; shrinks a boss | `requires` + `in_room` exist | exists; the shrink is a phase or an NPC swap (to decide) |
| Raft at a dock, ladder across a gap, bracelet on a rock | exit item requirements | exist |
| Keys: consumed, nine at most; a master key never spent | `locked` + `consume` | exists; a cap on held keys to decide |
| Kill-all rooms, shutters | `room_cleared`, `condition` exits | exist |
| Push a block to open a way | an item-free interaction | **to decide**: `push` as an env reaction, or content-only (a `search`) |
| Dark dungeon rooms | dark rooms | exist |
| Enemy: wallmaster (back to the entrance) | an attack effect `teleport` | `npc_cast` + a spell with `teleport` to check |
| Enemy: shield-eater (takes your shield) | a `steal` of equipment | `steal` exists for items; **to check** for worn items |
| Enemy: zols that split, a mother that bursts | on-death spawn | **new**: `on_death.spawn` (check `spawn_npc` trigger on `npc_killed` first: exists, so content may do) |
| Enemy: multi-headed Gleeok, Manhandla's mouths | parts that die separately | NPC groups with `requires_ally`; heads as separate NPCs; content |
| Enemy: Digdogger, Dodongo | resistances (Dodongo: only explosive hurts) | `resistances` exist |
| Enemy: Gohma (hurt only when the eye is open) | phases with `untouchable` | exist |
| Enemy: wizzrobe (appears, shoots, vanishes) | an NPC that teleports between rooms | **to check**: a behaviour, or phases with an `untouchable` hidden state |
| Enemy: pols voice (arrows only), Patra (orbiting minions) | resistances; `requires_ally` | exist |
| Enemy: armos (wakes when touched), leever (rises) | an ambush NPC | **to check**: an NPC that waits as scenery until you step in |
| Final fight: invisible, found by `search`, exposed, vanishes | a trigger-driven boss | `searched` event, `spawn_npc`/`remove_npc`, `health_below`; **to design**: re-hide after damage taken |
| Rupee cap of 255 | a currency cap | **new** ruleset key (or `purse` cap) |
| Death: start over keeping everything | respawn, gold loss 0 | exists (`ruleset.death`) |
| Money games, door repair charges | a random effect; `take_gold` | **to check** a chance effect |
| Hungry guard, monster bait | an item used on an NPC in a place | `give` to an NPC exists |
| Letter then potion | quest items | content |

"To check" lines are resolved by reading the code at the start of each slice, and the answer goes in this table.

## Engine work, in the order the slices need it

1. **Hearts** (slice 1): health display unit and max-health condition.
2. **Counted items with a cap and `use` that explodes** (slice 1): bombs, the bomb bag upgrade, arrows' cost; the editor authors them.
3. **Candle latch and fire** (slice 1).
4. Enemy mechanics as each dungeon needs them (wallmaster, shield-eater, split, ambush, wizzrobe, multi-part bosses), each with the whole chain.
5. The final boss's disappearing act (slice 5).

## Order of work

1. This plan and `zelda-rename-table.md` agreed (done once the questions in them are answered).
2. Per slice: engine work first with the whole chain, then content, then a growing `toolkit/adaptation_walkthroughs/walk_zelda1.py` segment, tests, commit.
3. A hand-testing walkthrough at the end, like `docs/reference/DQ1_SLICE_WALKTHROUGH.md`.
