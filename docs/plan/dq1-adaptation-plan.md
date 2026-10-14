# The dq1 adaptation: a short game, built whole

`content_sets/dq1_slice` (not yet created) adapts the original Dragon Quest / Dragon Warrior. It is chosen because it is short, linear in
its goal and not party-based: one hero, one story, no scenes that take control away. Unlike `ff4_slice` the aim is a **complete** game, small
and finishable in a sitting, not a proof of concept to broaden later. Everything is renamed (the story uses its own names; see
`CLAUDE.md`). The set is data only; each engine gap below is built as a general feature, with the editor chain, tests and docs
(`docs/reference/ENGINE_CHANGE_RECIPES.md`).

## The story, in play order

Sources: StrategyWiki and Gamer Corner walkthroughs, Wikipedia. Original names in brackets, for this document only.

1. **A king's hall.** The hero, last of an old line, stands before the king (Lorik) of a small walled castle (Tantegel). A demon lord (the Dragonlord)
   took the sacred light (the Ball of Light) and the monsters came; the king's daughter (Gwaelin) was carried off. The king gives a little gold,
   a key and a torch; chests in the castle hold a few more.
2. **The first town (Brecconary).** Buy a first weapon and armour with what you have; grind levels on the plain around the castle, going no farther
   than you can survive. Herbs and keys are for sale. The distance to the castle grows the monsters.
3. **The old line's cave (Erdrick's cave, north).** A cave with no monsters and a tablet that tells the hero what he is: the descendant who will use the
   sun, the rain and a token to make a rainbow.
