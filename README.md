# Pygame Text RPG Engine

A robust, modular, and data-driven Text-Based RPG engine built with Python and Pygame. While visually presented as a classic MUD (Multi-User Dungeon), it features a modern hybrid UI with clickable text, hotbars, and mouse interaction, sitting on top of a deep simulation of world mechanics.

## 🚀 Getting Started

### Prerequisites
*   Python 3.11+
*   Pygame (`pip install pygame`)
*   Transformers / PyTorch (Optional, for LLM-based ambient flavor text)

### Running the Game
```bash
python main.py
```
*   **Arguments:**
    *   `--save <filename>`: Load a specific save file (default: `default_save.json`).

## ⚙️ Engine Systems

This engine is built on a Component-Entity-System architecture heavily reliant on JSON data definitions.

### 1. World & Environment
*   **Dynamic Region Generation:** Procedural generation of dungeons and areas using 3D geometric algorithms.
*   **Time System:** Full calendar cycle (Day/Night, Seasons, Years). Time passes in "ticks" or via specific actions.
*   **Dynamic Weather:** Weather patterns (Rain, Storm, Snow, Clear) flow based on the season and can affect gameplay (e.g., fire damage is weaker in rain).
*   **Reactive Environment:** Rooms act as game objects. Casting "Ice" on a water room freezes it; "Fire" burns webs.
*   **Hazard System:** Rooms can contain hazards (Heat, Poison Gas) that deal DoT unless the player has specific resistances.

### 2. Entities & AI
*   **NPC Schedules:** NPCs have daily routines (Sleep, Work, Eat, Socialize) and physically move between rooms based on the time of day.
*   **Faction & Reputation:** A relationship matrix tracks how factions feel about each other. Player actions (killing friendlies or enemies) dynamically alter reputation, changing NPCs from Neutral to Hostile or Friendly.
*   **Combat AI:** Enemies can flee when low on health, retreat to mana fonts, assist allies (Social Aggro), or use specific spells based on the situation.
*   **Minions:** Players can summon minions that follow them, attack aggressors, and persist across regions.

### 3. Combat & Magic
*   **Grand Elemental System:** 11+ Damage types (Physical, Fire, Ice, Holy, Shadow, etc.) with a rock-paper-scissors relationship logic (e.g., Water douses Fire).
*   **Spell Engine:** Support for Single Target, AoE, HoT (Heal over Time), DoT (Damage over Time), Buffs, Debuffs, and Utility (Unlock, Cleanse).
*   **Status Effects:** Complex tagging system. Effects like "Blind" cap hit chance; "Silence" prevents casting.
*   **Interactions:** Effects interact (e.g., casting "Cleanse" removes tags `poison` and `curse` but leaves `buffs` intact).

### 4. Items & Economy
*   **Procedural Loot:** Diablo-style item generation with Prefixes (e.g., "Sharp", "Fiery") and Suffixes (e.g., "of the Bear", "of Vampirism") that modify stats and add passive effects.
*   **Set Bonuses:** Equipping multiple items from the same named set grants cumulative stat bonuses.
*   **Crafting & Salvaging:** Breakdown items into raw materials (`salvage`) and build new ones using recipes (`craft`) at specific stations (Anvil, Alchemy Table).
*   **Economy:** Vendors have dynamic inventories, buy/sell multipliers, and persistent stock (items you sell stay on the vendor).
*   **Durability:** Weapons and armor degrade on use and require repair.

### 5. Quest System
*   **Dynamic Generation:** NPCs procedurally generate quests based on their interests and the world state (Kill, Fetch, Deliver).
*   **Instance Quests:** Accepting specific quests generates a temporary, instanced dungeon region with a portal entrance.
*   **Quest Board:** A refreshing board of tasks available in major hubs.

---

## 🎮 Controls & UI

*   **Keyboard:** Type commands and press `ENTER`.
    *   `UP/DOWN`: Scroll through command history.
    *   `TAB`: Auto-complete commands.
    *   `PAGE UP/DOWN`: Scroll the text log.
*   **Mouse:**
    *   **Clickable Text:** Click highlighted text (Items, NPCs, Exits) to interact immediately.
    *   **Panels:** Drag and drop UI panels to customize your layout.
    *   **Context Menu:** Right-click objects for a list of actions (Look, Take, Attack).

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

## 🕹️ Gameplay Example

**1. The Setup**
You start in the Town Square. You check your status and gear up.
```text
> status
Name: Adventurer | Class: Warrior | Level: 1
Health: 100/100 | Mana: 50/50
Stats: STR 12, DEX 10, INT 8
Equipped: Worn Sword (Main Hand)

> i
You are carrying:
- 2x Small Healing Potion
- 1x Iron Ration
```

**2. Getting a Quest**
You see a board and an Elder.
```text
> look board
Available Quests:
1. Bounty: Giant Rats (Kill 5) - Reward: 50g
2. Investigation: The Old Cellar (Instance) - Reward: Rare Item

> accept quest 2
You accept the quest. A shimmering portal appears to the North!
Elder Thorne approaches you. "The cellar has been overrun. Please clear it out."
```

