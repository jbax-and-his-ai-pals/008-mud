# engine/core/combat_system.py
"""
Centralized logic for combat calculations to ensure consistency between
Player and NPC actions.
"""
import random
from typing import Tuple, Optional, Union, TYPE_CHECKING, Dict, Any

from engine.config import (
    HIT_CHANCE_AGILITY_FACTOR, LEVEL_DIFF_COMBAT_MODIFIERS, 
    MAX_HIT_CHANCE, MIN_HIT_CHANCE, MINIMUM_DAMAGE_TAKEN,
    PLAYER_ATTACK_DAMAGE_VARIATION_RANGE, NPC_ATTACK_DAMAGE_VARIATION_RANGE,
    PLAYER_BASE_HIT_CHANCE, NPC_BASE_HIT_CHANCE,
    FORMAT_ERROR, FORMAT_RESET
)
from engine.utils.text_formatter import get_level_diff_category, format_target_name
from engine.utils.utils import format_name_for_display

if TYPE_CHECKING:
    from engine.player import Player
    from engine.npcs.npc import NPC
    from engine.items.item import Item

Entity = Union['Player', 'NPC']

class CombatSystem:
    @staticmethod
    def calculate_hit_chance(attacker: Entity, defender: Entity) -> float:
        """Calculates the probability (0.0 - 1.0) of a physical attack hitting."""
        
        if attacker.has_effect("Blind"):
            # Hard cap for blind characters
            return 0.20

        is_player = getattr(attacker, 'faction', '') == 'player'
        base_chance = PLAYER_BASE_HIT_CHANCE if is_player else NPC_BASE_HIT_CHANCE

        attacker_agi = attacker.get_effective_stat("agility")
        defender_agi = defender.get_effective_stat("agility")
        
        agi_mod = (attacker_agi - defender_agi) * HIT_CHANCE_AGILITY_FACTOR
        
        attacker_level = getattr(attacker, 'level', 1)
        defender_level = getattr(defender, 'level', 1)
        category = get_level_diff_category(attacker_level, defender_level)
        
        level_hit_mod, _, _ = LEVEL_DIFF_COMBAT_MODIFIERS.get(category, (1.0, 1.0, 1.0))
        
        final_chance = (base_chance + agi_mod) * level_hit_mod
        return max(MIN_HIT_CHANCE, min(final_chance, MAX_HIT_CHANCE))

    @staticmethod
    def calculate_physical_damage(attacker: Entity, defender: Entity, attack_power: int) -> int:
        """Calculates raw physical damage before reduction by armor."""
        is_player = getattr(attacker, 'faction', '') == 'player'
        
        variation_range = PLAYER_ATTACK_DAMAGE_VARIATION_RANGE if is_player else NPC_ATTACK_DAMAGE_VARIATION_RANGE
        damage_var = random.randint(*variation_range)
        
        base_damage = max(1, attack_power + damage_var)
        
        attacker_level = getattr(attacker, 'level', 1)
        defender_level = getattr(defender, 'level', 1)
        category = get_level_diff_category(attacker_level, defender_level)
        
        _, damage_mod, _ = LEVEL_DIFF_COMBAT_MODIFIERS.get(category, (1.0, 1.0, 1.0))
        
        return max(MINIMUM_DAMAGE_TAKEN, int(base_damage * damage_mod))

    @staticmethod
    def execute_attack(attacker: Entity, defender: Entity, attack_power: int, weapon_name: str = "attack", 
                       always_hit: bool = False, viewer: Optional[Entity] = None) -> Dict[str, Any]:
        """
        Performs a full attack calculation and generates descriptive messages.
        """
        # 1. Check Hit
        hit_chance = 1.0 if always_hit else CombatSystem.calculate_hit_chance(attacker, defender)
        is_hit = random.random() <= hit_chance
        
        # --- Name Resolution ---
        if viewer and attacker == viewer:
            att_name = "You"
            att_possessive = "your"
        else:
            att_name = format_name_for_display(viewer, attacker, start_of_sentence=True)
            att_possessive = "its" 

        if viewer and defender == viewer:
            def_name = "you"
        else:
            def_name = format_name_for_display(viewer, defender, start_of_sentence=False)

        # Clean up weapon name
        display_weapon = weapon_name.replace("item_", "").replace("_", " ")
        is_generic_attack = display_weapon == "attack"

        result = {
            "success": True,
            "is_hit": is_hit,
            "damage": 0,
            "target_defeated": False,
            "message": ""
        }

        verb = "deal" if att_name == "You" else "deals"
        attack_verb = "attack" if att_name == "You" else "attacks"
        miss_verb = "miss" if att_name == "You" else "misses"

        # --- Miss Message ---
        if not is_hit:
            if is_generic_attack:
                result["message"] = f"{att_name} {attack_verb} {def_name}, but {miss_verb}!"
            else:
                result["message"] = f"{att_name} {attack_verb} {def_name} with {att_possessive} {display_weapon}, but {miss_verb}!"
            return result

        # 2. Calculate & Apply Damage
        raw_damage = CombatSystem.calculate_physical_damage(attacker, defender, attack_power)
        actual_damage = defender.take_damage(raw_damage, damage_type="physical")
        result["damage"] = actual_damage

        # --- Vampirism Logic ---
        vampiric_heal = 0
        if attacker.has_effect("Vampirism") and actual_damage > 0:
            vampiric_heal = int(actual_damage * 0.5)
            attacker.heal(vampiric_heal)

        # 3. Construct Hit Message
        if is_generic_attack:
            # "The goblin attacks you and deals 5 damage."
            msg = f"{att_name} {attack_verb} {def_name} and {verb} {actual_damage} damage."
        else:
            # "You attack the goblin with your sword and deal 5 damage."
            msg = f"{att_name} {attack_verb} {def_name} with {att_possessive} {display_weapon} and {verb} {actual_damage} damage."
        
        # 4. Handle Defeat
        if not defender.is_alive:
            result["target_defeated"] = True
            if def_name == "you":
                msg += f" {FORMAT_ERROR}You have been defeated!{FORMAT_RESET}"
            else:
                msg += f" {format_name_for_display(viewer, defender, start_of_sentence=True)} is defeated!"

        result["message"] = msg
        return result