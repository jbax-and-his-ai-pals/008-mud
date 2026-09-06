# engine/commands/debug/state.py
import time
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_HIGHLIGHT, FORMAT_RESET
from engine.magic.debug_effects import DEBUG_EFFECTS

@command("sethealth", ["hp"], "debug", "Set current health.\nUsage: sethealth <amount>")
def sethealth_handler(args, context):
    player = context.get("player")
    if not player or not args: return f"{FORMAT_ERROR}Usage: sethealth <amount>{FORMAT_RESET}"
    try:
        val = int(args[0])
        player.health = max(0, min(val, player.max_health))
        if player.health == 0: player.die(context["world"])
        return f"{FORMAT_SUCCESS}Health set to {player.health}.{FORMAT_RESET}"
    except ValueError: return "Invalid number."

@command("setgold", ["gold"], "debug", "Set currency amount.\nUsage: setgold <amount>", ruleset_system="economy")
def setgold_handler(args, context):
    player = context.get("player")
    if not player or not args: return f"{FORMAT_ERROR}Usage: setgold <amount>{FORMAT_RESET}"
    try:
        val = int(args[0])
        if val < 0: return f"{FORMAT_ERROR}Amount cannot be negative.{FORMAT_RESET}"
        player.runtime_state.gold = val
        currency = context["world"].currency_name().capitalize()
        return f"{FORMAT_SUCCESS}{currency} set to {val}.{FORMAT_RESET}"
    except ValueError: return "Invalid number."

@command("level", ["levelup"], "debug", "Level up player.\nUsage: level [count]", ruleset_system="progression")
def level_command_handler(args, context):
    player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}Player not found.{FORMAT_RESET}"
    count = int(args[0]) if args and args[0].isdigit() else 1
    msgs = []
    for _ in range(count):
        player.runtime_state.progression.experience = player.runtime_state.progression.experience_to_level
        msgs.append(player.level_up())
    return "\n".join(msgs)

@command("applyeffect", ["ae"], "debug", "Apply debug effect.\nUsage: ae <target> <effect>")
def applyeffect_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if len(args) < 2: return f"Available: {', '.join(DEBUG_EFFECTS.keys())}"
    
    target_name = args[0].lower()
    target = player if target_name in ["self", "me"] else world.find_npc_in_room_for_player(target_name, player)
    if not target: return "Target not found."
    
    eff = DEBUG_EFFECTS.get(args[1].lower())
    if not eff: return "Effect not found."
    
    target.apply_effect(eff, time.time())
    return f"{FORMAT_SUCCESS}Applied {args[1]}.{FORMAT_RESET}"

@command("removeeffect", ["cleareffect"], "debug", "Remove effect.\nUsage: removeeffect <target> <name>")
def removeeffect_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if len(args) < 2: return "Usage: removeeffect <target> <name>"
    
    target_name = args[0].lower()
    target = player if target_name in ["self", "me"] else world.find_npc_in_room_for_player(target_name, player)
    if not target: return "Target not found."

    # active_effects entries are keyed by display name (e.g. "Debug Poison"),
    # not the DEBUG_EFFECTS registry key (e.g. "debug_poison") used here and
    # by `applyeffect`, so the key must be resolved before matching.
    eff = DEBUG_EFFECTS.get(args[1].lower())
    if not eff: return "Effect not found."

    if target.remove_effect(eff["name"]):
        return f"{FORMAT_SUCCESS}Removed {args[1]}.{FORMAT_RESET}"
    return "Effect not found."
