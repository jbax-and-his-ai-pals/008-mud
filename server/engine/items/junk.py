# engine/items/junk.py
from typing import Optional
from engine.items.item import Item

class Junk(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Junk",
                 description: str = "An item of little apparent use, but maybe someone will buy it.",
                 weight: float = 0.2, value: int = 1, 
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
        return f"You examine the {self.name}, but can't find any immediate use for it."