# engine/items/inventory/core.py
from typing import List, Optional, Tuple
from engine.items.item import Item
from .slot import InventorySlot
from .display import InventoryDisplayMixin
from .persistence import InventoryPersistenceMixin

class Inventory(InventoryDisplayMixin, InventoryPersistenceMixin):
    """
    Manages a collection of items in inventory slots.
    Mixins handle display strings and serialization.
    """

    def __init__(self, max_slots: int = 20, max_weight: float = 100.0):
        self.slots: List[InventorySlot] = [InventorySlot() for _ in range(max_slots)]
        self.max_slots = max_slots
        self.max_weight = max_weight

    def can_add_item(self, item: Item, quantity: int = 1) -> Tuple[bool, str]:
         """Check weight and slot constraints before adding."""
         current_weight = self.get_total_weight()
         added_weight = item.weight * quantity
         if current_weight + added_weight > self.max_weight:
             return False, f"Adding {item.name} would exceed your carry weight ({self.max_weight:.1f})."

         remaining_quantity = quantity
         # FIX: Use len(self.slots) to ensure list size matches iteration loop
         temp_slots_used = [False] * len(self.slots)

         # Check existing stacks
         if item.stackable:
              for i, slot in enumerate(self.slots):
                   if slot.item and slot.item.obj_id == item.obj_id:
                        temp_slots_used[i] = True 
                        remaining_quantity = 0 
                        break 

         # Check empty slots needed
         if remaining_quantity > 0:
             slots_needed = remaining_quantity if not item.stackable else 1
             empty_slots_available = 0
             for i, slot in enumerate(self.slots):
                  if not slot.item and not temp_slots_used[i]:
                       empty_slots_available += 1

             if empty_slots_available < slots_needed:
                  return False, f"You don't have enough empty inventory slots for {item.name}."

         return True, ""

    def add_item(self, item: Item, quantity: int = 1) -> Tuple[bool, str]:
        can_add, message = self.can_add_item(item, quantity)
        if not can_add:
             return False, message

        # Add to existing stacks
        if item.stackable:
            for slot in self.slots:
                if slot.item and slot.item.obj_id == item.obj_id:
                    added = slot.add(item, quantity)
                    quantity -= added
                    if quantity <= 0:
                        return True, f"Added {item.name} to inventory."

        # Add to empty slots
        while quantity > 0:
            empty_slot = next((slot for slot in self.slots if not slot.item), None)
            if not empty_slot:
                 return False, f"Not enough space for the remaining {quantity} {item.name}."

            to_add_this_slot = 1 if not item.stackable else quantity
            empty_slot.add(item, to_add_this_slot)
            quantity -= to_add_this_slot

        return True, f"Added {item.name} to inventory."

    def remove_item(self, obj_id: str, quantity: int = 1) -> Tuple[Optional[Item], int, str]:
        """
        Remove an item from the inventory by obj_id.
        Returns (ItemInstance, CountRemoved, Message).
        """
        total_available = sum(slot.quantity for slot in self.slots
                             if slot.item and slot.item.obj_id == obj_id)

        if total_available == 0:
            instance_to_remove = self.find_item_by_id(obj_id)
            if instance_to_remove:
                 if self.remove_item_instance(instance_to_remove):
                      return instance_to_remove, 1, f"Removed {instance_to_remove.name}."
                 else:
                      return None, 0, f"Failed to remove specific instance {obj_id}."
            else:
                 return None, 0, "You don't have that item."

        quantity_to_remove = min(total_available, quantity)
        actual_removed_count = 0
        last_removed_instance: Optional[Item] = None

        # Iterate backwards
        for slot in reversed(self.slots):
            if slot.item and slot.item.obj_id == obj_id:
                 if actual_removed_count < quantity_to_remove:
                      needed = quantity_to_remove - actual_removed_count
                      removed_item_type, removed_from_slot = slot.remove(needed)

                      if removed_item_type and removed_from_slot > 0:
                           last_removed_instance = removed_item_type 
                           actual_removed_count += removed_from_slot

            if actual_removed_count >= quantity_to_remove:
                 break

        if last_removed_instance:
             return last_removed_instance, actual_removed_count, f"Removed {actual_removed_count} {last_removed_instance.name}."
        else:
             return None, 0, "Error removing item."

    def get_item(self, obj_id: str) -> Optional[Item]:
        for slot in self.slots:
            if slot.item and slot.item.obj_id == obj_id:
                return slot.item
        return None

    def get_total_weight(self) -> float:
        return sum(slot.item.weight * slot.quantity for slot in self.slots if slot.item)

    def get_empty_slots(self) -> int:
        return sum(1 for slot in self.slots if not slot.item)

    def find_item_by_name(self, name: str, partial: bool = True, exclude: Optional[Item] = None) -> Optional[Item]:
        name_lower = name.lower()
        for slot in self.slots:
            if slot.item:
                if exclude and slot.item is exclude: continue

                match = False
                if partial and name_lower in slot.item.name.lower(): match = True
                elif not partial and name_lower == slot.item.name.lower(): match = True
                elif name_lower == slot.item.obj_id: match = True

                if match: return slot.item
        return None

    def count_item(self, obj_id: str) -> int:
        count = 0
        for slot in self.slots:
            if slot.item and slot.item.obj_id == obj_id:
                count += slot.quantity
        return count

    def find_item_by_id(self, obj_id: str) -> Optional[Item]:
        for slot in self.slots:
            if slot.item and slot.item.obj_id == obj_id:
                return slot.item 
        return None

    def remove_item_instance(self, item_instance: Item) -> bool:
        if not item_instance: return False

        for slot in self.slots:
            if slot.item is item_instance:
                removed_type, removed_count = slot.remove(1) 
                return removed_type is not None and removed_count == 1
        return False