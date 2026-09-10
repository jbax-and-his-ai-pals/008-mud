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
    def _compute_score(player, skill_name: str) -> int:
        """Shared by attempt_check and attempt_check_with_margin: rolls the
        d100 and adds skill level + stat bonus. Kept separate so a second
        entry point can expose the margin against difficulty without
        changing attempt_check's existing return shape (six call sites
        across the engine unpack it as a plain (bool, str) pair today).
        """
        # Skill names are entirely content-authored (a fantasy set might use
        # "lockpicking", a sci-fi one "hacking") -- progression itself may
        # also be disabled for this content set, in which case there's no
        # persistent skill level to draw on.
        progression = player.runtime_state.progression
        skill_data = progression.skills.get(skill_name) if progression is not None else None

        if isinstance(skill_data, dict):
            skill_level = skill_data.get("level", 0)
        else:
            skill_level = 0

        # Which stat backs a given skill is content-defined via ruleset
        # "skills.stat_bonuses" (e.g. {"lockpicking": {"stat": "dexterity",
        # "per_point": 2}}); the engine ships no default mapping since skill
        # names and stat vocabularies are both content-authored.
        stat_bonus = 0
        world = getattr(player, "world", None)
        bonus_config = world.ruleset_section("skills").get("stat_bonuses", {}) if world is not None else {}
        bonus_rule = bonus_config.get(skill_name)
        if isinstance(bonus_rule, dict):
            stat_name = bonus_rule.get("stat")
            per_point = bonus_rule.get("per_point", 1)
            if stat_name:
                stat_bonus = (player.stats.get(stat_name, 10) - 10) * per_point

        roll = random.randint(1, 100)
        return roll + skill_level + stat_bonus

    @staticmethod
    def attempt_check(player, skill_name: str, difficulty: int) -> Tuple[bool, str]:
        """
        Performs a skill check.
        Formula: Roll (0-100) + Skill_Level + Stat_Bonus >= Difficulty
        """
        total_score = SkillSystem._compute_score(player, skill_name)
        success = total_score >= difficulty

        # Debug detail (could be hidden behind a debug flag)
        return success, f"(Rolled {total_score} vs DC {difficulty})"

    @staticmethod
    def attempt_check_with_margin(player, skill_name: str, difficulty: int) -> Tuple[bool, str, int]:
        """Same check as attempt_check, plus the signed margin by which it
        passed or failed (total_score - difficulty; negative on failure).
        For callers that need to scale a consequence by how badly an
        attempt missed (e.g. lockpick wear) rather than just pass/fail.
        """
        total_score = SkillSystem._compute_score(player, skill_name)
        margin = total_score - difficulty
        success = margin >= 0
        return success, f"(Rolled {total_score} vs DC {difficulty})", margin

    @staticmethod
    def grant_xp(player, skill_name: str, amount: int) -> str:
        """Adds XP to a skill and handles leveling up."""
        progression = player.runtime_state.progression
        if progression is None:
            return ""
        if skill_name not in progression.skills:
            progression.skills[skill_name] = {"level": 1, "xp": 0}

        data = progression.skills[skill_name]
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
