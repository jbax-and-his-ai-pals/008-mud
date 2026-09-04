# engine/commands/crafting.py
from engine.commands.command_system import command
from engine.config import FORMAT_TITLE, FORMAT_RESET, FORMAT_HIGHLIGHT, FORMAT_CATEGORY, FORMAT_SUCCESS, FORMAT_ERROR

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
