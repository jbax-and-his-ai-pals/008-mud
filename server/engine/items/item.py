# engine/items/item.py
from typing import Dict, Any, List, Optional
from engine.game_object import GameObject

class Item(GameObject):
    """Base class for all items in the game."""

    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Item",
                 description: str = "No description", weight: float = 1.0,
                 value: int = 0, stackable: bool = False,
                 equip_slot: Optional[List[str]] = None,
                 **kwargs):
        super().__init__(obj_id, name, description)
        # These are set directly on the instance
        self.weight = weight
        self.value = value
        self.stackable = stackable # Set initial value based on argument

        # Store core properties *also* in the properties dictionary for consistency
        self.update_property("weight", self.weight)
        self.update_property("value", self.value)
        self.update_property("stackable", self.stackable)
        if equip_slot:
            self.update_property("equip_slot", equip_slot)

        # Store any additional properties from subclasses
        # Skip keys that are already core attributes or GameObject attributes
        # Added 'world' to skip_keys to prevent serialization errors if passed in kwargs
        skip_keys = {"weight", "value", "stackable", "equip_slot", "name", "description", "obj_id", "id", "world"}
        for key, kwarg_value in kwargs.items():
             if key not in skip_keys:
                  self.update_property(key, kwarg_value)

    def examine(self) -> str:
        base_desc = f"{self.name}\n\n{self.description}\n\nWeight: {self.weight}, Value: {self.value}"
        equip_slots = self.get_property("equip_slot")
        if equip_slots:
            slots_str = ", ".join([s.replace('_', ' ') for s in equip_slots])
            base_desc += f"\nEquip Slot(s): {slots_str}"
        extra_props = []
        skip_keys = {"weight", "value", "stackable", "equip_slot", "name", "description", "id", "obj_id", "type", "world"}
        for key, value in self.properties.items():
            if key not in skip_keys:
                if isinstance(value, (int, float, str, bool)):
                    formatted_name = key.replace('_', ' ').title()
                    extra_props.append(f"{formatted_name}: {value}")
        if extra_props:
            base_desc += "\n\n" + "\n".join(extra_props)
        return base_desc

    def use(self, user, **kwargs) -> str:
        return f"You don't know how to use the {self.name}."

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        # Ensure core properties are present at top level for compatibility/readability
        data["weight"] = self.weight
        data["value"] = self.value
        data["stackable"] = self.stackable
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Item':
        """
        Create an item from a dictionary. Revised logic.
        """
        # 1. Create the instance using the specific class (cls)
        #    Pass only obj_id, name, description initially. __init__ will handle defaults.
        item = cls(
            obj_id=data.get("obj_id") or data.get("id"),
            name=data.get("name", "Unknown Item"),
            description=data.get("description", "No description"),
            # Let weight/value/stackable use __init__ defaults or be set below
        )

        # 2. Load all properties from the dictionary first.
        #    This allows subclasses in their __init__ to set default properties
        #    which might then be overwritten by the loaded data.
        item.properties = data.get("properties", {}).copy()

        # 3. Explicitly set core attributes on the instance, checking both
        #    the top-level data and the loaded properties dictionary.
        #    Fall back to the value potentially set by __init__.
        item.weight = data.get("weight", item.properties.get("weight", item.weight))
        item.value = data.get("value", item.properties.get("value", item.value))
        item.stackable = data.get("stackable", item.properties.get("stackable", item.stackable))

        # 4. Ensure these core attributes are also updated *in* the properties dict
        #    for consistency if they were loaded from top-level data.
        item.update_property("weight", item.weight)
        item.update_property("value", item.value)
        item.update_property("stackable", item.stackable)

        # Load equip_slot specifically if present in properties
        equip_slot = item.properties.get("equip_slot")
        if equip_slot:
             item.update_property("equip_slot", equip_slot) # Ensure it's in properties

        # Note: Subclasses can override from_dict to load *their* specific non-property
        # attributes after calling super().from_dict(data) if needed.

        return item