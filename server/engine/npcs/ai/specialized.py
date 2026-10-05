# engine/npcs/ai/specialized.py
from typing import TYPE_CHECKING, Optional, List, Union
from engine.config import NPC_HEALER_HEAL_THRESHOLD
from engine.magic.spell_registry import get_spell
from engine.utils.utils import format_name_for_display
from engine.npcs import combat as npc_combat, combat_detail
from engine.world import factions
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

COMPANION_HEAL_THRESHOLD = 0.6   # a companion with a healing spell tends anyone in the party below this fraction of health


def _party_in_room(npc: 'NPC', world: 'World', owner) -> list:
    """The owner and the owner's companions standing in `npc`'s room, the fallen included."""
    from engine.npcs import companions

    here = (npc.current_region_id, npc.current_room_id)
    members = [owner] if owner is not None and owner.is_alive and (owner.current_region_id, owner.current_room_id) == here else []
    members += [m for m in companions.companions_of(world, owner) if m is not npc and (m.current_region_id, m.current_room_id) == here]
    return members


def perform_companion_support(npc: 'NPC', world: 'World', current_time: float, player: 'Player') -> Optional[str]:
    """A companion that knows a `revive` or a `heal` spell tends the party: stands up the fallen first, then mends the
    most hurt. It acts on the same rhythm as a blow (`combat.pacing`), so it is not a free action on top of one."""
    from engine.npcs import companions, pacing

    if not npc.usable_spells or npc.has_effect_tag("silence"):
        return None
    if current_time - npc.last_combat_action < pacing.cooldown_of(world, npc.combat_cooldown):
        return None
    owner = world.get_player_by_id(npc.properties.get("owner_id"))
    if owner is None:
        return None
    ready = [s for s_id in npc.usable_spells
             if (s := get_spell(s_id)) and s.target_type == "friendly"
             and current_time >= npc.spell_cooldowns.get(s_id, 0) and npc.mana >= s.mana_cost]
    if not ready:
        return None
    party = _party_in_room(npc, world, owner) + [npc]
    spell, target = None, None
    for candidate in ready:
        if candidate.has_effect_type("revive"):
            down = [m for m in party if companions.is_fallen(m)]
            if down:
                spell, target = candidate, down[0]
                break
    if spell is None:
        for candidate in ready:
            if candidate.has_effect_type("heal"):
                hurt = [m for m in party if m.is_alive and not companions.is_fallen(m) and m.max_health > 0
                        and m.health / m.max_health < COMPANION_HEAL_THRESHOLD]
                if hurt:
                    spell, target = candidate, min(hurt, key=lambda m: m.health / m.max_health)
                    break
    if spell is None or not pacing.room_is_open(world, npc, current_time):
        return None
    npc.last_combat_action = current_time
    pacing.note_action(world, npc, current_time)
    result = npc_combat.cast_spell(npc, spell, target, current_time)
    viewer = world.get_viewer_for_npc(npc, preferred_player=player)
    return result.get("message") if viewer is not None else None


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
        told = perform_follow(npc, world, owner, path_override=None)
        if told and (npc.current_region_id, npc.current_room_id) == owner_loc:
            # It has just walked into the owner's room. The world files an NPC's line under where it *was*, so the owner
            # would never see "arrives": tell them directly.
            if hasattr(world, "notify_player"):
                world.notify_player(owner, told)
            return None
        return told

    if my_loc == owner_loc:
        owner_combat = owner.runtime_state.combat
        if owner_combat is not None and owner_combat.in_combat and owner_combat.target:
            target = owner_combat.target
            if target and target.is_alive:
                npc_combat.enter_combat(npc, target)
                return combat_detail.routine_line(world, owner, f"{npc.name} moves to assist you against {format_name_for_display(owner, target, False)}!", world.clock.now())

        room_npcs = world.get_npcs_in_room(npc.current_region_id, npc.current_room_id)
        attacker = next((other for other in room_npcs if other.is_alive and owner in other.combat_targets), None)
        if attacker:
            npc_combat.enter_combat(npc, attacker)
            return combat_detail.routine_line(world, owner, f"{npc.name} intercepts {format_name_for_display(owner, attacker, False)}!", world.clock.now())

        hostile = next(
            (other for other in room_npcs if other.is_alive and factions.is_hostile(other, world)), None
        )
        if hostile:
            npc_combat.enter_combat(npc, hostile)
            return combat_detail.routine_line(world, owner, f"{npc.name} moves to attack {format_name_for_display(owner, hostile, False)}!", world.clock.now())
            
    return None
