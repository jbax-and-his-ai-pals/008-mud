# Walking through `dq1_slice`, from the throne room to the end

A hand-testing route for the whole set: from King Aldric's throne room in Telgard to Maldrath's defeat and the king's offer of the crown. It is written from the content files and from `toolkit/adaptation_walkthroughs/walk_dq1.py`, which plays this route by script (108 checks, run it with `.venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_dq1.py`). Nobody has yet played it all the way by hand, so treat each "expect" line as a claim to check.

The set adapts the NES release of Dragon Warrior with every name changed (`docs/plan/dq1-rename-table.md`). The fighting is the engine's real-time combat, not turn-based, so expect fights to be short and numbers to be close, not identical.

Commands are what you type. `reply N` picks the Nth choice in a conversation. Directions are the ones the walk script uses; overland stretches are given as a rough run ("east along the road") because the fields are a grid and a wrong turn costs only time.

**Shortcuts for testing.** In a test session (the client's test mode, or `python toolkit/play_script.py dq1_slice --debug ...`) `checkpoint <name>` puts a fresh character at that point of the story, with level, gear, items and flags. Names, in story order: `armed`, `vault`, `barrow`, `hermit`, `tunnel`, `court`, `sage`, `shore`, `throne`. `level`, `tp` and `scene skip` are there too. Note that `tunnel` drops you into the drake's den with the drake already there, so be ready to fight, or use `court` onward instead.

**Things to try in every chapter.** `journal`; `status`; `look` after every move in a dark place; fighting at low health (you can die: you lose half your gold and wake at the throne room); buying, selling and the number shown against the price; `search` in any room that looks like it hides something.

**The rules of this game that differ from a normal set:**
- Your level comes from the level table, not from gear or stats alone; your stats are set by it (strength, agility, health, mana, spells).
- Dark places show nothing: no name, no description, no exits. Moving blind either works or tells you there is a wall. A torch (`use pitch torch`) or the spell Glimmer lights them for a while.
- Monsters find you on the open ground; the ones you flee from are gone when you move on. The Dawnglass (the end) silences them all.
- Death costs half your gold and sends you back to the king.

---

## 1. Telgard: the king and the treasury

1. You start in the throne room with nothing and no gold. `talk king`, `reply 1`. Expect the king's charge (rescue the princess, find the Dawnglass); the flag `met_king` is set.
2. `go south` to the treasury. `open royal coffer`, `take all from royal coffer`; the same for the `cedar box` and the `iron-banded chest`. Expect 120 gold, a pitch torch and a brass key between them.
3. `go north`, `go down` to the great hall. `go west`: the storeroom is locked, and the key is spent opening it. `open storeroom chest` and take: four small purses of gold (repeat the open and take for each).
4. `go east` twice: the keysmith's hall is locked and you have no key left, so it will not open.

*Check:* the key is gone after the storeroom; the treasury chests are one-time; the king's second talk does not repeat the charge.

## 2. Out into the fields, and Bracken Ford

1. `go south` twice to the castle gate. You are on the fields (a 5 by 4 grid). Something finds you after a few steps. Fight it (`attack <name>`); you will lose a lot of health the first time. A dead monster pays gold and experience.
2. Go east along the road to **Bracken Ford** (four steps east of the gate, then the gate room). Its chapel is north-east of the square.
3. The armoury is north of the inn side street: `trade armourer`, `list`, `buy bronze blade` (180 gold), `equip bronze blade`. You will need to fight to earn the gold; the walk script cheats this with a gift of 500 gold, you should not.
4. The inn: `talk innkeeper`, `reply 1`. A bed costs 6 gold here (it is dearer in later towns). You heal fully.

*Check:* prices read against the NES tables (bronze blade 180); selling gets half; you cannot equip a thing you do not own; a fight that is too hard can be fled (`go` out of the room), and the foe is left behind.

## 3. The north: Ostrun's Vault and Harrowmere

1. From the castle gate go west, then north three times: the moors, then a stone door in a hillside (Northmarch). `go down`.
2. **The vault is dark.** `look` shows only "pitch dark". `go north` says there is no way. `use pitch torch`, `look`: now you see the vault door. From here: east, down, east, north to the **sanctum**. `look at stone tablet`: it names the sunstones, the signet and the moon harp, the three things you will need.
3. Back out: south, west, up, west, up.
4. Go to **Harrowmere** (west of the moors). `trade provisioner` to see wyrm scale on the list. Go west, south: a shuttered house that wants a key. Buy or use a spare brass key. Inside, three chests (oak, pine, elm): gold, a torch and healing moss.
5. From the gate go west, south, then north and east to the **graveyard** on the hill.

## 4. Harrow's Barrow (four floors, dark)

Light a torch on the way down; the floors are dark and a torch lasts a while.

1. From the graveyard: down, north, east: a cell with a `mouldering chest` (moss). West, north: the Hall of Lamps and a `rotted chest` (gold). Southeast: an oak door opened by a key, with a `barrow chest` (gold). Back northwest, east, down.
2. Second floor: north, north, down to the third floor landing.
3. Third floor: north, west: the `black coffer` holds a **gravebound circlet** (cursed; see below). East, east: the `silver-bound chest` holds the **moon harp**.
4. `use moon harp`: it calls something of the dark. Fight it or not.
5. The way out. By level 13 you have **Egress** (out of a cave to the entrance) and **Recall** (home to Telgard). `cast recall` underground: it refuses. `cast egress`: you are at the graveyard. `cast recall`: you are in Telgard's courtyard.

*Check:* Recall refuses underground with a sensible message; Egress works in a cave and is useless in the open; the harp's monster is not a boss.

## 5. The curse (do this on purpose)

1. Put on the circlet: `equip gravebound circlet`. It cannot be taken off.
2. Walk back to the castle gate and try `go north`: the gate turns you away because you are cursed.
3. Go to Bracken Ford's chapel (from the courtyard: south, east, east, east, north). `talk priest`, `reply 1`. Expect the circlet lifted from your head and gone from your pack.

*Check:* the curse really blocks the castle; the priest's free service works once and does not take your gold.

## 6. The east: Kalder, the hermit, the cavern, the drake and the princess

1. Take the east road from Bracken Ford to **Kalder** (a long walk east). In the back lane (four steps south of the bath, lane 4) type `search`: you find a **slumber pipe**. A second `search` finds nothing.
2. West of the gate is an old locked house; it takes a key.
3. North and east to **Frostfell Hollow** and the **Hermit's Hall**. Without the harp, `talk hermit` gives you nothing. With the moon harp, `talk hermit`, `reply 1`: you get the **cloudcaller's staff**, he keeps the harp.
4. **Greyhorn Cavern** (south-east of the hollow). From its landing the chests are: up, south, east (cavern chest); the torch room (stone chest); the band room (iron-bound chest: a brawler's band); the gold room (lidded chest, over a hundred gold); and a hidden trove (heavy chest). The cavern is dark.
5. **Mirewater Tunnel**: a long walk east and then down. At the end is the drake's den. Be at least level 15 with a good weapon and some moss. `attack drake`. The drake is level 21 and hurts. When it falls, wait a few seconds: the way north to the cell is shown.
6. `go north` (the iron door yields to a key). `talk princess`, `reply 1`: she walks with you. Do not lose her; she follows from room to room and she cannot be hurt.
7. Walk home to the throne room (south, west, north, north, up, north, north, then a long run west). Wait about 20 seconds: the king takes his daughter. `talk princess`, `reply 1`: she gives you her **locket**.
8. `use elowen's locket` out in the fields: it tells you how many steps you are from the castle. It is not used up.

*Check:* the princess is "with you" in `companions`, follows you home, and the king's talk afterwards reads differently (victory options appear later); the locket works anywhere.

## 7. The south-east: the sunstones, Rivenhal, the sage

1. In Telgard, under the castle (down, down, south from the throne room) is a `stone casket`: the **sunstones**.
2. Leave Mirewater by its southern mouth (from the den: west, south, south, south). You are in the **Fenlands**. East is **Rivenhal**'s east gate.
3. In Rivenhal: the locksmith (east, south) sells brass keys (about 52 each). The strongroom (east, east, north, north) is behind two locked doors; its `inner chest` holds a **homing feather**. The armourers' row (east, north) sells spellwoven mail and a plate harness.
4. West and south through the **Sagehollow** to the sage's hall. Without the three things (sunstones, staff and signet) the sage only waits. With them, `talk sage`, `reply 1`: they are consumed and you get the **prism tear**. (The signet must be found first in the fen; see section 8; the walk script just gives you one.)

## 8. The south: the colossus, Cairnwall, Haskarth, the fen

1. South from the sage along the road to the **Southwilds**. At the road south there is a **colossus** you cannot walk past. `go south` and it blocks. `use slumber pipe on mossback colossus`: it sleeps. `go south` again: the gate of **Cairnwall**.
2. Cairnwall: the key shop (plaza, east, east) sells keys for about 98. The vault armoury (plaza, south, west, behind a locked door) sells **emberbrand** and the **moonsilver shield**. The inn (plaza, south): a bed costs 100.
3. **Haskarth** (nine steps back, through the trees and an entrance "in"). The street, then east, north: the grove behind the armoury. `search` before killing the **cleaver knight** finds nothing. Kill it (`attack cleaver`), `search` again: **Ostrun's mail**.
4. The fen end of the Southwilds is 39 steps from the castle. Stand there and `use elowen's locket`: it says so. Then `search`: the **signet**.

## 9. The shore, the isle and the end

1. Be around level 26 or higher, armoured with mail and the moonsilver shield, with torches and moss. Go to the **dark shore** (east, east, south, east from the castle gate). `go east`: no way across the water. Use the prism tear *only here*; elsewhere it tells you it will not work.
2. A rainbow bridge forms. Cross onto **Skarn Isle** (the landing, the blasted shore, the approach, the iron gate). Go north three times and in: the **Black Hall**.
3. The first floor is lit, the rest is dark. From the hall: north, down, east, north, down, east: the **Sealed Chamber** with an iron strongbox holding **Ostrun's edge**. `equip ostrun's edge`.
4. Descend through the floors, fighting. The fifth and sixth floors have burning and poisoned floors: your health ticks down as you stand on them. Keep moving, keep the moss and Mend handy.
5. At the seventh floor's anteroom: west is the **treasure room** (three chests, 600+ gold), south is the **throne**.
6. `talk maldrath`: he offers half the realm. `reply 1` ends the game at once (a hard game over). `reply 2` refuses: he rises as a man and fights you.
7. The first form falls, a few seconds pass, and he rises again as a wyrm. Heal and fight. When it falls, wait: the light returns, the colossus (if still there) is gone, and the fields go quiet.
8. Return to Telgard. `talk king`, `reply 1`. Wait about 40 seconds: the king offers his crown and you decline. That is the end.

*Check:* both forms need a fight; the quiet world after (no more monsters on the fields); the choice at the offer really is final for the first option; the king's last talk reads as victory.

---

## What to look for when you play it for balance

- The first two hours on the fields. The first fight should be hard and winnable, leveling should feel like the NES game, and nothing in the first area should kill a level-1 hero in one hit.
- Prices against what you earn: a bronze blade at 180 should take a handful of fights, not a hundred.
- The drake. A level-13 hero in the test checkpoint dies there; a level-15 hero with a longblade and moss wins it. If that feels wrong, the drake's attack is the knob.
- The two Maldrath forms. The first should be a real fight, the second a longer one.
- Dark rooms: whether "no way north" is enough feedback, or whether you wish it said more.
- Everything an NPC says. The dialogue is original wording, not the NES text.

## Known approximations

- Barrier-floor damage (4 per 3 seconds) is tuned by feel.
- The 1-in-32 death-necklace chest is a plain chest.
- Levels 21 to 30 use interpolated stats (the NES table stops earlier).
- Egress and Recall use the region's `entrance` property and the `dark` rule rather than a real "inside or outside" test.
- The harp calls a monster of the zone you are in.
- Overland distances are not tile-exact; the regions follow the general shape of the original world.
