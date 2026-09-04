# engine/commands/magic.py
import time
from typing import Any, Dict, List, Optional
from engine.commands.command_system import command
from engine.config import (
    CAST_COMMAND_PREPOSITION, FORMAT_CATEGORY, FORMAT_ERROR, FORMAT_HIGHLIGHT,
    FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE, TARGET_SELF_ALIASES
)
from engine.magic.spell import Spell
from engine.magic.spell_registry import get_spell, get_spell_by_name
from engine.npcs.npc import NPC
from engine.items.item import Item
from engine.world.room import Room

@command("cast", ["c"], "magic", "Cast a known spell.\nUsage: cast <spell_name> [on <target_name>]", content_capability="magic")
def cast_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.is_alive: return f"{FORMAT_ERROR}You cannot cast spells while dead.{FORMAT_RESET}"

    current_time = time.time()

    if not args:
        spells_known_text = player.get_status().split(f"{FORMAT_TITLE}SPELLS KNOWN{FORMAT_RESET}")
        if len(spells_known_text) > 1:
             return f"{FORMAT_TITLE}SPELLS KNOWN{FORMAT_RESET}\n" + spells_known_text[1].strip() + "\n\nUsage: cast <spell_name> [on <target_name>]"
        else:
             return f"{FORMAT_ERROR}You don't know any spells.{FORMAT_RESET}\n\nUsage: cast <spell_name> [on <target_name>]"

    # --- Argument Parsing ---
    target_name = ""
    spell_name = ""
    if CAST_COMMAND_PREPOSITION in [a.lower() for a in args]:
         try:
              on_index = [a.lower() for a in args].index(CAST_COMMAND_PREPOSITION)
              spell_name = " ".join(args[:on_index]).lower()
              target_name = " ".join(args[on_index + 1:]).lower()
         except ValueError:
              spell_name = " ".join(args).lower()
    else:
        spell_name = " ".join(args).lower()

    spell = get_spell_by_name(spell_name)
    if not spell: return f"{FORMAT_ERROR}You don't know a spell called '{spell_name}'.{FORMAT_RESET}"

    target = None
    
    # --- Target Resolution ---

    # 1. Item Targeting (Utility Spells like 'Unlock', 'Remove Curse')
    if spell.target_type == "item":
        if not target_name:
            return f"{FORMAT_ERROR}Cast {spell.name} on what item?{FORMAT_RESET}"
        
        # Look in Room
        target = world.find_item_in_room_for_player(target_name, player)
        # Look in Inventory
        if not target:
            target = player.inventory.find_item_by_name(target_name)
        # Look in Equipment
        if not target:
            for item in player.equipment.values():
                if item and target_name in item.name.lower():
                    target = item; break
        
        if not target:
             return f"{FORMAT_ERROR}You don't see '{target_name}' here.{FORMAT_RESET}"
             
        if not isinstance(target, Item):
             return f"{FORMAT_ERROR}That is not a valid target for this spell.{FORMAT_RESET}"

    # 2. Environmental Targeting (Room)
    elif target_name in ["room", "here", "environment", "ground", "area", "floor"]:
        target = world.get_room_for_player(player)

    # 3. Entity Targeting (NPCs/Player)
    elif spell.target_type == "self":
        target = player
    elif target_name:
        # Explicit target name provided
        target = world.find_npc_in_room_for_player(target_name, player)
        if not target and target_name in TARGET_SELF_ALIASES + [player.name.lower()]: 
            target = player
        
        if not target: 
            return f"{FORMAT_ERROR}You don't see '{target_name}' here to target.{FORMAT_RESET}"

    # 4. Auto-Targeting (Enemy)
    elif spell.target_type == "enemy":
         # If already fighting, default to current target
         if player.runtime_state.combat is not None and player.runtime_state.combat.in_combat and player.runtime_state.combat.target and player.runtime_state.combat.target.is_alive:
              target = player.runtime_state.combat.target
              # Verify target is actually in the room (e.g. didn't flee)
              if target not in world.get_npcs_for_player(player): 
                  target = None

         # Otherwise, find the first hostile in the room
         if not target:
              hostiles = [npc for npc in world.get_npcs_for_player(player) if npc.faction == 'hostile']
              if hostiles: 
                  target = hostiles[0]
              else: 
                  return f"{FORMAT_ERROR}Who do you want to cast {spell.name} on?{FORMAT_RESET}"
    
    # 5. Auto-Targeting (AoE)
    elif spell.target_type == "all_enemies":
        # Player.cast_spell handles the actual list generation for AoE.
        # We just need to pass a valid non-None value to bypass "Invalid target" checks below if needed,
        # or rely on Player.cast_spell handling None.
        # However, typically we pass None and let Player.cast_spell scan the room.
        target = None 

    # 6. Default Fallback (Friendly/Buffs)
    else: 
        target = player

    # --- Target Validation ---
    
    # Allow passing None for AoE spells (Player.cast_spell handles it)
    if not target and spell.target_type != "all_enemies":
        return f"{FORMAT_ERROR}Invalid target for {spell.name}.{FORMAT_RESET}"

    # Validate Entity Types (Don't allow healing enemies, etc.)
    # Skip this check if targeting Items or Rooms
    if target and not isinstance(target, (Item, Room)):
        is_enemy = isinstance(target, NPC) and target.faction == "hostile"
        is_friendly_npc = isinstance(target, NPC) and target.faction != "hostile"
        is_self = target == player
        
        if spell.target_type == "enemy" and not is_enemy: 
            return f"{FORMAT_ERROR}You can only cast {spell.name} on hostile targets.{FORMAT_RESET}"
        
        if spell.target_type == "friendly" and not (is_friendly_npc or is_self): 
            return f"{FORMAT_ERROR}You can only cast {spell.name} on yourself or friendly targets.{FORMAT_RESET}"

    # --- Execution ---
    result = player.cast_spell(spell, target, current_time, world)
    return result["message"]

