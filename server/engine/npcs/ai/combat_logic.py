# engine/npcs/ai/combat_logic.py
import random
from typing import TYPE_CHECKING, Optional
from engine.utils.utils import format_name_for_display
from .movement import execute_move
from engine.npcs import combat as npc_combat

if TYPE_CHECKING:
    from engine.npcs.npc import NPC
    from engine.player import Player
    from engine.world.world import World

def try_flee(npc: 'NPC', world: 'World', player: 'Player') -> Optional[str]:
    """Attempts to move the NPC to an adjacent room during combat."""
    if not npc.current_region_id or not npc.current_room_id: return None
    region = world.get_region(npc.current_region_id)
    if not region: return None
    room_before_flee = region.get_room(npc.current_room_id)
    
    if not room_before_flee or not room_before_flee.exits:
        return None 

    player_can_see_flee = (
        player
        and player.is_alive
        and player.current_region_id == npc.current_region_id
        and player.current_room_id == room_before_flee.obj_id
    )

    valid_exits = {}
    if npc.faction == 'hostile':
        for direction, dest_id in room_before_flee.exits.items():
            r_id, room_id = (dest_id.split(':') if ':' in dest_id else (npc.current_region_id, dest_id))
            if not world.is_location_safe(r_id, room_id):
                valid_exits[direction] = dest_id
        if not valid_exits: valid_exits = room_before_flee.exits 
    else:
        valid_exits = room_before_flee.exits

    direction = random.choice(list(valid_exits.keys()))
    
    npc_combat.exit_combat(npc)
    execute_move(npc, world, player, direction)
    
    if player_can_see_flee:
        return f"{format_name_for_display(player, npc, True)} flees to the {direction}!"

    return None

def start_retreat(npc: 'NPC', world: 'World', current_time: float, player: 'Player') -> Optional[str]:
    """Calculates a path to a safe zone and sets the AI state to retreating."""
    if not npc.current_region_id or not npc.current_room_id: return None

    if not npc.retreat_destination and npc.current_region_id and npc.current_room_id:
        npc.retreat_destination = world.find_nearest_safe_room(npc.current_region_id, npc.current_room_id)
        
    if npc.retreat_destination:
        path = world.find_path(
            npc.current_region_id, 
            npc.current_room_id, 
            npc.retreat_destination[0], 
            npc.retreat_destination[1]
        )
        
        if path:
            first_direction = path[0]
            npc.current_path = path 
            
            npc.original_behavior = npc.behavior_type
            npc.behavior_type = "retreating_for_mana"
            npc_combat.exit_combat(npc)
            
            if player and player.current_region_id == npc.current_region_id and player.current_room_id == npc.current_room_id:
                return f"{format_name_for_display(player, npc, True)} looks exhausted and retreats from battle, heading {first_direction}!"
        else:
            npc.retreat_destination = None 
            return None 

    return None

def perform_retreat(npc: 'NPC', world: 'World', current_time: float, player: 'Player') -> Optional[str]:
    """Logic for handling the 'retreating_for_mana' state."""
    if npc.mana >= npc.max_mana:
        npc.behavior_type = npc.original_behavior or "wanderer"
        npc.retreat_destination = None
        npc.current_path = []
        if player and player.current_region_id == npc.current_region_id and player.current_room_id == npc.current_room_id:
            return f"{format_name_for_display(player, npc, True)} looks recovered."
        return None

    if npc.retreat_destination and (npc.current_region_id, npc.current_room_id) == npc.retreat_destination:
        npc.current_path = [] 
        return None 

    if npc.current_path:
        next_direction = npc.current_path.pop(0)
        return execute_move(npc, world, player, next_direction)

    npc.behavior_type = npc.original_behavior or "wanderer"
    npc.retreat_destination = None
    if player and player.current_region_id == npc.current_region_id and player.current_room_id == npc.current_room_id:
        return f"{format_name_for_display(player, npc, True)} seems to have lost their way and stops retreating."
    return None

