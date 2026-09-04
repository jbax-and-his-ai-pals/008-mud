# engine/core/skill_system.py
import random
from typing import Tuple, Dict, Any
from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET

# Configuration
BASE_XP_TO_LEVEL_SKILL = 100
SKILL_XP_MULTIPLIER = 1.5
MAX_SKILL_LEVEL = 100

class SkillSystem:
    @staticmethod
    def get_xp_for_next_level(current_level: int) -> int:
        """Calculates XP needed to go from current_level to next."""
        return int(BASE_XP_TO_LEVEL_SKILL * (SKILL_XP_MULTIPLIER ** (current_level - 1)))

    @staticmethod
    def attempt_check(player, skill_name: str, difficulty: int) -> Tuple[bool, str]:
        """
        Performs a skill check.
        Formula: Roll (0-100) + Skill_Level + Stat_Bonus >= Difficulty
        """
        # Skill state is always a structured object.
        skill_data = player.runtime_state.progression.skills.get(skill_name)
        
        if isinstance(skill_data, dict):
            skill_level = skill_data.get("level", 0)
        else:
            skill_level = 0
        
        # Get relevant stat bonus (simple mapping)
        stat_bonus = 0
        stats = player.stats
        if skill_name == "lockpicking":
            stat_bonus = (stats.get("dexterity", 10) - 10) * 2
        elif skill_name == "crafting":
            stat_bonus = (stats.get("intelligence", 10) - 10) * 2
        elif skill_name == "mercantile":
            stat_bonus = (stats.get("wisdom", 10) - 10) * 2
            
        roll = random.randint(1, 100)
        total_score = roll + skill_level + stat_bonus
        
        success = total_score >= difficulty
        
        # Debug detail (could be hidden behind a debug flag)
        return success, f"(Rolled {total_score} vs DC {difficulty})"

    @staticmethod
    def grant_xp(player, skill_name: str, amount: int) -> str:
        """Adds XP to a skill and handles leveling up."""
        if skill_name not in player.runtime_state.progression.skills:
            player.runtime_state.progression.skills[skill_name] = {"level": 1, "xp": 0}
            
        data = player.runtime_state.progression.skills[skill_name]
        if data["level"] >= MAX_SKILL_LEVEL:
            return ""

        data["xp"] += amount
        msg = ""
        
        # Check for level up
        required = SkillSystem.get_xp_for_next_level(data["level"])
        while data["xp"] >= required and data["level"] < MAX_SKILL_LEVEL:
            data["xp"] -= required
            data["level"] += 1
            required = SkillSystem.get_xp_for_next_level(data["level"])
            msg += f"\n{FORMAT_HIGHLIGHT}Your {skill_name} skill has increased to {data['level']}!{FORMAT_RESET}"
            
        return msg