**3. The Dungeon**
You enter the procedural instance.
```text
> north
You enter The Old Cellar.
It is very dark here. The air smells of rot.

> cast light
You cast Light! The room brightens.
You see: 2x Giant Rat, 1x Rusty Chest (Locked).

> attack rat
You attack the Giant Rat with your Worn Sword for 8 physical damage.
The Giant Rat bites you for 3 physical damage.
```

**4. Loot and Mechanics**
After the fight, you find loot.
```text
> take all
You pick up a Rat Tail, 2 Gold.

> pick chest
You successfully pick the lock! (Skill: Lockpicking increased to 2)
You open the chest. Inside you see:
- Sharp Iron Dagger of Fire

> look dagger
Sharp Iron Dagger of Fire
Damage: 12 (+2 Fire)
Value: 150g
```

**5. Crafting & Economy**
You return to town to sell junk and salvage gear.
```text
> salvage worn sword
You break down the Worn Sword into: 1x Iron Scrap.

> trade merchant
> sell rat tail
You sell Rat Tail for 2 gold.

> craft
Nearby: Anvil
Recipes:
- Iron Dagger (Requires: 2x Iron Scrap, 1x Leather Scrap) [Locked]
- Iron Sword (Requires: 3x Iron Scrap, 1x Leather Scrap) [Ready]

> craft craft_iron_sword
You hammer the metal violently... (Rolled 45 vs DC 20)
Successfully crafted 1 x Iron Sword! Your Crafting skill increased to 2!

> equip iron sword
(You unequip the Worn Sword)
You equip the Iron Sword in your Main Hand.
```

---

## 📂 Project Structure

The engine is designed to be data-driven. Logic resides in `engine/`, while content resides in `data/`.

```text
├── main.py                 # Entry point
├── engine/
│   ├── config/             # Configuration constants (combat, display, etc.)
│   ├── core/               # Main game loop, input handling, time, weather
│   ├── commands/           # Command parsing and logic handlers
│   ├── items/              # Item classes, Inventory, Loot Generation
│   ├── magic/              # Spells, Effects, and Registry
│   ├── npcs/               # NPC logic, AI, and pathfinding
│   ├── player/             # Player class and persistence logic
│   ├── ui/                 # Pygame rendering, panels, and menus
│   ├── utils/              # Pathfinding (A*), text formatting
│   └── world/              # Room, Region, and Spawner logic
├── data/
│   ├── combat/             # Elemental relationships and flavor text
│   ├── crafting/           # Recipe definitions (*.json)
│   ├── items/              # Item templates (*.json) & Sets
│   ├── magic/              # Spell definitions (*.json)
│   ├── npcs/               # NPC templates (*.json)
│   ├── player/             # Class definitions (Warrior, Mage, etc.)
│   ├── quests/             # Instance quest templates
│   └── regions/            # Region definitions and dynamic themes
└── tests/                  # Unit and integration tests
```

---

## 🛠️ Modding & Adding Content

Because the engine uses JSON for almost all content, you can add new items, monsters, and spells without writing Python code.

### 1. Adding a New Item
Create a file in `data/items/my_items.json`:
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
Create a file in `data/magic/my_spells.json`:
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
Create `data/regions/my_dungeon.json`:
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

## 🧪 Testing

The engine includes a comprehensive suite of unit and batch tests.

```bash
# Run all tests
python -m unittest discover tests

# Run specific batch tests (e.g., Loot System)
python -m unittest tests.batch.test_batch_loot
```

---

## 📄 License

This project is provided as-is for educational and development purposes.

---

## 🗺️ Godot + True MUD Commercialization Roadmap

Goal: evolve this singleplayer simulation-first game into a commercial, server-authoritative multiplayer MUD with Godot client UX.

Execution docs live in `docs/roadmap/`:
- `docs/roadmap/README.md`
- `docs/roadmap/phases/`
- `docs/roadmap/adr/`
- `docs/roadmap/platform-architecture.md`
- `docs/roadmap/steam-packaging-track.md`
- `docs/roadmap/theme-pack-spec-v1.md`

Current content-engine development flow:

- Validate Fantasy Frontier: `python toolkit/content_set_validator.py content_sets/fantasy_frontier`
- Launch Fantasy Frontier directly (the default content set):
  - `python server/launch_content_set.py --transport tcp`
  - `python server/launch_content_set.py --transport ws`

Legacy server-fixture operator flow:
- Refresh fixture: `python toolkit/fixture_refresh.py --source mud-world-editor/data --latest-root content_sets/fantasy_frontier/data --fixture-root tmp/content_fixtures --fixture-name fantasy_editor_migrated_latest`
- Launch from latest selected fixture (auto-reads `tmp/content_fixtures/LATEST_REFRESH.json`):
  - `python server/launch_from_latest_fixture.py --transport tcp`
  - `python server/launch_from_latest_fixture.py --transport ws`
