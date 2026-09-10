# engine/items/lockpick.py
from typing import Optional, Any, cast
from engine.items.item import Item
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET, LOCKPICK_DURABILITY_LOSS_DIVISOR
from engine.core.skill_system import SkillSystem

class Lockpick(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Lockpick",
                 description: str = "No description", weight: float = 0.1,
                 value: int = 5, durability: int = 10, max_durability: Optional[int] = None,
                 **kwargs):

        # Durability is per-instance wear, so (like Weapon/Armor) a
        # lockpick can't be a stackable, interchangeable resource -- each
        # pick needs its own inventory slot.
        kwargs.pop('stackable', None)

        super().__init__(
            obj_id=obj_id,
            name=name,
            description=description,
            weight=weight,
            value=value,
            stackable=False,
            **kwargs
        )

        self.max_durability = max_durability if max_durability is not None else durability
        self.durability = min(durability, self.max_durability)
        self.update_property("durability", self.durability)
        self.update_property("max_durability", self.max_durability)

    def apply_wear(self, user, margin: int) -> Optional[str]:
        """Reduce durability after a failed attempt, scaled by how badly it
        missed (a narrow miss barely wears the pick; a bad one costs more).
        Only ever called on failure -- a clean success costs nothing.
        Returns a break message if this destroys the pick, a wear message
        reporting remaining durability otherwise.
        """
        loss = max(1, abs(margin) // LOCKPICK_DURABILITY_LOSS_DIVISOR)
        self.durability = max(0, self.durability - loss)
        self.update_property("durability", self.durability)

        if self.durability <= 0:
            if hasattr(user, "inventory"):
                user.inventory.remove_item(self.obj_id, 1)
            return f"\n{FORMAT_ERROR}Your {self.name} snaps in the mechanism!{FORMAT_RESET}"
        return f"\n(lockpick durability: {self.durability}/{self.max_durability})"

    def use(self, user, target: Optional[Item] = None, **kwargs) -> str:
        if not target:
            return f"What do you want to use the {self.name} on?"

        if hasattr(target, 'pick_lock') and callable(getattr(target, 'pick_lock', None)):
            target_as_any = cast(Any, target)

            # A trapped-and-undisarmed lock always goes off when you try to
            # pick it, win or lose -- disarming first is the only way to
            # avoid it via lockpicking alone.
            trap_msg = ""
            if hasattr(target_as_any, "trigger_trap"):
                trap_msg = target_as_any.trigger_trap(user) or ""
            if trap_msg and not getattr(user, "is_alive", True):
                return trap_msg.strip()

            difficulty = target.get_property("lock_difficulty", 30)
            success, debug_msg, margin = SkillSystem.attempt_check_with_margin(user, "lockpicking", difficulty)

            wear_msg = ""
            if success:
                xp_gain = max(10, difficulty // 2)
                xp_msg = SkillSystem.grant_xp(user, "lockpicking", xp_gain)
                target_as_any.pick_lock(user)
                msg = f"{FORMAT_SUCCESS}Click! You skillfully pick the lock on the {target.name}.{FORMAT_RESET}"
            else:
                xp_msg = SkillSystem.grant_xp(user, "lockpicking", 2)
                wear_msg = self.apply_wear(user, margin) or ""
                msg = f"{FORMAT_ERROR}You fumble with the lock but fail to open it.{FORMAT_RESET}"

            return f"{trap_msg}{msg} {debug_msg}{wear_msg}{xp_msg}"
        else:
            return f"You can't use a lockpick on the {target.name}."
