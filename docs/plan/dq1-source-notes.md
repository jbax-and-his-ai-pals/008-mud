# dq1: the original's numbers, as collected

Research record for `docs/plan/dq1-adaptation-plan.md`. Taken from the Gamer Corner Dragon Warrior guides
(`guides.gamercorner.net/dw/...`), which were read through a summariser: **verify a figure against a second source before it goes into content.**
Gaps (levels 21 to 30, 20 of 40 monsters, some chests) are marked and are filled from the same site when the content is written.
Original names are used here only; the set renames everything.

## Version

The target is the **NES release, Dragon Warrior** (1989, North America). The later remakes (Game Boy Color, mobile, Switch) and the
Japanese Famicom Dragon Quest differ in numbers, names and a few quests; where a source disagrees, prefer the NES figure. The tables below come from a
guide for that release (it uses its spellings, including "Tantagel" in places), but two details disagree between the guides read and need a check
against the NES game itself: who trades the staff (the sage in the Northern Cave, for the silver harp, is what is recorded here) and who
combines the rainbow drop (the sage in the Southern Cave, for the stones, the staff and the token).

## Settled quest givers (NES)

* The sage in the Northern Cave trades the **staff of rain** for the **silver harp**.
* The sage in the Southern Cave makes the **rainbow drop** from the stones, the staff and the token.
* Cumulative experience to reach a level: 7, 23, 47, 110, 220, 450, 800, 1300, 2000, 2900, 4000, 5500, 7500, 10000, 13000, 16000, 19000,
  22000, 26000 (level 20), then 30000 to 62000 in steps of 4000, then 65000 (level 30). A `level_table` row's `xp` is the cost to the **next** level.

## Fidelity rule

Locations, caves, floors, items, quests and the numbers in these tables are kept **1:1**. The overworld map is not tile-exact: it is a set of
sensible regions that keep the shape of the original (what lies north, east, south of the castle, and how far).

## Levels (experience is per level; cumulative thresholds are the running sum)

| L | XP to reach (from previous) | Str | Agi | HP | MP | Spell |
|---|---|---|---|---|---|---|
| 1 | 0 | 4 | 4 | 15 | 0 | |
| 2 | 7 | 5 | 4 | 22 | 0 | |
| 3 | 16 | 7 | 6 | 24 | 5 | Heal |
| 4 | 24 | 7 | 8 | 31 | 16 | Hurt |
| 5 | 63 | 12 | 10 | 35 | 20 | |
| 6 | 110 | 16 | 10 | 38 | 24 | |
| 7 | 230 | 18 | 17 | 40 | 26 | Sleep |
| 8 | 350 | 22 | 20 | 46 | 29 | |
| 9 | 500 | 30 | 22 | 50 | 36 | Radiant |
| 10 | 700 | 35 | 31 | 54 | 40 | Stopspell |
| 11 | 900 | 40 | 35 | 62 | 50 | |
| 12 | 1100 | 48 | 40 | 63 | 58 | Outside |
| 13 | 1500 | 52 | 48 | 70 | 64 | Return |
| 14 | 2000 | 60 | 55 | 78 | 70 | |
| 15 | 2500 | 68 | 64 | 86 | 72 | Repel |
| 16 | 3000 | 72 | 70 | 92 | 95 | |
| 17 | 3000 | 72 | 78 | 100 | 100 | Healmore |
| 18 | 3000 | 85 | 84 | 115 | 108 | |
| 19 | 3000 | 87 | 86 | 130 | 115 | Hurtmore |
| 20 | 4000 | 92 | 88 | 138 | 128 | |
| 21 to 30 | to reach: 30000, 34000, 38000, 42000, 46000, 50000, 54000, 58000, 62000, 65000 (cumulative) | interpolated | interpolated | interpolated | interpolated | none |

Levels 21 to 30: the experience is the original's; the other columns are **interpolated** in a straight line from level 20 towards the level-30
maximum of one name (strength 136, agility 126, HP 195, MP 193), because the NES hero's growth depends on the letters of the name. The cap is 30.

## Spells

