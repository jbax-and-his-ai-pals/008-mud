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
    spell_default_damage_type
)
from engine.contracts import stats as stats_contract
from engine.utils.utils import format_name_for_display, get_article

if TYPE_CHECKING:
    from engine.player import Player
    from engine.npcs.npc import NPC

CasterType = Union['Player', 'NPC']
SpellTargetType = Union['Player', 'NPC', Item, Room]
ViewerType = Union['Player'] 

# A flat bonus added to an ability's value, for an entity that does not carry
# whatever stat the content set names for it. Zero, not "neutral": the curve
# already measures the power stat against neutral, so a second neutral here would
# count twice.
DEFAULT_ABILITY_POWER_BONUS = 0

def apply_spell_effect(caster: CasterType, target: SpellTargetType, spell: Spell, viewer: Optional[ViewerType],
                       first_target: bool = True, landing: bool = False) -> Tuple[int, str]:
    """`first_target` is False for the second and later targets of one cast: a summon happens once per cast, not once per target.
    `landing` is the second half of an ability with a wind-up (magic/windup.py): the effects fall now."""
    from engine.npcs.npc_factory import NPCFactory
    from engine.player import Player
    from engine.magic import windup as _windup

    if _windup.windup_of(spell) and not landing and first_target and not isinstance(target, Room):
        return _windup.begin(caster, target, spell, viewer)
    
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
                    # Forcing a lock open by magic is just as much "trying
                    # to pick the lock without disarming" as doing it by
                    # hand -- a trapped, undisarmed chest goes off either way.
                    if ef_type == "unlock" and hasattr(target, "trigger_trap"):
                        trap_msg = target.trigger_trap(caster)
                        if trap_msg:
                            messages.append(trap_msg)
            return total_value, "\n".join(messages)

    # ... (Rest of function logic same as previous step, just ensure Room import is there)
    # Re-pasting the core loop for completeness/context is safest to ensure no regression.
    
    for effect_def in spell.effects:
        eff_type = effect_def.get("type")
        eff_value = effect_def.get("value", 0)
        eff_dmg_type = effect_def.get("damage_type") or spell_default_damage_type()
        
        # ... (Calc Logic) ...
        # Which stat an ability's own value answers to is the content set's
        # `stats` contract; the curve (one point per five above neutral, plus
        # the power stat directly) is engine config.
        caster_stats = getattr(caster, 'stats', {}) if hasattr(caster, 'stats') else {}
        caster_world = getattr(caster, 'world', None)
        caster_int = stats_contract.stat_for(
            caster_world, caster_stats, "power", stats_contract.NEUTRAL_STAT_VALUE,
        )
        caster_power = stats_contract.stat_for(
            caster_world, caster_stats, "ability_power", DEFAULT_ABILITY_POWER_BONUS
        )
        stat_bonus = max(0, (caster_int - stats_contract.NEUTRAL_STAT_VALUE) // 5) + caster_power
        
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
            from engine.npcs import phases as npc_phases

            if npc_phases.is_untouchable(target):
                # A creature in a phase nothing can touch (mist): the ability passes through it, and it answers.
                shown = format_name_for_display(viewer, target, start_of_sentence=False) if viewer else target_name_raw
                counter = npc_phases.on_blocked_attack(target, viewer)
                messages.append("%s passes straight through %s!" % (spell.name, shown) + (("\n" + counter) if counter else ""))
                continue
            if hasattr(target, 'take_damage'):
                target.last_absorbed = 0
                health_before = getattr(target, "health", 0)
                dmg = getattr(target, 'take_damage')(final_val, damage_type=eff_dmg_type)
                from engine.core import kill_credit
                kill_credit.record_damage(target, caster, min(dmg, health_before), health_before)   # overkill is not extra credit
                total_value += dmg
                
                flavor = ""
                if eff_dmg_type != "physical" and hasattr(target, 'get_resistance'):
                    res = getattr(target, 'get_resistance')(eff_dmg_type)
                    f_key = "weakness" if res < 0 else ("strong_resistance" if res >= 50 else ("resistance" if res > 0 else None))
                    if f_key:
                        raw_flavor = DAMAGE_TYPE_FLAVOR_TEXT.get(eff_dmg_type, DAMAGE_TYPE_FLAVOR_TEXT["default"]).get(f_key)
                        if raw_flavor: flavor = f"{FORMAT_HIGHLIGHT}{raw_flavor.format(target_name=target_name_raw)}{FORMAT_RESET}\n"

                formatted_target = format_name_for_display(viewer, target, start_of_sentence=False) if viewer else target_name_raw
                try:
                     msg = spell.hit_message.format(
                         caster_name=formatted_caster_name, target_name=formatted_target, spell_name=spell.name,
                         value=dmg, damage_type=eff_dmg_type,
                     )
                except: msg = f"{spell.name} hits {formatted_target} for {dmg} {eff_dmg_type} damage."
                if dmg == 0 and getattr(target, "last_absorbed", 0) > 0:
                    msg = f"{formatted_target[:1].upper() + formatted_target[1:]} drinks in the {eff_dmg_type} and is healed for {target.last_absorbed}!"
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

                target_world = getattr(target, "world", None)
                success, _ = getattr(target, 'apply_effect')(dot_payload, target_world.clock.now() if target_world else time.time())
                if success:
                    total_value += 1
                    messages.append(f"{target_name_raw} is afflicted by {dot_payload['name']}.")

        elif eff_type == "percent_damage":
            from engine.npcs import phases as npc_phases

            if npc_phases.is_untouchable(target):
                continue
            immune = getattr(target, "properties", {}).get("percent_immune") is True if isinstance(getattr(target, "properties", None), dict) else False
            shown = format_name_for_display(viewer, target, start_of_sentence=True) if viewer else target_name_raw
            if immune or not hasattr(target, "take_damage"):
                messages.append("%s is untouched." % shown)
                continue
            health_before = getattr(target, "health", 0)
            share = max(1, int(health_before * max(0, min(100, eff_value if eff_value else 25)) / 100.0))
            dmg = target.take_damage(share, damage_type=eff_dmg_type)
            from engine.core import kill_credit
            kill_credit.record_damage(target, caster, min(dmg, health_before), health_before)
            total_value += dmg
            messages.append("%s takes %d %s damage!" % (shown, dmg, eff_dmg_type))

        elif eff_type == "steal":
            from engine.magic import stealing

            line = stealing.attempt(caster, target)
            if line:
                total_value += 1
                messages.append(line)

        elif eff_type == "revive":
            from engine.npcs import companions as _companions

            formatted_target = format_name_for_display(viewer, target, start_of_sentence=False) if viewer else target_name_raw
            if _companions.is_fallen(target):
                health = _companions.revive(target, (eff_value if eff_value else 25) / 100.0)
                total_value += health
                messages.append("%s brings %s back to their feet." % (formatted_caster_name, formatted_target))
            else:
                messages.append("%s has no need of reviving." % (formatted_target[:1].upper() + formatted_target[1:]))

        elif eff_type == "heal":
            from engine.npcs import companions as _companions

            if _companions.is_fallen(target):
                messages.append("%s is down, and must be revived first." % (format_name_for_display(viewer, target, start_of_sentence=True) if viewer else target_name_raw))
                continue
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
                  messages.append(spell.remove_curse_item_message.format(target_name=target.name))
             elif hasattr(target, 'equipment'):
                  count = 0
                  equipment_dict = getattr(target, 'equipment', {})
                  for item in equipment_dict.values():
                       if item and item.get_property("cursed"):
                            item.update_property("cursed", False)
                            count += 1
                  if count > 0:
                      total_value += count
                      messages.append(spell.remove_curse_equipment_message.format(target_name=target_name_raw, value=count))
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
                
                target_world = getattr(target, "world", None)
                success, _ = getattr(target, 'apply_effect')(eff_data, target_world.clock.now() if target_world else time.time())
                if success:
                    total_value += 1
                    formatted_target = format_name_for_display(viewer, target, start_of_sentence=False) if viewer else target_name_raw
                    messages.append(f"{formatted_target} is affected by {eff_data.get('name', 'magic')}.")

        elif eff_type == "summon":
             if isinstance(caster, Player) and first_target:
                  tid = effect_def.get("summon_template_id")
                  dur = effect_def.get("summon_duration", 0)
                  if tid and caster.world:
                       # At the cap, the oldest living summon from this ability
                       # is dismissed to make room: the cost is already paid, so
                       # refusing would waste the cast.
                       cap = effect_def.get("max_summons")
                       if isinstance(cap, int) and not isinstance(cap, bool) and cap > 0:
                            owned = caster.runtime_state.magic.summons.get(spell.spell_id, [])
                            owned[:] = [i for i in owned if (n := caster.world.get_npc(i)) is not None and n.is_alive]
                            while len(owned) >= cap:
                                 oldest = caster.world.get_npc(owned.pop(0))
                                 if oldest is not None:
                                      oldest.despawn(caster.world, silent=True)
                                      messages.append(f"Your {oldest.name} fades away.")
                       instance_id = f"sum_{uuid.uuid4().hex[:4]}"
                       # The minion has to start where the caster is and know whose it is:
                       # the factory reads its location from `current_*_id` and the AI
                       # reads its owner from `properties.owner_id`. A summon without
                       # either was created, listed in the caster's summons, and never
                       # appeared in any room or acted (`perform_minion_logic` returns
                       # at once for an NPC with no location, and despawns one with no
                       # owner).
                       overrides = {
                           "owner_id": caster.obj_id,
                           "current_region_id": caster.current_region_id,
                           "current_room_id": caster.current_room_id,
                           "properties_override": {"owner_id": caster.obj_id, "summon_duration": dur, "creation_time": caster.world.clock.now(), "is_summoned": True},
                           "faction": "player_minion",
                       }
                       npc = NPCFactory.create_npc_from_template(tid, caster.world, instance_id, **overrides)
                       if npc:
                            caster.world.add_npc(npc)
                            summons = caster.runtime_state.magic.summons
                            if spell.spell_id not in summons: summons[spell.spell_id] = []
                            summons[spell.spell_id].append(npc.obj_id)
                            total_value += 1
                            messages.append(f"{npc.name} appears to serve you.")

    return total_value, "\n".join(messages) if messages else f"{spell.name} has no effect."
