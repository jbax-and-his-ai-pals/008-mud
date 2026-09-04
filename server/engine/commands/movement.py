# engine/commands/movement.py
"""
Contains all commands related to player movement.
"""
from engine.commands.command_system import command, registered_commands
from engine.config import FORMAT_ERROR, FORMAT_RESET

DIRECTIONS = [
    {"name": "north", "aliases": ["n"], "description": "Move north."},
    {"name": "south", "aliases": ["s"], "description": "Move south."},
    {"name": "east", "aliases": ["e"], "description": "Move east."},
    {"name": "west", "aliases": ["w"], "description": "Move west."},
    {"name": "northeast", "aliases": ["ne"], "description": "Move northeast."},
    {"name": "northwest", "aliases": ["nw"], "description": "Move northwest."},
    {"name": "southeast", "aliases": ["se"], "description": "Move southeast."},
    {"name": "southwest", "aliases": ["sw"], "description": "Move southwest."},
    {"name": "up", "aliases": ["u"], "description": "Move up."},
    {"name": "down", "aliases": ["d"], "description": "Move down."},
    {"name": "in", "aliases": ["enter", "inside"], "description": "Enter."},
    {"name": "out", "aliases": ["exit", "outside", "o"], "description": "Exit."},
    # --- ADDED ---
    {"name": "upstream", "aliases": ["upriver"], "description": "Move upstream."},
    {"name": "downstream", "aliases": ["downriver"], "description": "Move downstream."}
]

def register_movement_commands():
    """Dynamically creates and registers all movement commands."""
    for direction_info in DIRECTIONS:
        direction_name = direction_info["name"]
        direction_aliases = direction_info["aliases"]
        direction_description = direction_info["description"]
        if direction_name in registered_commands: continue

        def create_direction_handler(dir_name):
            def handler(args, context):
                world = context["world"]
                player = context.get('player')
                if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
                if player.trading_with:
                    vendor = world.get_npc(player.trading_with)
                    if vendor: vendor.is_trading = False
                    player.trading_with = None
                if not player.is_alive: return f"{FORMAT_ERROR}You are dead. You cannot move.{FORMAT_RESET}"
                return world.change_room(dir_name, player=player)
            return handler

        handler_func = create_direction_handler(direction_name)
        command(
            name=direction_name,
            aliases=direction_aliases,
            category="movement",
            help_text=direction_description
        )(handler_func)

@command("go", ["move", "walk"], "movement", "Move in a direction.\nUsage: go <direction>")
def go_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if player.trading_with:
        vendor = world.get_npc(player.trading_with)
        if vendor: vendor.is_trading = False
        player.trading_with = None
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead. You cannot move.{FORMAT_RESET}"
    if not args: return "Go where?"
    return world.change_room(args[0].lower(), player=player)
