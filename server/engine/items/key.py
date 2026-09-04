# engine/items/key.py
from typing import Optional
from engine.items.item import Item

class Key(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Key",
                 description: str = "No description", weight: float = 0.1,
                 value: int = 15, target_id: Optional[str] = None, **kwargs):
        
        if 'stackable' in kwargs:
            kwargs.pop('stackable')
            
        super().__init__(obj_id, name, description, weight, value, stackable=False, target_id=target_id, **kwargs)
        self.update_property("stackable", False)

    def use(self, user, target: Optional[Item] = None, **kwargs) -> str:
        if not target:
            return f"What do you want to use the {self.name} on?"

        if hasattr(target, 'toggle_lock') and callable(getattr(target, 'toggle_lock', None)):
            success = getattr(target, 'toggle_lock')(self)
            
            if success:
                is_locked = target.get_property("locked")
                if is_locked:
                    return f"You lock the {target.name} with the {self.name}."
                else:
                    return f"You unlock the {target.name} with the {self.name}."
            else:
                return f"The {self.name} doesn't fit the lock on the {target.name}."
        else:
            return f"You can't use the {self.name} on the {target.name}."