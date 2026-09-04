# engine/items/lockpick.py
import random
from typing import Optional, Any, cast
from engine.items.item import Item
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_HIGHLIGHT, FORMAT_RESET
from engine.core.skill_system import SkillSystem

class Lockpick(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Lockpick",
                 description: str = "No description", weight: float = 0.1,
                 value: int = 5, break_chance: float = 0.25, **kwargs):
                 
        is_stackable = kwargs.pop('stackable', True)

        super().__init__(
            obj_id=obj_id, 
            name=name, 
            description=description, 
            weight=weight, 
            value=value, 
            stackable=is_stackable, 
            **kwargs
        )
        
        self.break_chance = break_chance
        self.update_property("break_chance", break_chance)

    def use(self, user, target: Optional[Item] = None, **kwargs) -> str:
        if not target:
            return f"What do you want to use the {self.name} on?"

        if hasattr(target, 'pick_lock') and callable(getattr(target, 'pick_lock', None)):
            target_as_any = cast(Any, target)
            
            difficulty = target.get_property("lock_difficulty", 30)
            success, debug_msg = SkillSystem.attempt_check(user, "lockpicking", difficulty)
            
            xp_msg = ""
            if success:
                xp_gain = max(10, difficulty // 2)
                xp_msg = SkillSystem.grant_xp(user, "lockpicking", xp_gain)
            else:
                xp_msg = SkillSystem.grant_xp(user, "lockpicking", 2)

            skill_level = user.get_skill_level("lockpicking")
            adjusted_break_chance = max(0.05, self.break_chance - (skill_level * 0.005))
            
            break_msg = ""
            if random.random() < adjusted_break_chance:
                if hasattr(user, "inventory"):
                    user.inventory.remove_item(self.obj_id, 1)
                break_msg = f"\n{FORMAT_ERROR}Your lockpick snaps in the mechanism!{FORMAT_RESET}"

            if success:
                target_as_any.pick_lock(user)
                msg = f"{FORMAT_SUCCESS}Click! You skillfully pick the lock on the {target.name}.{FORMAT_RESET}"
            else:
                msg = f"{FORMAT_ERROR}You fumble with the lock but fail to open it.{FORMAT_RESET}"

            return f"{msg} {debug_msg}{break_msg}{xp_msg}"
        else:
            return f"You can't use a lockpick on the {target.name}."