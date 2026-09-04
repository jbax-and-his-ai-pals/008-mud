# engine/items/inventory/display.py
from typing import TYPE_CHECKING, cast
from engine.config import (
    FORMAT_CATEGORY, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_ERROR
)

if TYPE_CHECKING:
    from engine.items.inventory.core import Inventory

# Helper for sorting
def _get_item_sort_key(slot):
    if slot.item:
        return (type(slot.item).__name__, slot.item.name)
    return ("", "")

class InventoryDisplayMixin:
    """Mixin for generating text representations of the inventory."""

    def list_items(self) -> str:
        # Cast self to Inventory to satisfy static analysis
        inventory = cast('Inventory', self)
        
        if all(not slot.item for slot in inventory.slots):
            return f"{FORMAT_CATEGORY}Your inventory is empty.{FORMAT_RESET}"

        # Sort before displaying for tidiness
        inventory.sort_items()

        result = []
        items_found = False
        for i, slot in enumerate(inventory.slots):
            if slot.item:
                items_found = True
                if slot.item.stackable and slot.quantity > 1:
                    item_text = f"- {FORMAT_HIGHLIGHT}{slot.item.name}{FORMAT_RESET} (x{slot.quantity})"
                else:
                    item_text = f"- {FORMAT_HIGHLIGHT}{slot.item.name}{FORMAT_RESET}"
                
                # Add weight info per item/stack
                total_stack_weight = slot.item.weight * slot.quantity
                item_text += f" [{total_stack_weight:.1f} wt]"
                result.append(item_text)

        if not items_found: 
            return f"{FORMAT_CATEGORY}Your inventory is empty.{FORMAT_RESET}"

        # Weight and Slot info
        total_weight = inventory.get_total_weight()
        weight_percent = (total_weight / inventory.max_weight) * 100 if inventory.max_weight > 0 else 0
        
        if weight_percent >= 90: 
            weight_text = f"{FORMAT_ERROR}{total_weight:.1f}/{inventory.max_weight:.1f}{FORMAT_RESET}"
        elif weight_percent >= 75: 
            weight_text = f"{FORMAT_HIGHLIGHT}{total_weight:.1f}/{inventory.max_weight:.1f}{FORMAT_RESET}"
        else: 
            weight_text = f"{total_weight:.1f}/{inventory.max_weight:.1f}"
            
        weight_info = f"{FORMAT_CATEGORY}Total weight:{FORMAT_RESET} {weight_text}"

        used_slots = inventory.max_slots - inventory.get_empty_slots()
        slot_percent = (used_slots / inventory.max_slots) * 100 if inventory.max_slots > 0 else 0
        
        if slot_percent >= 90: 
            slot_text = f"{FORMAT_ERROR}{used_slots}/{inventory.max_slots}{FORMAT_RESET}"
        elif slot_percent >= 75: 
            slot_text = f"{FORMAT_HIGHLIGHT}{used_slots}/{inventory.max_slots}{FORMAT_RESET}"
        else: 
            slot_text = f"{used_slots}/{inventory.max_slots}"
            
        slot_info = f"{FORMAT_CATEGORY}Slots used:{FORMAT_RESET} {slot_text}"

        return "\n".join(result) + f"\n\n{weight_info}\n{slot_info}"

    def sort_items(self) -> None:
        """Sorts the inventory, grouping items by type and then alphabetically."""
        inventory = cast('Inventory', self)
        
        item_slots = [slot for slot in inventory.slots if slot.item]
        empty_slots = [slot for slot in inventory.slots if not slot.item]

        item_slots.sort(key=_get_item_sort_key)

        inventory.slots = item_slots + empty_slots