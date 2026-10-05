# Authoring a Content Set

For the **planned editor-first journey**, milestones and safe system overhauls,
see the [game-authoring roadmap](../plan/game-authoring-roadmap.md). This guide
describes the current file/CLI contract; that plan is not a claim that all of its
workflows are already available in the editor.

This is the guide from an empty directory to a set that boots and passes the
gate. Every command in it has been run, and every JSON fragment is a truncation
of a file that exists.

**Verified 2026-09-20** against this checkout. If a fact here disagrees with
`server/engine/server/content_set/`, the code is right and this page is stale —
the shapes it describes live in that one file, so the fix is local.

---

## 1. The one idea

**Content declares; the engine resolves.** The engine does not know what a barrel
is, a spell is, or a hazard is. It knows how to read a declaration and hand the
answer to the systems that ask.

Two shipped sets say the same thing in different words. In `fantasy_frontier` a
workbench is an item that names a crafting station
(`data/items/materials.json`):

```json
"item_drying_rack": {
  "type": "Item",
  "name": "drying rack",
  "description": "Slatted wooden frames stacked for air-drying herbs and meat.",
  "properties": { "crafting_station_type": "drying_rack", "can_take": false }
}
```

In `orbital_salvage` the same declaration carries a fabrication bay
(`data/items/gear.json`):

```json
"item_fabricator": {
  "type": "Item",
  "name": "fabricator",
  "properties": { "crafting_station_type": "fabricator", "can_take": false }
}
```

The engine never learns what a "drying rack" is. It learns that this room holds a
station called `drying_rack`, and a recipe that says `"station_required":
"drying_rack"` becomes craftable here — which is how the same code path serves a
space station's fabricator.

The practical consequence for you as an author: when something you want does not
exist, the question is *"which declaration is missing"*, not *"which engine
feature is missing"*. And when a decision belongs to the engine (what a class
name is, what `hostile` means), you will find it in
[content-authoring-and-mod-publishing-guidelines.md](content-authoring-and-mod-publishing-guidelines.md)
under **Closed engine vocabularies**.

---

## 2. The contract

A content set is a directory. The gate finds it at `content_sets/<set_id>/`, and
the editor can scaffold one for you (*Create content set…*), but the shape is
small enough to write by hand.

### `content_set.manifest.json`

| Field | Value |
|---|---|
| `id`, `title`, `version` | Required strings. `id` must match the directory name; `version` is semver-ish (`0.1.0`). |
| `manifest_schema_version` | `"1"`. |
| `engine_api_min` / `engine_api_max` | `"1.0"` / `"1.0"` — this set works on engine API 1.x. |
| `paths.content_root` | `"data"`. |
| `paths.ruleset` | `"rules/ruleset.json"`. |
| `paths.presentation` | `"presentation/default.json"`. |
| `paths.opening` | Optional, but a set with one gets a proper arrival screen. |
| `start.region_id` / `start.room_id` | Where a new character wakes up. Both must exist. |
| `start.scenario_id` | A name for the opening scenario. |
| `capabilities` | The systems this set turns on. |

### `data/` — three directories are required, always

`regions/`, `items/`, `npcs/`. Declaring the `quests` capability adds two more,
`quests/` and `campaigns/` — the gate says
`missing required data directory 'quests'` if you forget.

### The eleven capabilities

`inventory`, `dialogue`, `combat`, `abilities`, `magic`, `crafting`, `gathering`,
`quests`, `collections`, `discoveries`, `social`.

Each one builds a subsystem and gates its commands. Two rules bite first:

* **The manifest and the ruleset must agree.** `"capabilities": ["quests"]` with
  `ruleset.systems.quests.enabled: false` is
  `ruleset.systems.quests.enabled conflicts with manifest capability 'quests'` —
  an error, not a warning. Either declare the capability and drop the `systems`
  entry (declared *is* enabled), or set it `true` as well.
* **A capability with no content gets a warning, not an error.** A set with NPCs
  and no `social` section is told its NPCs have no bond surface. That is usually
  correct for a small set; keep it knowingly.

---

## 3. The walkthrough

Everything below is a fragment of a working minimum: one region, two rooms, one
item, one NPC, one conversation topic.

