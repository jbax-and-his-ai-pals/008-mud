# engine/player/magic.py
from typing import TYPE_CHECKING, Tuple, Dict, Any, Optional, cast
import random
import uuid
import time

from engine.magic.spell import Spell
from engine.magic.spell_registry import get_spell
from engine.magic.effects import apply_spell_effect
from engine.npcs.npc import NPC
from engine.config import FORMAT_ERROR, FORMAT_RESET
from engine.utils.utils import calculate_xp_gain, format_loot_drop_message

if TYPE_CHECKING:
    from engine.player.core import Player
    from engine.world.world import World

class PlayerMagicMixin:
    """Mixin for handling player magic and spellcasting."""

    def learn_spell(self, spell_id: str) -> Tuple[bool, str]:
        p = cast('Player', self)
        if p.runtime_state.magic is None:
            return False, "Magic is not enabled for this game."
        spell = get_spell(spell_id)
        if not spell: return False, f"The secrets of '{spell_id}' seem non-existent."
        if spell_id in p.runtime_state.magic.known_spells: return False, f"You already know how to cast {spell.name}."
        if p.runtime_state.progression is not None and p.runtime_state.progression.level < spell.level_required: return False, f"You lack the experience to grasp {spell.name} (requires level {spell.level_required})."
        
        p.runtime_state.magic.known_spells.add(spell_id)
        return True, f"You study the technique and successfully learn {spell.name}!"

    def forget_spell(self, spell_id: str) -> bool:
        p = cast('Player', self)
        if p.runtime_state.magic is None:
            return False
        if spell_id in p.runtime_state.magic.known_spells:
            p.runtime_state.magic.known_spells.remove(spell_id)
            p.runtime_state.magic.cooldowns.pop(spell_id, None)
            return True
        return False

    def can_cast_spell(self, spell: Spell, current_time: float) -> Tuple[bool, str]:
        p = cast('Player', self)
        if p.runtime_state.magic is None:
            return False, "Magic is not enabled for this game."
        if not p.is_alive: return False, "You cannot cast spells while dead."
        
        if p.has_effect("Silenced") or p.has_effect_tag("silence"):
            return False, f"{FORMAT_ERROR}You are silenced and cannot speak the incantations!{FORMAT_RESET}"

        if spell.spell_id not in p.runtime_state.magic.known_spells: return False, "You don't know that spell."
        if p.runtime_state.progression is not None and p.runtime_state.progression.level < spell.level_required: return False, f"You need to be level {spell.level_required} to cast {spell.name}."
        if p.runtime_state.magic.mana < spell.mana_cost: return False, f"Not enough mana (need {spell.mana_cost}, have {int(p.runtime_state.magic.mana)})."
        
        cooldown_end_time = p.runtime_state.magic.cooldowns.get(spell.spell_id, 0)
        if current_time < cooldown_end_time: 
            return False, f"{spell.name} is on cooldown for {max(0, cooldown_end_time - current_time):.1f}s."
            
        return True, ""

    def cast_spell(self, spell: Spell, target, current_time: float, world: Optional['World'] = None) -> Dict[str, Any]:
        p = cast('Player', self)
        if p.runtime_state.magic is None:
            return {"success": False, "message": "Magic is not enabled for this game.", "mana_cost": 0}
        if p.has_effect("Stun"): 
            return {"success": False, "message": f"{FORMAT_ERROR}You are stunned!{FORMAT_RESET}", "mana_cost": 0}
        
        targets = []
        # AoE Logic
        if spell.target_type == "all_enemies":
            target_world = world or p.world
            if not target_world: 
                return {"success": False, "message": "System Error: No world context for AoE.", "mana_cost": 0}
            
            from engine.npcs.combat import is_hostile_to
            room_npcs = target_world.get_npcs_in_room(p.current_region_id or "", p.current_room_id or "")
            targets = [n for n in room_npcs if is_hostile_to(n, p)]
            
            if not targets:
                 return {"success": False, "message": "There are no enemies here to hit.", "mana_cost": 0}
        else:
            # Single Target Validation
            if spell.target_type == 'enemy':
                 from engine.npcs.npc import NPC
                 is_npc_friendly = isinstance(target, NPC) and target.faction != 'hostile'
                 is_self = (target == p)
                 
                 if is_self or is_npc_friendly:
                      return {"success": False, "message": f"{FORMAT_ERROR}You can only cast {spell.name} on hostile targets.{FORMAT_RESET}", "mana_cost": 0}
            
            # Note: Environmental/Item targeting (Room/Item) bypasses these checks in command handler, 
            # but here we just process what is passed.
            targets = [target]

        can_cast, reason = self.can_cast_spell(spell, current_time)
        if not can_cast: return {"success": False, "message": reason, "mana_cost": 0}

        # Deduct Cost & Set Cooldown
        p.runtime_state.magic.mana -= spell.mana_cost
        p.runtime_state.magic.cooldowns[spell.spell_id] = current_time + spell.cooldown
        
        results = []
        from engine.npcs.npc import NPC
        
        for t in targets:
            # Auto-engage if offensive
            if spell.target_type == "all_enemies" or (spell.target_type == "enemy" and t != p): 
                if hasattr(t, 'is_alive') and t.is_alive:
                    if p.runtime_state.combat is not None:
                        p.enter_combat(t)
            
            # Apply Effects
            value, effect_message = apply_spell_effect(p, t, spell, p)
            results.append(effect_message)
            
            # Handle Kill
            if isinstance(t, NPC) and not t.is_alive and spell.has_effect_type("damage"):
                 if p.runtime_state.combat is not None:
                     p.exit_combat(t)
                 target_world = world or p.world
                 if target_world: 
                     target_world.dispatch_event("npc_killed", {"player": p, "npc": t})

                 gold_dropped = 0
                 if hasattr(t, "loot_table"):
                     gold_data = t.loot_table.get("gold_value")
                     if gold_data and isinstance(gold_data, dict):
                         if random.random() < gold_data.get("chance", 0.0):
                             qty_range = gold_data.get("quantity", [1, 1])
                             gold_dropped = random.randint(qty_range[0], qty_range[1])

                 final_xp = (
                     calculate_xp_gain(p.runtime_state.progression.level, getattr(t, 'level', 1), getattr(t, 'max_health', 10))
                     if p.runtime_state.progression is not None
                     else 0
                 )
                 if p.runtime_state.gold is None:
                     gold_dropped = 0
                 server = getattr(target_world, "server", None)
                 use_party_routing = (
                     server is not None
                     and hasattr(server, "party_reward_routing_active")
                     and server.party_reward_routing_active(p)
                 )
                 if use_party_routing and (final_xp > 0 or gold_dropped > 0):
                     reward_text = str(server.grant_party_rewards(p, {"xp": final_xp, "gold": gold_dropped}))
                     if reward_text:
                         results.append(reward_text)
                 else:
                     if gold_dropped > 0 and p.runtime_state.gold is not None:
                         p.runtime_state.gold += gold_dropped
                         results.append(f"You find {gold_dropped} gold.")
                     if final_xp > 0 and p.runtime_state.progression is not None:
                         p.gain_experience(final_xp)
                         results.append(f"You gain {final_xp} experience!")

                 if target_world and hasattr(t, "die"):
                     loot_str = format_loot_drop_message(p, t, t.die(target_world))
                     if loot_str:
                         results.append(loot_str)

        # Formatting Output
        if len(targets) > 1:
            full_message = f"{spell.format_cast_message(p)}\n" + "\n".join(results)
        else:
            full_message = f"{spell.format_cast_message(p)}\n{results[0]}"

        p._add_combat_message(full_message)
        return {"success": True, "message": full_message, "value": 0}
