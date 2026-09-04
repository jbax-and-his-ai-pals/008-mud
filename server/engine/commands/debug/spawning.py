# engine/commands/debug/spawning.py
import random
from typing import Optional, Dict
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET, FORMAT_HIGHLIGHT
from engine.items.item_factory import ITEM_CLASS_MAP, ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.utils.utils import format_name_for_display, get_article, simple_plural

@command("spawn", ["create"], "debug", "Spawn entities.\nUsage: spawn <name> [count] [level]")
def spawn_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not args:
        return f"{FORMAT_ERROR}Usage: spawn <item/npc_name> [count] [level]{FORMAT_RESET}"

    def _resolve_item_id(user_input: str) -> Optional[str]:
        user_input_lower = user_input.lower()
        if user_input_lower in world.item_templates: return user_input_lower
        for prefix in ["item_", "scroll_"]:
            pid = f"{prefix}{user_input_lower}"
            if pid in world.item_templates: return pid
        return None

    def _spawn_item(item_id: str, quantity: int) -> str:
        if not player or not player.current_region_id or not player.current_room_id:
            return f"{FORMAT_ERROR}Player location unavailable.{FORMAT_RESET}"
        resolved_id = _resolve_item_id(item_id)
        if not resolved_id: return f"{FORMAT_ERROR}Item template '{item_id}' not found.{FORMAT_RESET}"
        
        items = []
        for _ in range(quantity):
            inst = ItemFactory.create_item_from_template(resolved_id, world)
            if inst: 
                world.add_item_to_room(player.current_region_id, player.current_room_id, inst)
                items.append(inst)
        
        if not items: return f"{FORMAT_ERROR}Failed to spawn items.{FORMAT_RESET}"
        
        names = {}
        for i in items: names[i.name] = names.get(i.name, 0) + 1
        parts = []
        for name, count in names.items():
            parts.append(f"{count} {simple_plural(name)}" if count > 1 else f"{get_article(name)} {name}")
        return f"{FORMAT_SUCCESS}Spawned {', '.join(parts)}.{FORMAT_RESET}"

    def _spawn_npc(template_id: str, count: int, level: Optional[int]) -> str:
        if not player or not player.current_region_id or not player.current_room_id:
            return f"{FORMAT_ERROR}Player location unavailable.{FORMAT_RESET}"
        names = []
        for _ in range(count):
            overrides = {"current_region_id": player.current_region_id, "current_room_id": player.current_room_id}
            if level: overrides["level"] = level
            npc = NPCFactory.create_npc_from_template(template_id, world, **overrides)
            if npc:
                world.add_npc(npc)
                names.append(npc.name)
            else: return f"{FORMAT_ERROR}Failed to create NPC '{template_id}'.{FORMAT_RESET}"
            
        if len(names) == 1:
            return f"{format_name_for_display(player, world.get_npc(list(world.npcs.keys())[-1]), start_of_sentence=True)} appears!{FORMAT_RESET}"
        return f"{FORMAT_SUCCESS}Spawned {count} {simple_plural(names[0])}.{FORMAT_RESET}"

    if args[0].lower() == 'npc':
        if len(args) < 2: return "Usage: spawn npc <id> [count] [level]"
        return _spawn_npc(args[1], int(args[2]) if len(args)>2 else 1, int(args[3]) if len(args)>3 else None)

    # Smart Match
    parts = list(args)
    val1 = None; val2 = None
    if parts[-1].isdigit():
        val1 = int(parts.pop())
        if parts and parts[-1].isdigit():
             val2 = val1; val1 = int(parts.pop())
    
    name = " ".join(parts)
    
    # Try Item
    if _resolve_item_id(name):
        return _spawn_item(name, val1 if val1 else 1)
        
    # Try NPC
    if name.lower() in world.npc_templates:
        return _spawn_npc(name.lower(), val1 if val1 else 1, val2)

    return f"{FORMAT_ERROR}No match for '{name}'.{FORMAT_RESET}"

@command("debuggear", ["dbggear"], "debug", "Toggle debug gear.\nUsage: debuggear <on|off>")
def debuggear_command_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player or not args: return f"{FORMAT_ERROR}Usage: debuggear <on|off>{FORMAT_RESET}"
    
    action = args[0].lower()
    ids = ["debug_sword", "debug_shield", "debug_armor", "debug_helmet", "debug_gauntlets", "debug_boots", "debug_amulet"]
    msgs = []
    
    if action == "on":
        equipped_ids = {i.obj_id for i in player.equipment.values() if i}
        for iid in ids:
            if iid in equipped_ids or player.inventory.find_item_by_id(iid): continue
            item = ItemFactory.create_item_from_template(iid, world)
            if item:
                player.inventory.add_item(item)
                player.equip_item(item)
                msgs.append(f"Equipped {item.name}")
        return "\n".join(msgs) or "Gear already present."
    else:
        for iid in ids:
            player.inventory.remove_item(iid, 999)
            for s, i in list(player.equipment.items()):
                if i and i.obj_id == iid: player.unequip_item(s)
        return "Debug gear removed."
