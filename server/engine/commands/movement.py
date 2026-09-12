# engine/commands/movement.py
"""
Contains all commands related to player movement.
"""
import random
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

@command("flee", ["retreat"], "combat", "Attempt to break away from combat by fleeing to a nearby room.\nUsage: flee", content_capability="combat")
def flee_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead. You cannot flee.{FORMAT_RESET}"
    combat_state = getattr(player.runtime_state, "combat", None)
    if combat_state is None or not combat_state.in_combat:
        return f"{FORMAT_ERROR}You are not in combat.{FORMAT_RESET}"

    current_room = world.get_current_room(player)
    if not current_room or not current_room.exits:
        return f"{FORMAT_ERROR}There's nowhere to run!{FORMAT_RESET}"

    # A player fleeing prefers safety, the mirror image of a hostile NPC's
    # own try_flee (engine/npcs/ai/combat_logic.py), which prefers exits
    # AWAY from safe rooms since it wants to keep fighting elsewhere.
    safe_exits = []
    other_exits = []
    for direction, dest_id in current_room.exits.items():
        region_id, room_id = (dest_id.split(":") if ":" in dest_id else (player.current_region_id, dest_id))
        (safe_exits if world.is_location_safe(region_id, room_id) else other_exits).append(direction)

    direction = random.choice(safe_exits) if safe_exits else random.choice(other_exits)
    return world.change_room(direction, player=player)
