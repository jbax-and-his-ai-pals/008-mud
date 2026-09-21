# FANTASY FRONTIER
### An Adventurer's Handbook

*Everything you need to know before you set foot past the village gate.*

---

## Table of Contents

1. Welcome, Traveler
2. Getting Started
3. Your Character
4. The Lay of the Land
5. Moving About
6. Talking, Trading, and Making Friends
7. Combat
8. Magic
9. Skills
10. Gathering & the Wild
11. Crafting
12. Coin & Commerce
13. Quests and the Notice Board
14. A Place to Call Home
15. Crime, Notoriety, and the Long Arm of the Law
16. Collections & Discoveries
17. Games of Chance
18. Quick-Reference Command Table
19. Work That Takes Time
20. A Few Words of Advice

---

## 1. Welcome, Traveler

You are standing at the edge of **Riverside Village**, a timber-and-thatch
settlement on the banks of the Silver River, with the **Whispering Woods**
pressing in close at its northern gate. Somewhere beyond the trees,
something is stirring. What you do about it — or whether you do anything
about it at all — is entirely up to you.

This handbook won't tell you how the story ends, because there isn't
one single ending. It will tell you what tools you have, what the world
expects of you, and where to start looking if you want more.

---

## 2. Getting Started

When you first arrive, you'll be asked to name your character — and,
if you like, to say where you came from:

```
char create Rowan
char create Rowan as acolyte
```

Six beginnings are on offer (`backgrounds` lists them): a **wanderer** who
arrived with a knife and a bedroll, a **labourer** with a work axe and a
season of hard graft behind them, an **apprentice** who has read a page and
cast a spell, an **acolyte** with the words that mend, a **pedlar** who knows
what things are worth, and a **poacher** who knows what runs where. Each
decides where you start — stats, kit, a couple of skills, a recipe or two —
and none of them decides what you can become. Take any background and any
path later; nothing is closed to you. If you'd rather not choose, `char
create Rowan` alone gives you the wanderer.

Once you're standing in the town square, four paths are laid out for you —
take any one of them, or ignore all four and wander off on your own:

1. **Get oriented.** `look` around, check your `inventory`, and note the
   exits from the room you're in.
2. **Help Riverside.** Check the notice board (`look board`), accept a
   commission (`accept quest <#>`), then talk to Elder Thorne. He explains the
   work, teaches the needed recipe, and points you to the community garden.
3. **Trade and prepare.** Visit Talia at the market to see what's for
   sale before you go looking for trouble.
4. **Explore and face danger.** Equip your weapon (`equip dagger`, `equip
   axe`, `equip bow`) and take the north road into the woods.

None of these paths closes off the others. Riverside doesn't run out
while you're busy elsewhere.

Hazards are part of that warning. A yellow haze, sparking floor, killing
cold, blistering heat, oppressive shadow, or a patch of sucking mud is a
real environmental danger that can hurt at regular intervals while you
remain there — and weather can make a bad spot worse, not just miserable
to walk through. `look` first, retreat if you are not prepared, and return
with the right resistance when you have it.

A few commands you'll use constantly from the very first minute:

| Command | What it does |
|---|---|
| `look` | Describe the room you're standing in. |
| `look <target>` | Look more closely at something or someone. |
| `go <direction>` (or just the direction, e.g. `north`, `n`) | Move. |
| `inventory` (`i`) | See what you're carrying. |
| `status` (`st`) | See your health, mana, level, and stats at a glance. |
| `help` | A categorized list of everything you can do. |
| `help <command>` | Details on one specific command. |
| `save` / `load` | Save or load your progress. |

---

## 3. Your Character

Everyone who takes up the adventurer's trade is built from six core
attributes:

- **Strength** — how hard you hit, and how much you can carry.
- **Dexterity** — your precision with weapons, and your knack with locks.
- **Constitution** — your health and staying power.
- **Agility** — how quickly you move, dodge, and slip away unnoticed.
- **Intelligence** — your aptitude for crafting and the finer points of magic.
- **Wisdom** — your instinct for a fair deal, and your connection to
  restorative magic.