- Operator reference: `docs/roadmap/server-operator-guide.md`

### Guiding Product/Tech Decisions
* Keep simulation logic authoritative on the server.
* Treat the Godot client as a view/controller layer over networked game state.
* Preserve data-driven content pipelines (`data/*.json`) as long as possible to reduce rewrite risk.
* Use existing tests as migration safety rails before replacing systems.

### Current State (What Helps Us)
* Strong domain coverage in tests (`tests/` includes combat, world, AI, economy, quests, persistence).
* Clean command dispatch layer (`engine/commands/command_system.py`) that can become protocol-facing handlers.
* Central world lifecycle (`engine/world/world.py`) and persistence (`engine/world/save_manager.py`) already exist.
* Data definitions are externalized in JSON, which is migration-friendly.

### Phase 0: Product and Architecture Baseline (2-4 weeks)
Deliverables:
* Define commercial target: buy-to-play vs F2P, session model, expected CCU, and platform targets.
* Define networking authority model and anti-cheat stance.
* Write a canonical architecture decision record (ADR) for:
  * Server runtime choice (`Python headless` first, or full GDScript/C# port later).
  * Protocol format (JSON over WebSocket first, versioned messages).
  * Account/auth boundary (guest/local dev now, real auth later).
* Establish KPIs: tick time budget, command latency, reconnect success, crash-free session rate.

Exit gate:
* Signed-off architecture + business constraints + scope for first paid launch.

### Phase 1: Extract Headless Authoritative Server Core (4-8 weeks)
Deliverables:
* Separate simulation engine from Pygame-specific rendering/input concerns.
* Introduce server loop that owns:
  * world updates
  * command processing
  * save/load
  * AI ticks
* Introduce a network session model:
  * `player_id`, connection state, command queue, outbound event stream.
* Add protocol boundary adapters around command input/output.
* Keep existing content files and mechanics unchanged where possible.

Recommended first implementation:
* Keep server in Python to minimize rewrite risk.
* Build thin Godot client that connects and renders text/UI events.

Exit gate:
* Multiple remote clients can connect, issue commands, and observe shared world state.

### Phase 2: Godot Client Foundation (4-6 weeks)
Deliverables:
* Godot project with:
  * login/character select flow
  * command input + history/autocomplete
  * text/event feed
  * panelized UI (inventory, map, quests, status)
* Network client with reconnect and session resume handling.
* Message schema versioning support in client.
* Minimal accessibility baseline (font scaling, color contrast presets, keybind config).

Exit gate:
* Playable vertical slice in Godot client with parity for core text loop (move/look/combat/inventory/save).

### Phase 3: Multiplayer Semantics and Live Ops Core (6-10 weeks)
Deliverables:
* Shared-world rules:
  * room occupancy
  * visibility/broadcast scoping
  * interaction contention rules
* Persistence model upgrades:
  * account-level data
  * character slots
  * migration/version handling for saves
* Operational services:
  * structured logs
  * metrics
  * admin commands
  * crash recovery and backup restore drills
* Abuse/security baseline:
  * input validation
  * rate limits
  * moderation hooks

Exit gate:
* Closed alpha with stable multi-user sessions and durable progression.

### Phase 4: Content Pipeline and Tooling for Scale (ongoing)
Deliverables:
* Content schema validation and CI checks for `data/`.
* World/content editor integration path (`mud-world-editor`) with export contracts.
* Regression harness for command transcripts and deterministic combat/world snapshots.
* Authoring docs for designers (items/spells/regions/quests conventions).

Exit gate:
* New content can be added by non-engineers with low defect rates.

### Phase 5: Commercial Readiness (8-12 weeks)
Deliverables:
* Platform and legal readiness:
  * Terms/Privacy
  * account deletion/export policy
  * telemetry disclosures
* Commerce stack:
  * entitlement checks
  * billing integration
  * fraud and chargeback handling policy
* Launch operations:
  * patching and rollback strategy
  * support workflows
  * incident runbooks and on-call rotation
* QA:
  * load testing
  * soak testing
  * compatibility matrix

Exit gate:
* Release candidate passes technical, operational, and legal go-live checklist.

### Migration Risks to Manage Early
* Tight coupling between loop/UI/simulation in current `GameManager`.
* Tick-rate and deterministic behavior drift once network latency is introduced.
* Save format evolution (`save_format_version`) under live-service constraints.
* Tooling debt for validating JSON content at scale.

### Suggested First Milestone in This Repo
1. Create `/docs/roadmap/` with ADRs and milestone checklists.
2. Add a `server_mode` entry point that runs headless without Pygame rendering.
3. Add a simple socket/WebSocket adapter that forwards commands into `CommandProcessor`.
4. Add an integration test: two simulated clients, one shared world, verified state/events.
```
