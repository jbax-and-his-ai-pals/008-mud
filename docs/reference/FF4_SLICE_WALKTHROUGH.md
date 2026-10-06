# Walking through `ff4_slice`, start to the Paladin

A hand-testing route for the whole slice as it stands: from the crystal chamber in Ilmara to the Paladin conversion on Mount Vigil. It is written from the content files and from the scripted walks (`toolkit/adaptation_walkthroughs/walk_ff4.py` covers the first half and is run by the gate; the later chapters are covered by `server/tests/singles/test_adaptation_slices.py`). The later chapters have been tested in pieces, not played start to finish by hand, so treat each "expect" line as a claim to check.

Commands are what you type. `reply N` picks the Nth choice in a conversation. "Wait" means let the clock run (a scene is told over a minute or so; just stand there, or `look` now and then).

**Shortcuts for testing.** In a test session (the client's test mode, or `python toolkit/play_script.py ff4_slice --debug ...`) `checkpoint <name>` jumps you to a chapter with the right flags, gear, party and quest state. Names, in story order: `king`, `road`, `cave`, `hollow`, `village`, `ruin`, `wood`, `inn`, `dunhallow`, `desert`, `brineway`, `camp`, `brine_gate`, `ashmere`, `throne`, `after_throne`, `skimmer`, `pit`, `corrin`, `tolmere`, `quay`, `vessa`, `vigil`, `paladin`. `level`, `tp` and `scene skip` are there too.

**Things to try in every chapter.** `companions` and `companions <name>`; `combat normal` / `combat brief` / `combat full` in the big fights (the digest should fold your party's chatter and keep what matters); `journal`; `status`; talking to a companion again after they have joined; `look` in a room after a scene (the text should match what just happened).

---

## 1. Ilmara: the crystal

1. You start in the crystal chamber of Ilmara, with the commander's seal, a dark blade and dark armour.
2. Wait about 80 seconds. The Ilmaran acolytes fall to your troops; the elder is left.
3. `talk elder`, then `take crystal`. Expect the elder's curse-in-all-but-name, and then, after a wait, the crystal carries you off.
4. **The airship.** You land on a deck in the clouds. Two sky creatures rise: kill them (`attack <name>`). A short while later a second wave of three. Kill those. Wait for the landing.

*Check:* the elder's `after` line once you hold the crystal; the second wave starts by itself; nothing stalls on the deck.

## 2. Varenholt: the king, Kessa, the night

1. You arrive in the throne room (walked in by the chancellor). `talk king` (King Aldous).
   - Choice 1 or 4 ("At once, my king" / "I will go"): you obey.
   - Choice 2 ("the raid was a slaughter"): you are stripped of your seal. This is a real branch: it changes the later lines (`questioned_king` flag, the guards at the throne room door, Kessa's briefing text).
   - Choice 3 asks about the package; talk to the king again after.
2. Either way you are marched to the courtyard with a **package**. Try `go north` back into the throne room: the guards turn you away.
3. `go east` to the barracks. `talk kessa`, `reply 1` (obeyed) or `reply 2` (stripped). She says to rest and meet her at dawn.
4. Try the castle gate (west, then south from the barracks): "Not alone." Go to your quarters (back north, east, north: the barracks' north door) and wait. Morning comes, you are rested.
5. Back to the castle gate. `talk kessa`, `reply 1`: she joins.
6. **Optional:** the chapel (west of the courtyard) has Rosalind, who heals you for free if you ask (`talk rosalind`, choice 1). The chancellor in the throne room has a second conversation: `talk chancellor`, `reply 1` unmasks a fiend (a fight; see if you want it).
7. The stores (east of the castle gate) sell supplies.

*Check:* the dismissed-courier path versus the obeyed path read differently; the guards do not let you into the throne room either way; Kessa's lines change when she is with you inside the castle (she offers to hold there).

## 3. The road and the Fog Cave

1. South of the gate is the castle road. Goblin scout, then wolf (east). Walk east and north, then `go in`.
2. **Fogreach (the cave).** `go east`; two bats. North is the guano nook: `open oilskin bundle`, `get iron helm from oilskin bundle`. At the crystal pool, north is an alcove with an iron chest: `open iron chest`, take potions and the wayfarer's charm.
3. South of the pool is a **warning**: the first try is stopped by fog; wait a few seconds and try again to get through. The ledge and the gallery do the same (three warnings in all). A cave imp waits on the ledge.
4. In the hollow, wait for the **Fog Drake**. There is no leaving: `go north` fails. Kill it (Kessa helps; Gloom Wave costs you an eighth of your health, no mana). It goes through phases: at one point it turns to mist and cannot be touched, so wait it out.
5. After it falls, `go down` opens to Hazevale.

## 4. Hazevale: the package and the fire

1. `go south` to the square. `talk mayor`; `give sealed package to mayor`. Wait: the package opens, the village burns, you stand in the ruin.
2. South to the shrine, with **Ryn**. `talk ryn`, `reply 1` (or 2: both are checked). Wait; Kessa works out what the king meant and relents.
3. Talk to Ryn **three more times**, `reply 1` each time. She refuses twice; the third time she calls the colossus.
4. Wait: the quake brings the mountain down and you wake in Thornwood with Ryn carried, unconscious. Kessa is gone. (Ryn is a passenger now: enemies cannot target her.)

## 5. Thornwood to Dunhallow

1. East, east, east... the walk script goes east seven times and then north to the inn. Wolves and jackals are on the way. You are carrying Ryn; `companions` should show her.
2. At the **Blue Door Inn** wait: she is put to bed. Wait again: the king's guards arrive and you refuse to hand her over. Beat the sergeant and the guards.
3. Wait: Ryn wakes, thanks you and **joins** (she has Ember and a basic Mend). The innkeeper mentions a woman asking after you.
4. **Orrin's house.** From the inn go south (square), south (lane), east. North is the back room. On entering (wait): **Rosalind**, sick with the salt fever. `talk orrin`: `reply 2` asks where a mirage pearl is found. The cure is a mirage pearl; the old stories say the kings of Ashmere kept some.
5. Pell's Trading Post (east of the square, north) sells salves; `trade pell`, `list`, `stoptrade`.

*Check:* Orrin's three "Go on" loops return to the right node; the fever-time answer ("a month") does not contradict the story.

## 6. The Brineway

1. From Dunhallow's gate go west into the desert: dune road, dry wash, then south to the salt flats, east to the glass dunes, south to the bleached ridge, east to the sinkhole, `go down`. (Scorpions and jackals on the way.)
2. At the mouth wait: **Belaric** meets you. `talk belaric`, `reply 1` to take him along.
3. East three times to the Dry Hall. The party camps for the night (wait). `talk belaric`: ask `reply 2` (who), `reply 1` (go on), `reply 1`, `reply 3` (the Brinecoil), `reply 1`, then `reply 5` (sleep). Wait: morning; Ryn is taught Lightning.
4. East, north for the Nacre Grotto's cache of salves (`open cache`, `get all from cache`; no pearl here). The Brine Gate warns once.
5. The **Drowned Gallery**: wait. The Brinecoil rises with several legs. Kill the legs first (Belaric and Ryn burn them with you), then the head.
6. After it falls the arches open. `go up` to the far shore; Ashmere is east.

## 7. Ashmere: Mirelle, Lucan, the skimmer

1. East to the road: besiegers. Kill them; the gate and courtyard have more besiegers and a lancer. Wounded soldiers are not enemies. The infirmary (south of the courtyard) has a healer.
2. Up from the courtyard is the throne room. On entering (wait; about two minutes): Belaric finds **Mirelle** dying, beats the prince with his staff, hears her last wish, and goes alone after Varkos. He is gone from your party.
3. `talk mirelle`, `reply 2` (the last goodbye). Then `talk lucan`, `reply 1`: **Lucan joins** (a bard: songs for sleep and so on; try `combat normal` here).
4. **King Osric**, in the great hall (north of the courtyard). Once Lucan is with you `talk osric` offers the secret: `reply 1` ("Thank you, Majesty") and the **royal skimmer** is placed in the boathouse (east of the great hall). Before Lucan joins he only grieves or greets.

## 8. The sand sea and the Sandmaw

1. In the boathouse: `embark skimmer` (alias `ride`). `go north`. On the first launch a short scene plays. North again to the Rim of the Basin, then `go down` to the pit.
2. At the Funnel's Edge the skimmer cannot follow: `disembark`. East to the Spiral Slope; south and east are the burrows (grubs, a scorpion). The Lower Burrows (south) has a **silted chest**.
3. East then south to the Nest. The way east warns once, then lets you through to the **Maw**: the way back is sealed and the **Sandmaw** rises. Kill it. It drops the **mirage pearl**; the way west reopens.
4. Back out, `embark skimmer`, south, south to the boathouse; the other way out is west from the Open Drift across to the Wind-Scoured Drift and on to the Glass Dunes. Walk back to Dunhallow (west across the desert, the way you came).
5. Orrin's house, `talk orrin`, `reply 1` (give the pearl). Wait: Rosalind wakes. Go into the back room, `talk rosalind`, `reply 1` ("Then come"): **Rosalind joins** (healer: she raises the fallen).

*Check:* the skimmer works on sand only and is refused elsewhere; the pearl is not in the Brineway's cache; the sickroom text changes once she is cured.

## 9. Mount Corrin

1. From the date grove (east of the square's market street) go north. Without Rosalind the way is shut ("pearl, the fever and Rosalind").
2. Foot of the path (an imp), then the **Switchbacks**: on entering with Ryn in your party (wait) a **wall of ice** stops you and Ryn learns **Blaze** and melts it. Kill the imp and wisp, take the potion, go north.
3. The rope bridge (a wisp), then the **Wind Ledge**. **Bram** the monk is here: `talk bram`, `reply 1` and he joins. Take the potion. East is warned once; the second try goes through.
4. **The Black Ring.** Wait: the **Cinder Mother** lifts. Fight it with the party. At about two thirds it sheds **six little bombs**: kill them. At a third it swells and goes off, hurting (and possibly felling) your party but not you. Fallen companions are "recovering"; check `companions`.
5. After it falls you are rewarded, Bram gets up, and the way north to Tolmere opens.

## 10. Tolmere: the siege, Kessa, the duel

1. The gate has a monk. North is the courtyard, full of fighting. Kill the soldiers (wave 1). The monks fight beside you.
2. **Six waves in all:** wave 2 comes through the gate in the courtyard; then a monk calls "fall back to the hall" and waves 3 and 4 fill the **great hall** (north); then the king calls you out and waves 5 and 6 are back in the courtyard (the last has two lancers). Each wave starts when the last is cleared; you can rest only if nothing is in the room.
3. After wave 6: a wyvern lands, the monks step aside, **Kessa** walks out. `talk` does nothing ("..."); she is not hostile until she raises her spear. She cannot be put to sleep and goes for you. You cannot win: when you drop to about a third, wait. **Varkos** appears on the hall roof, takes the crystal and **Rosalind** and leaves with Kessa.
4. The crystal room (north of the great hall) is empty. `talk haldane`, `reply 1`: he lends you the **Gull**. Ryn, Lucan and Bram are still with you.

*Check:* the monks leave when Kessa arrives; the duel does not fire early (during waves 1 to 5); losing Rosalind leaves Ryn, Lucan and Bram only; the king's lines change after the duel.

## 11. The Gull and the Maelrake

1. The quay is east of the courtyard. `embark gull`, `go east` twice. At the **Dark Water** the storm rises (wait) and the **Maelrake** attacks. You cannot win it: at half its health, or if you drop low, the Gull is wrecked.
2. You wake alone at **Vessa**, on the shore. Ryn, Lucan and Bram are gone for now.

## 12. Vessa

1. Up the steps to the lane. `talk` to the scholar (flavour). East of the lane is the **Dawn Forge**: **Aud the smith** sells dawn mail and a dawn helm (you cannot afford much yet; they matter after the mountain).
2. North to the square. West is the elder's hall: `talk hesper`. `reply 1` ("What would I have to become?") then `reply 1`; or `reply 2` to go straight. Either way **Tobin and Tamsin** (the twins) join you. The north road is shut until they have.

## 13. Mount Vigil

1. North of the square: foot, the **Pilgrim Stair** (a hound), the **Field of Cairns** (a pilgrim and a hound). On entering the cairns (wait) **Belaric** steps out of a door in the mountain: `talk belaric`, `reply 1`: he rejoins and remembers **Meteor**, which costs more than he has (try it: it is refused).
2. The **Crypt Gate**: a candle wight. North of it warns once, then goes through to the **Hall of Candles**. Wait: **Morvane** rises, with four skullnants. Fight the whole party. Fire is his weakness (Ryn's Blaze, Ember).
3. When he falls the hall goes quiet. North across the **Narrow Bridge**, to its far end. Wait: **Morvane returns** behind you, in a second form. Fight him on the landing. The way up is shut until he falls.
4. At the **Mirror Stair** (north of the landing) the party stops: "I can't put my foot on it." Tobin, Tamsin and Belaric are dismissed and wait.
5. Go `up` alone to the **Still Summit**. A voice, then your **shadow**. It cannot be hurt much, mirrors you, and pays in blood to attack (a fight to outlast, not to burst down). When it is nearly spent the light comes: you are made a **Paladin**. The dark blade becomes a **dawn blade**; you get a **pilgrim's tunic** only; the dark spells are forgotten and you learn Smite, Radiance and Mercy. `title` should show Paladin.
6. Go back down. The twins and Belaric are waiting: `talk tobin` (or Tamsin, or `talk belaric`), `reply 1` to take each back.
7. Optional: back to Vessa and Aud's forge to buy the dawn mail and helm; equip them (`equip <item>`).

*Check:* the new gear and spells really replaced the old; Morvane's second form does not appear on the first visit to the bridge's end until after the first form is dead; nobody can follow onto the stair; Belaric's Meteor is refused.

---

## Where it ends, and what is not there yet

The slice stops with the Paladin and the party reunited. Not yet built: the return to Baron's equivalent (the impostor king), the airship, the twins' petrify sacrifice, the Tower of Zot and Belaric's Meteor, the Underworld, the Lunar Whale and the moon. `docs/plan/ff4-adaptation-plan.md` has the order.

## Known soft spots worth poking at

* Fabul's equivalent, Tolmere, has the six waves but not the original's revive-after-the-duel scene.
* The first Mount Hobs equivalent (Corrin) has the ice wall only if Ryn is in the party at the switchbacks.
* Timing: several scenes need a wait; if one seems stuck, `look` and wait another half minute before reporting it.
* The Brineway, Sandmaw and Vigil fights were tuned with a scripted player; a human with a different build may find them too soft or too hard. Notes on which would help.
