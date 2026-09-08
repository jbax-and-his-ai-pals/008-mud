# engine/commands/crafting.py
from engine.commands.command_system import command
from engine.config import FORMAT_TITLE, FORMAT_RESET, FORMAT_HIGHLIGHT, FORMAT_CATEGORY, FORMAT_SUCCESS, FORMAT_ERROR
from engine.items.attachments import installed_attachments
from engine.items.item_factory import ItemFactory

@command("recipes", ["craftlist"], "crafting", "List available recipes and crafting stations.\nUsage: recipes [all]", content_capability="crafting")
def recipes_handler(args, context):
    world = context["world"]
    player = context.get('player')
    manager = world.game.crafting_manager
    
    if not manager: return "Crafting system unavailable."

    nearby_stations = manager.get_nearby_stations(player)
    show_all = args and args[0].lower() == "all"

    # Header
    out = [f"{FORMAT_TITLE}CRAFTING{FORMAT_RESET}"]
    if nearby_stations:
        out.append(f"Nearby Stations: {FORMAT_HIGHLIGHT}{', '.join([s.replace('_', ' ').title() for s in nearby_stations])}{FORMAT_RESET}")
    else:
        out.append("Nearby Stations: None")
    out.append("-" * 20)

    # List Recipes
    available_count = 0
    for r_id, recipe in manager.recipes.items():
        can_do, _ = manager.can_craft(player, recipe)
        
        # Filter: Only show if we can craft it OR if the user typed "recipes all"
        # We also show it if we have the station but missing ingredients, to help player learn.
        has_station = not recipe.station_required or recipe.station_required in nearby_stations
        
        if show_all or has_station:
            prefix = f"{FORMAT_SUCCESS}[Ready]{FORMAT_RESET}" if can_do else f"{FORMAT_ERROR}[Locked]{FORMAT_RESET}"
            
            # Format Ingredients string
            ing_list = []
            for ing in recipe.ingredients:
                # Get name from factory/template for display
                from engine.items.item_factory import ItemFactory
                template = ItemFactory.get_template(ing['item_id'], world)
                i_name = template.get("name", ing['item_id']) if template else ing['item_id']
                
                has = player.inventory.count_item(ing['item_id'])
                req = ing['quantity']
                color = FORMAT_SUCCESS if has >= req else FORMAT_ERROR
                ing_list.append(f"{color}{has}/{req} {i_name}{FORMAT_RESET}")
            
            req_str = ", ".join(ing_list)
            station_str = f" ({recipe.station_display})" if recipe.station_required else ""
            
            out.append(f"{prefix} {FORMAT_HIGHLIGHT}{recipe.name}{FORMAT_RESET} {station_str}")
            out.append(f"    Requires: {req_str}")
            craft_count = int(getattr(player, "recipe_craft_counts", {}).get(r_id, 0))
            milestone = recipe.familiarity_milestone(craft_count)
            familiarity = str(milestone.get("label", "")) if milestone else "Unpracticed"
            out.append(f"    Practice: {craft_count} craft{'s' if craft_count != 1 else ''} ({familiarity})")
            out.append(f"    Command: craft {r_id}")
            available_count += 1

    if available_count == 0:
        out.append("No recipes available at current stations.")
        if not show_all:
            out.append("(Type 'recipes all' to see everything you know)")

    return "\n".join(out)

@command("craft", ["make"], "crafting", "Craft an item.\nUsage: craft <recipe_id>", content_capability="crafting")
def craft_handler(args, context):
    world = context["world"]
    player = context.get('player')
    manager = world.game.crafting_manager

    if not args:
        return f"{FORMAT_ERROR}Craft what? Usage: craft <recipe_id> (Use 'recipes' to see list){FORMAT_RESET}"
    
    recipe_id = args[0].lower()
    
    # Fuzzy match for recipe name/id
    if recipe_id not in manager.recipes:
        found = None
        for rid, r in manager.recipes.items():
            if recipe_id in rid.lower() or recipe_id in r.name.lower():
                found = rid
                break
        if found:
            recipe_id = found
        else:
            return f"{FORMAT_ERROR}Unknown recipe '{recipe_id}'.{FORMAT_RESET}"

    result = manager.craft(player, recipe_id)
    
    if "Successfully" in result:
        return f"{FORMAT_SUCCESS}{result}{FORMAT_RESET}"
    else:
        return f"{FORMAT_ERROR}{result}{FORMAT_RESET}"
    
@command("salvage", ["breakdown", "scrap"], "crafting", "Break an item into materials.\nUsage: salvage <item>", content_capability="crafting")
def salvage_handler(args, context):
    world = context["world"]
    player = context.get('player')
    manager = world.game.crafting_manager
    
    if not args: return f"{FORMAT_ERROR}Salvage what?{FORMAT_RESET}"
    
    item_name = " ".join(args).lower()
    item = player.inventory.find_item_by_name(item_name)
    
    if not item: return f"{FORMAT_ERROR}You don't have '{item_name}'.{FORMAT_RESET}"
    
    # Optional: Check for tool (Hammer/Kit) here if desired
    
    return manager.salvage(player, item)