**`content_set.manifest.json`**

```json
{
  "id": "wayfarer_camp",
  "title": "Wayfarer's Camp",
  "version": "0.1.0",
  "manifest_schema_version": "1",
  "engine_api_min": "1.0",
  "engine_api_max": "1.0",
  "paths": {
    "content_root": "data",
    "ruleset": "rules/ruleset.json",
    "presentation": "presentation/default.json",
    "opening": "opening/arrival.json"
  },
  "start": { "scenario_id": "arrival", "region_id": "camp", "room_id": "gate" },
  "capabilities": ["inventory", "dialogue"]
}
```

**`data/regions/camp.json`** — a region is a name, a description, and rooms. An
exit is a direction and a room id; `north` from `gate` lands in `fire`, and exits
are one-way unless you write the other one too. Rooms place things with `items`
and `initial_npcs`, which is how every NPC and object in the shipped sets gets
into the world.

```json
{
  "region_id": "camp",
  "name": "Wayfarer's Camp",
  "description": "A small camp where the road gives up on the hills.",
  "properties": { "safe_zone": true },
  "rooms": {
    "gate": {
      "name": "Camp Gate",
      "description": "A gap in a thorn fence, with a cart track running north.",
      "exits": { "north": "fire" }
    },
    "fire": {
      "name": "Cook Fire",
      "description": "A low fire under a tripod, and a bench worn smooth.",
      "exits": { "south": "gate" },
      "items": [{ "item_id": "travel_ledger" }],
      "initial_npcs": [{ "template_id": "cook", "instance_id": "cook_at_fire" }]
    }
  }
}
```

**`data/items/camp_kit.json`** — items are templates keyed by id. `properties` is
where behaviour lives when it needs no code: `use_text` is what `use` prints,
`equip_slot` makes a thing wearable, `can_take: false` makes it scenery. A set
with a `contracts/world_contracts.json` can also assign an `item_family`, which
is what the advancement ledger matches on (see §4).

```json
{
  "travel_ledger": {
    "type": "Item",
    "name": "travel ledger",
    "description": "A ruled notebook, half full of somebody else's distances.",
    "weight": 0.4, "value": 3, "stackable": false,
    "properties": {}
  }
}
```

**`data/npcs/camp_folk.json`** — `faction` and `behavior_type` are the two closed
vocabularies here; `dialog` is the flat keyword dictionary that `ask <npc> <topic>`
reads. An NPC who needs a conversation with branches points at a dialogue graph
instead, with `properties.dialogue: "<graph id>"` and a file in `data/dialogue/`.

```json
{
  "cook": {
    "name": "Orla the Cook",
    "description": "A broad woman in a scorched apron.",
    "health": 40, "level": 1, "friendly": true,
    "faction": "friendly", "behavior_type": "stationary",
    "dialog": {
      "greeting": "Sit if you like. It is not ready yet, and it never is.",
      "stew": "Barley, roots, and whatever the last traveller carried too much of."
    },
    "properties": { "wander_chance": 0, "move_cooldown": 9999 }
  }
}
```