Beyond these, you track **Health** (how much punishment you can take
before you fall), and, if you take up the practice of magic, **Mana**
(the well you draw spells from). Both grow as you gain experience and
rise in level.

Experience comes from *doing*, not from any one thing. You are paid the
first time you walk into a region you've never seen, meet a creature or a
person you've never met, pick up a material you've never held, learn a
recipe or a spell, cross a threshold of trust with someone, finish a
commission, or complete a collection. Killing things pays too — but a
return trip to a place you know pays nothing, so there is no incentive to
farm the same room, and a curious traveller advances at least as quickly as
a busy one.

`advancement` (also `progress` or `fieldjournal`) opens your field journal:
everything you have seen and done, sorted by kind. It is the honest record
of your travels, and it is worth a look when you're not sure what to do
next — the gaps are the map.

Type `status` any time to check where you stand.

---

## 4. The Lay of the Land

The world beyond your front door is bigger than it first appears — five
towns' worth of bigger, each one an anchor for the danger and the
opportunity around it. You won't see all of this on your first day.
That's rather the point.

### Around Riverside (the gentle end)

- **Riverside Village** — home. Market, tavern, shrine, museum,
  blacksmith, and a scattering of houses along a quiet residential lane.
- **Riverside Catacombs** — a neglected burial network under the shrine
  and the tavern cellar, where old foundations meet a natural cave. Gentle
  enough for a first dungeon, with two ways back to the surface.
- **Whispering Woods** — the forest north of the village. Wolves, goblins,
  and bandits keep to its shadows, and **Briarhook Scrapcamp** — a proper
  goblin settlement, not just a wandering pack — is dug in among the
  briars. Local legend says the woods hide something older still.
- **Ancient Ruins** — the crumbling remains of a forgotten civilization,
  buried deep in the Whispering Woods.
- **Windy Foothills** — grassy highlands east of the farms, home to
  goblin and orc raiding parties and, tucked into a fold of the hills,
  **Gallows Hollow** — a watched, supplied bandit camp, not an easy mark.
- **Murkwater Swamp** — a humid, treacherous bog south of the river, home
  to **Reedscale Village**, a lizardfolk settlement raised on root-bound
  platforms above the deeper channels.
- **Riverside Farmlands** — the fields and pastures that feed the village.
- **The Gilded Lotus** — an unexpectedly lavish casino, for those who'd
  rather test their luck than their sword arm.

### The Coast

- **Portbridge** — a harbor town where the Silver River meets the sea.
  Sailors, merchants, a harbourmaster with a tariff problem, and — if
  rumor is to be believed — smugglers working the tunnels beneath it.
- **Tidewell Underworks** — a drowned tangle of old drainage works,
  smuggler storehouses, and failing tide machinery under Portbridge's
  harbor. The sea reaches every low point eventually.
- **Salt-Kissed Path** — the coastal road where the swamp finally gives
  way to open shore, with **Tideglass Warren** — a kobold settlement dug
  into the dry rock behind the sea caves — tucked along it.

### The High Country

- **Frostpeak Mountains** — the high, cold country beyond the foothills.
  Orcs, harpies, trolls, and worse make their homes among the peaks. Not a
  place for the underprepared.
- **Frostpeak Outpost** — a mining town where the foothill road meets the
  high pass: a forge, a supply yard, and the Mining Lodge, built for
  people who work the mountain rather than just pass through it.
- **Shadow Caves** — a cave network in the hills, including a sunken lake
  far below the old mine shafts that the miners broke into by accident.
  Seldom visited, full of stories nobody can quite confirm.
- **The Obsidian Trial** — an ancient volcanic proving ground, reached
  through the caves, for those who've already tested everything else.

### The Desert Road

- **Sunscorch Expanse** — beyond Frostpeak's dry eastern pass, broken
  highland gives way to salt flats, wind-cut stone, and distant dunes. The
  caravan road is the only reliable way across.
- **Sunscorch Caravanserai** — a walled desert town built around a
  dependable spring, trading water, repairs, news, and safe passage in
  equal measure.

### Aurelia and Beyond

- **Aurelian Outlands** — where the desert loosens into dry, cultivated
  country around Aurelia. Imperial milestones and old aqueducts promise
  order; the abandoned works beyond the road have not gotten the message.