def scan_for_targets(npc: 'NPC', world: 'World', player: 'Player', force_aggression: bool = False) -> Optional[str]:
    """
    Checks for enemies in the current room and initiates combat if found.
    force_aggression: If True, treats the NPC as having at least 1.0 aggression.
    """
    if not npc.current_region_id or not npc.current_room_id: return None

    proactive_aggression = 1.0 if force_aggression else npc.aggression
    
    proactive_targets = []
    social_targets = []
    room_players = world.get_players_in_room(npc.current_region_id, npc.current_room_id, alive_only=True)
    
    # --- 1. Proactive Scan (Faction Enemies) ---
    # Only scan for proactive targets if we have some aggression
    if proactive_aggression > 0:
        ignore_player = world.game and world.game.debug_ignore_player
        
        # Check Player
        for room_player in room_players:
            if ignore_player and room_player is player:
                continue
            if npc_combat.is_hostile_to(npc, room_player):
                proactive_targets.append(room_player)

        # Check other NPCs
        room_npcs = world.get_npcs_in_room(npc.current_region_id, npc.current_room_id)
        for other_npc in room_npcs:
            if other_npc != npc and other_npc.is_alive:
                if npc_combat.is_hostile_to(npc, other_npc):
                    proactive_targets.append(other_npc)

    # --- 2. Social Aggro (Defending Friends) ---
    # Always check this unless hostile (hostiles usually fend for themselves or use proactive logic)
    if npc.faction != "hostile":
        room_npcs = world.get_npcs_in_room(npc.current_region_id, npc.current_room_id)
        
        # Check Player attacking friend
        for room_player in room_players:
             if room_player.runtime_state.combat.in_combat:
                 for target in room_player.runtime_state.combat.targets:
                     # If player is attacking someone this NPC likes
                     if hasattr(target, 'faction') and npc_combat.get_relation_to(npc, target) > 0:
                         social_targets.append(room_player)
                         break

        # Check other NPCs attacking friends
        for actor in room_npcs:
            if actor == npc or not actor.is_alive: continue
            if actor.faction == npc.faction: continue # Ignore infighting within faction
            
            actor_combat = getattr(actor, "runtime_state", None).combat if getattr(actor, "runtime_state", None) is not None else actor
            if actor_combat.in_combat:
                for target in actor_combat.targets if hasattr(actor_combat, "targets") else actor_combat.combat_targets:
                     if hasattr(target, 'faction') and npc_combat.get_relation_to(npc, target) > 0:
                         social_targets.append(actor)
                         break

    # --- 3. Decision Logic ---
    target_to_attack = None
    
    # Priority: Social defense happens automatically (defending allies), Proactive uses RNG check
    if social_targets:
        target_to_attack = random.choice(social_targets)
    elif proactive_targets and random.random() < proactive_aggression:
        target_to_attack = random.choice(proactive_targets)
        
    if target_to_attack:
        npc_combat.enter_combat(npc, target_to_attack)
        return _execute_immediate_attack_msg(npc, world, target_to_attack, player)
            
    return None

def _execute_immediate_attack_msg(npc: 'NPC', world: 'World', target, player: 'Player') -> Optional[str]:
    """Helper to try an attack immediately and format the engage message."""
    import time
    current_time = time.time()
    
    immediate_msg = npc_combat.try_attack(npc, world, current_time)
    
    engage_message = ""
    if (
        player
        and player.is_alive
        and player.current_region_id == npc.current_region_id
        and player.current_room_id == npc.current_room_id
    ):
        att_name = format_name_for_display(player, npc, start_of_sentence=True)
        def_name = format_name_for_display(player, target, start_of_sentence=False)
        engage_message = f"{att_name} moves to attack {def_name}!"

    if immediate_msg:
        return (engage_message + "\n" + immediate_msg).strip()
    return engage_message if engage_message else None
