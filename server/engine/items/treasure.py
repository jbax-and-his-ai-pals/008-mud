# engine/items/treasure.py
from typing import Optional
from engine.items.item import Item

class Treasure(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Treasure",
                 description: str = "No description", weight: float = 0.5,
                 value: int = 100, **kwargs):
        
        is_stackable = kwargs.pop('stackable', False)
        
        super().__init__(
            obj_id=obj_id, 
            name=name, 
            description=description, 
            weight=weight, 
            value=value, 
            stackable=is_stackable, 
            treasure_type="generic",
            **kwargs
        )
    
    def use(self, user, **kwargs) -> str:
        return f"You admire the {self.name}. It looks quite valuable."