- **Aurelia** — the prosperous-city anchor at the far end of the road:
  guild halls, a museum, an auction house, and institutions old enough to
  believe they'll outlast every traveller who needs them.
- **Starwell Archive** — the oldest vault beneath Aurelia's museum, built
  around a damaged imperial instrument that once charted the sky. Not a
  place for a first adventure.

Each town serves a rough band of danger — Riverside for the newly
arrived, Portbridge and Frostpeak Outpost for the proven, Sunscorch
Caravanserai and Aurelia for the seasoned — but nothing stops you from
seeing a further town before you're ready for what's around it. The
world doesn't gate you; the danger speaks for itself.

---

## 5. Moving About

Movement uses compass directions — `north`/`n`, `south`/`s`, `east`/`e`,
`west`/`w`, and their diagonal cousins (`northeast`/`ne`, and so on),
plus `up`/`u` and `down`/`d` for stairs and slopes, and `in`/`out` for
doorways, gates, and other thresholds that aren't really a "direction"
so much as a way through.

Some passages are locked, warded, or otherwise require something of
you before they'll let you by — a key, a lockpick, or a skill you've
practiced. The game will tell you what's missing when you try.

Within a region, `survey` will tell you what's gatherable nearby, and
`minimap` toggles a visual map if you'd rather see the shape of things
than read about them.

The sky matters too. `weather` tells you what's happening overhead, and
it isn't just flavor — a coastal road turns windy, an alpine pass buries
itself in snow or blinds you in a blizzard, a desert clear day turns
windy and a storm turns to a blinding sandstorm, marshland fills with
mist, and open fields turn to mud in the rain. Exposed travel will warn
you when conditions are bad, and some gathering spots (a sea-fishing
line in a storm, say) simply won't work until the weather clears.

---

## 6. Talking, Trading, and Making Friends

Riverside (and everywhere beyond it) is full of people, not just
monsters. Use `talk <name>` to strike up a conversation, or `ask <name>
about <topic>` once you know what to ask about — new topics reveal
themselves as you learn more.

Some people have a great deal to say. When you `talk` to them you get a
**conversation**: what they say, and below it a numbered list of what you
can say back.

```
> talk grenda
CONVERSATION WITH GRENDA THE BLACKSMITH

"Well met. The forge is hot, but my supplies are low."

1. What are you working on?
2. I could use some iron.
3. No time. Goodbye.
```

`reply <number>` picks one — or type the words of the reply, or enough of
them to be clear: `reply 1`, `reply what are you working on`, and
`reply the forge` all work if they mean the same thing. If two replies fit
what you typed, you'll be asked again rather than have words put in your
mouth. Typing an unrelated `talk <name> <topic>` in the middle of a
conversation asks the question instead of ending it.

**Some replies only appear when they should.** A smith won't offer to teach
you a pattern while your hands are empty, and won't discuss her private
business with a stranger. She also *remembers* — tell her you'll look into
something and she'll expect you to, because what you say to people is part
of the world. You never see a locked list; the conversation simply has more
in it once you've earned it.

**Relationships** matter here. Every named NPC you deal with keeps a
private opinion of you, visible with `relationship <name>` (or
`relationships` for the full ledger). Give someone a **gift** they'd
appreciate — with `give <item> to <name>` — and that opinion improves;
give them something they dislike, and it won't. Climb high enough and
you'll cross a **friendship tier** (Stranger, Acquaintance, Friend,
Close Friend), each one unlocking a small vendor discount and, in
some cases, wares or opportunities that aren't offered to a stranger.

You will notice that second part by its absence rather than its
presence: someone who doesn't know you yet simply won't mention the
work they have going, and the notice board will have less on it. There
is no locked list to work through — people who trust you offer you
more, and the surest way to be trusted is to be useful and to
remember what people like.

**Negotiations are conversations too.** When a commission comes down to
talking someone round, you'll be offered your approach as a reply, and your
nerve and your manner decide how it lands. Pick your words badly and you may
have to finish the job another way.

