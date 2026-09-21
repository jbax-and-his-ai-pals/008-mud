# engine/npcs/ai/dispatcher.py
"""One NPC's turn: which routine runs, given what it is and what is happening.

`npc.behavior_type` is engine-owned, closed vocabulary -- see
`config_npc.NPC_BEHAVIOR_TYPES` for the authorable list and what each value does,
and `NPC_RUNTIME_BEHAVIORS` for the one the engine assigns to itself. A value
outside both means no routine runs at all, so an NPC whose author mistyped
`wanderer` simply stands there; `content_set.py` warns about one at gate time and
`test_npc_behavior_vocabulary.py` proves every declared value is reachable here.

Priority is deliberate and ordered: a stunned or trading NPC does nothing, a
minion may expire, a schedule can force aggression, a healer heals, a retreating
NPC walks home, combat resolves, and only then does idle movement happen -- and
only on the NPC's own cooldown.
"""
from typing import TYPE_CHECKING, Optional
from engine.npcs import combat as npc_combat
from .movement import perform_wander, perform_patrol, perform_follow, perform_schedule
from .combat_logic import try_flee, scan_for_targets, perform_retreat
from .specialized import perform_healer_logic, perform_minion_logic

if TYPE_CHECKING:
    from engine.npcs.npc import NPC
    from engine.player import Player
    from engine.world.world import World

# The one place a behaviour name turns into a routine. `stationary` is
# deliberately absent -- standing still *is* its routine -- and the engine's own
# `retreating_for_mana` is handled above, because it is a state, not a choice.
# Every other authorable behaviour appears here, and
# `test_npc_behavior_vocabulary.py` fails if the declared list and this table
# ever disagree, so a behaviour cannot be documented without being dispatched.
IDLE_ROUTINES = {
    "wanderer": lambda npc, world, player, now: perform_wander(npc, world, player),
    "aggressive": lambda npc, world, player, now: perform_wander(npc, world, player),
    # A healer that never walks cannot reach the people it heals.
    "healer": lambda npc, world, player, now: perform_wander(npc, world, player),
    "patrol": lambda npc, world, player, now: perform_patrol(npc, world, player),
    "follower": lambda npc, world, player, now: perform_follow(npc, world, player),
    "scheduled": lambda npc, world, player, now: perform_schedule(npc, world, player),
    "minion": lambda npc, world, player, now: perform_minion_logic(npc, world, now, player),
}

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

    previous_location = (npc.current_region_id, npc.current_room_id)
    routine = IDLE_ROUTINES.get(npc.behavior_type)
    move_message = routine(npc, world, player, current_time) if routine else None

    if move_message or (npc.current_region_id, npc.current_room_id) != previous_location:
        npc.last_moved = current_time
    return move_message
