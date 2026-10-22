# Walking through `zelda1`, from the meadow to the Starcrown

A hand-testing route for the whole set: a hero with three hearts and no sword, to Princess Ismera in the Ashgrave Citadel. It is written from the content files and from `toolkit/adaptation_walkthroughs/walk_zelda1.py`, which plays this route by script (294 checks, run it with `.venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_zelda1.py`); `server/tests/singles/test_zelda1.py` pins the same ground in 69 tests. Nobody has yet played it all the way by hand, so treat each "expect" line as a claim to check.

The set adapts the first quest of the NES Legend of Zelda with every name changed (`docs/plan/zelda-rename-table.md`). Fighting is the engine's real-time combat, not the original's action: you cannot dodge, so the hero is hard to hit (a high evasion stat) and creatures hit less often than they swing. A sword blow is one *unit* (8 points of health); a half heart is 8 points, a heart is 16, and the status line shows hearts: `Health: 2½/3 hearts`.

Commands are what you type. `reply N` picks the Nth choice. `cast arrow` (or `cast arrow on <creature>`) shoots; `use bomb` lights a bomb where you stand; `use blue candle` lights the room.

**Shortcuts for testing.** In a test session (`python toolkit/play_script.py zelda1 --debug ...`, or the client's test mode) `checkpoint <name>` puts a fresh character at that point of the story with what was won by then. Names, in story order: `armed`, `crescent`, `pinwheel`, `adders`, `gecko`, `wyvern`, `fiend`, `mane`, `peak`, `ghaldur`. `tp <region> <room>`, `level` and `scene skip` are there too.

**Things to try in every chapter.** `status` (hearts), `inventory`, `abilities`; an empty-handed bomb in an ordinary room (it goes off and does nothing); the same dungeon in a different order; dying (you wake at the meadow with your rupees and your hearts).

**The shape of the map.** There are four overworld regions in a loose cross with the meadow at the centre. East of the lake road is `ardenmoor_east` (lake, waterfall, salt flats, dunes); north of the south road is `ardenmoor_north` (graves, hills, shops); north of the graves is Mount Ashgrave. Rooms are named; `go in` enters a cave or dungeon and `go out` leaves.

---

## 1. The meadow and the old man

1. You start in **The Meadow** with a small shield and nothing else. `status`: `3/3 hearts`.
2. `go in`: a cave with an old man. `talk old man`, `reply 1`: you are given a **wooden sword** and it is in your hand.
3. Walk east, west, and look about. Creatures come out of the grass: **spitters** that spit stones (a small shield halves them).

*Check:* a second `talk` gives nothing more. A spitter dies to one sword blow.

## 2. Kestrel Keep (Dungeon 1)

From the meadow go west to **The Tree-Line Gap**, then `go in`.

1. The keep door, then north to the **Mustering Hall**.
2. **West:** the guardroom, two bone warriors. **North of it:** the Archers' Gallery, three more, with a **bow** on the sill. The door shuts behind you until all three are down. `take bow`; `cast arrow on <creature>` costs a rupee.
3. **East:** the Cistern Gallery, three slimes. **East of it:** the Store, two hurlers and a **whirlwing** (`cast whirlwing`) and a **small key**; also a shutter door.
4. **North:** the Upper Hall, two bats and a **grasping hand** that carries you to the entrance. **East of it:** the Cracked Chamber; `use bomb` and a hidden cache opens (rupees and a bomb).
5. The iron door north of the Upper Hall takes the key. Beyond it the Drake's Roost: **Aquilor**, who throws fire. Six blows of the wooden sword.

*Check:* the first shard (`inventory`), a fourth heart, and the heart is shown in the status line. In the south region, the **Stony Rise** (north-east of the meadow) has a rock that rings hollow: a bomb opens a hollow with 30 rupees.

## 3. The east: the lake road, the lantern shop, the waterfall

1. East of the Lakeshore Reeds is the **east region**. The **Old Dock** has a gap of water east: it wants a raft (later).
2. **Windy Plateau** (north-east): `go in` to the lantern shop; `trade old man`, `list`. Bombs 20, recovery hearts 10, bait 60.
3. **Waterfall Ledge:** `go in`. The old man gives the **pale blade** only to someone with five hearts.
4. **Dry Reeds:** `go in` for a hint: the stone-jaw cannot abide smoke and thunder.

## 4. The Crescent Vault (Dungeon 2)

South through the salt flats to **The Crescent Stones** in the dunes, then `go in`. Cord-snakes, great slimes (which burst into two slimes), a powder store with three bombs, a great worm with the **stormwing**, a key. The jaw's lair has the **stone-jaw**: a sword does nothing (the status shows `deals 0 damage`); **two bombs** kill it. Second shard, a fifth heart, and the old man behind the waterfall now gives the **pale blade** (attack goes from 8 to 16).

## 5. The Pinwheel (Dungeon 3)

**Lake Sorrel, West Shore** has the round black door. Great slimes that split, bone warriors, bats, a raft in a room that shuts until the slimes are down, a hidden closet, a hand. The **snap-jaw bloom** in the last room cannot be struck while any of its four mouths lives; the attack tells you why. Third shard and a sixth heart. With the **raft** you can cross from the Old Dock to the island; take the **heart container** there (seventh heart).

## 6. The north: shops, a bush, the Lost Hills

1. North of the south road: **The Eastern Rise** has a candle shop (blue candle 60); **The Withered Wood** a shield shop (magical shield 130). The magical shield is eaten by the shield-eaters later and is gone for good.
2. **The Hill Road** has a thick bush. `use blue candle`: it burns; the doorway shows. A heart container inside. A blue candle works **once in each room**: the second `use` says "already burns"; leave the room and it works again.
3. **The Standing Stones** (north-west): `go in` is the **Lost Hills**. North five times, no step aside; a step east or west puts you back at the start. At the top, `go in`.

## 7. The Gecko Halls (Dungeon 5)

Dark: `look` in the Long Gallery shows only "It is pitch dark." Light a candle. Bats, revenants, bone warriors, a hexer that flickers in and out (strike when it is there), the **reed pipe**, a nook where an old man sells a **bomb bag** (100 rupees; twelve bombs). The heaving floor: the **burrowing eye** is untouchable by anything. `use reed pipe` there and it shrinks to a small eye you can fight. Fifth shard.

The reed pipe has three more places: `use reed pipe` at **The Black Pool** (north region, centre) opens a stair to a **fairy pool** where the fairy heals every wound; at **The Quiet Bay** (below) it opens the Fiend's Hold.

## 8. The Adder's Coil (Dungeon 4) and the far dock

From the island go north with the raft to **The Far Shore**, then `go in`. Hexers, bone warriors, the **ladder** in a shut room. The boss is **the hydra**: a body behind two heads. The body cannot be struck until both are dead. Fourth shard. With the ladder, go east of the far shore to the **Far Dock** for another heart container.

## 9. The Wyvern Deep (Dungeon 6)

North of the Hollow Graves, `go in`. Revenants, hexers, a lesser hydra guarding the **wyrmrod** (`cast wyrmrod`), shield-eaters (`devour shield`: a magical shield worn on the arm may be swallowed), a dark stair. The **great claw** at the bottom: swords and bombs do nothing; its eye opens for six seconds in twelve, and **arrows** (a rupee each) hurt it. Sixth shard.

## 10. The hungry brute, the Fiend's Hold (Dungeon 7)

North of **The Cliff Path** (east region, north-west corner) is a narrow pass blocked by a **hungry brute**. `buy bait` in the lantern shop, `talk brute`, `reply 1`. Beyond it, **The Quiet Bay**: `use reed pipe`. In the Hold: ironclads, strong hexers, the **red candle** (no limit per room), a **large bomb bag** (sixteen). **Aquilor the Elder** at the top. Seventh shard.

## 11. The Mane (Dungeon 8)

**The Burnt Rise** (east of Windy Plateau): a bush over a door. `use red candle`. Inside: the **tome of cinders** (with the wyrmrod, `cast wyrmflame`), the **open key** (a master key: it opens every lock and is never spent), blue ironclads, and **the great hydra** with four heads. Eighth shard. By now you should have about fourteen hearts.

## 12. Odd corners worth visiting

* A bomb at **Briar Hollow**'s corner (`as_2_0`, south-west) opens a ruined home; the old man bills you 20 rupees.
* A bomb in **The Whispering Pines** opens a hollow where a ring shop sells the **sapphire band** (250).
* The scribe's cave in **Reed Marsh** gives a letter; a bomb at **The Southern Road** opens a medicine shop that sells a red draught only to someone who shows it.

## 13. The graveyard and the mountain

North of **The Hollow Graves**: **The Old Stones**. East of it, **The Stone Guardians**: `search` wakes one (three blows of the sword); it leaves the **strongarm bracer**. At the Old Stones, `use strongarm bracer`: the big stone grinds across, and `go in` shows an old man who gives the **dawn blade** only to someone with twelve hearts. North: the mountain, and the **Hollow Peak**. Seven shards do not open the door; eight do.

## 14. The Ashgrave Citadel and Ghaldur

A dark keep of blue ironclads, shield-eaters, a sand worm, hexers. A niche holds the **ruby band**, a hall of silver chains holds the **silver arrows** behind the **eye-swarm** (six eyes ring a great eye; the great eye is guarded until they fall). The iron door to the north takes the key (or the open key).

At the top, **Ghaldur's lair** is three round galleries. Nothing is in them that you can see.

1. In the first gallery, `search`. The air folds back; Ghaldur is there. Strike him. When you have hurt him past the line he flinches and is gone.
2. `search` the wrong room and nothing happens. He is in the *next* gallery. `search` there, strike again; again he is gone.
3. The third stage ends in the first gallery again.
4. The fourth time he has nothing left to hide behind. A sword does nothing; **`cast silver arrow`** (a rupee each) does.
5. When he falls, a stair opens behind the throne. The princess is at the top. `talk princess`, `reply 1`: give her the eight shards, and the Starcrown is whole.

*Check:* each vanish moves him to the next room; a search elsewhere finds nothing; the silver arrow is refused without the bow or the rupee.

---

## What to look for when you play it for balance

* The first hour. A bare-handed hero can only run; once you have the sword, spitters should die in a blow and cost you a quarter heart at most.
* Dungeon 1's archers' gallery. Three bone warriors at once should cost about a heart and a half, not three.
* The stone-jaw. If a sword does nothing and no one tells you, you wander; the hint cave is the answer. Does the old man's line read as a hint?
* Rupee income. The shops want 60, 100, 130, 250 and 40 each; creatures drop 1 to 12. You should not need to farm for a single dungeon's purchase.
* Dark rooms. A bright hall followed by darkness is the point; does `use candle` feel like the answer?
* Ghaldur's hunt. Three searches should be enough. If you are searching a room twice, the flags are wrong; tell me the room.

## Known approximations

* Dungeon layouts, key counts and enemy mixes follow the original in shape, not tile for tile.
* The great hydra and the lesser hydra use the same head template; each body counts only the heads in its own room.
* Rings are worn on the `hands` slot because the engine has no ring slot.
* The original's tree money game, the free-100-rupees cave, and a few more secrets are not in. They are content only and easy to add.
* The old `zelda_slice` set is still in the tree.