4. **The ruined north (Garinham).** A town with clues, better arms for sale, and below it a **grave** (Garin's grave) with the **silver harp**, and a
   cursed belt (a trap) among its chests.
5. **The east (Kol).** A town whose keeper has the **staff of rain**, and trades it for the harp. A northern cave with gold and monsters; a mountain
   cave with treasure.
6. **The swamp cave.** One cave that runs under a swamp to the far town, and holds, at its north end, the **Green Dragon** that holds the princess.
7. **The far town (Rimuldar).** The **magic keys** are sold here; with them and the clues of the villagers the **fairy flute** and the **stones of
   sunlight** are found (one is in the cellars, one in a locked room).
8. **The southern cave and its sage.** Goldmen, and an old man who will combine the three relics.
9. **The princess.** Return to the swamp cave and kill the dragon; carry Gwaelin out (she follows; at the king's hall the king takes her back and
   offers his thanks, and she gives the hero "Gwaelin's love", an item that tells him how far he is from the castle: it is a **locator** for the token).
10. **The long journey (Cantlin).** A fortified town far off, guarded by a **Golem** that the flute puts to sleep. It sells the best arms in the
    game.
11. **The ruins (Hauksness).** A destroyed town; the hero searches a floor tile and finds the **old line's armour**.
12. **The token.** With Gwaelin's love in hand, the hero walks the swamp until the distance reads zero and **searches**: the **token**.
13. **The rainbow.** Staff, stones and token to the sage: the **rainbow drop**. Used at the water's edge it makes a **bridge** to the demon
    lord's island (Charlock).
14. **The castle of the demon lord.** A dungeon of dark halls (torches or Radiant), barrier floors that hurt, a **knight** with an axe, and the
    **old line's sword** in a chest in the cellar. At the bottom: the **Dragonlord**.
15. **The choice.** He offers half the world if the hero will join him. "No" starts the fight (a man; then, when beaten, a great dragon).
    "Yes" ends the game in sleep. Victory returns the light; the king offers the kingdom and the hero declines, setting off with the princess.

## Systems the original has, against what the engine has

| The original | What it needs | Engine today |
|---|---|---|
| One hero, one monster at a time | a duel | combat is real time and one-on-one by default: fits |
| Levels, stat growth, spells learned at levels | an XP curve with spells at fixed levels | advancement and `level_required` on spells exist; **check how stats grow per level** (the engine has "no level-up choices", which is what the original has too) |
| Spells: Heal 3, Hurt 4, Sleep 7, Radiant 9, Stopspell 10, Outside 12, Return 13, Repel 15, Healmore 17, Hurtmore 19 | the ten, including teleports and a light | damage/heal/status exist; **teleport spells (Return, Outside), Radiant (light) and Repel (no encounters) are new** |
| A torch, and Radiant, in dark places | dark rooms | **not built**: deferred since the Zelda slice (`work-tracks.md`) |
| Random encounters in fields and forests | weaker near home, stronger far off | placed hostiles with `respawn_cooldown`; **an "encounter zone" for open ground is new** (or a roaming spawner) |
| Doors that need keys (magic keys sold in a town) | consumed keys | exit requirement `locked` with `consume` exists |
| A tablet, rumours, a king who saves your game | NPC text; a save point | dialogue and knowledge exist; `set_respawn` exists |
| Death: half the gold, back to the king | a death penalty and a respawn | respawn exists; **a gold penalty on death is new** |
| Search a tile for a hidden item | a hidden item found by `search` | check `search`/discoveries; **the token needs a "search here" spot, revealed by a distance** |
| Gwaelin's love: "the distance to the castle is N" | an item that reads a number | **new**: an item effect/`use` that reports distance (or a room-graph "steps to X") |
| The princess carried out | a rescued NPC that follows | companions exist; `recruit` and follow |
| The rainbow bridge, used at one tile | an item used at a place that opens a path | `reveal_exit` exists; **an item `use` restricted to a place is to check** |
| Barrier floors that hurt | a hazard | hazards exist |
| The Dragonlord's two forms and the offer | a branching dialogue then a two-phase boss | dialogue and phases exist |
| Gold-poor economy, weapon and armour tiers, selling at half | shops | vendors exist; check sell price (half) |

## Engine status (what has been built for this set)

Built, with their editor authoring, tests and docs (`docs/plan/editor-coverage-ledger.md` has the rows):

| Need | What it became |
|---|---|
| The level table: stats, health, magic, cost to the next level, the cap, spells learned | `ruleset.advancement.level_table` |
| Dark places, a torch, a spell of light | `ruleset.world.dark_requires_light`; a status tag `light`; message `too_dark` |
| Where walking is dangerous | encounter zones, `data/encounters/*.json` |
| Repel and fairy water | a status tag `repel`, honoured by the zones against the hero's defence |
| Return, Outside, Wings | a spell effect (and consumable) running `teleport`; `teleport: {to: "entrance"}` and a region's `entrance` property |
| A spell or item that works only somewhere (not in a cave; at the shore) | `requires` / `requires_message` on abilities and consumables; conditions `in_room`, `room_is` |
| Falling costs gold | `ruleset.death.gold_loss_fraction` |
| The token under a tile | trigger event `searched` (the `search` command) |
| The princess's love, the distance to the castle | effect `tell_distance`; consumable property `reusable` |
| Weapon, armour and shop prices; selling at half | already content (`sells_items`, `sell_rate_multiplier`) |

Still open, to be settled when the set is built:

* **Damage arithmetic.** The original's attack is strength plus the weapon and its defence is half agility plus armour; the engine divides
  the attack stat by a constant (`PLAYER_ATTACK_POWER_STR_DIVISOR`) and mixes dexterity into defence. The numbers will be close, not exact, until
  the divisors are the set's to say.
* **Spell resistance** (the original's "sleep resisted 7 times in 16") and **monster flight/run chance** are not exact mechanics here.
* **The map**: regions, rooms and the way the 20 encounter groups divide them.

## Decisions to make before building

* **Scale and fidelity (decided).** Locations, caves and their floors, items, quests and every number (the level table, spells, arms,
  prices, monsters, encounter groups, treasure) are **1:1** with the original, under new names. The overworld is **not** tile-exact: it is a
  set of regions of a few rooms each, keeping the shape of the original (what lies north, east and south of the castle, and roughly how far).
  The figures are in `docs/plan/dq1-source-notes.md`. This is a test of the engine, not a release.
* **Encounters.** Open ground needs something for "walking is dangerous". The original has 20 encounter groups tied to areas and cave floors, so this is required, not optional. Proposed: a ruleset-level **encounter zone** on a region/room
  (a list of monsters, a chance per move that is higher the farther from the castle) that spawns one monster on entry. Generic, authorable, off by default.
* **Dark rooms.** The castle of the demon lord and several caves need them. Proposed: a room property `dark: true`; unlit, you cannot see
  exits or things; a lit torch (an item with a duration) or Radiant (a spell with a duration) lights it. Generic.
* **The Return/Outside teleports.** Proposed: a spell effect `teleport` to a named place, using the existing `teleport` effect machinery.
* **Names.** All proper nouns are new. A table is made before content.

## Order of work

1. Plan agreed (this document, with the questions above answered).
2. Engine work first, each with the whole chain: dark rooms + light source; encounter zones; teleport and light spells; gold penalty on death;
   the distance item; place-bound item use (as needed).
3. Content in play order: castle, first town, plains, cave of the tablet, north (grave), east (staff), swamp and dragon, far town, southern sage,
   rescue, far journey, ruins, token, rainbow, castle of the demon lord, two-form fight and the ending choice.
4. A scripted walk (`toolkit/adaptation_walkthroughs/walk_dq1.py`), tests in `test_adaptation_slices.py`, a hand-testing walkthrough.

Sources: [StrategyWiki walkthrough](https://strategywiki.org/wiki/Dragon_Warrior/Walkthrough), [Gamer Corner walkthrough](https://guides.gamercorner.net/dw/walkthrough/),
[Wikipedia](https://en.wikipedia.org/wiki/Dragon_Quest_(video_game)). The two walkthroughs disagree on a few giver locations (who trades the staff,
who forges the rainbow drop); the set will follow one story, chosen when its towns are laid out.
