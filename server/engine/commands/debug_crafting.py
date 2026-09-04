# engine/commands/debug_crafting.py
from engine.commands.command_system import command
from engine.config import FORMAT_SUCCESS, FORMAT_ERROR, FORMAT_RESET
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
    for ing in recipe.ingredients:
        item_id = ing["item_id"]
        qty = ing["quantity"]
        
        # Create and add
        for _ in range(qty):
            item = ItemFactory.create_item_from_template(item_id, world)
            if item:
                player.inventory.add_item(item)
                added_count += 1
                
    return f"{FORMAT_SUCCESS}Added ingredients for {recipe.name} ({added_count} items).{FORMAT_RESET}"

@command("spawnstation", ["station"], "debug", "Spawn a crafting station in the room.\nUsage: spawnstation <type> (anvil/alchemy)")
def spawnstation_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if not args: return "Usage: spawnstation <anvil|alchemy>"
    if not player or not player.current_region_id or not player.current_room_id:
        return "Player location is unavailable."
    
    st_type = args[0].lower()
    item_id = None
    
    if "anvil" in st_type: item_id = "item_anvil"
    elif "alch" in st_type: item_id = "item_alchemy_kit"
    
    if not item_id: return "Unknown station type."
    
    item = ItemFactory.create_item_from_template(item_id, world)
    if item:
        world.add_item_to_room(player.current_region_id, player.current_room_id, item)
        return f"{FORMAT_SUCCESS}Spawned {item.name}.{FORMAT_RESET}"
    return "Failed to create station."
