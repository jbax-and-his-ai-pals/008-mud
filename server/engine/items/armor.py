# engine/items/armor.py
from engine.items.item import Item
from typing import List, Optional

class Armor(Item):
    """
    Represents a piece of armor that provides defense when equipped.
    """
    def __init__(self,
                 obj_id: Optional[str] = None,
                 name: str = "Unknown Armor",
                 description: str = "A piece of protective gear.",
                 weight: float = 5.0,
                 value: int = 50,
                 defense: int = 1,
                 durability: int = 100,
                 equip_slot: Optional[List[str]] = None,
                 **kwargs):

        if equip_slot is None:
            # Fallback to body as a guess, but this is bad data.
            equip_slot = ["body"]
        elif isinstance(equip_slot, str):
            equip_slot = [equip_slot]

        # Prevent duplicate stackable arg error
        if 'stackable' in kwargs:
            kwargs.pop('stackable')

        super().__init__(
            obj_id=obj_id,
            name=name,
            description=description,
            weight=weight,
            value=value,
            stackable=False,
            defense=defense,
            durability=durability,
            max_durability=durability,
            equip_slot=equip_slot,
            **kwargs
        )
        self.update_property("stackable", False)


    def use(self, user, **kwargs) -> str:
        """Using armor equips it."""
        is_equipped = False
        for slot, equipped_item in user.equipment.items():
            if equipped_item and equipped_item.obj_id == self.obj_id:
                is_equipped = True
                break

        if is_equipped:
            durability = self.get_property("durability", 0)
            max_durability = self.get_property("max_durability", 1)
            condition = "good"
            if max_durability > 0:
                ratio = durability / max_durability
                if ratio <= 0.1: condition = "almost broken"
                elif ratio <= 0.5: condition = "worn"
                elif ratio <= 0.9: condition = "slightly damaged"
            return f"You check your equipped {self.name}. It's in {condition} condition."
        else:
            success, message = user.equip_item(self)
            return message

    def examine(self) -> str:
        return super().examine()