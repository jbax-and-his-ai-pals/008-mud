# engine/commands/interaction/info.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET

@command("collection", ["col"], "information", "View status of a collection.\nUsage: collection <id>")
def collection_status_handler(args, context):
    game = context["game"]
    player = context["world"].player
    if not args: return f"{FORMAT_ERROR}Usage: collection <collection_id>{FORMAT_RESET}"
    
    col_id = args[0].lower()
    return game.collection_manager.get_collection_status(player, col_id)