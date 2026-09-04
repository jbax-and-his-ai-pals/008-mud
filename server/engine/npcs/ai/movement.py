# engine/npcs/ai/movement.py
import random
from typing import TYPE_CHECKING, Optional
from engine.utils.utils import format_npc_departure_message, format_npc_arrival_message

if TYPE_CHECKING:
    from engine.npcs.npc import NPC
    from engine.player import Player
    from engine.world.world import World

def execute_move(npc: 'NPC', world: 'World', player: 'Player', direction: str) -> Optional[str]:
    """Helper function to execute NPC movement and generate messages."""
    if not npc.current_region_id or not npc.current_room_id: return None

    old_room_id = npc.current_room_id
    region = world.get_region(npc.current_region_id)
    if not region: return None
    
    room = region.get_room(old_room_id)
    if not room: return None 
    
    destination = room.exits.get(direction)
    if not destination: return None

    new_region_id, new_room_id = (destination.split(':') if ':' in destination else (npc.current_region_id, destination))
    
    message = None
    if (
        player
        and player.is_alive
        and player.current_region_id == npc.current_region_id
        and player.current_room_id == old_room_id
    ):
        message = format_npc_departure_message(npc, direction, player)
    
    npc.current_region_id = new_region_id
    npc.current_room_id = new_room_id
    
    if (
        player
        and player.is_alive
        and player.current_region_id == new_region_id
        and player.current_room_id == new_room_id
    ):
        # If a departure message was already created, append arrival. Otherwise, just create arrival.
        arrival_msg = format_npc_arrival_message(npc, direction, player)
        message = (message + "\n" + arrival_msg) if message else arrival_msg
        
    return message

def perform_wander(npc: 'NPC', world: 'World', player: 'Player') -> Optional[str]:
    if random.random() > npc.wander_chance: return None
    if not npc.current_region_id or not npc.current_room_id: return None
    
    region = world.get_region(npc.current_region_id)
    if not region: return None
    
    room = region.get_room(npc.current_room_id)
    if not room or not room.exits: return None
    
    valid_exits = {}
    is_in_instance = npc.current_region_id and npc.current_region_id.startswith("instance_")

    for direction, dest_id in room.exits.items():
        dest_region_id, dest_room_id = (dest_id.split(':') if ':' in dest_id else (npc.current_region_id, dest_id))

        if not dest_region_id: continue

        # no npcs should enter instances randomly
        if not is_in_instance and dest_region_id.startswith("instance_"):
            continue

        # npcs inside instances cannot leave randomly
        if is_in_instance:
            if dest_region_id == npc.current_region_id:
                valid_exits[direction] = dest_id
            continue

        # hostiles shouldn't wander into safe zones
        if npc.faction == 'hostile':
            if not world.is_location_safe(dest_region_id, dest_room_id):
                valid_exits[direction] = dest_id
        else:
            # friendly npcs can enter safe zones
            valid_exits[direction] = dest_id

    if not valid_exits: return None
    
    direction_to_go = random.choice(list(valid_exits.keys()))
    return execute_move(npc, world, player, direction_to_go)

def perform_patrol(npc: 'NPC', world: 'World', player: 'Player') -> Optional[str]:
    if not npc.patrol_points: return None
    target_room_id = npc.patrol_points[npc.patrol_index]
    
    if npc.current_room_id == target_room_id:
        npc.patrol_index = (npc.patrol_index + 1) % len(npc.patrol_points)
        return None # Arrived at patrol point, wait for next cooldown

    # Find path to the *next* patrol point
    if not npc.current_region_id or not npc.current_room_id or not npc.home_region_id: return None
    path = world.find_path(npc.current_region_id, npc.current_room_id, npc.home_region_id, target_room_id)
    if path: 
        return execute_move(npc, world, player, path[0])
    else:
        # Cannot find path to patrol point, just wander
        return perform_wander(npc, world, player)

def perform_follow(npc: 'NPC', world: 'World', player: 'Player', path_override=None) -> Optional[str]:
    path = path_override
    if not path:
        target_id = npc.follow_target
        if not target_id: return None # No one to follow

        target = world.get_player_by_id(target_id) or world.get_npc(target_id)
        if not target or not target.is_alive: 
            npc.follow_target = None # Target is gone
            return None
        
        # Don't move if in the same room
        if npc.current_region_id == target.current_region_id and npc.current_room_id == target.current_room_id:
            return None 

        # FIX: Removed 'or not npc.home_region_id' check. Minions don't necessarily have homes.
        if not npc.current_region_id or not npc.current_room_id or not target.current_region_id or not target.current_room_id: return None
        path = world.find_path(npc.current_region_id, npc.current_room_id, target.current_region_id, target.current_room_id)
    
    if path: 
        direction = path[0] 
        if path_override: path.pop(0) 
        return execute_move(npc, world, player, direction)
    return None

def perform_schedule(npc: 'NPC', world: 'World', player: 'Player') -> Optional[str]:
    game = world.game
    if not game: return None
    
    # Find the correct schedule entry for the current hour
    current_hour_str = str(game.time_manager.hour)
    target_entry = None
    if current_hour_str in npc.schedule:
        target_entry = npc.schedule[current_hour_str]
    else:
        # Find the most recent schedule entry before the current hour
        sorted_hours = sorted([int(h) for h in npc.schedule.keys()], reverse=True)
        for hour in sorted_hours:
            if game.time_manager.hour >= hour:
                target_entry = npc.schedule[str(hour)]
                break
        if not target_entry and sorted_hours: # Handle wrap-around
            target_entry = npc.schedule[str(sorted_hours[0])]
            
    if not target_entry: return None 

    dest_region = target_entry.get("region_id")
    dest_room = target_entry.get("room_id")
    activity = target_entry.get("activity", "idle")

    new_destination = (dest_region, dest_room, activity)
    
    # Update AI state if destination is new
    if npc.schedule_destination != new_destination:
        npc.schedule_destination = new_destination
        npc.current_path = [] # Clear old path
        npc.ai_state["current_activity"] = activity

    # If at destination, do nothing
    if npc.current_region_id == dest_region and npc.current_room_id == dest_room:
        npc.current_path = [] # Clear path on arrival
        return None

    # Find path if we don't have one
    if not npc.current_path:
        if not npc.current_region_id or not npc.current_room_id: return None
        path = world.find_path(npc.current_region_id, npc.current_room_id, dest_region, dest_room)
        if path:
            npc.current_path = path
        else:
            npc.schedule_destination = None 
            return None
    
    # Move along the path
    direction = npc.current_path.pop(0)
    return execute_move(npc, world, player, direction)
