# engine/commands/gathering.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET
from engine.items.resource_node import ResourceNode

@command("gather", ["mine", "harvest", "chop"], "interaction", "Gather resources from a node.\nUsage: gather <target>", content_capability="gathering")
def gather_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not args: return f"{FORMAT_ERROR}Gather from what?{FORMAT_RESET}"
    
    target_name = " ".join(args).lower()
    target = world.find_item_in_room_for_player(target_name, player)
    
    if not target: return f"{FORMAT_ERROR}You don't see '{target_name}' here.{FORMAT_RESET}"
    
    if isinstance(target, ResourceNode):
        return target.gather(player, world)
    else:
        return f"{FORMAT_ERROR}You cannot gather from {target.name}.{FORMAT_RESET}"