To do business: `trade <name>` with anyone who deals in goods, then
`list` their wares, `buy <item>`, or `sell <item>`. Some vendors also
keep standing **buy orders** — check `orders` while trading, and
`fulfill <order>` when you've got what they're after. A few of these
are repeatable income if you keep the right materials coming.

---

## 7. Combat

`attack <target>` (or `kill`/`fight`) starts a fight, or joins one
already underway.

**You swing when you type, and they swing back while you decide.** Combat is
not automatic: each `attack` is one exchange, and your weapon has a short
cooldown between blows (`combat` shows your current fight, including whether
you are ready). In between, anything fighting you keeps attacking on its own —
so standing in a fight doing nothing is a way to lose one. `status` shows your
health; a creature that is badly hurt will say so when you look at it.

Some creatures are worth sizing up before you commit. You will not be told a
monster's level or its exact hit points; what you can see is how it looks and
how the fight is going.

**Retreating is not free.** Walking away from an active fight — whether
you use ordinary movement or the dedicated `flee` (or `retreat`)
command — means trying to slip past your opponent, and that's a real
contest: the tougher the fight, the harder it is to break away cleanly.
`flee` will pick a nearby way out for you, favoring safety if there's
a safe direction to run; fail the attempt and you're still in the
fight, so don't count on retreat as a guaranteed escape hatch.

Most creatures you'll meet are ordinary. Some aren't. Every so often,
the wilds produce something **elite** — a noticeably tougher, oddly-named
version of an otherwise familiar threat ("Alpha wolf," "Dread orc,"
"Ancient troll," and the like), carrying better loot than its plain
kin. The town guard occasionally posts **bounties** on these elites
specifically — check the notice board.

**When you win, look down.** A defeated creature drops what it was carrying on
the ground where it fell; it does not go into your pack by itself. The game
will tell you what fell and how to pick it up.

**Steel matters as much as skill.** Every weapon cuts, stabs, or crushes,
and every suit of body armor is cloth, leather, chain, or plate — and the
two interact the way you'd expect from the real thing. A blade opens up
unarmored cloth and leather but glances off plate; a thrusting weapon
(a spear, a rapier) finds the gaps in mail that a slash can't; a mace or
hammer doesn't care what it's hitting through, and plate is exactly what
it's built to answer. There's no in-game readout for this — it's
something you learn by noticing what works, same as sizing up a fight.

Check `combat` (or `cstat`/`fightstatus`) at any time for a status
readout of your current fight.

**If you fall**, you are not out of the game — you can `respawn` and carry on.
Dying costs you the fight, not your progress.

---

## 8. Magic

If you've taken up spellcraft, `cast <spell> [target]` puts it to use,
and `spells` lists everything you currently know. Spells cost
**mana**, which regenerates over time (faster when you're not in a
fight), and most have a minimum level before you can learn them.

Spells are learned from the world, not handed out at level-up: an
apprentice or an acolyte begins knowing one, and the rest are found —
scribbled on scrolls and runes that teach the reader, or taught by
whoever in the world has reason to teach you. If you started with none,
nothing is closed to you but the finding.

The schools of magic on offer include:

- **Offense** — Magic Missile, Zap, Ice Shard, Bone Shard, Ember Bolt,
  Poison Cloud, Immolate, and more direct ways of making your point.
- **Elemental** — Fireball, Frostbolt, Chain Lightning, Holy Light,
  Shadow Word: Pain.
- **Restoration** — Minor Heal, for when things go wrong.
- **Buffs & Debuffs** — Resist Fire, Weaken, Frost Curse, and other
  ways to tilt a fight before it starts.
- **Summoning** — Raise Skeleton, Raise Skeletal Mage, Summon Spirit
  Wolf, Summon Fire Imp, Summon Stone Golem: conjure something to fight
  at your side.
- **Utility** — Knock (opens a mundane lock through force of will) and
  Arcane Lock (the opposite problem, for anyone who'd rather keep
  something shut).

---

## 9. Skills

Beyond your six core attributes, certain trades are tracked as their
own skills, sharpened by use and backed by a particular attribute:

