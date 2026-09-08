# engine/commands/interaction/pickup_drop.py
from typing import List, Dict, Any
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET, FORMAT_HIGHLIGHT, GET_COMMAND_PREPOSITION
from engine.items.container import Container
from engine.items.item_factory import ItemFactory
from engine.utils.utils import get_article, simple_plural

def _handle_item_acquisition(args: List[str], context: Dict[str, Any], command_verb: str) -> str:
    world = context["world"]
    player = context.get('player')
    server = getattr(world, "server", None)
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}{command_verb.capitalize()} what?{FORMAT_RESET}"

    item_name = ""
    qty = 1
    take_all = False
    
    if args[0].lower() == "all":
        take_all = True
        qty = None
        if len(args) > 1: item_name = " ".join(args[1:]).lower()
    elif args[0].isdigit():
        qty = int(args[0])
        item_name = " ".join(args[1:]).lower()
    else:
        item_name = " ".join(args).lower()

    candidates = []
    # Room items
    room_items = world.get_items_in_room(player.current_region_id, player.current_room_id)
    for item in room_items:
        candidates.append((item, None))
    # Open containers in room
    for item in room_items:
        if isinstance(item, Container) and item.properties.get("is_open"):
            for sub in item.properties.get("contains", []):
                candidates.append((sub, item))

    if not candidates: return f"{FORMAT_ERROR}Nothing here to {command_verb}.{FORMAT_RESET}"

    targets = []
    if take_all and not item_name:
        # Take everything from floor
        targets = [c for c in candidates if c[1] is None]
        if not targets: return f"{FORMAT_ERROR}Nothing on the floor.{FORMAT_RESET}"
    else:
        # Match name
        matches = []
        for item, source in candidates:
            if item_name == item.name.lower(): matches.append((item, source))
            elif item_name in item.name.lower(): matches.append((item, source))
        
        if not matches: return f"{FORMAT_ERROR}You don't see '{item_name}'.{FORMAT_RESET}"
        
        # Priority: Exact match
        exact = [m for m in matches if m[0].name.lower() == item_name]
        targets = exact if exact else matches
        
        if not take_all:
            targets = targets[:qty] if qty else [targets[0]]

    taken_log = {}
    err_msg = ""
    hints = []

    for item, source in targets:
        if not item.get_property("can_take", True):
             err_msg = f" (The {item.name} is fixed in place)."
             continue
             
        can, msg = player.inventory.can_add_item(item)
        if not can:
             err_msg = " (You cannot carry any more)."
             break
        
        success = False
        if source: success = source.remove_item(item)
        else: success = world.remove_item_instance_from_room(player.current_region_id, player.current_room_id, item)
        
        if success:
             recipient = player
             route_note = ""
             if server is not None and hasattr(server, "distribute_party_loot"):
                  recipient, route_note = server.distribute_party_loot(player, item)
             recipient.inventory.add_item(item)
             # Collection Logic
             hint = context["game"].collection_manager.handle_collection_discovery(recipient, item)
             if hint: hints.append(hint)
             discovery_manager = getattr(context["game"], "discovery_manager", None)
             if discovery_manager:
                  hint = discovery_manager.handle_item_discovery(recipient, item)
                  if hint: hints.append(hint)
             if route_note:
                  hints.append(route_note)
             
             src_key = source.name if source else "__ground__"
             if src_key not in taken_log: taken_log[src_key] = []
             display_name = item.name if recipient is player else f"{item.name} -> {recipient.name}"
             taken_log[src_key].append(display_name)

    if not taken_log: return f"{FORMAT_ERROR}Couldn't take anything.{err_msg}{FORMAT_RESET}"

    msgs = []
    for src, names in taken_log.items():
        count_map = {}
        for n in names: count_map[n] = count_map.get(n, 0) + 1
        parts = []
        for n, c in count_map.items():
            parts.append(f"{c} {simple_plural(n)}" if c > 1 else f"{get_article(n)} {n}")
        
        item_str = ", ".join(parts)
        if src == "__ground__": msgs.append(f"You pick up {item_str}.")
        else: msgs.append(f"You get {item_str} from the {src}.")
        
    return f"{FORMAT_SUCCESS}{' '.join(msgs)}{FORMAT_RESET}{err_msg}\n" + "\n".join(set(hints))

