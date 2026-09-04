# engine/player/display.py
import time
import math
from typing import TYPE_CHECKING, Optional, cast, Any, List
from engine.config import (
    FORMAT_TITLE, FORMAT_RESET, FORMAT_CATEGORY, FORMAT_ERROR, FORMAT_HIGHLIGHT, 
    FORMAT_SUCCESS, FORMAT_CYAN, FORMAT_ORANGE, FORMAT_GRAY, TEXT_COLOR,
    PLAYER_STATUS_HEALTH_CRITICAL_THRESHOLD, PLAYER_STATUS_HEALTH_LOW_THRESHOLD,
    VALID_DAMAGE_TYPES, EQUIPMENT_SLOTS, DEFAULT_COLORS, MIN_ATTACK_COOLDOWN
)
from engine.config.config_display import FORMAT_YELLOW
from engine.items.item import Item
from engine.magic.spell_registry import get_spell
from engine.utils.utils import format_name_for_display

if TYPE_CHECKING:
    from engine.player.core import Player

class PlayerDisplayMixin:
    """
    Mixin class containing display and formatting logic for the Player.
    """

    def get_combat_status(self) -> str:
        # Cast self to Player to satisfy static analysis
        p = cast('Player', self)
        
        if p.runtime_state.combat is None or not p.runtime_state.combat.in_combat or not p.runtime_state.combat.targets: return ""
        
        status = f"{FORMAT_TITLE}COMBAT STATUS{FORMAT_RESET}\n{FORMAT_CATEGORY}Fighting:{FORMAT_RESET}\n"
        
        # FIX: Only count targets that are alive AND in the same room
        valid_targets: List[Any] = [
            t for t in p.runtime_state.combat.targets 
            if hasattr(t, 'is_alive') and t.is_alive and 
            hasattr(t, 'current_room_id') and t.current_room_id == p.current_room_id
        ]
        
        if not valid_targets: 
            status += "  (No current targets in sight)\n"
        else:
            for target in valid_targets:
                formatted_name = format_name_for_display(p, target, start_of_sentence=True)
                if hasattr(target, "health") and hasattr(target, "max_health") and target.max_health > 0:
                    hp_percent = (target.health / target.max_health) * 100
                    hp_color = FORMAT_SUCCESS if hp_percent > 50 else (FORMAT_HIGHLIGHT if hp_percent > 25 else FORMAT_ERROR)
                    status += f"  - {formatted_name}: {hp_color}{int(target.health)}/{int(target.max_health)}{FORMAT_RESET} HP\n"
                else: 
                    status += f"  - {formatted_name}\n"
                    
        if p.combat_messages:
            status += f"\n{FORMAT_CATEGORY}Recent Actions:{FORMAT_RESET}\n"
            for msg in p.combat_messages: 
                status += f"  - {msg}\n"
                
        return status

    def get_status(self) -> str:
        # ... (rest of get_status logic remains the same) ...
        p = cast('Player', self)
        
        health_percent = (p.health / p.max_health) * 100 if p.max_health > 0 else 0
        health_text = f"{int(p.health)}/{int(p.max_health)}"
        if health_percent <= PLAYER_STATUS_HEALTH_CRITICAL_THRESHOLD: health_display = f"{FORMAT_ERROR}{health_text}{FORMAT_RESET}"
        elif health_percent <= PLAYER_STATUS_HEALTH_LOW_THRESHOLD: health_display = f"{FORMAT_HIGHLIGHT}{health_text}{FORMAT_RESET}"
        else: health_display = f"{FORMAT_SUCCESS}{health_text}{FORMAT_RESET}"
        
        has_magic = (not p.world or p.world.has_capability("magic")) and p.runtime_state.magic is not None
        mana_display = ""
        if has_magic and p.runtime_state.magic is not None:
            mana_text = f"{int(p.runtime_state.magic.mana)}/{int(p.runtime_state.magic.max_mana)}"
            mana_display = f"{FORMAT_CYAN}{mana_text}{FORMAT_RESET}"
        
        uses_progression = (not p.world or p.world.uses_progression()) and p.runtime_state.progression is not None
        shows_economy = (not p.world or p.world.ruleset_system_enabled("economy")) and p.runtime_state.gold is not None

        status = f"{FORMAT_CATEGORY}Name:{FORMAT_RESET} {p.name}\n"
        if uses_progression:
            status += f"{FORMAT_CATEGORY}Class:{FORMAT_RESET} {p.runtime_state.progression.player_class}\n"
            status += f"{FORMAT_CATEGORY}Level:{FORMAT_RESET} {p.runtime_state.progression.level} ({FORMAT_CATEGORY}XP:{FORMAT_RESET} {p.runtime_state.progression.experience}/{p.runtime_state.progression.experience_to_level})\n"
        status += f"{FORMAT_CATEGORY}Health:{FORMAT_RESET} {health_display}"
        if has_magic:
            status += f"  {FORMAT_CATEGORY}Mana:{FORMAT_RESET} {mana_display}"
        status += "\n"
        
        if uses_progression:
            stat_parts = []
            stats_to_show = ["strength", "dexterity", "constitution", "agility", "intelligence", "wisdom"]
            if has_magic:
                stats_to_show.extend(["spell_power", "magic_resist"])
            for stat_name in stats_to_show:
                base_stat = p.stats.get(stat_name, 0)
                effective_stat = p.get_effective_stat(stat_name)
                color = FORMAT_RESET
                if effective_stat > base_stat: color = FORMAT_SUCCESS
                elif effective_stat < base_stat: color = FORMAT_ERROR
                abbr = stat_name[:3].upper() if stat_name not in ["spell_power", "magic_resist"] else stat_name.upper()
                stat_parts.append(f"{abbr} {color}{effective_stat}{FORMAT_RESET}")
            status += f"{FORMAT_CATEGORY}Stats:{FORMAT_RESET} {', '.join(stat_parts)}\n"
        if shows_economy:
            status += f"{FORMAT_CATEGORY}Gold:{FORMAT_RESET} {p.runtime_state.gold}\n"
        has_combat = (not p.world or p.world.has_capability("combat")) and p.runtime_state.combat is not None
        if has_combat:
            effective_cd = p.get_effective_attack_cooldown()
            status += f"{FORMAT_CATEGORY}Attack:{FORMAT_RESET} {p.get_attack_power()} ({effective_cd:.1f}s CD), {FORMAT_CATEGORY}Defense:{FORMAT_RESET} {p.get_defense()}\n"

        resistance_parts = []
        for dmg_type in VALID_DAMAGE_TYPES:
            res_value = p.get_resistance(dmg_type)
            if res_value != 0:
                color = FORMAT_SUCCESS if res_value > 0 else FORMAT_ERROR
                resistance_parts.append(f"{dmg_type.capitalize()} {color}{res_value:+}%{FORMAT_RESET}")
        if resistance_parts:
            status += f"{FORMAT_CATEGORY}Resistances:{FORMAT_RESET} {', '.join(resistance_parts)}\n"

        equipped_items_found = False; equip_lines = []
        for slot in EQUIPMENT_SLOTS:
            item = p.equipment.get(slot)
            if isinstance(item, Item):
                equipped_items_found = True
                slot_display = slot.replace('_', ' ').capitalize()
                durability_str = ""
                max_dura = item.get_property("max_durability", 0)
                if max_dura > 0:
                     current_dura = item.get_property("durability", max_dura)
                     dura_percent = (current_dura / max_dura) * 100
                     dura_color = FORMAT_SUCCESS
                     if current_dura <= 0: dura_color = FORMAT_ERROR
                     elif dura_percent <= 30: dura_color = FORMAT_YELLOW 
                     durability_str = f" [{dura_color}{int(current_dura)}/{int(max_dura)}{FORMAT_RESET}]"
                equip_lines.append(f"  - {slot_display}: {item.name}{durability_str}")
        if equipped_items_found: status += f"\n{FORMAT_TITLE}EQUIPPED{FORMAT_RESET}\n" + "\n".join(equip_lines) + "\n"
        
        if p.active_effects:
            status += f"\n{FORMAT_TITLE}EFFECTS{FORMAT_RESET}\n"
            effect_lines = []
            for effect in sorted(p.active_effects, key=lambda e: e.get("name", "zzz")):
                name = effect.get('name', 'Unknown Effect'); duration = effect.get('duration_remaining', 0)
                duration_str = f"{duration / 60:.1f}m" if duration > 60 else f"{duration:.1f}s"
                details = ""
                if effect.get("type") == "dot":
                     details = f" ({effect.get('damage_per_tick', 0)} {effect.get('damage_type', '')}/ {effect.get('tick_interval', 3.0):.0f}s)"
                elif effect.get("type") == "hot":
                    details = f" (+{effect.get('heal_per_tick', 0)} HP/ {effect.get('tick_interval', 3.0):.0f}s)"
                duration_display = f" ({duration_str} remaining)" if "duration_remaining" in effect else ""
                effect_lines.append(f"  - {name}{details}{duration_display}")
            status += "\n".join(effect_lines) + "\n"
        
        if has_magic and p.runtime_state.magic.known_spells:
             status += f"\n{FORMAT_TITLE}SPELLS KNOWN{FORMAT_RESET}\n"
             spell_list = []; current_time = time.time()
             for spell_id in sorted(list(p.runtime_state.magic.known_spells)):
                  spell = get_spell(spell_id)
                  if spell:
                       cooldown_end = p.runtime_state.magic.cooldowns.get(spell_id, 0)
                       cd_status = f" [{FORMAT_ERROR}CD {max(0, cooldown_end - current_time):.1f}s{FORMAT_RESET}]" if current_time < cooldown_end else ""
                       if p.runtime_state.progression is not None:
                            req_color = FORMAT_SUCCESS if p.runtime_state.progression.level >= spell.level_required else FORMAT_ERROR
                            level_req_display = f" ({req_color}L{spell.level_required}{FORMAT_RESET})" if spell.level_required > 1 else ""
                       else:
                            level_req_display = ""
                       spell_list.append(f"  - {FORMAT_HIGHLIGHT}{spell.name}{FORMAT_RESET}{level_req_display}: {spell.mana_cost} MP{cd_status}")
             status += "\n".join(spell_list) + "\n"

        if has_combat and p.runtime_state.combat.in_combat: status += "\n" + self.get_combat_status()
        if not p.is_alive: status += f"\n{FORMAT_ERROR}** YOU ARE DEAD **{FORMAT_RESET}\n"
        return status.strip()
