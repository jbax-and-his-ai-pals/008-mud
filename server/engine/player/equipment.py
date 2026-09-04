# engine/player/equipment.py
from typing import List, Tuple, Optional, TYPE_CHECKING, cast
import time
from engine.items.item import Item
from engine.config import FORMAT_ERROR, FORMAT_RESET

if TYPE_CHECKING:
    from engine.player.core import Player

class PlayerEquipmentMixin:
    """Mixin for handling player equipment logic."""

    def get_valid_slots(self, item: Item) -> List[str]:
        p = cast('Player', self)
        valid = []
        item_type_name = item.__class__.__name__
        
        # Check explicit slot property
        item_slots = item.get_property("equip_slot")
        if isinstance(item_slots, str): item_slots = [item_slots]
        if isinstance(item_slots, list):
             for slot in item_slots:
                  if slot in p.equipment: valid.append(slot)
             if valid: return valid
             
        # Fallback to type mapping
        if item_type_name in p.valid_slots_for_type:
             for slot in p.valid_slots_for_type[item_type_name]:
                  if slot in p.equipment: valid.append(slot)
             return valid
             
        return valid

    def equip_item(self, item: Item, slot_name: Optional[str] = None) -> Tuple[bool, str]:
        p = cast('Player', self)
        if not p.is_alive: return False, "You cannot equip items while dead."
        
        # Stat Requirements
        requirements = item.get_property("requirements", {})
        for stat, req_value in requirements.items():
            my_stat = p.get_effective_stat(stat)
            if my_stat < req_value:
                return False, f"You need {req_value} {stat.capitalize()} to equip {item.name} (Have: {my_stat})."

        # Determine Slot
        valid_slots = self.get_valid_slots(item)
        if not valid_slots: return False, f"You can't figure out how to equip the {item.name}."
        
        target_slot = None
        if slot_name:
            if slot_name in valid_slots: 
                target_slot = slot_name
            else: 
                return False, f"The {item.name} cannot be equipped in the '{slot_name}' slot. Valid: {', '.join(valid_slots)}"
        else:
            # Auto-find empty
            for s in valid_slots:
                if p.equipment[s] is None: 
                    target_slot = s
                    break
            if target_slot is None: 
                target_slot = valid_slots[0]

        # Verify Ownership
        if not p.inventory.get_item(item.obj_id): 
            return False, f"You don't have the {item.name} in your inventory."
        
        # Handle Swapping
        unequip_message = ""
        currently_equipped = p.equipment.get(target_slot)
        if currently_equipped:
            success, msg = self.unequip_item(target_slot)
            if not success: 
                return False, f"Could not unequip {currently_equipped.name} to make space: {msg}"
            unequip_message = f"(You unequip the {currently_equipped.name}) "

        # Execute Equip
        removed_item, _, remove_msg = p.inventory.remove_item(item.obj_id, 1)
        if not removed_item: 
            return False, f"Failed to remove {item.name} from inventory: {remove_msg}"
        
        p.equipment[target_slot] = item
        
        # Apply Equip Effects
        effect_data = item.get_property("equip_effect")
        if effect_data and isinstance(effect_data, dict): 
            p.apply_effect(effect_data, time.time())
            
        return True, f"{unequip_message}You equip the {item.name} in your {target_slot.replace('_', ' ')}."

    def unequip_item(self, slot_name: str) -> Tuple[bool, str]:
        p = cast('Player', self)
        if not p.is_alive: return False, "You cannot unequip items while dead."
        if slot_name not in p.equipment: return False, f"Invalid equipment slot: {slot_name}"
        
        item_to_unequip = p.equipment.get(slot_name)
        if not item_to_unequip: return False, f"You have nothing equipped in your {slot_name.replace('_', ' ')}."
        
        if item_to_unequip.get_property("cursed"):
            return False, f"{FORMAT_ERROR}You cannot remove the {item_to_unequip.name}! It binds to your flesh with a dark curse.{FORMAT_RESET}"

        # Remove Effects
        effect_data = item_to_unequip.get_property("equip_effect")
        if effect_data and isinstance(effect_data, dict):
            effect_name = effect_data.get("name")
            if effect_name: p.remove_effect(effect_name)

        # Move to Inventory
        success, add_message = p.inventory.add_item(item_to_unequip, 1)
        if not success: 
            # Re-apply effects if fail
            if effect_data: p.apply_effect(effect_data, time.time())
            return False, f"Could not unequip {item_to_unequip.name}: {add_message}"

        p.equipment[slot_name] = None
        return True, f"You unequip the {item_to_unequip.name} from your {slot_name.replace('_', ' ')}."

    def get_resistance(self, damage_type: str) -> int:
        p = cast('Player', self)
        # Call GameObject's get_resistance via super() logic proxy
        # Since mixins don't have super() to GameObject usually, we access stats directly
        # But Player calls super().get_resistance. The Mixin's version needs to add to that.
        # This method overrides the one in Player/GameObject chain.
        # We need the base resistance first.
        
        # NOTE: In Python's MRO, if Player inherits (EquipmentMixin, GameObject), 
        # super() here calls GameObject.
        
        total_res = super().get_resistance(damage_type) # type: ignore
        
        for item in p.equipment.values():
            if item:
                item_resistances = item.get_property("resistances", {})
                total_res += item_resistances.get(damage_type, 0)
                
        return total_res
