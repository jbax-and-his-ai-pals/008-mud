# engine/commands/interaction/info.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET

@command("collection", ["col", "collections"], "information", "List your collections, or see what one still needs.\nUsage: collection [name]", content_capability="collections")
def collection_status_handler(args, context):
    game = context["game"]
    player = context.get("player")
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    manager = game.collection_manager
    # Named by what a player can see: a collection's name. It used to demand
    # the collection's id, which nothing ever shows a player.
    if not args:
        return manager.list_collections(player)
    query = " ".join(args)
    matches = manager.find_collections(query)
    if len(matches) == 1:
        return manager.get_collection_status(player, matches[0])
    if matches:
        names = ", ".join(str(manager.collections[m].get("name", m)) for m in matches)
        return f"More than one collection matches '{query}': {names}."
    return f"{FORMAT_ERROR}No collection called '{query}'.{FORMAT_RESET}\n\n" + manager.list_collections(player)
