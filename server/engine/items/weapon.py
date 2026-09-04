# engine/items/weapon.py
from engine.items.item import Item
from typing import List, Optional

class Weapon(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Weapon",
                 description: str = "No description", weight: float = 2.0,
                 value: int = 10, damage: int = 5, durability: int = 100,
                 equip_slot: Optional[List[str]] = None,
                 **kwargs):
        if equip_slot is None:
             equip_slot = ["main_hand", "off_hand"]

        # Prevent duplicate stackable arg error
        if 'stackable' in kwargs:
            kwargs.pop('stackable')

        super().__init__(
            obj_id=obj_id, name=name, description=description, weight=weight,
            value=value, equip_slot=equip_slot, stackable=False,
            damage=damage, durability=durability, max_durability=durability,
            **kwargs
        )
        self.update_property("stackable", False)

    def use(self, user, **kwargs) -> str:
        is_equipped = False
        for slot, equipped_item in user.equipment.items():
             if equipped_item and equipped_item.obj_id == self.obj_id:
                  is_equipped = True
                  break

        if is_equipped:
             durability = self.get_property("durability")
             if durability <= 0: return f"The {self.name} is broken and cannot be used."
             condition = "sturdy" if durability > self.get_property("max_durability", 1) / 2 else "worn"
             return f"You practice swinging the equipped {self.name}. It feels {condition}."
        else:
             success, message = user.equip_item(self)
             return message

    def examine(self) -> str:
        return super().examine()