def _handle_item_disposal(args: List[str], context: Dict[str, Any], command_verb: str) -> str:
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You can't {command_verb} items while dead.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}{command_verb.capitalize()} what?{FORMAT_RESET}"

    item_name = ""
    quantity_requested = 1
    drop_all_of_type = False
    
    if args[0].lower() == "all":
        drop_all_of_type = True
        quantity_requested = None 
        item_name = " ".join(args[1:]).lower() if len(args) > 1 else "" 
    elif args[0].isdigit():
        try:
            quantity_requested = int(args[0])
            item_name = " ".join(args[1:]).lower()
            if quantity_requested <= 0: return f"{FORMAT_ERROR}Quantity must be positive.{FORMAT_RESET}"
            if not item_name: return f"{FORMAT_ERROR}{command_verb.capitalize()} {quantity_requested} of what?{FORMAT_RESET}"
        except ValueError: return f"{FORMAT_ERROR}Invalid quantity '{args[0]}'.{FORMAT_RESET}"
    else: 
        item_name = " ".join(args).lower()

    items_in_inventory = [slot.item for slot in player.inventory.slots if slot.item]
    if not items_in_inventory: return f"{FORMAT_ERROR}Your inventory is empty.{FORMAT_RESET}"
    
    # Matching Logic
    items_to_drop = []
    if drop_all_of_type and not item_name: 
        items_to_drop = list(items_in_inventory)
    else:
        exact_matches = []
        partial_matches = []
        for item in items_in_inventory:
            if item_name == item.name.lower(): exact_matches.append(item)
            elif item_name in item.name.lower(): partial_matches.append(item)
        matches = exact_matches or partial_matches
        
        if not matches: return f"{FORMAT_ERROR}You don't have any '{item_name}'.{FORMAT_RESET}"
        matches.sort(key=lambda item: item.name)
        items_to_drop = matches

    if not items_to_drop: return f"{FORMAT_ERROR}You don't have any '{item_name}' to {command_verb}.{FORMAT_RESET}"

    # Execution Logic
    items_dropped_summary = {}
    qty_remaining_to_drop = quantity_requested if quantity_requested is not None else float('inf')
    
    # Iterate over a COPY of the list
    for item_instance in list(items_to_drop):
        if qty_remaining_to_drop <= 0: break
        if player.inventory.count_item(item_instance.obj_id) <= 0: continue

        if item_instance.stackable:
            count_in_inv = player.inventory.count_item(item_instance.obj_id)
            amount_to_process = min(qty_remaining_to_drop, count_in_inv)
            
            removed_item_type, actual_removed, _ = player.inventory.remove_item(item_instance.obj_id, amount_to_process)
            
            if removed_item_type and actual_removed > 0:
                for _ in range(actual_removed):
                    dropped_copy = ItemFactory.create_item_from_template(item_instance.obj_id, world)
                    if not dropped_copy:
                        import copy
                        dropped_copy = copy.deepcopy(item_instance)
                        dropped_copy.quantity = 1 
                    world.add_item_to_room(player.current_region_id, player.current_room_id, dropped_copy)
                
                summary_key = f"{item_instance.obj_id}_{item_instance.name}"
                if summary_key not in items_dropped_summary:
                    items_dropped_summary[summary_key] = {"name": item_instance.name, "count": 0}
                items_dropped_summary[summary_key]["count"] += actual_removed
                qty_remaining_to_drop -= actual_removed
                
        else:
            if player.inventory.remove_item_instance(item_instance):
                world.add_item_to_room(player.current_region_id, player.current_room_id, item_instance)
                summary_key = f"{item_instance.obj_id}_{item_instance.name}"
                if summary_key not in items_dropped_summary: 
                    items_dropped_summary[summary_key] = {"name": item_instance.name, "count": 0}
                items_dropped_summary[summary_key]["count"] += 1
                qty_remaining_to_drop -= 1

    if not items_dropped_summary: return f"{FORMAT_ERROR}You couldn't {command_verb} any '{item_name}'.{FORMAT_RESET}"
    
    success_parts = []
    for data in items_dropped_summary.values():
        name = data["name"]
        count = data["count"]
        success_parts.append(f"{get_article(name)} {name}" if count == 1 else f"{count} {simple_plural(name)}")

    return f"{FORMAT_SUCCESS}You {command_verb} {', '.join(success_parts)}.{FORMAT_RESET}"

@command("get", ["take", "pickup", "grab"], "interaction", "Pick up items.")
def get_handler(args, context):
    if GET_COMMAND_PREPOSITION in [a.lower() for a in args]:
        try:
            idx = [a.lower() for a in args].index(GET_COMMAND_PREPOSITION)
            item_name = " ".join(args[:idx]).lower()
            cont_name = " ".join(args[idx+1:]).lower()
        except (ValueError, IndexError): return f"{FORMAT_ERROR}Usage: get <item> from <container>{FORMAT_RESET}"
        
        world = context["world"]
        player = context.get('player')
        container = world.find_item_in_room_for_player(cont_name, player)
        if not container: container = player.inventory.find_item_by_name(cont_name)
        
        if not container or not isinstance(container, Container): return f"{FORMAT_ERROR}Container '{cont_name}' not found.{FORMAT_RESET}"
        if not container.properties.get("is_open"): return f"{FORMAT_ERROR}It's closed.{FORMAT_RESET}"
        
        if item_name == "all":
             items = list(container.properties.get("contains", []))
             if not items: return "It's empty."
             count = 0
             for i in list(items):
                  if player.inventory.can_add_item(i)[0] and container.remove_item(i):
                       player.inventory.add_item(i)
                       count += 1
             return f"{FORMAT_SUCCESS}You take {count} items from the {container.name}.{FORMAT_RESET}"

        target = container.find_item_by_name(item_name)
        if not target: return f"{FORMAT_ERROR}'{item_name}' not found in container.{FORMAT_RESET}"
        
        if player.inventory.can_add_item(target)[0]:
             if container.remove_item(target):
                  player.inventory.add_item(target)
                  return f"{FORMAT_SUCCESS}You get the {target.name} from the {container.name}.{FORMAT_RESET}"
        return f"{FORMAT_ERROR}Cannot carry that.{FORMAT_RESET}"

    return _handle_item_acquisition(args, context, "take")

# Export alias explicitly so __init__.py can find it
take_handler = get_handler

@command("drop", [], "interaction", "Drop items.")
def drop_handler(args, context): 
    return _handle_item_disposal(args, context, "drop")
