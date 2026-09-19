# engine/commands/debug_crafting.py
from engine.commands.command_system import command
from engine.config import FORMAT_SUCCESS, FORMAT_ERROR, FORMAT_RESET
from engine.crafting.recipe import Recipe
from engine.items.item_factory import ItemFactory

@command("givemats", ["gm"], "debug", "Give all ingredients for a specific recipe.\nUsage: givemats <recipe_id>")
def givemats_handler(args, context):
    world = context["world"]
    player = context.get('player')
    manager = world.game.crafting_manager
    
    if not manager: return "Crafting system not loaded."
    if not args: return "Usage: givemats <recipe_id>"
    
    recipe_id = args[0].lower()
    recipe = manager.recipes.get(recipe_id)
    
    if not recipe:
        # Fuzzy search
        for rid in manager.recipes:
            if recipe_id in rid:
                recipe = manager.recipes[rid]
                break
        if not recipe: return f"{FORMAT_ERROR}Recipe not found.{FORMAT_RESET}"

    added_count = 0
    unresolved = []
    for ing in recipe.ingredients:
        # An ingredient may name a family or a capability rather than one
        # template; the manager resolves that to a concrete id so the debug
        # command still hands over something the recipe will accept.
        item_id = manager.resolve_reference_template(ing)
        if not item_id:
            unresolved.append(Recipe.describe_reference(ing, world))
            continue
        qty = max(1, int(ing.get("quantity", 1)))

        # Create and add
        for _ in range(qty):
            item = ItemFactory.create_item_from_template(item_id, world)
            if item:
                player.inventory.add_item(item)
                added_count += 1

    note = f" [unresolved: {', '.join(unresolved)}]" if unresolved else ""
    return f"{FORMAT_SUCCESS}Added ingredients for {recipe.name} ({added_count} items).{FORMAT_RESET}{note}"

@command("spawnstation", ["station"], "debug", "Spawn a crafting station in the room.\nUsage: spawnstation <type>")
def spawnstation_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if not args: return "Usage: spawnstation <type>"
    if not player or not player.current_region_id or not player.current_room_id:
        return "Player location is unavailable."

    # Which items are spawnable stations is content-authored, matching the
    # engine's general neutrality rule. A content set lists them under
    # `debug.spawnable_stations` as name -> item id; without that, any item
    # carrying a `crafting_station_type` property is a candidate.
    st_type = args[0].lower()
    configured = (world.ruleset_section("debug") or {}).get("spawnable_stations")
    candidates = {}
    if isinstance(configured, dict):
        candidates = {str(k).lower(): str(v) for k, v in configured.items()}
    else:
        for item_id, template in world.item_templates.items():
            if not isinstance(template, dict):
                continue
            station_type = template.get("properties", {}).get("crafting_station_type")
            if station_type:
                candidates[str(station_type).lower().replace("_", " ")] = item_id

    item_id = next((iid for key, iid in candidates.items() if key in st_type), None)
    if not item_id:
        known = ", ".join(sorted(candidates)) or "none configured"
        return f"Unknown station type. Known types: {known}"

    item = ItemFactory.create_item_from_template(item_id, world)
    if item:
        world.add_item_to_room(player.current_region_id, player.current_room_id, item)
        return f"{FORMAT_SUCCESS}Spawned {item.name}.{FORMAT_RESET}"
    return "Failed to create station."
