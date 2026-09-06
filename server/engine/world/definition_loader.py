# engine/world/definition_loader.py
"""
Handles loading all game definitions from JSON files and initializing a new world state.
"""
import json
import os
import time
import uuid
from typing import TYPE_CHECKING

from engine.config import FORMAT_ERROR, FORMAT_RESET, PLAYER_DEFAULT_NAME
from engine.items.item_factory import ItemFactory
from engine.magic.spell_registry import load_spells_from_json
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import initialize_npc_schedules
from engine.player import Player
from engine.world.region import Region
from engine.utils.logger import Logger

if TYPE_CHECKING:
    from engine.world.world import World


def load_all_definitions(world: 'World'):
    """Populates the world's template dictionaries by loading from disk."""
    resolved_content_root = world.content_root
    Logger.info("Loader", "Loading definitions...")
    if world.has_capability("magic"):
        spell_stats = load_spells_from_json(resolved_content_root)
        spell_stats["enabled"] = True
    else:
        spell_stats = {
            "enabled": False,
            "files_loaded": 0,
            "spells_loaded": 0,
            "overwrites": 0,
            "file_errors": 0,
            "dir_missing": 0,
        }
    item_stats = _load_item_templates(world, resolved_content_root)
    npc_stats = _load_npc_templates(world, resolved_content_root)
    world.definition_load_stats = {
        "spell_registry": spell_stats,
        "item_templates": item_stats,
        "npc_templates": npc_stats,
    }
    if world.quest_manager:
        world.quest_manager._load_npc_interests()
    _load_regions(world, resolved_content_root)
    Logger.info("Loader", "Definitions loaded.")

