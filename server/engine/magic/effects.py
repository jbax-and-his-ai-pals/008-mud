# engine/magic/effects.py
import random
import time
from typing import TYPE_CHECKING, Any, Optional, Tuple, Union, Dict
import uuid

from engine.items.container import Container
from engine.items.item import Item
from engine.world.room import Room # NEW
from engine.utils.text_formatter import get_level_diff_category, format_target_name
from engine.magic.spell import Spell
from engine.config import (
    DAMAGE_TYPE_FLAVOR_TEXT, EFFECT_DEFAULT_TICK_INTERVAL, FORMAT_HIGHLIGHT, FORMAT_RESET,
    LEVEL_DIFF_COMBAT_MODIFIERS, MINIMUM_SPELL_EFFECT_VALUE, SPELL_DAMAGE_VARIATION_FACTOR,
    SPELL_DEFAULT_DAMAGE_TYPE
)
from engine.utils.utils import format_name_for_display, get_article

if TYPE_CHECKING:
    from engine.player import Player
    from engine.npcs.npc import NPC

CasterType = Union['Player', 'NPC']
SpellTargetType = Union['Player', 'NPC', Item, Room]
ViewerType = Union['Player'] 

def apply_spell_effect(caster: CasterType, target: SpellTargetType, spell: Spell, viewer: Optional[ViewerType]) -> Tuple[int, str]:
    from engine.npcs.npc_factory import NPCFactory
    from engine.player import Player
    
    total_value = 0
    messages = []
    
    formatted_caster_name = format_name_for_display(viewer, caster, start_of_sentence=True) if viewer else getattr(caster, 'name', 'Someone')
    target_name_raw = getattr(target, 'name', 'target')

    # --- 0. Environmental Interaction ---
    if isinstance(target, Room):
        # Scan all effects for damage types that might interact
        reacted = False
        for effect_def in spell.effects:
            dmg_type = effect_def.get("damage_type")
            if dmg_type:
                env_msg = target.apply_elemental_interaction(dmg_type)
                if env_msg:
                    messages.append(env_msg)
                    reacted = True
        
        if reacted: return 1, "\n".join(messages)
        else: return 0, "The spell dissipates into the air with no effect."

    # --- 1. Item/Container Logic ---
    if spell.has_effect_type("unlock") or spell.has_effect_type("lock"):
        if isinstance(target, Container):
            # Iterate effects to find the specific lock action
            for ef in spell.effects:
                ef_type = ef.get("type")
                if ef_type and ef_type in ["unlock", "lock"]:
                    success, msg = target.magic_interact(ef_type)
                    if success: total_value = 1
                    messages.append(msg)
            return total_value, "\n".join(messages)

    # ... (Rest of function logic same as previous step, just ensure Room import is there)
    # Re-pasting the core loop for completeness/context is safest to ensure no regression.
    
    for effect_def in spell.effects:
        eff_type = effect_def.get("type")
        eff_value = effect_def.get("value", 0)
        eff_dmg_type = effect_def.get("damage_type", "magical")
        
        # ... (Calc Logic) ...
        caster_int = getattr(caster, 'stats', {}).get('intelligence', 10) if hasattr(caster, 'stats') else 10
        caster_power = getattr(caster, 'stats', {}).get('spell_power', 0) if hasattr(caster, 'stats') else 0
        stat_bonus = max(0, (caster_int - 10) // 5) + caster_power
        
        modified_value = eff_value + stat_bonus
        variation = random.uniform(-SPELL_DAMAGE_VARIATION_FACTOR, SPELL_DAMAGE_VARIATION_FACTOR)
        stat_based_value = max(MINIMUM_SPELL_EFFECT_VALUE, int(modified_value * (1 + variation)))
        
        caster_level = getattr(caster, 'level', 1)
        target_level = getattr(target, 'level', 1)
        category = get_level_diff_category(caster_level, target_level)
        _, damage_heal_mod, _ = LEVEL_DIFF_COMBAT_MODIFIERS.get(category, (1.0, 1.0, 1.0))
        
        final_val = stat_based_value
        if eff_type in ["damage", "heal", "life_tap"]:
            final_val = max(MINIMUM_SPELL_EFFECT_VALUE, int(stat_based_value * damage_heal_mod))

        if eff_type == "damage":
            if hasattr(target, 'take_damage'):
                dmg = getattr(target, 'take_damage')(final_val, damage_type=eff_dmg_type)
                total_value += dmg
                
                flavor = ""
                if eff_dmg_type != "physical" and hasattr(target, 'get_resistance'):
                    res = getattr(target, 'get_resistance')(eff_dmg_type)
                    f_key = "weakness" if res < 0 else ("strong_resistance" if res >= 50 else ("resistance" if res > 0 else None))
                    if f_key:
                        raw_flavor = DAMAGE_TYPE_FLAVOR_TEXT.get(eff_dmg_type, DAMAGE_TYPE_FLAVOR_TEXT["default"]).get(f_key)
                        if raw_flavor: flavor = f"{FORMAT_HIGHLIGHT}{raw_flavor.format(target_name=target_name_raw)}{FORMAT_RESET}\n"

                formatted_target = format_name_for_display(viewer, target, start_of_sentence=False) if viewer else target_name_raw
                msg = spell.hit_message.replace("points!", f"{eff_dmg_type} points!")
                try:
                     msg = msg.format(caster_name=formatted_caster_name, target_name=formatted_target, spell_name=spell.name, value=dmg)
                except: msg = f"{spell.name} hits {formatted_target} for {dmg} {eff_dmg_type} damage."
                messages.append(flavor + msg)

        elif eff_type == "apply_dot":
            if hasattr(target, 'apply_effect'):
                dot_payload = {
                    "type": "dot",
                    "name": effect_def.get("dot_name", "DoT"),
                    "base_duration": effect_def.get("dot_duration", 10.0),
                    "damage_per_tick": effect_def.get("dot_damage_per_tick", 5),
                    "tick_interval": effect_def.get("dot_tick_interval", EFFECT_DEFAULT_TICK_INTERVAL),
                    "damage_type": effect_def.get("dot_damage_type", eff_dmg_type),
                    "source_id": getattr(caster, 'obj_id', None)
                }
                # Tags
                if effect_def.get("effect_data") and "tags" in effect_def["effect_data"]:
                    dot_payload["tags"] = effect_def["effect_data"]["tags"]

                success, _ = getattr(target, 'apply_effect')(dot_payload, time.time())
                if success:
                    total_value += 1
                    messages.append(f"{target_name_raw} is afflicted by {dot_payload['name']}.")

        elif eff_type == "heal":
            if hasattr(target, 'heal'):
                healed = getattr(target, 'heal')(final_val)
                total_value += healed
                formatted_target = format_name_for_display(viewer, target, start_of_sentence=False) if viewer else target_name_raw
                msg = spell.heal_message if caster != target else spell.self_heal_message
                try:
                    msg = msg.format(caster_name=formatted_caster_name, target_name=formatted_target, spell_name=spell.name, value=healed)
                except: msg = f"{spell.name} heals {formatted_target} for {healed}."
                messages.append(msg)

        elif eff_type == "cleanse":
             if hasattr(target, 'remove_effects_by_tag'):
                effect_data = effect_def.get("effect_data") or {}
                tags = effect_data.get("tags", ["poison", "disease", "curse"])
                count = 0
                for t in tags: count += len(target.remove_effects_by_tag(t))
                if count > 0: 
                    total_value += count
                    messages.append(f"{target_name_raw} is cleansed of {count} afflictions.")
                else: messages.append(f"{spell.name} finds nothing to cleanse on {target_name_raw}.")

        elif eff_type == "remove_curse":
             if isinstance(target, Item) and target.get_property("cursed"):
                  target.update_property("cursed", False)
                  total_value += 1
                  messages.append(f"The curse on {target.name} is lifted.")
             elif hasattr(target, 'equipment'):
                  count = 0
                  equipment_dict = getattr(target, 'equipment', {})
                  for item in equipment_dict.values():
                       if item and item.get_property("cursed"):
                            item.update_property("cursed", False)
                            count += 1
                  if count > 0: 
                      total_value += count
                      messages.append(f"A holy light unbinds {count} cursed items from {target_name_raw}.")
                  else:
                      messages.append(f"{target_name_raw} is not wearing any cursed items.")

        elif eff_type == "life_tap":
             if hasattr(target, 'take_damage'):
                  dmg = getattr(target, 'take_damage')(final_val, damage_type=eff_dmg_type)
                  total_value += dmg
                  if dmg > 0:
                       heal = int(dmg * 0.5)
                       if hasattr(caster, 'heal'): caster.heal(heal)
                       messages.append(f"{spell.name} drains {dmg} life from {target_name_raw} and heals you for {heal}!")
                  else: messages.append(f"{spell.name} fails to drain {target_name_raw}.")
        
        elif eff_type == "apply_effect":
            if hasattr(target, 'apply_effect'):
                eff_data = (effect_def.get("effect_data") or {}).copy()
                if not eff_data: continue 

                if "base_duration" not in eff_data:
                     if "dot_duration" in effect_def:
                          eff_data["base_duration"] = effect_def["dot_duration"]
                     elif "base_duration" in effect_def:
                          eff_data["base_duration"] = effect_def["base_duration"]
                
                success, _ = getattr(target, 'apply_effect')(eff_data, time.time())
                if success:
                    total_value += 1
                    formatted_target = format_name_for_display(viewer, target, start_of_sentence=False) if viewer else target_name_raw
                    messages.append(f"{formatted_target} is affected by {eff_data.get('name', 'magic')}.")

        elif eff_type == "summon":
             if isinstance(caster, Player):
                  tid = effect_def.get("summon_template_id")
                  dur = effect_def.get("summon_duration", 0)
                  if tid and caster.world:
                       instance_id = f"sum_{uuid.uuid4().hex[:4]}"
                       overrides = {"owner_id": caster.obj_id, "properties_override": {"summon_duration": dur, "creation_time": time.time(), "is_summoned": True}, "faction": "player_minion"}
                       npc = NPCFactory.create_npc_from_template(tid, caster.world, instance_id, **overrides)
                       if npc:
                            caster.world.add_npc(npc)
                            summons = caster.runtime_state.magic.summons
                            if spell.spell_id not in summons: summons[spell.spell_id] = []
                            summons[spell.spell_id].append(npc.obj_id)
                            total_value += 1
                            messages.append(f"{npc.name} appears to serve you.")

    return total_value, "\n".join(messages) if messages else f"{spell.name} has no effect."
