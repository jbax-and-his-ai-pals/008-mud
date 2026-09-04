# engine/items/gem.py
from typing import Optional
from engine.items.item import Item

class Gem(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Gem",
                 description: str = "A precious, cut gemstone.",
                 weight: float = 0.1, 
                 value: int = 50, 
                 **kwargs):
        
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

    def use(self, user, **kwargs) -> str:
        return f"You hold the {self.name} up to the light. It sparkles brilliantly."