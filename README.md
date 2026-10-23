# MUD Engine

[![Server tests](https://github.com/jbax-and-his-ai-pals/008-mud/actions/workflows/server-tests.yml/badge.svg)](https://github.com/jbax-and-his-ai-pals/008-mud/actions/workflows/server-tests.yml)
[![Editor checks](https://github.com/jbax-and-his-ai-pals/008-mud/actions/workflows/editor-checks.yml/badge.svg)](https://github.com/jbax-and-his-ai-pals/008-mud/actions/workflows/editor-checks.yml)
[![Client checks](https://github.com/jbax-and-his-ai-pals/008-mud/actions/workflows/client-checks.yml/badge.svg)](https://github.com/jbax-and-his-ai-pals/008-mud/actions/workflows/client-checks.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)

A data-driven text-RPG (MUD) engine in Python, with a Godot client and a Godot world editor.
**All functionality lives in the engine; a game is content only**: JSON files in a *content set*
that the engine validates, serves and the editor can author. The same engine runs a fantasy
frontier, a sci-fi salvage yard, a modern night shift, and faithful-in-shape adaptations of three
classic console RPGs, which exist to find and harden the engine's gaps.

## Games that ship in the tree

| Content set | What it is |
|---|---|
| [`dq1_slice`](content_sets/dq1_slice) | *The Dawnglass*: a complete, finishable adaptation of the original Dragon Quest. Level table, dark caves, encounter zones, a rainbow bridge, a two-form final boss. [Walkthrough](docs/reference/DQ1_SLICE_WALKTHROUGH.md) |
| [`zelda1`](content_sets/zelda1) | *The Starcrown of Ardenmoor*: a complete adaptation of the first Legend of Zelda quest. Hearts and half-hearts, bombs that open walls, candles, eight dungeons, a boss who must be searched out. [Walkthrough](docs/reference/ZELDA1_WALKTHROUGH.md) |
| [`ff4_slice`](content_sets/ff4_slice) | A party-based slice of Final Fantasy IV: companions, scenes, cutscenes, a Paladin conversion. [Walkthrough](docs/reference/FF4_SLICE_WALKTHROUGH.md) |
| [`fantasy_frontier`](content_sets/fantasy_frontier) | The large, open sandbox set: crafting, procedural loot, schedules, factions, weather, dynamic quests. |
| [`orbital_salvage`](content_sets/orbital_salvage), [`night_shift`](content_sets/night_shift), [`modern_capsule`](content_sets/modern_capsule) | Sci-fi, modern and capsule proofs that the engine carries no fantasy assumptions. |

Every name in the adaptations is changed; they are engine tests, not releases.

## What is in the box

* **Engine** (`server/engine/`): a headless, server-authoritative simulation with TCP and WebSocket transports, persistence, real-time combat, abilities, quests, dialogue graphs, scenes, triggers, companions, dark rooms, encounter zones, hearts or numbers, crafting, economy, weather and time.
* **Content sets** (`content_sets/`): data only. A validator (`toolkit/content_set_validator.py`) refuses bad values before a game boots.
* **World editor** (`mud-world-editor/`): a Godot app that authors every content kind, writes the same JSON byte for byte, and is checked against the engine's own vocabulary.
* **Godot client** (`client/`): panels, clickable text, a test mode with checkpoints.
* **Toolkit** (`toolkit/`): launcher GUI, scripted playthroughs (`play_script.py`, `adaptation_walkthroughs/`), authoring helpers.

## Quick start

Needs Python **3.12**. From the repository root:

```bash
# Windows: creates .venv and installs the locked dependencies
powershell -ExecutionPolicy Bypass -File bootstrap.ps1
# Linux / macOS
python3.12 -m venv .venv && .venv/bin/python -m pip install -r server/requirements.lock
```

Play in a terminal (use `.venv/Scripts/python.exe` on Windows):

```bash
python server/server_main.py --content-set content_sets/zelda1
python server/server_main.py --content-set content_sets/dq1_slice
```

Or read what a scripted player reads, with no setup of your own:

```bash
python toolkit/play_script.py zelda1 look "go in" "talk old man" "reply 1"
```

Serve a set to the Godot client over WebSocket:

```bash
python server/launch_content_set.py --transport ws --content-set content_sets/zelda1
```

`launcher.bat` (or `python toolkit/launcher.py`) is a small GUI that picks a set, validates it,
starts and stops servers and opens the client or editor. Its **Quick play (Test)** starts a
throwaway server with test tools: skip a scene, or jump to any checkpoint of the story.

## Checking your work

```bash
python check.py            # all four gates (unit, content, editor, client), about two minutes
python check.py --quick    # only what your diff can affect, plus the content gate
python run_tests.py --modules tests.singles.test_zelda1
```

## Making a game

A content set is a folder: a manifest, a ruleset, and `data/` JSON for regions, items, creatures,
dialogue, quests, scenes and triggers. Start with
[`docs/reference/AUTHORING_A_CONTENT_SET.md`](docs/reference/AUTHORING_A_CONTENT_SET.md); the two
complete adaptations above are the best worked examples. Changing the engine itself has a checklist
per kind of change in [`docs/reference/ENGINE_CHANGE_RECIPES.md`](docs/reference/ENGINE_CHANGE_RECIPES.md).

## Documentation

[`docs/README.md`](docs/README.md) sorts everything by how fast it changes: `plan/` (what is next),
`reference/` (how it works), `design/` (why), `archive/` (history). [`ROADMAP.md`](ROADMAP.md) holds
standing decisions; [`CLAUDE.md`](CLAUDE.md) is the working guide for contributors and AI assistants.

## Project layout

```text
server/engine/       the engine (commands, world, npcs, magic, items, player, server/ transports)
server/tests/        unit and journey tests
content_sets/        the games (data only)
mud-world-editor/    Godot world editor
client/              Godot game client
toolkit/             validators, launcher, scripted playthroughs, authoring tools
docs/                plan, reference, design, archive
```

---

## 📜 Command Reference

### Movement
*   `go <dir>`, `n`, `s`, `e`, `w`, `u`, `d` - Move in a direction.
*   `enter`, `out` - Enter or exit buildings/portals.
*   `climb`, `swim` - Traverse specific terrain (may require skills).

### Interaction & Items
*   `look` / `l` - Look at the room.
*   `look <target>` / `x <target>` - Examine an item or NPC.
*   `take <item>` / `get <item>` - Pick up an item (supports `take all`).
*   `drop <item>` - Drop an item on the ground.
*   `put <item> in <container>` - Store items.
*   `open <container>` / `close <container>` - Interact with chests/doors.
*   `use <item>` - Drink potions, read scrolls, etc.
*   `equip <item>` / `unequip <item>` - Manage gear.
*   `pick <direction/container>` - Attempt to pick a lock (requires Lockpick).
*   `pull <object>` - Interact with levers or switches.
*   `gather <node>` - Harvest resources (requires tools like Pickaxe).

### Combat
*   `attack <target>` / `kill <target>` - Initiate physical combat.
*   `cast <spell> [on <target>]` - Cast a spell. Target defaults to enemy if in combat.
*   `stop` - Stop attacking or auto-traveling.

### Social & Trade
*   `talk <npc>` - Start a conversation.
*   `ask <npc> <topic>` - Ask about a specific keyword (e.g., "job", "rumors").
*   `trade <npc>` - Open the trade interface.
*   `buy <item> [qty]` / `sell <item> [qty]` - Transact with vendors.
*   `repair <item>` - Pay an NPC to repair gear.
*   `give <item> to <npc>` - Hand over items (used for quests).
*   `follow <npc>` - Start following an NPC.
*   `guide <npc>` - Ask a quest giver to lead you to the quest location.

### Crafting & Skills
*   `recipes` - List known recipes and nearby stations.
*   `craft <recipe_id>` - Create an item.
*   `salvage <item>` - Break an item down into materials.
*   `skills` - View your skill proficiency (e.g., Mining, Lockpicking).

### Information
*   `inventory` / `i` - Show inventory.
*   `status` / `st` - Show health, mana, stats, and active effects.
*   `spells` - List known spells and cooldowns.
*   `journal` / `quests` / `log` - View active or completed quests.
*   `time` - Check the current in-game time and date.
*   `calendar` - View the full calendar (day/month names, days per week/month).
*   `weather` - Check current weather conditions.
*   `map` / `minimap` - Toggle the ASCII minimap panel.
*   `help` - Show command categories.

### System
*   `save [filename]` - Save the game.
*   `load [filename]` - Load a game.
*   `quit` - Return to title screen.
*   `view <panel> <on/off>` - Toggle UI panels.
*   `invmode <text/icon/hybrid>` - Change inventory display style.

---

## 🛠️ Modding & Adding Content

Because the engine uses JSON for almost all content, you can add new items, monsters, and spells without writing Python code.

### 1. Adding a New Item
Create a file in `content_sets/<your_set>/data/items/my_items.json`:
```json
{
  "item_fire_brand": {
    "type": "Weapon",
    "name": "Fire Brand",
    "description": "A sword wreathed in flame.",
    "weight": 4.0,
    "value": 500,
    "properties": {
      "damage": 12,
      "equip_slot": ["main_hand"],
      "equip_effect": {
        "type": "stat_mod",
        "modifiers": {"damage_fire": 5}
      }
    }
  }
}
```

### 2. Adding a New Spell
Create a file in `content_sets/<your_set>/data/magic/my_spells.json`:
```json
{
  "meteor_swarm": {
    "name": "Meteor Swarm",
    "description": "Calls down meteors on all enemies.",
    "mana_cost": 50,
    "cooldown": 30.0,
    "level_required": 10,
    "target_type": "all_enemies",
    "effects": [
      {"type": "damage", "value": 40, "damage_type": "fire"},
      {"type": "apply_dot", "dot_name": "Burn", "dot_damage_per_tick": 5}
    ]
  }
}
```

### 3. Creating a New Region
Create `content_sets/<your_set>/data/regions/my_dungeon.json`:
```json
{
  "name": "The Dark Hold",
  "description": "An ancient fortress.",
  "rooms": {
    "entry": {
      "name": "The Gate",
      "description": "A massive iron gate stands here.",
      "exits": {"north": "hallway"}
    },
    "hallway": {
      "name": "Dark Hallway",
      "description": "Torches flicker on the walls.",
      "exits": {"south": "entry"},
      "initial_npcs": [{"template_id": "goblin"}]
    }
  },
  "spawner": {
    "monster_types": {"goblin": 5, "orc": 1},
    "level_range": [2, 5]
  }
}
```

---


## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). A change is done when
`python check.py` passes.

## License

No license has been chosen yet, so all rights are reserved by the authors until one is added.