| Spell | MP | Level | Hero | Monster |
|---|---|---|---|---|
| Heal | 4 | 3 | 10 to 17 HP | 20 to 27 |
| Hurt | 2 | 4 | 5 to 12 | 3 to 10 |
| Sleep | 2 | 7 | sleep | sleep |
| Radiant | 3 | 9 | light, radius 3 | |
| Stopspell | 2 | 10 | blocks casting | blocks casting |
| Outside | 6 | 12 | warps from inside a cave to its entrance | |
| Return | 8 | 13 | to the king's castle | |
| Repel | 2 | 15 | weaker enemies stay away | |
| Healmore | 10 | 17 | 85 to 100 | 85 to 100 |
| Hurtmore | 5 | 19 | 58 to 65 | 30 to 45 |
| Breath of fire (1) | | | | 16 to 23 |
| Breath of fire (2) | | | | 65 to 72 (the Dragonlord's second form) |

## Arms

| Weapon | Atk | Buy | Where |
|---|---|---|---|
| Bamboo pole | 2 | 10 | Brecconary, Cantlin |
| Club | 4 | 60 | Brecconary, Garinham, Cantlin |
| Copper sword | 10 | 180 | Brecconary, Garinham, Kol, Rimuldar, Cantlin |
| Hand axe | 15 | 560 | Garinham, Kol, Rimuldar, Cantlin |
| Broad sword | 20 | 1500 | Rimuldar, Cantlin |
| Flame sword | 28 | 9800 | Cantlin (locked shop) |
| Erdrick's sword | 40 | not sold | Charlock Castle |

| Armour | Def | Buy | Where |
|---|---|---|---|
| Clothes | 2 | 20 | Brecconary |
| Leather armour | 4 | 70 | Brecconary, Garinham, Cantlin |
| Chain mail | 10 | 300 | Garinham, Cantlin |
| Half plate | 16 | 1000 | Garinham, Kol, Rimuldar |
| Full plate | 24 | 3000 | Kol, Rimuldar, Cantlin |
| Magic armour | 24 | 7700 | Rimuldar, Cantlin |
| Erdrick's armour | 28 | not sold | Hauksness |

| Shield | Def | Buy | Where |
|---|---|---|---|
| Small shield | 4 | 90 | Brecconary, Kol |
| Large shield | 10 | 800 | Garinham, Cantlin |
| Silver shield | 20 | 14800 | Cantlin (locked shop) |

Everything sells for half. Erdrick's pieces sell for 1.

## Items

| Item | Effect | Buy | Where |
|---|---|---|---|
| Herb | 23 to 30 HP | 24 | Brecconary, Garinham, Kol, Cantlin |
| Magic key | opens one door | 53 (85 at Tantegel, 98 at Cantlin) | Tantegel, Rimuldar, Cantlin |
| Torch | light radius 1 | 8 | Brecconary, Garinham, Kol, Cantlin |
| Fairy water | weaker enemies stay away | 38 | Brecconary, Cantlin |
| Wings | to the king's castle | 70 | Kol, Cantlin |
| Dragon's scale | +2 defence, permanent | 20 | Brecconary, Garinham, Kol, Cantlin |
| Fairy flute | puts the Golem to sleep | | Kol (search four steps south of the bath) |
| Fighter's ring | no effect | sell 15 | Mountain Cave |
| Erdrick's token | proves the line | | the overworld (search) |
| Gwaelin's love | shows your place and the XP to the next level | | Tantegel (princess) |
| Cursed belt | cursed; stops you entering the castle | 180 | Garinham, Charlock |
| Silver harp | calls a weak monster | | Garinham (grave) |
| Death necklace | cursed | 1200 | Mountain Cave (1/32 chance) |
| Stones of sunlight | with the staff, the rainbow drop | | Tantegel B1 secret room |
| Staff of rain | with the stones, the rainbow drop | | Northern Cave |
| Rainbow drop | makes the bridge | | Southern Cave |

## Places (offset from the castle, floors, inn, locked doors)

| Place | Floors | Position | Inn | Doors | Contents |
|---|---|---|---|---|---|
| Tantegel Castle | 1F 2F B1 | 0 | | 3 | 120 gold, torch, key, 4 x 6-13 gold, Stones of Sunlight (B1 secret), Gwaelin's love |
| Brecconary | 1F | 2N 5E | 6 | 2 | |
| Erdrick's Cave | B1 B2 | 31N 15W | | | the tablet |
| Garinham | 1F B1-B4 | 41N 41W | 25 | 3 | torch, herbs, gold, cursed belt, silver harp (B-floors) |
| Kol | 1F | 33N 61E | 20 | 2 | Fairy flute |
| Northern Cave | B1 | 42N 38E | | | Staff of rain |
| Mountain Cave | B1 B2 | 14S 14W | | | herb, torch, fighter's ring, gold, death necklace |
| Swamp Cave | B1 | 1S 61E | | 1 | (leads to the dragon) |
| Rimuldar | 1F | 29S 59E | 55 | 2 | Wings (inn chest) |
| Southern Cave | B1 | 66S 65E | | | Rainbow drop (sage) |
| Cantlin | 1F | 59S 30E | 100 | 5 | |
| Hauksness | 1F | 46S 18W | | | Erdrick's armour |
| Charlock Castle | 1F B1-B7 | 5S 5E | | 3 | Erdrick's sword, herbs, 500-755 gold, key, wings, cursed belt |

## Shops

* **Brecconary:** bamboo pole, club, copper sword, clothes, leather armour, small shield; herb, torch, dragon's scale; fairy water (behind a door).
* **Garinham:** club, copper sword, hand axe, leather armour, chain mail, large shield, half plate; herb, torch, dragon's scale.
* **Kol:** copper sword, hand axe, small shield, half plate, full plate; herb, torch, dragon's scale, wings.
* **Rimuldar:** copper sword, hand axe, half plate, broad sword, full plate, magic armour; magic key.
* **Tantegel:** magic key (behind a door).
* **Cantlin:** north: bamboo pole, club, copper sword, leather armour, chain mail, large shield, herb, torch; south: hand axe, broad sword, full plate, magic armour, dragon's scale, wings; locked: flame sword, silver shield; fairy water; magic key.

## Monsters seen (20 of 40)

HP is a range; XP and gold; abilities with their rates.

| Monster | HP | XP | Gold | Abilities |
|---|---|---|---|---|
| Drakee | 5-6 | 2 | 2 | |
| Ghost | 6-7 | 3 | 3-4 | |
| Magidrakee | 12-15 | 5 | 9-11 | Hurt 2/4 |
| Druin | 17-22 | 7 | 12-15 | |
| Poltergeist | 18-23 | 8 | 13-17 | Hurt 3/4 |
| Droll | 19-25 | 10 | 18-24 | |
| Drakeema | 16-20 | 11 | 15-19 | Heal 1/4, Hurt 2/4 |
| Specter | 28-36 | 18 | 52-69 | Sleep 1/4, Hurt 3/4 |
| Druinlord | 27-35 | 20 | 63-84 | Heal 3/4, Hurt 1/4 |
| Drollmagi | 29-38 | 22 | 67-89 | Stopspell 2/4 |
| Knight | 42-55 | 33 | 97-129 | Stopspell 2/4 |
| Goldman | 38-50 | 6 | 150-199 | |
| Green Dragon | 49-65 | 45 | 120-159 | Fire 1/4 |
| Golem | 53-70 | 5 | 7-9 | |
| Axe Knight | 53-70 | 54 | 123-164 | Sleep 1/4 |
| Blue Dragon | 53-70 | 60 | 112-149 | Fire 1/4 |
| Red Dragon | 76-100 | 100 | 105-139 | Sleep 1/4, Fire 3/4 |
| Stoneman | 121-160 | 65 | 105-139 | |
| Dragonlord (1) | 76-100 | | | Stopspell 1/4, Hurtmore 3/4 |
| Dragonlord (2) | 130 | | | Fire (2) 2/4 |

Not yet read: Slime, Red Slime, Magician, Scorpion, Skeleton, Warlock, Metal Scorpion, Wolf, Wraith, Metal Slime, Wolflord, Wyvern,
Rogue Scorpion, Wraith Knight, Magiwyvern, Demon Knight, Werewolf, Starwyvern, Wizard, Armored Knight.

## Encounter groups (20; five monsters each, drawn at random)

| # | Area | Monsters |
|---|---|---|
| 1 | around the castle | Slime x3, Red Slime x2 |
| 2 | outer castle | Red Slime x3, Slime, Drakee |
| 3 | north | Slime, Ghost x2, Drakee, Red Slime |
| 4 | Garinham area; east of the castle | Red Slime x2, Drakee, Ghost, Magician |
| 5 | west of Kol; south of Garinham; SE of the Mountain Cave | Ghost, Magician, Magidrakee x2, Scorpion |
| 6 | Mountain Cave B1; Swamp Cave | Ghost, Magician, Scorpion, Druin x2 |
| 7 | east of Kol; around the Mountain and Northern Caves | Ghost, Magician, Magidrakee, Scorpion, Skeleton |
| 8 | north of Rimuldar | Magidrakee, Scorpion, Skeleton, Warlock, Wolf |
| 9 | Garinham B1; Mountain Cave B2 | Poltergeist, Droll, Drakeema, Skeleton, Warlock |
| 10 | around Rimuldar; Garinham B2 | Skeleton, Warlock, Metal Scorpion, Wolf x2 |
| 11 | south of Rimuldar; NE of Hauksness | Metal Scorpion, Wraith, Wolflord x2, Goldman |
| 12 | Southern Cave area; SW bridge | Wraith, Wyvern x2, Wolflord, Goldman |
| 13 | Garinham B3, B4 | Specter, Wolflord, Druinlord, Drollmagi, Wraith Knight |
| 14 | west of Hauksness | Wyvern, Rogue Scorpion, Wraith Knight, Knight, Demon Knight |
| 15 | south of Hauksness | Wraith Knight, Knight, Magiwyvern, Demon Knight, Metal Slime |
| 16 | outer Cantlin; the dragon's isle | Knight, Magiwyvern, Demon Knight, Werewolf, Starwyvern |
| 17 | Cantlin area; Hauksness | Werewolf, Green Dragon, Starwyvern x2, Wizard |
| 18 | Charlock 1F, B1 | Werewolf, Green Dragon, Starwyvern, Wizard, Axe Knight |
| 19 | Charlock B2 to B4 | Wizard, Axe Knight, Blue Dragon x2, Stoneman |
| 20 | Charlock B5 to B7 | Wizard, Stoneman, Armored Knight x2, Red Dragon |
