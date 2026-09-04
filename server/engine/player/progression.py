# engine/player/progression.py
from typing import Tuple, Dict, TYPE_CHECKING, cast

from engine.config import (
    PLAYER_BASE_XP_TO_LEVEL, PLAYER_XP_TO_LEVEL_MULTIPLIER, 
    PLAYER_LEVEL_UP_STAT_INCREASE, PLAYER_LEVEL_HEALTH_BASE_INCREASE,
    PLAYER_LEVEL_CON_HEALTH_MULTIPLIER, PLAYER_MANA_LEVEL_UP_MULTIPLIER,
    PLAYER_MANA_LEVEL_UP_INT_DIVISOR,
    FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_CATEGORY
)
from engine.core.skill_system import SkillSystem

if TYPE_CHECKING:
    from engine.player.core import Player

class PlayerProgressionMixin:
    """Mixin for leveling, skills, and reputation."""

    def gain_experience(self, amount: int) -> Tuple[bool, str]:
        p = cast('Player', self)
        if p.runtime_state.progression is None:
            return False, ""
        p.runtime_state.progression.experience += amount
        leveled_up = False
        level_up_messages = []
        
        while p.runtime_state.progression.experience >= p.runtime_state.progression.experience_to_level:
            level_up_message = p.level_up()
            level_up_messages.append(level_up_message)
            leveled_up = True
            
        return (leveled_up, "\n".join(level_up_messages))

    def level_up(self) -> str:
        p = cast('Player', self)
        if p.runtime_state.progression is None:
            return ""
        old_stats = p.stats.copy()
        old_max_health = p.max_health
        old_max_mana = p.runtime_state.magic.max_mana if p.runtime_state.magic is not None else None
        
        p.runtime_state.progression.level += 1
        p.runtime_state.progression.experience -= p.runtime_state.progression.experience_to_level
        p.runtime_state.progression.experience_to_level = int(p.runtime_state.progression.experience_to_level * PLAYER_XP_TO_LEVEL_MULTIPLIER)
        
        # Increase Core Stats
        for stat in ["strength", "dexterity", "intelligence", "wisdom", "constitution", "agility"]:
            p.stats[stat] += PLAYER_LEVEL_UP_STAT_INCREASE
            
        # Increase HP
        health_increase = PLAYER_LEVEL_HEALTH_BASE_INCREASE + int(p.stats.get('constitution', 10) * PLAYER_LEVEL_CON_HEALTH_MULTIPLIER)
        p.max_health += health_increase
        p.health += (p.max_health - old_max_health)
        
        # Increase Mana
        if p.runtime_state.magic is not None:
            mana_increase = int(p.runtime_state.magic.max_mana * (PLAYER_MANA_LEVEL_UP_MULTIPLIER - 1) + p.stats["intelligence"] / PLAYER_MANA_LEVEL_UP_INT_DIVISOR)
            p.runtime_state.magic.max_mana += mana_increase
            p.runtime_state.magic.mana += (p.runtime_state.magic.max_mana - old_max_mana)
        
        # Build Message
        message = f"{FORMAT_HIGHLIGHT}You have reached level {p.runtime_state.progression.level}!{FORMAT_RESET}\n"
        message += f"  - Max Health: {old_max_health} -> {p.max_health} (+{p.max_health - old_max_health})\n"
        if p.runtime_state.magic is not None and old_max_mana is not None:
            message += f"  - Max Mana:   {old_max_mana} -> {p.runtime_state.magic.max_mana} (+{p.runtime_state.magic.max_mana - old_max_mana})\n"
        message += f"{FORMAT_CATEGORY}Stats Increased:{FORMAT_RESET}\n"
        
        for stat_name, old_value in old_stats.items():
            if stat_name == "resistances": continue
            new_value = p.stats[stat_name]
            if new_value > old_value: 
                message += f"  - {stat_name.capitalize()}: {old_value} -> {new_value} (+{new_value - old_value})\n"
                
        return message.strip()

    def add_skill(self, skill_name: str, level: int = 1) -> None:
        p = cast('Player', self)
        if p.runtime_state.progression is None:
            return
        if skill_name not in p.runtime_state.progression.skills:
            p.runtime_state.progression.skills[skill_name] = {"level": level, "xp": 0}
        else:
            p.runtime_state.progression.skills[skill_name]["level"] += level

    def get_skill_level(self, skill_name: str) -> int:
        p = cast('Player', self)
        if p.runtime_state.progression is None:
            return 0
        skill_data = p.runtime_state.progression.skills.get(skill_name)
        if not skill_data: return 0
        return skill_data.get("level", 0)

    def adjust_reputation(self, faction: str, amount: int):
        p = cast('Player', self)
        if faction not in p.reputation:
            p.reputation[faction] = 0
        p.reputation[faction] += amount
        # Clamp between -100 and 100
        p.reputation[faction] = max(-100, min(100, p.reputation[faction]))

    def get_reputation(self, faction: str) -> int:
        p = cast('Player', self)
        return p.reputation.get(faction, 0)
