# engine/commands/interaction/containers.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE, PUT_COMMAND_PREPOSITION
from engine.items.container import Container

@command("open", [], "interaction", "Open a container.\nUsage: open <container_name>")
def open_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}Open what?{FORMAT_RESET}"
    
    name = " ".join(args).lower()
    
    target = world.find_item_in_room_for_player(name, player)
    if not target: target = player.inventory.find_item_by_name(name)
    
    if not target: return f"{FORMAT_ERROR}You don't see '{name}' here.{FORMAT_RESET}"
    if not isinstance(target, Container): return f"{FORMAT_ERROR}The {target.name} is not a container.{FORMAT_RESET}"
    
    return f"{FORMAT_HIGHLIGHT}{target.open()}{FORMAT_RESET}"

@command("close", [], "interaction", "Close a container.\nUsage: close <container_name>")
def close_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}Close what?{FORMAT_RESET}"
    
    name = " ".join(args).lower()
    target = world.find_item_in_room_for_player(name, player)
    if not target: target = player.inventory.find_item_by_name(name)
    
    if not target: return f"{FORMAT_ERROR}You don't see '{name}' here.{FORMAT_RESET}"
    if not isinstance(target, Container): return f"{FORMAT_ERROR}Not a container.{FORMAT_RESET}"
    
    return f"{FORMAT_HIGHLIGHT}{target.close()}{FORMAT_RESET}"

@command("put", ["store"], "interaction", "Put an item into a container.\nUsage: put <item> in <container>")
def put_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"
    
    if PUT_COMMAND_PREPOSITION not in [a.lower() for a in args]:
        return f"{FORMAT_ERROR}Usage: put <item> {PUT_COMMAND_PREPOSITION} <container>{FORMAT_RESET}"
    
    try:
        idx = [a.lower() for a in args].index(PUT_COMMAND_PREPOSITION)
        item_name = " ".join(args[:idx]).lower()
        cont_name = " ".join(args[idx+1:]).lower()
    except (ValueError, AttributeError): return f"{FORMAT_ERROR}Parse error.{FORMAT_RESET}"

    item = player.inventory.find_item_by_name(item_name)
    if not item: return f"{FORMAT_ERROR}You don't have '{item_name}'.{FORMAT_RESET}"

    container = world.find_item_in_room_for_player(cont_name, player)
    if not container or not isinstance(container, Container):
        # Check inventory
        container = player.inventory.find_item_by_name(cont_name)
        if not container or not isinstance(container, Container):
            return f"{FORMAT_ERROR}You don't see a container '{cont_name}'.{FORMAT_RESET}"

    # Recursion Check
    if item is container: return f"{FORMAT_ERROR}Cannot put item inside itself.{FORMAT_RESET}"
    
    if isinstance(item, Container):
        # Simple recursive check
        def check(c):
            for i in c.properties.get("contains", []):
                if i is container: return True
                if isinstance(i, Container) and check(i): return True
            return False
        if check(item): return f"{FORMAT_ERROR}The {container.name} is already inside the {item.name}!{FORMAT_RESET}"

    can_add, msg = container.can_add(item)
    if not can_add: return f"{FORMAT_ERROR}{msg}{FORMAT_RESET}"

    rem_item, _, _ = player.inventory.remove_item(item.obj_id, 1)
    if rem_item:
        if container.add_item(rem_item):
            return f"{FORMAT_SUCCESS}You put the {rem_item.name} in the {container.name}.{FORMAT_RESET}"
        else:
            player.inventory.add_item(rem_item)
            return f"{FORMAT_ERROR}Failed to add item.{FORMAT_RESET}"
    return f"{FORMAT_ERROR}Failed to remove item from inventory.{FORMAT_RESET}"