def _load_item_templates(world: 'World', content_root: str) -> dict[str, int]:
    world.item_templates = {}
    stats = {
        "files_loaded": 0,
        "metadata_files_skipped": 0,
        "duplicate_ids": 0,
        "invalid_missing_required": 0,
        "file_errors": 0,
        "dir_missing": 0,
    }
    item_template_dir = os.path.join(content_root, "items")
    if not os.path.isdir(item_template_dir):
        stats["dir_missing"] = 1
        Logger.warning("Loader", f"Item template directory not found: {item_template_dir}")
        return stats
    for filename in os.listdir(item_template_dir):
        if filename.endswith(".json"):
            # Item-set and procedural-affix definitions are deliberately kept
            # beside item data, but are consumed by SetManager / affix_data's
            # configure_item_affixes() rather than ItemFactory.
            if filename in ("sets.json", "affixes.json"):
                stats["metadata_files_skipped"] += 1
                continue
            path = os.path.join(item_template_dir, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    stats["files_loaded"] += 1
                    for item_id, template_data in data.items():
                        if item_id in world.item_templates:
                            stats["duplicate_ids"] += 1
                        if "name" not in template_data or "type" not in template_data:
                            stats["invalid_missing_required"] += 1
                            continue
                        world.item_templates[item_id] = template_data
            except Exception as e:
                stats["file_errors"] += 1
                Logger.error("Loader", f"Error loading item templates from {path}: {e}")
    if stats["duplicate_ids"] > 0:
        Logger.warning("Loader", f"Item templates: detected {stats['duplicate_ids']} duplicate ID collision(s).")
    if stats["invalid_missing_required"] > 0:
        Logger.warning(
            "Loader",
            f"Item templates: skipped {stats['invalid_missing_required']} template(s) missing required fields ('name' or 'type').",
        )
    return stats

def _load_npc_templates(world: 'World', content_root: str) -> dict[str, int]:
    world.npc_templates = {}
    stats = {
        "files_loaded": 0,
        "duplicate_ids": 0,
        "invalid_missing_name": 0,
        "file_errors": 0,
        "dir_missing": 0,
    }
    npc_template_dir = os.path.join(content_root, "npcs")
    if not os.path.isdir(npc_template_dir):
        stats["dir_missing"] = 1
        Logger.warning("Loader", f"NPC template directory not found: {npc_template_dir}")
        return stats
    for filename in os.listdir(npc_template_dir):
        if filename.endswith(".json"):
            path = os.path.join(npc_template_dir, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    stats["files_loaded"] += 1
                    for template_id, template_data in data.items():
                        if template_id in world.npc_templates:
                            stats["duplicate_ids"] += 1
                        if "name" not in template_data:
                            stats["invalid_missing_name"] += 1
                            continue
                        world.npc_templates[template_id] = template_data
            except Exception as e:
                stats["file_errors"] += 1
                Logger.error("Loader", f"Error loading NPC templates from {path}: {e}")
    if stats["duplicate_ids"] > 0:
        Logger.warning("Loader", f"NPC templates: detected {stats['duplicate_ids']} duplicate ID collision(s).")
    if stats["invalid_missing_name"] > 0:
        Logger.warning(
            "Loader",
            f"NPC templates: skipped {stats['invalid_missing_name']} template(s) missing required field ('name').",
        )
    Logger.info("Loader", f"[NPC Templates] Loaded {len(world.npc_templates)} NPC templates.")
    return stats

def _load_regions(world: 'World', content_root: str):
    world.regions = {}
    region_dir = os.path.join(content_root, "regions")
    if not os.path.isdir(region_dir):
        Logger.warning("Loader", f"Region directory not found: {region_dir}")
        return
    for filename in os.listdir(region_dir):
        if filename.endswith(".json"):
            path = os.path.join(region_dir, filename)
            try:
                with open(path, 'r') as f:
                    region_data = json.load(f)
                    region_id = filename[:-5]
                    region_data['obj_id'] = region_id
                    region = Region.from_dict(region_data)
                    world.add_region(region_id, region)
            except Exception as e:
                Logger.error("Loader", f"Error loading region from {path}: {e}")

def grant_starting_inventory(world: 'World', player: Player, entries: object = None) -> None:
    """Grant explicit bootstrap inventory from the selected content package."""
    raw_entries = world.initial_inventory() if entries is None else entries
    if not isinstance(raw_entries, list):
        return
    for entry in raw_entries:
        if isinstance(entry, str):
            item_id, quantity = entry.strip(), 1
        elif isinstance(entry, dict):
            item_id = str(entry.get("item_id", "")).strip()
            quantity = max(1, int(entry.get("quantity", 1)))
        else:
            continue
        if item_id == "":
            continue
        if item_id not in world.item_templates:
            Logger.warning("Loader", f"Starter item template '{item_id}' is missing for this data root. Skipping.")
            continue
        item = ItemFactory.create_item_from_template(item_id, world)
        if item:
            player.inventory.add_item(item, quantity)


def initialize_new_world(world: 'World', start_region: str, start_room: str):
    Logger.info("Loader", "Initializing new world state...")
    skip_initial_player = bool(getattr(world, "skip_initial_player", False))
    world.bootstrap_start_region = start_region
    world.bootstrap_start_room = start_room
    world.player = None
    initial_player = None
    if not skip_initial_player:
        initial_player = Player(PLAYER_DEFAULT_NAME, world=world)
        initial_player.world = world
        world.initialize_content_player(initial_player)
        world.player = initial_player
    if initial_player is not None:
        grant_starting_inventory(world, initial_player, getattr(world, "bootstrap_starter_items", None))

    if initial_player is not None:
        initial_player.current_region_id = start_region
        initial_player.current_room_id = start_room
        initial_player.respawn_region_id = start_region
        initial_player.respawn_room_id = start_room

    world.npcs = {}
    world.respawn_manager.respawn_queue = []
    
    npcs_created_count = 0
    for region_id, region in world.regions.items():
        for room_id, room in region.rooms.items():
            room.items = [] # Clear items from previous sessions
            
            for item_ref in getattr(room, 'initial_item_refs', []):
                if item_ref and "item_id" in item_ref:
                    item = ItemFactory.create_item_from_template(item_ref["item_id"], world, **item_ref.get("properties_override", {}))
                    if item:
                        room.add_item(item)
            for npc_ref in getattr(room, 'initial_npc_refs', []):
                instance_id = npc_ref.get("instance_id", f"{npc_ref.get('template_id')}_{uuid.uuid4().hex[:8]}")
                if npc_ref.get("template_id") and instance_id not in world.npcs:
                    overrides = {"current_region_id": region_id, "current_room_id": room_id, "home_region_id": region_id, "home_room_id": room_id}
                    npc = NPCFactory.create_npc_from_template(npc_ref.get("template_id"), world, instance_id, **overrides)
                    if npc:
                        world.add_npc(npc)
                        npcs_created_count += 1

    if npcs_created_count == 0:
        Logger.warning("Loader", "No initial NPCs were spawned. The world may feel empty.")

    initialize_npc_schedules(world)

    # Newly loaded populations otherwise all have ``last_moved == 0`` and
    # immediately attempt movement together on the first simulation tick.
    # Begin their normal cooldown now so a new arrival can read its opening
    # before the world starts producing ambient movement narration.
    initial_movement_time = time.time()
    for npc in world.npcs.values():
        # Spread first moves across each NPC's normal cooldown instead of
        # releasing the whole bootstrap population on the same tick. The
        # stable instance-id phase is deterministic and consumes no gameplay
        # randomness.
        cooldown = max(0.0, float(getattr(npc, "move_cooldown", 0.0)))
        phase = (sum(ord(char) for char in str(getattr(npc, "obj_id", ""))) % 1000) / 1000.0
        npc.last_moved = initial_movement_time + (phase * cooldown)

    # initialize quest board
    world.quest_board = []
    if world.quest_manager:
        world.quest_manager.ensure_initial_quests(initial_player)
    
    if world.player is None:
        Logger.info("Loader", f"New world initialized. Character creation required at {start_region}:{start_room}")
    else:
        Logger.info("Loader", f"New world initialized. Player at {start_region}:{start_room}")
