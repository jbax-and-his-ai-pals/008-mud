# engine/npcs/ai/dispatcher.py
from typing import TYPE_CHECKING, Optional
from engine.npcs import combat as npc_combat
from .movement import perform_wander, perform_patrol, perform_follow, perform_schedule
from .combat_logic import try_flee, scan_for_targets, perform_retreat
from .specialized import perform_healer_logic, perform_minion_logic

if TYPE_CHECKING:
    from engine.npcs.npc import NPC
    from engine.player import Player
    from engine.world.world import World

def handle_ai(npc: 'NPC', world: 'World', current_time: float, player: 'Player') -> Optional[str]:
    """Main AI handler that delegates to specific behaviors."""
    combat_enabled = world.has_capability("combat")
    
    if npc.has_effect("Stun"):
        return None 

    if npc.is_trading: return None 

    # --- 1. Minion Expiry (High Priority) ---
    if npc.behavior_type == "minion":
        duration = npc.properties.get("summon_duration", 0)
        created = npc.properties.get("creation_time", 0)
        if duration > 0 and current_time > (created + duration):
            return npc.despawn(world, silent=False)
            
    # --- 2. Schedule Override Check (Before Movement/Idle logic) ---
    # Check if schedule dictates aggressive behavior for this specific time
    if combat_enabled and npc.behavior_type == "scheduled":
        game = world.game
        if game:
             current_hour = str(game.time_manager.hour)
             entry = npc.schedule.get(current_hour)
             if entry:
                 override = entry.get("behavior_override")
                 if override == "aggressive":
                     # Initiate combat scan with FORCED AGGRESSION
                     initiate_msg = scan_for_targets(npc, world, player, force_aggression=True)
                     if initiate_msg: return initiate_msg

    # --- 3. High-priority specialized actions ---
    if npc.behavior_type == "healer":
        heal_msg = perform_healer_logic(npc, world, current_time, player)
        if heal_msg: return heal_msg
        
    if npc.behavior_type == "retreating_for_mana":
        return perform_retreat(npc, world, current_time, player)

    # --- 4. Combat Action (if already in combat) ---
    if combat_enabled and npc.in_combat:
        if npc.is_alive and npc.health < npc.max_health * npc.flee_threshold:
            flee_msg = try_flee(npc, world, player)
            if flee_msg: return flee_msg
        return npc_combat.try_attack(npc, world, current_time)

    # --- 5. Combat Initiation (if NOT in combat) ---
    if combat_enabled:
        initiate_msg = scan_for_targets(npc, world, player)
        if initiate_msg:
            return initiate_msg

    # --- 6. Idle Movement (Cooldown check) ---
    if current_time - npc.last_moved < npc.move_cooldown: return None
    
    behavior = npc.behavior_type
    if behavior == "healer": behavior = "wanderer" 
    
    previous_location = (npc.current_region_id, npc.current_room_id)
    move_message = None
    if behavior == "wanderer" or behavior == "aggressive": 
        move_message = perform_wander(npc, world, player)
    elif behavior == "patrol": 
        move_message = perform_patrol(npc, world, player)
    elif behavior == "follower": 
        move_message = perform_follow(npc, world, player)
    elif behavior == "scheduled": 
        move_message = perform_schedule(npc, world, player)
    elif behavior == "minion": 
        move_message = perform_minion_logic(npc, world, current_time, player)
    
    if move_message or (npc.current_region_id, npc.current_room_id) != previous_location:
        npc.last_moved = current_time
    return move_message
