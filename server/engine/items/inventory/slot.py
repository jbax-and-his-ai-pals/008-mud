# engine/items/inventory/slot.py
from typing import Dict, Any, Optional, Tuple
from engine.items.item import Item
from engine.items.item_factory import ItemFactory

class InventorySlot:
    """Represents a single slot in an inventory that can hold items."""

    def __init__(self, item: Optional[Item] = None, quantity: int = 1):
        self.item = item
        # Ensure quantity matches stackability
        if item and not item.stackable:
             self.quantity = 1
        else:
             self.quantity = quantity if item else 0 # Quantity is 0 if no item

    def add(self, item: Item, quantity: int = 1) -> int:
        """Adds quantity to existing item or sets new item."""
        if not self.item:
            self.item = item
            self.quantity = quantity if item.stackable else 1
            return quantity # Added all requested

        if self.item.obj_id == item.obj_id and self.item.stackable:
            self.quantity += quantity
            return quantity

        return 0 # Could not add to this slot

    def remove(self, quantity: int = 1) -> Tuple[Optional[Item], int]:
        """Removes quantity, clears slot if quantity becomes zero."""
        if not self.item: return None, 0

        quantity_to_remove = min(self.quantity, quantity)
        removed_item = self.item # Keep reference to the item type

        self.quantity -= quantity_to_remove

        if self.quantity <= 0:
            self.item = None # Clear the slot fully
            self.quantity = 0

        return removed_item, quantity_to_remove

    def to_dict(self) -> Dict[str, Any]:
        return {"item": self.item.to_dict() if self.item else None, "quantity": self.quantity}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InventorySlot':
        item = ItemFactory.from_dict(data["item"]) if data.get("item") else None
        return cls(item, data.get("quantity", 1 if item else 0))