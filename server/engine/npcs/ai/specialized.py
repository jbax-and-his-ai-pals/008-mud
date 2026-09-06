# engine/npcs/ai/specialized.py
from typing import TYPE_CHECKING, Optional, List, Union
from engine.config import NPC_HEALER_HEAL_THRESHOLD
from engine.magic.spell_registry import get_spell
from engine.utils.utils import format_name_for_display
from engine.npcs import combat as npc_combat
from .movement import perform_follow

if TYPE_CHECKING:
    from engine.npcs.npc import NPC
    from engine.player import Player
    from engine.world.world import World

def perform_healer_logic(npc: 'NPC', world: 'World', current_time: float, player: 'Player') -> Optional[str]:
    """Behavior for healer NPCs to heal wounded allies."""
    
    if not npc.current_region_id or not npc.current_room_id:
        return None

    # Find a heal spell
    heal_spell = next((s for s_id in npc.usable_spells 
                       if (s := get_spell(s_id)) 
                       and s.has_effect_type("heal") 
                       and current_time >= npc.spell_cooldowns.get(s_id, 0) 
                       and npc.mana >= s.mana_cost), None)
    
    if not heal_spell: return None
    
    targets: List[Union['NPC', 'Player']] = list(world.get_npcs_in_room(npc.current_region_id, npc.current_room_id))
    targets.extend(world.get_players_in_room(npc.current_region_id, npc.current_room_id, alive_only=True))
    
    wounded = [t for t in targets 
               if t.is_alive 
               and not npc_combat.is_hostile_to(npc, t) 
               and (t.health / t.max_health) < NPC_HEALER_HEAL_THRESHOLD]
    
    if not wounded: return None
    
    target_to_heal = min(wounded, key=lambda t: t.health / t.max_health)
    npc.last_combat_action = current_time 
    
    result = npc_combat.cast_spell(npc, heal_spell, target_to_heal, current_time)
    
    viewer = world.get_viewer_for_npc(npc, preferred_player=player)
    if viewer is not None:
        return result.get("message")
    
    return None

def perform_minion_logic(npc: 'NPC', world: 'World', current_time: float, player: 'Player') -> Optional[str]:
    """Handles logic for minions when they are IDLE (not in combat)."""
    
    if not npc.current_region_id or not npc.current_room_id:
        return None

    owner_id = npc.properties.get("owner_id")
    owner = world.get_player_by_id(owner_id)

    if not owner:
        return npc.despawn(world, silent=True)
        
    duration = npc.properties.get("summon_duration", 0)
    created = npc.properties.get("creation_time", 0)
    if duration > 0 and current_time > (created + duration):
        return npc.despawn(world, silent=False) 

    owner_loc = (owner.current_region_id, owner.current_room_id)
    my_loc = (npc.current_region_id, npc.current_room_id)

    if my_loc != owner_loc:
        npc.follow_target = owner.obj_id 
        return perform_follow(npc, world, owner, path_override=None)

    if my_loc == owner_loc:
        owner_combat = owner.runtime_state.combat
        if owner_combat is not None and owner_combat.in_combat and owner_combat.target:
            target = owner_combat.target
            if target and target.is_alive:
                npc_combat.enter_combat(npc, target)
                return f"{npc.name} moves to assist you against {format_name_for_display(owner, target, False)}!"

        room_npcs = world.get_npcs_in_room(npc.current_region_id, npc.current_room_id)
        attacker = next((other for other in room_npcs if other.is_alive and owner in other.combat_targets), None)
        if attacker:
            npc_combat.enter_combat(npc, attacker)
            return f"{npc.name} intercepts {format_name_for_display(owner, attacker, False)}!"

        hostile = next((other for other in room_npcs if other.is_alive and other.faction == "hostile"), None)
        if hostile:
            npc_combat.enter_combat(npc, hostile)
            return f"{npc.name} moves to attack {format_name_for_display(owner, hostile, False)}!"
            
    return None
