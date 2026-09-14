# engine/items/inventory/core.py
from collections import Counter
from typing import Callable, Iterable, List, Optional, Tuple
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
        return self.remove_item_instances([item_instance])

    def select_items(
        self,
        obj_id: str,
        quantity: int,
        *,
        predicate: Optional[Callable[[Item], bool]] = None,
        sort_key: Optional[Callable[[Item], object]] = None,
    ) -> List[Item]:
        """Select exact inventory instances without mutating the inventory.

        A stack contributes the same instance once per requested unit.  That
        representation lets callers later consume precisely the candidates
        they inspected, whether they are unique quality-bearing items or an
        ordinary stack.
        """
        if quantity <= 0:
            return []
        candidates = [
            slot for slot in self.slots
            if slot.item is not None and slot.item.obj_id == obj_id
            and (predicate is None or predicate(slot.item))
        ]
        if sort_key is not None:
            candidates.sort(key=lambda slot: sort_key(slot.item), reverse=True)

        selected: List[Item] = []
        for slot in candidates:
            selected.extend([slot.item] * min(slot.quantity, quantity - len(selected)))
            if len(selected) >= quantity:
                break
        return selected

    def remove_item_instances(self, item_instances: Iterable[Item]) -> bool:
        """Atomically remove the exact item units supplied by a caller.

        The method validates every requested identity and quantity before
        touching a slot.  Callers can therefore safely award a reward only
        after this returns true; a stale or mismatched selection cannot cause
        a partial spend.
        """
        requested = [item for item in item_instances if item is not None]
        if not requested:
            return False
        removal_plan = self._exact_removal_plan(requested)
        if removal_plan is None:
            return False
        slots_by_id = {id(slot): slot for slot in self.slots}
        for slot_id, count in removal_plan.items():
            removed_item, removed_count = slots_by_id[slot_id].remove(count)
            if removed_item is None or removed_count != count:
                # This is unreachable after the validation above unless an
                # external mutation races the inventory; do not report a
                # successful transaction in that case.
                return False
        return True

    def _exact_removal_plan(self, item_instances: Iterable[Item]) -> Optional[dict[int, int]]:
        """Return per-slot quantities for an exact-unit removal, or None."""
        requested = [item for item in item_instances if item is not None]
        if not requested:
            return None
        requested_counts = Counter(id(item) for item in requested)
        candidates = {
            item_id: [slot for slot in self.slots if slot.item is not None and id(slot.item) == item_id]
            for item_id in requested_counts
        }
        if any(not slots or sum(slot.quantity for slot in slots) < requested_counts[item_id]
               for item_id, slots in candidates.items()):
            return None
        plan: dict[int, int] = {}
        for item_id, count in requested_counts.items():
            remaining = count
            for slot in candidates[item_id]:
                removed_here = min(slot.quantity, remaining)
                if removed_here:
                    plan[id(slot)] = removed_here
                    remaining -= removed_here
                if remaining == 0:
                    break
        return plan

    def can_add_item_after_removing(
        self, item: Item, quantity: int, removed_items: Iterable[Item]
    ) -> Tuple[bool, str]:
        """Check output capacity against the inventory after an exact spend."""
        if quantity <= 0:
            return True, ""
        selected = [entry for entry in removed_items if entry is not None]
        # Recipes with no ingredients are valid authored rewards.  They do
        # not spend anything, but still need the ordinary capacity check.
        removal_plan = {} if not selected else self._exact_removal_plan(selected)
        if removal_plan is None:
            return False, "The selected ingredients are no longer available."

        current_weight = self.get_total_weight()
        slots_by_id = {id(slot): slot for slot in self.slots}
        removed_weight = sum(slots_by_id[slot_id].item.weight * count for slot_id, count in removal_plan.items())
        if current_weight - removed_weight + item.weight * quantity > self.max_weight:
            return False, f"Adding {item.name} would exceed your carry weight ({self.max_weight:.1f})."

        remaining_stack = any(
            slot.item is not None
            and slot.item.obj_id == item.obj_id
            and slot.item.stackable
            and slot.quantity - removal_plan.get(id(slot), 0) > 0
            for slot in self.slots
        )
        if item.stackable and remaining_stack:
            return True, ""
        freed_slots = sum(
            1 for slot in self.slots
            if slot.item is not None and slot.quantity == removal_plan.get(id(slot), 0)
        )
        empty_slots = self.get_empty_slots() + freed_slots
        slots_needed = 1 if item.stackable else quantity
        if empty_slots < slots_needed:
            return False, f"You don't have enough empty inventory slots for {item.name}."
        return True, ""
