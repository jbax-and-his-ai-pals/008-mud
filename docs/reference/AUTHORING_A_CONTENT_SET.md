# Authoring a Content Set

For the **planned editor-first journey**, milestones and safe system overhauls,
see the [game-authoring roadmap](../plan/game-authoring-roadmap.md). This guide
describes the current file/CLI contract; that plan is not a claim that all of its
workflows are already available in the editor.

This is the guide from an empty directory to a set that boots and passes the
gate. Every command in it has been run, and every JSON fragment is a truncation
of a file that exists.

**Verified 2026-09-20** against this checkout. If a fact here disagrees with
`server/engine/server/content_set.py`, the code is right and this page is stale —
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
type, and `objectives_heading` lets you replace "First steps:".

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
| `python run_tests.py --suite all` | 4,500+ unit/journey tests, including every content set's playability journeys |
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
| How the engine reads a set | `server/engine/server/content_set.py` — the file this page describes |

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
`server/engine/server/content_set.py` and the check list in
`toolkit/content_check_steps.py`; `toolkit/engine_vocabulary_dump.py` prints the
condition kinds, effect keys, objective types and manifest vocabulary as one JSON
object, which is also what the editor's schema parity check compares against.