- **Lockpicking** (Dexterity) — opening what wasn't meant to open.
- **Crafting** (Intelligence) — the quality of what you make.
- **Mercantile** (Wisdom) — your instinct for a good trade.
- **Stealth** (Agility) — slipping away unnoticed, whether that's from
  a fight or from the scene of a theft.

Skills rise by being used, not by being chosen: pick a lock, make a
thing, haggle a price, slip out of a fight, and the skill behind it
grows — including when the attempt fails, because a failed attempt is
still practice. Some of your background's skills start above zero, but
nothing you didn't start with is closed to you.

Type `skills` to see where you currently stand in each.

### Titles

What you're *called* is earned, not chosen at the start. Keep at a
trade, keep your word with the right people, and someone will eventually
have a name for what you've become — **Hand** of the workward, **Trader**
of the market row, **Pathfinder** on the roads, **Hedge Healer** of the
Order of the Dawn, and — if you make it as far as Aurelia — an
**Aurelian Surveyor** or **Aurelian Artificer** of that city's own guild
halls, and others besides. A trade name follows you home; it isn't tied
to where you earned it.

Type `title` to see what you've earned, what's within reach, and what
each one wants from you. When you've earned one, `title <name>` wears
it — the name appears when others look at you. Titles grant no powers;
they are what people call you, which in a village that remembers faces
is worth something on its own. Stop living up to one and it can lapse.

---

## 10. Gathering & the Wild

The land provides, if you know how to ask. Use `gather` (also
`mine`, `harvest`, or `chop`, depending on what feels right for the
material) on a resource node to collect from it — clay banks, ore
veins, herb patches, fishing spots, and more. Any tool a patch needs is
noted when you survey it, and every patch has a limit on how much it
will give before it needs time to recover.

You won't be told exactly how many gathers are left in a patch, or the
day it will come back — someone working a hillside knows when it has
been picked over, not the schedule behind it. What the game will tell
you is when there is nothing left to take, and where else to look:
patches of the same material elsewhere, or something else that will do
instead. Learning the good spots is part of the game.

Some finds are simply better than others — gathered materials can
carry a **quality grade**, and a rare, pristine specimen is worth
seeking out over the ordinary kind, especially if you're crafting
something meant to last.

---

## 11. Crafting