@command("spells", ["spl", "magic"], "magic", "List spells you know.\nUsage: spells [spell_name]", content_capability="magic")
def spells_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    current_time = time.time()

    if player.runtime_state.magic is None:
        return f"{FORMAT_ERROR}Magic is not enabled for this game.{FORMAT_RESET}"
    if not player.runtime_state.magic.known_spells:
        return f"{FORMAT_ERROR}You don't know any spells.{FORMAT_RESET}"

    if args:
        spell_name = " ".join(args).lower()
        found_spell = None
        for spell_id in player.runtime_state.magic.known_spells:
            spell = get_spell(spell_id)
            if spell and (spell.name.lower() == spell_name or spell_name in spell.name.lower()):
                found_spell = spell; break

        if found_spell:
            spell = found_spell
            cooldown_end = player.runtime_state.magic.cooldowns.get(spell.spell_id, 0)
            cooldown_status = f" [{FORMAT_ERROR}On Cooldown: {max(0, cooldown_end - current_time):.1f}s{FORMAT_RESET}]" if current_time < cooldown_end else ""
            
            info = f"{FORMAT_TITLE}{spell.name.upper()}{FORMAT_RESET}\n\n"
            info += f"{FORMAT_CATEGORY}Description:{FORMAT_RESET} {spell.description}\n"
            info += f"{FORMAT_CATEGORY}Mana Cost:{FORMAT_RESET} {spell.mana_cost}\n"
            info += f"{FORMAT_CATEGORY}Cooldown:{FORMAT_RESET} {spell.cooldown:.1f}s{cooldown_status}\n"
            info += f"{FORMAT_CATEGORY}Target:{FORMAT_RESET} {spell.target_type.capitalize()}\n"
            
            # Display Effects
            info += f"{FORMAT_CATEGORY}Effects:{FORMAT_RESET}\n"
            for effect in spell.effects:
                eff_type = effect.get("type", "Unknown").capitalize()
                val = effect.get("value", 0)
                info += f"  - {eff_type}: {val} (Base)\n"
            
            if spell.level_required > 1 and player.runtime_state.progression is not None:
                 req_color = FORMAT_SUCCESS if player.runtime_state.progression.level >= spell.level_required else FORMAT_ERROR
                 info += f"\n{FORMAT_CATEGORY}Level Req:{FORMAT_RESET} {req_color}{spell.level_required}{FORMAT_RESET}\n"
            return info
        else:
            return f"{FORMAT_ERROR}You don't know a spell called '{' '.join(args)}'.{FORMAT_RESET}\nType 'spells' to see all known spells."
    else:
        response = f"{FORMAT_TITLE}KNOWN SPELLS{FORMAT_RESET}\n\n"
        spell_lines = []
        sorted_spells = sorted(list(player.runtime_state.magic.known_spells), key=lambda sid: getattr(get_spell(sid), 'name', sid))
        for spell_id in sorted_spells:
            spell = get_spell(spell_id)
            if spell:
                cooldown_end = player.runtime_state.magic.cooldowns.get(spell_id, 0)
                cooldown_status = f" [{FORMAT_ERROR}CD {max(0, cooldown_end - current_time):.1f}s{FORMAT_RESET}]" if current_time < cooldown_end else ""
                if player.runtime_state.progression is not None:
                    req_color = FORMAT_SUCCESS if player.runtime_state.progression.level >= spell.level_required else FORMAT_ERROR
                    level_req_display = f" ({req_color}L{spell.level_required}{FORMAT_RESET})" if spell.level_required > 1 else ""
                else:
                    level_req_display = ""
                spell_lines.append(f"- {FORMAT_HIGHLIGHT}{spell.name}{FORMAT_RESET}{level_req_display}: {spell.mana_cost} MP{cooldown_status}")
            else:
                spell_lines.append(f"- {FORMAT_ERROR}Unknown Spell ID: {spell_id}{FORMAT_RESET}")
        response += "\n".join(spell_lines)
        response += f"\n\n{FORMAT_CATEGORY}Mana:{FORMAT_RESET} {player.runtime_state.magic.mana}/{player.runtime_state.magic.max_mana}\n\nType 'spells <spell_name>' for more details."
        return response