**A dialogue node can ask for its words to be revealed slowly.** Text is shown at once by
default. Give a node `"pace": "slow"` and a client that supports it types the NPC's words out a
few characters at a time, so a story beat (the king's orders, a vision) is read rather than
scanned; the player can skip ahead by clicking the log or sending a command, and can turn the
effect off in the client. A pace is a name (`brisk` 180, `measured` 110, `slow` 70, `solemn` 40
characters a second) or a number from 5 to 200. Only the NPC's words are paced, never the replies
or the instructions, and only for players (authoring views show everything). The server marks the
passage (`[[PACE:25]]...[[/PACE]]`, like colours and links); a client that does not reveal
gradually shows it at once. The validator refuses anything that is not a pace.

**Leaving ends a conversation, and a node can be a scene.** Walking away from an NPC (or being
taken away, or the NPC leaving or dying) ends the conversation with them; a later `reply` says you
are not talking to anyone. A node marked `"must_answer": true` insists on an answer: while it is
open the player cannot move or act on the world (fight, use, drop, cast, trade...), each attempt
is refused with "<NPC> awaits your answer" and the replies are shown again. Looking, the pack,
status, the journal, help and saving still work, so the player can read their options. Use it
sparingly, for a moment that must be played through (the king's orders). It needs at least one
choice and cannot be an `"end": true` node; the validator refuses both mistakes.

A node marked `"narration": true` is told plainly instead of said: no `<NPC> speaks:` line and no quotation
marks, so a still figure or a deathbed can be written as what the player sees (`(She does not stir.)`).
The validator refuses a value that is not true or false.

Quest text is paced `slow` by default without any authoring: a player's client is asked to reveal
every paragraph that starts `[Quest Accepted]`, `[Quest Update]`, `[Quest Complete]`,
`[Objective ...` or `New Objective:`. A server turns that off or changes it with
`server.quest_text_pace` (a pace, or `None`); a player option for it is still to come.

**`rules/ruleset.json`** — the set's own rules. `systems` mirrors the manifest
(see §5), and everything else is optional: progression curve, skills, weather,
hazards, social tiers, quest generation, crime. A set that declares nothing gets
the engine's defaults, which are the *neutral* ones — an undeclared ladder means
no bonds at all.

```json
{
  "progression_model": "level_based",
  "systems": {
    "inventory": { "enabled": true },
    "dialogue": { "enabled": true },
    "combat": { "enabled": false }
  }
}
```

**`presentation/default.json`** — presentation overrides: theme pack, currency
name, prompt styling. `{}` is valid.

**`opening/arrival.json`** — what a new character is told. `scenario_id` is
required; `objectives` are numbered suggestions, each with the literal command to
type, and `objectives_heading` lets you replace "First steps:". An optional `pace` (`brisk`, `measured`, `slow`,
`solemn`, or characters per second) has a client type the whole brief out instead of showing it at once.

```json
{
  "scenario_id": "arrival",
  "heading": "Arrival",
  "intro": "You have walked further than you meant to.",
  "objectives_heading": "First steps:",
  "objectives": [
    { "id": "orient", "instruction": "Take in the gate and its exits", "command": "look" },
    { "id": "warm_up", "instruction": "Walk north to the fire", "command": "north" }
  ]
}
```

### Booting it

```bash
python server/launch_content_set.py --content-set content_sets/wayfarer_camp --dry-run
python server/launch_content_set.py --content-set content_sets/wayfarer_camp --transport ws
```

`--dry-run` prints the command it would run without starting anything, which is
the fastest way to find a typo'd path. Once running, a session starts with no
character: the first command is `char create <name>` (add
`as <background>` if the set declares backgrounds), and the opening you wrote is
printed as the reply.

---

## 4. How it gets checked

Three gates, all from the repository root:

| Gate | What it runs |
|---|---|
| `python run_tests.py --suite all` | 5,700+ unit/journey tests, including every content set's playability journeys, run as parallel shards (under a minute; `--jobs 1` for one process) |
| `python run_content_checks.py` | the validators below, over every shipped set |
| `python run_editor_checks.py --godot <path>` | 30 editor smoke checks, including a byte-compare round trip of every set's files |

The individual checks the content gate runs over one set — run these while
writing, they are seconds each:

```bash
python toolkit/content_set_validator.py content_sets/wayfarer_camp
python toolkit/data_integrity_validator.py content_sets/wayfarer_camp/data
python toolkit/reference_integrity_validator.py content_sets/wayfarer_camp/data
python toolkit/stale_reference_audit.py content_sets/wayfarer_camp/data --output tmp/stale.txt
python toolkit/skill_audit.py content_sets/wayfarer_camp/data
```

**A warning is a verdict, not noise.** `content_set_validator.py` and
`skill_audit.py` are warnings-only *by design* — a skill no check rolls, an item
family no grant pays for, a capability declared without matching content are
design questions, and the gate says so rather than failing your build. An
`[ERROR]` line always names the file, the field, and the fix.

**A new set is only swept once it is listed.** `run_content_checks.py` iterates
`CONTENT_SETS` in `toolkit/content_check_steps.py`, so add your `set_id` to that
tuple (and to `NEUTRALITY_SETS` if the set is not fantasy) to have the gate and
the editor's Validate button cover it end to end. Until then the per-set commands
above still work.

**Two things worth knowing before you author at length:**

* Numbers in JSON are one type. A tool that writes `10.0` where you wrote `10`
  changes what the engine reads, which is why the gate runs
  `normalize_content_numbers.py` over every set.
* Every file a *shipped* set has is also round-tripped through the editor
  (`content_round_trip_smoke.gd`): load, save, compare bytes. Python's
  `Path.write_text` translates `\n` to `\r\n` on Windows and the editor does not,
  so a scripted edit of an editor-owned file is the usual way to turn that check
  red — which is how the sweep behind this document was caught mid-flight.

---

## 6. Where the rest of it lives

| You want | Read |
|---|---|
| Every closed engine vocabulary (`faction`, `behavior_type`, effect keys, objective types) | [content-authoring-and-mod-publishing-guidelines.md](content-authoring-and-mod-publishing-guidelines.md) |
| Running and configuring a server | [server-operator-guide.md](server-operator-guide.md) |
| What a player can type | [PLAYER_MANUAL.md](PLAYER_MANUAL.md) |
| The world's target shape, rings and towns | [../design/WORLD_DESIGN.md](../design/WORLD_DESIGN.md) |
| What to work on next | [`/ROADMAP.md`](../../ROADMAP.md) and [`../plan/chunks-of-work.md`](../plan/chunks-of-work.md) |
| How the engine reads a set | `server/engine/server/content_set/` — the file this page describes |

---

## 5. Adding the second capability

Start with `inventory` and `dialogue`: with those two a set is playable, and
nothing else is required of it.

To add one, change **three** things at once, and the gate will tell you if you
miss one:

1. the manifest's `capabilities` array;
2. the ruleset's `systems` entry for it, if you want it explicitly on (declared
   *is* enabled; disagreeing with yourself is the error);
3. the content the capability is for — `quests` needs `data/quests/` **and**
   `data/campaigns/`, `crafting` needs recipes and a station item, `combat` needs
   something to fight and a `loot_table` worth fighting it for.

### Telling a story

Each of these is read by the engine, refused by the validator when it is wrong, and has a field in the editor.

| What | Where | What it does |
|---|---|---|
| `ready_text` | a quest stage | What the quest update says to do once the objective is done, instead of "Report back to X." (for when the player has not met X). Used for every kind of objective. |
| `completion_narration` | a quest stage | What is *told*, not said, when it is handed in: plain text, no quotation marks. (`completion_dialogue` is spoken, and quoted.) |
| `spawn_on_start.intro` | a quest stage | Beats `{text, after, pace}` told a moment apart before the creature the stage brings in arrives; the creature appears with the last. How far it has got is kept, so a restart carries on instead of leaving a quest with nothing to fight. |
| `entries` | a conversation | Alternate openings `{node, condition}`, tried in order: the first whose condition holds is what the NPC says, and the opening node is what is left. The first node's effects run when it opens. |
| `end: true` | a conversation node | The NPC says it and the conversation is over, with no reply to click through first. |
| `pace` | a conversation node, a campaign transition, an intro beat | How fast a client types the words out (`brisk`, `measured`, `slow`, `solemn`, or characters per second). |
| `properties.despawn_message` | an NPC | How a summoned creature leaves ("The Colossus sinks back into the earth."). |
| `properties.essential: true` | an NPC | Cannot be killed unless recruited as a companion: left on the brink instead. |
| `properties.unique: true` | an NPC | Called "the mayor", not "a mayor". |
| `equipment` | an NPC template | `{"main_hand": "item_iron_sword", "body": "item_leather_tunic"}`: what it starts wearing (slots: main_hand, off_hand, head, body, hands, feet, neck; each item must fit its slot). A weapon in the main hand and armor add to its attack and defense; a companion can be re-dressed in play (`equip <item> on <name>`). |
| `properties.attack_modes` | a Weapon | `[{"verb": "thrust", "text": "{attacker} {verb} {possessive} {weapon} at {defender}", "weapon_damage_type": "piercing", "damage_bonus": 0}, ...]`: the ways it may be struck, one chosen at random for each blow, by a player or a creature holding it (a companion). `verb` is the plain form (conjugated for "You" or anyone else); `text` is the sentence (it must name `{attacker}` and `{defender}`; `{verb}`, `{possessive}` and `{weapon}` are filled too), and the engine adds "and deals N damage." or ", but misses!"; `weapon_damage_type` is the type of blow that way deals. All keys are optional. |
| `properties.rejoin_health` | a companion | 0 to 1 (default 0.6): a companion that fell back hurt rests, keeps out of fights, and rejoins (walking to find the player) once back to this fraction of its health and the player is not fighting. |
| `{"kind": "companion_recovering", "npc_id": ...}` | a condition | A companion that fell back hurt and has not rejoined yet; a conversation uses it to say so ("Give me a moment"). |
| `properties.attack_cooldown` | an NPC | Seconds between its blows, 0.5 to 120 (default 3): slower is easier to read in a staged fight. |
| `properties.respawn_cooldown: -1` | an NPC | Never comes back once dead (a hostile or a friendly alike). |
| `silent: true` | a `move_npc` effect | No "leaves" / "arrives" line: the scene says it in its own words ("The chancellor leads you north."). |
| `properties.phases: [{name, seconds, message, untouchable, counter, counter_cooldown, hint, counter_hint, miss_text, resistances}]` | an NPC | States a creature cycles through while it fights, each for `seconds` (out of a fight it rests in the first). Each change tells the room its `message`, then a `hint` an NPC who is in the room says (`{npc, text}`: a companion reading the fight for the player). An `untouchable` phase cannot be hurt: blows and damaging abilities miss it (`miss_text` is told), its friends hold back, and a `counter` ability (a spell id, used on every enemy in the room) answers whoever tries, at most once every `counter_cooldown` seconds (default 3), with a `counter_hint` told alongside. The Fog Drake is solid for twelve seconds and mist for ten. |
| `properties.hides_when_hurt: true` | an NPC (a companion) | When hurt (below its `flee_threshold`) it ducks out of a fight without leaving the room: it takes no part, cannot be hit, and comes out when the fight is over or it has been healed past `rejoin_health`. |
| `properties.falls_when_defeated: true` | an NPC (a companion) | A blow that would kill it puts it down instead: alive at 0 health, out of the fight, unhurtable and unhealable, until it is revived (`revive` spell effect, `revive` item, an inn's `restore` with `companions: true`) or gets up by itself some seconds after the fighting stops. Without it a companion dies as before. |
| `properties.grants_spells: ["lullaby"]` | a weapon or armour | A companion who holds it can cast those abilities (a harp that carries a song); put down, the songs go with it. |
| `properties.untargetable: true` | an NPC | Nothing picks it as a target and nothing that reaches it hurts it. With `pacifist` it takes no part in a fight at all: a child carried through one, a passenger. |
| `properties.pacifist: true` | an NPC | Never fights back and never starts a fight: it can be attacked and killed, and it does not retaliate. |
| `ruleset.factions.enmities` | the ruleset | `[{"faction": "red_fleet", "against": "ilmaran"}]`: the first faction attacks the second on sight, without either turning on the player. One way; list the pair both ways for a mutual fight. Both must be declared (`factions.extra` or an engine faction). |
| `{"kind": "npc_present", "npc_id": ..., "region_id", "room_id"}` | a condition | A living NPC of that template (or placed id), anywhere or in the room named (region and room together). `{"not": ...}` of it is "the last one is gone". |

**Scenes.** A scene is something the player watches: beats told a moment apart, with things happening between them.
`data/scenes/*.json` holds them (each file an object of scenes keyed by id):

```json
"ilmara_falls": {
  "beats": [
    {"text": "The doors burst inward, and the soldiers pour in.", "pace": "measured"},
    {"after": 3.5, "text": "Steel rings.", "pace": "slow", "effects": {"remove_npc": "acolyte_1"}},
    {"after": 3, "text": "Take the crystal. (take crystal)"}
  ]
}
```

A beat is `{text, after, pace, effects}`: `after` is the wait in seconds after the beat before it (0 before the first, 2
between the rest, up to 600), `pace` how fast a client types it out, and `effects` the same vocabulary a conversation
uses (people leave, a fight is spawned, the player is carried somewhere, the clock jumps on). The `play_scene` effect
begins one, so a trigger, a conversation, a quest or a campaign node can; a beat can begin another. While a scene runs its
player is a spectator (commands that change the world are refused, and so is starting a conversation: nobody can be talked to first; `reply` to one already open, and reading, are allowed) unless the scene says `"lock": false`; how far it has got is
kept, so a restart carries on instead of leaving the story half told. Three more things make an opening out of
these: a trigger's `on_enter` fires for a new character's first room, `item_taken` is a trigger event (the crystal on its altar),
`room_cleared` fires when the last enemy in a room dies (the second wave a short while after the first), and `advance_time`
(`{"to_hour": 6}`) lets a night pass. A starting-inventory entry may say `"equip": true` to begin worn.

**Skipping ahead, for testing.** `end_scene` (a scene id or a list) finishes a scene without telling it, so it counts as seen;
a scene whose id starts with `checkpoint_` and whose beats carry effects (`end_scene` for the story told so far, `set_flag`,
`give_item`, `start_campaign`, `recruit`, `teleport`...) is a *checkpoint*: it stands in for playing up to a point. In a test
session (not a player's) `checkpoint` lists them and `checkpoint <name>` jumps to one at once (what was running is ended); `scene`
lists the scenes, `scene skip` tells what is left of the running one at once, and `scene play <id>` / `scene end <id>` begin or
finish one. Checkpoints are offered (by `checkpoint` and in the client's picker) in the order the set declares them, so declare them in the order
of the story, in one file. The story slice has `checkpoint king` (the crystal in your pack, in the throne room) and `checkpoint road` (the king's
orders given, Kessa at your side on the castle road).

**Where the player rises after dying.** A player respawns at a point the character carries, which starts as the story's
start. The `set_respawn` effect (`{"region": "varenholt", "room": "castle_gate"}`) moves it: use it in scenes and triggers as the
story gets somewhere worth coming back to (the castle once the opening is over, the inn of a new village), so that dying in the
desert does not put the player back in the first room.

**Songs and other status abilities.** An ability whose `apply_effect` carries `effect_data` with `tags` does what the tag says to a
creature: `sleep` (it does nothing until it is struck), `silence` (it does not cast), `confuse` (it strikes at whoever is nearest, friend or
foe), alongside the older `Stun`. A companion may cast an `all_enemies` ability at every enemy in the room at once.

**A companion who tends the party.** A companion that knows a spell with a `heal` effect (target `friendly`) mends whoever in the party is below 60% health, and one that knows a `revive` effect (`{"type": "revive", "value": 50}`: the percent of health restored, 0 meaning a quarter) stands the fallen up first. They act on the same rhythm as a blow (`combat.pacing`). A heal does not raise the fallen; a `revive` consumable (`effect_type: revive`, `effect_value` the percent) used on a companion does.

**A companion who learns.** `teach_companion` (`{"npc": "ryn_young", "spell": "lightning"}`) gives one of the player's companions an
ability for good: it is added to what they cast and saved with them (`properties.learned_spells`). The slice has Belaric teach Ryn
lightning at the camp, in a scene.

**Vehicles.** `data/vehicles/*.json` (each file an object of vehicles keyed by id): `{"skimmer": {"name": "the skimmer", "description": "...", "start": {"region": "ashmere", "room": "boathouse"}, "board_text": "...", "disembark_text": "...", "lands_in_biomes": ["desert"], "note": "..."}}`. Only `name` is required. A vehicle waits in its `start` room (or is put somewhere by the `place_vehicle` effect), and the player `embark`s (`board`'s word is taken by the quest board) when it is in the room and `disembark`s to leave it parked; it goes wherever its rider goes. It may be set down only in a region whose `biome` is listed in `lands_in_biomes` (omit it to land anywhere), or in any room whose `properties.docks` lists the vehicle. A way that needs one is an exit requirement `{"type": "vehicle", "vehicle": "skimmer"}` (an id, or a list of ids; `failure_message` optional). The story has `place_vehicle` (`{vehicle, region, room}`: a story moving it; whoever rode it is put ashore), `board_vehicle` (a vehicle id: the player is put aboard, the vehicle comes to wherever they stand) and the `aboard` condition (`vehicle_id` optional). A rider who dies leaves it where they fell. Where each vehicle is is kept in the world's state and what the player rides with the character.

**Resistances, absorption and a phase's own.** A creature's `stats.resistances` (and an item's) are percents by damage type: 50 halves it, -100 doubles it, 100 takes none. From 101 to 200 the creature *absorbs* the blow: it takes nothing and is healed by the excess ("drinks in the fire and is healed"). A phase may carry `resistances` (`{"fire": 200, "ice": -50}`) that add to the creature's own while that phase lasts: a fire-master under a cloak of flame that cannot be burned, a creature of ice that takes double from flame until it thaws.

**A fight the story decides.** The trigger event `health_below` (`{"event": "health_below", "who": "player", "fraction": 0.25}`; `who` is `player` or an NPC's template or placed id; an optional `region`/`room` narrows it) fires as a blow takes `who` past that share of its health, once per crossing; with the `end_fight` effect (`{}` for the player's room, or `{region, room}`: everyone there stops fighting) and a scene, it is the duel the hero cannot win, or a boss that yields at half.

**More for an ability to do.** `windup` (`{"seconds": 3, "leave_message": "{caster_name} leaps away!", "land_message": "{caster_name} drops on {target_name}!"}`, an `enemy`-target ability only): the caster is gone for those seconds (airborne: it acts not, cannot be struck and is not picked) and then the effects fall on the target, if it is still there. `requires_ally: ["npc_template"]`: cast only while those NPCs stand beside the caster, alive and able to act (a twin spell). Effect `percent_damage` (`value`: the percent of the target's *current* health it takes, 0 meaning a quarter; a creature with `properties.percent_immune: true` is untouched) and effect `steal` (takes the next item from the target's `properties.steal_items: [{"item_id": "item_ruby", "chance": 0.5}]`, once each, for the caster or a companion's owner; a creature does not waste its turn stealing from someone with nothing left). The status tag `petrify` (an `apply_effect` with `effect_data.tags: ["petrify"]`) turns a creature to stone: it does nothing, cannot be struck and is not picked, until a `cleanse` of that tag frees it; a companion with such a cleanse frees a petrified friend by itself.

**An exit that warns.** A room's `properties.exit_requirements` gives one direction a rule; a `warning` is met once:
`{"south": {"type": "warning", "scene": "warn_pool", "failure_message": "You start south, and stop."}}`. The first attempt to go
that way is refused (the `failure_message` is shown at once) and the scene told (give it `"lock": false` and slow beats, so the
player may simply try again); the second attempt, and every one after, goes through. It is remembered on the player
(`exit_warned:<region>:<room>:<direction>`). A `warning` needs a `scene`, a `failure_message`, or both. The story slice's cave
warns three times this way before its last hollow.

A fight need not be narrated: give two factions an enmity (`ruleset.factions.enmities`), spawn the aggressors from a beat,
and the engine's ordinary combat tells it. The victims can be `pacifist`. A death the player only watched fires
`npc_killed` triggers (and nothing else: no XP, quest credit or reputation), so a trigger on the victims' template with
`when: {"not": {"kind": "npc_present", ...}}` plays the next scene when the last of them has fallen.

**Quest text speed.** Quest text is story, so a player's client types it out. The engine's default is `slow`;
a set can ask for its own with `presentation.quest_text_pace` (a pace, or `"instant"`); a server's operator can
override both with `session.quest_text_pace` in the server config; and a player can turn typing off or change its
speed in the client. Lines a conversation or scene gives its own `pace` keep it.

**What a level brings.** `ruleset.advancement.level_up` says what each level is worth:
`"stat_growth": {"default": 1, "strength": 2, "agility": 0}` (what each stat gains; `default` is every stat not
named, and 0 means it never grows) and `"health_base": 5` (the flat health a level brings, before what the health stat
adds). Several levels gained at once are reported once, as the whole difference.

**The engine's own words.** `ruleset.messages` replaces the sentences the engine says at the moments every game has:
`kill_experience`, `kill_gold`, `shared_experience`, `level_reached`, `levels_gained`, `defeated`, `respawn_hint`,
`summon_departs`, `quest_complete` and `scene_locked` (what a player is told when a command is not taken while
a scene plays; the client also mutes its command line and shows that line as its hint for as long as the scene runs).
A line may use only the fields its message has, written `{like_this}`
(the editor shows them); a line that cannot be used leaves the engine's words in place. Colour and layout stay with
the engine.

**Naming one-of-a-kind characters.** A lowercase NPC name takes an article in the text ("a goblin", "an innkeeper"). Set `properties.unique: true` on someone who is the only one of their kind and the text says "the mayor of Hazevale" instead. The Properties section of the NPC inspector has a "Unique" box for it.

**Who earns experience (and money) for a kill.** Everyone who hurt the creature earns a share, however many players
there are and whoever struck the last blow; an ally's blows (a summon, a companion) count for its owner,
and an NPC ally that is not owned takes a share of the damage that is simply not paid out. Players who were
not in the room are told what they earned. `ruleset.combat.experience_sharing` changes the rule:
`"mode"` is `"proportional"` (the default: each earns their share of the damage), `"equal"` (every
participant earns the same) or `"killer"` (whoever lands the killing blow earns it all, as in older games),
and `"min_share"` (default `0.05`, from 0 up to but not including 1) is the least a player must have done to
count as a participant, and `"memory_seconds"` (default `300`; `0` never forgets) is how long a blow counts: a
creature that was left, healed and fought again does not pay the people who hurt it earlier (and one back at full
health starts a new tally at once). The same shares split the money the creature drops (its `loot_table.gold_value`),
and the player who is watching is told what they earned in the kill's own message, before the quest update.
The ruleset editor has a section for it ("Experience from a kill").

**The rhythm of a fight.** Every creature but the player acts on its own cooldown (`properties.attack_cooldown`). `ruleset.combat.pacing` slows and staggers all of them at once, so a party and a crowd do not fire in the same instant: `"npc_cooldown_scale"` (1 to 10, default 1) stretches every creature's pause between actions, monsters, allies, companions and summons alike, and `"action_gap"` (0 to 10 seconds, default 0) is the least time between any two creatures' actions in the same room, so their blows arrive one after another. The player's own cooldown is untouched: they are the quick one. A world with no `pacing` is as it always was. `python toolkit/combat_noise.py <set> <checkpoint> "go east"...` plays a fight and reports lines a second, to tune it by.

**How much of a fight a player reads.** The player chooses with `combat full` (every line, and where everyone starts), `combat normal` (what matters in full, the rest folded into a short summary every few seconds) or `combat brief` (only what matters). What matters, always told in full: a blow at the player, a death, a spell, song or special attack, a friend knocked low. The numbers stay in the text at every level. The choice is kept with the character.

What each capability gives you, and what the gate says when the content is thin:

| Capability | Turns on | The common first message |
|---|---|---|
| `combat` | `attack`, combat AI, hazards, `flee` | `ruleset.combat.retreat` declared with no `skill`: *this section is declared and names no skill, so whatever it gates is ungated* |
| `crafting` | `recipes`, `craft`, `salvage`, stations, quality tiers | A recipe the player cannot reach: check `station_required` names a `crafting_station_type` some item actually declares |
| `gathering` | `gather`, resource nodes, `survey` | A node whose `yields` reference an item nobody authored — validated, and an error |
| `quests` | the board, `journal`, campaigns, dialogue `start_quest` | `missing required data directory 'quests'` (and `'campaigns'`) |
| `abilities` / `magic` | `cast`, the ability pool, `abilities` | An ability no item, trainer or spell-teaching effect grants |
| `social` | bonds, tiers, gift scoring, vendor discounts | A ladder declared with no bottom rung at `min: 0`, or a capability declared with no ladder to show |
| `collections` / `discoveries` | `turnin`, `collection`, `discoveries` | A collection whose members no item satisfies |

The full list of what each one gates is `_CAPABILITY_SYSTEMS` in
`server/engine/server/content_set/` and the check list in
`toolkit/content_check_steps.py`; `toolkit/engine_vocabulary_dump.py` prints the
condition kinds, effect keys, objective types and manifest vocabulary as one JSON
object, which is also what the editor's schema parity check compares against.