`recipes` shows what you know how to make (add `all` to include
recipes you're still missing materials for), and `craft <recipe>`
makes it, provided you're carrying the ingredients and, for some
recipes, standing near the right station. Each entry lists the
materials it needs and its own command line, which is the surest thing
to type. `salvage <item>` breaks an item back down into raw materials,
if you'd rather reclaim than keep.

Practice matters: crafting the same recipe repeatedly can unlock
higher **quality tiers** — Simple, Fine, Masterwork — each worth more
and, for gifts, more appreciated by the person you hand it to. Using
finer raw materials pushes the ceiling even higher. `recipes` tells you
what a given recipe would produce right now, and what would raise it.

`attach` and `detach` handle equipment attachments, for gear that
supports them.

### Field alchemy

Riverside's alchemist has an **alchemy kit** in the shop and sells empty
glass vials. Gather herbs or berries, bring a vial, and use `recipes all` to
see the small field preparations you can make there. They are useful choices,
not merely differently named healing food:

- `craft marshguard` makes a three-minute poison-resistance ward for bad air
  and venom.
- `craft trailblazer` grants a short agility buff.
- `craft antidote` makes a purifying draught that clears poison and disease
  effects from you (or use it `on <target>`).
- `craft sunfire` makes a disposable thrown weapon; `use sunfire flask on
  <foe>` hurls it at that foe.

Active wards and buffs appear in `status`, including how long they have left.
The useful habit is to make a preparation before entering the danger its
description warns about, rather than attempting to out-heal an unseen hazard.

---

## 12. Coin & Commerce

Riverside (and everywhere else) runs on **gold**. Earn it from combat,
quests, gathering, and trade; spend it on gear, materials, repairs,
and property.

- `buy <item>` / `sell <item>` while trading with a vendor.
- `repaircost <item>` / `repair <item>` for worn equipment and armor.
- `appraise <item>` for a closer look at something you're unsure about.

Watch for regional quirks: Portbridge, for instance, currently carries
a noticeable tariff on all buying and selling — a direct consequence
of unresolved trouble in its harbor. Some problems in this world have
prices attached.

---

## 13. Quests and the Notice Board

Riverside's notice board (`look board` to read it, `accept quest <#>`
to take one on) is the steadiest source of work, refreshing with new
opportunities as old ones are cleared. Track what you've taken on with
`journal` (add `completed` to review what you've already finished),
and turn a finished task in with `turnin quest`, `complete quest`, or
by simply talking to whoever gave it to you and asking to `complete`.

Some notices come around again, but never immediately. When a giver takes
one down or the board is picked over, follow another lead and check back
later; the world will tell you what is happening without turning it into a
countdown timer.

**The board shows what is actually available to you.** If a task needs
a giver's trust and you have not earned it yet, the notice simply will
not be there — you are not shown a list of things you are barred from.
That also means the board is worth re-reading after you have done
someone a good turn: new notices appear as people decide they can rely
on you.

Not every quest is solved the same way — some accept combat, some
favor a gathered or crafted solution, and a few will let you `negotiate`
your way through instead of fighting. If an NPC offers to walk you
somewhere, `guide <name>` will have them lead the way; `stop` cancels
being guided (or any other automated action) early.

Some threads run deeper than a single task — multi-stage **campaigns**
with branching outcomes, started through conversation rather than the
board. Choose carefully; these don't always have a clean, single "right"
answer. Talking to people is how most of them begin, so it is worth
asking the people in charge what is worrying them.

Boards are not a Riverside peculiarity. There is one in Portbridge's
harbor district, one in the Frostpeak Mining Lodge, one in the Wayfarers'
Rest at the Sunscorch caravanserai, and the notice boards in Aurelia's
Guild Square carry the same notices — the same work, read wherever you
happen to be standing.

Two things about deliveries and quest items. When you accept a courier
job, whoever hired you hands over what you are carrying, so check your
pack before you set out; a run with several stops needs one delivery
each, and the game will tell you who is still owed theirs. And a **quest
item** is not yours to part with: you cannot sell one, and you cannot
give one away to somebody it was not meant for. If a task handed you
something, it is because that thing has somewhere to be.

---

## 14. A Place to Call Home

Riverside's property agent, found near the residential lane, will sell
you a house of your own (`buy house`) — a private space, locked to
everyone but you, that persists for as long as you keep playing.
Once you own one, the same agent doubles as a contractor: `house` shows
your current tier and whatever upgrade is on offer next, and `expand
house [branch]` commits to one, gated by gold and the right materials.
Choose a branch (garden or pond, at present) — it shapes how your home
grows from here.

---

## 15. Crime, Notoriety, and the Long Arm of the Law

Not everything worth having is for sale. `steal <item> from <target>`
lets you take from a vendor's stock or an NPC's home instead of
paying for it — but anyone present has a chance to notice, weighing
your **stealth** against their own alertness (the town watch is
particularly sharp-eyed).

Get caught, and the consequences scale with what you've taken and how
much trouble you've already caused: a fine for a minor offense, or a
stay in the jail cell for a serious one. Jail strips your belongings
into holding until you're released or escape — and if you've built
your stealth and lockpicking up enough, you're guaranteed some way
out, one way or another. `wait`/`rest` passes the time; `search`
occasionally turns up something useful in a cell; `pick <direction>`
is how you'd attempt to break out.

Locked doors and chests can also be **trapped**. `disarm <item>` reuses
your lockpicking skill to defuse one safely — a narrow miss can be
retried, but a bad enough attempt sets it off. Paying a locksmith to
open something is always trap-free, if you'd rather not risk it
yourself.

---

## 16. Collections & Discoveries

Keep an eye out for gems, curiosities, and specimens worth cataloguing
— `collection <id>` shows your progress toward a given set, and
`turnin` hands completed sets to whoever's collecting them. Separately,
`discoveries` and `journal` (in its broader sense) track knowledge
you've picked up along the way — recipes learned, materials identified,
places and creatures catalogued as you encounter them.

`advancement` (also `progress`) is the same record read the other way
round: not *what* you know but *what it was worth*, sorted by kind, with
the things you haven't met yet conspicuous by their absence. It is the
closest thing this game has to a quest log for your own curiosity.

---

## 17. Games of Chance

The Gilded Lotus offers dice, cards, and a spinning wheel, for anyone
who'd rather risk their coin than their neck. `guess`, `hit`, and
`stand` cover the table games on offer; `rules` (or `payouts`/`odds`)
explains whatever game you're currently seated at, including the odds
you're up against.

---

## 18. Quick-Reference Command Table

| Category | Commands |
|---|---|
| **Movement** | `north` `south` `east` `west` `northeast` `northwest` `southeast` `southwest` `up` `down` `in` `out` `go <dir>` |
| **Information** | `look` `status` `skills` `title` `advancement` `background` `backgrounds` `journal` `discoveries` `collection` `relationship(s)` `survey` `appraise` `calendar` `time` `weather` |
| **Interaction** | `talk` `reply/respond/choose` `ask` `say` `yell` `give` `take/get` `drop` `use` `read` `examine` `open` `close` `unlock` `pick` `pull` `search` `follow` `guide` `wait` `plant` |
| **Combat** | `attack` `flee`/`retreat` `combat` |
| **Magic** | `cast` `spells` |
| **Crafting** | `craft` `recipes` `salvage` `attach` `detach` |
| **Work that takes time** | `jobs` `begin <job>` `collect` (some work only finishes later — see §19) |
| **Gathering** | `gather` (`mine`/`harvest`/`chop`) |
| **Trade** | `trade` `list` `buy` `sell` `orders` `fulfill` `repair` `repaircost` `stoptrade` |
| **Quests** | `look board` `accept quest` `turnin quest` `negotiate` |
| **Property** | `buy house` `house` `expand house` |
| **Crime** | `steal` `disarm` |
| **Gambling** | `bet` `guess` `hit` `stand` `rules` |
| **Inventory** | `inventory` `equip` `unequip` `invmode` |
| **System** | `help` `save` `load` `quit` `minimap` `view` `stop` |

Type `help <command>` any time for the full details on any of these.

---

## 19. Work That Takes Time

Some things cannot be hurried. A batch in a fabrication bay, a barrel left to
work, a rack of herbs drying over a season: you put the materials in, and the
world clock does the rest — whether or not you are standing there, and whether or
not you are logged in.

```
jobs                      what can be made where you are, and what is under way
begin patch-kit batch     start one: the materials leave your pack
collect                   take anything that has finished
```

Three things are worth knowing:

- **The station decides.** `jobs` tells you what the room offers and what a job
  still needs; work that wants a bay cannot be started away from one.
- **Waiting is a trade, not a tax.** A job usually costs less per item than doing
  it by hand and pays more of it, in exchange for the time — and a slow, careful
  run is checked against a skill where a hurried one is not.
- **A run can go badly.** If the check fails you still get *something*, but less
  of it. Nothing is destroyed outright.

Leaving a batch running before you log off is the intended way to play it.

---

## 20. A Few Words of Advice

- **Talk to everyone at least once.** Riverside is small, and its
  people remember you.
- **A gift costs little and buys a lot.** Figure out what someone
  likes before you need a favor from them.
- **Don't run into the mountains — or the desert, or Aurelia — before
  you're ready.** Nothing out there scales down to meet you.
- **Know what you're swinging at.** A mace beats plate; a blade beats an
  unarmored foe. Carrying more than one weapon type is rarely wasted.
- **Retreat is a gamble, not a button.** Don't pick a fight you're not
  prepared to either win or lose.
- **The notice board refreshes.** If nothing on it appeals to you
  today, come back tomorrow.
- **Nothing valuable stays a secret for long.** If a rumor points
  somewhere, it's usually worth a look.
- **Go somewhere you've never been.** A new road, a new face, a new
  stone in your pack: the first time is the only time it pays, so the
  fastest way to grow is to keep moving rather than to keep killing.

Good luck out there.

*— The Riverside Adventurers' Guild (unofficial, unaffiliated, and not
responsible for anything that happens to you beyond the village gate)*