@command("attach", ["install"], "crafting", "Install an attachment token into an item.\nUsage: attach <token> to <item>", content_capability="crafting")
def attach_handler(args, context):
    """Install a content-authored attachment without assuming a token theme."""
    player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    lowered = [str(arg).lower() for arg in args]
    if "to" not in lowered:
        return f"{FORMAT_ERROR}Usage: attach <token> to <item>{FORMAT_RESET}"
    split_at = lowered.index("to")
    token_name = " ".join(args[:split_at]).strip()
    host_name = " ".join(args[split_at + 1:]).strip()
    if not token_name or not host_name:
        return f"{FORMAT_ERROR}Usage: attach <token> to <item>{FORMAT_RESET}"
    token = player.inventory.find_item_by_name(token_name)
    if token is None:
        return f"{FORMAT_ERROR}You do not have '{token_name}'.{FORMAT_RESET}"
    attachment = token.get_property("attachment")
    if not isinstance(attachment, dict):
        return f"{FORMAT_ERROR}The {token.name} is not an attachment token.{FORMAT_RESET}"
    slot = str(attachment.get("slot", "")).strip()
    modifiers = attachment.get("modifiers", {})
    if not slot or not isinstance(modifiers, dict):
        return f"{FORMAT_ERROR}The {token.name} has an invalid attachment definition.{FORMAT_RESET}"
    host = player.inventory.find_item_by_name(host_name)
    if host is None:
        host = next((item for item in player.equipment.values() if item and host_name.lower() in item.name.lower()), None)
    if host is None:
        return f"{FORMAT_ERROR}You do not have '{host_name}'.{FORMAT_RESET}"
    slots = host.get_property("attachment_slots", [])
    if not isinstance(slots, list) or slot not in slots:
        return f"{FORMAT_ERROR}The {host.name} has no compatible '{slot}' attachment slot.{FORMAT_RESET}"
    attachments = installed_attachments(host)
    if any(str(entry.get("slot", "")) == slot for entry in attachments):
        return f"{FORMAT_ERROR}The {host.name}'s '{slot}' attachment slot is already occupied.{FORMAT_RESET}"
    removed, _count, _message = player.inventory.remove_item(token.obj_id, 1)
    if removed is None:
        return f"{FORMAT_ERROR}Failed to install the {token.name}.{FORMAT_RESET}"
    attachments.append({"slot": slot, "item_id": token.obj_id, "name": token.name, "modifiers": modifiers})
    host.update_property("attachments", attachments)
    return f"{FORMAT_SUCCESS}You install {token.name} in the {host.name}'s {slot} slot.{FORMAT_RESET}"


@command("detach", ["remove attachment"], "crafting", "Remove an attachment token from an item.\nUsage: detach <slot> from <item>", content_capability="crafting")
def detach_handler(args, context):
    """Return an installed token to inventory using its content template."""
    player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    lowered = [str(arg).lower() for arg in args]
    if "from" not in lowered:
        return f"{FORMAT_ERROR}Usage: detach <slot> from <item>{FORMAT_RESET}"
    split_at = lowered.index("from")
    slot = " ".join(args[:split_at]).strip()
    host_name = " ".join(args[split_at + 1:]).strip()
    if not slot or not host_name:
        return f"{FORMAT_ERROR}Usage: detach <slot> from <item>{FORMAT_RESET}"
    host = player.inventory.find_item_by_name(host_name)
    if host is None:
        host = next((item for item in player.equipment.values() if item and host_name.lower() in item.name.lower()), None)
    if host is None:
        return f"{FORMAT_ERROR}You do not have '{host_name}'.{FORMAT_RESET}"
    attachments = installed_attachments(host)
    match_index = next((index for index, entry in enumerate(attachments) if str(entry.get("slot", "")).lower() == slot.lower()), None)
    if match_index is None:
        return f"{FORMAT_ERROR}The {host.name} has no '{slot}' attachment installed.{FORMAT_RESET}"
    attachment = attachments[match_index]
    token_id = str(attachment.get("item_id", "")).strip()
    token = ItemFactory.create_item_from_template(token_id, player.world)
    if token is None:
        return f"{FORMAT_ERROR}The installed attachment cannot be recovered safely.{FORMAT_RESET}"
    can_add, space_message = player.inventory.can_add_item(token)
    if not can_add:
        return f"{FORMAT_ERROR}Not enough inventory space: {space_message}{FORMAT_RESET}"
    attachments.pop(match_index)
    host.update_property("attachments", attachments)
    player.inventory.add_item(token)
    return f"{FORMAT_SUCCESS}You remove {token.name} from the {host.name}'s {slot} slot.{FORMAT_RESET}"
