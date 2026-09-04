# engine/commands/interaction/environment.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET
from engine.items.interactive import Interactive
from engine.items.container import Container # Needed for casting
from engine.items.lockpick import Lockpick

@command("pull", ["push", "interact", "flip"], "interaction", "Interact with an object (lever, button, etc).\nUsage: pull <object>")
def interact_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not args: return f"{FORMAT_ERROR}Interact with what?{FORMAT_RESET}"
    
    target_name = " ".join(args).lower()
    target = world.find_item_in_room_for_player(target_name, player)
    
    if not target: return f"{FORMAT_ERROR}You don't see '{target_name}' here.{FORMAT_RESET}"
    
    if isinstance(target, Interactive):
        return target.interact(player, world)
    else:
        return f"{FORMAT_ERROR}Nothing happens when you interact with the {target.name}.{FORMAT_RESET}"

@command("pick", [], "interaction", "Pick a lock on a door or container.\nUsage: pick <direction> | pick <container>")
def pick_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not args: return f"{FORMAT_ERROR}Pick what? Usage: pick <direction> or pick <container>{FORMAT_RESET}"
    
    target_str = args[0].lower()
    
    # 1. Check Directions
    if target_str in ["north", "south", "east", "west", "up", "down", "n", "s", "e", "w", "u", "d"]:
        # Expand alias
        from engine.commands.command_system import direction_aliases
        if target_str in direction_aliases: target_str = direction_aliases[target_str]
        
        return world.attempt_pick_lock_direction(target_str, player=player)
        
    # 2. Check Containers
    target_name = " ".join(args).lower()
    container = world.find_item_in_room_for_player(target_name, player)
    
    # Check inventory for lockpick item class usage flow
    # Ideally, we find a lockpick in inv and call use() on it targeting the container.
    pick_tool = None
    for slot in player.inventory.slots:
        if isinstance(slot.item, Lockpick):
            pick_tool = slot.item
            break
            
    if not pick_tool: return f"{FORMAT_ERROR}You don't have a lockpick.{FORMAT_RESET}"
    
    if container:
        return pick_tool.use(player, container)
    
    return f"{FORMAT_ERROR}You see nothing to pick there.{FORMAT_RESET}"
