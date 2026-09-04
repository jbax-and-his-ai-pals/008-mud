# engine/core/quest_generation/objectives.py
import random
import uuid
from typing import Dict, Any, Optional

from engine.utils.utils import simple_plural

def generate_kill_objective(world, player_level, giver_npc, config) -> Optional[Dict[str, Any]]:
    level_range = config.get("quest_level_range_player", 3)
    min_lvl, max_lvl = max(1, player_level - level_range), player_level + level_range
    valid_targets = [tid for tid, t in world.npc_templates.items() if t.get("faction") == "hostile" and min_lvl <= t.get("level", 1) <= max_lvl]
    if not valid_targets: return None
    selected_tid = random.choice(valid_targets)
    target_template = world.npc_templates[selected_tid]
    giver_region = world.get_region(giver_npc.current_region_id) if giver_npc.current_region_id else None
    location_hint = f"the area around {giver_region.name}" if giver_region else "nearby regions"
    qty = max(1, int(config.get("kill_quest_quantity_base", 3) + (player_level * config.get("kill_quest_quantity_per_level", 0.5))))
    return {
        "type": "kill",
        "target_template_id": selected_tid,
        "target_name_plural": simple_plural(target_template.get("name", selected_tid)),
        "required_quantity": qty, "current_quantity": 0, "location_hint": location_hint,
        "difficulty_level": target_template.get("level", 1)
    }

def generate_fetch_objective(world, player_level, giver_npc, config) -> Optional[Dict[str, Any]]:
    level_range = config.get("quest_level_range_player", 3)
    min_mob_lvl, max_mob_lvl = max(1, player_level - level_range), player_level + level_range
    valid_options = []
    for item_id, item_template in world.item_templates.items():
        if item_template.get("type") == "Key": continue
        for mob_tid, mob_template in world.npc_templates.items():
            if mob_template.get("faction") == "hostile" and min_mob_lvl <= mob_template.get("level", 1) <= max_mob_lvl:
                if item_id in mob_template.get("loot_table", {}):
                        valid_options.append((item_id, mob_tid))
    if not valid_options: return None
    item_id, source_mob_tid = random.choice(valid_options)
    item_template = world.item_templates[item_id]
    source_mob_template = world.npc_templates[source_mob_tid]
    qty = max(1, int(config.get("fetch_quest_quantity_base", 5) + (player_level * config.get("fetch_quest_quantity_per_level", 1))))
    return {
        "type": "fetch",
        "item_id": item_id, "item_name": item_template.get("name", item_id),
        "item_name_plural": simple_plural(item_template.get("name", item_id)),
        "required_quantity": qty, "current_quantity": 0,
        "source_enemy_name_plural": simple_plural(source_mob_template.get("name", source_mob_tid)),
        "location_hint": "nearby areas", "difficulty_level": item_template.get("value", 1) * qty
    }

def generate_deliver_objective(world, player_level, giver_npc, config) -> Optional[Dict[str, Any]]:
    recipients = [npc for npc in world.npcs.values() if npc.is_alive and npc.faction != "hostile" and npc.obj_id != giver_npc.obj_id]
    if not recipients: return None
    recipient_npc = random.choice(recipients)
    package_template = world.item_templates.get("quest_package_generic")
    if not package_template: return None
    
    item_name = package_template.get("name", "Package")
    item_desc = f"A package for {recipient_npc.name} from {giver_npc.name}."
    region_name = world.regions[recipient_npc.current_region_id].name if recipient_npc.current_region_id else "Unknown"
    return {
        "type": "deliver",
        "item_template_id": "quest_package_generic",
        "item_instance_id": f"delivery_{uuid.uuid4().hex[:4]}",
        "item_to_deliver_name": item_name, "item_to_deliver_description": item_desc,
        "recipient_instance_id": recipient_npc.obj_id, "recipient_name": recipient_npc.name,
        "recipient_location_description": f"{region_name}", "difficulty_level": 5
    }
