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
19. A Few Words of Advice

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

When you first arrive, you'll be asked to name your character and given
a moment to get your bearings in the town square. From there, four paths
are laid out for you — take any one of them, or ignore all four and
wander off on your own:

1. **Get oriented.** `look` around, check your `inventory`, and note the
   exits from the room you're in.
2. **Help Riverside.** Check the notice board (`look board`), then head
   to the community garden to see what your neighbors need.
3. **Trade and prepare.** Visit Talia at the market to see what's for
   sale before you go looking for trouble.
4. **Explore and face danger.** Equip your rusty dagger and take the
   north road into the woods.

None of these paths closes off the others. Riverside doesn't run out
while you're busy elsewhere.

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
rise in level. Defeating enemies, completing quests, and — in some
cases — simply succeeding at a difficult task all grant experience.

Type `status` any time to check where you stand.

---

## 4. The Lay of the Land

The world beyond your front door is bigger than it first appears.
Here's what's known to be out there:

- **Riverside Village** — home. Market, tavern, shrine, museum,
  blacksmith, and a scattering of houses along a quiet residential lane.
- **Whispering Woods** — the forest north of the village. Wolves, goblins,
  and bandits keep to its shadows; local legend says the woods hide
  something older still.
- **Windy Foothills** — grassy highlands east of the farms, home to
  goblin and orc raiding parties.
- **Frostpeak Mountains** — the high, cold country beyond the foothills.
  Orcs, harpies, trolls, and worse make their homes among the peaks.
  Not a place for the underprepared.
- **Shadow Caves** — a cave network in the hills, seldom visited, full
  of stories nobody can quite confirm.
- **Ancient Ruins** — the crumbling remains of a forgotten civilization,
  buried deep in the Whispering Woods.
- **Murkwater Swamp** — a humid, treacherous bog south of the river.
  Lizardfolk territory, and none too welcoming.
- **Salt-Kissed Path** — the coastal road where the swamp finally gives
  way to open shore.
- **Riverside Farmlands** — the fields and pastures that feed the village.
- **Portbridge** — a harbor town where the Silver River meets the sea.
  Sailors, merchants, a harbourmaster with a tariff problem, and — if
  rumor is to be believed — smugglers working the tunnels beneath it.
- **The Gilded Lotus** — an unexpectedly lavish casino, for those who'd
  rather test their luck than their sword arm.
- **The Obsidian Trial** — an ancient volcanic proving ground, for those
  who've already tested everything else.

You won't see all of this on your first day. That's rather the point.

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

---

## 6. Talking, Trading, and Making Friends

Riverside (and everywhere beyond it) is full of people, not just
monsters. Use `talk <name>` to strike up a conversation, or `ask <name>
about <topic>` once you know what to ask about — new topics reveal
themselves as you learn more.

**Relationships** matter here. Every named NPC you deal with keeps a
private opinion of you, visible with `relationship <name>` (or
`relationships` for the full ledger). Give someone a **gift** they'd
appreciate — with `give <item> to <name>` — and that opinion improves;
give them something they dislike, and it won't. Climb high enough and
you'll cross a **friendship tier** (Stranger, Acquaintance, Friend,
Close Friend), each one unlocking a small vendor discount and, in
some cases, wares or trust-gated opportunities that aren't available
to a stranger.

To do business: `trade <name>` with anyone who deals in goods, then
`list` their wares, `buy <item>`, or `sell <item>`. Some vendors also
keep standing **buy orders** — check `orders` while trading, and
`fulfill <order>` when you've got what they're after. A few of these
are repeatable income if you keep the right materials coming.

---

## 7. Combat

`attack <target>` (or `kill`/`fight`) starts a fight, or joins one
already underway. Combat continues automatically as you exchange blows
— keep attacking, or make a choice about how to get out of it.

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

Check `combat` (or `cstat`/`fightstatus`) at any time for a status
readout of your current fight.

---

## 8. Magic

