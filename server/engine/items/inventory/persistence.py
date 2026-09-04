# engine/items/inventory/persistence.py
from typing import Dict, Any, TYPE_CHECKING, Optional, cast
from engine.utils.utils import _serialize_item_reference
from engine.items.item_factory import ItemFactory
from .slot import InventorySlot

if TYPE_CHECKING:
    from engine.items.inventory.core import Inventory
    from engine.world.world import World

class InventoryPersistenceMixin:
    """Mixin handling JSON serialization/deserialization."""

    def to_dict(self, world: 'World') -> Dict[str, Any]:
        """Serialize inventory using item references."""
        # Cast self to Inventory to satisfy static analysis for attribute access
        inventory = cast('Inventory', self)
        
        serialized_slots = []
        for slot in inventory.slots:
            if slot.item:
                item_ref = _serialize_item_reference(slot.item, slot.quantity, world)
                serialized_slots.append(item_ref)
            else:
                serialized_slots.append(None)

        return {
            "max_slots": inventory.max_slots,
            "max_weight": inventory.max_weight,
            "slots": serialized_slots
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], world: Optional['World']) -> 'Inventory':
        # Import core here to avoid circular imports
        from .core import Inventory
        
        if not world:
             print("Error: World context required to load inventory.")
             return Inventory(max_slots=data.get("max_slots", 20), max_weight=data.get("max_weight", 100.0))

        inventory = Inventory(max_slots=data.get("max_slots", 20), max_weight=data.get("max_weight", 100.0))
        loaded_slots_data = data.get("slots", [])
        inventory.slots = [] 

        for slot_data in loaded_slots_data:
            if slot_data and isinstance(slot_data, dict) and "item_id" in slot_data:
                item_id = slot_data["item_id"]
                quantity = slot_data.get("quantity", 1)
                overrides = slot_data.get("properties_override", {})

                item = ItemFactory.create_item_from_template(item_id, world, **overrides)

                if item:
                    actual_quantity = quantity if item.stackable else 1
                    inventory.slots.append(InventorySlot(item, actual_quantity))
                    if not item.stackable and quantity > 1:
                         print(f"Warning: Loaded non-stackable item '{item.name}' with quantity {quantity}. Set to 1.")
                else:
                    print(f"Warning: Failed to load item '{item_id}'. Adding empty slot.")
                    inventory.slots.append(InventorySlot()) 
            else:
                inventory.slots.append(InventorySlot())

        # Ensure correct number of slots
        while len(inventory.slots) < inventory.max_slots:
            inventory.slots.append(InventorySlot())
        inventory.slots = inventory.slots[:inventory.max_slots]

        return inventory