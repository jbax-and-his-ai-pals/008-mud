# engine/commands/interaction/observation.py
from typing import Any, List
from engine.commands.command_system import command, registered_commands
from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_TITLE, QUEST_BOARD_ALIASES
from engine.items.container import Container
from engine.items.item import Item
from engine.npcs.npc import NPC

@command("look", ["l"], "interaction", "Look around or examine something.\nUsage: look [target]")
def look_handler(args: List[str], context: Any):
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not args: return world.look(minimal=True, player=player)

    args_lower = [a.lower() for a in args]
    target_name = ""
    look_inside = False

    if "in" in args_lower:
        idx = args_lower.index("in")
        if idx + 1 < len(args): 
            target_name = " ".join(args[idx+1:]).lower()
            look_inside = True
        else: return f"{FORMAT_ERROR}Look in what?{FORMAT_RESET}"
    elif "inside" in args_lower:
        idx = args_lower.index("inside")
        if idx + 1 < len(args): 
            target_name = " ".join(args[idx+1:]).lower()
            look_inside = True
        else: return f"{FORMAT_ERROR}Look inside what?{FORMAT_RESET}"
    elif "at" in args_lower:
        idx = args_lower.index("at")
        if idx + 1 < len(args): 
            target_name = " ".join(args[idx+1:]).lower()
        else: return f"{FORMAT_ERROR}Look at what?{FORMAT_RESET}"
    else: 
        target_name = " ".join(args).lower()

    if look_inside and target_name in ["inventory", "my inventory", "bag", "backpack"]:
        from engine.commands.inventory import inventory_handler
        return inventory_handler([], context)

    if not look_inside and target_name in QUEST_BOARD_ALIASES:
        # Check if the look board command is registered and delegate
        board_look_command = registered_commands.get("look board")
        if board_look_command and 'handler' in board_look_command: 
            return board_look_command['handler']([], context)
        # Fallback if board command isn't loaded for some reason
        quest_manager = world.quest_manager
        if not quest_manager:
             return f"{FORMAT_ERROR}The quest system seems to be unavailable.{FORMAT_RESET}"

    # Search Priority: Player -> NPC -> Room Item -> Inventory -> Equipment
    target = None
    for p in world.players.values():
        if p != player and p.current_region_id == player.current_region_id and p.current_room_id == player.current_room_id:
            if target_name in p.name.lower():
                target = p
                break
                
    if not target: target = world.find_npc_in_room_for_player(target_name, player)
    if not target: target = world.find_item_in_room_for_player(target_name, player)
    if not target: target = player.inventory.find_item_by_name(target_name)
    if not target:
        for slot, item in player.equipment.items():
            if item and (target_name == item.name.lower() or target_name in item.name.lower()): 
                target = item
                break

    if not target: return f"{FORMAT_ERROR}You don't see '{target_name}' here.{FORMAT_RESET}"

    if look_inside:
        if isinstance(target, Container):
            if target.properties.get("is_open", False): 
                return f"{FORMAT_TITLE}Inside the {target.name}:{FORMAT_RESET}\n{target.list_contents()}"
            else: 
                return f"The {target.name} is {'locked' if target.properties.get('locked', False) else 'closed'}."
        else: return f"{FORMAT_ERROR}That is not a container.{FORMAT_RESET}"
    else:
        from engine.player.core import Player
        if isinstance(target, NPC): return target.get_description()
        elif isinstance(target, Player):
            desc = f"{FORMAT_TITLE}{target.name}{FORMAT_RESET}\n{target.description}\n"
            desc += f"They look like a level {target.runtime_state.progression.level} {target.runtime_state.progression.player_class}.\n"
            health_pct = (target.health / target.max_health) * 100 if target.max_health > 0 else 0
            if health_pct > 80: desc += "They appear to be in excellent health."
            elif health_pct > 50: desc += "They look a bit banged up."
            elif health_pct > 20: desc += "They are badly wounded."
            else: desc += "They are barely clinging to life."
            return desc
        elif isinstance(target, Item): return target.examine()
        
    return f"You see {target.name}."

@command("examine", ["x", "exam"], "interaction", "Examine something.\nUsage: examine <target>")
def examine_handler(args, context):
    player = context.get("player")
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}What do you want to examine?{FORMAT_RESET}"
    return look_handler(args, context)

@command("read", category="interaction", help_text="Read something, like a book, scroll, or sign.\nUsage: read <object>")
def read_handler(args, context):
    if not args: return f"{FORMAT_ERROR}What do you want to read?{FORMAT_RESET}"
    return look_handler(args, context)