If you've taken up spellcraft, `cast <spell> [target]` puts it to use,
and `spells` lists everything you currently know. Spells cost
**mana**, which regenerates over time (faster when you're not in a
fight), and most have a minimum level before you can learn them.

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

Type `skills` to see where you currently stand in each.

---

## 10. Gathering & the Wild

The land provides, if you know how to ask. Use `gather` (also
`mine`, `harvest`, or `chop`, depending on what feels right for the
material) on a resource node to collect from it — clay banks, ore
veins, herb patches, fishing spots, and more, each requiring the right
tool and each with a limited number of charges before it needs time to
recover. `survey` will tell you what's available in your current
surroundings, what tool it needs, and how it's holding up.

Some finds are simply better than others — gathered materials can
carry a **quality grade**, and a rare, pristine specimen is worth
seeking out over the ordinary kind, especially if you're crafting
something meant to last.

---

## 11. Crafting

`recipes` shows what you're currently able to make (add `all` to see
recipes you haven't unlocked the materials for yet), and `craft
<recipe>` makes it, provided you're carrying the ingredients and, for
some recipes, standing near the right station. `salvage <item>` breaks
an item back down into raw materials, if you'd rather reclaim than
keep.

Practice matters: crafting the same recipe repeatedly can unlock
higher **quality tiers** — Simple, Fine, Masterwork — each worth more
and, for gifts, more appreciated by the person you hand it to. Using
finer raw materials pushes the ceiling even higher.

`attach` and `detach` handle equipment attachments, for gear that
supports them.

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

Not every quest is solved the same way — some accept combat, some
favor a gathered or crafted solution, and a few will let you `negotiate`
your way through instead of fighting. If an NPC offers to walk you
somewhere, `guide <name>` will have them lead the way; `stop` cancels
being guided (or any other automated action) early.

Some threads run deeper than a single task — multi-stage **campaigns**
with branching outcomes, started through conversation rather than the
board. Choose carefully; these don't always have a clean, single "right"
answer.

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
| **Information** | `look` `status` `skills` `journal` `discoveries` `collection` `relationship(s)` `survey` `appraise` `calendar` `time` `weather` |
| **Interaction** | `talk` `ask` `say` `yell` `give` `take/get` `drop` `use` `read` `examine` `open` `close` `unlock` `pick` `pull` `search` `follow` `guide` `wait` |
| **Combat** | `attack` `flee`/`retreat` `combat` |
| **Magic** | `cast` `spells` |
| **Crafting** | `craft` `recipes` `salvage` `attach` `detach` |
| **Gathering** | `gather` (`mine`/`harvest`/`chop`) |
| **Trade** | `trade` `list` `buy` `sell` `orders` `fulfill` `repair` `repaircost` `stoptrade` |
| **Quests** | `look board` `accept quest` `turnin quest` `negotiate` |
| **Property** | `buy house` `house` `expand house` |
| **Crime** | `steal` `disarm` |
| **Gambling** | `bet` `guess` `hit` `stand` `rules` |
| **Inventory** | `inventory` `equip` `unequip` `invmode` |
| **System** | `help` `save` `load` `quit` `minimap` `view` |

Type `help <command>` any time for the full details on any of these.

---

## 19. A Few Words of Advice

- **Talk to everyone at least once.** Riverside is small, and its
  people remember you.
- **A gift costs little and buys a lot.** Figure out what someone
  likes before you need a favor from them.
- **Don't run into the mountains at level two.** The Frostpeaks don't
  scale down to meet you.
- **Retreat is a gamble, not a button.** Don't pick a fight you're not
  prepared to either win or lose.
- **The notice board refreshes.** If nothing on it appeals to you
  today, come back tomorrow.
- **Nothing valuable stays a secret for long.** If a rumor points
  somewhere, it's usually worth a look.

Good luck out there.

*— The Riverside Adventurers' Guild (unofficial, unaffiliated, and not
responsible for anything that happens to you beyond the village gate)*
