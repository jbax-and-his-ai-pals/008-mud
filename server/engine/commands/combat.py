# engine/commands/combat.py
"""
Contains all commands related to player combat actions.
"""
import time
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET

# "hit" is intentionally not an alias here -- gambling.py's blackjack "hit"
# command already owns that word, and registered_commands is a flat
# name->handler map, so the later-loaded module always wins.
@command("attack", ["kill", "fight"], "combat", "Attack a target.\nUsage: attack <target_name>", content_capability="combat")
def attack_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead. You cannot attack.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}Attack whom?{FORMAT_RESET}"

    if player.trading_with:
        vendor = world.get_npc(player.trading_with)
        if vendor:
            vendor.is_trading = False
        player.trading_with = None

    target_name = " ".join(args).lower()
    
    # 1. Look for live NPCs first
    target_npc = world.find_npc_in_room_for_player(target_name, player)
    
    if target_npc:
        if not target_npc.is_alive:
             return f"{FORMAT_ERROR}{target_npc.name} is already defeated.{FORMAT_RESET}"
    else:
        # 2. Check for dead bodies in the room to give better feedback
        rid, rmid = player.current_region_id, player.current_room_id
        if rid and rmid:
             all_npcs = [n for n in world.npcs.values() if n.current_region_id == rid and n.current_room_id == rmid]
             for npc in all_npcs:
                  if target_name in npc.name.lower():
                       if not npc.is_alive:
                            return f"{FORMAT_ERROR}{npc.name} is already defeated.{FORMAT_RESET}"

        return f"{FORMAT_ERROR}No '{target_name}' here to attack.{FORMAT_RESET}"

    current_time = time.time()
    
    if not player.can_attack(current_time):
        effective_cooldown = player.get_effective_attack_cooldown()
        time_left = effective_cooldown - (current_time - player.last_attack_time)
        return f"Not ready. Wait {max(0, time_left):.1f}s."

    attack_result = player.attack(target_npc, world)
    return attack_result["message"]

@command("combat", ["cstat", "fightstatus"], "combat", "Show combat status.", content_capability="combat")
def combat_status_handler(args, context):
    player = context.get("player")
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    return player.get_combat_status()
